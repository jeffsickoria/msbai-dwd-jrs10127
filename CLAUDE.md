# Citibike Pipeline — Project Spec

## Scope
- NYC trips only (Jersey City excluded). Reason: ...
- Date range: 2013-present. Reason: ...

## Schema
- Two schemas exist (pre/post 2021). Unified mapping: [list columns]

## Distance
- Computed as Haversine straight-line distance from start/end lat/lon.
- Disclosure: this is not route distance.

## Day Definition
- A trip counts toward the day of its start_time in US/Eastern timezone.

## Pipeline Stages
archive → GCS → raw BQ tables → clean unified view → daily summary view → materialized table

## GCP
- Project: [your project id]
- GCS bucket: [your bucket name]
- BQ dataset: [your dataset name]


##Here are my decisions and reasoning:

**1. NYC vs Jersey City — NYC only.**
The NYC files have 10–100x more trips, giving better statistical power for any analysis. JC files are also inconsistently named (spaces, typos) and start later (Sep 2015). Keeping one geography also avoids the confound of different urban environments and station densities.

**2. Cutoff — 2020 onward (monthly files only).**
Pre-2021 annual bundles bundle 12 months into one zip with unknown internal structure, and the schema change lands around 2021 (old: `starttime`, `tripduration`; new: `started_at`, `ride_id`, `rideable_type`). Starting at 202001 gives clean monthly granularity, a consistent new schema, and still covers 5+ years / 300M+ rows. We discard 2013–2019 annual zips entirely.

**3. Distance — Haversine, disclosed.**
Agreed. Fast to compute at scale, no routing API dependency, reproducible. We document it as straight-line distance and note it underestimates true route distance by ~20–30%.

**4. "Day" — trip `started_at` localized to US/Eastern.**
Captures the rider's behavioral day (commute, weekend leisure, etc.) and aligns with any weather data joined by date.

**5. Files we actually need — from the inventory:**

```
202001-citibike-tripdata.zip  through  202605-citibike-tripdata.zip
```

That's lines 8–40 in `archive_inventory.txt` — **33 files**, all NYC, all monthly, consistent new schema. No JC files, no annual bundles, no `index.html`.

Ready to build the download script?
