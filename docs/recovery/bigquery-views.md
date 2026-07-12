# Recovered BigQuery View Definitions

The SQL files `sql/trips.sql` and `sql/trips_daily.sql` are the **exact current
definitions** of the two BigQuery views, retrieved verbatim from
`INFORMATION_SCHEMA.VIEWS`. They are not reconstructions and were not reformatted.

## Source

| Field | Value |
|---|---|
| Project | `msbai-dwd-jrs10127` |
| Dataset | `citibike` |
| Views | `trips`, `trips_daily` |
| Authoritative source | `msbai-dwd-jrs10127.citibike.INFORMATION_SCHEMA.VIEWS` (`view_definition` column) |
| Recovery date | 2026-07-12 |

Each saved file was byte-compared against the `view_definition` string returned by
`INFORMATION_SCHEMA.VIEWS` and matches **exactly** (files intentionally carry no added
trailing newline so the bytes equal the stored definition).

## Checksums (SHA-256)

| File | SHA-256 |
|---|---|
| `sql/trips.sql` | `f7a4b3f91f8d18686b4f46fd82521616ebfebe060e74aff70a00395e9de95786` |
| `sql/trips_daily.sql` | `5922bfdb434f623a1f6b64a1b968e5aaee31e719438259477f862fc0621e8ced` |

## What each view does

### `trips`
Row-level unified trip view. Reads the two raw ingestion tables (`raw_pre2021`,
`raw_post2021`), maps their two different schemas onto one common set of columns,
parses timestamps, normalizes rider type, converts the start time to US/Eastern, and
computes a straight-line (Haversine) `distance_km`. Output schema:

```
ride_id STRING, rideable_type STRING, started_at STRING, ended_at STRING,
start_station_name STRING, start_station_id STRING, end_station_name STRING,
end_station_id STRING, start_lat FLOAT, start_lng FLOAT, end_lat FLOAT, end_lng FLOAT,
member_casual STRING, started_at_eastern DATETIME, started_at_ts TIMESTAMP,
ended_at_ts TIMESTAMP, distance_km FLOAT
```

### `trips_daily`
Daily aggregate built on top of `trips`. Groups by Eastern-localized date, region, and
rider type; emits trip counts and guarded average duration/distance. Output schema:

```
date DATE, region STRING, rider_type STRING, trip_count INTEGER,
avg_duration_minutes FLOAT, avg_distance_km FLOAT
```

## Dependencies

- `trips` → `msbai-dwd-jrs10127.citibike.raw_pre2021`, `msbai-dwd-jrs10127.citibike.raw_post2021`
- `trips_daily` → `msbai-dwd-jrs10127.citibike.trips` (and transitively the two raw tables)

No other objects are referenced. The materialized `trips_daily_table` and the
`trips_daily_model` table are **not** part of these view definitions.

## Read-only validation results

- **Exact-match:** both files diff-clean against `INFORMATION_SCHEMA.VIEWS`.
- **Dry-run (no execution):**
  - `SELECT * FROM citibike.trips` — valid; est. **≈64.8 GB** processed.
  - `SELECT * FROM citibike.trips_daily` — valid; est. **≈37.3 GB** processed.
  - Representative filtered query `trips_daily WHERE date BETWEEN 2024-01-01 AND 2024-01-31`
    — valid; still est. **≈37.3 GB** (the date filter does **not** prune input; see concerns).
- **Output schemas:** listed above (from table metadata; no data scanned).
- No full-table scan was executed — dry-run and metadata only.

## Logic inspected (§8)

- **Timestamp parsing.** `raw_pre2021` (STRING `starttime`/`stoptime`) is parsed with a
  `COALESCE` over two formats: `'%m/%d/%Y %H:%M:%S'` then `'%Y-%m-%d %H:%M:%E*S'`, using
  `SAFE.PARSE_TIMESTAMP` (unparseable → NULL). `raw_post2021` (`started_at`/`ended_at`)
  uses only `'%Y-%m-%d %H:%M:%E*S'`. Coordinates use `SAFE_CAST(... AS FLOAT64)`.
- **Timezone handling.** The parsed timestamp `_ts` becomes `started_at_ts` (TIMESTAMP),
  and `started_at_eastern = DATETIME(_ts, 'America/New_York')`. `trips_daily` derives the
  reporting day as `DATE(started_at_eastern)` — i.e., the day is defined in US/Eastern.
- **Rider-type normalization.** `raw_pre2021.usertype`: `subscriber→member`,
  `customer→casual`, otherwise `LOWER(TRIM(usertype))`. `raw_post2021.member_casual` is
  passed through unchanged. `trips_daily` then applies
  `COALESCE(NULLIF(TRIM(member_casual),''), 'unknown')`.
- **NYC vs Jersey City.** `region` is a **hard-coded literal `'NYC'`** in `trips_daily`.
  There is **no** geographic filter or JC exclusion in either view — every row is labeled
  `'NYC'` regardless of station location.
- **Distance calculation.** Haversine great-circle distance in km, Earth radius `6371`,
  `π` via `ACOS(-1)`. Returns NULL when any lat/lng is NULL or exactly `0`.
- **Invalid-duration filtering.** In `trips_daily`, `duration_min` is NULL when either
  timestamp is NULL, when `ended-started < 0` s, or when `> 86400` s (24 h); otherwise
  seconds/60. Rows with NULL `started_at_eastern` are dropped (`WHERE started_at_eastern
  IS NOT NULL`). `trip_count = COUNT(*)` counts all surviving rows for the group, including
  those whose duration/distance is NULL; the averages are taken over non-null values only.

## Logic / data-quality concerns discovered

1. **Region is not real.** `region='NYC'` is hard-coded; Jersey City trips (if present in
   the raw tables) are **labeled NYC, not excluded** — this contradicts the project spec in
   `CLAUDE.md` ("NYC only, Jersey City excluded").
2. **Timezone shift risk.** Citibike raw timestamps are wall-clock **local (NYC)** time, but
   `PARSE_TIMESTAMP` without a zone interprets them as **UTC**; `DATETIME(_ts,
   'America/New_York')` then shifts them ~4–5 h earlier. Trips in the early-morning hours can
   be attributed to the **previous** calendar day. If exact daily attribution matters, the
   parse should treat the string as Eastern local time.
3. **Possible double counting.** `trips` is a plain `UNION ALL` of the two raw tables with no
   dedup. The GCS staging layout shows `post2021` CSVs starting as early as 2016, so if
   `raw_pre2021` and `raw_post2021` cover **overlapping months**, those trips would be counted
   twice. Not confirmed here (would require a scan); flagged for verification.
4. **Query cost.** Because the raw tables are unpartitioned and the date is derived from a
   parsed STRING, a date filter on `trips_daily` cannot prune input — every query rescans the
   full ~331M-row raw tables (≈37–65 GB). This is the motivation for the materialized
   `trips_daily_table`; querying the view directly is expensive.

## Confirmation

No BigQuery objects were created, replaced, or modified. Neither view was re-created; no
`CREATE OR REPLACE` was issued. Only `INFORMATION_SCHEMA` reads, table-metadata reads, dry
runs, and byte-for-byte file comparison were performed. No credentials, tokens, or secret
values are included in this document.
