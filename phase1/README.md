# Phase 1 dashboard rebuild

The live portfolio is a static GitHub Pages site. The original December 2023 warehouse visuals remain available as a labeled snapshot. The comparison and holdout use an independent offline rebuild from official sources.

## Inputs and reproduction

1. Download all 48 monthly [BTS Reporting Carrier On-Time Performance archives](https://www.transtats.bts.gov/PREZIP/) for January 2022 through December 2025. Rename the ZIPs to `YYYY-MM.zip`. Download [NOAA station files](https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/) for BWI (`USW00093721`), DCA (`USW00013743`), IAD (`USW00093738`), and Central Park (`USW00094728`). Keep the original NOAA filenames.
2. Install pandas 2.2.3, scikit-learn 1.8.0, and SciPy 1.17.0 in a Python 3.12 environment. Run `python phase1/build_flight_phase1.py INPUT_DIR flight-rebuild-evidence.json`.
3. Save the previous portfolio HTML using `git show c0b17093a06dec746608c341231db78e0d1acbc3:index.html > original.html`. Run `python phase1/assemble.py original.html flight-rebuild-evidence.json INPUT_DIR/USW00094728.csv.gz index.html`.

The evidence JSON includes the evaluation, monthly BTS row counts, eligible departures, archive SHA-256 digests, and comparison aggregates. No account credentials or private raw data are required.

## Flight definitions

- Eligible departures are BTS records leaving BWI, DCA, or IAD that were neither canceled nor diverted and have a departure delay value. The event is a departure delay of at least 15 minutes.
- The comparison uses descriptive 2022–2024 rates for the 20 highest-volume destinations with at least 100 eligible flights from each of two regional origins. Each pair uses the same pooled dry/wet mix where both options have at least 100 eligible departures and at least 30 flights per weather category.
- Weather is wet if NOAA reports nonzero or trace daily precipitation or snowfall, and dry if both valid measurements are zero. The holdout also requires valid daily maximum temperature. Same-day observed weather is used in this retrospective evaluation.
- The baseline is a regularized logistic model of origin, operating carrier, destination, calendar month, and scheduled departure bucket. The weather model adds the wet indicator and maximum temperature. Both train on the same eligible 2022–2024 rows with complete weather and are scored on the same 2025 rows using the Brier score. The comparison omits cancellations and diversions from both model denominators.
- December 2023 reconciles to the existing warehouse export at 23,258 eligible flights and 4,860 departures delayed 15 minutes or more.

## Citi Bike definitions

A flag is a date with observed trips strictly outside its saved model range for the selected rider group. The lower chart shows observed minus expected trips. Central Park weather is observed context alongside the original model export. Precipitation includes liquid equivalent for frozen precipitation where recorded, and traces remain identified. The missing February 23, 2026 ridership observation remains a gap.
