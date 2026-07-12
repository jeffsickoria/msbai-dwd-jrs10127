-- Materialize citibike.trips_daily_table_v2 from citibike.trips_daily_v2.
-- Creates/replaces ONLY the _v2 replacement table, clustered by region, rider_type.
-- The current (non-v2) citibike.trips_daily_table is NOT touched.

CREATE OR REPLACE TABLE `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
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
