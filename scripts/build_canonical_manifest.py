#!/usr/bin/env python3
"""Build the canonical source manifest for the corrected (_v2) Citibike rebuild.

READ-ONLY. Reads the committed GCS inventory (evidence/gcs-source-inventory.csv)
and inspects each staging CSV's *actual* header via a tiny HTTP Range read to
decide schema routing (never trusting the GCS directory name). It then selects
exactly one logical representation per (schema_era, year-month) and writes
evidence/canonical-source-manifest.csv.

It creates, modifies, loads, moves, and deletes NOTHING. Excluded objects stay
in GCS and are recorded with a reason.

Auth for header reads: OAuth token in $GCP_ACCESS_TOKEN. If --headers-cache is
given, headers are read from / written to that JSON cache so the manifest is
reproducible without live access.

Usage:
    GCP_ACCESS_TOKEN=$(...) python3 scripts/build_canonical_manifest.py \
        --inventory evidence/gcs-source-inventory.csv \
        --bucket bigdataday1 \
        --out evidence/canonical-source-manifest.csv \
        [--headers-cache evidence/.staging-headers.json]
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request

GCS_DL = "https://storage.googleapis.com"

# Column signatures of the two Citibike schema eras (order-insensitive check on
# a few stable tokens).
LEGACY_TOKENS = ("tripduration", "starttime", "stoptime", "usertype")
NEW_TOKENS = ("ride_id", "rideable_type", "started_at", "member_casual")

# Table routing targets.
T_PRE = "raw_pre2021_v2"    # legacy-header files
T_POST = "raw_post2021_v2"  # new-header files

YM_RE = re.compile(r"(20\d{2})(\d{2})")


def read_header(bucket, name, token, cache):
    if cache is not None and name in cache:
        return cache[name]
    url = f"{GCS_DL}/{bucket}/{urllib.parse.quote(name)}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Range", "bytes=0-1023")
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = r.read().decode("utf-8", "replace")
    header = blob.splitlines()[0] if blob else ""
    if cache is not None:
        cache[name] = header
    return header


def classify_schema(header):
    # Despace so the Title-Case legacy variant ("Trip Duration,Start Time,...")
    # and the lowercase legacy variant ("tripduration,starttime,...") both match.
    h = header.lower().replace('"', "")
    tokset = {t.strip().replace(" ", "") for t in h.split(",")}
    if all(t in tokset for t in LEGACY_TOKENS):
        return "legacy"
    if all(t in tokset for t in NEW_TOKENS):
        return "new"
    return "unknown"


def representation_type(name):
    """full-month = unsuffixed base file; chunk = any split spelling; other otherwise.

    Observed chunk spellings: '_1.csv', '.csv_1.csv', '-part1.csv'.
    The only full-month (unsuffixed) files in this bucket are the duplicated
    2013/2018 months.
    """
    base = name.rsplit("/", 1)[-1]
    if re.search(r"(?:_\d+\.csv|\.csv_\d+\.csv|-part\d+\.csv)$", base, re.I):
        return "chunk"
    if re.search(r"^\d{6}-citibike-tripdata\.csv$", base, re.I):
        return "full-month"
    return "other"


def norm_ym(name):
    b = name.rsplit("/", 1)[-1]
    m = YM_RE.search(b)
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", default="evidence/gcs-source-inventory.csv")
    ap.add_argument("--bucket", default="bigdataday1")
    ap.add_argument("--out", default="evidence/canonical-source-manifest.csv")
    ap.add_argument("--headers-cache")
    args = ap.parse_args()

    cache = None
    if args.headers_cache and os.path.exists(args.headers_cache):
        cache = json.load(open(args.headers_cache))
    elif args.headers_cache is not None:
        cache = {}

    token = os.environ.get("GCP_ACCESS_TOKEN")

    rows = [r for r in csv.DictReader(open(args.inventory))
            if r["schema_era"] in ("pre2021", "post2021")]  # staging CSVs only

    recs = []
    for r in rows:
        name = r["object_name"]
        if token is None and (cache is None or name not in cache):
            sys.exit(f"ERROR: need GCP_ACCESS_TOKEN or cached header for {name}")
        header = read_header(args.bucket, name, token, cache)
        schema = classify_schema(header)          # actual header, not folder
        rep = representation_type(name)
        ym = norm_ym(name)
        recs.append({
            "object_uri": f"gs://{args.bucket}/{name}",
            "object_name": name,
            "gcs_folder": "pre2021" if "pre2021" in name else "post2021",
            "year_month": ym,
            "inferred_year": ym.split("-")[0] if ym else "",
            "schema_era": schema,                 # legacy | new | unknown
            "representation": rep,                 # full-month | chunk | other
            "size_bytes": r["size_bytes"],
            "md5_hash": r["md5_hash"],
            "crc32c": r["crc32c"],
            "generation": r["generation"],
            "target_table": "",
            "selected_for_load": "false",
            "exclusion_reason": "",
        })

    if args.headers_cache is not None and cache is not None:
        json.dump(cache, open(args.headers_cache, "w"), indent=0, sort_keys=True)

    # ---- routing: by ACTUAL schema header ----
    for m in recs:
        if m["schema_era"] == "legacy":
            m["target_table"] = T_PRE
        elif m["schema_era"] == "new":
            m["target_table"] = T_POST
        # unknown -> left blank, will fail the validation below

    # ---- selection: exactly one representation per (target_table, year-month) ----
    # Preference: full-month over chunk (defect #2/#3 — 2018 full files are the
    # complete ones; apply the same rule to 2013). If a month has ONLY chunks,
    # select the whole chunk set as the single logical representation. If a month
    # has ONLY a full-month file, select it.
    from collections import defaultdict
    groups = defaultdict(list)
    for m in recs:
        if m["target_table"]:
            groups[(m["target_table"], m["year_month"])].append(m)

    for (tbl, ym), members in groups.items():
        has_full = any(x["representation"] == "full-month" for x in members)
        has_chunk = any(x["representation"] == "chunk" for x in members)
        for x in members:
            if has_full and has_chunk:
                # duplicate representations present -> keep full-month, drop chunks
                if x["representation"] == "full-month":
                    x["selected_for_load"] = "true"
                else:
                    x["exclusion_reason"] = (
                        "duplicate month representation; full-month file selected, "
                        "chunk excluded")
            elif has_full:
                if x["representation"] == "full-month":
                    x["selected_for_load"] = "true"
                else:
                    x["exclusion_reason"] = "non-full representation in full-only month"
            elif has_chunk:
                if x["representation"] == "chunk":
                    x["selected_for_load"] = "true"
                else:
                    x["exclusion_reason"] = "non-chunk representation in chunk-only month"
            else:
                x["exclusion_reason"] = "no full-month or chunk representation"

    # ---- write manifest ----
    cols = ["object_uri", "object_name", "gcs_folder", "year_month",
            "inferred_year", "schema_era", "representation", "size_bytes",
            "md5_hash", "crc32c", "generation", "target_table",
            "selected_for_load", "exclusion_reason"]
    recs.sort(key=lambda m: (m["target_table"], m["year_month"], m["object_name"]))
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(recs)

    # ---- fail-loud consistency checks ----
    errors = []
    # unknown headers
    for m in recs:
        if m["schema_era"] == "unknown":
            errors.append(f"unknown header: {m['object_name']}")
    # duplicate selected URIs
    sel = [m for m in recs if m["selected_for_load"] == "true"]
    seen = set()
    for m in sel:
        if m["object_uri"] in seen:
            errors.append(f"duplicate selected URI: {m['object_uri']}")
        seen.add(m["object_uri"])
    # one selected logical representation per (table, month); and no month with
    # BOTH a selected full-month and a selected chunk (representation overlap)
    permonth = defaultdict(lambda: {"full": 0, "chunk": 0, "other": 0})
    for m in sel:
        key = (m["target_table"], m["year_month"])
        permonth[key][m["representation"].split("-")[0] if m["representation"] == "full-month" else m["representation"]] = \
            permonth[key].get("full" if m["representation"] == "full-month" else m["representation"], 0) + 1
    for (tbl, ym), members in groups.items():
        s = [x for x in members if x["selected_for_load"] == "true"]
        reps = {x["representation"] for x in s}
        if not s:
            errors.append(f"month with NO selected source: {tbl} {ym}")
        if "full-month" in reps and "chunk" in reps:
            errors.append(f"month selects BOTH full and chunk: {tbl} {ym}")
        if "full-month" in reps and sum(1 for x in s if x["representation"] == "full-month") > 1:
            errors.append(f"month selects >1 full-month file: {tbl} {ym}")
    # explicit 2013/2018 guard: no selected month may mix full+chunk
    for yr in ("2013", "2018"):
        for (tbl, ym), members in groups.items():
            if ym.startswith(yr):
                reps = {x["representation"] for x in members if x["selected_for_load"] == "true"}
                if "full-month" in reps and "chunk" in reps:
                    errors.append(f"{yr} month mixes representations: {ym}")

    sel_n = len(sel)
    exc_n = sum(1 for m in recs if m["selected_for_load"] != "true")
    print(f"[manifest] {len(recs)} staging objects | selected={sel_n} excluded={exc_n}")
    by_tbl = defaultdict(int)
    for m in sel:
        by_tbl[m["target_table"]] += 1
    print(f"[manifest] selected by table: {dict(by_tbl)}")
    months = sorted({(m["target_table"], m["year_month"]) for m in sel})
    print(f"[manifest] selected months: {len(months)}")

    if errors:
        print("\n=== MANIFEST VALIDATION FAILED ===", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        sys.exit(2)
    print("[manifest] all consistency checks PASSED")


if __name__ == "__main__":
    main()
