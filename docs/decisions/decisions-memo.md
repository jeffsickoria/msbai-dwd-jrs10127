# Decisions Memo — Parts 1 (Pipeline) & 2 (Dashboard)

One consolidated record of the project's decisions with a one-line reason each.
Detailed evidence is linked rather than duplicated.

## Part 1 — Data pipeline
| # | Decision | Reason | Detail |
|---|---|---|---|
| 1 | **NYC only**, exclude Jersey City/Hoboken | one urban geography, ~10–100× volume, consistent station density; avoids a confounded two-city mix | `CLAUDE.md` §Scope |
| 2 | Archive = official `s3.amazonaws.com/tripdata` | authoritative source; staged copies verified byte-identical (MD5) | `docs/verification/official-source-freshness.md` |
| 3 | **One representation per (table, month)** (full-month OR chunks, never both) | prevents the 2013/2018 double-count from ingesting duplicate packagings | `evidence/canonical-source-manifest.csv`, `docs/repair/corrected-pipeline-plan.md` |
| 4 | **Route by actual CSV header**, not folder/filename | Oct 2016–Mar 2017 legacy files live under `post2021/`; header is the truth | `scripts/build_canonical_manifest.py` |
| 5 | Date coverage 2013-06 → 2026-05 (156 months, no gaps) | full available history for trend/seasonality | `docs/execution/v2-build.md` |
| 6 | **Timestamps = New York local civil time**, parse then `TIMESTAMP(dt,'America/New_York')` | source strings are local; never parse-as-UTC-then-shift (the original bug) | `sql/trips_v2.sql` |
| 7 | A **trip's day = `DATE(started_at_eastern)`** | attributes riding to the rider's local day; aligns with daily weather | `sql/trips_daily_v2.sql` |
| 8 | Rider mapping subscriber→member, customer→casual, blank/other→unknown | one vocabulary across both schema eras | `sql/trips_v2.sql` |
| 9 | **Unknown included in total, never folded into member/casual** | faithful to source; unknown ≈0.017% (Oct 2016–Mar 2017) | `sql/trips_daily_v2.sql` |
| 10 | Trip-duration validity: drop negative / > 24 h | removes clock errors and abandoned docks from duration stats | `sql/trips_daily_v2.sql` |
| 11 | **Distance = Haversine straight-line** between stations | fast, reproducible, no routing API; disclosed as ~20–30% under true route | `sql/trips_v2.sql`, `CLAUDE.md` |
| 12 | Layered raw → clean view → daily view → materialized table | isolates all-STRING ingest, semantics, aggregation, and a fast serving table | `CLAUDE.md` §Pipeline |
| 13 | Materialized table **partitioned monthly (`DATE_TRUNC(date,MONTH)`), clustered by region, rider_type** | few rows/day over >150 months → monthly avoids thousands of tiny partitions while staying time-unit partitioned on `date` | `sql/materialize_daily_v2.sql` |
| 14 | Independent reconciliation vs the course reference | quantifies correctness and localizes disagreements | `docs/verification/v2-reconciliation.md` |
| 15 | Official-source freshness audit | proves staged data is current and the reference (not the project) overcounts | `docs/verification/official-source-freshness.md` |
| 16 | Reproducible ingestion/staging script (dry-run default) | closes the previously uncommitted staging stage; safe, manifest-driven | `scripts/prepare_staging.py` |

## Part 2 — Dashboard
| # | Decision | Reason | Detail |
|---|---|---|---|
| 17 | Default trip source = verified `trips_daily_table_v2` | independently verified more accurate than the reference for the disputed periods | `docs/verification/v2-cutover-decision.md` |
| 18 | Env-driven config; `CITIBIKE_SOURCE_MODE` fails on unknown values | no scattered names; never silently pick a source | `query.py` |
| 19 | Weather join `nyu-datasets.weather.m_weather_daily_nyc` (inner) | daily NYC weather; disclosed 2-day tail drop (weather ends 2026-05-29) | `query.py`, `docs/spec/dashboard-spec.md` |
| 20 | Filters = rider type + date range only | the two dimensions non-technical users actually vary; keeps UI legible | `app.py` |
| 21 | Cache client (`cache_resource`) + daily/model reads (`cache_data`, 1 h) | rider switching re-slices cached data; only new date ranges query | `app.py` |
| 22 | Five charts: trend+temp, temp response, day-of-week, weather impact, model | cover the business questions with minimal redundancy | `docs/spec/dashboard-spec.md` |
| 23 | **Every chart shows a data-derived one-sentence finding (direction+magnitude)** | non-technical clarity criterion; no generic claims | `app.py`, `docs/verification/acceptance-criteria.md` |
| 24 | Model = simple interpretable log-space OLS on weather + calendar | interpretable, reproducible; log linearizes multiplicative weather/growth effects | `scripts/build_weather_model_v2.py`, `docs/verification/weather-model-v2.md` |
| 25 | **Global linear growth trend tested and rejected on diagnostics** | it worsened time-based holdout error (unstable extrapolation); month effects absorb within-window structure | `docs/verification/weather-model-v2.md` |
| 26 | Objective flag = outside the model's ~95% prediction band | data-driven, not chosen for visual effect; "merits investigation," not causal | `scripts/build_weather_model_v2.py` |
| 27 | Model limitations disclosed; no causal claims | a flagged day does not prove shortage/outage/event/promotion; growth beyond window unmodeled | `app.py`, `docs/spec/dashboard-spec.md` |
| 28 | Deployed to Cloud Run, public, image pinned by digest, settings preserved | reproducible controlled deploy; code cutover approved separately from build | `docs/execution/dashboard-v2-deployment.md` |
| 29 | **Post-deployment acceptance target** (speed ≤20s/≤10s; clarity finding rule) | closes omitted verification; explicitly labeled post-hoc, not pre-registered | `docs/verification/acceptance-criteria.md` |

## Open items requiring explicit approval (not done here)
Live monthly-partition migration; creating/validating `trips_daily_model_v2`;
one controlled dashboard redeploy pointing `MODEL_TABLE` at the v2 model;
external acceptance retest. See the PR report.
