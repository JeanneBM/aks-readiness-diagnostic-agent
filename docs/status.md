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

## Verification boundary

Local verification on 26 October 2026: 40 automated tests passed, including preregistration, repeated scoring, citation-risk handling, startup-log preservation and ASGI response logic. A1 still matches the 18 synthetic regression labels. These are implementation checks, not a held-out result or evidence that A1 generalizes.

Offline tests use mocked provider and kubectl responses. Development replay checks known fixtures. A working adapter or mock is not a successful live provider integration. A Pod manifest is not evidence that a workload has run on AKS.

No live model call, cluster collection, cloud provisioning or automatic mutation was performed while preparing this repository. Independent held-out evaluation, human explanation review and any generalization claim remain pending.

Docker, kind, kubectl and Go were unavailable here. Container builds, Go compilation and the full eight-case recording pipeline require local verification; no fabricated recording results are committed. Entra authentication and a multi-step C2 tool loop remain outside the current implementation.

The repository contains no credentials and no recorded real customer or cluster evidence. Generated local runs belong under .local and are ignored by Git.

## Next experiment

1. Check prerequisites and record the local Uvicorn/Go development cases with tools/run_local_lab.py.
2. Inspect evidence, run A1, then run a repeated C1/H pilot with an explicitly configured provider.
3. Strengthen A1 and model prompts fairly, then freeze them.
4. Independently prepare held-out cases and run the paired diagnostic evaluation.
5. Decide whether to keep rules, add an explanation-only assistant or justify a separate remediation stage.
