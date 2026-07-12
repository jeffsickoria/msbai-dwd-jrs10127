# Corrected Citibike Pipeline (`_v2`) — Build & Validation Plan

**Status:** built, **not executed**. This PR adds a non-destructive corrected pipeline
(manifest, corrected SQL, a dry-run-by-default rebuild script) but creates **no** GCP resource.
The existing objects (`raw_pre2021`, `raw_post2021`, `trips`, `trips_daily`,
`trips_daily_table`, `trips_daily_model`, the Cloud Run app) are left untouched.

## Proven defects and causes (from PR #4 reconciliation and PR #5 diagnosis)

| defect | cause (proven) |
|---|---|
| 2013 & 2018 totals ≈2× / 1.86× reference | `staging/pre2021` holds, for each 2013/2018 month, **both** an unsuffixed full-month `.csv` **and** `_1`/`_2` chunk files of the same month; the single wildcard `WRITE_TRUNCATE` load ingested both. 2018 is absent from `raw_post2021`, so it is intra-table duplication, not a union overlap. |
| Missing early-2015 dates | Jan/Feb/Mar/Jun 2015 files use `M/D/YYYY H:MM` (no seconds); the original view's two `PARSE_TIMESTAMP` formats both fail → NULL → dropped by `trips_daily`. |
| Legacy `Customer`/`Subscriber` labels in 2016–2017 | Old-format (legacy-header) files for Oct 2016–Mar 2017 were stored under `staging/post2021/` and loaded into the new-schema `raw_post2021`; the view's post-branch passed `member_casual` through unnormalized. |
| Day-level jitter vs reference | Local timestamps were parsed as UTC then shifted to Eastern, mis-attributing early-morning trips to the previous day. |

## Canonical file-selection rules (`scripts/build_canonical_manifest.py` → `evidence/canonical-source-manifest.csv`)

- Representation is derived from the filename: **full-month** = unsuffixed
  `YYYYMM-citibike-tripdata.csv`; **chunk** = any split spelling (`_N.csv`,
  `.csv_N.csv`, `-partN.csv`).
- **Exactly one logical representation per (target table, year-month):**
  - If a month has both a full-month file and chunks (only 2013 & 2018), **select the
    full-month file and exclude the chunks** (defect #2: the 2018 chunk set is incomplete
    relative to the full file; defect #3: same rule applied to 2013 — the diagnosis shows the
    full-month files are the complete ones, sizes ≥ chunk sums).
  - Otherwise the month is chunk-only → the whole chunk set is the single representation.
- **Fail-loud** if any month has no selected source, more than one full representation, an
  unknown header, duplicate selected URIs, or a month that selects both full and chunk.
- Excluded objects are **never deleted** — they remain in GCS and are recorded with an
  `exclusion_reason`.

Result: **371 selected / 31 excluded** (the 31 = 10 chunk files from 2013 + 21 from 2018).
Selected coverage **2013-06 → 2026-05, 156 distinct months, no gaps**.

## Schema-routing rules (route by ACTUAL header, not folder — defect #5)

- Header is read via a tiny Range read and despaced/lowercased, then matched:
  legacy = `{tripduration, starttime, stoptime, usertype}` (covers both the lowercase and the
  Title-Case `Trip Duration,Start Time,…` variants); new = `{ride_id, rideable_type,
  started_at, member_casual}`.
- **Legacy header → `raw_pre2021_v2`; new header → `raw_post2021_v2`.**
- The Oct 2016–Mar 2017 files (legacy header, but sitting under `staging/post2021/`) therefore
  route to **`raw_pre2021_v2`**, where they are normalized like every other legacy file.

Routing counts (selected): `raw_pre2021_v2` = **113 files, 79 months (2013-06…2019-12)**;
`raw_post2021_v2` = **258 files, 77 months (2020-01…2026-05)**. Clean era split at 2020 — no
new-schema file before 2020, no legacy file after 2019.

## Corrected timestamp semantics (`sql/trips_v2.sql`)

- Source strings are **New York local civil time**. Parse to a `DATETIME` with
  `SAFE.PARSE_DATETIME` (never to a UTC `TIMESTAMP`), expose it as `started_at_eastern`, and
  derive the instant with `TIMESTAMP(datetime, 'America/New_York')`. The reporting day is
  `DATE(started_at_eastern)`. **No parse-as-UTC-then-shift.**
- Supported formats, in precedence order (layouts are distinct, so order is safe):
  `%Y-%m-%d %H:%M:%E*S`, `%Y-%m-%d %H:%M:%S`, `%Y-%m-%d %H:%M`, `%m/%d/%Y %H:%M:%S`,
  `%m/%d/%Y %H:%M`. The last recovers the no-seconds early-2015 rows.

## Corrected rider-type semantics

Applied **identically in both branches** (`usertype` for pre, `member_casual` for post):
`subscriber|member → member`; `customer|casual → casual`; blank/NULL/anything else →
`unknown`. This removes the leaking `Customer`/`Subscriber` labels.

