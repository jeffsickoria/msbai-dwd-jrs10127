# Citibike Pipeline — Project Spec

## Scope
- **NYC trips only** (Jersey City / Hoboken excluded): larger volume, single
  urban geography, consistent station density. `JC-*` archive files are never
  staged or loaded.
- **Source coverage: 2013-06 through 2026-05** (156 months, no gaps) from the
  official archive `https://s3.amazonaws.com/tripdata/`. Annual bundles cover
  2013–2023; monthly zips cover 2024-01 onward.
- GCP project **`msbai-dwd-jrs10127`** · GCS bucket **`bigdataday1`** ·
  BigQuery dataset **`citibike`** · Cloud Run service **`citibike-app`**
  (us-central1, https://citibike-app-kpkbtfmmcq-uc.a.run.app).

## Pipeline (v2 — the corrected, verified pipeline)
archive → `gs://bigdataday1/raw/` (verbatim zips) → `staging/` (extracted CSVs)
→ canonical manifest → `raw_pre2021_v2` + `raw_post2021_v2` → `trips_v2` view
→ `trips_daily_v2` view → `trips_daily_table_v2` (materialized, clustered) →
Streamlit dashboard.

The **five `_v2` objects are authoritative**. The original non-v2 objects
(`raw_pre2021`, `raw_post2021`, `trips`, `trips_daily`, `trips_daily_table`)
carry known defects (2013/2018 double-loads, 2015 parse gap, timezone shift,
label leakage) and are **retained only as historical evidence — never use them
for analysis and never rebuild them**.

## Canonical manifest rules (`evidence/canonical-source-manifest.csv`)
- Built by `scripts/build_canonical_manifest.py`, which inspects each staged
  CSV's **actual header** — files are routed to `raw_pre2021_v2` (legacy
  15-column schema) or `raw_post2021_v2` (new 13-column `ride_id` schema) by
  header, **not** by folder or filename. (Oct 2016–Mar 2017 files live under
  `staging/post2021/` but have legacy headers and route to pre.)
- **Exactly one logical representation is selected per (table, month)** — where
  a month exists as both a full-month CSV and `_N` chunks, one representation
  is selected and the duplicates are excluded (they stay in GCS, documented).
  This is what prevents the 2013/2018 double-counting.
- Loads use the manifest's **explicit URI list** (never wildcards),
  all-STRING positional schemas, `skipLeadingRows=1`, `WRITE_TRUNCATE`
  (on `_v2` tables only), `maxBadRecords=0`.

## Semantics
- **Timestamps are New York local civil time.** Source strings are parsed with
  `SAFE.PARSE_DATETIME` (5 layouts incl. no-seconds `%m/%d/%Y %H:%M`, which
  recovers early 2015) and the absolute instant is derived via
  `TIMESTAMP(dt, 'America/New_York')`. Never parse as UTC and shift.
- **A trip counts toward the day of its NY-local start time**
  (`DATE(started_at_eastern)`).
- **Rider types normalize to `member`, `casual`, or `unknown`**
  (subscriber→member, customer→casual, blank/other→unknown) identically in
  both schema branches. Unknown is ≈0.0168% of trips (Oct 2016–Mar 2017 only)
  and is included in totals but never folded into member/casual.
- **Distance is Haversine straight-line distance between start/end stations**
  — not traveled route distance (understates routes by ~20–30%). Disclose this
  wherever distance is shown.

## Dashboard
- `query.py` owns all table names and source selection via env vars
  (`CITIBIKE_SOURCE_MODE=v2|reference`, defaults documented in README.md).
  Default source: `trips_daily_table_v2`. `reference` selects the course
  fallback `nyu-datasets.citibike.m_daily_trips`; any other value fails fast.
- Weather join: `nyu-datasets.weather.m_weather_daily_nyc` (currently ends
  2026-05-29, so the inner join drops the last two trip dates).
  Model section: `msbai-dwd-jrs10127.citibike.trips_daily_model` (fitted
  pre-v2; its 2022+ actuals run ~3% above v2 until refitted).
