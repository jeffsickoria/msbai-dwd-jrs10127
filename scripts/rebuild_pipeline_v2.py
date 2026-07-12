#!/usr/bin/env python3
"""Controlled, non-destructive rebuild of the corrected (_v2) Citibike pipeline.

SAFETY MODEL
------------
* DRY-RUN by DEFAULT. Nothing is created unless --apply is passed explicitly.
* Writes ONLY to *_v2 destinations. A hard guard refuses any destination whose
  table name does not end in "_v2".
* Never deletes or moves GCS objects. Never touches the existing non-v2 tables or
  views (trips, trips_daily, trips_daily_table, raw_pre2021, raw_post2021).
* Never deploys anything.
* Loads use the EXPLICIT selected source URIs from the canonical manifest — never
  broad wildcards — so the duplicate 2013/2018 chunk files are structurally
  excluded.
* WRITE_TRUNCATE is used only on the _v2 raw tables.
* Stops immediately on any failed load.

Usage:
    # dry-run (default) — prints the full plan, calls no mutating API:
    GCP_ACCESS_TOKEN=$(...) python3 scripts/rebuild_pipeline_v2.py

    # execute (requires explicit opt-in):
    GCP_ACCESS_TOKEN=$(...) python3 scripts/rebuild_pipeline_v2.py --apply
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request

BQ = "https://bigquery.googleapis.com/bigquery/v2"

# Explicit all-STRING schemas (positional; load uses skipLeadingRows=1 so header
# naming variants — lowercase vs Title-Case legacy — do not matter).
PRE_COLUMNS = [
    "tripduration", "starttime", "stoptime", "start_station_id",
    "start_station_name", "start_station_latitude", "start_station_longitude",
    "end_station_id", "end_station_name", "end_station_latitude",
    "end_station_longitude", "bikeid", "usertype", "birth_year", "gender",
]
POST_COLUMNS = [
    "ride_id", "rideable_type", "started_at", "ended_at", "start_station_name",
    "start_station_id", "end_station_name", "end_station_id", "start_lat",
    "start_lng", "end_lat", "end_lng", "member_casual",
]

RAW_PRE = "raw_pre2021_v2"
RAW_POST = "raw_post2021_v2"
SQL_FILES = ["sql/trips_v2.sql", "sql/trips_daily_v2.sql", "sql/materialize_daily_v2.sql"]


def guard_v2(name):
    if not name.endswith("_v2"):
        sys.exit(f"REFUSING: destination '{name}' does not end in _v2")
    return name


def _req(url, token, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def load_manifest(path):
    rows = [r for r in csv.DictReader(open(path)) if r["selected_for_load"] == "true"]
    groups = {RAW_PRE: [], RAW_POST: []}
    for r in rows:
        tbl = r["target_table"]
        if tbl not in groups:
            sys.exit(f"REFUSING: manifest routes to unexpected table '{tbl}'")
        groups[tbl].append(r["object_uri"])
    return groups


def schema_json(columns):
    return [{"name": c, "type": "STRING", "mode": "NULLABLE"} for c in columns]


def run_load(token, project, dataset, table, uris, columns, apply):
    guard_v2(table)
    cfg = {
        "configuration": {
            "load": {
                "destinationTable": {"projectId": project, "datasetId": dataset,
                                     "tableId": table},
                "sourceUris": uris,                      # EXPLICIT, not wildcard
                "sourceFormat": "CSV",
                "skipLeadingRows": 1,
                "writeDisposition": "WRITE_TRUNCATE",    # _v2 only
                "createDisposition": "CREATE_IF_NEEDED",
                "schema": {"fields": schema_json(columns)},
                "maxBadRecords": 0,
                "allowQuotedNewlines": True,
            }
        }
    }
    print(f"\n[load] {project}.{dataset}.{table}  <=  {len(uris)} explicit URIs")
    print(f"       first: {uris[0]}")
    print(f"       last:  {uris[-1]}")
    print(f"       schema: {len(columns)} STRING columns; WRITE_TRUNCATE; skipLeadingRows=1")
    if not apply:
        print("       [dry-run] not submitted")
        return None
    job = _req(f"{BQ}/projects/{project}/jobs", token, "POST", cfg)
    jid = job["jobReference"]["jobId"]
    while True:
        st = _req(f"{BQ}/projects/{project}/jobs/{jid}", token)
        if st["status"]["state"] == "DONE":
            break
        time.sleep(2)
    if st["status"].get("errorResult"):
        sys.exit(f"LOAD FAILED ({jid}): {st['status']['errorResult']['message']}")
    ld = st["statistics"]["load"]
    print(f"       job={jid} rows={ld.get('outputRows')} badRecords={ld.get('badRecords')} "
          f"inputFiles={ld.get('inputFiles')}")
    return jid


def run_sql(token, project, dataset, path, apply):
    sql = open(path).read()
    if not (project == "msbai-dwd-jrs10127" and dataset == "citibike"):
        sql = sql.replace("msbai-dwd-jrs10127.citibike.", f"{project}.{dataset}.")
    # guard: the statement's target must be a _v2 object
    lowered = sql.lower()
    for tgt in ("create or replace view", "create or replace table"):
        if tgt in lowered:
            after = lowered.split(tgt, 1)[1].strip()
            # crude object-name extraction between backticks
            obj = after.split("`")[1] if "`" in after else after.split()[0]
            guard_v2(obj.rstrip("`").split(".")[-1])
    print(f"\n[sql] {path} -> target verified _v2")
    if not apply:
        print("      [dry-run] not submitted")
        return None
    job = _req(f"{BQ}/projects/{project}/jobs", token, "POST",
               {"configuration": {"query": {"query": sql, "useLegacySql": False}}})
    jid = job["jobReference"]["jobId"]
    while True:
        st = _req(f"{BQ}/projects/{project}/jobs/{jid}", token)
        if st["status"]["state"] == "DONE":
            break
        time.sleep(2)
    if st["status"].get("errorResult"):
        sys.exit(f"SQL FAILED ({jid}) for {path}: {st['status']['errorResult']['message']}")
    print(f"      job={jid} OK")
    return jid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="msbai-dwd-jrs10127")
    ap.add_argument("--dataset", default="citibike")
    ap.add_argument("--manifest", default="evidence/canonical-source-manifest.csv")
    ap.add_argument("--apply", action="store_true",
                    help="ACTUALLY create the _v2 objects (default is dry-run)")
    args = ap.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== rebuild_pipeline_v2 [{mode}] project={args.project} dataset={args.dataset} ===")

    groups = load_manifest(args.manifest)
    print(f"manifest: {RAW_PRE}={len(groups[RAW_PRE])} URIs, "
          f"{RAW_POST}={len(groups[RAW_POST])} URIs")

    token = os.environ.get("GCP_ACCESS_TOKEN")
    if args.apply and not token:
        sys.exit("ERROR: --apply requires GCP_ACCESS_TOKEN")
    if not args.apply:
        print("NOTE: dry-run — no BigQuery API calls will be made. Pass --apply to execute.")

    # 1) raw tables (explicit URIs, all-STRING, WRITE_TRUNCATE, _v2 only)
    run_load(token, args.project, args.dataset, RAW_PRE, groups[RAW_PRE], PRE_COLUMNS, args.apply)
    run_load(token, args.project, args.dataset, RAW_POST, groups[RAW_POST], POST_COLUMNS, args.apply)

    # 2) corrected views + materialization (each target guarded _v2)
    for path in SQL_FILES:
        run_sql(token, args.project, args.dataset, path, args.apply)

    print(f"\n=== {mode} complete ===")
    if not args.apply:
        print("Existing non-v2 tables/views were not referenced for writes. "
              "Re-run with --apply (and human approval) to build the _v2 objects.")


if __name__ == "__main__":
    main()
