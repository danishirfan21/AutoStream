-- READ-ONLY extract: ingestion runs in execution order. run_seq is the 1-based order by start time
-- (ties broken by id); it is the join key to 05_ingestion_errors. Run ids and timestamps are excluded.
SELECT row_number() OVER (ORDER BY started_at, id) AS run_seq,
       source_name, status, total_records, inserted_records, updated_records,
       duplicate_records, invalid_records, failed_records, error_message
FROM ingestion_runs
ORDER BY run_seq;
