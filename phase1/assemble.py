"""Inject reviewed phase-one aggregates and controls into the existing portfolio HTML."""
import json
from pathlib import Path
import re
import sys

from build_flight_phase1 import station_days

root = Path(__file__).resolve().parent
original, flights, nyc, output = map(Path, sys.argv[1:])
page = original.read_text()
flight_data = json.loads(flights.read_text())
if len(flight_data["sourceMonths"]) != 48 or flight_data["decemberReconciliation"] != [23258, 4860]:
    raise ValueError("Flight rebuild failed December reconciliation or full-month coverage.")
bike_weather = station_days(nyc)
context = {}
for day, measurements in bike_weather.items():
    if "2022-01-01" <= day <= "2026-05-31":
        context[day] = [measurements.get(element) for element in ("PRCP", "SNOW", "TMAX")]


def replace(old, new):
    global page
    if page.count(old) != 1:
        raise ValueError(f"Expected one match for {old[:80]}")
    page = page.replace(old, new, 1)


def payload(name, value):
    return '<script type="application/json" id="' + name + '">' + json.dumps(value, separators=(",", ":")) + '</script>\n'


flight_markup = """<div class="panel" id="flight-comparison">
<h3>Compare two ways to fly</h3>
<p>Compare completed departures to the same destination. The comparison uses 2022–2024 data for 20 high-volume destinations served by at least two regional airports.</p>
<div class="controls">
<label>Destination <select id="compare-destination"></select></label>
<label>Compare by <select id="compare-dimension"><option value="1">Origin airport</option><option value="2">Reporting carrier</option><option value="3">Scheduled departure window</option></select></label>
<label>Origin <select id="compare-origin"><option>BWI</option><option>DCA</option><option>IAD</option></select></label>
<label>Option A <select id="compare-a"></select></label>
<label>Option B <select id="compare-b"></select></label>
</div>
<div id="compare-results" aria-live="polite"></div>
</div>
<div class="panel" id="flight-holdout"><h3>2025 holdout evaluation</h3>
<p>Both models were trained on 2022–2024 BTS departure records. The baseline uses airport, reporting carrier, destination, month, and scheduled departure window. The second model adds daily airport precipitation or snowfall and maximum temperature. A delay means departure at least 15 minutes late among eligible completed flights.</p>
<div id="holdout-results"></div>
<p class="note"><a href="https://www.transtats.bts.gov/PREZIP/">BTS monthly files</a> · <a href="https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/">NOAA daily station observations</a> · <a href="flight-rebuild-evidence.json" download>Download evaluation and monthly reconciliation</a></p>
</div>
"""
replace('<div class="panel">\n<h3>Routes and departure windows</h3>', '<div class="panel">\n<h3>December 2023 routes and departure windows</h3>')
replace('<p class="kicker">BTS and NOAA · December 2023</p>', '<p class="kicker">BTS and NOAA · 2022–2025</p>')
replace('<div class="metrics"><div class="metric"><strong>23,258', flight_markup + '<h3>December 2023 warehouse snapshot</h3>\n<div class="metrics"><div class="metric"><strong>23,258')
replace('<h3>Daily observed and expected ridership</h3>', '<h3>Daily ridership anomaly explorer</h3>')
replace('Pick a rider group, then compare unusually high and low dates with the model’s expected range. Click the chart or select a date to inspect the observed count, the model estimate, and the expected range.', 'Select a rider group or use the flagged-date list to inspect a day outside the model range. The lower chart shows observed minus expected trips on the same date scale.')
replace('<div id="bike-detail"></div>', '<div id="bike-detail"></div>\n<p class="note">Weather context comes from <a href="https://www.ncei.noaa.gov/access/search/data-search/daily-summaries?stations=USW00094728">NOAA’s Central Park station</a>. It is displayed for reference alongside the saved model output.</p>')
replace('</style>', '[hidden]{display:none!important}\n#bike-detail h4{margin-bottom:.35rem}\n</style>')
replace('<script>\n', payload("phase-one-flight-data", {k: flight_data[k] for k in ("evaluation", "routes")})
        + payload("phase-one-bike-weather", context) + '<script>\n')
replace('function showBike(data) {', '''const bikeWeather = JSON.parse(document.getElementById("phase-one-bike-weather").textContent);
function showBike(data) {''')
replace("Inspect date <input type=\"date\" id=\"daily-date\"></label></div><div class=\"result\"></div><p id=\"daily-readout\" class=\"readout\" aria-live=\"polite\"></p>';", """Inspect date <input type="date" id="daily-date"></label><label>Flagged dates <select id="flagged-date"></select></label></div><div class="result"></div><div id="daily-readout" class="readout" aria-live="polite"></div>';""")
replace('  const readout = target.querySelector("#daily-readout");', '''  const readout = target.querySelector("#daily-readout");
  const flagSelect = target.querySelector("#flagged-date");
  const allDates = new Map();
  for (const row of data.rows) {
    if (!allDates.has(row.date)) allDates.set(row.date, []);
    allDates.get(row.date).push(row);
  }
  const trips = n => format.format(Math.round(n));
  const signed = n => (Math.round(n) > 0 ? "+" : "") + trips(n);''')
