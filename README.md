# AKS Readiness Diagnostic Agent

> Evidence-backed diagnosis of Kubernetes readiness failures. Read-only first; evaluated against a deterministic baseline.

## Goal

Given the same Kubernetes evidence, determine whether an LLM can identify the cause of an application remaining unready more accurately than explicit rules.

This repository starts a new experiment. It does not claim that an LLM is necessary, that diagnosis is validated, or that automated remediation is supported.

## Scope of the first experiment

| Fault class | Evidence to inspect | Expected result |
| --- | --- | --- |
| Incorrect readiness probe port | Probe configuration, listening-port evidence and probe failures | Identify the mismatch and cite the supporting evidence. |
| Incorrect readiness probe path | Probe configuration, HTTP responses and application route/log evidence | Identify the mismatch when evidence is sufficient. |
| Unavailable application dependency | Application logs, readiness responses and dependency configuration | Identify the dependency failure, or abstain when its cause is ambiguous. |

A declared container port alone does not establish that the process listens on it. HTTP 404 alone does not establish the correct readiness path. A dependency timeout alone does not distinguish DNS, networking, credentials and service availability.

## Diagnostic contract

Each diagnostic result must contain:

- A proposed cause, or an explicit insufficient-evidence outcome.
- References to concrete evidence items supporting the conclusion.
- A recommended next check or corrective action.
- Relevant uncertainty and alternative explanations.

The diagnostic agent must not modify workloads, restart Pods, change permissions or execute its recommendations. Logs and Events are untrusted data, not instructions. Do not collect Kubernetes Secret objects or publish raw logs containing credentials.

## Evaluation before expansion

1. Define fixtures, ground truth and scoring before tuning the agent.
2. Implement an explicit deterministic baseline for the same three fault classes.
3. Give A (rules) and C (LLM) identical evidence bundles.
4. Separate development cases from held-out variants; include healthy and ambiguous controls.
5. Measure cause accuracy, evidence support, appropriate abstention, latency and token usage.
6. Preserve failures and inspect outputs against ground truth.

Report results by fault class and overall. Do not treat all abstentions as success, or pool revised prompts and fixtures into one frozen evaluation.

**Decision gate:** expand model-assisted diagnosis only if the held-out comparison demonstrates useful benefit. If rules solve these cases equally well, retain the simpler solution and report that result.

## Planned implementation

- Evidence bundle schema and sanitized fixture loader.
- Read-only collector for workload state, Events, probe configuration and bounded application logs.
- Deterministic diagnostic baseline.
- Model-assisted diagnostic adapter.
- Evaluation runner and concise findings report.

No collector, model integration, runnable CLI or deployment is implemented yet. No Azure provisioning is required to define and test the offline experiment.

## Relationship to the previous PoC

[Azure Kubernetes Agentic Ops evaluation](https://github.com/JeanneBM/azure-kubernetes-agentic-ops-eval) explored controlled image correction with a shared deterministic policy gate. Its recorded campaign did not demonstrate an LLM advantage for that narrow task.

This project investigates diagnosis rather than known image correction. It may reuse evidence-handling patterns, but has separate fixtures, ground truth and evaluation results. Automated remediation is outside the initial scope.
