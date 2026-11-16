"""Rebuild monthly 2022–24 planner counts from the reconciled BTS archives."""
import json
import sys
import hashlib
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

ORIGINS = {"BWI", "DCA", "IAD"}
FIELDS = ["FlightDate", "Origin", "Dest", "CRSDepTime", "DepDelay", "Cancelled", "Diverted"]


def month_summary(path, month, destinations):
    with ZipFile(path) as archive:
        member, = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        with archive.open(member) as source:
            raw = pd.read_csv(source, usecols=FIELDS)
    if not raw.FlightDate.str.startswith(month).all():
        raise ValueError(f"Unexpected month in {path}")
    frame = raw.loc[raw.Origin.isin(ORIGINS) & raw.Dest.isin(destinations)].copy()
    hour = (frame.CRSDepTime // 100).replace(24, 0)
    frame["window"] = pd.cut(hour, [-1, 5, 9, 13, 17, 23], labels=False)
    scheduled = frame.Cancelled.isin([0, 1]) & frame.Diverted.isin([0, 1])
    classified = frame.Cancelled.eq(1) | frame.Diverted.eq(1) | frame.DepDelay.notna()
    valid = scheduled & classified & frame.window.notna()
    unknown = int((~valid).sum())
    frame = frame.loc[valid].copy()
    frame["cancel"] = frame.Cancelled.eq(1)
    frame["divert"] = ~frame.cancel & frame.Diverted.eq(1)
    frame["late"] = ~(frame.cancel | frame.divert) & frame.DepDelay.ge(15)
    group = frame.groupby(["Dest", "Origin", "window"], observed=True).agg(
        n=("cancel", "size"), late=("late", "sum"), cancel=("cancel", "sum"), divert=("divert", "sum"),
    )
    if group.n.sum() != len(frame):
        raise ValueError(f"Counts did not reconcile for {month}")
    return group.reset_index().values.tolist(), unknown, len(raw)


def main(directory, source_evidence, output):
    source = json.loads(source_evidence.read_text())
    destinations = {row[0] for row in source["routes"]}
    months = []
    excluded = 0
    for index, (month, expected_total, _, expected_sha) in enumerate(source["sourceMonths"]):
        if month >= "2025":
            continue
        path = directory / f"{month}.zip"
        with path.open("rb") as archive:
            sha = hashlib.file_digest(archive, "sha256").hexdigest()
        if sha != expected_sha:
            raise ValueError(f"Archive hash changed for {month}")
        rows, unknown, total = month_summary(path, month, destinations)
        if total != expected_total:
            raise ValueError(f"Archive count changed for {month}")
        months.extend([index, *row] for row in rows)
        excluded += unknown
        print(month, len(rows), unknown, flush=True)
    if len({row[0] for row in months}) != 36 or not all(
        n > 0 and 0 <= late + cancel + divert <= n for _, _, _, _, n, late, cancel, divert in months
    ):
        raise ValueError("Incomplete coverage or invalid counts")
    output.write_text(json.dumps({"excluded": excluded, "monthly": months}, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:]))
