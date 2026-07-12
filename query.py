"""Data layer and configuration for the Citi Bike dashboard.

All BigQuery object names and the trip-data source selection live here, driven
by environment variables (with production defaults) instead of hard-coded
strings scattered through the app:

    GCP_PROJECT               msbai-dwd-jrs10127
    CITIBIKE_SOURCE_MODE      v2 | reference   (anything else raises)
    CITIBIKE_V2_TABLE         msbai-dwd-jrs10127.citibike.trips_daily_table_v2
    CITIBIKE_REFERENCE_TABLE  nyu-datasets.citibike.m_daily_trips
    WEATHER_TABLE             nyu-datasets.weather.m_weather_daily_nyc
    MODEL_TABLE               msbai-dwd-jrs10127.citibike.trips_daily_model

Source modes:
  * "v2" (default) — the independently verified corrected pipeline output
    (see docs/verification/v2-cutover-decision.md). trips_daily_table_v2 is
    long-format (date, region, rider_type, trip_count, ...) and is pivoted
    here to the wide daily shape the dashboard consumes.
  * "reference" — the course fallback table nyu-datasets.citibike.m_daily_trips
    (already wide). Retained for comparison and as an emergency fallback.

Wide daily shape produced by TRIPS_DAILY_SQL in both modes:
    date, num_nyc_trips, num_member_trips_nyc, num_casual_trips_nyc,
    num_unknown_trips_nyc, avg_duration_minutes, avg_distance_km

Invariants: num_nyc_trips includes unknown-rider trips
(member + casual + unknown = total); the member/casual series never
silently absorb unknown trips. In reference mode num_unknown_trips_nyc and
the duration/distance columns are NULL (the reference does not carry them).
"""
import os
from datetime import date

from google.cloud import bigquery

_VALID_MODES = ("v2", "reference")


def get_config() -> dict:
    """Resolve configuration from the environment. Fails loudly on a bad mode."""
    mode = os.environ.get("CITIBIKE_SOURCE_MODE", "v2").strip().lower()
    if mode not in _VALID_MODES:
        raise ValueError(
            f"CITIBIKE_SOURCE_MODE={mode!r} is not valid; expected one of "
            f"{_VALID_MODES}. Refusing to guess a trip-data source."
        )
    return {
        "project": os.environ.get("GCP_PROJECT", "msbai-dwd-jrs10127"),
        "source_mode": mode,
        "v2_table": os.environ.get(
            "CITIBIKE_V2_TABLE",
            "msbai-dwd-jrs10127.citibike.trips_daily_table_v2"),
        "reference_table": os.environ.get(
            "CITIBIKE_REFERENCE_TABLE", "nyu-datasets.citibike.m_daily_trips"),
        "weather_table": os.environ.get(
            "WEATHER_TABLE", "nyu-datasets.weather.m_weather_daily_nyc"),
        "model_table": os.environ.get(
            "MODEL_TABLE", "msbai-dwd-jrs10127.citibike.trips_daily_model"),
    }


def active_trips_table(cfg: dict | None = None) -> str:
    cfg = cfg or get_config()
    return cfg["v2_table"] if cfg["source_mode"] == "v2" else cfg["reference_table"]


def trips_daily_sql(cfg: dict | None = None) -> str:
    """SQL producing one wide row per date from the active source.

    v2 mode pivots the long-format materialized table. Total includes unknown
    riders; member/casual are exact per-label sums. Duration/distance are
    trip-weighted means over the rider-type groups that have a value.
    """
    cfg = cfg or get_config()
    if cfg["source_mode"] == "v2":
        return f"""
            SELECT
                date,
                SUM(trip_count)                                    AS num_nyc_trips,
                SUM(IF(rider_type = 'member',  trip_count, 0))     AS num_member_trips_nyc,
                SUM(IF(rider_type = 'casual',  trip_count, 0))     AS num_casual_trips_nyc,
                SUM(IF(rider_type = 'unknown', trip_count, 0))     AS num_unknown_trips_nyc,
                SAFE_DIVIDE(
                    SUM(IF(avg_duration_minutes IS NOT NULL,
                           avg_duration_minutes * trip_count, 0)),
                    SUM(IF(avg_duration_minutes IS NOT NULL, trip_count, 0))
                )                                                  AS avg_duration_minutes,
                SAFE_DIVIDE(
                    SUM(IF(avg_distance_km IS NOT NULL,
                           avg_distance_km * trip_count, 0)),
                    SUM(IF(avg_distance_km IS NOT NULL, trip_count, 0))
                )                                                  AS avg_distance_km
            FROM `{cfg["v2_table"]}`
            GROUP BY date
        """
    return f"""
        SELECT
            date,
            num_nyc_trips,
            num_member_trips_nyc,
            num_casual_trips_nyc,
            CAST(NULL AS INT64)   AS num_unknown_trips_nyc,
            CAST(NULL AS FLOAT64) AS avg_duration_minutes,
            CAST(NULL AS FLOAT64) AS avg_distance_km
        FROM `{cfg["reference_table"]}`
    """


