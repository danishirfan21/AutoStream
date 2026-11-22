-- READ-ONLY extract: canonical vehicle rows (context for lookups; not evidence of source values).
-- Excluded on purpose: id, created_at, updated_at (database-generated, not reproducible).
SELECT v.vin, v.year, v.make, v.model, v.trim
FROM vehicles v
ORDER BY v.vin;
