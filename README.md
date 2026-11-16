# Citi Bike Ridership and NYC Weather

**How does daily Citi Bike usage change with weather, and which days are unusual enough to investigate?** This NYU Stern *Dealing with Data* project combines about **308 million NYC trips** from June 2013 through May 2026 with daily weather and presents the results in Streamlit.

[Open the hosted dashboard](https://citibike-app-kpkbtfmmcq-uc.a.run.app) · [Model validation](docs/verification/weather-model-v2.md) · [Source reconciliation](docs/verification/official-source-freshness.md)

## What to explore

1. Compare member and casual ridership across dates and weather conditions.
2. Compare observed ridership with the weather-adjusted historical baseline and inspect flagged days.
3. Check the active data source and date range before interpreting the charts.

## What the project delivered

- **Verified data pipeline.** Staged official Citi Bike archives in Cloud Storage, reconciled trip counts against published sources, and served the dashboard from a materialized BigQuery daily table.
- **Measured model performance.** On a 179-day holdout, the total-ridership baseline reduced mean absolute error by **18.0%** against a seasonal-naive benchmark. It also underpredicted part of the recent growth period. Its intended use is historical anomaly review.
- **Clear coverage.** The trip archive ends May 31, 2026. The joined weather analysis ends May 29, 2026. Jersey City and Hoboken are outside the project scope.

The deployment record identifies the verified dashboard revision at the time of the project. See the [deployment evidence](evidence/stage3-model-v2-deployment.csv) for that checkpoint.

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
`trips_daily_table_v2` (9,654 rows, monthly partitioned on `date` and
clustered by `region, rider_type`). The original non-v2 objects are retained 
only as historical evidence.

## Data verification

The v2 table was verified in three stages (all evidence in this repo):
1. **Reconciliation** against the course reference (`docs/verification/v2-reconciliation.md`) — loss-free build, 2013/2015/2018 defects fixed.
2. **Official-source audit** (`docs/verification/official-source-freshness.md`) — the staged archives are byte-identical (MD5) to the current official Citi Bike archive, and official row counts match `trips_daily_table_v2` exactly (24/26 target months at +0 rows; remainder are cross-archive month-boundary rows). NYC DOT-published totals agree with the project within 0.05%; the course reference overcounts April 2018 (2×) and 2022/2023/May 2024 (~2.4–3.2%).
3. **Cutover and deployment** — the verified v2 trip source and `trips_daily_model_v2` were deployed to Cloud Run at the recorded checkpoint. Deployment and external acceptance evidence are recorded under `docs/execution/` and `evidence/`.

Evidence lives in `evidence/` (manifests, job logs, inventories, row counts)
and `docs/` (execution, verification, repair, recovery records).

## Assignment deliverables

| Deliverable | Location |
|---|---|
| Part 2 dashboard specification | [`docs/specifications/part2-dashboard-specification.md`](docs/specifications/part2-dashboard-specification.md) |
| Acceptance criteria (correctness / speed / reach / clarity) | [`docs/specifications/acceptance-criteria.md`](docs/specifications/acceptance-criteria.md) |
| Decisions memo (Parts 1 & 2) | [`docs/decisions/parts-1-and-2-decisions.md`](docs/decisions/parts-1-and-2-decisions.md) |
| Ingestion / staging script | [`scripts/ingest_and_stage_archives.py`](scripts/ingest_and_stage_archives.py) |
| Reconciliation & official-source evidence | [`docs/verification/v2-reconciliation.md`](docs/verification/v2-reconciliation.md), [`docs/verification/official-source-freshness.md`](docs/verification/official-source-freshness.md) |
| Deployment evidence | [`docs/execution/dashboard-v2-deployment.md`](docs/execution/dashboard-v2-deployment.md), [`evidence/dashboard-deployment.csv`](evidence/dashboard-deployment.csv) |
| Weather-Adjusted Ridership v2 (Stretch 1) | [`docs/verification/weather-model-v2.md`](docs/verification/weather-model-v2.md), [`scripts/build_weather_model_v2.py`](scripts/build_weather_model_v2.py) |
| Public dashboard | https://citibike-app-kpkbtfmmcq-uc.a.run.app |
| BigQuery project & objects | project `msbai-dwd-jrs10127`; clean view `citibike.trips_v2`; daily view `citibike.trips_daily_v2`; materialized table `citibike.trips_daily_table_v2` |

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
| `MODEL_TABLE` | `msbai-dwd-jrs10127.citibike.trips_daily_model_v2` |

The dashboard shows the active source in a caption. Total NYC trips include
unknown-rider trips (≈0.017%); the member/casual series never absorb them.

## Setup & safe execution

```bash
pip install -r requirements.txt

# Configure authorized Google Cloud Application Default Credentials locally.
# The dashboard needs read access to the configured BigQuery data.

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
- The Weather-Adjusted Ridership model is descriptive rather than causal.
  Flagged dates fall outside the model's typical error range and merit
  investigation, but they do not prove an operational issue, event effect,
  bike shortage, or promotion impact.
- Distance is Haversine straight-line between stations — it understates true
  route distance by roughly 20–30%.
- NYC trips only; Jersey City / Hoboken are out of scope.
- The course reference table's known overcounts (April 2018, 2022, 2023,
  May 2024) mean dashboards in `reference` mode will show higher totals for
  those periods.
