-- READ-ONLY extract: one row per rejection OCCURRENCE (not per distinct record).
-- stored_source_record_id is exactly what the pipeline stored (marketplace rejects are positional, e.g. row-4).
-- occurrence_in_run numbers occurrences within a run in a content-based order.
-- error_type is evidence only; error_message text can vary with library versions.
WITH runs AS (
  SELECT id, source_name, row_number() OVER (ORDER BY started_at, id) AS run_seq
  FROM ingestion_runs
)
SELECT r.run_seq,
       r.source_name AS run_source_name,
       row_number() OVER (PARTITION BY r.run_seq
                          ORDER BY e.source_record_id, e.error_type, e.raw_payload::text, e.error_message) AS occurrence_in_run,
       e.source_record_id AS stored_source_record_id,
       e.error_type,
       e.error_message,
       e.raw_payload::text AS raw_payload_json
FROM ingestion_errors e
JOIN runs r ON r.id = e.ingestion_run_id
ORDER BY r.run_seq, occurrence_in_run;
