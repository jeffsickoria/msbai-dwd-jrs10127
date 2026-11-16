"""Build portfolio aggregates and evaluate a frozen 2025 departure-delay holdout.

Input: official BTS monthly ZIPs named YYYY-MM.zip and NOAA station CSV.GZs.
Dependencies: pandas, scikit-learn. Run with input directory and output JSON paths.
"""
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

STATIONS = {"BWI": "USW00093721", "DCA": "USW00013743", "IAD": "USW00093738"}
FIELDS = [
    "FlightDate", "Reporting_Airline", "Origin", "Dest", "CRSDepTime",
    "DepDelay", "Cancelled", "Diverted",
]
KEYS = ["date", "origin", "carrier", "destination", "window"]
PERIODS = [f"{year}-{month:02}" for year in range(2022, 2026) for month in range(1, 13)]


def station_days(path):
    result = {}
    with gzip.open(path, "rt", newline="") as source:
        for _, day, element, value, measure, quality, *_ in csv.reader(source):
            if quality or element not in {"PRCP", "SNOW", "TMAX"} or value == "-9999":
                continue
            date = f"{day[:4]}-{day[4:6]}-{day[6:]}"
            entry = result.setdefault(date, {})
            measurement = (int(value), measure == "T")
            if element in entry and entry[element] != measurement:
                raise ValueError(f"Conflicting observations in {path}: {day} {element}")
            entry[element] = measurement
    return result


def read_period(path, period):
    with ZipFile(path) as archive:
        member, = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        with archive.open(member) as source:
            raw = pd.read_csv(source, usecols=FIELDS, dtype={"Reporting_Airline": str})
    days = pd.to_datetime(raw.FlightDate, errors="raise")
    if not days.dt.strftime("%Y-%m").eq(period).all():
        raise ValueError(f"Unexpected flight date in {path}")
    eligible = raw.Origin.isin(STATIONS) & raw.Cancelled.eq(0) & raw.Diverted.eq(0) & raw.DepDelay.notna()
    frame = raw.loc[eligible].rename(columns={
        "FlightDate": "date", "Origin": "origin", "Reporting_Airline": "carrier", "Dest": "destination",
    })
    hour = (frame.CRSDepTime // 100).replace(24, 0)
    if frame[KEYS[:-1]].isna().any().any() or not hour.between(0, 23).all():
        raise ValueError(f"Invalid eligible flight dimensions in {path}")
    frame["window"] = pd.cut(hour, [-1, 5, 9, 13, 17, 23], labels=False)
    frame["delayed"] = frame.DepDelay.ge(15).astype(int)
    summary = frame.groupby(KEYS, observed=True).delayed.agg(n="size", delayed="sum").reset_index()
    return summary, len(raw)


def weather_label(observation):
    if any(element not in observation for element in ("PRCP", "SNOW")):
        return "unknown"
    return "wet" if any(value > 0 or trace for value, trace in
                        (observation["PRCP"], observation["SNOW"])) else "dry"


def features(frame, include_weather):
    for row in frame.itertuples():
        values = {
            "origin": row.origin, "carrier": row.carrier, "destination": row.destination,
            "window": str(row.window), "month": row.date[5:7],
        }
        if include_weather:
            values["wet"] = row.weather == "wet"
            values["temperature / 10 C"] = row.tmax / 100
        yield values


def holdout_score(train, test, include_weather):
    vectorizer = DictVectorizer()
    training = vectorizer.fit_transform(features(train, include_weather))
    testing = vectorizer.transform(features(test, include_weather))
    # Aggregate observations preserve the Bernoulli objective via frequency weights.
    from scipy.sparse import vstack

    model = LogisticRegression(C=1.0, max_iter=1000)
    model.fit(vstack([training, training]), [0] * len(train) + [1] * len(train),
              sample_weight=pd.concat([train.n - train.delayed, train.delayed]))
    risk = model.predict_proba(testing)[:, 1]
    return float(brier_score_loss(
        [0] * len(test) + [1] * len(test), list(risk) * 2,
        sample_weight=pd.concat([test.n - test.delayed, test.delayed]),
    ))


def main(directory, output):
    weather = {origin: station_days(directory / f"{station}.csv.gz")
               for origin, station in STATIONS.items()}
    parts = []
    source_months = []
    for period in PERIODS:
        path = directory / f"{period}.zip"
        if not path.exists():
            raise FileNotFoundError(path)
        summary, source_rows = read_period(path, period)
        for origin in STATIONS:
            seen = set(summary.loc[summary.origin.eq(origin), "date"])
            first = pd.Timestamp(period + "-01")
            expected = set(pd.date_range(first, periods=first.days_in_month).strftime("%Y-%m-%d"))
            if seen != expected:
                raise ValueError(f"Incomplete {period} coverage for {origin}")
        with path.open("rb") as archive:
            checksum = hashlib.file_digest(archive, "sha256").hexdigest()
        source_months.append([period, source_rows, int(summary.n.sum()), checksum])
        parts.append(summary)
        print(period, source_rows, int(summary.n.sum()), flush=True)
    frame = pd.concat(parts, ignore_index=True)
    observations = [weather[origin].get(day, {}) for day, origin in zip(frame.date, frame.origin)]
    frame["weather"] = [weather_label(obs) for obs in observations]
    frame["tmax"] = [obs.get("TMAX", (None, False))[0] for obs in observations]
    complete = frame.weather.ne("unknown") & frame.tmax.notna()
    train = frame[frame.date.lt("2025") & complete]
    test = frame[frame.date.ge("2025") & complete]
    evaluation = {
        "trainingFlights": int(train.n.sum()), "scoredFlights": int(test.n.sum()),
        "allHoldoutFlights": int(frame.loc[frame.date.ge("2025"), "n"].sum()),
        "baselineBrier": holdout_score(train, test, False),
        "weatherBrier": holdout_score(train, test, True),
    }
    # Keep descriptive comparison anchored to the training period.
    history = frame[frame.date.lt("2025")]
    volumes = history.groupby(["destination", "origin"]).n.sum().unstack(fill_value=0)
    options = volumes[(volumes >= 100).sum(axis=1) >= 2].sum(axis=1).nlargest(20).index
    groups = history[history.destination.isin(options)].groupby(
        ["destination", "origin", "carrier", "window", "weather"], observed=True
    )[["n", "delayed"]].sum().reset_index()
    december = frame[frame.date.str.startswith("2023-12")]
    result = {
        "evaluation": evaluation, "sourceMonths": source_months,
        "decemberReconciliation": [int(december.n.sum()), int(december.delayed.sum())],
        "routes": groups.values.tolist(),
    }
    output.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
