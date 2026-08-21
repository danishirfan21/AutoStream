from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LATEST = "SELECT DISTINCT ON (vehicle_id) vehicle_id, price, mileage, location, observed_at, source_name FROM vehicle_price_observations ORDER BY vehicle_id, observed_at DESC, id DESC"


async def market_summary(session: AsyncSession) -> dict:
    row = (await session.execute(text(f"""WITH latest AS ({LATEST}) SELECT
      (SELECT count(*) FROM vehicles) AS total_vehicles,
      (SELECT count(*) FROM vehicle_source_records) AS total_source_records,
      (SELECT count(*) FROM vehicle_price_observations) AS total_price_observations,
      avg(price) AS average_latest_price, min(price) AS min_latest_price, max(price) AS max_latest_price,
      count(DISTINCT v.make) AS represented_makes, count(DISTINCT latest.location) AS represented_locations
      FROM latest JOIN vehicles v ON v.id=latest.vehicle_id WHERE latest.price IS NOT NULL"""))).mappings().one()
    return dict(row)


async def by_make(session: AsyncSession) -> list[dict]:
    rows = (await session.execute(text(f"""WITH latest AS ({LATEST}) SELECT v.make, count(*) AS vehicle_count,
      avg(latest.price) AS average_latest_price, min(latest.price) AS min_latest_price, max(latest.price) AS max_latest_price
      FROM vehicles v LEFT JOIN latest ON latest.vehicle_id=v.id GROUP BY v.make ORDER BY v.make"""))).mappings().all()
    return [dict(row) for row in rows]


async def snapshot(session: AsyncSession, vin: str) -> dict | None:
    row = (await session.execute(text("""WITH ordered AS (
      SELECT o.*, row_number() OVER (ORDER BY o.observed_at DESC, o.id DESC) AS n
      FROM vehicle_price_observations AS o JOIN vehicles AS v ON v.id = o.vehicle_id
      WHERE v.vin = :vin
    ), counts AS (SELECT count(*) AS c FROM ordered)
    SELECT v.vin, v.year, v.make, v.model, v.trim,
      a.price AS latest_price, a.mileage AS latest_mileage, a.location AS latest_location, a.observed_at AS latest_observed_at,
      b.price AS previous_price, counts.c AS observation_count
    FROM vehicles AS v LEFT JOIN ordered AS a ON a.n = 1 LEFT JOIN ordered AS b ON b.n = 2 CROSS JOIN counts
    WHERE v.vin = :vin"""), {"vin": vin.upper()})).mappings().first()
    if not row: return None
    result = dict(row); result["price_change"] = (result["latest_price"] - result["previous_price"]) if result["latest_price"] is not None and result["previous_price"] is not None else None
    result["price_change_percent"] = (float(result["price_change"] / result["previous_price"] * 100) if result["price_change"] is not None and result["previous_price"] else None)
    return result
