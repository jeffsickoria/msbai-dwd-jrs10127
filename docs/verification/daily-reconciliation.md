# Daily-Data Reconciliation — `trips_daily_table` vs course reference

**Date:** 2026-07-12 · **Mode:** read-only (no BigQuery object created, modified, or
rematerialized; no raw/`trips`/`trips_daily` scans). All executed queries ran only against
the small daily/model tables plus the shared reference and weather tables.

## Tables examined

| Table | Rows | Date range | Role |
|---|---|---|---|
| `msbai-dwd-jrs10127.citibike.trips_daily_table` | 9,439 | 2013-05-31 → 2026-05-31 | project daily summary under test |
| `msbai-dwd-jrs10127.citibike.trips_daily_model` | 1,609 | 2022-01-01 → 2026-05-29 | project model output |
| `nyu-datasets.citibike.m_daily_trips` | 4,738 | 2013-06-01 → 2026-05-31 | **authoritative reference** |
| `nyu-datasets.weather.m_weather_daily_nyc` | 54,912 | (multi-year) | weather coverage check |

Reference schema (inspected, not assumed) separates NYC from Jersey City:
`num_nyc_trips`, `num_member_trips_nyc`, `num_casual_trips_nyc`, `num_jc_trips`,
`num_trips` (grand total incl. JC), plus rideable/duration/distance columns.

## Cost

23 executed queries, **total ≈ 3.79 MB processed** (3,973,632 bytes) — all against small
tables. Per-query bytes are listed in `sql/verification/*.sql` block order; the largest single
query was the weather-coverage join (452 KB) and the project↔reference join (417 KB).

Normalization applied **for comparison only** (sources untouched):
`Subscriber, member → member`; `Customer, casual → casual`; `unknown` preserved.

---

## 1. Profile of `trips_daily_table` (`sql/verification/profile_daily_table.sql`)

- **Range/shape:** 9,439 rows, 2013-05-31 → 2026-05-31, **1 region** (`NYC` only),
  **5 rider types**: `member`, `casual`, `Customer`, `Subscriber`, `unknown`.
- **Duplicates:** none — no repeated `(date, region, rider_type)`.
- **Null/negative/zero trip counts:** none (0 / 0 / 0).
- **Missing dates:** calendar span 4,749 days; 4,626 present; **123 missing days** — the whole
  of January 2015 onward is the largest gap (project is missing early-2015 dates that exist in
  the reference).
- **Totals by rider type:**

  | rider_type | rows | total trips | first | last |
  |---|---|---|---|---|
  | member | 4,445 | 266,697,492 | 2013-05-31 | 2026-05-31 |
  | casual | 4,444 | 57,065,011 | 2013-05-31 | 2026-05-31 |
  | Subscriber | 185 | 5,412,695 | 2016-09-30 | 2017-04-03 |
  | Customer | 186 | 364,519 | 2016-09-30 | 2017-04-06 |
  | unknown | 179 | 51,780 | 2016-09-30 | 2017-03-31 |

- **Legacy vs normalized coexistence:** legacy `Subscriber`/`Customer`/`unknown` values occur
  **only in 2016–2017**; every other year is purely `member`/`casual`. Importantly, 2016 and
  2017 *totals* still match the reference (below), so the mixed labels there are a **labeling**
  inconsistency, not extra counts.

## 2. Reconciliation vs `m_daily_trips` (`sql/verification/reconcile_shared_daily.sql`)

- **Common range:** 2013-06-01 → 2026-05-31, **4,620 dates compared**.
- **Exact-match dates (NYC total):** **8 / 4,620**. Member exact: 4; casual exact: 33.
- **Overall NYC-total discrepancy:** mean abs diff **5,750**, median abs diff **547**,
  guarded MAPE **13.30%**, mean *signed* diff **+4,285** (project runs high on average),
  largest positive **+81,005**, largest negative **−37,624**.
- **By era:**

  | era | dates | exact | mean abs diff | MAPE | mean signed |
  |---|---|---|---|---|---|
  | 2013–2020 | 2,645 | 8 | 8,558 | 21.53% | **+8,265** |
  | 2021–2023 | 1,094 | 0 | 2,226 | 2.76% | −1,794 |
  | 2024–2026 | 881 | 0 | 1,694 | 1.65% | −118 |

