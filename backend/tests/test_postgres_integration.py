import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set RUN_POSTGRES_INTEGRATION=1 to run against PostgreSQL", allow_module_level=True)

from app.db import SessionLocal
from app.ingestion import ingest_csv
from app.models import IngestionError, Vehicle, VehiclePriceObservation, VehicleSourceRecord

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_csv_ingestion_lifecycle_against_postgres() -> None:
    async def scenario() -> None:
        async with SessionLocal() as session:
            await session.execute(text("TRUNCATE ingestion_errors, vehicle_price_observations, vehicle_source_records, ingestion_runs, vehicles CASCADE"))
            await session.commit()

            first = await ingest_csv(session, FIXTURES / "dealer_feed_v1.csv")
            assert (first.status, first.inserted_records, first.updated_records, first.duplicate_records, first.invalid_records) == ("completed", 3, 0, 0, 0)
            accord = await session.scalar(select(Vehicle).where(Vehicle.vin == "1HGCM82633A004352"))
            assert accord is not None
            first_updated_at = accord.updated_at

            replay = await ingest_csv(session, FIXTURES / "dealer_feed_v1.csv")
            assert (replay.inserted_records, replay.updated_records, replay.duplicate_records) == (0, 0, 3)
            await session.refresh(accord)
            assert accord.updated_at == first_updated_at
            assert await session.scalar(select(func.count()).select_from(VehicleSourceRecord)) == 3
            assert await session.scalar(select(func.count()).select_from(VehiclePriceObservation)) == 3

            updated = await ingest_csv(session, FIXTURES / "dealer_feed_v2.csv")
            assert (updated.inserted_records, updated.updated_records, updated.duplicate_records, updated.invalid_records) == (1, 2, 1, 0)
            await session.refresh(accord)
            assert accord.updated_at == first_updated_at  # price/mileage are observations, not canonical fields
            tesla = await session.scalar(select(Vehicle).where(Vehicle.vin == "5YJ3E1EA7PF123456"))
            assert tesla.trim == "Long Range AWD"
            assert tesla.updated_at > first_updated_at
            assert await session.scalar(select(func.count()).select_from(Vehicle)) == 4
            assert await session.scalar(select(func.count()).select_from(VehicleSourceRecord)) == 6
            assert await session.scalar(select(func.count()).select_from(VehiclePriceObservation)) == 6

            invalid = await ingest_csv(session, FIXTURES / "invalid_feed.csv")
            assert (invalid.status, invalid.invalid_records) == ("completed", 2)
            assert await session.scalar(select(func.count()).select_from(IngestionError).where(IngestionError.ingestion_run_id == invalid.id)) == 2

    asyncio.run(scenario())
