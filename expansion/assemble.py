"""Build the expanded GitHub Pages portfolio from Phase 3 and audited data."""
import json
from pathlib import Path
import re
import sys

BIKE = """<div class="panel" id="bike-decision">
<h3>Where should we investigate the January 26–27 ridership drop?</h3>
<p>Both days fell below the citywide model range. Use station trip starts to decide where to investigate first. The station comparison uses the preceding four matching weekdays for each flagged date.</p>
<div class="controls"><label>Flagged week starting <select id="station-week"></select></label><label>Rider group <select id="station-rider"><option value="all">All riders</option><option value="member">Members</option><option value="casual">Casual riders</option></select></label><button type="button" id="station-example">Reset to January 26</button></div>
<div id="station-results" aria-live="polite"></div>
<p class="note">Shows the 12 largest decreases and 12 largest increases, where present, by station ID. Station openings or closures can affect the comparison. Trip records measure recorded use. Testing bike or dock availability would require station inventory history.</p>
<p><a href="bike-station-breakdown.csv" download>Download station results</a> · <a href="bike-archive-audit.json" download>Download archive reconciliation</a></p>
</div>
"""
FLIGHT = """<div class="panel" id="flight-decision">
<h3>Which Atlanta departure should I consider if morning or evening works?</h3>
<p>Compare disruption rates for morning and evening options from the Capital Region. For the worked date, the candidates are departures recorded in BTS for that day. Rates used to rank them come from 2022–2024.</p>
<label>Recorded Atlanta travel date <select id="schedule-date"></select></label>
<div id="schedule-example-output" aria-live="polite"></div>
<p><a href="#trip-planner">Change the destination or acceptable times in the historical planner</a> · <a href="#schedule-evaluation">See the evaluation</a></p>
<p class="note">Retrospective schedule replay. BTS departure records do not establish which flights a traveler could see or book in advance. This view uses no live schedule or fare data.</p>
</div>
"""
EVAL = """<div class="panel" id="schedule-evaluation">
<h3>Historical schedule replay · January–June 2026</h3>
<p>Both rankings use the same nonstop options recorded for each date and destination. Both require at least 100 classified departures across 12 training months for each option. The planner ranks by origin and window. The baseline pools time windows at each origin for that destination.</p>
<div class="controls"><label>Origin scope <select id="schedule-scope"><option>Capital Region</option><option>All origins</option></select></label><label>Preference <select id="schedule-preference"><option>Any time</option><option>Morning</option><option>Evening</option><option selected>Morning or evening</option></select></label></div>
<div id="schedule-eval-output" aria-live="polite"></div>
<p class="note">Equally weighted date–destination rates. A single day can have few flights. Outcomes are descriptive and groups may differ in carrier and schedule mix. <a href="flight-schedule-replay.csv.gz" download>Download case results (compressed CSV)</a> · <a href="flight-network-audit.json" download>Download coverage and source counts</a>.</p>
</div>
"""
NETWORK = """<div class="panel" id="flight-network">
<h3>Route map and departure-time heatmap</h3>
<p>Explore nonstop flights between the original three airports and the 20 airports previously offered as destinations. Disruption means a departure delayed at least 15 minutes, a cancellation, or a diversion.</p>
<div class="controls"><label>Departure airport <select id="network-origin"></select></label><label>Map destination <select id="network-destination"></select></label><label>Start month <input type="month" id="network-from" min="2022-01" max="2025-12" value="2025-01"></label><label>End month <input type="month" id="network-to" min="2022-01" max="2025-12" value="2025-12"></label></div>
<div id="network-output" aria-live="polite"></div>
<p class="note">Coverage from January 2022 through December 2025. The map displays up to 15 routes by flight volume, while the table lists every matching route. <a href="flight-network-audit.json" download>Download source and weather coverage</a>.</p>
</div>
"""


def main(original, data, output, watts):
    page = original.read_text()

    def replace(old, new):
        nonlocal page
        if page.count(old) != 1:
            raise ValueError(f"Invalid indicator {old!r}")
        page = page.replace(old, new, 1)

    bike = json.loads((data / "bike-expansion.json").read_text())
    page, count = re.subn(r"(const monthly = )(\[.*?\]);",lambda match: match[1]+json.dumps(
        json.loads(match[2])+bike["months"],separators=(",",":"))+";",page,count=1)
    if count != 1:
        raise ValueError("Missing monthly data")
    replace('<p class="kicker">Citi Bike · 2022 and 2023 archive audit</p>', '<p class="kicker">Citi Bike · 2022–2025 archive audit</p>')
    replace('<p>How does ridership change through the year, and when does it fall outside the range a historical model would expect?</p>', BIKE)
    replace('<p class="guide"><strong>Try this.</strong> Select 2023, compare member and casual trips, then open the model results. The monthly counts show seasonality. A daily weather-adjusted baseline is the next step when investigating a particular day.</p>', '')
    replace('<select id="bike-year"><option>2023</option><option>2022</option></select>', '<select id="bike-year"><option>2025</option><option>2024</option><option>2023</option><option>2022</option></select>')
    replace('Monthly totals count 2022 and 2023 archive records by trip-start month.', 'Monthly totals count 2022–2025 NYC archive records by local trip-start month.')
    replace('<div id="review-results" aria-live="polite"></div>', '<div id="review-results" aria-live="polite"></div><button type="button" id="weekly-stations">Inspect stations for this week</button><p id="weekly-station-status" class="note" aria-live="polite"></p>')
    replace('<p>How did departure reliability vary across BWI, DCA, and IAD, and how did it differ with daily weather?</p>', FLIGHT)
    replace('<div id="planner-performance" class="panel performance">', EVAL + NETWORK + '<div id="planner-performance" class="panel performance">')
    replace('December 2023 routes and departure windows', 'Archive example · December 2023 routes and departure windows')
    replace("renderBars(document.getElementById(\"bike-results\"),\"Month\",\"Trips\",rows,4000000,", "renderBars(document.getElementById(\"bike-results\"),\"Month\",\"Trips\",rows,Math.max(1,...rows.map(row=>row[1])),")
    replace('</style>', '''input[type=month]{font:inherit;border:1px solid #718998;border-radius:.35rem;padding:.2rem .35rem;color:var(--ink);background:white;max-width:100%}
#flight-network select{max-width:min(100%,24rem)}
#bike-decision button{font:inherit;color:var(--blue);background:white;border:1px solid #718998;border-radius:.35rem;padding:.3rem .55rem;cursor:pointer}
</style>''')
    replace('</body>', '<script src="expansion/views.js"></script>\n</body>')
    if watts:
        replace('https://watts-next-team.wintry-wasp-6446.chatgpt.site/', 'watts-next/')
    output.write_text(page)


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:4]), "--watts" in sys.argv[4:])