- **Member/casual:** member mean abs diff **4,951** (4 exact), casual **843** (33 exact) — the
  member series carries most of the error.
- **Monthly:** 154 months, 0 exact, monthly MAD 165,052, monthly MAPE 13.53%.
- **Yearly + JC test (the key discriminator):**

  | year | proj_total | ref_nyc | ref_jc | ref_grand | diff vs NYC | diff vs grand |
  |---|---|---|---|---|---|---|
  | 2013 | 11,230,461 | 5,614,888 | 0 | 5,614,888 | **+5,615,573 (≈2.00×)** | +5,615,573 |
  | 2014 | 8,080,531 | 8,081,216 | 0 | 8,081,216 | −685 | −685 |
  | 2015 | 8,173,715 | 9,937,969 | 52,883 | 9,990,852 | −1,764,254 | −1,817,137 |
  | 2016 | 13,845,626 | 13,845,655 | 247,584 | 14,093,239 | −29 | −247,613 |
  | 2017 | 16,364,395 | 16,364,657 | 294,928 | 16,659,585 | −262 | −295,190 |
  | 2018 | 35,096,691 | 18,855,882 | 353,892 | 19,209,774 | **+16,240,809 (≈1.86×)** | +15,886,917 |
  | 2019 | 20,553,266 | 20,551,697 | 404,947 | 20,956,644 | +1,569 | −403,378 |
  | 2020 | 19,562,670 | 19,506,857 | 336,802 | 19,843,659 | +55,813 | −280,989 |
  | 2021 | 27,132,509 | 27,126,485 | 644,443 | 27,770,928 | +6,024 | −638,419 |
  | 2022 | 29,839,834 | 30,689,921 | 895,485 | 31,585,406 | −850,087 | −1,745,572 |
  | 2023 | 35,108,989 | 36,227,010 | 988,851 | 37,215,861 | −1,118,021 | −2,106,872 |
  | 2024 | 44,303,783 | 44,399,405 | 1,052,453 | 45,451,858 | −95,622 | −1,148,075 |
  | 2025 | 45,768,725 | 45,771,161 | 1,002,715 | 46,773,876 | −2,436 | −1,005,151 |
  | 2026 | 14,530,302 | 14,536,571 | 305,829 | 14,842,400 | −6,269 | −312,098 |

- **Top-25 daily discrepancies:** **all 25 fall in 2018**, each with `proj_total ≈ 2.00 ×
  ref_nyc` (e.g. 2018-06-26: 161,656 vs 80,651). This is a clean double-count signature.
- **Dates present in only one source:** 6 only in project (incl. 2013-05-31, which precedes the
  reference; a few 2016–2017 dates); **118 only in the reference** (mostly the Jan-2015 gap).

## 3. Model-table profile (`sql/verification/profile_model_table.sql`)

- **Range/shape:** 1,609 rows, 2022-01-01 → 2026-05-29, all dates distinct; **no nulls**, **no
  duplicate dates**; **0 rows before 2022** (fully within the documented window).
- **`residual = num_nyc_trips − expected_rides`:** holds **exactly for all 1,609 rows**
  (max gap 0).
- **`residual_pct`:** equals `100 × residual / expected_rides` for all 1,609 rows
  (mean gap 0.0025, rounding only); the actual-denominator formula matches only 31 rows — so the
  denominator is **expected_rides**.
- **Error magnitude (from stored values):** MAE **21,437** trips/day; MAPE **27.60%** vs actual,
  **21.89%** vs expected. (High model error, but internally self-consistent.)
- **Weather coverage:** all 1,609 model dates have exactly **one** weather row — clean 1:1 join,
  no missing dates, no weather duplicates over the model window.

---

## Evaluation of previously identified concerns (hypothesis vs confirmed)

