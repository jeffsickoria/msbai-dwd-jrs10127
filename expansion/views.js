const reliabilityWindows = ["00:00–05:59", "06:00–09:59", "10:00–13:59", "14:00–17:59", "18:00–23:59"];
const archivedData = async name => {
  const response = await fetch(name);
  if (!response.ok) throw Error(name + " returned " + response.status);
  if (name.endsWith(".gz")) {
    return new Response(response.body.pipeThrough(new DecompressionStream("gzip"))).json();
  }
  return response.json();
};

function showStationReview(data) {
  const week = document.querySelector("#station-week");
  const rider = document.querySelector("#station-rider");
  const results = document.querySelector("#station-results");
  const available = Object.keys(data.weeks).sort().reverse();
  week.innerHTML = optionList(available.map(value => [value,value]));
  week.value = "2026-01-26";
  const fmt = value => format.format(Math.round(value * 100) / 100);
  const signed = value => (value > 0 ? "+" : "") + fmt(value);

  function draw() {
    const entry = data.weeks[week.value];
    const {total, unknown, stations} = entry.groups[rider.value];
    results.innerHTML = '<p><strong>' + entry.dates.map(plain).join(", ") + '</strong> · '
      + fmt(total[0]) + ' trip starts, versus ' + fmt(total[1]) + ' on comparable weekdays. Difference: '
      + signed(total[0] - total[1]) + '.</p>'
      + table(["Station", "Trip starts", "Prior matching weekdays", "Difference"],
        stations.map(([id, name, actual, previous]) =>
          [name + " (" + id + ")", fmt(actual), fmt(previous), signed(actual-previous)]))
      + '<p class="note">Missing station ID: ' + fmt(unknown[0]) + ' starts versus ' + fmt(unknown[1])
      + ' in the comparison. These trips are included in the headline.</p>';
  }
  rider.onchange = week.onchange = draw;
  document.querySelector("#station-example").onclick = () => {
    week.value = "2026-01-26"; rider.value = "all"; draw();
  };
  document.querySelector("#weekly-stations").onclick = () => {
    const index = Number(document.querySelector("#review-week").value);
    const day = new Date(Date.UTC(2022, 0, 1 + index)).toISOString().slice(0, 10);
    if (!Object.hasOwn(data.weeks,day)) {
      document.querySelector("#weekly-station-status").textContent = "This week has no station drill-down. Choose a flagged week in the supported archive.";
      return;
    }
    document.querySelector("#weekly-station-status").textContent = "";
    week.value = day;
    draw();
    document.querySelector("#bike-decision").scrollIntoView();
    week.focus({preventScroll:true});
  };
  draw();
}

function showScheduleReplay(data) {
  const date = document.querySelector("#schedule-date");
  const out = document.querySelector("#schedule-example-output");
  const result = document.querySelector("#schedule-eval-output");
  const scope = document.querySelector("#schedule-scope");
  const pref = document.querySelector("#schedule-preference");
  const intervals = new Map(JSON.parse(document.getElementById("phase-two-planner").textContent).options
    .filter(([dest]) => dest === "ATL").map(([, origin, window, ...stats]) => [origin + ":" + window, stats[5]]));
  const dates = Object.keys(data.atlanta).sort();
  date.innerHTML = optionList(dates.map(day=>[day,day]));
  date.value = dates.includes("2026-02-10") ? "2026-02-10" : dates[0];
  const pct = value => (100 * value).toFixed(1) + "%";
  function example() {
    const rows = [...data.atlanta[date.value]].sort((a,b)=>a[4]-b[4] || b[5]-a[5] || a[0].localeCompare(b[0]) || a[1]-b[1]);
    out.innerHTML = (rows.length >= 2
      ? '<p><strong>Lowest historical disruption rate:</strong> ' + plain(rows[0][0]) + ' · ' + reliabilityWindows[rows[0][1]] + '.</p>'
      : '<p>Fewer than two comparable choices that day.</p>')
      + table(["Option recorded that day", "Historical disruption rate", "Historical 95% interval", "Historical flights", "Disruptions that day", "Recorded flights that day"],
        rows.map(([origin, window, n, disrupted, risk, volume]) =>
          [origin+" · "+reliabilityWindows[window],pct(risk),intervals.get(origin+":"+window)?.map(pct).join("–") ?? "—",format.format(volume),disrupted,n]));
  }
  function evaluation() {
    const [cases, available, evaluated, different, wins, losses, planner, baseline] = data.metrics[scope.value + " / " + pref.value];
    result.innerHTML = '<p><strong>' + format.format(evaluated) + ' of ' + format.format(cases)
      + '</strong> date–destination cases supported a comparison. '
      + format.format(available) + ' had at least two recorded choices before applying historical sample requirements.</p>'
      + table(["Rule", "Average observed disruption rate"],
        [["Airport and time window",evaluated?pct(planner/evaluated):"—"],["Airport-only baseline",evaluated?pct(baseline/evaluated):"—"]])
      + '<p>Different picks in ' + format.format(different) + ' cases. The planner had a lower observed rate in '
      + format.format(wins) + ', a higher rate in ' + format.format(losses) + ', and tied in '
      + format.format(evaluated-wins-losses) + '.</p>';
  }
  date.onchange = example;
  scope.onchange = pref.onchange = evaluation;
  example();
  evaluation();
}

