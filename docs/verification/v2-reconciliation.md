# `trips_daily_table_v2` — Independent Reconciliation Against the Course Reference

**Date:** 2026-07-12 (immediately after the `_v2` build; see `docs/execution/v2-build.md`)
**Verdict summary:** the three defects the `_v2` pipeline set out to fix — 2013/2018 duplicate-file doubling, the early-2015 timestamp-parse gap, and legacy rider-type labels — are **all fixed and verified**. Two findings remain: a **reference-side April-2018 double-count** (the project table is the correct one) and a **~3% shortfall in 2022–2023 that lives in the staged GCS source files**, not in the pipeline.

## Tables and ranges

| Side | Table | Rows | Date range |
|---|---|---|---|
| Project | `msbai-dwd-jrs10127.citibike.trips_daily_table_v2` | 9,654 | 2013-06-01 → 2026-05-31 |
| Reference | `nyu-datasets.citibike.m_daily_trips` | 4,738 | 2013-06-01 → 2026-05-31 |

Common range: **2013-06-01 → 2026-05-31, 4,738 dates — a 100% date join in both directions** (0 dates missing from either source; the pre-repair pipeline was missing ~118 early-2015 dates).

Reference columns used (verified against the live schema): `num_nyc_trips` (primary target), `num_member_trips_nyc`, `num_casual_trips_nyc`, and `num_trips` (JC-inclusive, alignment test only). Project totals are `SUM(trip_count)` over all rider types (member + casual + unknown), with member/casual/unknown also compared separately.

Only the two small daily tables were queried (the raw `_v2` tables, `trips_v2`, `trips_daily_v2`, and all original objects were never scanned). **Total bytes processed across all verification queries: 4,632,046 bytes (≈4.4 MiB, ≈$0.00).** Per-query bytes:

| Query | Bytes |
|---|---|
| profile §1 basic / §2 by-rider / §3 unknown share / §4 unknown by month | 202,912 / 231,874 / 154,642 / 231,874 |
| profile §5 dup keys / §6 bad counts / §7 missing dates / §8 monthly / §9 yearly / §10 legacy labels | 202,912 / 0 (cache) / 115,136 / 154,464 / 154,464 / 77,410 |
| reconcile §1 daily join / §2 era stats / §3 member-casual / §4 yearly | 421,394 / 230,272 / 345,586 / 268,176 |
| reconcile §5 monthly / §6 top-25 / §7 missing dates / §8 2015 months | 230,272 / 230,272 / 115,136 / 230,272 |
| follow-ups: months >0.5% / ref Apr-2018 context / 2018-ex-April / 2022-23 rider split / zero-loss | 230,272 / 151,616 / 230,272 / 345,586 / 77,232 |

## Headline statistics (project total vs reference `num_nyc_trips`)

| Era | Dates | Exact match | Mean signed diff | MAE | Median AD | MAPE | Extremes (+/−) |
|---|---|---|---|---|---|---|---|
| **2013** | 214 | **100.00%** | 0.0 | 0.0 | 0 | **0.000%** | 0 / 0 |
| **2015** | 365 | **100.00%** | 0.0 | 0.0 | 0 | **0.000%** | 0 / 0 |
| **2018** | 365 | 91.78% | −3,582.3 | 3,582.3 | 0 | 4.110% | 0 / −66,077 |
| 2013–2020 | 2,763 | 79.62% | −452.8 | 493.7 | 0 | 0.582% | +962 / −66,077 |
| 2021–2023 | 1,094 | 27.15% | −1,799.0 | 1,805.0 | 1,820 | 2.002% | +583 / −7,307 |
| 2024–2026 | 881 | 96.25% | −109.4 | 110.0 | 0 | 0.080% | +249 / −4,907 |
| **Full range** | **4,738** | **70.60%** | **−699.8** | **725.1** | **0** | **0.817%** | +962 / −66,077 |

