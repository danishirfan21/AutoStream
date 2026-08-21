from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import engine, get_session
from app.config import get_fixtures_dir
from app.enrichment import enrich_nhtsa
from app.ingestion import ingest_csv, ingest_json
from app.models import IngestionError, IngestionRun, Vehicle, VehicleEnrichment, VehiclePriceObservation, VehicleSourceRecord
from app.schemas import EnrichmentOut, ErrorOut, PriceObservationOut, RunOut, SourceRecordOut, VehicleOut

app = FastAPI(title="AutoStream", version="0.1.0")
FIXTURES = get_fixtures_dir()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(select(1))
    return {"status": "ready"}


@app.post("/api/v1/ingestion/csv", response_model=RunOut, status_code=201)
async def import_csv(fixture: str = "dealer_feed_v1.csv", session: AsyncSession = Depends(get_session)) -> IngestionRun:
    path = (FIXTURES / fixture).resolve()
    if FIXTURES not in path.parents or not path.is_file() or path.suffix.lower() != ".csv":
        raise HTTPException(404, "CSV fixture not found")
    return await ingest_csv(session, path)


@app.post("/api/v1/ingestion/json", response_model=RunOut, status_code=201)
async def import_json(fixture: str = "marketplace_feed.json", session: AsyncSession = Depends(get_session)) -> IngestionRun:
    path = (FIXTURES / fixture).resolve()
    if FIXTURES not in path.parents or not path.is_file() or path.suffix.lower() != ".json":
        raise HTTPException(404, "JSON fixture not found")
    return await ingest_json(session, path)


@app.get("/api/v1/ingestion/runs", response_model=list[RunOut])
async def list_runs(session: AsyncSession = Depends(get_session)) -> list[IngestionRun]:
    return list((await session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()))).all())


@app.get("/api/v1/ingestion/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: UUID, session: AsyncSession = Depends(get_session)) -> IngestionRun:
    run = await session.get(IngestionRun, run_id)
    if not run:
        raise HTTPException(404, "Ingestion run not found")
    return run


@app.get("/api/v1/ingestion/runs/{run_id}/errors", response_model=list[ErrorOut])
async def get_errors(run_id: UUID, session: AsyncSession = Depends(get_session)) -> list[IngestionError]:
    return list((await session.scalars(select(IngestionError).where(IngestionError.ingestion_run_id == run_id))).all())


@app.get("/api/v1/vehicles", response_model=list[VehicleOut])
async def list_vehicles(make: str | None = None, model: str | None = None, year: int | None = None,
                        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                        session: AsyncSession = Depends(get_session)) -> list[Vehicle]:
    stmt = select(Vehicle).order_by(Vehicle.vin).limit(limit).offset(offset)
    if make: stmt = stmt.where(Vehicle.make.ilike(make.strip()))
    if model: stmt = stmt.where(Vehicle.model.ilike(model.strip()))
    if year: stmt = stmt.where(Vehicle.year == year)
    return list((await session.scalars(stmt)).all())


@app.get("/api/v1/vehicles/{vin}", response_model=VehicleOut)
async def get_vehicle(vin: str, session: AsyncSession = Depends(get_session)) -> Vehicle:
    vehicle = await session.scalar(select(Vehicle).where(Vehicle.vin == vin.upper()))
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    return vehicle


@app.get("/api/v1/vehicles/{vin}/sources", response_model=list[SourceRecordOut])
async def vehicle_sources(vin: str, session: AsyncSession = Depends(get_session)) -> list[VehicleSourceRecord]:
    vehicle = await session.scalar(select(Vehicle).where(Vehicle.vin == vin.upper()))
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    stmt = select(VehicleSourceRecord).where(VehicleSourceRecord.vehicle_id == vehicle.id).order_by(VehicleSourceRecord.ingested_at)
    return list((await session.scalars(stmt)).all())


@app.get("/api/v1/vehicles/{vin}/price-history", response_model=list[PriceObservationOut])
async def price_history(vin: str, session: AsyncSession = Depends(get_session)) -> list[VehiclePriceObservation]:
    vehicle = await session.scalar(select(Vehicle).where(Vehicle.vin == vin.upper()))
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    stmt = select(VehiclePriceObservation).where(VehiclePriceObservation.vehicle_id == vehicle.id).order_by(VehiclePriceObservation.observed_at)
    return list((await session.scalars(stmt)).all())


@app.post("/api/v1/vehicles/{vin}/enrich/nhtsa", response_model=EnrichmentOut)
async def enrich_vehicle(vin: str, session: AsyncSession = Depends(get_session)) -> VehicleEnrichment:
    try:
        return await enrich_nhtsa(session, vin)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/v1/vehicles/{vin}/enrichment", response_model=list[EnrichmentOut])
async def vehicle_enrichment(vin: str, session: AsyncSession = Depends(get_session)) -> list[VehicleEnrichment]:
    vehicle = await session.scalar(select(Vehicle).where(Vehicle.vin == vin.upper()))
    if not vehicle:
        raise HTTPException(404, "Vehicle not found")
    return list((await session.scalars(select(VehicleEnrichment).where(VehicleEnrichment.vehicle_id == vehicle.id).order_by(VehicleEnrichment.fetched_at.desc()))).all())
