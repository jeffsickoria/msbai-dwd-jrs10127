from datetime import date
from google.cloud import bigquery

_CLIENT = None

def _client() -> bigquery.Client:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = bigquery.Client(project="msbai-dwd-jrs10127")
    return _CLIENT


def daily_rides_with_temp(
    rider_type: str,          # "member", "casual", or "all"
    start_date: date,
    end_date:   date,
) -> list[dict]:
    """
    Return daily trip counts and average temperature for a rider type and date range.

    Each dict has:
        date          (datetime.date)
        num_trips     (int)
        tavg_f        (float)
        is_weekend    (int)
        season        (str)

    rider_type values:
        "member"  -> num_member_trips_nyc
        "casual"  -> num_casual_trips_nyc
        "all"     -> num_nyc_trips
    """
    trip_col = {
        "member": "num_member_trips_nyc",
        "casual": "num_casual_trips_nyc",
        "all":    "num_nyc_trips",
    }.get(rider_type.lower())

    if trip_col is None:
        raise ValueError(f"rider_type must be 'member', 'casual', or 'all'; got {rider_type!r}")

    sql = f"""
        SELECT
            t.date,
            t.{trip_col}                          AS num_trips,
            w.tavg_f,
            w.is_weekend,
            w.season
        FROM `nyu-datasets.citibike.m_daily_trips`       t
        JOIN `nyu-datasets.weather.m_weather_daily_nyc`  w USING (date)
        WHERE t.date BETWEEN @start_date AND @end_date
        ORDER BY t.date
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date.isoformat()),
            bigquery.ScalarQueryParameter("end_date",   "DATE", end_date.isoformat()),
        ]
    )

    return [dict(row) for row in _client().query(sql, job_config=job_config).result()]


if __name__ == "__main__":
    from datetime import date
    import json

    rows = daily_rides_with_temp(
        rider_type="member",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 10),
    )
    for r in rows:
        print(f"  {r['date']}  trips={r['num_trips']:>6,}  tavg={r['tavg_f']}F  "
              f"weekend={r['is_weekend']}  season={r['season']}")
