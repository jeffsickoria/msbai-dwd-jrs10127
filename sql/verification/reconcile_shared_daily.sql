-- Reconcile: msbai-dwd-jrs10127.citibike.trips_daily_table  vs
--            nyu-datasets.citibike.m_daily_trips   (authoritative course reference)
-- Read-only. Both are small daily tables (project 9,439 rows; reference 4,738 rows).
-- Normalization is applied ONLY for comparison; source tables are never modified:
--   Subscriber, member -> member ;  Customer, casual -> casual ;  unknown preserved.
-- The project view hard-codes region='NYC', so proj_total is compared against BOTH
-- the reference NYC total (num_nyc_trips) and the reference grand total (num_trips,
-- which includes Jersey City) to test the JC-contamination hypothesis.

-- Shared comparison CTE (repeated per statement; no TEMP tables are created).
-- ===========================================================================

-- A. Common date range and match counts
WITH proj AS (
  SELECT date,
         SUM(trip_count) AS proj_total,
         SUM(CASE WHEN LOWER(rider_type) IN ('subscriber','member') THEN trip_count ELSE 0 END) AS proj_member,
         SUM(CASE WHEN LOWER(rider_type) IN ('customer','casual')   THEN trip_count ELSE 0 END) AS proj_casual,
         SUM(CASE WHEN LOWER(rider_type) NOT IN ('subscriber','member','customer','casual') THEN trip_count ELSE 0 END) AS proj_unknown
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`
  GROUP BY date
),
ref AS (
  SELECT date, num_nyc_trips AS ref_nyc, num_member_trips_nyc AS ref_member,
         num_casual_trips_nyc AS ref_casual, num_jc_trips AS ref_jc, num_trips AS ref_grand
  FROM `nyu-datasets.citibike.m_daily_trips`
),
j AS (
  SELECT p.date, p.proj_total, p.proj_member, p.proj_casual, p.proj_unknown,
         r.ref_nyc, r.ref_member, r.ref_casual, r.ref_jc, r.ref_grand
  FROM proj p JOIN ref r USING (date)
)
SELECT
  COUNT(*)                                        AS dates_compared,
  MIN(date)                                       AS common_min_date,
  MAX(date)                                       AS common_max_date,
  COUNTIF(proj_total = ref_nyc)                   AS exact_match_vs_nyc_total,
  COUNTIF(proj_total = ref_grand)                 AS exact_match_vs_grand_total,
  COUNTIF(proj_member = ref_member)               AS exact_match_member,
  COUNTIF(proj_casual = ref_casual)               AS exact_match_casual
FROM j;

-- B. Discrepancy statistics for total NYC trips (signed diff = proj_total - ref_nyc)
WITH proj AS (
  SELECT date, SUM(trip_count) AS proj_total
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table` GROUP BY date
),
ref AS (SELECT date, num_nyc_trips AS ref_nyc FROM `nyu-datasets.citibike.m_daily_trips`),
d AS (
  SELECT date, proj_total - ref_nyc AS diff, ref_nyc,
         SAFE_DIVIDE(ABS(proj_total - ref_nyc), NULLIF(ref_nyc,0)) AS ape
  FROM proj JOIN ref USING (date)
)
SELECT
  COUNT(*)                                    AS dates_compared,
  ROUND(AVG(ABS(diff)), 2)                    AS mean_abs_diff,
  APPROX_QUANTILES(ABS(diff), 2)[OFFSET(1)]   AS median_abs_diff,
  ROUND(100 * AVG(ape), 4)                    AS mape_pct_guarded,
  MAX(diff)                                   AS largest_positive_diff,
  MIN(diff)                                   AS largest_negative_diff,
  ROUND(AVG(diff), 2)                         AS mean_signed_diff
FROM d;

-- C. Comparison by era (2013-2020, 2021-2023, 2024-2026)
WITH proj AS (
  SELECT date, SUM(trip_count) AS proj_total
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table` GROUP BY date
),
ref AS (SELECT date, num_nyc_trips AS ref_nyc FROM `nyu-datasets.citibike.m_daily_trips`),
d AS (
  SELECT date, proj_total - ref_nyc AS diff,
         SAFE_DIVIDE(ABS(proj_total - ref_nyc), NULLIF(ref_nyc,0)) AS ape,
         CASE
           WHEN EXTRACT(YEAR FROM date) BETWEEN 2013 AND 2020 THEN '2013-2020'
           WHEN EXTRACT(YEAR FROM date) BETWEEN 2021 AND 2023 THEN '2021-2023'
           WHEN EXTRACT(YEAR FROM date) BETWEEN 2024 AND 2026 THEN '2024-2026'
           ELSE 'other' END AS era
  FROM proj JOIN ref USING (date)
)
SELECT era,
  COUNT(*)                   AS dates_compared,
  COUNTIF(diff = 0)          AS exact_matches,
  ROUND(AVG(ABS(diff)), 2)   AS mean_abs_diff,
  ROUND(100*AVG(ape), 4)     AS mape_pct_guarded,
  ROUND(AVG(diff), 2)        AS mean_signed_diff,
  MAX(diff)                  AS max_pos_diff,
  MIN(diff)                  AS max_neg_diff
FROM d GROUP BY era ORDER BY era;

-- D. Member / casual daily discrepancies (normalized)
WITH proj AS (
  SELECT date,
         SUM(CASE WHEN LOWER(rider_type) IN ('subscriber','member') THEN trip_count ELSE 0 END) AS proj_member,
         SUM(CASE WHEN LOWER(rider_type) IN ('customer','casual')   THEN trip_count ELSE 0 END) AS proj_casual
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table` GROUP BY date
),
ref AS (SELECT date, num_member_trips_nyc AS ref_member, num_casual_trips_nyc AS ref_casual
        FROM `nyu-datasets.citibike.m_daily_trips`)
