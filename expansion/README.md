# Portfolio coverage and decision workflows

## Citi Bike

Download the official New York City files with `bash expansion/fetch-bike.sh INPUT_DIR`. Stream the monthly ZIPs with `bash expansion/process-bike.sh INPUT_DIR`. The January 2026 archive contributes December 2025 boundary records and covers the worked example. Run `python expansion/aggregate_bike.py INPUT_DIR PHASE3_HTML OUT_DIR`. Monthly totals use local trip start date, and the audit includes ZIP digests, row totals, missing station IDs, and reconciliation to the daily model. The 2024–2025 archive totals match the saved daily counts on every date.

Station results publish the largest 12 decreases and increases on each supported flagged week. For each flagged date, the station expectation is the mean of the preceding four matching weekdays. Dates with incomplete source coverage are skipped. Station totals include starts without a recorded station ID, shown separately. Comparison and source downloads contain aggregate data.

## Flights

The network is the original three Capital Region airports plus the 20 destinations from the prior comparison. Origins and destinations both use this set. Build `airports.json` with `map_weather.py`, using OurAirports airport coordinates and the NOAA ISD and GHCN station inventories. Match exact ICAO IDs and require a GHCN station within 15 km. Historical ISD record dates are a mapping check; use actual 2022–2025 GHCN precipitation and snow observations to measure coverage. The UI requires 95% matched selected flights and at least 30 flights in each weather group before comparing two or more origins. Missing weather remains unknown.

Run `python expansion/build_flights.py BTS_2022_2025 BTS_2026_JAN_JUN WEATHER_DIR flight-rebuild-evidence.json OUT_DIR` with the Phase 1 dependencies. Route and heatmap monthly network counts both reconcile to the selected BTS records. Each year is fetched separately as gzip-compressed JSON. The 2022–2024 training rule selects supported historical rates. The replay finds recorded route and time-window choices from January–June 2026 and applies the frozen rankings without consulting disruption outcomes when selecting. This is retrospective: BTS cannot establish which alternatives were visible or bookable before departure. The evaluated rates use equal weight per date and destination. The existing 2025 evaluation remains a different test.

## Publish

Run `python expansion/assemble.py PHASE3_HTML OUT_DIR index.html`, then `python expansion/add_tabs.py index.html` and `gzip -n -c OUT_DIR/flight-schedule-replay.csv > OUT_DIR/flight-schedule-replay.csv.gz`. Compress each flight-network-YYYY.json with gzip and publish the generated index, both expansion JS files, and aggregate evidence files. Use `--watts` when the static public Watt’s Next assets are deployed under `watts-next/`. That copy uses only assets served by the original public dashboard.
