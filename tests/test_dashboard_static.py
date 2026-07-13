"""Offline static checks for the dashboard data layer and caching wiring.
No cloud access. Run: python3 tests/test_dashboard_static.py"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
APP = open(os.path.join(ROOT, "app.py")).read()
QUERY = open(os.path.join(ROOT, "query.py")).read()

import query  # noqa: E402


def test_client_uses_cache_resource():
    assert re.search(r"@st\.cache_resource\s*\ndef get_client", APP), "get_client must be @st.cache_resource"


def test_reads_use_cache_data():
    assert re.search(r"@st\.cache_data\([^)]*\)\s*\ndef fetch_daily", APP), "fetch_daily must be @st.cache_data"
    assert re.search(r"@st\.cache_data\([^)]*\)\s*\ndef fetch_model", APP), "fetch_model must be @st.cache_data"


def test_daily_cache_key_excludes_rider_type():
    # rider switching must reuse cached source data -> fetch_daily keyed by (mode,start,end) only
    m = re.search(r"def fetch_daily\(([^)]*)\)", APP)
    assert m, "fetch_daily not found"
    params = [p.split(":")[0].strip() for p in m.group(1).split(",")]
    assert "rider_type" not in params, f"fetch_daily must not key on rider_type; got {params}"
    assert params[:3] == ["mode", "start", "end"], params


def test_every_chart_has_a_finding_source():
    # 5 charts -> at least 5 '**Finding:**' caption emissions in source
    n = APP.count("**Finding:**")
    assert n >= 5, f"expected >=5 Finding captions in app.py, found {n}"


def test_no_generic_finding_string():
    assert "Ridership varies with temperature" not in APP


def test_config_rejects_bad_mode():
    os.environ["CITIBIKE_SOURCE_MODE"] = "banana"
    raised = False
    try:
        query.get_config()
    except ValueError:
        raised = True
    finally:
        os.environ["CITIBIKE_SOURCE_MODE"] = "v2"
    assert raised, "unknown source mode must raise"


def test_config_defaults_and_tables():
    os.environ.pop("CITIBIKE_SOURCE_MODE", None)
    cfg = query.get_config()
    assert cfg["source_mode"] == "v2"
    assert cfg["v2_table"].endswith("trips_daily_table_v2")
    assert cfg["reference_table"] == "nyu-datasets.citibike.m_daily_trips"
    assert cfg["model_table"].endswith("trips_daily_model")


def test_model_sql_column_contracts():
    cfg = query.get_config()
    v2 = query.model_sql("v2", cfg).lower()
    for col in ("rider_series", "actual_trips", "expected_trips",
                "lower_expected_bound", "upper_expected_bound", "percent_gap", "gap_flag"):
        assert col in v2, f"v2 model_sql missing {col}"
    v1 = query.model_sql("v1", cfg).lower()
    # v1 normalizes legacy columns to the shared names
    assert "num_nyc_trips    as actual_trips" in v1 or "as actual_trips" in v1
    assert "expected_rides   as expected_trips" in v1 or "as expected_trips" in v1


def test_trips_daily_sql_total_includes_unknown():
    cfg = query.get_config()
    sql = query.trips_daily_sql(cfg).lower()
    assert "sum(trip_count)" in sql and "num_nyc_trips" in sql
    assert "num_unknown_trips_nyc" in sql


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
