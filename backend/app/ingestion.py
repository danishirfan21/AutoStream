import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
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

    for raw in adapter.fetch_records(path):
        run.total_records += 1
        source_id = raw.get("vin") or f"row-{run.total_records}"
        try:
            record = adapter.normalize_record(raw)
            source_id = record.vin
            digest = payload_hash(raw)
            existing_source = await session.scalar(select(VehicleSourceRecord.id).where(
                VehicleSourceRecord.source_name == adapter.source_name,
                VehicleSourceRecord.source_record_id == source_id,
                VehicleSourceRecord.payload_hash == digest,
            ))
            if existing_source:
                run.duplicate_records += 1
                continue

            existing_vehicle = await session.scalar(select(Vehicle).where(Vehicle.vin == record.vin))
            was_new = existing_vehicle is None
            values = {key: value for key, value in record.model_dump(exclude={"price", "mileage", "location", "source_timestamp"}).items() if value is not None}
            vehicle_insert = insert(Vehicle)
            stmt = vehicle_insert.values(vin=record.vin, **values).on_conflict_do_update(
                index_elements=[Vehicle.vin],
                set_={key: getattr(vehicle_insert.excluded, key) for key in values if key != "vin"},
            ).returning(Vehicle.id)
            vehicle_id = (await session.execute(stmt)).scalar_one()
            if was_new:
                run.inserted_records += 1
            else:
                run.updated_records += 1

            session.add(VehicleSourceRecord(
                vehicle_id=vehicle_id, source_name=adapter.source_name, source_record_id=source_id,
                raw_payload=raw, source_timestamp=record.source_timestamp, payload_hash=digest,
            ))
            if record.price is not None:
                session.add(VehiclePriceObservation(
                    vehicle_id=vehicle_id, source_name=adapter.source_name, price=record.price,
                    mileage=record.mileage, location=record.location,
                    observed_at=record.source_timestamp or datetime.now(timezone.utc),
                ))
        except Exception as exc:
            run.invalid_records += 1
            session.add(IngestionError(
                ingestion_run_id=run.id, source_record_id=source_id, error_type=type(exc).__name__,
                error_message=str(exc), raw_payload=raw,
            ))

    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(run)
    return run
