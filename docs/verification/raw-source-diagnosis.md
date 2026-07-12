# Raw-Source & Load-History Diagnosis

**Date:** 2026-07-12 · **Mode:** read-only. No GCS object, BigQuery table, or view was
created, modified, reloaded, or deleted. BigQuery job history was read via `jobs.list`; GCS via
object metadata; staging CSVs via tiny HTTP Range reads (headers + first rows only, never full
downloads). Phase-2 raw queries were dry-run, capped with `maximum_bytes_billed`, and limited to
one executed query per raw table.

Goal: prove the origin of (a) the 2013 & 2018 double-counting, (b) the missing early-2015 dates,
and (c) the 2016–2017 legacy rider labels — established as *symptoms* in PR #4.

Evidence artifacts in this PR:
- `evidence/bigquery-load-jobs.csv` — all 4 LOAD jobs with full config/stats.
- `evidence/gcs-source-inventory.csv` — deterministic inventory of all 443 bucket objects.
- `scripts/audit_load_history.py` — reproducible generator of both CSVs + the analysis.
- `sql/verification/raw_source_diagnostics.sql` — the two bounded raw queries.

---

## Phase 1 — load provenance (no raw scans)

### Load jobs (from `jobs.list`; `INFORMATION_SCHEMA.JOBS*` is denied to the restricted SA)

Exactly **four** LOAD jobs exist in project history; the two relevant ones:

| dest | write | format | skipRows | source URI | input files | output rows |
|---|---|---|---|---|---|---|
| `citibike.raw_pre2021` | **WRITE_TRUNCATE** | CSV | 1 | `gs://bigdataday1/staging/pre2021/*.csv` | 136 | 109,278,654 |
| `citibike.raw_post2021` | **WRITE_TRUNCATE** | CSV | 1 | `gs://bigdataday1/staging/post2021/*.csv` | 266 | 222,078,370 |

(The other two loads write `trips_daily_model` from Parquet — unrelated.)

**Conclusion:** each raw table was loaded **once**, with `WRITE_TRUNCATE`, from a **single
wildcard** over one staging folder. There are **no repeated loads, no `WRITE_APPEND`, no
re-append after rebuild, and no cross-table misrouting**. The doubling therefore did **not**
happen at BigQuery load time. `input_files` (136 / 266) equals the object count in each staging
folder, so the load ingested every staging CSV present — no more, no less.

### GCS inventory highlights (`evidence/gcs-source-inventory.csv`)

- 443 objects: 41 under `raw/`, 136 under `staging/pre2021/`, 266 under `staging/post2021/`,
  1 build tarball.
- **No two staging objects share an MD5 hash** → there are **no identical duplicate files**.
- Staging file counts by year × folder:

  | year | pre2021 | post2021 | note |
  |---|---|---|---|
  | 2013 | 17 | 0 | **>12: has full-month `.csv` *and* `_N` chunks** |
  | 2014 | 12 | 0 | one representation/month |
  | 2015 | 16 | 0 | one representation/month (but see gap) |
  | 2016 | 15 | 5 | pre=Jan–Sep, post=Oct–Dec (complementary) |
  | 2017 | 17 | 3 | pre=Apr–Dec, post=Jan–Mar (complementary) |
  | 2018 | 33 | 0 | **>12: full-month `.csv` *and* `_1`/`_2` chunks** |
  | 2019 | 26 | 0 | only `_1`/`_2`/`_3` chunks (no full-month file) |
  | 2020–2026 | 0 | 27–53 | post-schema only |

- For **2013** and **2018**, every month has BOTH an unsuffixed `YYYYMM-citibike-tripdata.csv`
  (the whole month) **and** split chunks `..._1.csv` / `..._2.csv` of the same month. Sampled
  first data rows are identical between the two (e.g. `201306-...csv` and `201306-..._1.csv`
  both start `695,…00:00:01` / `693,…00:00:08`; `201801-...csv` and `..._1.csv` both start
  `970,…13:50:57`). File sizes corroborate: for 2018-05 the full file (346 MB) ≈ `_1` (177 MB)
  + `_2` (151 MB).
- **2019** (a correct year) has **only** `_N` chunks and no unsuffixed full file — i.e. one
  representation per month. This is the control case that isolates the 2013/2018 pattern.
- **2015**: January exists in staging (`201501-citibike-tripdata_1.csv`) — the gap is **not** a
  missing file.

### Staging header samples (tiny Range reads)

| file | `starttime` sample | format |
|---|---|---|
| `201306-…_1.csv` | `2013-06-01 00:00:01` | ISO seconds |
| `201406-…_1.csv` | `2014-06-01 00:00:02` | ISO seconds |
| **`201501-…_1.csv`** | **`1/1/2015 0:01`** | **`M/D/YYYY H:MM` — no seconds** |
| `201801-…_1.csv` | `2018-01-01 13:50:57.4340` | ISO fractional |
| `201901-…_1.csv` | `2019-01-01 00:01:47.4010` | ISO fractional |

