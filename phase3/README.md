# Phase 3 performance evaluation

## Citi Bike

The seasonal replay spans the 13 complete weeks from June 2 to August 31, 2025. Each day's alert uses only the second-lowest and second-highest observations from up to 12 previous matching weekdays. A gap or an in-range day breaks a run, and the rule resets on Monday. The same-day comparator reviews any flag while the Phase 2 grouping rule waits for two consecutive same-direction flags. The later seven-day observations are used solely for retrospective follow-up. This evaluates workload and timing, with no verified incident labels.

## Flights

The planner and the pooled-airport baseline share the 20 Phase 2 destinations, candidate airport/window choices, time filters, and support threshold (100 classified departures and 12 observed months). The baseline pools all windows in training for each destination and origin. Within an equal score it favors the option with greater historical volume, then airport code and window order. Both sets of choices are written before loading 2025 outcomes and stay fixed across the 12 months. A comparable case requires 30 observed classified departures for each selected option in that month. Selection does not fall back to another option after examining 2025. Results publish comparable coverage, exclusion reasons, equal-case averages, and choice-level counts. The 2025 BTS files were previously used for Phase 1's different delay-model evaluation. Their outcomes were excluded from Phase 3 choice construction.

The test describes observed rates for historical alternatives. Flights are not matched by individual traveler itinerary, weekday, or carrier. Periods and time-preference cases overlap and should not be summed. Composite disruptions use the Phase 2 classification.

## Reproduce

Use the Phase 1 dependencies and archived BTS inputs. Run from the portfolio root.

```sh
git show d6e22d3ce5fcb7e25ad668b337c040f19a9d7547:index.html > phase2-original.html
python phase3/evaluate.py INPUT_DIR planner-monthly-evidence.json flight-rebuild-evidence.json phase2-original.html results
python phase3/assemble.py phase2-original.html results/performance.json index.html
```

Publish the two CSVs and frozen choices JSON alongside the generated index.
