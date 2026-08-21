import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set RUN_POSTGRES_INTEGRATION=1 to run against PostgreSQL", allow_module_level=True)

from app.db import SessionLocal
from app.config import get_fixtures_dir
from app.ingestion import ingest_csv, ingest_json
from app.main import app
from app.models import IngestionError, Vehicle, VehiclePriceObservation, VehicleSourceRecord

FIXTURES = get_fixtures_dir()


def test_csv_ingestion_lifecycle_against_postgres() -> None:
    async def scenario() -> None:
        assert (FIXTURES / "dealer_feed_v1.csv").is_file(), f"Fixture is unavailable: {FIXTURES / 'dealer_feed_v1.csv'}"
        async with SessionLocal() as session:
            await session.execute(text("TRUNCATE ingestion_errors, vehicle_price_observations, vehicle_source_records, ingestion_runs, vehicles CASCADE"))
            await session.commit()

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                first_response = await client.post("/api/v1/ingestion/csv?fixture=dealer_feed_v1.csv")
            assert first_response.status_code == 201
            first_payload = first_response.json()
            assert (first_payload["status"], first_payload["inserted_records"], first_payload["updated_records"], first_payload["duplicate_records"], first_payload["invalid_records"]) == ("completed", 3, 0, 0, 0)
            accord = await session.scalar(select(Vehicle).where(Vehicle.vin == "1HGCM82633A004352"))
            assert accord is not None
            first_updated_at = accord.updated_at

            replay = await ingest_csv(session, FIXTURES / "dealer_feed_v1.csv")
            assert replay.status == "completed", replay.error_message
            assert (replay.inserted_records, replay.updated_records, replay.duplicate_records) == (0, 0, 3)
            await session.refresh(accord)
            assert accord.updated_at == first_updated_at
            assert await session.scalar(select(func.count()).select_from(VehicleSourceRecord)) == 3
            assert await session.scalar(select(func.count()).select_from(VehiclePriceObservation)) == 3

            updated = await ingest_csv(session, FIXTURES / "dealer_feed_v2.csv")
            assert updated.status == "completed", updated.error_message
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
            assert invalid.status == "completed", invalid.error_message
            assert (invalid.status, invalid.invalid_records) == ("completed", 2)
            assert await session.scalar(select(func.count()).select_from(IngestionError).where(IngestionError.ingestion_run_id == invalid.id)) == 2

            marketplace = await ingest_json(session, FIXTURES / "marketplace_feed.json")
            assert marketplace.status == "completed", marketplace.error_message
            assert (marketplace.inserted_records, marketplace.updated_records, marketplace.duplicate_records, marketplace.invalid_records) == (1, 2, 0, 1)
            accord = await session.scalar(select(Vehicle).where(Vehicle.vin == "1HGCM82633A004352"))
            assert accord.trim == "EX"  # marketplace EX-L conflict cannot overwrite dealer canonical data
            assert await session.scalar(select(func.count()).select_from(Vehicle)) == 5
            assert await session.scalar(select(func.count()).select_from(VehicleSourceRecord)) == 9
            assert await session.scalar(select(func.count()).select_from(VehiclePriceObservation)) == 9
            assert await session.scalar(select(func.count()).select_from(VehicleSourceRecord).where(VehicleSourceRecord.source_name == "marketplace_json", VehicleSourceRecord.source_record_id == "mk-1001")) == 1

            marketplace_replay = await ingest_json(session, FIXTURES / "marketplace_feed.json")
            assert marketplace_replay.status == "completed", marketplace_replay.error_message
            assert (marketplace_replay.inserted_records, marketplace_replay.updated_records, marketplace_replay.duplicate_records, marketplace_replay.invalid_records) == (0, 0, 3, 1)
            assert await session.scalar(select(func.count()).select_from(VehicleSourceRecord)) == 9
            assert await session.scalar(select(func.count()).select_from(VehiclePriceObservation)) == 9

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                sources = await client.get("/api/v1/vehicles/1HGCM82633A004352/sources")
                history = await client.get("/api/v1/vehicles/1HGCM82633A004352/price-history")
            assert sources.status_code == 200
            assert {source["source_name"] for source in sources.json()} == {"dealer_csv", "marketplace_json"}
            assert history.status_code == 200
            assert {observation["source_name"] for observation in history.json()} == {"dealer_csv", "marketplace_json"}

    asyncio.run(scenario())
