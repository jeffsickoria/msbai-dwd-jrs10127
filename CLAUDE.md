# Citibike Pipeline — Project Spec

## Scope
- NYC trips only (Jersey City excluded). Reason: ...
- Date range: 2013-present. Reason: ...

## Schema
- Two schemas exist (pre/post 2021). Unified mapping: [list columns]

## Distance
- Computed as Haversine straight-line distance from start/end lat/lon.
- Disclosure: this is not route distance.

## Day Definition
- A trip counts toward the day of its start_time in US/Eastern timezone.

## Pipeline Stages
archive → GCS → raw BQ tables → clean unified view → daily summary view → materialized table

## GCP
- Project: msbai-dwd-jrs10127
- GCS bucket: bigdataday1
- BQ dataset: citibike
- Cloud Run service: citibike-app (us-central1)


##Here are my decisions and reasoning:

**1. NYC vs Jersey City — NYC only.**
The NYC files have 10–100x more trips, giving better statistical power for any analysis. JC files are also inconsistently named (spaces, typos) and start later (Sep 2015). Keeping one geography also avoids the confound of different urban environments and station densities.

**2. Cutoff — 2020 onward (monthly files only).**
Pre-2021 annual bundles bundle 12 months into one zip with unknown internal structure, and the schema change lands around 2021 (old: `starttime`, `tripduration`; new: `started_at`, `ride_id`, `rideable_type`). Starting at 202001 gives clean monthly granularity, a consistent new schema, and still covers 5+ years / 300M+ rows. We discard 2013–2019 annual zips entirely.

**3. Distance — Haversine, disclosed.**
Agreed. Fast to compute at scale, no routing API dependency, reproducible. We document it as straight-line distance and note it underestimates true route distance by ~20–30%.

**4. "Day" — trip `started_at` localized to US/Eastern.**
Captures the rider's behavioral day (commute, weekend leisure, etc.) and aligns with any weather data joined by date.

**5. Files we actually need — from the inventory:**

```
202001-citibike-tripdata.zip  through  202605-citibike-tripdata.zip
```

That's lines 8–40 in `archive_inventory.txt` — **33 files**, all NYC, all monthly, consistent new schema. No JC files, no annual bundles, no `index.html`.

Ready to build the download script?

## Cloud Credentials

Managed by the `cloud-bootstrap` skill (`.claude/skills/cloud-bootstrap/`). Encrypted service-account keys live in the repo; plaintext keys never do.

- **Provider / project:** GCP, `msbai-dwd-jrs10127`
- **Service account:** `claude-agent@msbai-dwd-jrs10127.iam.gserviceaccount.com`
- **Roles granted:**
  - `roles/bigquery.dataEditor` — query and maintain tables in the `citibike` dataset
  - `roles/bigquery.jobUser` — required to run any BigQuery job
  - `roles/storage.objectAdmin` — list/manage objects in `bigdataday1` (project-level; a bucket-scoped binding was attempted but the bootstrapping account lacks `storage.buckets.getIamPolicy` on that specific bucket — see note below)
  - `roles/run.developer` — inspect and deploy the `citibike-app` Cloud Run service
  - `roles/artifactregistry.writer` — build and push the app's container image
- **Multi-user setup:** each team member has their own `.cloud-credentials.<email>.enc`, encrypted with their own passphrase (`CLOUD_CREDENTIALS_KEY` / `GCP_CREDENTIALS_KEY` env var, never committed).
- **Authenticating:** automatic — the `SessionStart` hook (`.claude/hooks/cloud-auth.sh`) decrypts credentials and activates `gcloud` + Application Default Credentials at the start of each session.
- **Adding a team member:** ask Claude to "add cloud access for `<email>`" — it follows the skill's `add-team-member` workflow using an existing member's bootstrap token.
- **Escalating permissions:** if a command fails with 403, ask Claude to fix it — it will identify the specific missing role and ask you to grant it (it will not modify IAM policy without approval).

**Known gap:** `bigdataday1` appears to be a shared bucket outside this project's IAM scope for the current user — bucket-level object listing may need the bucket owner to grant `roles/storage.objectViewer` (or similar) directly to `claude-agent@msbai-dwd-jrs10127.iam.gserviceaccount.com` on the bucket.
