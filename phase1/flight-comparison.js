function showFlightPhaseOne(data) {
  const comparison = document.getElementById("flight-comparison");
  const rows = data.routes;
  const destinations = [...new Set(rows.map(row => row[0]))].sort();
  const windows = ["00:00–05:59", "06:00–09:59", "10:00–13:59", "14:00–17:59", "18:00–23:59"];
  const destination = comparison.querySelector("#compare-destination");
  const dimension = comparison.querySelector("#compare-dimension");
  const sameAirport = comparison.querySelector("#compare-origin");
  const a = comparison.querySelector("#compare-a");
  const b = comparison.querySelector("#compare-b");
  const output = comparison.querySelector("#compare-results");
  destination.innerHTML = optionList(destinations.map(code => [code, code]));
  destination.value = destinations.includes("ATL") ? "ATL" : destinations[0];
  const airportLabel = sameAirport.parentElement;

  function cohort() {
    return rows.filter(row => row[0] === destination.value
      && (dimension.value === "1" || row[1] === sameAirport.value));
  }

  function draw() {
    const selected = cohort();
    if (!a.value || !b.value || a.value === b.value) {
      output.textContent = "Select two distinct options. Some airports have only one carrier or window for this destination.";
      return;
    }
    function totals(value) {
      const counts = {all: [0, 0], dry: [0, 0], wet: [0, 0], unknown: [0, 0]};
      for (const row of selected) {
        if (String(row[Number(dimension.value)]) !== value) continue;
        const [, , , , weather, count, delayed] = row;
        counts.all[0] += count;
        counts.all[1] += delayed;
        counts[weather][0] += count;
        counts[weather][1] += delayed;
      }
      return counts;
    }
    const left = totals(a.value);
    const right = totals(b.value);
    const weather = ["dry", "wet"];
    const supported = [left, right].every(option =>
      option.all[0] >= 100 && weather.every(kind => option[kind][0] >= 30));
    const pooled = weather.map(kind => left[kind][0] + right[kind][0]);
    const weights = pooled.map(count => count / (pooled[0] + pooled[1]));
    const adjusted = option => weather.reduce((sum, kind, i) =>
      sum + weights[i] * option[kind][1] / option[kind][0], 0);
    output.innerHTML = table(
      ["Option", "Eligible flights", "Observed delayed", "Dry / wet flights", "Weather-standardized delayed"],
      [[a, left], [b, right]].map(([control, n]) => [
        control.selectedOptions[0].textContent, format.format(n.all[0]), rateLabel(n.all[1], n.all[0]),
        format.format(n.dry[0]) + " / " + format.format(n.wet[0]), supported ? rateLabel(adjusted(n), 1) : "Insufficient sample",
      ]),
    ) + '<p class="note">' + (supported
      ? "Both standardized rates use the same pooled mix of dry and wet days. Flights with missing weather are included only in the observed rates."
      : "Weather standardization needs at least 100 eligible flights and 30 flights in each weather category per option.")
      + " Carrier refers to the reporting operator. Historical rates describe completed flights; schedules and other differences can affect comparisons.</p>";
  }

  function choices() {
    airportLabel.hidden = dimension.value === "1";
    const priorOrigin = sameAirport.value;
    const available = [...new Set(rows.filter(row => row[0] === destination.value).map(row => row[1]))].sort();
    sameAirport.innerHTML = optionList(available.map(origin => [origin, origin]));
    if (available.includes(priorOrigin)) sameAirport.value = priorOrigin;
    const key = Number(dimension.value);
    const values = [...new Set(cohort().map(row => String(row[key])))].sort();
    const options = optionList(values.map(value => [value, key === 3 ? windows[Number(value)] : value]));
    const previousA = a.value;
    const previousB = b.value;
    a.innerHTML = options;
    b.innerHTML = options;
    if (values.includes(previousA)) a.value = previousA;
    b.value = values.includes(previousB) && previousB !== a.value
      ? previousB : values.find(value => value !== a.value) ?? "";
    draw();
  }
  for (const control of [destination, dimension, sameAirport]) control.addEventListener("change", choices);
  for (const control of [a, b]) control.addEventListener("change", draw);
  choices();

  const evaluation = data.evaluation;
  const result = document.getElementById("holdout-results");
  const score = value => value.toFixed(5);
  const delta = evaluation.weatherBrier - evaluation.baselineBrier;
  result.innerHTML = '<p><strong>' + format.format(evaluation.scoredFlights) + '</strong> of '
    + format.format(evaluation.allHoldoutFlights) + ' eligible 2025 flights had complete weather and were scored by both models.</p>'
    + table(["Model", "2025 Brier score"], [
      ["Historical flight characteristics", score(evaluation.baselineBrier)],
      ["Historical characteristics plus weather", score(evaluation.weatherBrier)],
    ])
    + '<p>Adding daily weather ' + (delta < 0 ? "lowered" : delta > 0 ? "raised" : "did not change")
    + (delta === 0 ? " the Brier score." : " the Brier score by " + score(Math.abs(delta)) + ".")
    + ' Lower scores indicate more accurate probabilities. This is an evaluation with observed departure-day weather; a prospective planner would need forecasts.</p>';
}
