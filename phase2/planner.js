function renderTripPlanner(data) {
  const section = document.getElementById("trip-planner");
  const destination = section.querySelector("#planner-destination");
  const windows = section.querySelector("#planner-windows");
  const output = section.querySelector("#planner-results");
  const labels = ["00:00–05:59", "06:00–09:59", "10:00–13:59", "14:00–17:59", "18:00–23:59"];
  const choices = [...new Set(data.options.map(row => row[0]))].sort();
  destination.innerHTML = optionList(choices.map(code => [code, code]));
  windows.innerHTML = labels.map((label, index) => '<label><input type="checkbox" value="' + index
    + '" checked> ' + label + '</label>').join("");
  const controls = [...windows.querySelectorAll("input")];
  const pct = probability => (100 * probability).toFixed(1) + "%";

  function draw() {
    const allowed = new Set(controls.filter(input => input.checked).map(input => Number(input.value)));
    if (!allowed.size) {
      output.textContent = "Select at least one acceptable departure window.";
      return;
    }
    const rows = data.options.filter(row => row[0] === destination.value && allowed.has(row[2]));
    const supported = rows.filter(row => row[8] !== null).sort((a,b) =>
      (a[4] + a[5] + a[6]) / a[3] - (b[4] + b[5] + b[6]) / b[3] || b[3] - a[3]);
    if (!rows.length) {
      output.textContent = "No recorded departures in these windows.";
      return;
    }
    output.innerHTML = (supported.length ? '<p><strong>Lowest observed risk:</strong> ' + supported[0][1]
      + ' · ' + labels[supported[0][2]] + '. Intervals may overlap.</p>'
      : '<p>These windows have too little history to rank.</p>')
      + table(["Airport and local time", "Disruption rate", "95% interval", "Scheduled flights", "Observed months", "Late / canceled / diverted"],
        [...supported, ...rows.filter(row => row[8] === null)].map(([, origin, window, n, late, canceled, diverted, months, interval]) => [
          origin + " · " + labels[window], interval ? pct((late+canceled+diverted)/n) : "Insufficient sample",
          interval ? interval.map(pct).join("–") : "—", format.format(n), months + " / 36",
          [late,canceled,diverted].map(value=>format.format(value)).join(" / "),
        ]));
  }
  function example() {
    destination.value = "ATL";
    controls.forEach(input => input.checked = ["1","4"].includes(input.value));
    draw();
  }
  destination.onchange = draw;
  controls.forEach(input => input.onchange = draw);
  section.querySelector("#planner-example").onclick = example;
  example();
}