SELECT
  COUNT(*)                                  AS dates_compared,
  ROUND(AVG(ABS(proj_member-ref_member)),2) AS member_mean_abs_diff,
  COUNTIF(proj_member=ref_member)           AS member_exact,
  ROUND(AVG(ABS(proj_casual-ref_casual)),2) AS casual_mean_abs_diff,
  COUNTIF(proj_casual=ref_casual)           AS casual_exact
FROM proj JOIN ref USING (date);

-- E. Monthly totals comparison
WITH proj AS (
  SELECT FORMAT_DATE('%Y-%m', date) AS ym, SUM(trip_count) AS proj_total
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table` GROUP BY ym
),
ref AS (
  SELECT FORMAT_DATE('%Y-%m', date) AS ym, SUM(num_nyc_trips) AS ref_nyc, SUM(num_trips) AS ref_grand
  FROM `nyu-datasets.citibike.m_daily_trips` GROUP BY ym
)
SELECT ym, proj_total, ref_nyc, ref_grand,
       proj_total - ref_nyc AS diff_vs_nyc,
       proj_total - ref_grand AS diff_vs_grand
FROM proj JOIN ref USING (ym)
ORDER BY ym;

-- F. Yearly totals + JC-contamination test (proj vs NYC-only vs grand incl JC)
WITH proj AS (
  SELECT EXTRACT(YEAR FROM date) AS yr, SUM(trip_count) AS proj_total
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table` GROUP BY yr
),
ref AS (
  SELECT EXTRACT(YEAR FROM date) AS yr, SUM(num_nyc_trips) AS ref_nyc,
         SUM(num_jc_trips) AS ref_jc, SUM(num_trips) AS ref_grand
  FROM `nyu-datasets.citibike.m_daily_trips` GROUP BY yr
)
SELECT yr, proj_total, ref_nyc, ref_jc, ref_grand,
       proj_total - ref_nyc   AS diff_vs_nyc,
       proj_total - ref_grand AS diff_vs_grand
FROM proj JOIN ref USING (yr)
ORDER BY yr;

-- G. Dates present in only one source (FULL OUTER JOIN)
WITH proj AS (SELECT DISTINCT date FROM `msbai-dwd-jrs10127.citibike.trips_daily_table`),
ref  AS (SELECT DISTINCT date FROM `nyu-datasets.citibike.m_daily_trips`)
SELECT
  COUNTIF(p.date IS NOT NULL AND r.date IS NULL) AS only_in_project,
  COUNTIF(p.date IS NULL AND r.date IS NOT NULL) AS only_in_reference,
  ARRAY(SELECT p2.date FROM proj p2 LEFT JOIN ref r2 USING(date) WHERE r2.date IS NULL ORDER BY p2.date LIMIT 25) AS sample_only_in_project,
  ARRAY(SELECT r2.date FROM ref r2 LEFT JOIN proj p2 USING(date) WHERE p2.date IS NULL ORDER BY r2.date LIMIT 25) AS sample_only_in_reference
FROM proj p FULL OUTER JOIN ref r USING (date);

-- H. Top 25 daily discrepancies (by absolute NYC-total difference)
WITH proj AS (
  SELECT date, SUM(trip_count) AS proj_total
  FROM `msbai-dwd-jrs10127.citibike.trips_daily_table` GROUP BY date
),
ref AS (SELECT date, num_nyc_trips AS ref_nyc, num_trips AS ref_grand FROM `nyu-datasets.citibike.m_daily_trips`)
SELECT date, proj_total, ref_nyc, ref_grand,
       proj_total - ref_nyc AS diff_vs_nyc,
       proj_total - ref_grand AS diff_vs_grand
FROM proj JOIN ref USING (date)
ORDER BY ABS(proj_total - ref_nyc) DESC
LIMIT 25;
