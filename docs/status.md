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

## Verification boundary

Local verification on 26 October 2026: 22 automated tests passed; A1 matched all 18 synthetic development labels with zero model calls. These are implementation checks on known examples, not a held-out result or evidence that A1 generalizes.

Offline tests use mocked provider and kubectl responses. Development replay checks known fixtures. A working adapter or mock is not a successful live provider integration. A Pod manifest is not evidence that a workload has run on AKS.

No live model call, cluster collection, cloud provisioning or automatic mutation was performed while preparing this repository. Independent held-out evaluation, human explanation review and any generalization claim remain pending.

The repository contains no credentials and no recorded real customer or cluster evidence. Generated local runs belong under .local and are ignored by Git.

## Next experiment

1. Run A1 locally and inspect outputs.
2. Run a small development C1/H comparison with an explicitly configured provider.
3. Strengthen A1 and model prompts fairly, then freeze them.
4. Independently prepare held-out cases and run the paired diagnostic evaluation.
5. Decide whether to keep rules, add an explanation-only assistant or justify a separate remediation stage.
