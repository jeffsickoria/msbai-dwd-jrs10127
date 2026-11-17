"""Build the 23-airport route explorer and a post-2025 schedule replay."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
import csv
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase1"))
from build_flight_phase1 import station_days, weather_label

FIELDS = ["FlightDate", "Origin", "Dest", "CRSDepTime", "DepDelay", "Cancelled", "Diverted"]
REGIONAL = {"BWI", "DCA", "IAD"}
PREFERENCES = {"Any time": set(range(5)), "Morning": {1}, "Evening": {4}, "Morning or evening": {1, 4}}


def read(path, month, codes):
    with path.open("rb") as source:
        sha = hashlib.file_digest(source, "sha256").hexdigest()
    with ZipFile(path) as archive:
        member, = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        with archive.open(member) as source:
            raw = pd.read_csv(source, usecols=FIELDS)
    if not raw.FlightDate.str.startswith(month).all():
        raise ValueError(f"Unexpected date in {path}")
    frame = raw.loc[raw.Origin.isin(codes) & raw.Dest.isin(codes) & raw.Origin.ne(raw.Dest)].copy()
    local = frame.CRSDepTime
    hour = (local // 100).replace(24, 0)
    frame["window"] = pd.cut(hour, [-1, 5, 9, 13, 17, 23], labels=False)
    valid = (local.mod(100).between(0, 59) & (local.lt(2400) | local.eq(2400))
             & frame.window.notna() & frame.Cancelled.isin([0, 1]) & frame.Diverted.isin([0, 1])
             & (frame.Cancelled.eq(1) | frame.Diverted.eq(1) | frame.DepDelay.notna()))
    excluded = int((~valid).sum())
    frame = frame.loc[valid].rename(columns={"FlightDate":"day","Origin":"origin","Dest":"destination"})
    frame["cancel"] = frame.Cancelled.eq(1)
    frame["divert"] = ~frame.cancel & frame.Diverted.eq(1)
    frame["late"] = ~(frame.cancel | frame.divert) & frame.DepDelay.ge(15)
    groups = frame.groupby(["day","origin","destination","window"], observed=True).agg(
        n=("late","size"), late=("late","sum"), cancel=("cancel","sum"), divert=("divert","sum")).reset_index()
    if int(groups.n.sum()) != len(frame):
        raise ValueError(f"Failed row reconciliation in {path}")
    return groups, [month, len(raw), sha, int(groups.n.sum()), excluded]


def count_groups(frame, group):
    columns = ["n", "late", "cancel", "divert"]
    return frame.groupby(group, observed=True)[columns].sum().reset_index().values.tolist()


def validate_weather(airports, directory):
    weather = {}
    for code, airport in airports.items():
        path = directory / f"{airport.get('station', '')}.csv.gz"
        if path.is_file():
            # GHCN station data can contain revisions on dates outside the study.
            weather[code] = {day: weather_label(row) for day, row in station_days(path).items()
                             if "2022-01-01" <= day <= "2025-12-31"}
            airport["weather_days"] = sum(label != "unknown" for label in weather[code].values())
    return weather


def replay(training, holdout, output):
    # All ranks are derived from the 36 training months, before outcomes are scored.
    records = defaultdict(list)
    for month, origin, dest, window, n, late, cancel, divert in training:
        records[dest, origin, window].append((n, late + cancel + divert))
    airport_totals = defaultdict(lambda: [0, 0])
    eligible = {}
    for (dest, origin, window), entries in records.items():
        n = sum(row[0] for row in entries)
        disrupted = sum(row[1] for row in entries)
        airport_totals[dest, origin][0] += n
        airport_totals[dest, origin][1] += disrupted
        if n >= 100 and len(entries) >= 12:
            eligible[dest, origin, window] = (n, Fraction(disrupted, n))
    results = {}
    records = {}
    groups = holdout.groupby(["day","destination"], sort=True)
    for (day, dest), rows in groups:
        observed = {(r.origin,r.window): (int(r.n),int(r.late+r.cancel+r.divert)) for r in rows.itertuples()}
        for scope in ("Capital Region", "All origins"):
            for pref, windows in PREFERENCES.items():
                available = [(o,w) for o,w in observed if w in windows and (scope != "Capital Region" or o in REGIONAL)]
                ranked = [(o,w) for o,w in available if (dest,o,w) in eligible]
                label = scope + " / " + pref
                stats = results.setdefault(label, [0,0,0,0,0,0,0.0,0.0])
                stats[0] += 1
                stats[1] += len(available) >= 2
                stats[2] += len(ranked) >= 2
                if dest == "ATL" and scope == "Capital Region" and pref == "Morning or evening":
                    records[day] = [[o,w,*observed[o,w],float(eligible[dest,o,w][1]),eligible[dest,o,w][0]]
                                    for o,w in ranked]
                if len(ranked) < 2:
                    continue
                def sort_key(option, planner):
                    o,w = option
                    volume, rate = eligible[dest,o,w]
                    if not planner:
                        n, d = airport_totals[dest,o]
                        rate = Fraction(d,n)
                    return rate, -volume, o, w
                a = min(ranked, key=lambda option: sort_key(option,True))
                b = min(ranked, key=lambda option: sort_key(option,False))
                an, ad = observed[a]
                bn, bd = observed[b]
                stats[3] += a != b
                stats[4] += ad * bn < bd * an
                stats[5] += ad * bn > bd * an
                stats[6] += ad/an
                stats[7] += bd/bn
                yield [scope,pref,day,dest,len(available),len(ranked),a[0],a[1],an,ad,b[0],b[1],bn,bd]
    (output/"flight-replay-summary.json").write_text(json.dumps({"metrics":results,"atlanta":records},separators=(",",":"))+"\n")


def main(inputs, fresh, weather_dir, evidence_path, output):
    output.mkdir(exist_ok=True)
    airports = json.loads((weather_dir/"airports.json").read_text())
    weather = validate_weather(airports, weather_dir)
    evidence = json.loads(evidence_path.read_text())
    periods = evidence["sourceMonths"]
    if len(periods) != 48:
        raise ValueError("Expected 48 verified training and descriptive archives")
    training = []
    audits = []
    yearly = {}
    with ThreadPoolExecutor(max_workers=4) as workers:
        for result, (month, count, _, sha) in zip(
            workers.map(lambda row: read(inputs / f"{row[0]}.zip", row[0], set(airports)), periods), periods
        ):
            frame, audit = result
            if (audit[0],audit[1],audit[2]) != (month,count,sha):
                raise ValueError(f"Source manifest mismatch for {month}")
            audits.append(audit)
            frame["weekday"] = pd.to_datetime(frame.day).dt.dayofweek
            frame["weather"] = [weather.get(origin,{}).get(day,"unknown") for day,origin in zip(frame.day,frame.origin)]
            route = count_groups(frame, ["origin","destination","weather"])
            heat = count_groups(frame, ["origin","weekday","window"])
            if sum(r[3] for r in route) != audit[3] or sum(r[3] for r in heat) != audit[3]:
                raise ValueError(f"Route and heatmap mismatch for {month}")
            yearly.setdefault(month[:4], {})[month] = {"routes":route,"heat":heat}
            if month < "2025":
                training.extend([month, *row] for row in count_groups(frame,["origin","destination","window"]))
            print(month, audit[3], flush=True)
        dates = [f"2026-{month:02}" for month in range(1,7)]
        holdout = []
        for frame, audit in workers.map(lambda month: read(fresh / f"{month}.zip", month, set(airports)), dates):
            holdout.append(frame)
            audits.append(audit)
            print(audit[0], audit[3], flush=True)
    for year, monthly in yearly.items():
        (output/f"flight-network-{year}.json").write_text(json.dumps(monthly,separators=(",",":"))+"\n")
    coverage = defaultdict(lambda: [0,0])
    for monthly in yearly.values():
        for month in monthly.values():
            for origin, _, label, n, *_ in month["routes"]:
                coverage[origin][0] += n
                coverage[origin][1] += n * (label != "unknown")
    (output/"flight-network-audit.json").write_text(json.dumps(
        {"airports":airports,"monthly_sources":audits,"weather_coverage":coverage},
        separators=(",",":"))+"\n")
    with (output/"flight-schedule-replay.csv").open("w",newline="") as file:
        writer=csv.writer(file)
        writer.writerow(["scope","preference","date","destination","recorded_options","rankable_options",
                         "planner_origin","planner_window","planner_flights","planner_disrupted",
                         "baseline_origin","baseline_window","baseline_flights","baseline_disrupted"])
        writer.writerows(replay(training,pd.concat(holdout,ignore_index=True),output))


if __name__ == "__main__":
    main(*map(Path,sys.argv[1:]))
