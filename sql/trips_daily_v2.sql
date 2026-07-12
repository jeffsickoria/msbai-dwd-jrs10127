-- citibike.trips_daily_v2 — corrected daily aggregate (replacement for citibike.trips_daily).
-- One row per (date, region, rider_type). Built on citibike.trips_v2 only.
--
-- Corrections carried in from trips_v2: correct New-York-local day attribution
-- (date = DATE(started_at_eastern)) and rider-type already normalized to
-- member/casual/unknown. Duration validation and NYC region labeling preserved
-- from the original trips_daily.

CREATE OR REPLACE VIEW `msbai-dwd-jrs10127.citibike.trips_daily_v2` AS
WITH base AS (
  SELECT
    DATE(started_at_eastern)                                  AS date,
    'NYC'                                                     AS region,
    -- rider_type is already normalized in trips_v2; COALESCE guards NULLs.
    COALESCE(NULLIF(TRIM(member_casual), ''), 'unknown')      AS rider_type,
    -- duration in minutes, guarded (drop negative and > 24h)
    CASE
      WHEN ended_at_ts IS NULL OR started_at_ts IS NULL THEN NULL
      WHEN TIMESTAMP_DIFF(ended_at_ts, started_at_ts, SECOND) < 0     THEN NULL
      WHEN TIMESTAMP_DIFF(ended_at_ts, started_at_ts, SECOND) > 86400 THEN NULL
      ELSE TIMESTAMP_DIFF(ended_at_ts, started_at_ts, SECOND) / 60.0
    END                                                       AS duration_min,
    distance_km
  FROM `msbai-dwd-jrs10127.citibike.trips_v2`
  WHERE started_at_eastern IS NOT NULL
)

SELECT
  date,
  region,
  rider_type,
  COUNT(*)                          AS trip_count,
  ROUND(AVG(duration_min), 2)       AS avg_duration_minutes,
  ROUND(AVG(distance_km),  3)       AS avg_distance_km
FROM base
GROUP BY date, region, rider_type;
