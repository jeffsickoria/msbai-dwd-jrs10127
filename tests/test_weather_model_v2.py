"""Unit tests for scripts/build_weather_model_v2.py — synthetic fixtures only,
no cloud access. Run: python3 -m pytest tests/test_weather_model_v2.py -q
(or python3 tests/test_weather_model_v2.py for a plain-assert run)."""
import os
import sys
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_weather_model_v2 as M  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def _synthetic(n=800, seed=0):
    """Deterministic synthetic daily frame with a known multiplicative
    weather/calendar structure, so tests do not depend on Math.random-style
    nondeterminism (seeded)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n, freq="D")
    dow = dates.dayofweek.to_numpy() + 1
    month = dates.month.to_numpy()
    tavg = 55 + 20 * np.sin(2 * np.pi * (dates.dayofyear.to_numpy() / 365.0)) + rng.normal(0, 3, n)
    prcp = np.clip(rng.exponential(0.1, n) - 0.05, 0, None)
    snow = np.where(month <= 2, np.clip(rng.exponential(0.2, n) - 0.1, 0, None), 0.0)
    base = 60000 * np.exp(-((tavg - 75) ** 2) / 2000.0)          # inverted-U in temp
    base *= np.where(dow >= 6, 0.7, 1.0)                          # weekend dip
    base *= np.exp(-1.5 * prcp) * np.exp(-2.0 * snow)             # weather suppression
    total = np.clip(base * rng.lognormal(0, 0.05, n), 100, None).round()
    member = (total * 0.8).round()
    casual = (total - member).round()
    return pd.DataFrame({
        "date": dates.date, "total": total, "member": member, "casual": casual,
        "day_of_week": dow, "month": month, "season": "x", "is_weekend": dow >= 6,
        "tavg_f": tavg.round(1), "prcp_inches": prcp.round(3), "snow_inches": snow.round(3),
    })


FEATURES = ["tavg_f", "tavg_f_sq", "prcp_inches", "snow_inches", "dow", "month"]


def test_guard_v2_rejects_non_v2():
    ok = False
    try:
        M.guard_v2("msbai-dwd-jrs10127.citibike.trips_daily_model")  # not _v2
    except SystemExit:
        ok = True
    assert ok, "guard_v2 must reject a non-_v2 destination"
    assert M.guard_v2("x.y.trips_daily_model_v2").endswith("_v2")


def test_build_design_shape_and_const():
    df = _synthetic(50)
    X = M.build_design(df, FEATURES)
    assert (X["const"] == 1.0).all()
    assert "tavg_f_sq" in X.columns and "trend_days" in X.columns  # helper always builds trend col
    # one-hots present for dow/month
    assert any(c.startswith("dow_") for c in X.columns)
    assert any(c.startswith("mon_") for c in X.columns)
    assert len(X) == len(df)


def test_fit_ols_recovers_linear_signal():
    # y = 3 + 2*x exactly -> lstsq must recover it
    x = np.linspace(0, 10, 100)
    X = pd.DataFrame({"const": 1.0, "x": x})
    beta, rmse = M.fit_ols(X, 3 + 2 * x)
    assert abs(beta[0] - 3) < 1e-6 and abs(beta[1] - 2) < 1e-6
    assert rmse < 1e-6


def test_mae_mape_basic():
    mae, mape = M.mae_mape([100, 200], [110, 190])
    assert abs(mae - 10) < 1e-9
    assert abs(mape - (10 / 100 + 10 / 200) / 2 * 100) < 1e-9


def test_evaluate_and_build_schema_and_calibration():
    df = _synthetic(800)
    metrics, rows = M.evaluate_and_build(df, FEATURES, holdout_days=120)
    # all three series present
    assert set(metrics) == set(M.SERIES)
    # output schema matches the proposed table schema exactly
    expected_cols = [c for c, _ in M.OUTPUT_SCHEMA]
    assert set(rows[0].keys()) == set(expected_cols)
    assert len(rows) == len(M.SERIES) * len(df)
    # total == member + casual actual_trips per date (unknown is 0 in fixture)
    by = {}
    for r in rows:
        by.setdefault(r["date"], {})[r["rider_series"]] = r["actual_trips"]
    for d, v in by.items():
        assert v["total"] == v["member"] + v["casual"]
    # PI calibration: on well-specified synthetic data the 95% band should flag
    # only a small fraction (sanity: < 15%), and bounds must bracket expected.
    for s in M.SERIES:
        assert metrics[s]["flagged_pct"] < 15.0
    for r in rows:
        assert r["lower_expected_bound"] <= r["expected_trips"] <= r["upper_expected_bound"]
        assert isinstance(r["gap_flag"], bool)
        assert r["model_version"] == M.MODEL_VERSION


def test_log_target_beats_raw_on_holdout():
    """Diagnostic assertion behind the design choice: the log target should not
    be worse than raw counts on the synthetic multiplicative data (casual)."""
    df = _synthetic(800).sort_values("date").reset_index(drop=True)
    split = 680
    tr, ho = df.iloc[:split], df.iloc[split:]
    Xtr = M.build_design(tr, FEATURES)
    Xho = M.build_design(ho, FEATURES).reindex(columns=Xtr.columns, fill_value=0.0)
    # raw
    b_raw, _ = M.fit_ols(Xtr, tr["casual"])
    _, mape_raw = M.mae_mape(ho["casual"], M.predict(Xho, b_raw))
    # log
    b_log, _ = M.fit_ols(Xtr, np.log1p(tr["casual"].to_numpy(float)))
    _, mape_log = M.mae_mape(ho["casual"], np.expm1(M.predict(Xho, b_log)))
    assert mape_log <= mape_raw + 1e-6


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
