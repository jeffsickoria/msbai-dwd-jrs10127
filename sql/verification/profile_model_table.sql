-- Profile: msbai-dwd-jrs10127.citibike.trips_daily_model  (1,609 rows)
-- Read-only. Joins only to nyu-datasets.weather.m_weather_daily_nyc for coverage.
-- No raw/view scans; no table modification.

-- 1. date range, row count, distinct dates
SELECT
  MIN(date)                AS min_date,
  MAX(date)                AS max_date,
  COUNT(*)                 AS row_count,
  COUNT(DISTINCT date)     AS distinct_dates
FROM `msbai-dwd-jrs10127.citibike.trips_daily_model`;

-- 2. null values per column
SELECT
  COUNTIF(date IS NULL)          AS null_date,
  COUNTIF(num_nyc_trips IS NULL) AS null_num_nyc_trips,
  COUNTIF(tavg_f IS NULL)        AS null_tavg_f,
  COUNTIF(day_of_week IS NULL)   AS null_day_of_week,
  COUNTIF(month IS NULL)         AS null_month,
  COUNTIF(expected_rides IS NULL) AS null_expected_rides,
  COUNTIF(residual IS NULL)      AS null_residual,
  COUNTIF(residual_pct IS NULL)  AS null_residual_pct
FROM `msbai-dwd-jrs10127.citibike.trips_daily_model`;

-- 3. duplicate dates (should be zero)
SELECT date, COUNT(*) AS n
FROM `msbai-dwd-jrs10127.citibike.trips_daily_model`
GROUP BY date HAVING COUNT(*) > 1
ORDER BY n DESC LIMIT 50;

-- 4. does residual == num_nyc_trips - expected_rides ?
--    (residual is INT64; test exact equality and report any mismatches)
SELECT
  COUNT(*)                                                        AS rows_checked,
  COUNTIF(residual = num_nyc_trips - expected_rides)              AS residual_matches_actual_minus_expected,
  COUNTIF(residual <> num_nyc_trips - expected_rides)             AS residual_mismatches,
  MAX(ABS(residual - (num_nyc_trips - expected_rides)))           AS max_abs_residual_gap
FROM `msbai-dwd-jrs10127.citibike.trips_daily_model`;

-- 5. how is residual_pct calculated? Compare stored value to candidate formulas.
--    Candidates: 100*residual/expected_rides  vs  100*residual/num_nyc_trips
SELECT
  COUNT(*)                                                                          AS rows_checked,
  ROUND(AVG(ABS(residual_pct - SAFE_DIVIDE(100*residual, NULLIF(expected_rides,0)))), 4) AS mean_abs_gap_vs_expected_denom,
  ROUND(AVG(ABS(residual_pct - SAFE_DIVIDE(100*residual, NULLIF(num_nyc_trips,0)))), 4)  AS mean_abs_gap_vs_actual_denom,
  COUNTIF(ROUND(residual_pct,2) = ROUND(SAFE_DIVIDE(100*residual, NULLIF(expected_rides,0)),2)) AS matches_expected_denom_2dp,
  COUNTIF(ROUND(residual_pct,2) = ROUND(SAFE_DIVIDE(100*residual, NULLIF(num_nyc_trips,0)),2))   AS matches_actual_denom_2dp
FROM `msbai-dwd-jrs10127.citibike.trips_daily_model`;

-- 6. MAE and MAPE computed from the stored actual/expected values
SELECT
  ROUND(AVG(ABS(residual)), 2)                                              AS mae_from_residual,
  ROUND(AVG(ABS(num_nyc_trips - expected_rides)), 2)                        AS mae_recomputed,
  ROUND(100 * AVG(SAFE_DIVIDE(ABS(residual), NULLIF(num_nyc_trips,0))), 4)  AS mape_pct_actual_denom,
  ROUND(100 * AVG(SAFE_DIVIDE(ABS(residual), NULLIF(expected_rides,0))), 4) AS mape_pct_expected_denom
FROM `msbai-dwd-jrs10127.citibike.trips_daily_model`;

-- 7. rows outside the documented 2022+ model window
SELECT
  COUNTIF(date < DATE '2022-01-01') AS rows_before_2022,
  COUNTIF(date >= DATE '2022-01-01') AS rows_2022_plus,
  MIN(date) AS min_date, MAX(date) AS max_date
FROM `msbai-dwd-jrs10127.citibike.trips_daily_model`;

-- 8. weather-table coverage over the model's dates
WITH m AS (SELECT DISTINCT date FROM `msbai-dwd-jrs10127.citibike.trips_daily_model`),
w AS (SELECT date, COUNT(*) AS n_weather_rows FROM `nyu-datasets.weather.m_weather_daily_nyc` GROUP BY date)
SELECT
  (SELECT COUNT(*) FROM m)                                          AS model_dates,
  COUNTIF(w.date IS NOT NULL)                                       AS model_dates_with_weather,
  COUNTIF(w.date IS NULL)                                           AS model_dates_missing_weather,
  (SELECT MAX(n_weather_rows) FROM w)                               AS max_weather_rows_per_date,
  ARRAY(SELECT m2.date FROM m m2 LEFT JOIN w USING(date) WHERE w.date IS NULL ORDER BY m2.date LIMIT 25) AS sample_missing_weather_dates
FROM m LEFT JOIN w USING (date);