The `trips` view parses `starttime` only with `'%m/%d/%Y %H:%M:%S'` or `'%Y-%m-%d %H:%M:%E*S'`.
A value like `1/1/2015 0:01` (no seconds) matches **neither** → `SAFE.PARSE_TIMESTAMP` returns
NULL.

---

## Phase 2 — bounded raw diagnostics (`sql/verification/raw_source_diagnostics.sql`)

Executed after dry-run; **29.03 GB total** (Q1 `raw_pre2021` 8.36 GB, Q2 `raw_post2021`
20.68 GB), each under an explicit `maximum_bytes_billed` cap; combined well under the 100 GB
stop. One query per raw table. The `trips`/`trips_daily` views were **not** queried.

Fingerprint caveat (surrogate, as declared): the pre2021 fingerprint concatenates
`starttime|stoptime|bikeid|start_station_id|end_station_id`. The duplicate 2013 files differ in
numeric **formatting** (e.g. `434` vs `434.0`), so the surrogate does **not** always match
across the duplicate pair — fingerprint-based duplicate counts are therefore a **lower bound**.
The reliable doubling proof is **raw row count vs the course reference** (`num_nyc_trips`).

### 2013 / 2018 doubling — CONFIRMED (intra-`raw_pre2021`)

- `raw_pre2021` yearly totals vs PR #4 reference:
  - **2013:** 11,229,776 rows vs reference 5,614,888 → **2.00×**.
  - **2018:** 35,096,678 rows vs reference 18,855,882 → **1.86×**.
- Fingerprint dedup directly caught ~50% duplicate rows in the months whose duplicate files
  share formatting (2013-07…12 and 2018-01…07; e.g. 2018-01: 1,437,988 rows, ~715,979 distinct,
  ~722,009 duplicates). Months where the paired files differ in formatting (e.g. 2013-06) show
  ~0 fingerprint duplicates yet still ~2× the reference — the surrogate under-counts there, as
  noted.
- **2018 does not exist in `raw_post2021`** (Q2 returns no 2018 rows) → the 2018 inflation is
  **entirely within `raw_pre2021`**, i.e. duplicate staging files, **not** a pre/post union
  overlap.

### 2015 gap — CONFIRMED (view timestamp-parse failure on no-seconds months)

`raw_pre2021` rows where the **view's** formats fail (`rows_unparseable_by_view = total_rows`):

| month | rows | unparseable by view |
|---|---|---|
| 2015-01 | 285,552 | **285,552 (100%)** |
| 2015-02 | 196,930 | **196,930 (100%)** |
| 2015-03 | 341,826 | **341,826 (100%)** |
| 2015-06 | 941,219 | **941,219 (100%)** |
| 2015-04/05/07…12 | — | 0 |

Those four months use `M/D/YYYY H:MM` (no seconds); the view yields NULL `started_at_eastern`,
and `trips_daily` drops them (`WHERE started_at_eastern IS NOT NULL`). Total dropped =
**1,765,527 rows** ≈ the 2015 shortfall PR #4 measured (proj 8.17M vs ref 9.94M ≈ −1.76M), and
Jan+Feb+Mar+Jun ≈ 120 days ≈ the 123 missing days. The data **is** in the raw table; the view
silently discards it.

### 2016–2017 legacy labels — CONFIRMED (old-format files loaded into the new-schema table)

`raw_post2021` months (Q2) 2016-10 → 2017-03 (plus a 41-row 2017-04 boundary spill) carry
`member_casual` values **`Customer` / `Subscriber`** (the *old* `usertype` vocabulary). The
`trips` view's post-branch passes `member_casual` through **unnormalized**, so those legacy
labels surface in `trips_daily_table` for exactly that window. Fingerprints are ~fully distinct
(1,568,087 of 1,573,757 for 2016-10) → **not** duplicated, consistent with 2016/2017 totals
matching the reference. (`ride_id` is near-constant for these back-filled old rows, so
`ride_id` distinctness is meaningless here — expected, since old-format files have no ride_id.)

Because `staging/pre2021` holds the *other* 2016–2017 months (Jan–Sep 2016, Apr–Dec 2017) and
`staging/post2021` holds Oct 2016–Mar 2017, each 2016–2017 month lives in **exactly one** folder
— complementary, no overlap — which is why those years are not doubled.

---

## Where each defect originated

| defect | extraction/staging | loading | view-union | proven? |
|---|---|---|---|---|
| 2013 & 2018 doubling | **YES** — duplicate full-month `.csv` + `_N` chunk files created in `staging/pre2021` | surfaced (wildcard truncate-load ingested both) | no | **Confirmed** (row count = 2.00×/1.86× reference; 2018 absent from post2021) |
| 2015 gap | source files use no-seconds timestamps | loaded fine (rows present in raw) | **view** drops them via failed `PARSE_TIMESTAMP` | **Confirmed** (100% unparseable for Jan/Feb/Mar/Jun 2015; dropped volume = shortfall) |
| 2016–2017 labels | old-format files binned into `staging/post2021` | loaded into new-schema table (usertype→member_casual) | view post-branch passes through unnormalized | **Confirmed** (post2021 labels = Customer/Subscriber) |

