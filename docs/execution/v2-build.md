# Corrected Pipeline (`_v2`) Build — Execution Record

**Date executed:** 2026-07-12
**Start:** 2026-07-12 13:57:35 UTC — **End:** 2026-07-12 13:59:17 UTC (**1 m 42 s** total)
**Result:** SUCCESS — all five jobs completed with zero errors and zero bad records.

## Provenance

| Item | Value |
|---|---|
| Repository commit | `origin/main` @ `04843e4` (merge of PR #6), clean working tree |
| Script | `scripts/rebuild_pipeline_v2.py` — git blob `ab372db`, sha256 `8ebde017e33a3e1c…bae24c8d` |
| Manifest | `evidence/canonical-source-manifest.csv` — git blob `34a79b4`, sha256 `dd92c27a0ccae8de…beaa352d` |
| SQL | `sql/trips_v2.sql` (`60484e3`), `sql/trips_daily_v2.sql` (`0681c4f`), `sql/materialize_daily_v2.sql` (`beecef0`) — all blob-identical to origin/main |
| Command | `python3 scripts/rebuild_pipeline_v2.py --apply --project msbai-dwd-jrs10127 --dataset citibike --manifest evidence/canonical-source-manifest.csv` |
| Auth | cloud-bootstrap service account `claude-agent@msbai-dwd-jrs10127.iam.gserviceaccount.com` via ADC; access token minted from the decrypted service-account key |

### Pre-execution re-verification (passed immediately before apply)

- All **371** selected GCS objects present in `gs://bigdataday1/staging/`, all **generations matching** the committed manifest (0 missing, 0 mismatched).
- **None of the five `_v2` targets existed** prior to the run.
- Script/manifest/SQL checksums matched `origin/main` exactly (table above).

## Jobs (from the BigQuery Jobs API — see `evidence/v2-build-jobs.csv`)

| # | Job ID | Type | Destination | Result |
|---|---|---|---|---|
| 1 | `job_1CpLlFgGJUex4c_BRfKMf0oB0lZz` | load | `citibike.raw_pre2021_v2` | 113 URIs / 113 files, 16,204,176,908 B in → **91,944,421 rows**, 0 bad, 36.5 s |
| 2 | `job_SvbbTiaWxR6yefrNLr6ps83Q9SMC` | load | `citibike.raw_post2021_v2` | 258 URIs / 258 files, 41,972,532,910 B in → **216,249,376 rows**, 0 bad, 29.9 s |
| 3 | `job_HyszYs_aLopQtxDzUO0kBylohJtr` | query (CREATE VIEW) | `citibike.trips_v2` | 0 B processed, 0.1 s |
| 4 | `job_sYImK5FOOrG-b7LknkTUUgMT7fvB` | query (CREATE VIEW) | `citibike.trips_daily_v2` | 0 B processed, 0.1 s |
| 5 | `job_dSMqm8uqIk8589JRrHQG9FKmWT-O` | query (CTAS) | `citibike.trips_daily_table_v2` | **34,674,311,168 B billed (32.29 GiB)**, 17.6 s |

**Totals:** 371 input files, 58,176,709,818 bytes ingested (free load ingestion), 308,193,797 raw rows, 0 bad records.
**Billed:** 34,674,311,168 bytes ≈ **$0.20** at on-demand pricing (the only billed job is the materialization).

## Objects created (the only five objects touched)

| Object | Type | Rows | Notes |
|---|---|---|---|
| `citibike.raw_pre2021_v2` | TABLE | 91,944,421 | 15 all-STRING columns, WRITE_TRUNCATE, explicit URIs |
| `citibike.raw_post2021_v2` | TABLE | 216,249,376 | 13 all-STRING columns, WRITE_TRUNCATE, explicit URIs |
| `citibike.trips_v2` | VIEW | — | corrected NY-local timestamp parsing, normalized rider type |
| `citibike.trips_daily_v2` | VIEW | — | daily aggregate on `trips_v2` |
| `citibike.trips_daily_table_v2` | TABLE | 9,654 | clustered by `region, rider_type`; 2013-06-01 → 2026-05-31 |

## Immediate post-build integrity checks (queried only the 434 KB daily table)

- Date range **2013-06-01 → 2026-05-31** (156 months, the previously missing early-2015 dates present).
- Duplicate `(date, region, rider_type)` keys: **0**.
- Null / zero / negative `trip_count`: **0**.
- Regions: `NYC` only. Rider types: `casual`, `member`, `unknown` — **`Customer`/`Subscriber` absent**.

## Scope confirmation

No non-`_v2` resource was modified. The six original objects (`raw_pre2021`, `raw_post2021`, `trips`, `trips_daily`, `trips_daily_model`, `trips_daily_table`) all show last-modified timestamps of 2026-06-10/11 — before this run. No GCS object was created, moved, or deleted; no dashboard, Cloud Run, IAM, or Artifact Registry change; the excluded duplicate 2013/2018 chunk files remain in the bucket untouched.

## Status at time of build

The immediate checks above are structural only. **Independent reconciliation against the course reference (`nyu-datasets.citibike.m_daily_trips`) was still required** and is performed in `docs/verification/v2-reconciliation.md` (this PR).
