-- Reconciliation of msbai-dwd-jrs10127.citibike.trips_daily_table_v2 (PR #7)
-- against the course reference nyu-datasets.citibike.m_daily_trips.
--
-- Reference columns used (verified against the live schema on 2026-07-12):
--   num_nyc_trips         — NYC-only daily total (primary comparison target)
--   num_member_trips_nyc  — NYC member trips
--   num_casual_trips_nyc  — NYC casual trips
--   num_trips             — grand total INCLUDING Jersey City (alignment test only)
--
-- Project-side definitions:
--   proj_total   = SUM(trip_count) over all rider types  (member+casual+unknown)
--   proj_member  = SUM(trip_count) WHERE rider_type='member'
--   proj_casual  = SUM(trip_count) WHERE rider_type='casual'
--   proj_unknown = SUM(trip_count) WHERE rider_type='unknown'
--
-- Read-only; touches only the two small daily tables (~1 MB combined).
-- Each section is a standalone statement built on the shared `joined` CTE.

-- ==== section 1: daily join over the common date range =====================
WITH proj AS (
  SELECT
    date,
    SUM(trip_count)                                          AS proj_total,
    SUM(IF(rider_type = 'member',  trip_count, 0))           AS proj_member,
    SUM(IF(rider_type = 'casual',  trip_count, 0))           AS proj_casual,
    SUM(IF(rider_type = 'unknown', trip_count, 0))           AS proj_unknown
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
  GROUP BY date
),
joined AS (
  SELECT
    r.date,
    p.proj_total, p.proj_member, p.proj_casual, p.proj_unknown,
    r.num_nyc_trips, r.num_member_trips_nyc, r.num_casual_trips_nyc, r.num_trips,
    p.proj_total - r.num_nyc_trips AS diff_total
  FROM `nyu-datasets.citibike.m_daily_trips` r
  JOIN proj p USING (date)
)
SELECT * FROM joined ORDER BY date;

-- ==== section 2: match statistics, full range and by era ===================
WITH proj AS (
  SELECT date,
         SUM(trip_count)                                AS proj_total,
         SUM(IF(rider_type='member', trip_count, 0))    AS proj_member,
         SUM(IF(rider_type='casual', trip_count, 0))    AS proj_casual
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
  GROUP BY date
),
joined AS (
  SELECT r.date, p.proj_total, p.proj_member, p.proj_casual,
         r.num_nyc_trips, r.num_member_trips_nyc, r.num_casual_trips_nyc,
         p.proj_total - r.num_nyc_trips AS diff
  FROM `nyu-datasets.citibike.m_daily_trips` r
  JOIN proj p USING (date)
),
eras AS (
  SELECT '2013'        AS era, DATE '2013-01-01' AS lo, DATE '2013-12-31' AS hi UNION ALL
  SELECT '2015',            DATE '2015-01-01', DATE '2015-12-31' UNION ALL
  SELECT '2018',            DATE '2018-01-01', DATE '2018-12-31' UNION ALL
  SELECT '2013-2020',       DATE '2013-01-01', DATE '2020-12-31' UNION ALL
  SELECT '2021-2023',       DATE '2021-01-01', DATE '2023-12-31' UNION ALL
  SELECT '2024-2026',       DATE '2024-01-01', DATE '2026-12-31' UNION ALL
  SELECT 'full',            DATE '2000-01-01', DATE '2100-01-01'
)
SELECT
  e.era,
  COUNT(j.date)                                            AS dates_compared,
  COUNTIF(j.diff = 0)                                      AS exact_match_dates,
  ROUND(100 * COUNTIF(j.diff = 0) / COUNT(j.date), 2)      AS exact_match_pct,
  ROUND(AVG(j.diff), 1)                                    AS mean_signed_diff,
  ROUND(AVG(ABS(j.diff)), 1)                               AS mean_abs_diff,
  APPROX_QUANTILES(ABS(j.diff), 2)[OFFSET(1)]              AS median_abs_diff,
  ROUND(100 * AVG(IF(j.num_nyc_trips > 0,
                     ABS(j.diff) / j.num_nyc_trips, NULL)), 3) AS mape_pct,
  MAX(j.diff)                                              AS largest_positive_diff,
  MIN(j.diff)                                              AS largest_negative_diff
FROM eras e
JOIN joined j ON j.date BETWEEN e.lo AND e.hi
GROUP BY e.era
ORDER BY MIN(e.lo), e.era;

-- ==== section 3: member / casual daily match statistics (full range) =======
WITH proj AS (
  SELECT date,
         SUM(IF(rider_type='member', trip_count, 0)) AS proj_member,
         SUM(IF(rider_type='casual', trip_count, 0)) AS proj_casual
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
  GROUP BY date
),
joined AS (
  SELECT r.date,
         p.proj_member - r.num_member_trips_nyc AS diff_member,
         p.proj_casual - r.num_casual_trips_nyc AS diff_casual,
         r.num_member_trips_nyc, r.num_casual_trips_nyc
  FROM `nyu-datasets.citibike.m_daily_trips` r
  JOIN proj p USING (date)
)
SELECT
  'member' AS series,
  COUNT(*)                                           AS dates_compared,
  COUNTIF(diff_member = 0)                           AS exact_match_dates,
  ROUND(100 * COUNTIF(diff_member = 0) / COUNT(*),2) AS exact_match_pct,
  ROUND(AVG(diff_member), 1)                         AS mean_signed_diff,
  ROUND(AVG(ABS(diff_member)), 1)                    AS mean_abs_diff,
  ROUND(100 * AVG(IF(num_member_trips_nyc > 0,
        ABS(diff_member) / num_member_trips_nyc, NULL)), 3) AS mape_pct
FROM joined
UNION ALL
SELECT
  'casual',
  COUNT(*),
  COUNTIF(diff_casual = 0),
  ROUND(100 * COUNTIF(diff_casual = 0) / COUNT(*), 2),
  ROUND(AVG(diff_casual), 1),
  ROUND(AVG(ABS(diff_casual)), 1),
  ROUND(100 * AVG(IF(num_casual_trips_nyc > 0,
        ABS(diff_casual) / num_casual_trips_nyc, NULL)), 3)
FROM joined;

-- ==== section 4: yearly totals, ratios, and NYC-vs-JC alignment ============
WITH proj AS (
  SELECT EXTRACT(YEAR FROM date) AS year, SUM(trip_count) AS proj_trips
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
  GROUP BY year
),
ref AS (
  SELECT EXTRACT(YEAR FROM date) AS year,
         SUM(num_nyc_trips) AS ref_nyc,
         SUM(num_trips)     AS ref_grand_incl_jc
  FROM `nyu-datasets.citibike.m_daily_trips`
  GROUP BY year
)
SELECT
  year,
  p.proj_trips,
  r.ref_nyc,
  r.ref_grand_incl_jc,
  ROUND(p.proj_trips / r.ref_nyc, 4)                          AS ratio_to_nyc,
  ROUND(p.proj_trips / r.ref_grand_incl_jc, 4)                AS ratio_to_grand,
  ROUND(100 * (p.proj_trips - r.ref_nyc) / r.ref_nyc, 3)      AS pct_diff_vs_nyc,
  ABS(p.proj_trips - r.ref_nyc) < ABS(p.proj_trips - r.ref_grand_incl_jc)
                                                              AS closer_to_nyc_than_grand
FROM proj p
JOIN ref r USING (year)
ORDER BY year;

-- ==== section 5: monthly totals with >5% flag ===============================
WITH proj AS (
  SELECT FORMAT_DATE('%Y-%m', date) AS month, SUM(trip_count) AS proj_trips
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
  GROUP BY month
),
ref AS (
  SELECT FORMAT_DATE('%Y-%m', date) AS month, SUM(num_nyc_trips) AS ref_nyc
  FROM `nyu-datasets.citibike.m_daily_trips`
  GROUP BY month
)
SELECT
  month,
  p.proj_trips,
  r.ref_nyc,
  ROUND(100 * (p.proj_trips - r.ref_nyc) / NULLIF(r.ref_nyc, 0), 3) AS pct_diff,
  ABS(p.proj_trips - r.ref_nyc) / NULLIF(r.ref_nyc, 0) > 0.05       AS exceeds_5pct
FROM proj p
JOIN ref r USING (month)
ORDER BY month;

-- ==== section 6: top 25 daily discrepancies =================================
WITH proj AS (
  SELECT date, SUM(trip_count) AS proj_total
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
  GROUP BY date
)
SELECT
  r.date,
  p.proj_total,
  r.num_nyc_trips,
  p.proj_total - r.num_nyc_trips                                  AS diff,
  ROUND(p.proj_total / NULLIF(r.num_nyc_trips, 0), 3)             AS ratio
FROM `nyu-datasets.citibike.m_daily_trips` r
JOIN proj p USING (date)
ORDER BY ABS(p.proj_total - r.num_nyc_trips) DESC
LIMIT 25;

-- ==== section 7: dates missing from either source ===========================
WITH proj AS (
  SELECT DISTINCT date FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
),
ref AS (
  SELECT date FROM `nyu-datasets.citibike.m_daily_trips`
)
SELECT
  'in_reference_not_in_project' AS direction, COUNT(*) AS n,
  MIN(r.date) AS first, MAX(r.date) AS last
FROM ref r LEFT JOIN proj p USING (date) WHERE p.date IS NULL
UNION ALL
SELECT
  'in_project_not_in_reference', COUNT(*),
  MIN(p.date), MAX(p.date)
FROM proj p LEFT JOIN ref r USING (date) WHERE r.date IS NULL;

-- ==== section 8: early-2015 parse-defect months (Jan/Feb/Mar/Jun 2015) ======
-- Pre-repair, these four months were 100% unparseable and dropped by the view.
WITH proj AS (
  SELECT FORMAT_DATE('%Y-%m', date) AS month,
         COUNT(DISTINCT date)       AS days_present,
         SUM(trip_count)            AS proj_trips
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
  WHERE FORMAT_DATE('%Y-%m', date) IN ('2015-01','2015-02','2015-03','2015-06')
  GROUP BY month
),
ref AS (
  SELECT FORMAT_DATE('%Y-%m', date) AS month,
         COUNT(DISTINCT date)       AS ref_days,
         SUM(num_nyc_trips)         AS ref_nyc
  FROM `nyu-datasets.citibike.m_daily_trips`
  WHERE FORMAT_DATE('%Y-%m', date) IN ('2015-01','2015-02','2015-03','2015-06')
  GROUP BY month
)
SELECT
  month, p.days_present, r.ref_days, p.proj_trips, r.ref_nyc,
  ROUND(p.proj_trips / r.ref_nyc, 4) AS ratio
FROM ref r
LEFT JOIN proj p USING (month)
ORDER BY month;
