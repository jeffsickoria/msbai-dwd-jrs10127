# Weather-Adjusted Ridership v2 — Model Design, Validation, and Deployment

Stretch 1 was completed using
`scripts/build_weather_model_v2.py`.

The model reads:

- `msbai-dwd-jrs10127.citibike.trips_daily_table_v2`
- `nyu-datasets.weather.m_weather_daily_nyc`

and created:

- `msbai-dwd-jrs10127.citibike.trips_daily_model_v2`

The final table contains 4,827 rows and model version `wa_v2_ols_1`. It is
monthly partitioned on `date` and clustered by `rider_series`.

## Design

- **Target:** `log1p(trips)`
- **Estimator:** ordinary least squares, one model per rider series
- **Series:** total, member, and casual
- **Features:** average temperature, temperature squared, precipitation, snow,
  day of week, and month
- **Modeling window:** 2022-01-01 through 2026-05-29
- **Holdout:** the final 179 days, 2025-12-01 through 2026-05-29
- **Training period:** 2022-01-01 through 2025-11-30
- **Unknown riders:** included in total but never reassigned to member or casual

A global linear time trend was tested and rejected because it worsened the
time-based holdout. The final no-trend specification outperformed the
seasonal-naive baseline for all three rider series.

## Time-based holdout results

| Series | MAE | MAPE | WAPE | Mean bias | Improvement over baseline | Flagged by expected band |
|---|---:|---:|---:|---:|---:|---:|
| Total | 23,808 | 31.7% | 26.1% | -17,630 | 18.0% | 4.23% |
| Member | 21,993 | 33.0% | 28.1% | -16,805 | 12.8% | 3.98% |
| Casual | 2,595 | 34.4% | 20.3% | -1,083 | 44.7% | 4.97% |

The negative holdout bias means the model underpredicts part of the recent
growth period. It is therefore used as a descriptive anomaly-detection aid,
not as a reliable forward forecasting model.

## Output schema

`trips_daily_model_v2` contains:

- `date`
- `rider_series`
- `actual_trips`
- `expected_trips`
- `lower_expected_bound`
- `upper_expected_bound`
- `residual`
- `percent_gap`
- `gap_flag`
- `model_version`
- `training_start`
- `training_end`

Validation confirmed:

- 4,827 unique date/rider-series keys
- zero duplicate keys
- zero null dates
- no negative actual-trip counts
- ordered expected bounds
- correct residual and percent-gap formulas
- gap flags consistent with the documented rule
- no rows from the old pre-v2 model

## Gap rule

A date is flagged when actual ridership falls outside the model's approximate
95% expected range.

A flagged day is outside the model's typical error range and merits
investigation. It does not prove a shortage, outage, special event, promotion,
or any other cause.

## Deployment

Cloud Run revision `citibike-app-00005-t4q` receives 100% of traffic and uses:

`MODEL_TABLE=msbai-dwd-jrs10127.citibike.trips_daily_model_v2`

The live dashboard displays actual versus expected ridership, the expected
range, high/low flags, and the non-causation caveat.

Two independent unauthenticated browser tests passed. Broadband load times
were 3 seconds cold and 1 second warm.

Detailed execution evidence:

- `docs/execution/stage2-bigquery-migration.md`
- `docs/execution/stage3-model-v2-deployment.md`
- `evidence/stage2-bigquery-resources.csv`
- `evidence/stage3-model-v2-deployment.csv`
