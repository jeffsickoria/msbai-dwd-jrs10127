-- citibike.trips_v2 — corrected unified trip view (replacement for citibike.trips).
--
-- References ONLY the corrected replacement raw tables:
--   msbai-dwd-jrs10127.citibike.raw_pre2021_v2   (legacy-schema months, 2013-06..2019-12)
--   msbai-dwd-jrs10127.citibike.raw_post2021_v2  (new-schema months,   2020-01..2026-05)
--
-- Corrections vs the original `trips` view:
--   1. TIMESTAMP semantics: source strings are New York LOCAL civil time. We parse
--      them to a DATETIME first (no zone), expose that civil value as
--      started_at_eastern, and derive the absolute instant with
--      TIMESTAMP(datetime, 'America/New_York'). We do NOT parse as UTC and shift.
--   2. Timestamp formats: SAFE.PARSE_DATETIME is tried in this precedence
--      (each layout is distinct, so order only breaks nothing — it just picks the
--      first shape that fully matches):
--         a. '%Y-%m-%d %H:%M:%E*S'  ISO with optional fractional seconds (new schema; 2018 pre)
--         b. '%Y-%m-%d %H:%M:%S'    ISO with seconds (2013-2014 pre)
--         c. '%Y-%m-%d %H:%M'       ISO without seconds
--         d. '%m/%d/%Y %H:%M:%S'    US m/d/Y with seconds
--         e. '%m/%d/%Y %H:%M'       US m/d/Y WITHOUT seconds (recovers Jan/Feb/Mar/Jun 2015)
--   3. Rider-type normalization is applied IDENTICALLY in both branches:
--         subscriber|member -> member ; customer|casual -> casual ; else -> unknown.
--
-- Preserved from the original: Haversine straight-line distance_km, NYC region
-- labeling (downstream), and the unified output column set.

CREATE OR REPLACE VIEW `msbai-dwd-jrs10127.citibike.trips_v2` AS
WITH pre AS (
  SELECT
    CAST(bikeid AS STRING)                                AS ride_id,
    CAST(NULL AS STRING)                                  AS rideable_type,
    TRIM(starttime)                                       AS started_at,
    TRIM(stoptime)                                        AS ended_at,
    TRIM(start_station_name)                              AS start_station_name,
    CAST(start_station_id AS STRING)                      AS start_station_id,
    TRIM(end_station_name)                                AS end_station_name,
    CAST(end_station_id AS STRING)                        AS end_station_id,
    SAFE_CAST(start_station_latitude  AS FLOAT64)         AS start_lat,
    SAFE_CAST(start_station_longitude AS FLOAT64)         AS start_lng,
    SAFE_CAST(end_station_latitude    AS FLOAT64)         AS end_lat,
    SAFE_CAST(end_station_longitude   AS FLOAT64)         AS end_lng,
    CASE
      WHEN LOWER(TRIM(usertype)) IN ('subscriber','member') THEN 'member'
      WHEN LOWER(TRIM(usertype)) IN ('customer','casual')   THEN 'casual'
      ELSE 'unknown'
    END                                                   AS member_casual,
    COALESCE(
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', TRIM(starttime)),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   TRIM(starttime)),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M',      TRIM(starttime)),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M:%S',   TRIM(starttime)),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M',      TRIM(starttime))
    )                                                     AS _start_dt,
    COALESCE(
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', TRIM(stoptime)),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   TRIM(stoptime)),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M',      TRIM(stoptime)),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M:%S',   TRIM(stoptime)),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M',      TRIM(stoptime))
    )                                                     AS _end_dt
  FROM `msbai-dwd-jrs10127.citibike.raw_pre2021_v2`
),

post AS (
  SELECT
    ride_id,
    rideable_type,
    started_at,
    ended_at,
    start_station_name,
    start_station_id,
    end_station_name,
    end_station_id,
    SAFE_CAST(start_lat AS FLOAT64)                       AS start_lat,
    SAFE_CAST(start_lng AS FLOAT64)                       AS start_lng,
    SAFE_CAST(end_lat   AS FLOAT64)                       AS end_lat,
    SAFE_CAST(end_lng   AS FLOAT64)                       AS end_lng,
    CASE
      WHEN LOWER(TRIM(member_casual)) IN ('subscriber','member') THEN 'member'
      WHEN LOWER(TRIM(member_casual)) IN ('customer','casual')   THEN 'casual'
      ELSE 'unknown'
    END                                                   AS member_casual,
    COALESCE(
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', TRIM(started_at)),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   TRIM(started_at)),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M',      TRIM(started_at)),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M:%S',   TRIM(started_at)),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M',      TRIM(started_at))
    )                                                     AS _start_dt,
    COALESCE(
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%E*S', TRIM(ended_at)),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M:%S',   TRIM(ended_at)),
      SAFE.PARSE_DATETIME('%Y-%m-%d %H:%M',      TRIM(ended_at)),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M:%S',   TRIM(ended_at)),
      SAFE.PARSE_DATETIME('%m/%d/%Y %H:%M',      TRIM(ended_at))
    )                                                     AS _end_dt
  FROM `msbai-dwd-jrs10127.citibike.raw_post2021_v2`
),

unified AS (
  SELECT * FROM pre
  UNION ALL
  SELECT * FROM post
)

SELECT
  ride_id, rideable_type, started_at, ended_at,
  start_station_name, start_station_id,
  end_station_name, end_station_id,
  start_lat, start_lng, end_lat, end_lng,
  member_casual,
  -- civil local (New York) datetime — the reporting day is DATE(started_at_eastern)
  _start_dt                                               AS started_at_eastern,
  -- absolute instants, derived by interpreting the civil value as New York local
  TIMESTAMP(_start_dt, 'America/New_York')                AS started_at_ts,
  TIMESTAMP(_end_dt,   'America/New_York')                AS ended_at_ts,
  CASE
    WHEN start_lat IS NULL OR start_lng IS NULL
      OR end_lat IS NULL OR end_lng IS NULL
      OR start_lat = 0 OR start_lng = 0
      OR end_lat = 0 OR end_lng = 0
    THEN NULL
    ELSE (
      2 * 6371 * ASIN(SQRT(
        POW(SIN(((end_lat - start_lat) * ACOS(-1) / 180) / 2), 2)
        + COS(start_lat * ACOS(-1) / 180)
        * COS(end_lat * ACOS(-1) / 180)
        * POW(SIN(((end_lng - start_lng) * ACOS(-1) / 180) / 2), 2)
      ))
    )
  END                                                     AS distance_km
FROM unified;
