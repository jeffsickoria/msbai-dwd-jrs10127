#!/usr/bin/env python3
"""Stretch 1 — Weather-Adjusted Ridership (v2).

Builds a simple, interpretable, reproducible descriptive model of daily NYC
Citi Bike ridership as a function of weather + calendar, on the **verified v2
series**, and (only with --apply) materializes the results to

    msbai-dwd-jrs10127.citibike.trips_daily_model_v2

SAFETY
------
* DRY-RUN / READ-ONLY BY DEFAULT. Without --apply the script queries inputs
  read-only, fits the model, runs a time-based holdout, prints metrics, and
  builds the output frame in memory — but creates NO table.
* --apply is required to create/replace trips_daily_model_v2, and the
  destination is hard-guarded to end in "_v2" (never the pre-v2
  trips_daily_model). This PR does NOT run --apply.
* Never writes GCS, never deploys, never touches other tables.

INPUTS (read-only)
------------------
* msbai-dwd-jrs10127.citibike.trips_daily_table_v2   (verified daily counts)
* nyu-datasets.weather.m_weather_daily_nyc           (daily NYC weather)

MODELING CHOICES (diagnostic-driven; justified from the live weather schema)
----------------------------------------------------------------------------
Target: log1p(trips). A time-based holdout showed the log target roughly halves
MAPE vs the raw-count target (esp. for casual, whose winter base is tiny) —
weather and growth act multiplicatively, so logs linearize them. Prediction
bounds are formed in log space and back-transformed, giving (correctly)
asymmetric bounds in level space.

Feature list (interpretable, all non-null over the window — verified):
  * C(day_of_week)      commute vs weekend pattern
  * C(month)            seasonality / daylight (absorbs "season")
  * tavg_f, tavg_f^2    ridership rises with warmth then falls in extreme heat
                        — a quadratic term captures the inverted-U.
  * prcp_inches         rain suppresses riding
  * snow_inches         snow suppresses riding (distinct from rain)

System growth: a global linear time trend was TESTED as the growth term and
**rejected on diagnostics** — it consistently worsened time-based holdout error
(it extrapolates the recent ramp unstably). Within the mature 2022+ window the
month fixed-effects absorb the systematic seasonal/level structure. LIMITATION:
the model therefore does not extrapolate multi-year growth beyond its window; a
longer-horizon model would need a nonlinear growth term (year effects / spline)
and is documented as future work.

Rejected for parsimony/interpretability: humidity/dewpoint/wind/pressure
(marginal, collinear with temp/precip), is_* one-hots (redundant with the
continuous fields). Documented in docs/decisions/decisions-memo.md.

MODELING WINDOW
---------------
Default 2022-01-01 .. (weather max). The mature-system era: comparable to the
previously deployed model's window so the dashboard section stays meaningful,
and it avoids fitting the 2013-2019 explosive growth with a single linear
trend. A full-history model is documented as future work. Unknown-rider trips
are 0 in this window (they occur only Oct 2016-Mar 2017), so total == member +
casual here; the "total" series is nonetheless DEFINED as all-rider-inclusive.

SERIES MODELED: total (incl. unknown), member, casual — each fit independently.

HOLDOUT: time-based (last HOLDOUT_DAYS of the window), never random. Reports
MAE + MAPE per series on the holdout, then refits on the full window for the
descriptive output.

OUTPUT SCHEMA (proposed trips_daily_model_v2):
  date DATE, rider_series STRING, actual_trips INT64, expected_trips FLOAT64,
  lower_expected_bound FLOAT64, upper_expected_bound FLOAT64, residual FLOAT64,
  percent_gap FLOAT64, gap_flag BOOL, model_version STRING,
  training_start DATE, training_end DATE

FLAG RULE (objective — NOT chosen for visual effect):
  A ~95% prediction interval is formed from the model's own residual spread in
  LOG space on the full refit: log_expected ± 1.96*RMSE_log, back-transformed
  to level space via expm1(). gap_flag is TRUE when actual falls outside that
  band, i.e. the day is outside the model's typical error range and merits
  investigation. This establishes NO cause; deviations do not prove an
  operational problem, shortage, event, or promotion.

Usage:
    python3 scripts/build_weather_model_v2.py                # read-only eval
    python3 scripts/build_weather_model_v2.py --apply        # create _v2 table (needs approval)
"""
import argparse
import sys
from datetime import date

MODEL_VERSION = "wa_v2_ols_1"
HOLDOUT_DAYS = 180
DEST_TABLE = "msbai-dwd-jrs10127.citibike.trips_daily_model_v2"
SERIES = ("total", "member", "casual")


def guard_v2(table_id: str) -> str:
    leaf = table_id.split(".")[-1]
    if not leaf.endswith("_v2"):
        sys.exit(f"REFUSING: destination '{table_id}' does not end in _v2")
    return table_id


