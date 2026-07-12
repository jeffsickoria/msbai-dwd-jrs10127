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
    CASE LOWER(TRIM(usertype))
      WHEN 'subscriber' THEN 'member'
      WHEN 'customer'   THEN 'casual'
      ELSE LOWER(TRIM(usertype))
    END                                                   AS member_casual,
    -- two timestamp formats: 'M/D/YYYY H:MM:SS' and 'YYYY-MM-DD HH:MM:SS.ssss'
    COALESCE(
      SAFE.PARSE_TIMESTAMP('%m/%d/%Y %H:%M:%S',   TRIM(starttime)),
      SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%E*S', TRIM(starttime))
    )                                                     AS _ts,
    COALESCE(
      SAFE.PARSE_TIMESTAMP('%m/%d/%Y %H:%M:%S',   TRIM(stoptime)),
      SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%E*S', TRIM(stoptime))
    )                                                     AS _end_ts
  FROM `msbai-dwd-jrs10127.citibike.raw_pre2021`
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
    member_casual,
    SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%E*S', started_at)  AS _ts,
    SAFE.PARSE_TIMESTAMP('%Y-%m-%d %H:%M:%E*S', ended_at)    AS _end_ts
  FROM `msbai-dwd-jrs10127.citibike.raw_post2021`
)

SELECT
  ride_id, rideable_type, started_at, ended_at,
  start_station_name, start_station_id,
  end_station_name, end_station_id,
  start_lat, start_lng, end_lat, end_lng,
  member_casual,
  DATETIME(_ts, 'America/New_York')                       AS started_at_eastern,
  _ts                                                     AS started_at_ts,
  _end_ts                                                 AS ended_at_ts,
  
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
      END                                         AS distance_km
FROM pre

UNION ALL

SELECT
  ride_id, rideable_type, started_at, ended_at,
  start_station_name, start_station_id,
  end_station_name, end_station_id,
  start_lat, start_lng, end_lat, end_lng,
  member_casual,
  DATETIME(_ts, 'America/New_York')                       AS started_at_eastern,
  _ts                                                     AS started_at_ts,
  _end_ts                                                 AS ended_at_ts,
  
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
      END                                        AS distance_km
FROM post