left = page.index('    const low = flagged')
right = page.index('    target.querySelector(".result")', left)
page = page[:left] + '''    const orderedFlags = flagged.slice().sort((a, b) =>
      Math.abs(b.actual - b.expected) - Math.abs(a.actual - a.expected) || a.date.localeCompare(b.date));
    flagSelect.innerHTML = optionList([["", "Choose a flagged day"], ...orderedFlags.map(r =>
      [r.date, r.date + " · " + signed(r.actual - r.expected) + " trips"])]);
    flagSelect.disabled = flagged.length === 0;
    const residualMax = Math.max(1, ...rows.map(r => Math.abs(r.actual - r.expected)));
    const residualY = r => 68 - 52 * (r.actual - r.expected) / residualMax;
''' + page[right:]
replace('      +examples.map(r=>', '      +flagged.map(r=>')
left = page.index('      +(examples.length?')
right = page.index('    const chart =', left)
page = page[:left] + '''      + '<h4>Trips above or below expected</h4>'
      + '<svg id="residual-plot" class="chart interactive-chart" viewBox="0 0 800 142" role="img" aria-label="Daily difference from expected trips">'
      + '<line x1="42" x2="784" y1="68" y2="68" stroke="#8195a1"/>'
      + '<text x="39" y="20" text-anchor="end" font-size="11">+' + Math.round(residualMax / 1000) + 'k</text>'
      + '<text x="39" y="72" text-anchor="end" font-size="11">0</text>'
      + '<text x="39" y="120" text-anchor="end" font-size="11">−' + Math.round(residualMax / 1000) + 'k</text>'
      + segments.map(points => '<polyline points="' + points.map(r => x(r).toFixed(1) + ',' +
        residualY(r).toFixed(1)).join(" ") + '" fill="none" stroke="#365f81" stroke-width="1.6"/>').join("")
      + flagged.map(r => '<circle cx="' + x(r) + '" cy="' + residualY(r) + '" r="3" fill="#a1491c"/>').join("")
      + '<line id="residual-cursor" y1="12" y2="120" stroke="#14283d" stroke-dasharray="4 4"/>'
      + '<text x="42" y="138" font-size="11">' + rows[0].date + '</text><text x="784" y="138" text-anchor="end" font-size="11">' + rows.at(-1).date + '</text></svg>'
      + '<p class="note">' + format.format(flagged.length) + ' of ' + format.format(rows.length)
      + ' days are outside the expected range. Orange dots mark these dates. A flag calls for investigation; it does not identify the cause.</p>';
''' + page[right:]
left = page.index('      const trips = n=>')
right = page.index('    inspect();\n  };', left)
page = page[:left] + '''      const cursor = target.querySelector("#residual-cursor");
      cursor.style.visibility = inRange ? "visible" : "hidden";
      if (inRange) {
        cursor.setAttribute("x1", x({date}));
        cursor.setAttribute("x2", x({date}));
      }
      flagSelect.value = r && (r.actual > r.upper || r.actual < r.lower) ? date : "";
      if (!r) {
        readout.textContent = inRange ? "No observation in the export for " + date + "." : "Choose a date within the selected period.";
        return;
      }
      const status = row => row.actual < row.lower ? "Below range" : row.actual > row.upper ? "Above range" : "In range";
      const wx = bikeWeather[date] ?? [];
      const measurement = (index, divisor, unit) => {
        const value = wx[index];
        if (!value) return "Unavailable";
        return value[1] ? "Trace" : (value[0] / divisor).toFixed(1) + " " + unit;
      };
      readout.innerHTML = '<strong>' + date + '</strong><p>Central Park · Precipitation: '
        + measurement(0, 10, "mm") + ' · Snow: ' + measurement(1, 1, "mm")
        + ' · High: ' + measurement(2, 10, "°C") + '</p>'
        + table(["Riders", "Observed", "Expected", "Difference", "Model range", "Status"],
            allDates.get(date).map(row => [row.series[0].toUpperCase() + row.series.slice(1),
              trips(row.actual), trips(row.expected), signed(row.actual - row.expected),
              trips(row.lower) + "–" + trips(row.upper), status(row)]));
    }
    dateInput.onchange = inspect;
    flagSelect.onchange = () => {
      if (!flagSelect.value) return;
      dateInput.value = flagSelect.value;
      inspect();
    };
    function inspectChart(event) {
      const chart = event.currentTarget;
      const transforms = chart.getScreenCTM();
      if (!transforms) return;
      const position = new DOMPoint(event.clientX, event.clientY).matrixTransform(transforms.inverse());
      const f = Math.max(0, Math.min(1, (position.x - 42) / 742));
      dateInput.value = new Date(first + Math.round(f * span / 86400000) * 86400000).toISOString().slice(0, 10);
      inspect();
    }
    chart.addEventListener("click", inspectChart);
    target.querySelector("#residual-plot").addEventListener("click", inspectChart);
''' + page[right:]
replace('const stateOutlines =', (root / "flight-comparison.js").read_text() +
        '\nshowFlightPhaseOne(JSON.parse(document.getElementById("phase-one-flight-data").textContent));\nconst stateOutlines =')
output.write_text(page)
