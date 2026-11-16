# Portfolio snapshot inputs

The portfolio accepts JSON files from the local device. Uploads stay in the browser. The bundled headline figures continue to display independently.

## Citi Bike daily model

Use the signed-off weather-model export, including date, rider series, actual trips, expected trips, lower and upper expected bounds, and weather category from the dated daily weather source. Translate the exported fields to this shape:

- Top level: `source` (short pedigree string) and `rows` (array).
- Each row: `date` (ISO day), `series` (total, member, or casual), `actual` (integer trips), `expected`, `lower`, `upper` (nonnegative trips as numbers), and `weather` (Adverse, Calm, or Unavailable).
- Use one row per day and series. Keep missing weather labeled Unavailable. Check sample days against the original model and preserve the model vintage.

## Airport reliability

Use the December 2023 route and departure-block serving exports. Sum counts across carriers before creating records. Use verified airport coordinates for route destinations.

- Top level: `source` (short pedigree string), `month` (2023-12), `routes` (array), and `windows` (array).
- Routes: `origin`, `destination` (airport codes), `lat`, `lon` (destination coordinates), `eligible`, `delayed` (integer counts). Use one row per origin and destination.
- Windows: `origin`, `day` (BTS Monday 1 through Sunday 7), `window` (native scheduled time block such as 0600-0659 or Unknown), `eligible`, `delayed` (integer counts). Use one row per origin, day, and block. Keep the unknown block in the data.
- The portfolio checks the fingerprint totals against the audited 23,258 eligible and 4,860 delayed departures. Independently reconcile the route export and coordinate join to source before sharing. The departure-window view pools destinations.

For the 2025 evaluation, use the offline script in the private airport repository with a separately reconciled four-year daily-summary CSV.
