# Stage 3 — Weather-Adjusted v2 Dashboard Deployment

**Date:** 2026-07-13 · **Result:** SUCCESS (deployed once, no rollback).
**Authorized scope:** one controlled Cloud Run deployment to `citibike-app`,
plus the Cloud Build + Artifact Registry writes needed to build the image (and
a build-source archive under `cloudbuild-source/`). No BigQuery/GCS-data/
manifest/IAM/billing/GitHub change; no other Cloud Run service touched.

## Source
Merged `main` commit **`c4ed5631ded2a6e700160f7ade6002ba0ff60454`** (PR #12
merge). This is the first image to carry the PR #11 dashboard code (model
v1/v2 detection, per-chart findings, expected-range band) **and** point
`MODEL_TABLE` at the v2 model — the previously deployed revision ran an older
image against the v1 model table.

## Build
| Item | Value |
|---|---|
| Build system | Cloud Build (local Docker unavailable), run as `claude-agent@…` SA, `logging=CLOUD_LOGGING_ONLY` |
| Build ID | `51a86370-8881-4e59-93b9-dd2de755575d` |
| Source archive | `gs://bigdataday1/cloudbuild-source/citibike-app-c4ed563.tar.gz` (Dockerfile + requirements.txt + app.py + query.py) |
| Image tags | `…/citibike/app:c4ed5631…` and `:latest` |
| Image digest | `sha256:236fdc10e474997c69839104d6ad142a5004bf18d2ad238ec1ac98d578b38be9` |
| Start / finish | 2026-07-13 00:28:23Z → 00:29:50Z (~87 s) |
| Result | SUCCESS |

## Deployment
Deployed once via the Cloud Run Admin (Knative) API, image pinned by digest.
Previous serving revision **`citibike-app-00004-52b`** → new
**`citibike-app-00005-t4q`**, Ready, **100% traffic**.

**Production environment variables (exact):**
```
GCP_PROJECT=msbai-dwd-jrs10127
CITIBIKE_SOURCE_MODE=v2
CITIBIKE_V2_TABLE=msbai-dwd-jrs10127.citibike.trips_daily_table_v2
CITIBIKE_REFERENCE_TABLE=nyu-datasets.citibike.m_daily_trips
WEATHER_TABLE=nyu-datasets.weather.m_weather_daily_nyc
MODEL_TABLE=msbai-dwd-jrs10127.citibike.trips_daily_model_v2
```

**Preserved settings (unchanged):** service account `claude-agent@…`, CPU 1,
memory 1Gi, concurrency 80, timeout 300 s, minScale 0 / maxScale 3,
cpu-throttling off, session affinity off, ingress all, public
(`allUsers → roles/run.invoker`).

## Pre-deployment verification (all PASS)
`py_compile` clean; unit tests 9+8+7; `test_chart_findings` AppTest 5/5;
AppTest with the exact production env — model band + flags active,
non-causation caveat present, pre-v2 caveat absent, no errors; headless
Streamlit health `ok` in ~1.05 s. BigQuery confirmed: `trips_daily_table_v2`
MONTH-partitioned on `date`, clustered `region, rider_type`;
`trips_daily_model_v2` present with a single `model_version = wa_v2_ols_1`;
weather table readable.

## Post-deployment verification
**Server-side (PASS):** new revision `citibike-app-00005-t4q` Ready; 100%
traffic; deployed digest = build digest `sha256:236fdc10…`; all six env vars
correct; public IAM binding `allUsers → roles/run.invoker`; active trip source
`trips_daily_table_v2`; active model source `trips_daily_model_v2`.

**Dashboard (local-equivalent, exact deployed env — PASS):** the deployed image
runs the committed `c4ed563` code with the production env; verified via
Streamlit AppTest that the app renders: the verified-v2 trip-source caption; the
data-quality disclosure; total rides including unknown riders; separate
member/casual results; all five chart sections; a data-derived direction-and-
magnitude finding for every chart (5/5); actual-vs-expected with lower/upper
expected bounds (the band); visibly flagged unusually high/low dates; the
non-causation caveat; and **no** pre-v2 model caveat. Date and rider controls
are present and wired; caching decorators (`cache_resource` + `cache_data`)
intact so control changes reuse cached source data; no visible application
error.

**No data resource modified:** BigQuery table modified timestamps are from
Stage 2 (`trips_daily_table_v2` 00:17Z, `trips_daily_model_v2` 00:18Z) or
earlier (`trips_daily_model` 2026-06-11, untouched); `staging/` newest object
2026-06-10 — none changed by this deploy. No GCS-data/IAM/billing change.

### Sandbox egress limitation (explicit)
The live `*.run.app` URL is **not reachable from the build sandbox** — the
egress proxy returns HTTP 000 / 403 CONNECT for `*.run.app`. Therefore all
dashboard-content checks above are **server-side + local-equivalent** (identical
image code + identical production env), not a real-browser fetch of the live
URL. **External browser verification remains PENDING** and must be done from a
real browser (see below).

## Rollback
Not used (no rollback condition triggered). Rollback target: previous revision
**`citibike-app-00004-52b`** (digest `sha256:ffe03a39…`). To roll back:
route 100% traffic back to it (Cloud Run revert / traffic update), e.g.
`gcloud run services update-traffic citibike-app --region us-central1 --to-revisions citibike-app-00004-52b=100`, or PUT the service traffic block to that revision. No BigQuery rollback is involved.

## Cloud resources created or modified (complete list)
- **Created:** Artifact Registry image `…/citibike/app@sha256:236fdc10…`
  (tags `c4ed5631…`, `latest`); Cloud Run revision `citibike-app-00005-t4q`;
  build-source object `gs://bigdataday1/cloudbuild-source/citibike-app-c4ed563.tar.gz`.
- **Modified:** Cloud Run service `citibike-app` now serves the new revision
  with `MODEL_TABLE=…trips_daily_model_v2`.
- **Untouched:** all BigQuery tables/views (incl. `trips_daily_model`, the
  backup, and `_preswap`), GCS raw/staging trip data, the canonical manifest,
  IAM, billing, GitHub, and every other Cloud Run service.

## Cost
Cloud Build ~87 s (well within free tier); Cloud Run serving is request-based
with `minScale=0`; no BigQuery query cost incurred by the deploy. Effectively
$0.00 for this stage.

## Stage status
- **Stage 1 — repository preparation:** complete (PR #11, merged).
- **Stage 2 — partition migration:** complete (PR #12, merged).
- **Stage 2 — `trips_daily_model_v2` creation:** complete (PR #12, merged).
- **Stage 3 — deployment:** **complete** (revision `citibike-app-00005-t4q`,
  100% traffic, `MODEL_TABLE=…trips_daily_model_v2`).
- **External acceptance verification:** **PENDING** — requires a real browser
  (see below).

## External tests still required (real browser, not sandbox)
1. Open https://citibike-app-kpkbtfmmcq-uc.a.run.app with no login and confirm it loads.
2. Confirm the v2 source caption + data-quality note are visible.
3. Confirm the model section shows actual-vs-expected with the shaded expected
   range and flagged high/low days, and the non-causation caveat.
4. Confirm every chart shows its one-sentence finding and controls respond.
5. Record cold/warm load times on stable broadband against the
   post-deployment acceptance target (cold ≤ 20 s, warm ≤ 10 s).
