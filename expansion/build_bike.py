"""Stream NYC archive CSVs into daily station/rider counts and source audits."""
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

import pandas as pd

COLUMNS = ["started_at", "start_station_id", "start_station_name", "member_casual"]


def process(archive, output):
    period = archive.stem
    rows = 0
    groups = {}
    names = {}
    with ZipFile(archive) as source:
        files = [name for name in source.namelist() if name.lower().endswith(".csv")
                 and not any(part.startswith((".", "__MACOSX")) for part in name.split("/"))]
        if not files:
            raise ValueError(f"No trip CSVs in {archive}")
        for name in files:
            with source.open(name) as csv:
                for chunk in pd.read_csv(csv, usecols=COLUMNS, dtype=str, chunksize=350_000):
                    rows += len(chunk)
                    chunk["day"] = chunk.started_at.str.slice(0, 10)
                    if not chunk.day.str.fullmatch(r"20\d\d-\d\d-\d\d").fillna(False).all():
                        raise ValueError(f"Invalid start date in {archive}/{name}")
                    chunk["station"] = chunk.start_station_id.str.strip().fillna("")
                    chunk["rider"] = chunk.member_casual.where(chunk.member_casual.isin(["member", "casual"]), "other")
                    chunk["name"] = chunk.start_station_name.fillna("").str.strip()
                    for (station, station_name), group in chunk.groupby(["station", "name"], sort=False).day.max().items():
                        if station and station_name:
                            names[station] = max(names.get(station, ("", "")), (group, station_name))
                    for key, count in chunk.groupby(["day", "station", "rider"], sort=False).size().items():
                        groups[key] = groups.get(key, 0) + int(count)
    if rows != sum(groups.values()):
        raise ValueError(f"Trip mismatch in {archive}")
    with archive.open("rb") as raw:
        sha = hashlib.file_digest(raw, "sha256").hexdigest()
    days = sorted({day for day, _, _ in groups})
    for day in days:
        pd.Timestamp(day)
    result = {"source": period, "rows": rows, "sha256": sha, "csv_files": len(files),
              "days": [days[0], days[-1]], "counts": [[*key, n] for key, n in groups.items()], "names": names}
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, separators=(",", ":")))
    temporary.replace(output)
    print(period, rows, result["days"], flush=True)


if __name__ == "__main__":
    process(*map(Path, sys.argv[1:]))
