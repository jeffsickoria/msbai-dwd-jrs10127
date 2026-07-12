-- Bounded raw-table diagnostics for the 2013/2018 doubling, the 2015 gap, and the
-- 2016-2017 legacy rider labels. READ-ONLY.
--
-- Guard rails (see docs/verification/raw-source-diagnosis.md):
--   * Dry-run each statement first; record estimated bytes.
--   * Run with maximum_bytes_billed set; abort if combined estimate > 100 GB.
--   * At most ONE executed query per raw table.
--   * Never query the `trips` / `trips_daily` views (they scan + union the sources
--     and would mask the per-table origin of each defect).
--
-- Fingerprints are SURROGATE trip keys, not guaranteed primary keys:
--   pre2021  : FARM_FINGERPRINT(starttime|stoptime|bikeid|start_station_id|end_station_id)
--   post2021 : ride_id is the real key; a parallel surrogate is also computed.

-- ===========================================================================
-- Q1  raw_pre2021 — monthly counts, view-parseability, duplication, rider types
--     Relevant years only: 2013, 2015, 2016, 2017, 2018.
--     ts_view  = the two formats the trips view actually uses.
--     ts_broad = ts_view plus 'M/D/YYYY H:M(:S)' so early-2015 rows can still be
--                binned to a month even though the view drops them.
-- ===========================================================================
WITH parsed AS (
  SELECT
    COALESCE(
      SAFE.PARSE_TIMESTAMP('%m/%d/%Y %H:%M:%S',   TRIM(starttime)),
      SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%E*S', TRIM(starttime))
    ) AS ts_view,
    COALESCE(
      SAFE.PARSE_TIMESTAMP('%m/%d/%Y %H:%M:%S',   TRIM(starttime)),
      SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%E*S', TRIM(starttime)),
      SAFE.PARSE_TIMESTAMP('%m/%d/%Y %H:%M',      TRIM(starttime)),
      SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M',      TRIM(starttime))
    ) AS ts_broad,
    usertype,
    FARM_FINGERPRINT(CONCAT(
      IFNULL(TRIM(starttime),''), '|', IFNULL(TRIM(stoptime),''), '|',
      IFNULL(CAST(bikeid AS STRING),''), '|',
      IFNULL(CAST(start_station_id AS STRING),''), '|',
      IFNULL(CAST(end_station_id AS STRING),'')
    )) AS fp
  FROM `msbai-dwd-jrs10127.citibike.raw_pre2021`
)
SELECT
  FORMAT_TIMESTAMP('%Y-%m', ts_broad)                 AS year_month,
  COUNT(*)                                            AS total_rows,
  COUNTIF(ts_view IS NULL)                            AS rows_unparseable_by_view,
  APPROX_COUNT_DISTINCT(fp)                           AS approx_distinct_fp,
  COUNT(*) - APPROX_COUNT_DISTINCT(fp)                AS approx_duplicate_rows,
  STRING_AGG(DISTINCT usertype, ',' ORDER BY usertype LIMIT 10) AS rider_types,
  MIN(ts_broad)                                       AS min_ts,
  MAX(ts_broad)                                       AS max_ts
FROM parsed
WHERE EXTRACT(YEAR FROM ts_broad) IN (2013, 2015, 2016, 2017, 2018)
   OR ts_broad IS NULL
GROUP BY year_month
ORDER BY year_month;

-- ===========================================================================
-- Q2  raw_post2021 — monthly counts, ride_id distinctness, surrogate duplication,
--     rider labels. Relevant years only: 2016, 2017, 2018 (2018 expected absent).
-- ===========================================================================
WITH parsed AS (
  SELECT
    SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%E*S', TRIM(started_at)) AS ts,
    ride_id,
    member_casual,
    FARM_FINGERPRINT(CONCAT(
      IFNULL(TRIM(started_at),''), '|', IFNULL(TRIM(ended_at),''), '|',
      IFNULL(TRIM(start_station_id),''), '|', IFNULL(TRIM(end_station_id),'')
    )) AS fp
  FROM `msbai-dwd-jrs10127.citibike.raw_post2021`
)
SELECT
  FORMAT_TIMESTAMP('%Y-%m', ts)                       AS year_month,
  COUNT(*)                                            AS total_rows,
  APPROX_COUNT_DISTINCT(ride_id)                      AS approx_distinct_ride_id,
  COUNT(*) - APPROX_COUNT_DISTINCT(ride_id)           AS approx_dup_by_ride_id,
  APPROX_COUNT_DISTINCT(fp)                           AS approx_distinct_fp,
  STRING_AGG(DISTINCT member_casual, ',' ORDER BY member_casual LIMIT 10) AS rider_labels,
  MIN(ts) AS min_ts, MAX(ts) AS max_ts
FROM parsed
WHERE EXTRACT(YEAR FROM ts) IN (2016, 2017, 2018)
GROUP BY year_month
ORDER BY year_month;
