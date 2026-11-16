"""Freeze flight choices before reading 2025 outcomes and replay Citi Bike alerts."""
from collections import defaultdict
import csv
from datetime import date, timedelta
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase2"))
from build_planner import month_summary

WINDOWS = ["00:00–05:59", "06:00–09:59", "10:00–13:59", "14:00–17:59", "18:00–23:59"]
SCOPES = {"Any time": range(5), "Morning only": [1], "Evening only": [4]}
DAYS = timedelta(days=1)


def freeze(training):
    options, airport = defaultdict(list), defaultdict(list)
    for month, destination, origin, window, n, late, cancel, divert in training["monthly"]:
        options[destination, origin, window].append((n, late + cancel + divert))
        airport[destination, origin].append((n, late + cancel + divert))

    def stats(rows):
        return sum(n for n, _ in rows), sum(d for _, d in rows)

    airports = {key: stats(rows) for key, rows in airport.items()}
    choices = defaultdict(list)
    for (destination, origin, window), rows in sorted(options.items()):
        n, disruptions = stats(rows)
        if n >= 100 and len(rows) >= 12:
            pooled_n, pooled_disruptions = airports[destination, origin]
            choices[destination].append((origin, window, n, Fraction(disruptions, n),
                                         Fraction(pooled_disruptions, pooled_n)))
    decisions = {}
    for destination in sorted({key[0] for key in options}):
        decisions[destination] = {}
        for scope, windows in SCOPES.items():
            eligible = [row for row in choices.get(destination, []) if row[1] in windows]
            if len(eligible) < 2:
                decisions[destination][scope] = None
                continue
            def pick(score):
                origin, window, _, _, _ = min(eligible, key=lambda row: (row[score], -row[2], row[0], row[1]))
                return [origin, int(window)]
            decisions[destination][scope] = [pick(3), pick(4)]
    return decisions


def evaluate_flights(root, evidence, decisions):
    audit = []
    cases = []
    for month, expected_rows, _, expected_hash in evidence["sourceMonths"]:
        if not month.startswith("2025-"):
            continue
        path = root / f"{month}.zip"
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != expected_hash:
                raise ValueError(f"Archive hash changed for {month}")
        rows, unknown, count = month_summary(path, month, set(decisions))
        if count != expected_rows:
            raise ValueError(f"Archive row count changed for {month}")
        totals = {(dest, origin, window): [n, late + cancel + divert]
                  for dest, origin, window, n, late, cancel, divert in rows}
        audit.append([month, count, sum(row[0] for row in totals.values()), unknown])
        for dest, scopes in decisions.items():
            for scope, choice in scopes.items():
                if choice is None:
                    cases.append([dest, month, scope, "Limited training choices", None, None])
                    continue
                selected = [[origin, window, *totals.get((dest, origin, window), [0, 0])]
                            for origin, window in choice]
                status = "Evaluated" if min(row[2] for row in selected) >= 30 else "Limited 2025 observations"
                cases.append([dest, month, scope, status, *selected])
        print(month, audit[-1], flush=True)
    if len(audit) != 12:
        raise ValueError("The 2025 holdout requires all twelve months.")
    return {"cases": cases, "audit": audit}


def replay_bike(html):
    payload = re.search(r'id="citibike-daily-data" type="application/json">(.*?)</script>', html).group(1)
    actual = {date(2022, 1, 1) + i * DAYS: count for i, count, *_ in json.loads(payload)}
    start = date(2025, 6, 2)
    end = date(2025, 9, 7)   # one extra week to classify persistence after Aug 31
    weeks = []
    for offset in range(0, (end - start).days + 1, 7):
        monday = start + offset * DAYS
        rows = []
        previous = 0
        for index in range(7):
            day = monday + index * DAYS
            prior = sorted(actual[d] for i in range(1, 13) if (d := day - 7 * i * DAYS) in actual)
            if day not in actual or len(prior) < 10:
                raise ValueError(f"Replay requires observations and prior support for {day}.")
            low, high = prior[1], prior[-2]
            flag = -1 if actual[day] < low else 1 if actual[day] > high else 0
            rows.append([day.isoformat(), actual[day], low, high, flag, bool(flag and flag == previous)])
            previous = flag
        weeks.append([monday.isoformat(), rows])
    future = {row[0]: row[4] for _, rows in weeks for row in rows}
    for _, rows in weeks[:-1]:
        for row in rows:
            day = date.fromisoformat(row[0])
            later = [future[(day + i * DAYS).isoformat()] for i in range(1, 8)]
            row.append(sum(flag == row[4] for flag in later) if row[4] else None)
    return weeks[:-1]


def save_csvs(bike, flights, directory):
    with (directory / "bike-season-replay.csv").open("w", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["week_start", "date", "trips", "prior_low", "prior_high", "direction",
                         "consecutive_flag", "same_direction_flags_next_7_days"])
        writer.writerows([week, *row] for week, rows in bike for row in rows)
    with (directory / "flight-ranking-holdout.csv").open("w", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["destination", "month", "time_preference", "status",
                         "planner_origin", "planner_window", "planner_flights", "planner_disrupted",
                         "baseline_origin", "baseline_window", "baseline_flights", "baseline_disrupted"])
        writer.writerows([dest, month, scope, status, *(left or [""] * 4), *(right or [""] * 4)]
                         for dest, month, scope, status, left, right in flights["cases"])


def main(root, training_path, evidence_path, page_path, output):
    training = json.loads(training_path.read_text())
    if {row[0] for row in training["monthly"]} != set(range(36)):
        raise ValueError("Expected only the 36 training months.")
    frozen = freeze(training)
    output.mkdir(exist_ok=True)
    (output / "flight-frozen-choices.json").write_text(json.dumps(frozen, indent=2) + "\n")
    flights = evaluate_flights(root, json.loads(evidence_path.read_text()), frozen)
    bike = replay_bike(page_path.read_text())
    save_csvs(bike, flights, output)
    result = {"bike": bike, "flights": flights}
    (output / "performance.json").write_text(json.dumps(result, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:]))