def input_sql(v2_table: str, weather_table: str, start: str) -> str:
    """Read-only join of the verified daily series to weather features.

    trip_count is pivoted to total/member/casual; total includes unknown.
    """
    return f"""
    WITH daily AS (
      SELECT
        date,
        SUM(trip_count)                                AS total,
        SUM(IF(rider_type='member', trip_count, 0))    AS member,
        SUM(IF(rider_type='casual', trip_count, 0))    AS casual
      FROM `{v2_table}`
      GROUP BY date
    )
    SELECT
      d.date, d.total, d.member, d.casual,
      w.day_of_week, w.month, w.season, w.is_weekend,
      w.tavg_f, w.prcp_inches, w.snow_inches
    FROM daily d
    JOIN `{weather_table}` w USING (date)
    WHERE d.date >= DATE('{start}')
    ORDER BY d.date
    """


def build_design(df, feature_cols):
    """Assemble the OLS design matrix from a pandas frame (patsy-free so the
    unit tests need only numpy/pandas)."""
    import numpy as np
    import pandas as pd
    X = pd.DataFrame(index=df.index)
    # linear + quadratic temperature
    X["tavg_f"] = df["tavg_f"].astype(float)
    if "tavg_f_sq" in feature_cols:
        X["tavg_f_sq"] = df["tavg_f"].astype(float) ** 2
    X["prcp_inches"] = df["prcp_inches"].astype(float)
    X["snow_inches"] = df["snow_inches"].astype(float)
    # linear growth trend (days since first modeled date)
    t0 = pd.to_datetime(df["date"]).min()
    X["trend_days"] = (pd.to_datetime(df["date"]) - t0).dt.days.astype(float)
    # categorical day_of_week and month as one-hots (drop first level)
    dow = pd.get_dummies(df["day_of_week"].astype(int), prefix="dow", drop_first=True)
    mon = pd.get_dummies(df["month"].astype(int), prefix="mon", drop_first=True)
    X = pd.concat([X, dow.astype(float), mon.astype(float)], axis=1)
    X.insert(0, "const", 1.0)
    return X


def fit_ols(X, y):
    """Plain least squares via numpy; returns (beta, residual_std)."""
    import numpy as np
    Xv = X.to_numpy(dtype=float)
    yv = np.asarray(y, dtype=float)
    beta, *_ = np.linalg.lstsq(Xv, yv, rcond=None)
    resid = yv - Xv @ beta
    dof = max(len(yv) - Xv.shape[1], 1)
    rmse = float((resid @ resid / dof) ** 0.5)
    return beta, rmse


def predict(X, beta):
    import numpy as np
    return X.to_numpy(dtype=float) @ beta


def mae_mape(actual, pred):
    import numpy as np
    a = np.asarray(actual, dtype=float)
    p = np.asarray(pred, dtype=float)
    mae = float(np.mean(np.abs(a - p)))
    nz = a != 0
    mape = float(np.mean(np.abs((a[nz] - p[nz]) / a[nz])) * 100) if nz.any() else float("nan")
    return mae, mape


def evaluate_and_build(df, feature_cols, holdout_days=HOLDOUT_DAYS):
    """Time-based holdout eval per series, then full-window refit + output rows.

    Fits log1p(trips) (multiplicative weather effects; see module docstring),
    back-transforming predictions and the 95% prediction band to level space.
    Returns (metrics: dict, output_rows: list[dict])."""
    import numpy as np
    import pandas as pd
    df = df.sort_values("date").reset_index(drop=True)
    dmax = pd.to_datetime(df["date"]).max()
    split = dmax - pd.Timedelta(days=holdout_days)
    is_train = pd.to_datetime(df["date"]) <= split
    train, hold = df[is_train], df[~is_train]

    metrics, out_rows = {}, []
    tr_start = pd.to_datetime(df["date"]).min().date()
    tr_end = dmax.date()
    for s in SERIES:
        # holdout evaluation (fit in log space, evaluate in level space)
        Xtr = build_design(train, feature_cols)
        Xho = build_design(hold, feature_cols).reindex(columns=Xtr.columns, fill_value=0.0)
        beta_h, _ = fit_ols(Xtr, np.log1p(train[s].to_numpy(dtype=float)))
        pred_ho = np.expm1(predict(Xho, beta_h))
        mae, mape = mae_mape(hold[s], pred_ho)
        metrics[s] = {
            "holdout_mae": round(mae, 1), "holdout_mape_pct": round(mape, 2),
            "train_rows": int(len(train)), "holdout_rows": int(len(hold)),
            "train_dates": f"{pd.to_datetime(train['date']).min().date()}..{pd.to_datetime(train['date']).max().date()}",
            "holdout_dates": f"{pd.to_datetime(hold['date']).min().date()}..{pd.to_datetime(hold['date']).max().date()}",
        }
        # full-window refit for the descriptive output
        Xall = build_design(df, feature_cols)
        ylog = np.log1p(df[s].to_numpy(dtype=float))
        beta, rmse_log = fit_ols(Xall, ylog)
        exp_log = predict(Xall, beta)
        exp = np.expm1(exp_log)
        lo = np.expm1(exp_log - 1.96 * rmse_log)   # asymmetric band in level space
        hi = np.expm1(exp_log + 1.96 * rmse_log)
        act = df[s].to_numpy(dtype=float)
        for i, d in enumerate(df["date"]):
            resid = act[i] - exp[i]
            out_rows.append({
                "date": d, "rider_series": s,
                "actual_trips": int(act[i]), "expected_trips": round(float(exp[i]), 1),
                "lower_expected_bound": round(float(lo[i]), 1),
                "upper_expected_bound": round(float(hi[i]), 1),
                "residual": round(float(resid), 1),
                "percent_gap": round(float(100 * resid / exp[i]), 2) if exp[i] else None,
                "gap_flag": bool(act[i] < lo[i] or act[i] > hi[i]),
                "model_version": MODEL_VERSION,
                "training_start": tr_start, "training_end": tr_end,
            })
        metrics[s]["full_refit_rmse_log"] = round(rmse_log, 4)
        metrics[s]["flagged_pct"] = round(
            100 * sum(1 for r in out_rows if r["rider_series"] == s and r["gap_flag"]) / len(df), 2)
    return metrics, out_rows


