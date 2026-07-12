WITH base AS (
  SELECT
    DATE(started_at_eastern)                                  AS date,

    'NYC'                                                         AS region,

    -- rider_type passthrough, normalise NULLs
    COALESCE(NULLIF(TRIM(member_casual), ''), 'unknown')      AS rider_type,

    -- duration in minutes, guarded
    CASE
      WHEN ended_at_ts IS NULL OR started_at_ts IS NULL THEN NULL
      WHEN TIMESTAMP_DIFF(ended_at_ts, started_at_ts, SECOND) < 0   THEN NULL
      WHEN TIMESTAMP_DIFF(ended_at_ts, started_at_ts, SECOND) > 86400 THEN NULL
      ELSE TIMESTAMP_DIFF(ended_at_ts, started_at_ts, SECOND) / 60.0
    END                                                       AS duration_min,

    distance_km

  FROM `msbai-dwd-jrs10127.citibike.trips`
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
GROUP BY 1, 2, 3