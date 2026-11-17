"""Match airports to NOAA airport stations by ICAO and verify proximity."""
import csv
import json
import math
from pathlib import Path
import sys


def km(lat, lon, other_lat, other_lon):
    a, b = map(math.radians, (lat, other_lat))
    delta = math.radians(other_lon - lon)
    return 6371 * 2 * math.asin(math.sqrt(math.sin((b-a)/2)**2
        + math.cos(a)*math.cos(b)*math.sin(delta/2)**2))


def main(airport_csv, directory, evidence_path):
    evidence = json.loads(evidence_path.read_text())
    codes = {row[0] for row in evidence["routes"]} | {"BWI","DCA","IAD"}
    airports = {}
    with airport_csv.open(newline="") as data:
        for row in csv.DictReader(data):
            code = row["iata_code"]
            if code in codes and row["type"] in {"large_airport", "medium_airport"} and row["iso_country"] == "US":
                if code in airports:
                    raise ValueError(f"Duplicate airport code {code}")
                airports[code] = {"name": row["name"], "icao": row["ident"],
                                  "lat": float(row["latitude_deg"]), "lon": float(row["longitude_deg"])}
    if set(airports) != codes:
        raise ValueError("Airport lookup incomplete")
    stations = {line[:11]: (float(line[12:20]), float(line[21:30]))
                for line in (directory/"ghcnd-stations.txt").read_text().splitlines() if line.startswith("USW")}
    with (directory/"isd-history.csv").open(newline="") as data:
        isd = list(csv.DictReader(data))
    for airport in airports.values():
        options = []
        for row in isd:
            station = "USW000" + row["WBAN"]
            if row["ICAO"] == airport["icao"] and station in stations and row["BEGIN"] <= "20220101" and row["END"] >= "20240101":
                distance = km(airport["lat"], airport["lon"], *stations[station])
                if distance <= 15:
                    options.append((distance, station))
        if options:
            distance, station = min(options)
            airport.update(station=station, distance_km=round(distance, 2))
    (directory/"airports.json").write_text(json.dumps(airports, indent=2) + "\n")
    for info in airports.values():
        if "station" in info:
            print(info["station"])


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:]))
