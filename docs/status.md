# Implementation status

## Implemented

- Installable Python package and CLI with no runtime third-party dependencies.
- Validated evidence/diagnosis contracts with separate ground truth.
- Explicit A1 baseline, optional C1 provider adapter and H cascade.
- Replay results, per-cause metrics, exact paired comparisons and drift manifests.
- Eighteen reproducible synthetic development fixtures, including ambiguous and injected-instruction examples.
- Explicitly enabled, bounded read-only kubectl collection.
- Disposable HTTP demo application and Pod manifest.
- Offline automated tests and CI configuration for Python 3.11–3.13.
- Schema-2 preregistration: frozen implementation checked separately from held-out dataset hashes.
- Repeated replay, case-level agreement and paired majority-correct comparisons without pseudoreplication.
- Contract errors included in diagnostic risk, separate provider errors and nullable evidence applicability.
- Sorted Events plus a bounded startup log prefix and explicit empty-window limitations.
- Uvicorn and Go workloads, real HTTP dependency and local kind recorder/pilot/cleanup commands.

## Recorded development pilot — verified 5 November 2026

[Actions run 41471820620](https://github.com/JeanneBM/aks-readiness-diagnostic-agent/actions/runs/41471820620) completed successfully on 2 November: eight real kind cases covering healthy, port, path and dependency scenarios for Uvicorn and Go. Anonymized evidence and separate labels are preserved in data/recorded-dev/2026-11-02-kind; source identity, hashes and original/sanitized A1 results are in eval/2026-11-02-kind.

A fresh replay on 5 November reproduced 24/24 correct A1 attempts across eight cases and three repetitions, with zero errors, zero unsupported conclusions and zero model calls. This verifies replay of known development cases. The first C1/H pilot is now preserved in [eval/2026-11-05-kind-paired](../eval/2026-11-05-kind-paired): C1 9/24 correct attempts, ten provider errors; H 24/24 using rules only. Held-out evaluation and live AKS validation remain pending.

## Historical verification boundary

Local verification on 26 October 2026: 40 automated tests passed, including preregistration, repeated scoring, citation-risk handling, startup-log preservation and ASGI response logic. A1 still matches the 18 synthetic regression labels. These are implementation checks, not a held-out result or evidence that A1 generalizes.

Offline tests use mocked provider and kubectl responses. Development replay checks known fixtures. A working adapter or mock is not a successful live provider integration. A Pod manifest is not evidence that a workload has run on AKS.

No live model call, cluster collection, cloud provisioning or automatic mutation was performed while preparing this repository. Independent held-out evaluation, human explanation review and any generalization claim remain pending.

Docker, kind, kubectl and Go were unavailable here. Container builds, Go compilation and the full eight-case recording pipeline require local verification; no fabricated recording results are committed. Entra authentication and a multi-step C2 tool loop remain outside the current implementation.

Follow-up: the Go application now explicitly selects slog.TextHandler. A historical real-output golden regression and a native-go CI capture check guard the baseline/recorder log contract. Refusals and truncated/filtered output are reported separately from invalid diagnoses; the conservative risk aggregate remains explicit. The development recorder must not be used as a natural-log held-out generator.

Local follow-up verification: 44 tests discovered, 43 passed and one native-process test skipped because no fresh compiled Go capture was available. The native-go job supplies that capture; its success must be checked separately before claiming Go integration validation.

Verified CI follow-up: workflow run 40381715977 passed Python 3.11, 3.12 and 3.13 checks and native-go compilation/capture tests. Actual Go process output and provenance were retrieved from artifact 12679415721 and preserved under tests/golden. This confirms the Go log contract and real HTTP status behavior; it does not validate Docker images, kind recording or model quality. After adding that captured-output regression, local verification found 45 tests: 44 passed and one fresh-process test skipped without a local Go toolchain.

The repository now includes anonymized real development cluster evidence from the owned kind lab; it contains no recorded customer evidence. Generated local runs belong under .local and are ignored by Git. The earlier environment limitations above are historical; the successful runner-based recording supersedes the pending kind verification.

## Next experiment

1. Review the preserved eight-case dataset and provenance; use the committed recordings rather than collecting them again.
2. Review the preserved paired pilot explanations and evidence rubric; decide on fair development improvements before any explicitly authorized paid follow-up.
3. Strengthen A1 and model prompts fairly, then freeze them.
4. Independently prepare held-out cases and run the paired diagnostic evaluation.
5. Decide whether to keep rules, add an explanation-only assistant or justify a separate remediation stage.

## Offline follow-up — 5 November 2026

Added safe provider error metadata, configurable request pacing (0–60 seconds, no automatic retries) and separate cause-mismatch/citation-gap fields while preserving existing risk scoring. Offline verification: 56 tests discovered, 55 passed, one fresh native-Go capture test skipped. New tests cover HTTP 429 persistence, metadata redaction, transport categories, pacing after failures and the recorded R003 citation gap. No live provider requests were made. Historical pilot files are unchanged; the ten historical provider errors remain unexplained.
