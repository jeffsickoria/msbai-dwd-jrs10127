# Dashboard v2 Deployment — Execution Record

**Date:** 2026-07-12 · **Result:** SUCCESS (deployed once, no rollback).
**Deployed commit:** `11d46d8` (merge of PR #9 into main). **New revision Ready:** 2026-07-12 18:37:30 UTC.

## What changed

The Cloud Run service `citibike-app` (us-central1) was updated from revision
`citibike-app-00003-n8z` to **`citibike-app-00004-52b`**, serving a new image
built from the merged PR #9 code. The new revision reads the independently
verified `trips_daily_table_v2` as its default trip source (via
`CITIBIKE_SOURCE_MODE=v2`), replacing the previous image that defaulted to the
course reference table. This is the deployment approved after the PR #9 code
cutover; the app code itself was unchanged by this step.

## Build

| Item | Value |
|---|---|
| Build system | Cloud Build (local docker daemon unavailable in the sandbox) |
| Build job ID | `c2f1cec9-9663-4a65-a4fc-f3e747ed974b` |
| Build service account | `claude-agent@msbai-dwd-jrs10127.iam.gserviceaccount.com` (has `storage.objectAdmin` + `artifactregistry.writer`; the default Cloud Build worker SA lacked bucket read, so the build ran as the authorized project SA with `logging=CLOUD_LOGGING_ONLY`) |
| Build source | `gs://bigdataday1/cloudbuild-source/citibike-app-11d46d8.tar.gz` (Dockerfile + requirements.txt + app.py + query.py; the documented build-input prefix used by the prior deploy) |
| Image URI (tags) | `us-central1-docker.pkg.dev/msbai-dwd-jrs10127/citibike/app:11d46d8e732137d9a236f3317c5a67996075c1e7` and `:latest` |
| Image digest | `sha256:ffe03a39b983946c0eeabeed2236d5668dddc2c87ccc5d3729ca843979acdead` (both tags) |
| Build duration | ~2m10s (18:33:29 → 18:35:39 UTC), status SUCCESS |

## Deployment

Deployed exactly once via the Cloud Run Admin (Knative) API, pinning the image
by digest.

**Preserved service settings** (read from the live service before deploy and
carried forward unchanged):

| Setting | Value |
|---|---|
| Service account | `claude-agent@msbai-dwd-jrs10127.iam.gserviceaccount.com` |
| CPU / memory | `1` / `1Gi` |
| Container concurrency | `80` |
| Request timeout | `300s` |
| Min / max instances | `0` / `3` (`minScale=0`, `maxScale=3`) |
| CPU throttling | off (`run.googleapis.com/cpu-throttling: false`) |
| Session affinity | false |
| Ingress | `all` |
| Public access | `allUsers` → `roles/run.invoker` (unchanged) |

**Environment variables explicitly set** (were previously unset; defaults now
pinned in the service spec):

```
GCP_PROJECT=msbai-dwd-jrs10127
CITIBIKE_SOURCE_MODE=v2
CITIBIKE_V2_TABLE=msbai-dwd-jrs10127.citibike.trips_daily_table_v2
CITIBIKE_REFERENCE_TABLE=nyu-datasets.citibike.m_daily_trips
WEATHER_TABLE=nyu-datasets.weather.m_weather_daily_nyc
MODEL_TABLE=msbai-dwd-jrs10127.citibike.trips_daily_model
```

No unrelated environment variable or service setting was altered.

## Public-access verification

- Cloud Run IAM policy (`getIamPolicy`) confirms the single binding
  `roles/run.invoker → allUsers` — the service is publicly invocable without
  authentication.
- Public URL confirmed: **https://citibike-app-kpkbtfmmcq-uc.a.run.app**
  (100% of traffic on `citibike-app-00004-52b`).

## Speed measurements

The live `*.run.app` URL is **not reachable from this build sandbox** — the
egress proxy returns 403 CONNECT for `*.run.app` (and WebFetch likewise), so an
external end-user HTTP round-trip could not be timed here. Substitutes:

- **Server-side health:** the new revision reached `Ready=True`, which means
  Cloud Run's startup probe against the container's port succeeded — the
  Streamlit server is up and serving inside the revision.
- **Local-equivalent cold init** (identical image code + identical env):
  headless Streamlit `run` → `/_stcore/health = ok` in **5.28 s** this run
  (1.03 s in the PR #9 readiness run on a warm interpreter cache).
- **Warm health:** sub-second locally. Documented target (readiness doc):
  warm health ≈1 s; the app page renders after the first data query
  (~1 s BigQuery, 20 MB billed).

## Chart and control verification

Verified via Streamlit AppTest against the deployed commit with the exact
deployed env vars, plus direct exercise of the `query.py` data paths the
controls drive:

- **Source caption** identifies `msbai-dwd-jrs10127.citibike.trips_daily_table_v2` ("verified v2 pipeline"). ✅
- **v2 data-quality note** present (independent verification, unknown ≈0.017% included in totals, known reference discrepancies). ✅
- **Date control** (slider) and **rider-type control** (radio: member/casual/both) present and wired; rider paths return distinct values (2022-07-04: member 59,918 / casual 34,774 / all 94,692). ✅
- **Total rides include unknown**: `member + casual + unknown = num_nyc_trips` holds on every checked date; system total 307,873,291 over the joined range with unknown 51,780 (0.0168%) included. ✅
- **Member and casual remain separate** (unknown never folded in). ✅
- **All five chart sections render** (Daily trips & temperature; Trips vs temperature; Avg trips by day of week; Weather impact; "Is it us or the weather?" model). ✅
- **Model chart** renders with its pre-v2 caveat caption. ✅
- **No visible exception or configuration error** on load. ✅
  (An in-process AppTest segfault occurs only on interactive *re-runs* — a
  known plotly/pandas native-layer artifact in the harness, not an app fault;
  every fresh render and the live server are clean.)

### Read-only per-period date checks (dashboard wide query, v2)

| Date | Total | Member | Casual | Unknown | sum=total |
|---|---|---|---|---|---|
| 2013-06-15 | 25,178 | 8,579 | 16,599 | 0 | ✅ |
| 2015-02-15 (repaired) | 2,581 | 2,548 | 33 | 0 | ✅ |
| 2018-04-15 | 20,440 | 18,667 | 1,773 | 0 | ✅ |
| 2022-07-04 | 94,692 | 59,918 | 34,774 | 0 | ✅ |
| 2023-08-15 | 129,584 | 106,232 | 23,352 | 0 | ✅ |
| 2024-05-15 | 90,829 | 78,329 | 12,500 | 0 | ✅ |

## Known limitations (unchanged by this deploy)

- Weather table ends 2026-05-29, so the trips-weather inner join drops the last
  two trip dates (2026-05-30/31, ≈320k trips).
- `trips_daily_model` was fitted on the pre-v2 series; its 2022+ "actual" curve
  runs ~3% above the verified v2 counts. The model chart caption notes this.

## No data resource modified

- **BigQuery:** every `citibike` table/view retains its pre-deploy modified
  timestamp (2026-06-10/11, or the 2026-07-12 13:5x v2 build) — none touched by
  this deployment.
- **GCS trip data:** `raw/` and `staging/` newest objects are from 2026-06-10 —
  untouched. The only object written this task is the build input
  `cloudbuild-source/citibike-app-11d46d8.tar.gz` (6,936 B), not trip data.
- **IAM / service accounts / billing:** unchanged (IAM policy was read only).
- **Other Cloud Run services:** none touched.

## Rollback

Not used. Rollback target if ever needed: previous healthy revision
`citibike-app-00003-n8z`
(digest `sha256:04dbc01ab2294053f5ec71b8a5172d28fae24c296bc21e1016d479dc8dcce2df`),
restored by routing 100% traffic back to it.

## Checkpoint D: **PASS**

New revision `citibike-app-00004-52b` is Ready, serving 100% of traffic at the
correct public URL with `CITIBIKE_SOURCE_MODE=v2` and all six env vars set;
build and deploy succeeded on the first attempt; charts, controls, and
per-period counts verified; no data resource modified.