- **The live Cloud Run app has NOT yet been redeployed with the v2 source** —
  it still serves the course-reference build until a separately approved
  deployment.

## Verification status (evidence under `docs/` and `evidence/`)
- `docs/execution/v2-build.md` — the one-shot `_v2` build record (job IDs, 0 bad records).
- `docs/verification/v2-reconciliation.md` — reconciliation vs the course reference.
- `docs/verification/official-source-freshness.md` — staged archives are
  byte-identical to the current official archive; official row counts match
  `trips_daily_table_v2`; the course reference overcounts April 2018 (exactly
  2×) and 2022/2023/May 2024 (~2.4–3.2%).
- `docs/verification/v2-cutover-decision.md` — decision record: v2 approved as
  the dashboard source; code cutover done, deployment pending.

## Procedures
- **Verification:** re-run `sql/verification/*.sql` sections individually
  (they touch only the small daily/reference tables, ~1 MB scans);
  `scripts/audit_official_source_freshness.py` re-audits the official archive
  read-only. Validate dashboard changes with
  `python3 -m py_compile app.py query.py`, Streamlit AppTest (both source
  modes), and BigQuery dry runs before executing anything.
- **Pipeline rebuild:** `scripts/rebuild_pipeline_v2.py` is dry-run by default,
  writes only `_v2` destinations, and requires `--apply` plus explicit human
  approval. There is currently **no reason to rebuild** — sources are verified
  current.
- **Deployment:** build the container per `Dockerfile`, push via Artifact
  Registry, deploy to Cloud Run `citibike-app` — only with explicit approval,
  and set `CITIBIKE_SOURCE_MODE` deliberately.
- **Never modify or delete cloud resources (BigQuery objects, GCS objects,
  Cloud Run services, IAM, Artifact Registry) without explicit human
  approval.** Read-only inspection is always fine. Never touch non-v2 objects
  or the excluded duplicate files in GCS at all.

## Cloud Credentials

Managed by the `cloud-bootstrap` skill (`.claude/skills/cloud-bootstrap/`). Encrypted service-account keys live in the repo; plaintext keys never do.

- **Provider / project:** GCP, `msbai-dwd-jrs10127`
- **Service account:** `claude-agent@msbai-dwd-jrs10127.iam.gserviceaccount.com`
- **Roles granted:**
  - `roles/bigquery.dataEditor` — query and maintain tables in the `citibike` dataset
  - `roles/bigquery.jobUser` — required to run any BigQuery job
  - `roles/storage.objectAdmin` — list/manage objects in `bigdataday1` (project-level; verified working for object listing)
  - `roles/run.developer` — inspect and deploy the `citibike-app` Cloud Run service
  - `roles/artifactregistry.writer` — build and push the app's container image
- **Multi-user setup:** each team member has their own `.cloud-credentials.<email>.enc`, encrypted with their own passphrase (`CLOUD_CREDENTIALS_KEY` / `GCP_CREDENTIALS_KEY` env var, never committed).
- **Authenticating:** automatic — the `SessionStart` hook (`.claude/hooks/cloud-auth.sh`) decrypts credentials and activates `gcloud` + Application Default Credentials at the start of each session. (If the sandbox blocks the gcloud SDK installer, decrypt per the skill's authenticate workflow and use the Python clients via `GOOGLE_APPLICATION_CREDENTIALS`.)
- **Adding a team member:** ask Claude to "add cloud access for `<email>`" — it follows the skill's `add-team-member` workflow using an existing member's bootstrap token.
- **Escalating permissions:** if a command fails with 403, ask Claude to fix it — it will identify the specific missing role and ask you to grant it (it will not modify IAM policy without approval).

**Note:** setting a *bucket-level* IAM policy on `bigdataday1` failed (`storage.buckets.getIamPolicy` denied for the bootstrapping user account), but this had no practical effect — the project-level `roles/storage.objectAdmin` binding already grants the service account full object read/write on the bucket, confirmed by a live listing.
