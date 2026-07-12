# Official-Source Freshness Audit — 2018-04, 2022, 2023, 2024-05

**Date:** 2026-07-12 · **Tool:** `scripts/audit_official_source_freshness.py` · **Evidence:** `evidence/official-source-comparison.csv`, `evidence/official-source-row-counts.csv`

**Question (from PR #7):** are the remaining `_v2` discrepancies caused by outdated/incomplete staged source files, or by defects in the course reference?

**Answer: the course reference.** The staged sources are byte-identical to the *current* official archives, and per-month official row counts equal the project's `trips_daily_table_v2` exactly. Independent NYC DOT usage reports corroborate the project's totals to within 0.05%. **No restaging is required.**

## Part A — official archive vs stored source

The official bucket (`https://s3.amazonaws.com/tripdata/`, 172 objects enumerated on 2026-07-12) covers the target periods with **annual bundles** for 2018/2022/2023 and a **monthly zip** for 2024-05. No standalone monthly NYC objects exist any more for 2018/2022/2023 (the old per-month `.csv.zip` files have been replaced by the annual re-publications); all `JC-*` objects are Jersey City and out of scope.

| Official object | Size | Last modified | Stored copy (`gs://bigdataday1/raw/`) | MD5 match |
|---|---|---|---|---|
| `2018-citibike-tripdata.zip` | 1,337,685,504 | 2024-02-22 | `raw/2018-citibike-tripdata.zip` (staged 2026-06-10) | **TRUE** |
| `2022-citibike-tripdata.zip` | 1,231,367,136 | 2024-07-31 | `raw/2022-citibike-tripdata.zip` (staged 2026-06-10) | **TRUE** |
| `2023-citibike-tripdata.zip` | 1,602,415,356 | 2025-07-03 | `raw/2023-citibike-tripdata.zip` (staged 2026-06-10) | **TRUE** |
| `202405-citibike-tripdata.zip` | 809,097,529 | 2025-07-03 | `raw/202405-citibike-tripdata.zip` (staged 2026-06-10) | **TRUE** |

MD5s were computed over the freshly downloaded official bytes and compared to the GCS-stored MD5s from `evidence/gcs-source-inventory.csv` (full name/size/ETag/generation/CRC32C detail in `official-source-comparison.csv`). Classification per the audit rubric: **same object and same bytes** in all four cases; every official object's last-modified predates the 2026-06-10 staging, so nothing was re-published after staging, and **no covering official object post-dates the project's copies**. The "official source changed after staging" hypothesis is **refuted**.

## Part B — official row counts (headers excluded)

Archives were downloaded to temporary session storage, zip member paths validated (no absolute paths or traversal), nested zips walked in memory, and every contained CSV streamed: header rows detected and **excluded** from all counts; rows assigned to months by the `started_at`/`starttime` value (`YYYY-MM` prefix); min/max timestamps and rider labels recorded per file (263 file×month rows in `official-source-row-counts.csv`). Downloads were deleted afterwards.

**Packaging quirk found in `2018-citibike-tripdata.zip`:** every month appears in *multiple redundant representations* — a top-level full-month CSV, top-level `_1`/`_2` chunks, and a `N_Month/` folder with the same chunks (April: 1,307,543 + 1,000,000 + 307,543 + 1,000,000 + 307,543 = 3,922,629 raw rows ≈ 3 × 1,307,543). Counting each month **once** (canonical full-month file):

| Month | Official (deduped) | Project `_v2` | Course reference | Ref vs official |
|---|---|---|---|---|
| **2018-04** | **1,307,543** | **1,307,543 (+0)** | 2,615,086 | **+100.000% (exactly 2×)** |
| 2022-01…2022-12 | 29,838,442 | 29,838,442 — **all 12 months +0** | 30,689,921 | +2.57% … +3.62% monthly |
| 2023-01…2023-11 | (see CSV) | **all 11 months +0** | — | +2.52% … +3.82% monthly |
| 2023-12 | 2,204,460 | 2,204,870 (+410)¹ | 2,274,075 | +3.16% |
| 2023 total | 35,106,710 | 35,107,120¹ | 36,227,010 | +3.19% |
| 2024-05 | 4,133,708 | 4,135,049 (+1,341)¹ | 4,231,701 | +2.37% |

¹ The only non-zero project−official differences (+410 and +1,341) are month-boundary rows: trips that started in 2023-12 / 2024-05 but are packaged in the *adjacent* archives (`202401-…`, `202404/202406-…`), which the project staged but this audit did not download. Symmetrically, the audited archives contained stray rows from neighboring months (visible in the per-file month assignments), confirming packaging is by publication month, not strictly by start month.

Rider labels in the official files normalize cleanly (April 2018: 1,158,232 subscriber/member + 149,311 customer/casual, 0 blank), consistent with the project's normalization.

## Part C — independent operator/DOT-published counts

The sandbox's network policy blocks `citibikenyc.com`, `nyc.gov`, and `ibo.nyc.gov` directly, so the monthly operating-report PDFs could not be opened here; figures below come from web-search result content citing those documents and should be re-verified against the PDFs when network access allows. **Limitation noted.** Definitions also differ slightly: published "rides/trips" totals are system-wide operator counts and may not exactly match the trip-file convention (≥60s, non-staff trips); they are used as corroboration, not ground truth.

| Period | Published figure | Source (as cited in search results) | Project | Reference |
|---|---|---|---|---|
| 2022 (quarterly sum) | Q1 4,067,433 + Q2 8,470,632 + Q3 10,385,954 + Q4 6,914,292 = **29,838,311** | NYC DOT Bike Share Usage Data Report ([nyc.gov](https://www.nyc.gov/html/dot/downloads/pdf/bike-share-usage-data-report-q2-2025.pdf)) | 29,838,442 (**+0.0004%**) | 30,689,921 (+2.85%) |
| 2023 (annual) | **35,088,551** | NYC DOT Bike Share Usage Data Report ([nyc.gov](https://www.nyc.gov/html/dot/downloads/pdf/bike-share-usage-data-report-q2-2025.pdf)) | 35,107,120 (**+0.05%**) | 36,227,010 (+3.24%) |
| 2022 (rounded) | "over 30 million trips" | NYC Comptroller, *Riding Forward* ([comptroller.nyc.gov](https://comptroller.nyc.gov/reports/riding-forward-overhauling-citi-bikes-contract-for-better-more-equitable-service/)) | consistent | consistent |
| 2023 (partial) | 30.7M rides by 2023-10-29 | NYC Mayor's Office ([nyc.gov](https://www.nyc.gov/mayors-office/news/2023/11/mayor-adams-dot-commissioner-rodriguez-lyft-expansion-improvements-citi-bike-system)) | consistent with ~35.1M | strains against 36.2M |
| April 2018 | monthly operating report not retrievable through the sandbox proxy | [citibikenyc.com/system-data/operating-reports](https://citibikenyc.com/system-data/operating-reports) | 1,307,543 fits the seasonal curve | 2,615,086 does not |

The DOT-published 2022 figure agrees with the project total to **131 trips in ~29.8M**; 2023 to **18,569 in ~35.1M**. Both are ~3% below the course reference.

## Findings

**Confirmed:**
1. The official source **did not change** after the project staged it — all four covering archives are MD5-identical to the stored copies. No changed or missing source objects exist.
2. **April 2018:** the official archive contains 1,307,543 April trips per representation; the project matches exactly (+0). The reference's 2,615,086 is exactly a double-ingest of the month's redundant packaging (full + chunks). **The project count is correct; the reference is defective for April 2018.**
3. **2022:** official = project **exactly, all 12 months (+0)**; DOT-published total within 0.0004% of project. **Project correct; reference overcounts ~+2.9%.**
4. **2023:** official = project exactly for 11 months; 2023-12 differs by the 410 boundary rows explained above; DOT-published total within 0.05% of project. **Project correct; reference overcounts ~+3.2%.**
5. **May 2024:** official = project to within 1,341 boundary rows (0.03%); reference overcounts +2.37%. **Project correct.**
6. The `_v2` pipeline remains loss-free (established in PR #7): staged CSVs ↔ raw `_v2` ↔ daily table reconcile row-for-row.

**Unresolved hypotheses (not needed for the recommendation):**
- *Why* the reference overcounts 2022–2024: most plausibly it was built from the original per-month publications (since replaced by the cleaned annual re-publications of 2024-07-31 / 2025-07-03) which contained rows later removed by Lyft's dedup/cleanup, and/or it double-ingested redundant representations as it demonstrably did for April 2018. Confirming this would require the retired original monthly files, which no longer exist in the official bucket.
- Whether the published operating-report figures use precisely the trip-file definition (limitation in Part C).

## Months requiring restaging: **none.**

The staged sources are the current official revision, and everywhere the reference and project disagree, the official archive (and DOT publications) side with the project. Restaging would download the same bytes already in `gs://bigdataday1/raw/`.

**Hypothetical repair scope, for completeness (not recommended):** re-staging 2018 + 2022 + 2023 + 2024-05 would mean ~4.98 GB S3 download, ~4.98 GB GCS upload, re-extracting ~25 GB of CSVs, two `WRITE_TRUNCATE` loads (~58 GB free ingestion), one ~32 GiB materialization (≈$0.20), and a reconciliation re-run (<5 MB) — and would reproduce the current tables bit-for-bit.

## Recommendation: **NO-GO on repairing the v2 source — there is nothing to repair.**

The correct next actions are instead:
1. Report to course staff that `nyu-datasets.citibike.m_daily_trips` overcounts April 2018 by exactly 2× and 2022 / 2023 / May 2024 by ~2.4–3.2% relative to the current official archives and NYC DOT-published totals.
2. Treat `trips_daily_table_v2` as the more accurate series for those periods, and re-evaluate PR #7's conditional NO-GO on dashboard cutover in that light (criterion F's "unexplained" differences are now explained as reference-side; a follow-up decision PR can formalize cutover).

No GCS, BigQuery, pipeline, dashboard, `CLAUDE.md`, or authentication change was made by this audit; downloaded archives were deleted after counting.
