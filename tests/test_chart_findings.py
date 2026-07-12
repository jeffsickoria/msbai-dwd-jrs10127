"""Clarity acceptance check: every rendered chart must show a visible, data-
derived one-sentence finding with a direction and a magnitude.

This drives the real app via Streamlit AppTest, so it needs read-only BigQuery
access. It SKIPS cleanly (exit 0) when credentials are absent so a credential-
less CI does not fail. Run: python3 tests/test_chart_findings.py
"""
import os
import re
import sys

DIRECTION = re.compile(r"\b(more|fewer|less|higher|lower|peaks?|above|below|rose|rise|climbs?|falls?|drop)\b", re.I)
MAGNITUDE = re.compile(r"(\d[\d,]*\.?\d*\s*(%|×|x)|\b\d[\d,]{2,}\b|\d+\.\d+×)")
BANNED = "ridership varies with temperature"


def main():
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print("SKIP test_chart_findings: no GOOGLE_APPLICATION_CREDENTIALS (needs read-only BigQuery)")
        return 0
    os.environ.setdefault("CITIBIKE_SOURCE_MODE", "v2")
    os.environ.setdefault("GCP_PROJECT", "msbai-dwd-jrs10127")
    from streamlit.testing.v1 import AppTest

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(root)              # so `from query import ...` resolves like production
    if root not in sys.path:
        sys.path.insert(0, root)
    at = AppTest.from_file("app.py", default_timeout=240)
    at.run()

    errs = [e.value for e in at.error] + [e.value for e in at.exception]
    assert not errs, f"app raised: {errs}"

    caps = [c.value for c in at.caption]
    findings = [c for c in caps if c.strip().startswith("**Finding:**")]
    # There are 5 charts (KPIs excluded): trend+temp, temp-response, day-of-week,
    # weather impact, model. Each must carry exactly one finding.
    n_charts = 5
    assert len(findings) >= n_charts, f"expected >= {n_charts} findings, got {len(findings)}: {findings}"

    for f in findings:
        low = f.lower()
        assert BANNED not in low, f"generic banned finding: {f}"
        assert DIRECTION.search(f), f"finding lacks a direction word: {f}"
        assert MAGNITUDE.search(f), f"finding lacks a magnitude: {f}"

    print(f"PASS test_chart_findings: {len(findings)} data-derived findings, "
          f"each with direction + magnitude, no generic claims")
    return 0


if __name__ == "__main__":
    sys.exit(main())
