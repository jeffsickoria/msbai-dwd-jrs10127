function renderWeeklyReview(exportRows) {
  const section = document.getElementById("bike-weekly");
  const weekControl = section.querySelector("#review-week");
  const direction = (actual, lower, upper) => actual < lower ? -1 : actual > upper ? 1 : 0;
  const isoDay = day => new Date(Date.UTC(2022, 0, 1 + day)).toISOString().slice(0, 10);
  const monday = day => day - ((day + 5) % 7);
  const point = (day, counts) => {
    const [actual, expected, lower, upper] = counts;
    return {day, actual, expected, flag: direction(actual, lower, upper)};
  };
  function groupWeeks(rows) {
    const weeks = new Map();
    for (const row of rows) {
      const week = monday(row.day);
      if (!weeks.has(week)) weeks.set(week, []);
      weeks.get(week).push(row);
    }
    return weeks;
  }
  function episodes(rows) {
    const runs = [];
    for (const row of rows) {
      if (!row.flag) continue;
      const previous = runs.at(-1);
      if (previous && previous.at(-1).day + 1 === row.day && previous[0].flag === row.flag) {
        previous.push(row);
      } else {
        runs.push([row]);
      }
    }
    return runs;
  }
  const points = exportRows.map(([day, ...counts]) => ({
    ...point(day, counts),
    member: point(day, counts.slice(4, 8)),
    casual: point(day, counts.slice(8, 12)),
  }));
  const weeks = groupWeeks(points);
  const example = [...weeks.entries()].reverse().find(([, rows]) =>
    rows.length === 7 && episodes(rows).some(run => run.length >= 2))[0];
  weekControl.innerHTML = optionList([...weeks.entries()].reverse().map(([week, rows]) =>
    [week, isoDay(week) + " · " + rows.filter(row => row.flag).length + " flagged"]));
  weekControl.value = String(example);

  const number = value => format.format(Math.round(value));
  const signed = value => (Math.round(value) > 0 ? "+" : "") + number(value);
  const delta = row => row.actual - row.expected;
  const flagName = value => value < 0 ? "Below range" : value > 0 ? "Above range" : "In range";
  const output = section.querySelector("#review-results");
  const download = section.querySelector("#review-download");
  function draw() {
    const week = Number(weekControl.value);
    const rows = weeks.get(week);
    const runs = episodes(rows);
    const long = runs.filter(run => run.length >= 2);
    const flagged = runs.flat();
    const label = (count, name) => count + " " + name + (count === 1 ? "" : "s");
    output.innerHTML = '<p><strong>' + label(flagged.length, "flagged day") + '</strong> · ' + label(long.length, "sustained run")
      + ' · ' + label(runs.length - long.length, "isolated flag") + ' · '
      + rows.length + '/7 dates observed</p>'
      + (runs.length ? table(["Dates", "Pattern", "Direction", "Total gap", "Member gap", "Casual gap", "Larger same-direction gap"],
        runs.map(run => {
          const sum = group => run.reduce((total, row) => total + delta(group ? row[group] : row), 0);
          const member = sum("member");
          const casual = sum("casual");
          const sign = run[0].flag;
          const driver = Math.max(member * sign, casual * sign) <= 0 ? "—"
            : member === casual ? "Equal" : member * sign > casual * sign ? "Members" : "Casual riders";
          return [isoDay(run[0].day) + (run.length > 1 ? " to " + isoDay(run.at(-1).day) : ""),
            run.length > 1 ? "Sustained" : "Isolated", flagName(sign), signed(sum()), signed(member), signed(casual), driver];
        })) : '<p>No flagged days in this week.</p>')
      + '<details><summary>See each day</summary>'
      + table(["Date", "Observed", "Expected", "Difference", "Status"],
        rows.map(row => [isoDay(row.day), number(row.actual), number(row.expected), signed(delta(row)), flagName(row.flag)])) + '</details>';
    download.disabled = flagged.length === 0;
    download.onclick = () => {
      const csv = [["date", "pattern", "direction", "observed", "expected", "difference", "member_difference", "casual_difference"],
        ...runs.flatMap(run => run.map(row => [isoDay(row.day), run.length > 1 ? "sustained" : "isolated", flagName(row.flag),
          row.actual, row.expected, delta(row).toFixed(1), delta(row.member).toFixed(1), delta(row.casual).toFixed(1)]))]
        .map(row => row.join(",")).join("\r\n") + "\r\n";
      const url = URL.createObjectURL(new Blob([csv], {type:"text/csv;charset=utf-8"}));
      const link = document.createElement("a");
      link.href = url;
      link.download = "citibike-flagged-" + isoDay(week) + ".csv";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    };
  }
  section.querySelector("#review-example").onclick = () => {
    weekControl.value = String(example);
    draw();
  };
  weekControl.onchange = draw;
  draw();

  // Evaluate the run rule on alerts made with data available before each date.
  const actualByDay = new Map(points.map(row => [row.day, row.actual]));
  const replay = points.flatMap(row => {
    const comparable = Array.from({length:12}, (_, i) => actualByDay.get(row.day - (i + 1) * 7))
      .filter(value => value !== undefined).sort((a,b) => a-b);
    if (comparable.length < 10 || !isoDay(row.day).startsWith("2025")) return [];
    return [{day:row.day, flag:direction(row.actual, comparable[1], comparable.at(-2))}];
  });
  const audited = [...groupWeeks(replay).values()].filter(rows => rows.length === 7);
  const runCounts = audited.map(rows => episodes(rows));
  const reviewAny = runCounts.filter(runs => runs.length > 0).length;
  const reviewSustained = runCounts.filter(runs => runs.some(run => run.length >= 2)).length;
  section.querySelector("#review-backtest").innerHTML = table(["Review rule", "Weeks triggering review"],
    [["Any flagged day", reviewAny + " / " + audited.length],
      ["Two consecutive same-direction flags", reviewSustained + " / " + audited.length]]);
}
