# Portfolio snapshot inputs

## Citi Bike daily model

The portfolio embeds the validated BigQuery CSV export in the page as compact JSON. It contains 4,827 rows across 1,609 dates, with total, member, and casual counts for each included date. February 23, 2026 is absent and is rendered as a gap.

The embedded rows have this order: days since 2022-01-01 (UTC), then actual trips, expected trips, lower bound, and upper bound for each group in total, member, casual order. The CSV contained the saved model output. Daily precipitation and snowfall labels are unavailable in this export. The chart uses the full refit, while the holdout summary comes from the original validation record.

The airport JSON input stays in the browser when opened.

## Airport reliability

Use the December 2023 route and departure-block serving exports. Sum counts across carriers before creating records. Use verified airport coordinates for route destinations.

- Top level: `source` (short pedigree string), `month` (2023-12), `routes` (array), and `windows` (array).
- Routes: `origin`, `destination` (airport codes), `lat`, `lon` (destination coordinates), `eligible`, `delayed` (integer counts). Use one row per origin and destination.
- Windows: `origin`, `day` (BTS Monday 1 through Sunday 7), `window` (native scheduled time block such as 0600-0659 or Unknown), `eligible`, `delayed` (integer counts). Use one row per origin, day, and block. Keep the unknown block in the data.
- The portfolio checks the fingerprint totals against the audited 23,258 eligible and 4,860 delayed departures. Independently reconcile the route export and coordinate join to source before sharing. The departure-window view pools destinations.

For the 2025 evaluation, use the offline script in the private airport repository with a separately reconciled four-year daily-summary CSV.