def trips_weather_sql(cfg: dict | None = None) -> str:
    """Daily trips (wide) joined 1:1 to daily NYC weather."""
    cfg = cfg or get_config()
    return f"""
        WITH trips_daily AS ({trips_daily_sql(cfg)})
        SELECT
            t.date,
            t.num_nyc_trips,
            t.num_member_trips_nyc,
            t.num_casual_trips_nyc,
            t.num_unknown_trips_nyc,
            t.avg_duration_minutes,
            t.avg_distance_km,
            w.tavg_f,
            w.prcp_inches,
            w.is_weekend,
            w.season,
            w.is_rainy,
            w.is_snowy
        FROM trips_daily t
        JOIN `{cfg["weather_table"]}` w USING (date)
        WHERE t.date BETWEEN @s AND @e
        ORDER BY t.date
    """


# ── Model section (weather-adjusted ridership) ───────────────────────────────
# Two model-table shapes are supported so a MODEL_TABLE swap needs no code
# change and a wrong table fails loudly instead of showing stale results:
#   v1 (pre-v2, trips_daily_model): date, num_nyc_trips, expected_rides,
#       residual, residual_pct
#   v2 (trips_daily_model_v2):      date, rider_series, actual_trips,
#       expected_trips, lower_expected_bound, upper_expected_bound, residual,
#       percent_gap, gap_flag, model_version, training_start, training_end
MODEL_V1_REQUIRED = {"date", "num_nyc_trips", "expected_rides", "residual_pct"}
MODEL_V2_REQUIRED = {"date", "rider_series", "actual_trips", "expected_trips",
                     "lower_expected_bound", "upper_expected_bound",
                     "percent_gap", "gap_flag"}


def detect_model_kind(client, cfg: dict | None = None) -> str:
    """Inspect MODEL_TABLE's columns. Returns 'v2' or 'v1'.

    Raises ValueError if the table is missing or its schema matches neither
    contract — so the dashboard can show a clear error instead of stale data.
    """
    cfg = cfg or get_config()
    from google.api_core.exceptions import NotFound
    try:
        cols = {f.name for f in client.get_table(cfg["model_table"]).schema}
    except NotFound:
        raise ValueError(f"MODEL_TABLE {cfg['model_table']!r} does not exist")
    if MODEL_V2_REQUIRED.issubset(cols):
        return "v2"
    if MODEL_V1_REQUIRED.issubset(cols):
        return "v1"
    raise ValueError(
        f"MODEL_TABLE {cfg['model_table']!r} has an incompatible schema "
        f"(columns: {sorted(cols)}); expected the v1 or v2 model contract")


def model_sql(kind: str, cfg: dict | None = None) -> str:
    """Parameterized (@s,@e) SELECT for the model section, normalized so the app
    consumes the same column names regardless of table version.

    v2 exposes the full total/member/casual series with prediction bounds and an
    objective gap flag; v1 is the legacy total-only residual table.
    """
    cfg = cfg or get_config()
    if kind == "v2":
        return f"""
            SELECT date, rider_series, actual_trips, expected_trips,
                   lower_expected_bound, upper_expected_bound,
                   percent_gap, gap_flag, model_version
            FROM `{cfg["model_table"]}`
            WHERE date BETWEEN @s AND @e
            ORDER BY date
        """
    return f"""
        SELECT date,
               'total'          AS rider_series,
               num_nyc_trips    AS actual_trips,
               expected_rides   AS expected_trips,
               CAST(NULL AS FLOAT64) AS lower_expected_bound,
               CAST(NULL AS FLOAT64) AS upper_expected_bound,
               residual_pct     AS percent_gap,
               ABS(residual_pct) > 15 AS gap_flag,
               'v1_pre_v2'      AS model_version
        FROM `{cfg["model_table"]}`
        WHERE date BETWEEN @s AND @e
        ORDER BY date
    """


_CLIENT = None


def _client(cfg: dict | None = None) -> bigquery.Client:
    global _CLIENT
    if _CLIENT is None:
        cfg = cfg or get_config()
        _CLIENT = bigquery.Client(project=cfg["project"])
    return _CLIENT


def daily_rides_with_temp(
    rider_type: str,          # "member", "casual", or "all"
    start_date: date,
    end_date:   date,
) -> list[dict]:
    """
    Return daily trip counts and average temperature for a rider type and date
    range, from the active source (see CITIBIKE_SOURCE_MODE).

    Each dict has:
        date          (datetime.date)
        num_trips     (int)
        tavg_f        (float)
        is_weekend    (int)
        season        (str)

    rider_type values:
        "member"  -> member trips only
        "casual"  -> casual trips only
        "all"     -> total NYC trips (INCLUDING unknown-rider trips)
    """
    trip_col = {
        "member": "num_member_trips_nyc",
        "casual": "num_casual_trips_nyc",
        "all":    "num_nyc_trips",
    }.get(rider_type.lower())

    if trip_col is None:
        raise ValueError(f"rider_type must be 'member', 'casual', or 'all'; got {rider_type!r}")

    cfg = get_config()
    sql = f"""
        WITH joined AS ({trips_weather_sql(cfg)})
        SELECT date, {trip_col} AS num_trips, tavg_f, is_weekend, season
        FROM joined
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("s", "DATE", start_date.isoformat()),
            bigquery.ScalarQueryParameter("e", "DATE", end_date.isoformat()),
        ]
    )
    return [dict(row) for row in _client(cfg).query(sql, job_config=job_config).result()]


if __name__ == "__main__":
    rows = daily_rides_with_temp(
        rider_type="member",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 10),
    )
    for r in rows:
        print(f"  {r['date']}  trips={r['num_trips']:>6,}  tavg={r['tavg_f']}F  "
              f"weekend={r['is_weekend']}  season={r['season']}")
