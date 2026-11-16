# Portfolio snapshot inputs

## Citi Bike daily model

The portfolio embeds the validated BigQuery CSV export in the page as compact JSON. It contains 4,827 rows across 1,609 dates, with total, member, and casual counts for each included date. February 23, 2026 is absent and is rendered as a gap.

The embedded rows have this order: days since 2022-01-01 (UTC), then actual trips, expected trips, lower bound, and upper bound for each group in total, member, casual order. The CSV contained the saved model output. Daily precipitation and snowfall labels are unavailable in this export. The chart uses the full refit, while the holdout summary comes from the original validation record.

## Airport reliability

The portfolio embeds December 2023 aggregates from the project warehouse. The daily summary contains all 31 dates and 1,016 rows at date × origin × carrier grain. The departure-window export has 2,008 source rows and reconciles to the daily summary by origin, carrier, and weekday, including 23,258 eligible departures and 4,860 delayed departures in total.

The page combines carriers into 377 scheduled-window groups and 18 origin-destination groups. The route export includes six destinations and 5,338 eligible departures. Its counts describe those routes only. The 2025 holdout still requires the complete four-year aviation export and is outside this December snapshot.
