# Weather-Adjusted Ridership v2 — Model Design & Holdout Evaluation

Stretch 1. Builder: `scripts/build_weather_model_v2.py` (dry-run/read-only by
default; `--apply` — not run here — would create
`msbai-dwd-jrs10127.citibike.trips_daily_model_v2`). Inputs (read-only):
`trips_daily_table_v2` ⋈ `nyu-datasets.weather.m_weather_daily_nyc`.

## Design
- **Target:** `log1p(trips)`. Weather and growth act multiplicatively; logs
  linearize them and stabilize percentage error (especially for low-count
  casual winter days).
- **Estimator:** ordinary least squares (numpy `lstsq`), one model per series.
- **Features (interpretable, all non-null over the window — verified):**
  `tavg_f` + `tavg_f²` (inverted-U temperature response), `prcp_inches`,
  `snow_inches`, `C(day_of_week)`, `C(month)`.
- **System growth:** a global linear time trend was **tested and rejected** —
  it consistently worsened the time-based holdout (unstable extrapolation of the
  recent ramp). Month fixed-effects absorb within-window seasonal/level
  structure. **Limitation:** expected values do not extrapolate multi-year
  growth beyond the modeling window; a longer horizon would need year
  effects / a spline (future work).
- **Window:** 2022-01-01 → 2026-05-29 (mature system; comparable to the prior
  deployed model so the dashboard section stays meaningful; avoids fitting the
  2013–2019 explosive growth with one trend). Unknown riders are 0 here, so
  total = member + casual in-window, though `total` remains defined as
  all-rider-inclusive.
- **Series:** total (incl. unknown), member, casual — fit independently.

## Diagnostic that drove the design (time-based holdout, last 180 days)
Holdout MAPE by specification (lower is better):

| Series | linear +trend | linear −trend | log +trend | **log −trend (chosen)** |
|---|---|---|---|---|
| total | 66.4% | 41.9% | 43.3% | **31.7%** |
| member | 63.9% | 42.9% | 45.2% | **33.0%** |
| casual | 88.2% | 86.0% | 44.6% | **34.4%** |

Log target roughly halves MAPE; adding the trend never helps. Chosen:
**log, no global trend.**

## Final holdout metrics (chosen spec; time-based, not random)
Train 2022-01-01…2025-11-30 (1,430 days); holdout 2025-12-01…2026-05-29
(179 days); 1,609 modeled days total; weather complete over the window
(inner join drops none). Read-only input scan ≈ 3.6 MB.

| Series | Holdout MAE | Holdout MAPE | Full-refit RMSE (log) | Flagged (95% band) |
|---|---|---|---|---|
| total | 35,298 | 38.3% | 0.229 | 5.84% |
| member | 32,566 | 40.6% | 0.229 | 5.84% |
| casual | 3,377 | 34.6% | 0.278 | 5.72% |

The holdout is the hardest 180 days (winter→spring 2026 growth ramp on a low
winter base), so out-of-sample MAPE is high; the in-window ~95% prediction band
is well-calibrated (~5.8% flagged vs 5% nominal). This is a **descriptive**
model for flagging unusual days within observed history, not a forecaster.

## Proposed output table `trips_daily_model_v2`
`date, rider_series, actual_trips, expected_trips, lower_expected_bound,
upper_expected_bound, residual, percent_gap, gap_flag, model_version,
training_start, training_end` — monthly-partitioned on `date`, clustered by
`rider_series`.

## Flag rule (objective)
`gap_flag = actual outside [expm1(log_expected − 1.96·RMSE_log),
expm1(log_expected + 1.96·RMSE_log)]` — the model's own ~95% band, asymmetric in
level space. A flagged day is **outside the model's typical error range and
merits investigation**; it establishes **no cause** (not proof of a shortage,
outage, event, or promotion).

## Reproduce
`python3 scripts/build_weather_model_v2.py` (read-only holdout + in-memory
build). Unit tests on synthetic fixtures: `tests/test_weather_model_v2.py`.
Creating the table requires `--apply` + explicit approval (not done in this PR).
