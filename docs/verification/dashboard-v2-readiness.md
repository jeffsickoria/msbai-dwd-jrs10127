# Dashboard v2 Readiness — Validation Record

**Date:** 2026-07-12 · **Scope:** read-only validation of the `app.py`/`query.py` cutover to `trips_daily_table_v2` (PR #9). No deployment, no image build, no Cloud Run/BigQuery/GCS modification.

## What changed in the code

- `query.py` now owns all configuration: `GCP_PROJECT`, `CITIBIKE_SOURCE_MODE` (`v2` default / `reference` fallback / anything else raises `ValueError`), `CITIBIKE_V2_TABLE`, `CITIBIKE_REFERENCE_TABLE`, `WEATHER_TABLE`, `MODEL_TABLE`.
- In `v2` mode the long-format table is pivoted to the wide daily shape: `num_nyc_trips` (= member + casual + **unknown**), `num_member_trips_nyc`, `num_casual_trips_nyc`, `num_unknown_trips_nyc`, plus trip-weighted `avg_duration_minutes` / `avg_distance_km`. In `reference` mode the course table passes through with NULL unknown/duration/distance columns.
- `app.py` runs **one cached daily query per (mode, date-range)** instead of one per rider type, slices member/casual series from the cached frame (unknown is never folded into either), shows a source caption, and shows a data-quality note in v2 mode. Layout, charts, controls, and the model section are otherwise unchanged.

## Query validation

**Dry runs (all variants valid):** v2 `trips_daily` 386,338 B · v2 `trips_weather` 3,326,432 B · reference `trips_daily` 151,616 B · reference `trips_weather` 3,091,710 B · model query 64,360 B.

**v2 mode, executed full range (2013-06-01 → 2026-05-31):**
- 4,736 rows, **no duplicate dates**; range 2013-06-01 → **2026-05-29**.
- `member + casual + unknown = num_nyc_trips` on **every** date (0 violations).
- Totals include unknown: 307,873,291 trips over the joined range, unknown = 51,780 (0.0168%). (Full table total is 308,193,797; see weather-join note below.)
- **Weather join does not multiply rows** (4,736 joined ≤ 4,738 trip dates). It *drops* 2026-05-30/31 (≈320,506 trips) because `m_weather_daily_nyc` currently ends 2026-05-29 — pre-existing inner-join behavior, identical in the previous app version.
- **Sample dates match the verified v2 table exactly**: 2013-06-01 (8,722), 2018-04-15 (20,440), 2022-07-04 (94,692), 2024-05-15 (90,829), 2026-05-29 (191,759).

**reference mode, executed:** fallback works; columns map correctly (`num_nyc_trips`, `num_member_trips_nyc`, `num_casual_trips_nyc` pass through; `num_unknown_trips_nyc`/duration/distance are NULL as designed). Spot row 2024-01-01: 47,278 total / 36,000 member / 11,278 casual — and v2 returns the same member value for that date.

**Invalid mode:** `CITIBIKE_SOURCE_MODE=bogus` raises `ValueError` in `query.get_config()`; in the app it renders a visible "Configuration error" and stops before any chart — no silent source choice.

## Performance

| Measurement | Result |
|---|---|
| Default dashboard query (2022-01-01→2024-12-31, v2, executed) | 1,096 rows, **20,971,520 bytes billed (20 MB minimum billing), 1.02 s** |
| Full-range v2 query | 4,736 rows, 20,971,520 bytes billed, 1.41 s |
| Reference-mode query | 20,971,520 bytes billed, 0.84 s |
| Local Streamlit startup → `/_stcore/health` = `ok` | **1.03 s**, app page HTTP 200, no errors logged |
| Full app execution (Streamlit AppTest, v2) | 5.2 s cold incl. 2 BigQuery queries; **zero errors/exceptions**; all 7 metrics render |
| Full app execution (AppTest, reference) | 4.7 s; zero errors; quality note correctly suppressed |

**Caching:** `@st.cache_resource` (client) and `@st.cache_data(ttl=3600)` (daily + model queries) preserved; the daily cache key now includes the source mode. Rider-type switching no longer re-queries at all (it re-slices the cached wide frame). An in-process AppTest warm-re-run segfaulted in the plotly/pandas native layer (test-harness artifact; each fresh process runs cleanly, as does the real server), so warm-vs-cold timing was not captured numerically.

## Local checks

- `python3 -m py_compile app.py query.py` — clean.
- Import checks (`streamlit 1.59.1`, `plotly`, `pandas`, `statsmodels`, `google-cloud-bigquery`) — clean; `requirements.txt` unchanged and sufficient.
- `query.daily_rides_with_temp()` public API works in both modes ("member"/"casual"/"all"; "all" includes unknown).
- No pre-existing test suite exists in the repo; the AppTest runs above serve as the functional test.

## Chart-by-chart compatibility review

| Chart | Claim/caption | Still supported? |
|---|---|---|
| KPIs | "Total trips" | ✅ Now the true NYC total (includes unknown) in "both" mode; per-series totals when a single rider type is selected. |
| 1 — Daily trips & temperature | member/casual lines + temp | ✅ Same series, same semantics; values now verified v2. |
| 2 — Trips vs temperature | avg daily trips per 5°F bucket | ✅ Unchanged computation on the same columns. |
| 3 — Avg trips by day of week | ✅ Unchanged. |
| 4 — Weather impact (Clear/Rain/Snow) | ✅ Unchanged. |
| 5 — "Is it us or the weather?" model | actual vs expected, ±15% outlier days | ⚠️ Supported with a caveat: `trips_daily_model` was fitted on the pre-v2 series, so its "actual" curve for 2022+ runs ~3% above the verified v2 counts. Calculations untouched (per instruction); the caption now notes the caveat. Refit is future work. |
| New source caption + quality note | v2 verification, unknown ≈0.017%, reference discrepancies | ✅ Verified rendered in v2 mode, suppressed in reference mode. |

## Verdict

All Part D checks pass. The code cutover is safe to merge; deployment (image build + Cloud Run) remains a separate approval per `docs/verification/v2-cutover-decision.md`.
