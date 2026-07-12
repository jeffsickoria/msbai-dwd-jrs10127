# Decision Record — `trips_daily_table_v2` Approved as the Dashboard's Primary Source

**Date:** 2026-07-12 · **Status:** GO for **code** cutover (this PR); deployment is a separate, later step.
**Supersedes:** the conditional NO-GO in `docs/verification/v2-reconciliation.md` (PR #7). That document, and the PR #8 audit (`docs/verification/official-source-freshness.md`), are preserved unchanged as the audit trail; this record only changes the *decision*, not the evidence.

## Evidence chain

**PR #7 (`v2-reconciliation.md`)** reconciled `trips_daily_table_v2` against the course reference `nyu-datasets.citibike.m_daily_trips`:
- All three targeted pipeline defects fixed: 2013 doubling (ratio 1.0000), early-2015 parse gap (0 missing dates), rider-label leakage (0 `Customer`/`Subscriber`).
- Loss-free pipeline: 308,193,797 rows loaded = 308,193,797 daily trips.
- Residual disagreements with the reference: April 2018 (project exactly ½ of reference), 2022 (−2.77%), 2023 (−3.09%), May 2024 (−2.3%).
- At that time the residuals were *assumed* to be staged-source gaps → **conditional NO-GO** pending restaging.

**PR #8 (`official-source-freshness.md`)** tested that assumption against the official archive and refuted it:
- All four covering official archives are **MD5-identical** to the project's stored `gs://bigdataday1/raw/` copies; nothing upstream changed after staging.
- Official per-month row counts equal the project **exactly in 24/26 target months (+0 rows)**; the two residuals (+410, +1,341) are month-boundary rows packaged in adjacent archives.
- **April 2018:** the official 2018 annual zip packages every month redundantly (full CSV + duplicate chunk copies). Counted once, April = **1,307,543 = the project's value**; the reference's 2,615,086 is exactly a double-ingest of the duplicate packaging.
- **2022 / 2023 / May 2024:** official counts equal the project; NYC DOT-published totals corroborate (2022: 29,838,311 vs project 29,838,442, +0.0004%; 2023: 35,088,551 vs project 35,107,120, +0.05%). The course reference overcounts these periods by ~2.4–3.2%.
- **DOT evidence limitation (carried forward):** the sandbox proxy blocked the DOT/operator PDFs, so those published figures came from search-result citations of the NYC DOT Bike Share Usage Data Reports and should be re-verified against the PDFs directly when possible. The archive-level byte and row evidence does not depend on them.

## Why the conditional NO-GO is superseded

PR #7's two conditions were: (1) restage 2022-01→2023-12 and 2024-05, rebuild, re-reconcile; (2) handle the April-2018 reference anomaly. PR #8 showed condition (1) is vacuous — restaging would re-download byte-identical files and rebuild identical tables ("**no restaging is needed**") — and resolved (2) by proving the anomaly is a reference-side double-ingest. Every disagreement between the project table and the course reference is now **explained in the project's favor**. Acceptance criteria E and F from PR #7 fail only against a reference now known to be wrong in exactly those places.

## Decision

1. **`trips_daily_table_v2` is approved as the primary trip-data source for the dashboard.** The course reference remains available as an explicit fallback (`CITIBIKE_SOURCE_MODE=reference`), clearly labeled.
2. **GO for code cutover** — this PR changes `app.py`/`query.py` defaults to the v2 table, with validation in `docs/verification/dashboard-v2-readiness.md`.
3. **NOT YET deployment** — the live Cloud Run service (`citibike-app`, https://citibike-app-kpkbtfmmcq-uc.a.run.app) still runs the previous image against the course reference until a separately approved deployment.

## Remaining limitations

- The weather table (`nyu-datasets.weather.m_weather_daily_nyc`) currently ends 2026-05-29, so the dashboard's inner join drops the final two trip dates (2026-05-30/31, ≈320k trips) — pre-existing behavior, unchanged by this cutover.
- `trips_daily_model` was fitted on the pre-v2 daily series; its "actual trips" curve for 2022+ reflects reference-era counts (~3% above v2). Model refit is future work; the chart caption notes this.
- Unknown-rider trips (51,780 = 0.0168%, confined to Oct 2016–Mar 2017) are included in totals and excluded from the member/casual series, by design.
- The DOT figures limitation described above.
- The reference-side defects have not yet been reported to course staff (recommended follow-up).