| # | Concern | Verdict | Evidence |
|---|---|---|---|
| 1 | Hard-coded `region='NYC'` | **Confirmed (cosmetic)** | Only region value is `NYC`; the label is literal, not derived. |
| 2 | Jersey City contamination | **NOT supported** | Project totals track `num_nyc_trips` (NYC-only) and sit **below** `num_trips` (grand incl. JC) in essentially every year. If JC leaked in, proj would trend toward the grand total; it does not. JC is only ~0.3–1M/yr, far too small to explain the large gaps. |
| 3 | Legacy + normalized rider types coexisting | **Confirmed, isolated** | `Subscriber`/`Customer`/`unknown` appear only 2016–2017; 2016/2017 totals still match the reference, so this is inconsistent labeling, not extra volume. |
| 4 | Local timestamps parsed as UTC → shifted to Eastern | **Supported** | Recent years show near-zero *annual* net diff (2025 −2,436 on 45.8M ≈ 0%) yet daily MAD ≈ 1,700 and essentially no exact-match days — the signature of trips shuffled between adjacent days while yearly totals are preserved. |
| 5 | pre/post raw-table overlap → double counting | **Confirmed for 2013 & 2018** | Both years are ≈2× the reference NYC total (2013 ×2.00, 2018 ×1.86); all top-25 daily discrepancies are 2018 dates at ≈2.00×. Consistent with the same period being loaded from both raw tables (staging shows `post2021` CSVs back to 2016). *Which* months overlap is not proven here (would need raw-table inspection). |
| 6 | No dedup in `UNION ALL` | **Supported (mechanism for #5)** | The `trips` view is a plain `UNION ALL`; with overlapping source months this necessarily double-counts. Confirmed at the aggregate level; row-level proof needs raw data. |
| 7 | Stale materialization | **NOT supported / partly refuted** | Coverage is current through 2026-05-31 (= reference max). The 2016–2017 legacy labels are explained by the current view's post-branch passthrough, not by staleness. |
| 8 | Cannot prune raw tables by date | **Confirmed (from PR #3 dry-runs)** | Unpartitioned raw + STRING-derived date; a filtered `trips_daily` query still estimated ≈37 GB. Not re-tested here (would require scanning the expensive views). |

**Confirmed findings:** double-counting in **2013** and **2018** (~2×); missing early-2015
dates (118 reference dates absent); isolated 2016–2017 label inconsistency; a day-boundary
(timezone) attribution difference vs the reference; the model table is internally consistent.

**Unresolved hypotheses (need raw-data investigation):** the exact overlapping month range
behind the 2013/2018 doubling; whether the timezone shift (vs some other cause) fully accounts
for the residual daily jitter in 2019–2026; whether any JC rows exist at all in the raw tables.

## Answers to the questions posed

- **Is `trips_daily_table` current or stale?** *Current in coverage* (through 2026-05-31) but
  **not correct**: 2013 and 2018 are roughly doubled and early-2015 is missing.
- **Is overlap/double-counting supported?** **Yes, at the aggregate level** for 2013 and 2018
  (≈2× reference, clean per-day 2.00× signature). The precise overlapping months remain a
  hypothesis pending raw inspection.
- **Is the table safe to connect to the dashboard?** **No.** The dashboard already reads the
  course table `nyu-datasets.citibike.m_daily_trips` for its main charts, not this table — which
  is fortunate, because `trips_daily_table` would misreport 2013 and 2018 by ~2× and understate
  early 2015. It should not back the dashboard in its current state.
- **Is the model table internally consistent?** **Yes.** `residual` and `residual_pct` reproduce
  exactly, no nulls/dupes, fully within 2022+, and weather covers every date 1:1. Its ~22–28%
  MAPE is a model-quality matter, not a consistency defect.

## Recommendation

**Rebuild `trips_daily_table` before relying on it — but fix the pipeline first.** In order:

1. **Find and remove the source overlap** driving the 2013/2018 doubling (inspect the month
   ranges in `raw_pre2021` vs `raw_post2021`; the `UNION ALL` should dedup or partition sources
   by non-overlapping date ranges). This is the one defect that must be fixed at the raw/view
   layer, not by rematerializing the same logic.
2. **Fix timestamp timezone handling** in `trips` (parse as Eastern local rather than parsing as
   UTC then shifting) so daily attribution matches the reference.
3. **Recover the missing early-2015 dates** (ingestion gap).
4. Only then **rematerialize** `trips_daily_table` and re-run this reconciliation; expect
   near-exact daily agreement with `num_nyc_trips`.
5. Interim: the dashboard can continue to use the course reference table; do **not** switch it to
   `trips_daily_table` until the rebuild passes reconciliation.

No BigQuery object was created, modified, or rematerialized during this analysis; no
credentials or secrets appear in this document.
