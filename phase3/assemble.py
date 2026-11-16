"""Add the verified performance views to the Phase 2 portfolio."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent

FLIGHT = """<div id="planner-performance" class="panel performance">
<h3>How the flight planner performed</h3>
<p>Both rules chose from the same eligible options using 2022–2024 history. The planner ranked each airport and time window separately. The baseline ranked airports using their pooled all-day disruption rates for the destination. The test compares those fixed choices on 2025 outcomes.</p>
<div class="controls"><label>Destination <select id="performance-destination"></select></label><label>Time preference <select id="performance-scope"><option>Any time</option><option>Morning only</option><option>Evening only</option></select></label></div>
<div id="ranking-summary" aria-live="polite"></div>
<details open><summary>See the January example</summary><div id="ranking-example"></div></details>
<p class="note">Every evaluated destination-month has the same weight. Both selected options need 30 observed flights that month. These historical groups contain different flights, so differences are descriptive. <a href="flight-ranking-holdout.csv" download>Download the results</a> · <a href="flight-frozen-choices.json" download>Download the frozen choices</a>.</p>
</div>
"""
BIKE = """<div id="bike-performance" class="panel performance">
<h3>How the Citi Bike review performed</h3>
<p>Replay 13 complete weeks from June 2 through August 31, 2025. Each day uses its prior matching weekdays to set the expected range. Compare immediate review after one flag with the dashboard rule that waits for two consecutive flags in the same direction.</p>
<div id="replay-summary"></div>
<div class="controls"><label>Week starting <select id="replay-week"></select></label><button type="button" id="replay-day">Reveal next day</button><button type="button" id="replay-next-week">Next week</button><button type="button" id="replay-follow">Reveal seven-day follow-up</button></div>
<div id="replay-detail" aria-live="polite"></div>
<p class="note">The replay measures alert workload and timing using historical review signals. The follow-up counts later signals and cannot verify incidents. <a href="bike-season-replay.csv" download>Download the daily results</a>.</p>
</div>
"""

def assemble(before, data_path, output):
    html = before.read_text()
    for marker, content in [
        ('<div class="panel" id="flight-comparison">', FLIGHT),
        ('<details><summary>Weather model and holdout results</summary>', BIKE),
    ]:
        if html.count(marker) != 1:
            raise ValueError(marker)
        html = html.replace(marker, content + marker, 1)
    html = html.replace('</style>', '''.performance button{font:inherit;color:var(--blue);background:white;border:1px solid #718998;border-radius:.35rem;padding:.3rem .55rem;cursor:pointer}
.performance button:disabled{opacity:.5;cursor:default}
</style>''', 1)
    payload = '<script type="application/json" id="phase-three-data">' + data_path.read_text().strip() + '</script>'
    html = html.replace('<script>\n', payload + '\n<script>\n', 1)
    code = (ROOT / "performance.js").read_text()
    html = html.replace('</script>\n</body>', code + """
showPerformance(JSON.parse(document.getElementById("phase-three-data").textContent));
</script>
</body>""", 1)
    output.write_text(html)


if __name__ == "__main__":
    assemble(*map(Path, sys.argv[1:]))
