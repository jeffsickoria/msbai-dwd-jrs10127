-- Profile: msbai-dwd-jrs10127.citibike.trips_daily_table
-- Read-only. Runs only against the small daily table (9,439 rows). No raw/view scans.
-- Each numbered block is an independent statement.

-- 1. min/max date, row count, distinct regions, distinct rider_type values
SELECT
  MIN(date)                       AS min_date,
  MAX(date)                       AS max_date,
  COUNT(*)                        AS row_count,
  COUNT(DISTINCT region)          AS distinct_regions,
  COUNT(DISTINCT rider_type)      AS distinct_rider_types,
  STRING_AGG(DISTINCT region, ',' ORDER BY region)      AS regions,
  STRING_AGG(DISTINCT rider_type, ',' ORDER BY rider_type) AS rider_types
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`;

-- 2. rows and trip totals by rider_type
SELECT
  rider_type,
  COUNT(*)          AS n_rows,
  SUM(trip_count)   AS total_trips,
  MIN(date)         AS first_date,
  MAX(date)         AS last_date
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`
GROUP BY rider_type
ORDER BY rider_type;

-- 3. duplicate (date, region, rider_type) combinations (should be zero)
SELECT date, region, rider_type, COUNT(*) AS n
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`
GROUP BY date, region, rider_type
HAVING COUNT(*) > 1
ORDER BY n DESC, date
LIMIT 50;

-- 4. null or negative trip counts
SELECT
  COUNTIF(trip_count IS NULL)  AS null_trip_counts,
  COUNTIF(trip_count < 0)      AS negative_trip_counts,
  COUNTIF(trip_count = 0)      AS zero_trip_counts
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`;

-- 5. missing dates within the observed range (gaps in the daily calendar,
--    measured on the set of distinct dates present for any rider_type)
WITH present AS (
  SELECT DISTINCT date FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`
),
cal AS (
  SELECT d AS date
  FROM present, UNNEST([1]) x
  CROSS JOIN UNNEST(GENERATE_DATE_ARRAY((SELECT MIN(date) FROM present),
                                        (SELECT MAX(date) FROM present))) d
  GROUP BY d
)
SELECT
  (SELECT COUNT(*) FROM cal)                                   AS calendar_days,
  (SELECT COUNT(*) FROM present)                               AS present_days,
  (SELECT COUNT(*) FROM cal) - (SELECT COUNT(*) FROM present)  AS missing_days,
  ARRAY(
    SELECT c.date FROM cal c
    LEFT JOIN present p USING (date)
    WHERE p.date IS NULL
    ORDER BY c.date
    LIMIT 25
  )                                                            AS sample_missing_dates;

-- 6. totals by year
SELECT
  EXTRACT(YEAR FROM date) AS year,
  COUNT(*)                AS n_rows,
  SUM(trip_count)         AS total_trips
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`
GROUP BY year
ORDER BY year;

-- 7. totals by month
SELECT
  FORMAT_DATE('%Y-%m', date) AS year_month,
  SUM(trip_count)            AS total_trips
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`
GROUP BY year_month
ORDER BY year_month;

-- 8. do legacy (Customer/Subscriber) and normalized (member/casual) values
--    coexist, and in which years?
SELECT
  EXTRACT(YEAR FROM date) AS year,
  SUM(IF(rider_type = 'Subscriber', trip_count, 0)) AS legacy_subscriber,
  SUM(IF(rider_type = 'Customer',   trip_count, 0)) AS legacy_customer,
  SUM(IF(rider_type = 'member',     trip_count, 0)) AS norm_member,
  SUM(IF(rider_type = 'casual',     trip_count, 0)) AS norm_casual,
  SUM(IF(rider_type = 'unknown',    trip_count, 0)) AS unknown,
  LOGICAL_OR(rider_type IN ('Subscriber','Customer')) AS has_legacy,
  LOGICAL_OR(rider_type IN ('member','casual'))       AS has_normalized
FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`
GROUP BY year
ORDER BY year;
