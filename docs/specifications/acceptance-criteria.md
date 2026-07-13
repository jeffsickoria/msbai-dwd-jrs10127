# Acceptance Criteria — Correctness, Speed, Reach, Clarity

Labeled acceptance criteria for the Citi Bike + Weather data product. Each row
records the criterion, how it was measured, the result, where the evidence
lives, and **whether the criterion was defined before or after deployment**.

> Honesty note: the page-load **speed** target and the **clarity** criterion
> were defined **after** deployment to close omitted verification requirements.
> They are not back-dated and are not claimed to have been pre-registered. This
> file does not rewrite history.

## Correctness — defined during build (pre-deployment)
| Field | Value |
|---|---|
| Criterion | v2 daily counts reconcile with the official source; pipeline is loss-free and duplication-free; rider labels normalized; no missing dates. |
| Measurement | Reconciliation vs the course reference and the official Citi Bike archive (MD5-identical staged sources; DOT-published totals); zero-loss row accounting; structural checks (dup keys, null/neg, legacy labels). |
| Result | **PASS.** 2013 doubling fixed (ratio 1.0000), early-2015 gap fixed (0 missing dates), 0 `Customer`/`Subscriber`; official row counts equal the project in 24/26 target months (+0 rows); loads 308,193,797 rows = 308,193,797 daily trips. Course reference overcounts Apr 2018 (2×) and 2022/2023/May 2024 (~2.4–3.2%); project sides with the official archive + DOT. |
| Evidence | `docs/verification/v2-reconciliation.md`, `docs/verification/official-source-freshness.md`, `docs/execution/v2-build.md` |
| Status | **PASS** |
| When defined | **pre-deployment** |

## Speed — target defined AFTER deployment (post-hoc)
| Field | Value |
|---|---|
| Criterion | Cold load ≤ 20 s, warm refresh ≤ 10 s, on stable home Wi-Fi / wired broadband; "usable" = KPIs + first chart visible and controls respond. |
| Measurement | Independent unauthenticated browser tests (broadband + 5G), plus local headless health-check and server-side revision readiness. |
| Result | **PASS on broadband:** cold **6 s**, warm **3 s** (within target). Retained separately: **5G mobile** cold **37 s** / warm **17 s** (mobile latency/bandwidth + `minScale=0` cold start; not judged against the broadband target). |
| Evidence | `docs/execution/dashboard-v2-deployment.md` (External browser verification; Speed measurements) |
| Status | **PASS on broadband** (post-hoc target) |
| When defined | **post-deployment.** No page-load target was committed before deployment — a repo search found only measurements (local health 1.03 s), never an SLA. A future change should commit this target so it gates prospectively. |

## Reach — defined during deployment
| Field | Value |
|---|---|
| Criterion | Publicly reachable without login at the documented Cloud Run URL. |
| Measurement | Cloud Run IAM policy (`getIamPolicy`) + independent no-login browser tests. |
| Result | **PASS.** IAM binding `allUsers → roles/run.invoker`; independent testers opened the URL in Chrome Guest / no-login and it rendered. |
| Evidence | `docs/execution/dashboard-v2-deployment.md` (Public-access verification) |
| Status | **PASS** |
| When defined | **during deployment** |

## Clarity — criterion defined AFTER deployment (post-hoc)
| Field | Value |
|---|---|
| Criterion | **Every chart must display a one-sentence finding containing direction and magnitude, such that a non-technical visitor can state the chart's conclusion without inspecting code or the underlying data.** |
| Measurement | Static + AppTest check that each rendered chart is accompanied by a `**Finding:**` caption whose text is computed from the displayed data (not a fixed string) and names both a direction (more/fewer/higher/peak) and a magnitude (%, ×, or count). Generic statements ("ridership varies with temperature") do not satisfy it. |
| Result | **PASS.** All five charts emit data-derived findings, verified by `tests/test_chart_findings.py` and an AppTest run (e.g., "casual riders ride ~39% more on weekends"; "average daily trips run ~21% fewer on rainy and ~67% fewer on snowy days vs clear"). |
| Evidence | `app.py` (Finding captions), `tests/test_chart_findings.py`, `docs/verification/weather-model-v2.md` |
| Status | **PASS** — `tests/test_chart_findings.py` confirms all 5 charts satisfy it (AppTest, read-only). Not marked PASS on assertion alone; the app test is the gate. |
| When defined | **post-deployment** (post-hoc). Not a pre-registered requirement; being formalized after deployment. |

## Summary
Correctness and reach were established as part of the build/deploy and PASS.
Speed and clarity criteria were **added after deployment** to close omitted
requirements; both now PASS as measured, with the post-hoc status disclosed and
not back-dated.
