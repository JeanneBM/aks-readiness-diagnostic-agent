# AKS Readiness Diagnostic Agent

**Can an LLM explain readiness failures better than explicit rules using the same evidence?**

A runnable, read-only diagnostic experiment with an explicit baseline, optional model adapter, rules-to-model cascade, recorded-evidence replay, bounded Kubernetes collector and disposable demo application.

**Status:** development implementation with synthetic fixtures. No held-out LLM advantage, live AKS validation or automated repair is claimed.

## Scope

| Input | Output |
| --- | --- |
| Pod readiness state, HTTP probe configuration, readiness failure Events and application logs | Proposed cause, evidence IDs, recommendation and uncertainty |
| Missing, ambiguous or conflicting evidence | Explicit insufficient-evidence outcome |

Initial causes: incorrect probe port, incorrect probe path and unavailable application dependency. Healthy and ambiguous controls are included. A dependency failure diagnosis does not establish whether DNS, networking, credentials or the service itself caused it.

There is no mutation executor. Recommendations are text, never executed commands.

## Start offline

Python 3.11 or newer. Run from the repository root:

```bash
python -m venv .venv
```

Activate on Windows Git Bash with `source .venv/Scripts/activate`, or on Linux/macOS with `source .venv/bin/activate`. Then:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m readiness_agent.cli diagnose data/dev/evidence/D001.json
python -m readiness_agent.cli evaluate --cases data/dev --variants A1 --output .local/runs/dev-001
```

Default commands make no Kubernetes or model requests. Existing result directories are never overwritten.

## Variants

| Variant | Implementation |
| --- | --- |
| A1 | Explicit rules over the recorded bundle; abstains outside known patterns |
| C1 | One model request over the same bundle |
| H | A1 first; C1 only when A1 abstains |

A1 is the initial transparent baseline, not a claim of the strongest possible rules engine. Improve rules and prompts on development data with comparable effort before freezing them. Model requests require provider configuration and an explicit flag.

## Evaluation rules

- Keep ground truth in separate label files. Models receive evidence only.
- Freeze rules, prompts and scoring before independent held-out preparation.
- Preserve provider and contract failures as ERROR, not correct abstentions.
- Measure cause accuracy, evidence-rubric coverage, abstention, unsupported conclusions, latency and reported tokens.
- Existing evidence IDs do not prove semantic support. Human review remains necessary.

The 18 committed fixtures are synthetic development examples, including ambiguous and injected-instruction cases. Passing them checks implementation consistency, not generalization or prompt-injection resistance.

## Local framework pilot

Uvicorn and Go applications, a separate HTTP dependency and a cross-platform recorder are provided under lab and tools. Start by checking local prerequisites:

```bash
python tools/run_local_lab.py check
```

Then follow docs/local-lab.md to record three faults plus a healthy control per framework on a dedicated kind cluster. Both variants replay the same actual recordings; no Azure provisioning is needed. Container builds and the full kind recording flow still require local verification.

Evaluation supports 1–10 repetitions, per-case agreement and schema-2 development preregistration for new held-out data. Contract-invalid model output, including invented evidence IDs, counts as diagnostic risk; provider failures remain separate errors.

## Repository contents

| Path | Purpose |
| --- | --- |
| src/readiness_agent | Contracts, rules, model adapter, collector, replay and CLI |
| data/dev/evidence | Synthetic input bundles |
| data/dev/labels | Separate scoring labels |
| tools/generate_dev_fixtures.py | Reproduce development fixtures in a new directory |
| tests | Offline contract, replay, collector and provider-adapter tests |
| demo | Disposable application, Dockerfile and Pod manifest |
| lab | Uvicorn and Go development workloads with a real HTTP dependency |
| tools/run_local_lab.py | Local preflight, recording, pilot replay and cleanup |
| docs/local-lab.md | Exact local pilot commands and verification limits |
| docs/usage.md | Commands and operating limits |
| docs/evaluation.md | Scoring, freezing and experiment boundaries |
| docs/phase-2.md | Broader experiment design and staged expansion |
| docs/status.md | Implemented, verified and pending work |
| .github/workflows/ci.yml | Offline checks on Python 3.11–3.13 |

## Boundaries

No Azure resources are provisioned or cluster permissions changed. Secret objects are never read. Logs may still contain sensitive data: inspect bundles before provider submission or publication. Redaction is best effort, not a confidentiality guarantee.

The provider adapter has no automatic retries. Model calls may incur charges; CI and default commands never make them.

Keep rules if they suffice. Use the model for explanations if that is its only demonstrated benefit. Automated remediation requires a separate safety and outcome evaluation.
