# Citi Bike + NYC Weather — Dealing with Data

End-to-end data product for the NYU *Dealing with Data* course: an ETL pipeline
that loads the complete NYC Citi Bike trip history (2013-06 → 2026-05, ~308M
trips) into BigQuery, joins it to daily NYC weather, and serves an interactive
Streamlit dashboard on Cloud Run.

**Live app:** https://citibike-app-kpkbtfmmcq-uc.a.run.app
*Note: the currently deployed revision predates the v2 cutover and still reads
the course fallback table; the next deployment will serve the verified v2
source that this repository's code now defaults to.*

## Architecture

```
Citi Bike official archive (s3.amazonaws.com/tripdata)
        │  zips staged verbatim
        ▼
GCS  gs://bigdataday1/raw/ (archives)  →  staging/ (extracted CSVs)
        │  explicit per-file manifest (evidence/canonical-source-manifest.csv)
        ▼
BigQuery raw tables      citibike.raw_pre2021_v2 · citibike.raw_post2021_v2
        ▼
Unified trip view        citibike.trips_v2          (NY-local timestamps, normalized riders, Haversine km)
        ▼
Daily aggregate view     citibike.trips_daily_v2    (date × region × rider_type)
        ▼
Materialized table       citibike.trips_daily_table_v2   ← dashboard source
        ▼
Streamlit (app.py + query.py)  →  Cloud Run (citibike-app, us-central1)
                       ⇡ joined at query time to nyu-datasets.weather.m_weather_daily_nyc
```

The five **v2 BigQuery objects** (project `msbai-dwd-jrs10127`, dataset
`citibike`) are the corrected pipeline: `raw_pre2021_v2` (91,944,421 rows),
`raw_post2021_v2` (216,249,376 rows), `trips_v2`, `trips_daily_v2`, and
`trips_daily_table_v2` (9,654 rows, clustered by region/rider_type). The
original non-v2 objects are retained only as historical evidence.

## Data verification

The v2 table was verified in three stages (all evidence in this repo):
1. **Reconciliation** against the course reference (`docs/verification/v2-reconciliation.md`) — loss-free build, 2013/2015/2018 defects fixed.
2. **Official-source audit** (`docs/verification/official-source-freshness.md`) — the staged archives are byte-identical (MD5) to the current official Citi Bike archive, and official row counts match `trips_daily_table_v2` exactly (24/26 target months at +0 rows; remainder are cross-archive month-boundary rows). NYC DOT-published totals agree with the project within 0.05%; the course reference overcounts April 2018 (2×) and 2022/2023/May 2024 (~2.4–3.2%).
3. **Cutover decision** (`docs/verification/v2-cutover-decision.md`) — GO for code cutover; deployment pending.

Evidence lives in `evidence/` (manifests, job logs, inventories, row counts)
and `docs/` (execution, verification, repair, recovery records).

## Specifications & decisions

- **Dashboard specification (Part 2):** [`docs/spec/dashboard-spec.md`](docs/spec/dashboard-spec.md) — purpose, audience, business questions, charts, and the per-chart finding requirement.
- **Acceptance criteria:** [`docs/verification/acceptance-criteria.md`](docs/verification/acceptance-criteria.md) — correctness / speed / reach / clarity, each with measurement, result, and pre/post-deployment status.
- **Decisions memo (Parts 1 & 2):** [`docs/decisions/decisions-memo.md`](docs/decisions/decisions-memo.md).
- **Weather-Adjusted Ridership v2 (Stretch 1):** [`docs/verification/weather-model-v2.md`](docs/verification/weather-model-v2.md) — design, holdout, proposed `trips_daily_model_v2`.

## Dashboard configuration

`query.py` centralizes all table names and the source selection via
environment variables (defaults in parentheses):

| Variable | Default |
|---|---|
| `GCP_PROJECT` | `msbai-dwd-jrs10127` |
| `CITIBIKE_SOURCE_MODE` | `v2` (`reference` = course fallback; anything else fails fast) |
| `CITIBIKE_V2_TABLE` | `msbai-dwd-jrs10127.citibike.trips_daily_table_v2` |
| `CITIBIKE_REFERENCE_TABLE` | `nyu-datasets.citibike.m_daily_trips` |
| `WEATHER_TABLE` | `nyu-datasets.weather.m_weather_daily_nyc` |
| `MODEL_TABLE` | `msbai-dwd-jrs10127.citibike.trips_daily_model` |

The dashboard shows the active source in a caption. Total NYC trips include
unknown-rider trips (≈0.017%); the member/casual series never absorb them.

## Setup & safe execution

```bash
pip install -r requirements.txt

# Credentials: cloud-bootstrap (see CLAUDE.md) decrypts the service-account
# key automatically in Claude Code sessions; otherwise set
# GOOGLE_APPLICATION_CREDENTIALS to a key with BigQuery read access.

streamlit run app.py                      # local dashboard (verified v2 source)
CITIBIKE_SOURCE_MODE=reference streamlit run app.py   # course-reference fallback

python3 query.py                          # tiny smoke query (10 days, member)

# Pipeline rebuild is DRY-RUN by default and only ever writes *_v2 objects:
python3 scripts/rebuild_pipeline_v2.py            # plan only, no API calls
python3 scripts/rebuild_pipeline_v2.py --apply    # requires explicit human approval

# Read-only source audit (downloads official archives to temp, deletes after):
python3 scripts/audit_official_source_freshness.py
```

## Known limitations

- Weather coverage ends 2026-05-29, so the trips-weather inner join drops the
  last two trip dates (2026-05-30/31).
- `trips_daily_model` was fitted on the pre-v2 series; its 2022+ "actual"
  counts run ~3% above the verified v2 numbers until refitted.
- Distance is Haversine straight-line between stations — it understates true
  route distance by roughly 20–30%.
- NYC trips only; Jersey City / Hoboken are out of scope.
- The course reference table's known overcounts (April 2018, 2022, 2023,
  May 2024) mean dashboards in `reference` mode will show higher totals for
  those periods.