## Duplication taxonomy (explicitly distinguished)

- **Identical duplicate files:** none (no shared MD5 across staging).
- **Different files with overlapping/identical dates:** the cause of 2013/2018 — unsuffixed
  full-month `.csv` vs `_N` chunk files for the same month (different bytes/formatting, same
  trips).
- **Repeated BigQuery loads:** none (single `WRITE_TRUNCATE` per table).
- **Duplicate rows within one source file:** not observed as the driver; duplication is across
  sibling staging objects, which then appear as duplicate rows in `raw_pre2021`.

## Hypotheses ruled out

- **Jersey City contamination** (already doubted in PR #4): unchanged — the defects are
  duplication and parsing, not JC leakage.
- **pre/post raw-table overlap for 2018:** ruled out — 2018 is absent from `raw_post2021`.
- **Repeated / appended BigQuery loads:** ruled out by load history.
- **A missing January-2015 file:** ruled out — the file exists; the view discards its rows.
- **`UNION ALL` (view) as the doubling source:** ruled out — the duplication is already present
  inside `raw_pre2021` before any union.

## Bytes processed by executed raw queries

Q1 `raw_pre2021` 8,355,257,534 B (8.36 GB); Q2 `raw_post2021` 20,677,823,601 B (20.68 GB);
**total 29,033,081,135 B ≈ 29.03 GB**. All small metadata/inventory queries in Phase 1 used
`jobs.list` + object metadata + Range reads (negligible).

---

## Proposed correction plan (NOT implemented here)

1. **De-duplicate `staging/pre2021` for 2013 & 2018.** For each affected month, keep exactly one
   representation — either the single full-month `.csv` **or** the `_N` chunk set, not both.
   (2019's chunk-only layout is the correct template.) Affected objects: the 17 (2013) and 33
   (2018) objects under `staging/pre2021/` listed in `evidence/gcs-source-inventory.csv`.
2. **Fix the timestamp parser in `sql/trips.sql`.** Add the no-seconds formats
   (`'%m/%d/%Y %H:%M'`, and defensively `'%Y-%m-%d %H:%M'`) to the `COALESCE`, and parse the
   local strings as **America/New_York** rather than parsing naive-UTC then shifting (the
   day-boundary issue from PR #4). This recovers Jan/Feb/Mar/Jun 2015.
3. **Normalize rider type on the post branch too.** Apply the same
   `subscriber→member / customer→casual` mapping to `raw_post2021.member_casual` so the
   2016–2017 back-filled old labels stop leaking through. (Optional: relabel/relocate those
   old-format files, but the view fix is sufficient for correctness.)
4. **Rebuild** `trips_daily_table` from the corrected view, then re-run PR #4's reconciliation.

### Cloud objects the eventual fix would touch

- GCS: duplicate 2013/2018 objects under `gs://bigdataday1/staging/pre2021/` (removal or
  re-stage). Nothing else in the bucket.
- BigQuery: `raw_pre2021` would be reloaded from the de-duplicated staging set;
  `citibike.trips` view redefined (parser + post-branch normalization); `trips_daily_table`
  rematerialized. `raw_post2021`, `trips_daily_model`, and the reference dataset are untouched.
- No Cloud Run / IAM / Artifact Registry changes.

### How the correction would be verified independently

- After reload, `raw_pre2021` yearly row counts for 2013 and 2018 should fall to ≈1× the course
  reference `num_nyc_trips` (from ~11.23M→~5.61M and ~35.1M→~18.86M).
- `SELECT COUNTIF(view-parse IS NULL)` on 2015 months should be 0.
- Re-run `sql/verification/reconcile_shared_daily.sql`: exact-match dates should jump from 8 to
  near the full common range; 2013/2018 `diff_vs_nyc` should approach 0; 2015 should no longer be
  short ~1.76M.
- Confirm no `member_casual` value outside `{member, casual, unknown}` remains in the daily
  table.

## Remaining unresolved questions

- **Why** 2013 & 2018 (specifically) got both a full-month file and chunk files, while
  2015/2019 did not — i.e. the exact extraction/split step that produced the extra objects
  (the ingestion/extraction scripts were never committed; this is the PR-D recovery target).
- Whether a handful of the 123 missing 2015 days beyond Jan/Feb/Mar/Jun come from scattered
  unparseable rows in otherwise-good months (minor; not separately quantified).
- Whether the residual daily jitter in 2019–2026 is fully explained by the timezone shift alone
  (PR #4 hypothesis) — separable only after the parser/timezone fix and a rebuild.

No BigQuery object was created, modified, or rematerialized; no GCS object was changed; no
credentials or secrets appear in this document.
