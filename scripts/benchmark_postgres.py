"""Measure repeatable localhost HTTP endpoint latency and capture PostgreSQL plans."""
import argparse, asyncio, json, os, statistics, time
from pathlib import Path
import asyncpg, httpx

async def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--iterations",type=int,default=30); p.add_argument("--plans-dir",default="/tmp/autostream-performance"); args=p.parse_args()
    dsn=os.environ.get("DATABASE_URL","postgresql://autostream:autostream@db:5432/autostream").replace("+asyncpg", ""); conn=await asyncpg.connect(dsn)
    vin=await conn.fetchval("SELECT vin FROM vehicles ORDER BY vin OFFSET (SELECT count(*)/2 FROM vehicles) LIMIT 1")
    operations={"vin_lookup":f"/api/v1/vehicles/{vin}","make_listing":"/api/v1/vehicles?make=Honda","provenance":f"/api/v1/vehicles/{vin}/sources","price_history":f"/api/v1/vehicles/{vin}/price-history","market_snapshot":f"/api/v1/vehicles/{vin}/market-snapshot","market_summary":"/api/v1/analytics/market-summary"}
    async with httpx.AsyncClient(base_url="http://localhost:8000",timeout=30) as client:
        results={}
        for name,path in operations.items():
            await client.get(path); samples=[]
            for _ in range(args.iterations):
                start=time.perf_counter(); response=await client.get(path); response.raise_for_status(); samples.append((time.perf_counter()-start)*1000)
            results[name]={"median_ms":round(statistics.median(samples),3),"p95_ms":round(sorted(samples)[max(0,int(len(samples)*.95)-1)],3),"min_ms":round(min(samples),3),"max_ms":round(max(samples),3),"iterations":args.iterations}
    plan_queries={"vin_lookup":("SELECT * FROM vehicles WHERE vin=$1",vin),"provenance":("SELECT * FROM vehicle_source_records s JOIN vehicles v ON v.id=s.vehicle_id WHERE v.vin=$1",vin),"latest_observation":("SELECT * FROM vehicle_price_observations o JOIN vehicles v ON v.id=o.vehicle_id WHERE v.vin=$1 ORDER BY o.observed_at DESC,o.id DESC LIMIT 1",vin),"market_snapshot":("SELECT * FROM vehicle_price_observations o JOIN vehicles v ON v.id=o.vehicle_id WHERE v.vin=$1 ORDER BY o.observed_at DESC,o.id DESC",vin),"market_summary":("SELECT DISTINCT ON (vehicle_id) vehicle_id,price FROM vehicle_price_observations ORDER BY vehicle_id,observed_at DESC,id DESC",None)}
    out=Path(args.plans_dir); out.mkdir(parents=True,exist_ok=True)
    for name,(query,param) in plan_queries.items():
        statement="EXPLAIN (ANALYZE, BUFFERS) "+query; rows=await conn.fetch(statement,*(([param]) if param else [])); (out/f"{name}.txt").write_text("\n".join(row[0] for row in rows)+"\n")
    print(json.dumps({"vin":vin,"results":results},indent=2)); await conn.close()
if __name__=="__main__": asyncio.run(main())
