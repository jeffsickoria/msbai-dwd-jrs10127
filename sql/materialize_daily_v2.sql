-- Materialize citibike.trips_daily_table_v2 from citibike.trips_daily_v2.
-- Creates/replaces ONLY the _v2 replacement table. The current (non-v2)
-- citibike.trips_daily_table is NOT touched.
--
-- PARTITIONING / CLUSTERING
-- -------------------------
-- Monthly date partitioning + clustering by (region, rider_type):
--
--     PARTITION BY DATE_TRUNC(date, MONTH)
--     CLUSTER BY region, rider_type
--
-- Why MONTHLY (not daily) date partitioning:
--   * The table is one row per (date, region, rider_type) — a handful of rows
--     per day, ~9.7k rows total.
--   * It spans 2013-06 .. 2026-05 — >150 months / >4,700 days.
--   * DAILY partitioning would create thousands of tiny partitions (BigQuery's
--     ~10k-partition limit is a real ceiling over the full history) with no
--     scan benefit at this size; MONTHLY keeps partitions to ~156, each still
--     pruned by any date-range filter.
--   * DATE_TRUNC(date, MONTH) is time-unit partitioning on the existing `date`
--     column — no surrogate column, no ingestion-time partitioning.
--
-- NOTE ON THE LIVE TABLE (do not misread this file as applied):
-- The live trips_daily_table_v2 built on 2026-07-12 is CLUSTER-ONLY (it was
-- created before this partitioning was specified). This DDL is the intended
-- FUTURE materialization; applying it (a live repartition migration) requires
-- separate explicit human approval and is NOT run in this change.
--
-- MIGRATION CONSTRAINT (verified by dry-run 2026-07-12): BigQuery refuses to
-- `CREATE OR REPLACE` a table with a *different* partitioning spec —
-- "Cannot replace a table with a different partitioning spec. Instead, DROP
-- the table, and then recreate it." So the in-place repartition migration must
-- be done as either:
--   (a) build a partitioned sibling then atomically swap, e.g.
--         CREATE TABLE ...trips_daily_table_v2_partitioned PARTITION BY ... AS SELECT ...;
--         -- validate row counts / reconciliation, then:
--         DROP TABLE ...trips_daily_table_v2;
--         ALTER TABLE ...trips_daily_table_v2_partitioned RENAME TO trips_daily_table_v2;
--   (b) or DROP the existing table and run this CTAS.
-- Option (a) is preferred (no read gap; validate before cutover). The plain
-- CREATE OR REPLACE below is the definition of record for a from-scratch build;
-- for the live migration use option (a).

CREATE OR REPLACE TABLE `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
PARTITION BY DATE_TRUNC(date, MONTH)
CLUSTER BY region, rider_type
AS
SELECT
  date,
  region,
  rider_type,
  trip_count,
  avg_duration_minutes,
  avg_distance_km
FROM `msbai-dwd-jrs10127.citibike.trips_daily_v2`;
