"""Reconcile source start months and publish station breakdowns for flagged weeks."""
from collections import Counter, defaultdict
from datetime import date, timedelta
import csv
import json
from pathlib import Path
import re
import sys

DAYS = timedelta(days=1)
SERIES = ["member", "casual", "other"]


def main(directory, html_path, output):
    daily = defaultdict(Counter)
    months = defaultdict(Counter)
    names = {}
    audits = []
    missing = defaultdict(Counter)
    dates = [f"{year}{month:02}" for year in [2024, 2025] for month in range(1, 13)] + ["202601"]
    for period in dates:
        bundle = json.loads((directory/f"{period}.json").read_text())
        if bundle["source"] != period:
            raise ValueError(f"Unexpected source identity for {period}")
        if sum(record[3] for record in bundle["counts"]) != bundle["rows"]:
            raise ValueError(f"Reconciliation failed for {period}")
        start_months = Counter()
        absent = 0
        nominal = date(int(period[:4]),int(period[4:]),1)
        following = (nominal + 32 * DAYS).replace(day=1)
        for day, station, rider, n in bundle["counts"]:
            dt = date.fromisoformat(day)
            if not nominal - 4 * DAYS <= dt < following:
                raise ValueError(f"Unexpected source boundary {period} {day}")
            months[day[:7]][rider] += n
            start_months[day[:7]] += n
            if not station:
                missing[day[:7]][rider] += n
                absent += n
            daily[dt][(station,rider)] += n
        for station, label in bundle["names"].items():
            names[station] = max(names.get(station, ["",""]), label)
        audits.append([period,bundle["sha256"],bundle["csv_files"],bundle["rows"],dict(start_months),absent])
    expected = {date(2024,1,1) + offset * DAYS for offset in range((date(2026,2,1)-date(2024,1,1)).days)}
    if not expected.issubset(daily):
        raise ValueError("At least one expected trip-start date is missing")
    months_out = [[month,[sum(counter.values()),*[counter[key] for key in SERIES]]]
                  for month,counter in sorted(months.items()) if "2024-01" <= month <= "2025-12"]
    if len(months_out) != 24:
        raise ValueError("Missing months")

    page = html_path.read_text()
    model = json.loads(re.search(r'id="citibike-daily-data" type="application/json">(.*?)</script>',page).group(1))
    flags = defaultdict(list)
    daily_audit = defaultdict(Counter)
    for offset, observed, expected_trips, low, high, *_ in model:
        day = date(2022,1,1) + offset * DAYS
        if day in expected:
            archived = sum(daily[day].values())
            month = day.isoformat()[:7]
            daily_audit[month].update({"archive_count":archived,"model_count":observed,
                                       "days":1,"days_matching_model":int(archived==observed)})
        if observed < low or observed > high:
            monday = day - day.weekday() * DAYS
            flags[monday].append(day)

    weeks = {}
    with (output/"bike-station-breakdown.csv").open("w",newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["week_start","flagged_dates","rider","station_id","station_name","starts","matching_weekday_expected","difference"])
        for monday, flag_days in flags.items():
            # Every flagged date and its matched weekdays must belong to the new archive.
            reference = [day - 7 * days * DAYS for day in flag_days for days in range(1,5)]
            if not all(day in expected for day in [*flag_days,*reference]):
                continue
            observed = sum((daily[day] for day in flag_days),Counter())
            baseline = sum((daily[day] for day in reference),Counter())
            key = monday.isoformat()
            targets = [day.isoformat() for day in flag_days]
            groups = {}
            for rider in ("all","member","casual"):
                values = defaultdict(lambda:[0,0])
                for index,counts in enumerate([observed,baseline]):
                    for (station,group),n in counts.items():
                        if rider == "all" or rider == group:
                            values[station][index] += n
                total = [sum(row[i] for row in values.values()) for i in range(2)]
                unlabeled = values.pop("",[0,0])
                ranked = sorted(values.items(),key=lambda row:(row[1][0]*4-row[1][1],row[0]))
                loss = [(station,row) for station,row in ranked if row[0]*4 < row[1]][:12]
                gain = [(station,row) for station,row in reversed(ranked) if row[0]*4 > row[1]][:12]
                selected = []
                for station, (actual, prior) in [*loss,*gain]:
                    label = names.get(station,["",station])[1]
                    selected.append([station,label,actual,prior/4])
                    writer.writerow([key," ".join(targets),rider,station,("'" + label if label.startswith(("=", "+", "-", "@", "\t", "\r")) else label),actual,prior/4,actual-prior/4])
                groups[rider] = {"total":[total[0],total[1]/4],"unknown":[unlabeled[0],unlabeled[1]/4],"stations":selected}
            weeks[key] = {"dates":targets,"groups":groups}

    if "2026-01-26" not in weeks:
        raise ValueError("Worked decision is missing")
    data = {"months":months_out,"weeks":weeks}
    (output/"bike-expansion.json").write_text(json.dumps(data,separators=(",",":"))+"\n")
    (output/"bike-archive-audit.json").write_text(json.dumps(
        {"columns":["source_month","sha256","csv_members","raw_trip_records","trip_start_month_counts","missing_station_id"],
         "files":audits,"missing_station_by_start_month":missing,"daily_model_reconciliation":daily_audit},
        separators=(",",":"))+"\n")
    print("Monthly trips",sum(r[1][0] for r in months_out),"station weeks",len(weeks),flush=True)


if __name__ == "__main__":
    main(*map(Path,sys.argv[1:]))
