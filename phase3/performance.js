function showPerformance(data) {
  const bike = document.getElementById("bike-performance");
  const select = bike.querySelector("#replay-week");
  const summary = bike.querySelector("#replay-summary");
  const detail = bike.querySelector("#replay-detail");
  const nextDay = bike.querySelector("#replay-day");
  const nextWeek = bike.querySelector("#replay-next-week");
  const follow = bike.querySelector("#replay-follow");
  const weeks = data.bike;
  const flags = weeks.flatMap(([, rows]) => rows.filter(row => row[4]));
  const runs = weeks.flatMap(([, rows]) => rows.map((row, i) => {
    const direction = row[4];
    return direction && rows[i - 1]?.[4] !== direction
      && rows[i + 1]?.[4] !== direction ? row : null;
  }).filter(Boolean));
  const baselineWeeks = weeks.filter(([, rows]) => rows.some(row => row[4])).length;
  const ruleWeeks = weeks.filter(([, rows]) => rows.some(row => row[5])).length;
  const runCount = weeks.reduce((sum, [, rows]) => sum + rows.filter((row, i) =>
    row[5] && !rows[i-1]?.[5]).length, 0);
  summary.innerHTML = table(["Season measure", "Review any flag", "Review after two same-direction flags"], [
    ["Weeks sent for review", baselineWeeks + " / " + weeks.length, ruleWeeks + " / " + weeks.length],
    ["Daily signals or run starts per week", (flags.length / weeks.length).toFixed(2), (runCount / weeks.length).toFixed(2)],
    ["Time to flag a sustained within-week run", "First day", "Second day"],
    ["Isolated within-week flags that triggered a review signal", runs.length, 0],
  ]) + '<p class="note">' + flags.length + ' daily flags across ' + runCount + ' sustained runs and '
    + runs.length + ' isolated flags. Of the isolated flags, ' + runs.filter(row => row[6] >= 2).length
    + ' had at least two more same-direction flags in the next seven days. An isolated flag here is defined within one week.</p>';

  select.innerHTML = optionList(weeks.map(([week], i) => [i, week]));
  select.value = "0";
  let visibleDays = 1;
  let showFollow = false;
  function drawWeek() {
    const [, rows] = weeks[Number(select.value)];
    const visible = rows.slice(0, visibleDays);
    const firstBaseline = visible.find(row => row[4]);
    const firstRule = visible.find(row => row[5]);
    detail.innerHTML = '<p><strong>Review opened:</strong> Single-flag rule '
      + (firstBaseline?.[0] ?? "pending") + ' · two-flag rule ' + (firstRule?.[0] ?? "pending") + '.</p>'
      + table(["Date", "Trips", "Prior-weekday range", "Flag", "Two-day rule reached", ...(showFollow ? ["Same-direction flags in next 7 days"] : [])],
        visible.map(([day, actual, low, high, flag, alert, future]) => [
          day, format.format(actual), format.format(low) + "–" + format.format(high),
          flag < 0 ? "Below" : flag > 0 ? "Above" : "—", alert ? "Yes" : "—",
          ...(showFollow ? [future ?? "—"] : []),
        ]));
    nextDay.disabled = visibleDays === 7;
    follow.disabled = visibleDays !== 7 || showFollow;
    nextWeek.disabled = Number(select.value) === weeks.length - 1;
  }
  function reset() { visibleDays = 1; showFollow = false; drawWeek(); }
  nextDay.onclick = () => { visibleDays++; drawWeek(); };
  follow.onclick = () => { showFollow = true; drawWeek(); };
  nextWeek.onclick = () => { select.value = String(Number(select.value) + 1); reset(); };
  select.onchange = reset;
  drawWeek();

  const flight = document.getElementById("planner-performance");
  const scope = flight.querySelector("#performance-scope");
  const destination = flight.querySelector("#performance-destination");
  const out = flight.querySelector("#ranking-summary");
  const demo = flight.querySelector("#ranking-example");
  const pct = value => (value * 100).toFixed(1) + "%";
  const rate = row => row[3] / row[2];
  destination.innerHTML = optionList([["", "All destinations"], ...[...new Set(data.flights.cases.map(row => row[0]))]
    .sort().map(code => [code,code])]);
  const windows = ["00:00–05:59", "06:00–09:59", "10:00–13:59", "14:00–17:59", "18:00–23:59"];
  const option = row => row[0] + " · " + windows[row[1]];
  function drawFlights() {
    const selected = data.flights.cases.filter(row => row[2] === scope.value && (!destination.value || row[0] === destination.value));
    const evaluated = selected.filter(row => row[3] === "Evaluated");
    const trained = selected.filter(row => row[4]).length;
    const pairs = evaluated.map(row => row.slice(4));
    const count = pairs.length;
    const mean = i => pairs.reduce((sum, pair) => sum + rate(pair[i]), 0) / count;
    const wins = pairs.filter(([a,b]) => a[3] * b[2] < b[3] * a[2]).length;
    const losses = pairs.filter(([a,b]) => a[3] * b[2] > b[3] * a[2]).length;
    const same = pairs.filter(([a,b]) => option(a) === option(b)).length;
    const delta = count ? (mean(0) - mean(1)) * 100 : null;
    out.innerHTML = '<p><strong>' + count + ' of ' + selected.length + ' destination-month cases evaluated.</strong> '
      + (selected.length-trained) + ' lacked training choices; ' + (trained-count) + ' lacked 2025 volume.</p>'
      + (count ? table(["Rule", "Average observed disruption rate", "Observed flights across selected options"],
        [["Planner: destination × airport × window", pct(mean(0)), format.format(pairs.reduce((s,r)=>s+r[0][2],0))],
         ["Baseline: destination × airport", pct(mean(1)), format.format(pairs.reduce((s,r)=>s+r[1][2],0))]])
        + '<p>Planner minus baseline: <strong>' + (delta > 0 ? "+" : "") + delta.toFixed(2)
        + ' percentage points</strong>. Planner had a lower rate in ' + wins + ', a higher rate in '
        + losses + ', and tied in ' + (count-wins-losses) + ' cases. Both rules picked the same option in ' + same + ' cases.</p>'
        : '<p>No cases met the evaluation requirements.</p>');
    const january = evaluated.filter(row => row[1] === "2025-01");
    const example = january.find(row => row[0] === (destination.value || "ATL")) ?? january[0];
    demo.innerHTML = example?.[3] === "Evaluated"
      ? '<p><strong>' + example[0] + ' · January 2025</strong></p>'
        + table(["Rule", "Option chosen before 2025", "2025 disrupted / flights", "Observed rate"],
          example.slice(4).map((row,i) => [i ? "Baseline" : "Planner", option(row),
            format.format(row[3]) + " / " + format.format(row[2]), pct(rate(row))]))
      : '<p>The January example lacks enough observations for this selection.</p>';
  }
  scope.onchange = destination.onchange = drawFlights;
  drawFlights();
}
