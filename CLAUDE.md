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
