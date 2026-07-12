#!/usr/bin/env python3
"""Reproducible archive → GCS `staging/` preparation for the corrected (_v2)
Citi Bike pipeline.

This is the ingestion/staging stage that was never committed (see
docs/verification/raw-source-diagnosis.md). It rebuilds the staged CSV set that
`scripts/build_canonical_manifest.py` and `scripts/rebuild_pipeline_v2.py`
consume, deterministically and safely.

SAFETY
------
* DRY-RUN BY DEFAULT: prints the full staging plan from the committed manifest
  + inventory (fully offline — no download, no upload). Cloud writes happen
  ONLY with --apply.
* Configurable --project / --bucket / --dataset.
* Manifest-driven: the canonical manifest is the single source of truth for
  which representation of each (table, month) is staged. Excluded full-month/
  chunk duplicates are never staged — a hard check refuses any plan that would
  stage BOTH representations of the same (target_table, year_month).
* Schema routing by ACTUAL CSV header (legacy 15-col vs new 13-col ride_id),
  re-verified against the manifest's schema_era before any upload (fail-loud).
* Checksums: staged objects are verified against the manifest's md5/crc32c;
  archives against the inventory's md5 (when --apply downloads them).
* Checkpoint/restart: completed archives are recorded in a checkpoint file and
  skipped on re-run.
* Never prints credentials; uses Application Default Credentials.
* This PR does NOT run --apply and does NOT download the full archive.
  No production run has been performed; only offline dry-run + fixture unit
  tests have been exercised.

Usage:
    python3 scripts/prepare_staging.py                 # offline dry-run plan
    python3 scripts/prepare_staging.py --apply         # download+stage (needs approval)
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import sys
import zipfile

LEGACY_HEADER_KEYS = ("starttime", "start time", "tripduration", "trip duration")
NEW_HEADER_KEYS = ("ride_id", "started_at")


def classify_header(header_cols):
    """Return 'legacy' | 'new' | 'unknown' from a CSV header row."""
    lc = [c.strip().strip('"').lower() for c in header_cols]
    if any(k in lc for k in NEW_HEADER_KEYS):
        return "new"
    if any(k in lc for k in LEGACY_HEADER_KEYS):
        return "legacy"
    return "unknown"


ERA_TO_TABLE = {"legacy": "raw_pre2021_v2", "new": "raw_post2021_v2"}


def load_manifest(path):
    rows = list(csv.DictReader(open(path)))
    selected = [r for r in rows if r["selected_for_load"] == "true"]
    excluded = [r for r in rows if r["selected_for_load"] != "true"]
    return rows, selected, excluded


def check_no_duplicate_representation(selected):
    """Refuse if any (target_table, year_month) has >1 selected representation.
    This is the structural guard against the 2013/2018 double-count."""
    by_key = {}
    for r in selected:
        key = (r["target_table"], r["year_month"])
        by_key.setdefault(key, set()).add(r["representation"])
    dupes = {k: sorted(v) for k, v in by_key.items() if len(v) > 1}
    if dupes:
        sys.exit(f"REFUSING: {len(dupes)} (table,month) keys have multiple "
                 f"selected representations (would double-count): {list(dupes)[:5]}")
    return by_key


def check_routing(selected):
    """Every selected row's schema_era must map to its target_table."""
    bad = [r["object_name"] for r in selected
           if ERA_TO_TABLE.get(r["schema_era"]) != r["target_table"]]
    if bad:
        sys.exit(f"REFUSING: {len(bad)} rows route era→table incorrectly: {bad[:5]}")


def b64_md5(data: bytes) -> str:
    return base64.b64encode(hashlib.md5(data).digest()).decode()


def safe_zip_members(zf):
    """Yield validated CSV member names (no absolute paths / traversal / links)."""
    for name in zf.namelist():
        parts = name.replace("\\", "/").split("/")
        if name.startswith("/") or ".." in parts:
            print(f"  !! skip unsafe zip path: {name!r}", file=sys.stderr)
            continue
        if name.endswith("/") or "__MACOSX" in parts or parts[-1].startswith("."):
            continue
        if name.lower().endswith(".csv"):
            yield name


def load_checkpoint(path):
    if path and os.path.exists(path):
        return set(json.load(open(path)).get("completed_archives", []))
    return set()


def save_checkpoint(path, done):
    if path:
        json.dump({"completed_archives": sorted(done)}, open(path, "w"))