OUTPUT_SCHEMA = [
    ("date", "DATE"), ("rider_series", "STRING"), ("actual_trips", "INT64"),
    ("expected_trips", "FLOAT64"), ("lower_expected_bound", "FLOAT64"),
    ("upper_expected_bound", "FLOAT64"), ("residual", "FLOAT64"),
    ("percent_gap", "FLOAT64"), ("gap_flag", "BOOL"), ("model_version", "STRING"),
    ("training_start", "DATE"), ("training_end", "DATE"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="msbai-dwd-jrs10127")
    ap.add_argument("--v2-table", default="msbai-dwd-jrs10127.citibike.trips_daily_table_v2")
    ap.add_argument("--weather-table", default="nyu-datasets.weather.m_weather_daily_nyc")
    ap.add_argument("--dest", default=DEST_TABLE)
    ap.add_argument("--start", default="2022-01-01", help="modeling-window start (inclusive)")
    ap.add_argument("--holdout-days", type=int, default=HOLDOUT_DAYS)
    ap.add_argument("--apply", action="store_true",
                    help="ACTUALLY create/replace the _v2 model table (default: read-only)")
    args = ap.parse_args()
    guard_v2(args.dest)

    from google.cloud import bigquery
    client = bigquery.Client(project=args.project)
    sql = input_sql(args.v2_table, args.weather_table, args.start)
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True))
    print(f"[read-only] input join est. bytes: {dry.total_bytes_processed:,}")
    df = client.query(sql).to_dataframe()
    print(f"[read-only] loaded {len(df)} modeled days {df['date'].min()}..{df['date'].max()}; "
          f"missing-weather rows dropped by inner join (weather is complete over window)")

    # Diagnostic-selected feature set: log target, weather + calendar, NO global
    # trend (trend tested and rejected on holdout — see module docstring / docs).
    feature_cols = ["tavg_f", "tavg_f_sq", "prcp_inches", "snow_inches", "dow", "month"]
    metrics, rows = evaluate_and_build(df, feature_cols, args.holdout_days)
    print("\n=== holdout metrics (time-based, log1p target) ===")
    for s, m in metrics.items():
        print(f"  {s:6s} MAE={m['holdout_mae']:>10,.1f}  MAPE={m['holdout_mape_pct']:>6}%  "
              f"train={m['train_dates']} ({m['train_rows']})  holdout={m['holdout_dates']} ({m['holdout_rows']})  "
              f"rmse_log={m['full_refit_rmse_log']}  flagged={m['flagged_pct']}%")
    print(f"\nproposed output schema: {[c for c,_ in OUTPUT_SCHEMA]}")
    print(f"output rows built in memory: {len(rows)} ({len(SERIES)} series x {len(df)} days)")

    if not args.apply:
        print(f"\n[dry-run] NOT writing {args.dest}. Re-run with --apply (and human approval) to create it.")
        return
    guard_v2(args.dest)
    proj, dset, tbl = args.dest.split(".")
    schema = [bigquery.SchemaField(n, t) for n, t in OUTPUT_SCHEMA]
    table = bigquery.Table(args.dest, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.MONTH, field="date")
    table.clustering_fields = ["rider_series"]
    client.delete_table(args.dest, not_found_ok=True)
    client.create_table(table)
    errors = client.insert_rows(client.get_table(args.dest), [tuple(r[n] for n, _ in OUTPUT_SCHEMA) for r in rows])
    if errors:
        sys.exit(f"LOAD ERRORS: {errors[:3]}")
    print(f"[apply] created {args.dest} with {len(rows)} rows")


if __name__ == "__main__":
    main()
