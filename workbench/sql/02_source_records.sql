-- READ-ONLY extract: every accepted source record, one row each, with raw evidence.
-- source_timestamp_utc is the SOURCE-PROVIDED timestamp (empty = the payload had none).
-- raw_payload_json is the original payload as stored (jsonb text; key order is canonical).
-- Excluded on purpose: ids and ingested_at (database-generated; never used for ordering).
SELECT v.vin,
       r.source_name,
       r.source_record_id,
       to_char(r.source_timestamp AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS source_timestamp_utc,
       r.payload_hash,
       r.raw_payload::text AS raw_payload_json
FROM vehicle_source_records r
JOIN vehicles v ON v.id = r.vehicle_id
ORDER BY v.vin, r.source_name, r.source_timestamp, r.source_record_id, r.payload_hash;
