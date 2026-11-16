"""Add Phase 2 reviews to the deployed Phase 1 portfolio."""
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent


def planner_options(data):
    options = defaultdict(list)
    for month, destination, origin, window, n, late, canceled, diverted in data["monthly"]:
        options[destination, origin, int(window)].append((month, n, late, canceled, diverted))
    rng = np.random.default_rng(20251116)
    result = []
    for key, months in sorted(options.items()):
        n, late, canceled, diverted = (int(x) for x in np.asarray(months)[:, 1:].sum(axis=0))
        interval = None
        if n >= 100 and len(months) >= 12:
            counts = np.array(months)[:, 1:]
            draw = rng.integers(len(months), size=(2000, len(months)))
            sample = counts[draw].sum(axis=1)
            rate = sample[:, 1:].sum(axis=1) / sample[:, 0]
            interval = np.quantile(rate, [0.025, 0.975]).round(5).tolist()
        result.append([*key, n, late, canceled, diverted, len(months), interval])
    return {"options": result}


def assemble(before, planner_path, out):
    page = before.read_text()
    planner = planner_options(json.loads(planner_path.read_text()))
    flight = """<div class="panel" id="trip-planner">
<h3>Trip reliability planner</h3>
<p>Choose a destination and acceptable local departure times. Compare BWI, DCA, and IAD using historical rates for flights that left 15 minutes late or more, were canceled, or were diverted.</p>
<div class="controls"><label>Destination <select id="planner-destination"></select></label><button type="button" id="planner-example">Try Atlanta: morning vs. evening</button></div>
<fieldset id="planner-window-group"><legend>Acceptable departure windows</legend><div id="planner-windows" class="controls"></div></fieldset>
<div id="planner-results" aria-live="polite"></div>
<p class="note">BTS departures from 2022–2024. Options need 100 classified flights across at least 12 months. The 95% intervals resample whole observed months and describe uncertainty in the historical rate. Schedules may have changed. The 2025 weather holdout used observed weather, so this planner uses historical rates. <a href="planner-monthly-evidence.json" download>Download monthly counts</a>.</p>
</div>
"""
    bike = """<div class="panel" id="bike-weekly">
<h3>Weekly demand review</h3>
<p>Review weeks for unusually high or low total trips. Two or more consecutive flags in the same direction within a Monday–Sunday week form a sustained run. The member and casual gaps use each group’s own baseline and can differ in sum from the total gap.</p>
<div class="controls"><label>Week starting <select id="review-week"></select></label><button type="button" id="review-example">Try a week with a sustained run</button><button type="button" id="review-download">Download flagged dates (CSV)</button></div>
<div id="review-results" aria-live="polite"></div>
<details><summary>How often would the rules trigger?</summary>
<p>A chronological replay across complete weeks in 2025 used only earlier counts. It flags days outside the second-lowest and second-highest totals from up to 12 prior matching weekdays, with at least 10 available. The weekly dashboard above uses the saved weather-adjusted bands. The replay measures review workload, since confirmed incident labels are unavailable.</p>
<div id="review-backtest"></div>
</details>
</div>
"""

    def replace(old, new):
        nonlocal page
        if page.count(old) != 1:
            raise ValueError(f"Expected one marker: {old!r}")
        page = page.replace(old, new, 1)

    replace('<div class="panel" id="flight-comparison">', flight + '<div class="panel" id="flight-comparison">')
    replace('<details><summary>Weather model and holdout results</summary>', bike + '<details><summary>Weather model and holdout results</summary>')
    replace('</style>', '''#trip-planner button,#bike-weekly button{font:inherit;color:var(--blue);background:white;border:1px solid #718998;border-radius:.35rem;padding:.3rem .55rem;cursor:pointer}
#bike-weekly button:disabled{opacity:.5;cursor:default}#planner-window-group{display:block;margin:.7rem 0}#planner-windows{margin:.25rem 0}
#trip-planner th,#bike-weekly th{min-width:6rem}
</style>''')
    payload = '<script type="application/json" id="phase-two-planner">' + json.dumps(planner, separators=(",", ":")) + '</script>'
    code = "\n".join((ROOT / name).read_text() for name in ("weekly.js", "planner.js"))
    replace('<script>\n', payload + '\n<script>\n')
    replace('</script>\n</body>', code + """
renderWeeklyReview(exportRows);
renderTripPlanner(JSON.parse(document.getElementById("phase-two-planner").textContent));
</script>
</body>""")
    out.write_text(page)


if __name__ == "__main__":
    assemble(*map(Path, sys.argv[1:]))
