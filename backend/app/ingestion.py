import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import CsvFeedAdapter
from app.models import IngestionError, IngestionRun, Vehicle, VehiclePriceObservation, VehicleSourceRecord


def payload_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


async def ingest_csv(session: AsyncSession, path: Path) -> IngestionRun:
    adapter = CsvFeedAdapter()
    run = IngestionRun(source_name=adapter.source_name, status="running")
    session.add(run)
    await session.flush()

    try:
        rows = adapter.fetch_records(path)
        for raw in rows:
            run.total_records += 1
            source_id = raw.get("vin") or f"row-{run.total_records}"
            try:
                record = adapter.normalize_record(raw)
                source_id = record.vin
                digest = payload_hash(raw)
                async with session.begin_nested():
                    existing_source = await session.scalar(select(VehicleSourceRecord.id).where(
                        VehicleSourceRecord.source_name == adapter.source_name,
                        VehicleSourceRecord.source_record_id == source_id,
                        VehicleSourceRecord.payload_hash == digest,
                    ))
                    if existing_source:
                        run.duplicate_records += 1
                        continue

                    vehicle = await session.scalar(select(Vehicle).where(Vehicle.vin == record.vin))
                    canonical = record.model_dump(exclude={"vin", "price", "mileage", "location", "source_timestamp"}, exclude_none=True)
                    if vehicle is None:
                        vehicle_id = (await session.execute(insert(Vehicle).values(vin=record.vin, **canonical).returning(Vehicle.id))).scalar_one()
                        run.inserted_records += 1
                    else:
                        vehicle_id = vehicle.id
                        changes = {key: value for key, value in canonical.items() if getattr(vehicle, key) != value}
                        if changes:
                            changes["updated_at"] = func.now()
                            await session.execute(Vehicle.__table__.update().where(Vehicle.id == vehicle_id).values(**changes))
                        run.updated_records += 1

                    session.add(VehicleSourceRecord(
                        vehicle_id=vehicle_id, source_name=adapter.source_name, source_record_id=source_id,
                        raw_payload=raw, source_timestamp=record.source_timestamp, payload_hash=digest,
                    ))
                    if record.price is not None:
                        observation = insert(VehiclePriceObservation).values(
                            vehicle_id=vehicle_id, source_name=adapter.source_name, price=record.price,
                            mileage=record.mileage, location=record.location,
                            observed_at=record.source_timestamp or datetime.now(timezone.utc),
                        ).on_conflict_do_nothing(constraint="uq_price_observation")
                        await session.execute(observation)
            except Exception as exc:
                run.invalid_records += 1
                session.add(IngestionError(
                    ingestion_run_id=run.id, source_record_id=source_id, error_type=type(exc).__name__,
                    error_message=str(exc), raw_payload=raw,
                ))
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        session.add(IngestionError(
            ingestion_run_id=run.id, source_record_id=None, error_type=type(exc).__name__,
            error_message=str(exc), raw_payload={},
        ))
        await session.commit()
        await session.refresh(run)
        return run

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(run)
    return run
