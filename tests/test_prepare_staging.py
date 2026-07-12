"""Unit tests for scripts/prepare_staging.py — small in-memory fixtures, no
cloud. Run: python3 tests/test_prepare_staging.py"""
import csv
import io
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import prepare_staging as P  # noqa: E402

MANIFEST_COLS = ["object_uri", "object_name", "gcs_folder", "year_month",
                 "inferred_year", "schema_era", "representation", "size_bytes",
                 "md5_hash", "crc32c", "generation", "target_table",
                 "selected_for_load", "exclusion_reason"]


def _write_manifest(rows):
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in MANIFEST_COLS})
    return path


def _row(name, ym, era, rep, sel, table, reason=""):
    return {"object_name": name, "object_uri": "gs://b/" + name, "year_month": ym,
            "schema_era": era, "representation": rep, "selected_for_load": sel,
            "target_table": table, "exclusion_reason": reason,
            "md5_hash": "", "crc32c": "", "size_bytes": "1"}


def test_classify_header():
    assert P.classify_header(["ride_id", "started_at", "member_casual"]) == "new"
    assert P.classify_header(["tripduration", "starttime", "usertype"]) == "legacy"
    assert P.classify_header(["Trip Duration", "Start Time"]) == "legacy"
    assert P.classify_header(["foo", "bar"]) == "unknown"


def test_dup_representation_blocked():
    rows = [
        _row("staging/pre2021/201804-citibike-tripdata.csv", "2018-04", "legacy", "full-month", "true", "raw_pre2021_v2"),
        _row("staging/pre2021/201804-citibike-tripdata_1.csv", "2018-04", "legacy", "chunk", "true", "raw_pre2021_v2"),
    ]
    _, selected, _ = P.load_manifest(_write_manifest(rows))
    blocked = False
    try:
        P.check_no_duplicate_representation(selected)
    except SystemExit:
        blocked = True
    assert blocked, "must refuse two selected representations of the same (table,month)"


def test_dup_excluded_ok():
    rows = [
        _row("staging/pre2021/201804-citibike-tripdata.csv", "2018-04", "legacy", "full-month", "true", "raw_pre2021_v2"),
        _row("staging/pre2021/201804-citibike-tripdata_1.csv", "2018-04", "legacy", "chunk", "false", "raw_pre2021_v2", "duplicate"),
    ]
    _, selected, excluded = P.load_manifest(_write_manifest(rows))
    by_key = P.check_no_duplicate_representation(selected)  # no raise
    assert by_key[("raw_pre2021_v2", "2018-04")] == {"full-month"}
    assert len(excluded) == 1


def test_routing_mismatch_blocked():
    rows = [_row("staging/post2021/x.csv", "2020-01", "new", "chunk", "true", "raw_pre2021_v2")]  # wrong table
    _, selected, _ = P.load_manifest(_write_manifest(rows))
    blocked = False
    try:
        P.check_routing(selected)
    except SystemExit:
        blocked = True
    assert blocked, "new era routed to pre table must be refused"


def test_build_plan_groups_and_excludes():
    rows = [
        _row("staging/pre2021/201306-citibike-tripdata.csv", "2013-06", "legacy", "full-month", "true", "raw_pre2021_v2"),
        _row("staging/post2021/202001-citibike-tripdata_1.csv", "2020-01", "new", "chunk", "true", "raw_post2021_v2"),
        _row("staging/pre2021/201804-citibike-tripdata_1.csv", "2018-04", "legacy", "chunk", "false", "raw_pre2021_v2", "dup"),
    ]
    _, selected, excluded = P.load_manifest(_write_manifest(rows))
    plan, excl = P.build_plan(selected, excluded)
    assert len(plan["raw_pre2021_v2"]) == 1 and len(plan["raw_post2021_v2"]) == 1
    assert len(excl) == 1 and excl[0]["reason"] == "dup"


def test_safe_zip_members_filters_traversal():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("good.csv", "ride_id\n1\n")
        zf.writestr("nested/ok.csv", "starttime\n2020\n")
        zf.writestr("__MACOSX/junk.csv", "x")
    with zipfile.ZipFile(buf) as zf:
        members = list(P.safe_zip_members(zf))
    assert "good.csv" in members and "nested/ok.csv" in members
    assert not any("MACOSX" in m for m in members)


def test_checkpoint_roundtrip_and_skip():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    assert P.load_checkpoint(path) == set()
    P.save_checkpoint(path, {"2013-citibike-tripdata.zip"})
    done = P.load_checkpoint(path)
    assert "2013-citibike-tripdata.zip" in done


def test_b64_md5_matches_hashlib():
    import base64, hashlib
    data = b"hello world"
    assert P.b64_md5(data) == base64.b64encode(hashlib.md5(data).digest()).decode()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
