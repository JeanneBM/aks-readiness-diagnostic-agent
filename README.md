# AKS Readiness Diagnostic Agent

**A read-only Kubernetes readiness diagnostic experiment, validated on kind. AKS validation is pending.**

I compare explicit rules (A1), one model request (C1), and a rules-to-model cascade (H) on exactly the same recorded evidence. The question is whether a model improves diagnosis or explanation enough to justify its latency, cost and failure modes. Recommendations are displayed as text and never executed.

| Development pilot | Correct attempts | Provider failures | Model calls |
| --- | ---: | ---: | ---: |
| A1 — rules | 24/24 | 0 | 0 |
| C1 — gpt-4.1-nano | 9/24 | 10 | 24 |
| H — cascade | 24/24 | 0 | 0 |

Eight instrumented Uvicorn/Go cases, three repetitions each. **These results do not establish that rules outperform LLMs generally.** A1 was developed against these lab patterns. H never reached the model. Ten C1 requests failed without preserved HTTP details; missing Go answers cannot be attributed to model quality. There is no independent held-out result.

[Original pilot and provenance](eval/2026-11-05-kind-paired) · [Post-hoc citation review](eval/2026-11-05-kind-paired/rubric-v2) · [Current status](docs/status.md)

## Architecture

Read-only collection feeds the same evidence to rules (A1), a model (C1) or a rules-first cascade (H). Replay uses recorded evidence without cluster access. No branch executes a repair.

```mermaid
flowchart TD
  K8S[("Kubernetes API")] -->|"read-only kubectl"| COL["Evidence collector"]
  COL --> B[("Recorded evidence bundle")]
  subgraph LOCAL["Local diagnosis and evaluation"]
    B --> R["A1 rules or H rules-first"]
    B --> C["C1 model diagnosis"]
    R -->|"H abstains"| C
    R --> V["Validate contract and score against labels"]
    C --> V
    V --> OUT["Diagnosis, cited evidence and fixed advice"]
    V --> REPORT["Per-run evaluation report"]
  end
  C --> MODEL["Optional Azure OpenAI or OpenAI"]
  MODEL --> C
```

Evidence and ground-truth labels stay separate. Scoring distinguishes cause correctness and citation coverage; a valid evidence ID alone does not prove semantic support. Provider failures stay in the denominator. Repetitions measure consistency, while paired comparisons use eight cases, not 24 independent samples.

## Replay without a cluster or model

Python 3.11+. From the repository root:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python tools/run_local_lab.py pilot --cases data/recorded-dev/2026-11-02-kind --output .local/runs/a1-replay --variants A1 --repetitions 3
```

Use a new output directory each time. This makes no model requests. Eighteen additional fixtures under `data/dev` are synthetic regression examples, not independent validation.

## Citation review: preserve the original result

R003's access log contains both the registered readiness route and the failing 404 request. The original rubric unnecessarily also required the Event ID. A documented post-hoc rubric revision accepts `probe` plus `logs` or `startup` for this case. Rescoring the saved responses reduces the conservative C1 risk flags from six to three; cause accuracy and provider errors are unchanged. This is a development correction after observing outputs, not preregistered confirmation.

```bash
python tools/rescore_recorded_pilot.py --output .local/review/rubric-v2.json
```

The original evidence, labels and result files remain unchanged. New model recommendations use fixed, read-only templates, while dynamic strict schemas restrict citation IDs to the current bundle. Summary and uncertainty text remain untrusted model output.

## Phase 2: is a model suitable at all? (preregistered, not yet run)

The first pilot could not answer the question this repository exists for, because every recorded case matched the rules' patterns and H never consulted the model. [docs/phase-2-protocol.md](docs/phase-2-protocol.md) preregisters a 13-case matrix in three cohorts, with the decision rule committed before any recording or model request:

| Cohort | Cases | What the evidence looks like | Expected A1 | What the model must do |
| --- | ---: | --- | --- | --- |
| in-pattern | 3 | Formats the rules were written for | correct | match the rules |
| out-of-pattern | 6 | Same faults; Go JSON logs and a Node service the rules do not parse | abstains | recover the cause with valid citations |
| control | 4 | Probe timeouts and `--log-level warning` runs where no cause is supported | abstains | abstain, despite decoy signals |

Verdicts are `SUITABLE_STANDALONE`, `SUITABLE_AS_FALLBACK`, `NOT_SUITABLE` or `INCONCLUSIVE`; `tools/phase2_gate.py` applies the thresholds mechanically. A negative result is published with the same prominence as a positive one. The matrix is recorded by the [kind phase 2 workflow](.github/workflows/kind-phase2.yml) (`--matrix phase2`); `data/dev-phase2-synthetic` is the same matrix assembled offline from real captured application logs for regression tests only, never for the reported result.

```bash
readiness-agent evaluate --cases data/dev-phase2-synthetic --variants A1 --output .local/runs/phase2-a1-offline
```

A1 solves 3 of 3 in-pattern cases, abstains on all 6 out-of-pattern cases and abstains correctly on all 4 controls. That is the floor the model is measured against.

## Run and inspect

- [Local recorder and cleanup](docs/local-lab.md): dedicated kind lab, not Azure provisioning.
- [Usage and provider configuration](docs/usage.md): paid calls require an explicit flag.
- [Evaluation and freeze](docs/evaluation.md): code hashes normalize Python line endings; dataset bytes remain exact. Python patch versions stay strict.
- [Security](docs/security.md): collector RBAC, CodeQL, Trivy and authorization checks.
- [GitHub recording workflow](docs/github-actions-pilot.md): eight real development recordings and A1 replay.
- [Phase 2 protocol](docs/phase-2-protocol.md): preregistered LLM-suitability matrix, thresholds and limits.

## Boundaries

The collector reads named Pods, Events and logs; it does not read Secret objects or mutate workloads. It uses the credentials of the explicitly selected kubeconfig context; restricted RBAC requires a dedicated identity. Review logs before provider submission: pattern-based redaction is incomplete, and prompt-injection resistance is not established. The adapter has no automatic retries. Entra model authentication, temporally aware evidence, built-image scanning and live AKS validation remain pending. A green pipeline does not establish production readiness.
