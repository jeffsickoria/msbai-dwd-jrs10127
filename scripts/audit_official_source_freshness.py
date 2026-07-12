#!/usr/bin/env python3
"""Audit the official Citibike S3 archive (https://s3.amazonaws.com/tripdata/)
against this project's stored sources, for the periods left unresolved by the
_v2 reconciliation (docs/verification/v2-reconciliation.md):

    2018-04, 2022-01..2023-12, 2024-05

READ-ONLY with respect to the project: downloads official archives into a
local temp dir, streams row counts out of them, and writes two evidence CSVs.
Never touches GCS, BigQuery, or the repo's staged data. Downloads are deleted
after counting unless --keep is passed.

Outputs:
  evidence/official-source-comparison.csv   one row per official object that
      covers a target period, joined to the stored gs://bigdataday1/raw/ copy
      (from evidence/gcs-source-inventory.csv) and to the staging
      representation counts (from evidence/canonical-source-manifest.csv).
  evidence/official-source-row-counts.csv   one row per (archive, inner CSV,
      month): data rows (header rows excluded), min/max started_at, and rider
      label counts.

Usage:
    python3 scripts/audit_official_source_freshness.py \
        --workdir /path/to/tmp [--skip-download] [--keep]
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

S3_BASE = "https://s3.amazonaws.com/tripdata/"
NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"

TARGET_MONTHS = {"2018-04", "2024-05"} | {f"2022-{m:02d}" for m in range(1, 13)} \
    | {f"2023-{m:02d}" for m in range(1, 13)}

LEGACY_START = {"starttime", "start time"}
NEW_START = {"started_at"}
LEGACY_RIDER = {"usertype", "user type"}
NEW_RIDER = {"member_casual"}


def list_bucket():
    objs, token = [], None
    while True:
        url = S3_BASE + "?list-type=2&max-keys=1000"
        if token:
            url += "&continuation-token=" + urllib.parse.quote(token)
        with urllib.request.urlopen(url, timeout=120) as r:
            root = ET.fromstring(r.read())
        for c in root.findall(f"{NS}Contents"):
            objs.append({
                "key": c.find(f"{NS}Key").text,
                "size": int(c.find(f"{NS}Size").text),
                "etag": c.find(f"{NS}ETag").text.strip('"'),
                "last_modified": c.find(f"{NS}LastModified").text,
            })
        if root.find(f"{NS}IsTruncated").text != "true":
            break
        token = root.find(f"{NS}NextContinuationToken").text
    return objs


def key_coverage(key):
    """Months an official NYC key covers, derived from its name. JC keys are
    out of scope (project is NYC-only)."""
    base = key.split("/")[-1]
    if base.upper().startswith("JC-") or base == "index.html":
        return set()
    m = re.match(r"^(\d{6})-citibike-tripdata", base)
    if m:
        ym = m.group(1)
        return {f"{ym[:4]}-{ym[4:6]}"}
    m = re.match(r"^(\d{4})-citibike-tripdata", base)
    if m:
        y = m.group(1)
        return {f"{y}-{mm:02d}" for mm in range(1, 13)}
    return set()


def safe_members(zf):
    """Yield validated member names: no absolute paths, no traversal."""
    for name in zf.namelist():
        parts = name.replace("\\", "/").split("/")
        if name.startswith("/") or ".." in parts:
            print(f"    !! skipping unsafe zip path: {name!r}", file=sys.stderr)
            continue
        if name.endswith("/") or "__MACOSX" in parts or parts[-1].startswith("."):
            continue
        yield name


def classify_header(cols):
    lc = [c.strip().strip('"').lower() for c in cols]
    if any(c in NEW_START for c in lc):
        return "new", lc.index("started_at"), \
            lc.index("member_casual") if "member_casual" in lc else None
    for cand in LEGACY_START:
        if cand in lc:
            rider = next((lc.index(r) for r in LEGACY_RIDER if r in lc), None)
            return "legacy", lc.index(cand), rider
    return "unknown", None, None


def count_csv(fh, source_label):
    """Stream one CSV; return (era, per-month stats dict). Header row is
    detected and EXCLUDED from all row counts."""
    text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
    reader = csv.reader(text)
    header = next(reader, None)
    if header is None:
        return "empty", {}
    era, start_idx, rider_idx = classify_header(header)
    if era == "unknown":
        print(f"    !! unrecognized header in {source_label}: {header[:5]}",
              file=sys.stderr)
        return "unknown", {}
    months = {}
    for row in reader:
        try:
            ts = row[start_idx].strip()
        except IndexError:
            ts, month = "", "unparseable"
        month = ts[:7] if re.match(r"^\d{4}-\d{2}", ts) else "unparseable"
        st = months.setdefault(month, {
            "rows": 0, "min_ts": None, "max_ts": None,
            "member": 0, "casual": 0, "unknown": 0})
        st["rows"] += 1
        if month != "unparseable":
            if st["min_ts"] is None or ts < st["min_ts"]:
                st["min_ts"] = ts
            if st["max_ts"] is None or ts > st["max_ts"]:
                st["max_ts"] = ts
        label = (row[rider_idx].strip().lower() if rider_idx is not None
                 and rider_idx < len(row) else "")
        if label in ("member", "subscriber"):
            st["member"] += 1
        elif label in ("casual", "customer"):
            st["casual"] += 1
        else:
            st["unknown"] += 1
    return era, months


def walk_zip(zf, archive_key, rows_out, prefix=""):
    for name in safe_members(zf):
        label = f"{archive_key}!{prefix}{name}"
        if name.lower().endswith(".csv"):
            with zf.open(name) as fh:
                era, months = count_csv(fh, label)
            for month, st in sorted(months.items()):
                rows_out.append({
                    "archive_key": archive_key,
                    "member_path": prefix + name,
                    "schema_era": era,
                    "month": month,
                    "data_rows_excl_header": st["rows"],
                    "min_started_at": st["min_ts"] or "",
                    "max_started_at": st["max_ts"] or "",
                    "member_rows": st["member"],
                    "casual_rows": st["casual"],
                    "unknown_rider_rows": st["unknown"],
                })
            print(f"    {prefix+name}: {sum(s['rows'] for s in months.values()):,} rows "
                  f"({era}; months {sorted(m for m in months)})")
        elif name.lower().endswith(".zip"):
            with zf.open(name) as fh:
                data = io.BytesIO(fh.read())
            with zipfile.ZipFile(data) as inner:
                walk_zip(inner, archive_key, rows_out, prefix=prefix + name + "!")


def download(key, dest, expect_size):
    md5 = hashlib.md5()
    url = S3_BASE + urllib.parse.quote(key)
    with urllib.request.urlopen(url, timeout=600) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            md5.update(chunk)
    size = os.path.getsize(dest)
    if size != expect_size:
        sys.exit(f"FATAL: {key} downloaded {size} bytes, listing says {expect_size}")
    return base64.b64encode(md5.digest()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="/tmp/official-source-audit")
    ap.add_argument("--inventory", default="evidence/gcs-source-inventory.csv")
    ap.add_argument("--manifest", default="evidence/canonical-source-manifest.csv")
    ap.add_argument("--out-comparison", default="evidence/official-source-comparison.csv")
    ap.add_argument("--out-rowcounts", default="evidence/official-source-row-counts.csv")
    ap.add_argument("--skip-download", action="store_true",
                    help="only write the comparison CSV (no archive downloads)")
    ap.add_argument("--keep", action="store_true",
                    help="keep downloaded archives (default: delete after counting)")
    args = ap.parse_args()
    os.makedirs(args.workdir, exist_ok=True)

    inv = list(csv.DictReader(open(args.inventory)))
    raw_by_base = {r["object_name"].split("/")[-1]: r for r in inv
                   if r["prefix"] == "raw/"}
    manifest = list(csv.DictReader(open(args.manifest)))

    print("listing official bucket ...")
    objs = list_bucket()
    print(f"  {len(objs)} objects")

    comparison, to_download = [], []
    for o in objs:
        cover = key_coverage(o["key"])
        hit = sorted(cover & TARGET_MONTHS)
        if not hit:
            continue
        stored = raw_by_base.get(o["key"].split("/")[-1])
        staged = [m for m in manifest if m["year_month"] in cover]
        staged_sel = [m for m in staged if m["selected_for_load"] == "true"]
        if stored:
            same_size = int(stored["size_bytes"]) == o["size"]
            verdict = ("same filename, same size (md5 verified after download)"
                       if same_size else "same filename but CHANGED bytes (size differs)")
        else:
            verdict = "official object has NO stored raw/ counterpart"
        comparison.append({
            "official_key": o["key"],
            "official_size": o["size"],
            "official_etag": o["etag"],
            "official_last_modified": o["last_modified"],
            "covers_target_months": ";".join(hit),
            "coverage_kind": "annual" if len(cover) == 12 else "monthly",
            "stored_raw_object": stored["object_name"] if stored else "",
            "stored_size": stored["size_bytes"] if stored else "",
            "stored_md5_b64": stored["md5_hash"] if stored else "",
            "stored_crc32c": stored["crc32c"] if stored else "",
            "stored_generation": stored["generation"] if stored else "",
            "stored_gcs_updated": stored["updated"] if stored else "",
            "staged_csvs_for_months": len(staged),
            "staged_csvs_selected": len(staged_sel),
            "downloaded_md5_b64": "",
            "bytes_identical_to_stored": "",
            "official_existed_at_staging": ("yes — official last_modified "
                "predates GCS staging date" if stored and
                o["last_modified"] < stored["updated"] else "see notes"),
        })
        to_download.append(o)

    row_counts = []
    if not args.skip_download:
        for o, comp in zip(to_download, comparison):
            key = o["key"]
            dest = os.path.join(args.workdir, key.split("/")[-1])
            print(f"downloading {key} ({o['size']:,} B) ...")
            md5_b64 = download(key, dest, o["size"])
            comp["downloaded_md5_b64"] = md5_b64
            if comp["stored_md5_b64"]:
                comp["bytes_identical_to_stored"] = str(
                    md5_b64 == comp["stored_md5_b64"]).upper()
            print(f"  md5={md5_b64}  identical_to_stored={comp['bytes_identical_to_stored']}")
            with zipfile.ZipFile(dest) as zf:
                walk_zip(zf, key, row_counts)
            if not args.keep:
                os.remove(dest)

    with open(args.out_comparison, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(comparison[0].keys()))
        w.writeheader()
        w.writerows(comparison)
    print(f"wrote {args.out_comparison} ({len(comparison)} rows)")

    if row_counts:
        with open(args.out_rowcounts, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row_counts[0].keys()))
            w.writeheader()
            w.writerows(row_counts)
        print(f"wrote {args.out_rowcounts} ({len(row_counts)} rows)")

    # per-target-month official totals
    totals = {}
    for r in row_counts:
        if r["month"] in TARGET_MONTHS:
            totals[r["month"]] = totals.get(r["month"], 0) + r["data_rows_excl_header"]
    for m in sorted(totals):
        print(f"OFFICIAL {m}: {totals[m]:,} data rows")


if __name__ == "__main__":
    main()
