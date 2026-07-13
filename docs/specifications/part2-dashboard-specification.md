# Part 2 — Dashboard Specification (Citi Bike NYC + Weather)

Consolidated specification for the Streamlit dashboard served on Cloud Run
(`app.py` + `query.py`). This is the single Part-2 spec; detailed verification
lives under `docs/verification/`.

## Purpose
Let a non-technical reader see **how New York City Citi Bike ridership moves with
the weather and the calendar**, using the independently verified v2 daily
series, and see which days ran unusually high or low versus a simple
weather/calendar expectation.

## Intended audience
Non-technical: a course reviewer, a city/transport-curious reader, or an
operations stakeholder. No SQL or code literacy assumed — every chart states its
conclusion in one plain-English sentence.

## Business questions answered
1. How much does ridership rise in warm weather and fall in cold/rain/snow?
2. Do members and casual riders behave differently across the week?
3. Which specific days had far more or far fewer rides than weather and season
   alone would predict (i.e., days worth investigating)?
4. What is the overall volume and the member/casual/unknown split over a chosen
   period?

## Source tables
| Role | Table |
|---|---|
| Trips (default, verified) | `msbai-dwd-jrs10127.citibike.trips_daily_table_v2` |
| Trips (fallback) | `nyu-datasets.citibike.m_daily_trips` (`CITIBIKE_SOURCE_MODE=reference`) |
| Weather | `nyu-datasets.weather.m_weather_daily_nyc` |
| Model | `msbai-dwd-jrs10127.citibike.trips_daily_model` (v1 today) → `…trips_daily_model_v2` (after Stretch 1) |

## Date coverage
Trips 2013-06-01 → 2026-05-31; weather ends 2026-05-29, so the inner
trips⋈weather join drops the final two trip dates (≈320k trips). Model window
2022-01-01 onward.

## Metrics and dimensions
- **Metrics:** daily trip counts (total, member, casual, unknown), average trip
  duration (min) and Haversine distance (km, straight-line — disclosed), average
  temperature.
- **Dimensions:** date, rider type, day-of-week, temperature bucket, weather
  condition (clear/rain/snow), region (NYC only).

## Filters and controls
- **Rider type** radio: member / casual / both (default both).
- **Date range** slider: 2013-06-01 … 2026-05-31 (default 2022-01-01…2024-12-31).
Changing rider type re-slices cached data (no re-query); changing the date range
issues one cached query per range.

## Rider-type treatment
`member`, `casual`, `unknown` (subscriber→member, customer→casual, blank→unknown).
**Total includes unknown**; the member and casual series never absorb unknown.
Unknown is ≈0.017% of all trips (Oct 2016–Mar 2017 only), 0 in the 2022+ model
window.

## Charts — each requires a visible one-sentence finding (direction + magnitude)
| # | Chart | Required finding (data-derived) |
|---|---|---|
| KPIs | Total / avg-per-day / avg temp / days | — (headline numbers) |
| 1 | Daily trips + temperature | warm-quarter vs cold-quarter average ridership (× difference) |
| 2 | Trips vs temperature (bucketed, lowess) | temperature of peak ridership and the size of the peak |
| 3 | Avg trips by day-of-week | weekday↔weekend gap, per rider type, as a % |
| 4 | Weather impact (clear/rain/snow) | % drop on rainy and snowy days vs clear |
| 5 | "Is it us or the weather?" (actual vs expected) | share of days outside the expected range and the largest gap |

A finding must state **what happens and roughly how much** (e.g., "casual riders
ride ~39% more on weekends"), never a generic "ridership varies with weather."

## Caching behavior
- `@st.cache_resource` for the BigQuery client (one per process).
- `@st.cache_data(ttl=3600)` for the daily trips⋈weather read and the model
  read, keyed by (source mode / model kind, start, end).
- Rider-type switching reuses the cached wide frame; only a new date range
  triggers a new (then-cached) query.

## Model section
- **Purpose:** show actual daily ridership against a simple, interpretable
  weather+calendar **expectation**, with an expected range, and flag days that
  fall outside it as *worth investigating*.
- **v2 model (Stretch 1):** `trips_daily_model_v2` — log-space OLS on
  temperature (+quadratic), precipitation, snow, day-of-week, month; total /
  member / casual series; ~95% prediction band; objective gap flag. See
  `docs/verification/weather-model-v2.md`.
- **Limitations:** descriptive, not causal — a flagged day does **not** prove a
  shortage, outage, event, or promotion. Holiday effects, special events, and
  multi-year growth beyond the window are not modeled. The current live model is
  the pre-v2 v1 table (reference-era actuals ~3% above v2) until MODEL_TABLE is
  repointed.

## Public deployment expectation
Public, unauthenticated Cloud Run service (`citibike-app`, us-central1) at
https://citibike-app-kpkbtfmmcq-uc.a.run.app. A visible source caption names the
active trip table and a data-quality note states the unknown-rider share and the
known course-reference discrepancies. See `docs/specifications/acceptance-criteria.md`.

## Graceful failure behavior
- **Invalid `CITIBIKE_SOURCE_MODE`:** `query.get_config()` raises; the app shows
  a visible "Configuration error" and stops — it never silently picks a source.
- **Empty result for the chosen filters:** a visible warning ("No data for
  selected filters"), no blank charts.
- **Model table missing or schema-incompatible:** `detect_model_kind()` raises
  and the model section shows a clear `st.error` naming the problem — it never
  renders stale or mismatched model data. A v1 table shows the pre-v2 caveat; a
  v2 table removes it.
- **Model window:** requests before 2022-01-01 are clamped to the model window
  with an informational note rather than an error.
- **Weather coverage tail:** the trips⋈weather inner join drops the final two
  trip dates (weather ends 2026-05-29); disclosed, not silently mis-summed.
- **BigQuery/auth failure:** surfaces as a Streamlit exception on the affected
  section rather than a wrong number.
