# Phase 2 decision workflows

The GitHub Pages portfolio publishes two static tools using the Phase 1 sources. No warehouse connection is required.

## Citi Bike weekly demand review

The review groups total-ridership flags from the saved model export in Monday–Sunday weeks. Two consecutive same-direction flags form a sustained run. A missing or unflagged date breaks the run, as does a week boundary. Member and casual trip differences use their separate model baselines, so they need not add to the total residual. The CSV contains observed flagged dates for the current week.

The 2025 chronological replay evaluates alert workload using only earlier days. It flags a date outside the second-lowest and second-highest observations from the preceding 12 matching weekdays, requiring 10 valid observations. Only complete weeks in 2025 enter the replay comparison. This tests the alert grouping rule against a point-in-time baseline. The chart's full-data refit is a separate retrospective view.

## Flight planner

The planner ranks acceptable airport-by-scheduled-window options by historical disruption rates for the 20 Phase 1 destinations. A disruption is a cancellation, diversion, or departure at least 15 minutes late; the categories are mutually exclusive in that order. The denominator is classified scheduled departures. Flights with invalid times or insufficient status data are excluded and counted in the evidence. Options require 100 classified flights and observations in at least 12 months. Intervals are the 2.5th to 97.5th percentiles from 2,000 weighted rate calculations after resampling observed months with replacement. These intervals quantify historical sampling variability, not forecast uncertainty.

Phase 1 evaluated the delay model using observed same-day weather, and it did not model the planner's composite disruption outcome. The planner therefore displays historical disruption rates. The existing weather-standardized comparison remains a separate historical analysis.

## Reproduction

Install the Phase 1 Python dependencies. Obtain the Phase 1 BTS monthly files as documented in the Phase 1 README. This script rechecks archive hashes and national monthly totals before aggregating January 2022 through December 2024.

```sh
git show c6ef2a30ce0f00c9f6c07a2b68df5b8dba83b9b9:index.html > original.html
python phase2/build_planner.py INPUT_DIR flight-rebuild-evidence.json planner-monthly-evidence.json
python phase2/assemble.py original.html planner-monthly-evidence.json index.html
```

The planner evidence records compact arrays ordered as month index (0 = January 2022), destination, origin, window index (0 through 4), scheduled departures, late, canceled, diverted. See the planner for the five local-time window definitions.
