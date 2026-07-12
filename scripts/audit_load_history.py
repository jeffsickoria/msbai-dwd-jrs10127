#!/usr/bin/env python3
"""Audit BigQuery load-job history and GCS source objects for the Citibike project.

READ-ONLY. Lists BigQuery load jobs and Cloud Storage object metadata, writes two
deterministic evidence CSVs, and prints a duplicate / overlap analysis used to
diagnose the 2013 / 2018 double-counting and the 2015 gap.

It never creates, modifies, reloads, or deletes any cloud object. For staging CSVs
it performs only tiny HTTP Range reads (header + first data row) — never full
downloads.

Auth: expects an OAuth access token in $GCP_ACCESS_TOKEN (e.g. from the
cloud-bootstrap service account). Usage:

    GCP_ACCESS_TOKEN=$(...) python3 scripts/audit_load_history.py \
        --project msbai-dwd-jrs10127 --bucket bigdataday1 \
        --out-dir evidence [--sample-staging]
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request

BQ = "https://bigquery.googleapis.com/bigquery/v2"
GCS = "https://storage.googleapis.com/storage/v1"
GCS_DL = "https://storage.googleapis.com"

RAW_TABLES = ("raw_pre2021", "raw_post2021")
YEAR_RE = re.compile(r"(20\d{2})")
YM_RE = re.compile(r"(20\d{2})(\d{2})")


def _get(url, token, range_header=None):
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    if range_header:
        req.add_header("Range", range_header)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _get_json(url, token):
    return json.loads(_get(url, token))


# ---------------------------------------------------------------------------
# BigQuery load-job history (via jobs.list; INFORMATION_SCHEMA.JOBS needs
# project-level jobs.listAll which the restricted service account lacks).
# ---------------------------------------------------------------------------
def list_load_jobs(project, token):
    jobs, page = [], ""
    for _ in range(50):
        url = (f"{BQ}/projects/{project}/jobs?allUsers=true&maxResults=100"
               f"&projection=full{page}")
        data = _get_json(url, token)
        for j in data.get("jobs", []):
            if j.get("configuration", {}).get("jobType") == "LOAD":
                jobs.append(j)
        nxt = data.get("nextPageToken")
        if not nxt:
            break
        page = "&pageToken=" + urllib.parse.quote(nxt)
    return jobs


def load_job_row(j):
    cfg = j.get("configuration", {}).get("load", {})
    st = j.get("statistics", {})
    ld = st.get("load", {})
    dest = cfg.get("destinationTable", {})
    return {
        "job_id": j.get("jobReference", {}).get("jobId", ""),
        "creation_time_ms": st.get("creationTime", ""),
        "start_time_ms": st.get("startTime", ""),
        "end_time_ms": st.get("endTime", ""),
        "destination_table": ".".join(
            [dest.get("projectId", ""), dest.get("datasetId", ""),
             dest.get("tableId", "")]),
        "source_uris": "|".join(cfg.get("sourceUris", []) or []),
        "source_format": cfg.get("sourceFormat", ""),
        "write_disposition": cfg.get("writeDisposition", ""),
        "create_disposition": cfg.get("createDisposition", ""),
        "schema_update_options": "|".join(cfg.get("schemaUpdateOptions", []) or []),
        "skip_leading_rows": cfg.get("skipLeadingRows", ""),
        "max_bad_records": cfg.get("maxBadRecords", ""),
        "autodetect": cfg.get("autodetect", ""),
        "input_files": ld.get("inputFiles", ""),
        "input_bytes": ld.get("inputFileBytes", ""),
        "output_rows": ld.get("outputRows", ""),
        "bad_records": ld.get("badRecords", ""),
        "state": j.get("status", {}).get("state", ""),
        "error": (j.get("status", {}).get("errorResult", {}) or {}).get("message", ""),
    }


# ---------------------------------------------------------------------------
# GCS object inventory
# ---------------------------------------------------------------------------
def list_objects(bucket, token):
    items, page = [], ""
    for _ in range(50):
        url = (f"{GCS}/b/{bucket}/o?maxResults=1000"
               "&fields=items(name,size,updated,generation,md5Hash,crc32c,"
               f"contentType),nextPageToken{page}")
        data = _get_json(url, token)
        items.extend(data.get("items", []))
        nxt = data.get("nextPageToken")
        if not nxt:
            break
        page = "&pageToken=" + urllib.parse.quote(nxt)
    return items


def infer_era(prefix, name):
    if "pre2021" in prefix:
        return "pre2021"
    if "post2021" in prefix:
        return "post2021"
    return "raw_archive"


def normalize_base(name):
    b = name.rsplit("/", 1)[-1]
    # strip split suffixes like _1 / _2 / .csv_1 and the extension
    b = re.sub(r"\.csv(\.csv)?$", "", b, flags=re.I)
    b = re.sub(r"_\d+$", "", b)
    b = re.sub(r"\.csv$", "", b, flags=re.I)
    return b


def object_row(o):
    name = o["name"]
    prefix = name.rsplit("/", 1)[0] + "/" if "/" in name else "(root)"
    base = name.rsplit("/", 1)[-1]
    ym = YM_RE.search(base)
    year = ym.group(1) if ym else (YEAR_RE.search(base).group(1)
                                   if YEAR_RE.search(base) else "")
    month = ym.group(2) if ym else ""
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    return {
        "object_name": name,
        "prefix": prefix,
        "size_bytes": o.get("size", ""),
        "updated": o.get("updated", ""),
        "generation": o.get("generation", ""),
        "md5_hash": o.get("md5Hash", ""),
        "crc32c": o.get("crc32c", ""),
        "inferred_year": year,
        "inferred_month": month,
        "file_extension": ext,
        "normalized_base": normalize_base(name),
        "schema_era": infer_era(prefix, name),
    }


def sample_staging(bucket, name, token):
    """Tiny Range read: first ~2 KB (header + first data row). No full download."""
    url = f"{GCS_DL}/{bucket}/{urllib.parse.quote(name)}"
    try:
        head = _get(url, token, range_header="bytes=0-2047").decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return {"header": f"<range read failed: {e}>", "first_row": ""}
    lines = head.splitlines()
    return {"header": lines[0] if lines else "",
            "first_row": lines[1] if len(lines) > 1 else ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--out-dir", default="evidence")
    ap.add_argument("--sample-staging", action="store_true",
                    help="tiny Range reads of staging CSV headers/first rows")
    args = ap.parse_args()

    token = os.environ.get("GCP_ACCESS_TOKEN")
    if not token:
        sys.exit("ERROR: set GCP_ACCESS_TOKEN (read-only access token).")

    os.makedirs(args.out_dir, exist_ok=True)

    # ---- load jobs ----
    jobs = [load_job_row(j) for j in list_load_jobs(args.project, token)]
    jobs.sort(key=lambda r: r["creation_time_ms"])
    job_cols = list(jobs[0].keys()) if jobs else []
    with open(os.path.join(args.out_dir, "bigquery-load-jobs.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=job_cols)
        w.writeheader()
        w.writerows(jobs)
    print(f"[load-jobs] {len(jobs)} load jobs written")

    # ---- gcs inventory ----
    objs = [object_row(o) for o in list_objects(args.bucket, token)]
    objs.sort(key=lambda r: r["object_name"])
    obj_cols = list(objs[0].keys()) if objs else []
    with open(os.path.join(args.out_dir, "gcs-source-inventory.csv"), "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=obj_cols)
        w.writeheader()
        w.writerows(objs)
    print(f"[gcs] {len(objs)} objects written")

    # ---- detections ----
    def in_staging(r):
        return r["schema_era"] in ("pre2021", "post2021")

    staging = [r for r in objs if in_staging(r)]

    dup_hash = {}
    for r in staging:
        if r["md5_hash"]:
            dup_hash.setdefault(r["md5_hash"], []).append(r["object_name"])
    dup_hash = {k: v for k, v in dup_hash.items() if len(v) > 1}

    ym_folder = {}
    for r in staging:
        if r["inferred_year"] and r["inferred_month"]:
            key = (r["inferred_year"] + r["inferred_month"])
            ym_folder.setdefault(key, {"pre2021": [], "post2021": []})
            ym_folder[key][r["schema_era"]].append(r["object_name"])

    overlap_months = {k: v for k, v in ym_folder.items()
                      if v["pre2021"] and v["post2021"]}

    print("\n=== DETECTIONS ===")
    print(f"identical-hash duplicate groups (staging): {len(dup_hash)}")
    for h, names in list(dup_hash.items())[:20]:
        print(f"  md5 {h}: {names}")
    print(f"\nmonths present in BOTH pre2021 and post2021 staging: "
          f"{len(overlap_months)}")
    for k in sorted(overlap_months)[:40]:
        print(f"  {k}: pre={len(overlap_months[k]['pre2021'])} "
              f"post={len(overlap_months[k]['post2021'])}")

    # coverage by year x folder
    cov = {}
    for r in staging:
        if r["inferred_year"]:
            cov.setdefault(r["inferred_year"], {"pre2021": 0, "post2021": 0})
            cov[r["inferred_year"]][r["schema_era"]] += 1
    print("\nstaging file counts by year x folder:")
    for y in sorted(cov):
        print(f"  {y}: pre2021={cov[y]['pre2021']:3d} post2021={cov[y]['post2021']:3d}")

    if args.sample_staging:
        print("\n=== STAGING SAMPLES (tiny Range reads) ===")
        for r in staging:
            s = sample_staging(args.bucket, r["object_name"], token)
            print(f"\n{r['object_name']}\n  header: {s['header'][:200]}"
                  f"\n  row1:   {s['first_row'][:200]}")


if __name__ == "__main__":
    main()
