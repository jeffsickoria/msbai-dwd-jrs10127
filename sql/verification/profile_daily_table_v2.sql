-- Profile of msbai-dwd-jrs10127.citibike.trips_daily_table_v2 (PR #7).
--
-- Read-only profile of the corrected materialized daily table built by the
-- 2026-07-12 _v2 pipeline execution (see docs/execution/v2-build.md).
-- Touches ONLY the small materialized table (~434 KB) and the course
-- reference table nyu-datasets.citibike.m_daily_trips (~568 KB, used solely
-- to define the reference date range for the missing-date check).
-- No raw _v2 table or row-level view is scanned.
--
-- Each section is a standalone statement; run them individually.

-- ==== section 1: basic profile =============================================
SELECT
  MIN(date)                    AS min_date,
  MAX(date)                    AS max_date,
  COUNT(*)                     AS row_count,
  COUNT(DISTINCT date)         AS distinct_dates,
  COUNT(DISTINCT region)       AS distinct_regions,
  COUNT(DISTINCT rider_type)   AS distinct_rider_types,
  STRING_AGG(DISTINCT region, ',' ORDER BY region)     AS regions,
  STRING_AGG(DISTINCT rider_type, ',' ORDER BY rider_type) AS rider_types
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`;

-- ==== section 2: totals and date ranges by rider type ======================
SELECT
  rider_type,
  SUM(trip_count) AS total_trips,
  MIN(date)       AS first_date,
  MAX(date)       AS last_date,
  COUNT(*)        AS day_rows
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
GROUP BY rider_type
ORDER BY rider_type;

-- ==== section 3: unknown rider-type share ==================================
SELECT
  SUM(IF(rider_type = 'unknown', trip_count, 0))                    AS unknown_trips,
  SUM(trip_count)                                                   AS all_trips,
  ROUND(100 * SUM(IF(rider_type = 'unknown', trip_count, 0))
            / SUM(trip_count), 4)                                   AS unknown_pct
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`;

-- ==== section 4: unknown totals by year and by month =======================
SELECT
  EXTRACT(YEAR FROM date)  AS year,
  FORMAT_DATE('%Y-%m', date) AS month,
  SUM(trip_count)          AS unknown_trips
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
WHERE rider_type = 'unknown'
GROUP BY year, month
HAVING unknown_trips > 0
ORDER BY month;

-- ==== section 5: duplicate (date, region, rider_type) keys ================
SELECT date, region, rider_type, COUNT(*) AS n
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
GROUP BY date, region, rider_type
HAVING COUNT(*) > 1;

-- ==== section 6: null / zero / negative trip counts ========================
SELECT COUNT(*) AS bad_trip_count_rows
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
WHERE trip_count IS NULL OR trip_count <= 0;

-- ==== section 7: missing dates within the reference date range =============
-- Dates present in the course reference table but absent from the project
-- table (the pre-repair pipeline was missing ~118 early-2015 dates).
WITH ref AS (
  SELECT date FROM `nyu-datasets.citibike.m_daily_trips`
),
proj AS (
  SELECT DISTINCT date FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
)
SELECT r.date AS missing_date
FROM ref r
LEFT JOIN proj p USING (date)
WHERE p.date IS NULL
ORDER BY r.date;

-- ==== section 8: monthly totals ============================================
SELECT
  FORMAT_DATE('%Y-%m', date) AS month,
  SUM(trip_count)            AS trips
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
GROUP BY month
ORDER BY month;

-- ==== section 9: yearly totals =============================================
SELECT
  EXTRACT(YEAR FROM date) AS year,
  SUM(trip_count)         AS trips
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
GROUP BY year
ORDER BY year;

-- ==== section 10: legacy labels must be absent =============================
SELECT COUNT(*) AS legacy_label_rows
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
WHERE LOWER(rider_type) IN ('customer', 'subscriber');