Member/casual (full range, vs `num_member_trips_nyc` / `num_casual_trips_nyc`): member 72.88% exact, MAE 654.5, MAPE 0.886%; casual 71.70% exact, MAE 92.0, MAPE 0.663%.

Pre-repair baseline (PR #4): 8 exact-match days out of 4,620 (0.17%), mean signed diff +4,285, recent-year daily MAD ≈1,700. Post-repair: 3,345 exact days (70.6%), and 2024–2026 at 96.25% exact with MAE 110. **The New-York-local timestamp repair worked** — day attribution now matches the reference almost everywhere the underlying data agrees.

## Explicit tests

1. **Is 2013 still doubled? NO — fixed.** Annual ratio **1.0000** (5,614,888 vs 5,614,888), every day an exact match. (Pre-repair: 2.00×.)
2. **Is 2018 still doubled? NO — the doubling is fixed**, but the annual ratio is **0.9307** for a different reason (see finding R1: the *reference* double-counts April 2018). **Excluding April, 2018 matches the reference exactly: 16,240,796 vs 16,240,796, diff = 0.**
3. **Are Jan/Feb/Mar/Jun 2015 represented? YES — fully.** All 120 days present; each month exact: 2015-01 285,552; 2015-02 196,930; 2015-03 341,826; 2015-06 941,219 — ratio 1.0000 each. The 2015 shortfall is **eliminated** (annual 2015: 100% exact-match days).
4. **Did timezone handling improve matching? YES.** Exact-match days went from 0.17% to 70.6% overall (96.25% in 2024–2026); recent-year MAE fell from ≈1,700 to 110.
5. **Closer to reference NYC than to the JC-inclusive total? YES.** `ratio_to_nyc` is closer to 1 than `ratio_to_grand` in every year with JC data (2015+); 2013–2014 have no JC volume (the two reference columns are equal, so the comparison is a tie).
6. **Annual differences > 2%?** Three: 2018 −6.93% (explained — reference defect, R1), 2022 −2.77% and 2023 −3.09% (diagnosed to staged sources, R2).
7. **Monthly differences > 5%?** Exactly one: **2018-04 at −50.000%** (investigated and explained, R1). Next largest monthly deviations are 2023-04 −3.68% and the 2022–2023 block (R2); 2024-05 −2.28% is the only other month beyond ±2%.

## Findings

### R1 — April 2018: the *reference* is double-counted; the project table is correct. CONFIRMED

- Every April 2018 day has ratio **exactly 0.500** (e.g. 2018-04-26: project 66,077 vs reference 132,154); the month totals 1,307,543 vs 2,615,086 — reference is exactly 2.000× project.
- **All other 11 months of 2018 match the reference exactly (year-ex-April diff = 0).**
- Reference April 2018 (2,615,086) is a violent seasonal outlier in the reference itself: Mar 2018 976,672, May 2018 1,824,710, Apr 2017 1,315,404, Apr 2019 1,766,094. The project's 1,307,543 fits the seasonal curve; 2.6M does not.
- The staged April 2018 full-month file is 248 MB; at the ~180 B/row typical of neighboring months it can hold ≈1.3–1.4M rows — it cannot contain 2.6M trips.
- Arithmetic closure with PR #4/#5: the old pipeline (which double-loaded all 2018 months) measured 1.86× the reference annually — exactly what a truly-doubled project (2×) compared against a reference that is itself doubled in one month (18.86M rather than the true 17.55M) produces.

Consequence: acceptance criterion E fails *as written* against this reference, but the discrepancy is a reference-side defect. Measured against a corrected reference (year-ex-April), 2018 ratio = 1.0000.

### R2 — 2022–2023 (~3%) and 2024-05 (~2.3%) shortfall lives in the staged GCS sources. CONFIRMED shortfall; root cause UNRESOLVED

- Every month of 2022 (−2.50% to −3.49%) and 2023 (−2.46% to −3.68%) runs low; 2024-05 is −2.28%. Surrounding years are clean: 2021 +0.012%, 2024 −0.217% overall, 2025 and 2026 exact.
- **Zero-loss proof:** the two raw loads output 91,944,421 + 216,249,376 = 308,193,797 rows, and `trips_daily_table_v2` totals exactly **308,193,797** trips — 0 rows were dropped anywhere between GCS and the daily table (every timestamp in all 308.2M rows parsed). The missing ~1.97M trips of 2022–2023 are therefore **absent from the staged CSV files themselves**, not lost by the pipeline.
- The shortfall hits members (−3.07% / −3.44%) more than casuals (−1.70% / −1.55%), so it is a data gap, not a labeling issue.
- Unresolved hypothesis (out of scope for this read-only PR): the `staging/post2021` copies of the 2022–2023 (and 2024-05) monthly zips are incomplete relative to the revision the course reference was built from (Lyft has re-published historical months). Fix path: re-stage those months from the archive, re-run the manifest builder, rebuild `_v2`, re-run this reconciliation.

### R3 — Rider-type normalization worked; `unknown` is immaterial. CONFIRMED

- `Customer`/`Subscriber` rows: **0**. Distinct rider types: `casual`, `member`, `unknown` only.
- `unknown` totals **51,780 trips = 0.0168%** of 308.2M, confined exactly to the six legacy-header months routed from the post2021 folder (2016-10: 17,949; 2016-11: 12,534; 2016-12: 5,388; 2017-01: 3,193; 2017-02: 7,580; 2017-03: 5,136). These are rows whose `usertype` field was genuinely blank in the source. Judged immaterial.

### R4 — Structural integrity. CONFIRMED

Zero duplicate `(date, region, rider_type)` keys; zero null/zero/negative `trip_count`; zero missing dates against the reference in either direction; single region `NYC`.

### Minor notes (immaterial, documented for completeness)

- 2019 is +531 trips (+0.003%): the `202001` source file contains 531 trips that started on late-Dec-2019 New-York-local dates; they correctly attribute to 2019.
- 2020 is +0.287% and 2021 +0.012% — within tolerance, consistent with small source-revision differences.

## Acceptance criteria

| # | Criterion | Result |
|---|---|---|
| A | Zero duplicate date/region/rider_type keys | **PASS** (0) |
| B | Zero Customer/Subscriber rider types | **PASS** (0) |
| C | No missing reference dates from the 2015 parsing defect | **PASS** (0 missing dates anywhere) |
| D | 2013 ratio within 0.98–1.02 | **PASS** (1.0000, 100% exact days) |
| E | 2018 ratio within 0.98–1.02 | **FAIL as written** (0.9307) — fully attributed to the reference's April-2018 double-count (R1); ex-April ratio is exactly 1.0000 |
| F | No unexplained annual difference > 2% | **PARTIAL** — 2018 explained (R1); 2022 −2.77% / 2023 −3.09% diagnosed to staged sources (R2) but root cause not yet remediated |
| G | Monthly differences > 5% investigated and explained | **PASS** — only 2018-04 (−50.000%), explained by R1 |
| H | Unknown rider-type volume quantified and judged | **PASS** — 51,780 trips (0.0168%), immaterial (R3) |

## Recommendation: **NO-GO** for dashboard cutover (conditional)

The `_v2` pipeline logic is **validated**: it is loss-free and duplication-free end-to-end, and it reproduces the reference exactly wherever the staged data is complete (11 of 14 years match within ±0.3%, three of them perfectly). But cutting the dashboard over now would understate 2022–2023 by ~3% (≈1.97M trips) and April-2018 comparisons against the course reference would be confusing without the R1 caveat.

Conditions to reach GO:

1. Re-stage the 2022-01 → 2023-12 and 2024-05 source months from the Citibike archive, rebuild the manifest and the `_v2` objects, and re-run this reconciliation (expect criterion F to pass).
2. Report the April-2018 reference anomaly (R1) to the course staff; either the reference is corrected or the dashboard documents the known divergence.

No dashboard, Cloud Run, BigQuery, or GCS change was made in this PR; per instruction, cutover is deferred regardless of recommendation.