## Replacement object architecture

```
staging/*  --(explicit selected URIs)-->  raw_pre2021_v2   (legacy, all-STRING)
                                          raw_post2021_v2  (new,    all-STRING)
      -> trips_v2 (view)  -> trips_daily_v2 (view)  -> trips_daily_table_v2 (clustered table)
```

`sql/trips_v2.sql` references only `raw_pre2021_v2` / `raw_post2021_v2`;
`sql/materialize_daily_v2.sql` creates/replaces only `trips_daily_table_v2` (clustered by
`region, rider_type`). All destinations end in `_v2`; the rebuild script refuses any that do
not.

## Estimated affected data volume & costs

| item | value |
|---|---|
| Selected input `raw_pre2021_v2` | ≈ 16.20 GB (113 files) |
| Selected input `raw_post2021_v2` | ≈ 41.97 GB (258 files) |
| Selected total | ≈ 58.18 GB |
| Excluded (dropped 2013/2018 chunks) | ≈ 4.12 GB (31 files) |

- **Loads:** CSV load jobs are **not** billed as query bytes (free ingestion); cost is
  storage of the `_v2` tables (~roughly the input volume, plus BigQuery encoding).
- **Materialization query:** `CREATE TABLE trips_daily_table_v2 AS SELECT … FROM trips_daily_v2`
  scans `trips_v2` (i.e. both `_v2` raw tables). Expect on the order of the corrected raw size
  (~tens of GB) once, at ~\$5/TB on-demand — well under a dollar. Exact bytes should be
  confirmed by a dry-run at `--apply` time.
- The `_v2` raw tables should be **smaller** than the originals (2013/2018 duplicates removed):
  original `raw_pre2021` was 19.33 GB / 109.3M rows.

## Controlled rebuild (`scripts/rebuild_pipeline_v2.py`)

Dry-run by default; `--apply` required to create anything. Uses the explicit selected URIs
(no wildcards), all-STRING schemas, `WRITE_TRUNCATE` on the `_v2` raw tables only, then runs
the three SQL files. Logs job IDs / URIs / row counts / bad records; **stops on any failed
load**; never deletes GCS objects, never touches non-v2 objects, never deploys. `--project`
defaults to `msbai-dwd-jrs10127`, `--dataset` to `citibike`. A `_v2` guard aborts on any
non-`_v2` destination.

## Rollback strategy

- The rebuild is purely additive: it only creates `*_v2` objects. **Rollback = drop the `_v2`
  objects** (`raw_pre2021_v2`, `raw_post2021_v2`, `trips_v2`, `trips_daily_v2`,
  `trips_daily_table_v2`). No original object is modified, so there is nothing to restore.
- The dashboard stays on the course fallback (`nyu-datasets.citibike.m_daily_trips`) throughout,
  so rollback has zero user-facing impact.
- GCS is untouched (excluded duplicates remain in place), so re-running the manifest/rebuild is
  idempotent.

## Validation sequence (after `--apply`)

1. Dry-run the materialization to record exact bytes billed.
2. Re-run `sql/verification/profile_daily_table.sql` against `trips_daily_table_v2`.
3. Re-run `sql/verification/reconcile_shared_daily.sql` (pointed at `trips_daily_table_v2`)
   vs `nyu-datasets.citibike.m_daily_trips`, including monthly and yearly comparisons and the
   era splits (2013–2020 / 2021–2023 / 2024–2026).
4. Confirm the raw `_v2` yearly counts for 2013 and 2018 fell to ≈1× the reference.
5. Investigate any remaining discrepancy explicitly before proposing cutover.

**The `_v2` daily table must reconcile against `nyu-datasets.citibike.m_daily_trips` before any
cutover of the dashboard.**

## Acceptance criteria

- [ ] No duplicate `(date, region, rider_type)` rows in `trips_daily_table_v2`.
- [ ] No legacy `Customer`/`Subscriber` rider types (only `member`/`casual`/`unknown`).
- [ ] No missing January 2015 dates attributable to timestamp parsing (Jan/Feb/Mar/Jun 2015
      present).
- [ ] 2013 and 2018 annual totals no longer ≈ doubled (within normal daily variance of the
      reference NYC totals).
- [ ] Monthly and yearly comparisons vs the course reference pass; discrepancies explicitly
      investigated and explained.
- [ ] The existing dashboard remains on the course fallback until validation passes.

## Still requiring human approval before `--apply`

- Explicit approval to create the five `_v2` objects and incur the (small) load/query cost.
- Confirmation of the materialization dry-run byte estimate at run time.
- Sign-off that dropping/rerouting the excluded 2013/2018 duplicates from *future* ingestion
  (a separate PR-D concern) is acceptable — this PR only excludes them from the `_v2` load, it
  does not change GCS.

No GCP resource was created or modified, no table loaded, no view created, no GCS object moved
or deleted, and nothing deployed in this PR. No credentials or secrets appear in any committed
file.
