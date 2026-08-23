"""Generate deterministic synthetic benchmark data directly in PostgreSQL."""
import argparse, asyncio, os, random, time, uuid
from datetime import datetime, timedelta, timezone
import asyncpg

MAKES = {"Honda": ["Accord", "Civic"], "Toyota": ["Camry", "RAV4"], "Ford": ["F-150", "Escape"], "Tesla": ["Model 3", "Model Y"], "Nissan": ["Altima", "Rogue"], "BMW": ["330i", "X3"], "Hyundai": ["Elantra", "Tucson"], "Kia": ["K5", "Sportage"]}
SOURCES = ("dealer_csv", "marketplace_json", "auction_feed")
LOCATIONS = ("Dallas, TX", "Austin, TX", "Miami, FL", "Seattle, WA", "Denver, CO")
NAMESPACE = uuid.UUID("a45d1fb6-c493-44ee-a2cd-6c646ffcb8c0")

def batches(values, size=5000):
    for start in range(0, len(values), size): yield values[start:start + size]

async def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--vehicles", type=int, default=10000); parser.add_argument("--reset", action="store_true")
    args = parser.parse_args(); rng = random.Random(20260823); now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dsn = os.environ.get("DATABASE_URL", "postgresql://autostream:autostream@db:5432/autostream").replace("+asyncpg", "")
    conn = await asyncpg.connect(dsn); started = time.perf_counter()
    try:
        if args.reset: await conn.execute("TRUNCATE vehicle_enrichments, ingestion_errors, vehicle_price_observations, vehicle_source_records, ingestion_runs, vehicles CASCADE")
        vehicles=[]; sources=[]; observations=[]
        for i in range(args.vehicles):
            make = tuple(MAKES)[i % len(MAKES)]; model = MAKES[make][i % 2]; vehicle_id = uuid.uuid5(NAMESPACE, f"vehicle-{i}")
            vin = f"B{i:016d}"[-17:]; vehicles.append((vehicle_id, vin, 2012 + i % 14, make, model, "Synthetic"))
            for version in range(1 + (i % 3)):
                source = SOURCES[version % len(SOURCES)]; stamp = now - timedelta(days=version * 30)
                sources.append((uuid.uuid5(NAMESPACE, f"source-{i}-{version}"), vehicle_id, source, f"{source}-{i}-{version}", {"synthetic": True, "version": version}, stamp, stamp, f"{i:064x}"))
            for n in range(1 + (i % 12)):
                observed = now - timedelta(days=90 - n * 7, minutes=i % 60)
                observations.append((uuid.uuid5(NAMESPACE, f"observation-{i}-{n}"), vehicle_id, SOURCES[n % len(SOURCES)], 18000 + (i % 20000) + n * 25, 5000 + (i * 17 + n * 100) % 150000, LOCATIONS[i % len(LOCATIONS)], observed))
        for chunk in batches(vehicles): await conn.executemany("INSERT INTO vehicles (id,vin,year,make,model,trim) VALUES ($1,$2,$3,$4,$5,$6)", chunk)
        for chunk in batches(sources): await conn.executemany("INSERT INTO vehicle_source_records (id,vehicle_id,source_name,source_record_id,raw_payload,source_timestamp,ingested_at,payload_hash) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)", chunk)
        for chunk in batches(observations): await conn.executemany("INSERT INTO vehicle_price_observations (id,vehicle_id,source_name,price,mileage,location,observed_at) VALUES ($1,$2,$3,$4,$5,$6,$7)", chunk)
        await conn.execute("ANALYZE")
        print(f"BENCHMARK_DATA vehicles={len(vehicles)} sources={len(sources)} observations={len(observations)} load_seconds={time.perf_counter()-started:.3f}")
    finally: await conn.close()
if __name__ == "__main__": asyncio.run(main())