function showNetwork(audit) {
  const el = id => document.getElementById(id);
  const origin = el("network-origin");
  const destination = el("network-destination");
  const monthFrom = el("network-from");
  const monthTo = el("network-to");
  const codes = Object.keys(audit.airports).sort();
  const airportOptions = codes.map(code => [code, code+" · "+audit.airports[code].name]);
  origin.innerHTML = optionList(airportOptions);
  origin.value = "BWI";
  destination.innerHTML = optionList([["", "All network destinations"], ...airportOptions]);
  destination.value = "ATL";
  const yearCache = new Map();
  const getYear = year => {
    if (!yearCache.has(year)) {
      yearCache.set(year,archivedData("flight-network-"+year+".json.gz").catch(error => {
        yearCache.delete(year);
        throw error;
      }));
    }
    return yearCache.get(year);
  };
  const empty = () => ({n:0,d:0,known:0,wet:[0,0],dry:[0,0]});
  const add = (value, label, n, events) => {
    value.n += n;
    value.d += events;
    if (label in value && Array.isArray(value[label])) {
      value.known += n;
      value[label][0] += n;
      value[label][1] += events;
    }
  };
  const pct = (n,d) => d ? (100*n/d).toFixed(1)+"%" : "—";
  const plot = a => [(a.lon+126)*9.7+22,(50-a.lat)*12.8+10];
  const stationMet = value => value.known/value.n >= 0.95 && value.wet[0]>=30 && value.dry[0]>=30;
  let version = 0;
  async function draw() {
    const run = ++version;
    const from = monthFrom.value;
    const to = monthTo.value;
    const selectedOrigin = origin.value;
    const selectedDestination = destination.value;
    const output = el("network-output");
    if (from < "2022-01" || to > "2025-12" || from > to || !from || !to) {
      output.textContent = "Choose a valid month range between January 2022 and December 2025.";
      return;
    }
    if (selectedDestination === selectedOrigin) {
      output.textContent = "Choose a different destination or select all destinations.";
      return;
    }
    output.textContent = "Loading selected months…";
    try {
      const years = Array.from({length:Number(to.slice(0,4))-Number(from.slice(0,4))+1}, (_,i)=>Number(from.slice(0,4))+i);
      const monthly = await Promise.all(years.map(getYear));
      if (run !== version) return;
      const routes = new Map();
      const comparison = new Map();
      const heat = Array.from({length:5},()=>Array.from({length:7},empty));
      for (const year of monthly) {
        for (const [month, rows] of Object.entries(year)) {
          if (month < from || month > to) continue;
          for (const [o,d,w,n,late,canceled,diverted] of rows.routes) {
            if (selectedDestination && d === selectedDestination) {
              if (!comparison.has(o)) comparison.set(o,empty());
              add(comparison.get(o),w,n,late+canceled+diverted);
            }
            if (o !== selectedOrigin || (selectedDestination && d !== selectedDestination)) continue;
            if (!routes.has(d)) routes.set(d,empty());
            add(routes.get(d),w,n,late+canceled+diverted);
          }
          for (const [o,day,window,n,late,canceled,diverted] of rows.heat) {
            if (o === selectedOrigin) add(heat[window][day],"unknown",n,late+canceled+diverted);
          }
        }
      }
      const sorted = [...routes.entries()].sort((a,b)=>b[1].n-a[1].n);
      const [x,y] = plot(audit.airports[selectedOrigin]);
      const arcs = sorted.slice(0,15).map(([code,row])=>{
        const [u,v] = plot(audit.airports[code]);
        return '<line x1="'+x+'" y1="'+y+'" x2="'+u+'" y2="'+v+'" stroke="#226289" opacity=".75"><title>'
          +plain(selectedOrigin+" to "+code+" · "+format.format(row.n))+'</title></line>'
          +'<circle cx="'+u+'" cy="'+v+'" r="3" fill="#126352"/>';
      }).join("");
      output.innerHTML = '<p><strong>'+plain(selectedOrigin+' · '+from+' to '+to)+'</strong></p>'
        + (sorted.length ? '<svg class="chart" viewBox="0 0 620 350" role="img" aria-label="Selected departure routes on a map">'
          +'<path d="'+stateOutlines+'" fill="#e0eaeb" stroke="#a8bec7" stroke-width=".65"/>'+arcs
          +'<circle cx="'+x+'" cy="'+y+'" r="5" fill="#14283d"/></svg>'
          +table(["Destination","Scheduled flights","Disrupted","Observed disruption rate"],sorted.map(([d,r])=>
            [d,format.format(r.n),format.format(r.d),r.n<30?"Low volume":pct(r.d,r.n)])) : '<p>No recorded route in this selection.</p>')
        +'<h4>Departure-time heatmap · '+plain(selectedOrigin)+'</h4><p class="note">All destinations in this 23-airport network. Cells below 30 flights are muted.</p>'
        +'<div class="scroll"><table class="heatmap"><thead><tr>'+["Local time","Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(v=>'<th scope="col">'+v+'</th>').join("")+'</tr></thead><tbody>'
        +heat.map((days,i)=>'<tr><th scope="row">'+reliabilityWindows[i]+'</th>'+days.map(r=>{
          const ratio=r.n?r.d/r.n:0;
          const tone=r.n<30?"h-muted":ratio<.15?"h-low":ratio<.30?"h-mid":"h-high";
          return '<td class="'+tone+'">'+(r.n>=30?pct(r.d,r.n):"—")+'<small>'+format.format(r.n)+' flights</small></td>';
        }).join("")+'</tr>').join("")+'</tbody></table></div>';
      if (selectedDestination && comparison.size) {
        const rows = [...comparison.entries()].sort();
        const supported = rows.filter(([,r])=>stationMet(r));
        const dry = supported.reduce((sum,[,r])=>sum+r.dry[0],0);
        const wet = supported.reduce((sum,[,r])=>sum+r.wet[0],0);
        output.innerHTML += '<h4>Weather-standardized disruption rates to '+plain(selectedDestination)+'</h4>'
          + table(["Origin", "Observed", "Weather matched", "Weather-standardized"],rows.map(([o,r])=>
            [o,r.n<30?"Low volume":pct(r.d,r.n),pct(r.known,r.n),supported.length>=2&&stationMet(r)
              ? pct((dry*r.dry[1]/r.dry[0]+wet*r.wet[1]/r.wet[0]),dry+wet) : "Insufficient comparable weather"]))
          +'<p class="note">Standardization applies one pooled dry/wet mix to supported origins. It requires 95% station coverage and at least 30 flights in each weather group per origin and period. This is a historical comparison.</p>';
      }
    } catch (error) {
      if (run === version) output.textContent = "Could not load the selected months. Change a filter to retry.";
    }
  }
  for (const control of [origin,destination,monthFrom,monthTo]) control.onchange = draw;
  draw();
}

const reportError = (selector, text) => { document.querySelector(selector).textContent = text; };
archivedData("bike-expansion.json").then(showStationReview)
  .catch(() => reportError("#station-results","Station data could not load. Try reloading the page."));
archivedData("flight-replay-summary.json").then(showScheduleReplay)
  .catch(() => reportError("#schedule-example-output","The schedule replay could not load. Try reloading the page."));
archivedData("flight-network-audit.json").then(showNetwork)
  .catch(() => reportError("#network-output","Flight network metadata could not load. Try reloading the page."));