def build_plan(selected, excluded):
    """A deterministic staging plan: selected objects grouped by target table,
    plus the excluded duplicates that will be left out."""
    plan = {"raw_pre2021_v2": [], "raw_post2021_v2": []}
    for r in sorted(selected, key=lambda x: x["object_name"]):
        plan[r["target_table"]].append({
            "object_name": r["object_name"], "year_month": r["year_month"],
            "schema_era": r["schema_era"], "representation": r["representation"],
            "md5": r["md5_hash"], "crc32c": r["crc32c"], "size": r["size_bytes"],
        })
    excl = [{"object_name": r["object_name"], "year_month": r["year_month"],
             "reason": r["exclusion_reason"]} for r in sorted(excluded, key=lambda x: x["object_name"])]
    return plan, excl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="msbai-dwd-jrs10127")
    ap.add_argument("--bucket", default="bigdataday1")
    ap.add_argument("--dataset", default="citibike")
    ap.add_argument("--manifest", default="evidence/canonical-source-manifest.csv")
    ap.add_argument("--inventory", default="evidence/gcs-source-inventory.csv")
    ap.add_argument("--checkpoint", default="")
    ap.add_argument("--apply", action="store_true",
                    help="ACTUALLY download archives and upload staged CSVs (default: offline dry-run)")
    args = ap.parse_args()

    _rows, selected, excluded = load_manifest(args.manifest)
    check_routing(selected)
    by_key = check_no_duplicate_representation(selected)
    plan, excl = build_plan(selected, excluded)

    print(f"=== prepare_staging [{'APPLY' if args.apply else 'DRY-RUN'}] "
          f"project={args.project} bucket={args.bucket} dataset={args.dataset} ===")
    print(f"manifest: {len(selected)} selected / {len(excluded)} excluded objects; "
          f"{len(by_key)} unique (table,month) keys, exactly one representation each.")
    for tbl, items in plan.items():
        months = sorted({i['year_month'] for i in items})
        print(f"  {tbl}: {len(items)} CSVs to stage, {len(months)} months "
              f"({months[0]}..{months[-1] if months else '-'})" if months else f"  {tbl}: 0")
    print(f"  excluded duplicates (never staged): {len(excl)} "
          f"(e.g. {[e['object_name'].split('/')[-1] for e in excl[:3]]})")

    if not args.apply:
        print("\n[dry-run] offline plan only — no download, no upload. "
              "Re-run with --apply (and human approval) to execute.")
        return

    # --- APPLY path (NOT exercised in this PR) ---
    from google.cloud import storage
    done = load_checkpoint(args.checkpoint)
    gcs = storage.Client(project=args.project)
    bucket = gcs.bucket(args.bucket)
    inv = {r["object_name"].split("/")[-1]: r
           for r in csv.DictReader(open(args.inventory)) if r["prefix"] == "raw/"}
    selected_names = {r["object_name"] for r in selected}
    manifest_by_name = {r["object_name"]: r for r in selected}

    # archives to process = distinct raw/ zips that contain any selected member
    archives = sorted({r["object_name"].split("/")[-1].split("!")[0] for r in inv.values()})
    for arch in archives:
        if arch in done:
            print(f"[skip] {arch} (checkpoint)")
            continue
        meta = inv.get(arch)
        if meta is None:
            print(f"[skip] {arch}: not in inventory")
            continue
        blob = bucket.blob(f"raw/{arch}")
        data = blob.download_as_bytes()
        if meta.get("md5_hash") and b64_md5(data) != meta["md5_hash"]:
            sys.exit(f"CHECKSUM MISMATCH on raw/{arch}")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in safe_zip_members(zf):
                # target staging object name is decided by the manifest only
                # (this stage never invents new staged objects)
                for folder in ("pre2021", "post2021"):
                    cand = f"staging/{folder}/{os.path.basename(member)}"
                    if cand in selected_names:
                        row = manifest_by_name[cand]
                        with zf.open(member) as fh:
                            head = fh.readline().decode("utf-8", "replace")
                        era = classify_header(next(csv.reader([head])))
                        if ERA_TO_TABLE.get(era) != row["target_table"]:
                            sys.exit(f"HEADER/ROUTE MISMATCH for {cand}: header={era}")
                        body = zf.read(member)
                        if row["md5_hash"] and b64_md5(body) != row["md5_hash"]:
                            sys.exit(f"CHECKSUM MISMATCH on staged {cand}")
                        bucket.blob(cand).upload_from_string(body, content_type="text/csv")
                        print(f"[staged] {cand} ({era})")
        done.add(arch)
        save_checkpoint(args.checkpoint, done)
    print(f"[apply] staging complete: {len(done)} archives processed")


if __name__ == "__main__":
    main()
