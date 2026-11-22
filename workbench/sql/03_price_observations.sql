-- READ-ONLY extract: price/mileage/location observations.
-- Observations carry no source_record_id in the AutoStream schema. They link to a source record by
-- (vin, source_name, observed_at_utc = source_timestamp_utc). matching_source_records counts the
-- candidates: 1 = unambiguous; 0 = observed_at was the ingestion-time fallback; >1 = ambiguous.
SELECT v.vin,
       o.source_name,
       to_char(o.observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS observed_at_utc,
       o.price,
       o.mileage,
       o.location,
       (SELECT count(*) FROM vehicle_source_records r
         WHERE r.vehicle_id = o.vehicle_id AND r.source_name = o.source_name
           AND r.source_timestamp = o.observed_at) AS matching_source_records
FROM vehicle_price_observations o
JOIN vehicles v ON v.id = o.vehicle_id
ORDER BY v.vin, o.source_name, o.observed_at, o.price, o.mileage;
