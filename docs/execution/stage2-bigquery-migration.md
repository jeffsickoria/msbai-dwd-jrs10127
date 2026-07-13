# Stage 2 — BigQuery Partition Migration & Weather-Adjusted Model v2

**Date:** 2026-07-13 · **Branch base:** merged `main` `3fb337a` (PR #11).
**Scope of authorized writes (only these):** create a rollback backup, build a
partitioned candidate, replace `trips_daily_table_v2` in place, and create
`trips_daily_model_v2`. No GCS/Cloud Run/Artifact Registry/IAM/billing change;
the pre-v2 `trips_daily_model` was not touched; no deployment.

## 1. Original daily-table metadata (pre-migration)
`citibike.trips_daily_table_v2`: 9,654 rows, 434,608 bytes, created & modified
2026-07-12 13:59:16Z, **partitioning none**, clustering `[region, rider_type]`,
schema `date DATE, region STRING, rider_type STRING, trip_count INT64,
avg_duration_minutes FLOAT64, avg_distance_km FLOAT64`. Integrity: 4,738
distinct dates, range 2013-06-01…2026-05-31, **SUM(trip_count)=308,193,797**,
0 null dates, 0 negative counts, 0 duplicate (date,region,rider_type) keys.

## 2. Rollback backup
`citibike.trips_daily_table_v2_backup_20260713_001643` — created 2026-07-13
00:16:47Z via a (free) copy job; **expires 2026-08-12** (short-lived); 9,654
rows; SUM(trip_count)=308,193,797; range 2013-06-01…2026-05-31. Retained.

## 3. Candidate build + validation
`citibike.trips_daily_table_v2_candidate` built with the reviewed physical
design — `PARTITION BY DATE_TRUNC(date, MONTH) CLUSTER BY region, rider_type` —
as a partitioned copy of the canonical table (guarantees byte-identical data;
scans only the 434 KB source). Validation vs canonical **ALL PASS**:
identical schema; rows 9,654=9,654; distinct dates 4,738=4,738; min/max
2013-06-01 / 2026-05-31 identical; SUM 308,193,797 identical; 0 null, 0
negative, 0 duplicate keys; partition field `date`, granularity MONTH;
clustering `[region, rider_type]`. **Full-outer-join reconciliation:** 0 extra,
0 missing, 0 measure differences across all 9,654 keys.

## 4. Canonical-table replacement
Near-atomic metadata-only swap (no data scan):
`ALTER TABLE trips_daily_table_v2 RENAME TO trips_daily_table_v2_preswap;`
then `ALTER TABLE trips_daily_table_v2_candidate RENAME TO trips_daily_table_v2;`.
The old cluster-only table is preserved as `_preswap` (extra rollback). Post-swap
validation vs the backup **ALL PASS**: full-outer-join 0 extra / 0 missing / 0
measure diffs / 9,654 matched; 9,654 rows; SUM 308,193,797; range unchanged;
0 null/neg/dup. `query.py` reads the canonical name unchanged (verified by the
Streamlit AppTest in §9); the live Cloud Run app (source mode v2) reads the same
name and is unaffected by the physical repartition.

## 5. Final partition & clustering metadata
| Table | Rows | Partitioning | Clustering |
|---|---|---|---|
| `trips_daily_table_v2` (canonical, new) | 9,654 | MONTH on `date` | region, rider_type |
| `trips_daily_table_v2_preswap` (rollback) | 9,654 | none | region, rider_type |
| `trips_daily_table_v2_backup_20260713_001643` (rollback) | 9,654 | none | region, rider_type |
| `trips_daily_model_v2` (new) | 4,827 | MONTH on `date` | rider_series |

## 6. Model method & features
Builder `scripts/build_weather_model_v2.py` (log1p-target OLS). Inputs (read-only):
`trips_daily_table_v2` ⋈ `nyu-datasets.weather.m_weather_daily_nyc`.
**Final feature list:** `tavg_f`, `tavg_f²`, `prcp_inches`, `snow_inches`,
`C(day_of_week)`, `C(month)`. **Rejected:** a global linear time trend (tested;
degraded holdout — see below); humidity/dewpoint/wind/pressure and `is_*`
one-hots (collinear/redundant). Series: **total (incl. unknown), member,
casual**, each fit independently; unknown stays in total and is never
reassigned (unknown = 0 in the 2022+ window). Modeling window 2022-01-01 →
2026-05-29 (1,609 days; weather complete, inner join drops none).

> **Correction logged this stage:** `build_design` previously added `trend_days`
> unconditionally, so the "no-trend" spec had silently *included* the trend; this
> is fixed (gated on `feature_cols`) and unit-tested. With the fix the no-trend
> spec is genuinely better on every holdout metric and now matches PR #11's own
> diagnostic table (log, no trend). The corrected metrics below supersede the
> trend-on figures mistakenly reported as "final" in PR #11.

## 7. Time-based holdout metrics (train 2022-01-01…2025-11-30 = 1,430 d; holdout 2025-12-01…2026-05-29 = 179 d)
| Series | MAE | MAPE | WAPE | bias (pred−act) | actual tot | pred tot | baseline MAE (month×dow) | improvement | band-flagged |
|---|---|---|---|---|---|---|---|---|---|
| total | 23,808 | 31.7% | 26.1% | −17,630 | 16,307,814 | 13,152,103 | 29,038 | **+18.0%** | 4.23% |
| member | 21,993 | 33.0% | 28.1% | −16,805 | 14,013,594 | 11,005,521 | 25,230 | **+12.8%** | 3.98% |
| casual | 2,595 | 34.4% | 20.3% | −1,083 | 2,294,220 | 2,100,362 | 4,690 | **+44.7%** | 4.97% |

MAPE is inflated by low-volume winter days; the scale-aware **WAPE** (20–28%) is
the more reliable headline, and the model **beats the seasonal-naive baseline on
all three series**. The negative bias is a **disclosed forecasting limitation**:
without a growth term the model under-predicts the recent ramp, so it is
descriptive (flagging within observed history) rather than a forecaster. Gate
condition met: model improves materially over baseline **and** limitations are
disclosed.

## 8. Model-output validation (`trips_daily_model_v2`) — ALL PASS
Schema exactly the 12 required columns; MONTH partition on `date`, clustered by
`rider_series`; 4,827 rows = 4,827 unique (date, rider_series) keys (0 dup);
0 null dates; 0 negative actual; 0 negative expected (expm1 of a log fit ⇒
always ≥0); `lower ≤ expected ≤ upper` for every row; `residual = actual −
expected` (max abs error < 0.5); `percent_gap = 100·residual/expected`
verified; every `gap_flag` = (actual outside [lower, upper]); single
`model_version = wa_v2_ols_1` (no stale pre-v2 rows). Coverage 2022-01-01…
2026-05-29. Per-series flags: total 16 high / 52 low (4.23%); member 14/50
(3.98%); casual 18/62 (4.97%).

## 9. Dashboard compatibility (read-only; no deploy)
`py_compile` clean; unit tests 9+8+7 pass. Streamlit **AppTest** with
`CITIBIKE_SOURCE_MODE=v2`, `CITIBIKE_V2_TABLE=…trips_daily_table_v2`,
`MODEL_TABLE=…trips_daily_model_v2`: no errors; all 5 sections render; 5
data-derived findings (direction + magnitude); the model section shows
actual-vs-expected **with the expected-range band** and high/low flags; the
**non-causation caveat is visible**; the **pre-v2 caveat is not shown** (v2
active); controls reuse cached data (cache decorators asserted). The live Cloud
Run app still has `MODEL_TABLE=…trips_daily_model` (v1) and is unchanged.

## 10. Bytes processed & cost
Copy (backup), the two renames, and the model batch-load are **free**
(no query bytes). Candidate CTAS billed 10,485,760 B (10 MB minimum). The model
input read and all validation/reconciliation queries are on small tables
(≈10 MB minimum-billing each); Stage-2 query bytes billed total ≈ **0.1 GB**,
i.e. **≈ \$0.001** at \$6.25/TiB on-demand. Effectively \$0.00.

## 11. Cloud resources created or modified (complete list)
- **Created:** `trips_daily_table_v2_backup_20260713_001643`, `trips_daily_model_v2`.
- **Created then renamed to canonical:** `trips_daily_table_v2_candidate` → `trips_daily_table_v2`.
- **Renamed (old canonical, retained):** `trips_daily_table_v2` → `trips_daily_table_v2_preswap`.
- **Net effect on canonical:** `trips_daily_table_v2` repartitioned to MONTH/`date`, same data.
- **Untouched:** `trips_daily_model` and every other BigQuery object; GCS, Cloud Run, Artifact Registry, IAM, billing, GitHub.

## 12. Rollback instructions
- **Undo the partition migration** (restore the exact prior table):
  `DROP TABLE citibike.trips_daily_table_v2;`
  `ALTER TABLE citibike.trips_daily_table_v2_preswap RENAME TO trips_daily_table_v2;`
  (Equivalent from the copy: `CREATE OR REPLACE TABLE citibike.trips_daily_table_v2 AS SELECT * FROM citibike.trips_daily_table_v2_backup_20260713_001643;` — but this restores the cluster-only, unpartitioned form.)
- **Undo the model:** `DROP TABLE citibike.trips_daily_model_v2;` (safe — the live
  app's `MODEL_TABLE` still points at the v1 table; nothing depends on v2 until a
  future approved deploy repoints it).
- Backup and `_preswap` are retained (do not delete until Stage 2 is accepted).

## Stage boundaries
- **PR #11 (merged):** repository preparation only (specs, criteria, memo,
  ingestion script, partitioned SQL, model builder, dashboard code) — no cloud change.
- **This stage:** BigQuery partition migration of `trips_daily_table_v2` **done**;
  `trips_daily_model_v2` creation **done**.
- **Still pending (separate approval):** one controlled Cloud Run deployment
  repointing `MODEL_TABLE` → `trips_daily_model_v2`; external acceptance retest.
