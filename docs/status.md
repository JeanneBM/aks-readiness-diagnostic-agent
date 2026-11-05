# Status

## Current scope

I have implemented a read-only diagnostic experiment: explicit rules, one-call model diagnosis, a rules-first cascade, evidence recording and replay. The runtime has no third-party dependencies. The project has no mutation executor and no independent held-out or live AKS validation.

## Verified milestones

| Date | Evidence | What it establishes |
| --- | --- | --- |
| 26 October 2026 | Offline contract, collector and scoring tests | Implementation consistency on development fixtures; not generalization |
| October 2026 | [CI run 40381715977](https://github.com/JeanneBM/aks-readiness-diagnostic-agent/actions/runs/40381715977) and preserved Go output | Native Go compilation, HTTP behavior and log contract |
| 2 November 2026 | [Kind recording run 41471820620](https://github.com/JeanneBM/aks-readiness-diagnostic-agent/actions/runs/41471820620), `data/recorded-dev/2026-11-02-kind` | Eight real, instrumented development cases and A1 24/24 attempts |
| 5 November 2026 | `eval/2026-11-05-kind-paired` | A1 24/24, C1 9/24 with ten provider errors, H 24/24 using only rules |
| 5 November 2026 | [Security run 42099987269](https://github.com/JeanneBM/aks-readiness-diagnostic-agent/actions/runs/42099987269) | CodeQL Python/Go, Trivy dependency/secret gates, RBAC contracts and allowed/denied kind checks |
| 5 November 2026 | `eval/2026-11-05-kind-paired/rubric-v2` | Post-hoc citation rescore: C1 conservative risk flags 6 → 3; accuracy and errors unchanged |

## Latest offline changes

Provider errors preserve safe HTTP/transport metadata. Request pacing is configurable, with no automatic retries. Python code fingerprints normalize LF/CRLF; exact dataset hashes and Python patch-version checks remain strict. Old freezes must be regenerated after these implementation changes.

Model citation schemas use only current bundle IDs. Displayed model recommendations come from fixed read-only templates; model-controlled summaries and uncertainty are still untrusted. Original pilot files remain unchanged. The revised rubric is a separately versioned development review.

## Remaining work

1. Add sparse/default-log recordings and ambiguous controls without designing labels to force a model advantage; test H fallback offline.
2. Preserve readiness transition times, Event timing/counts and avoid duplicate log payloads. Review temporal conflict handling before live collection claims.
3. Improve rules and model instructions fairly on development data. Review semantic evidence support separately from cause correctness and citation coverage.
4. Add Entra model authentication; key-based access remains available locally.
5. Obtain explicit authorization before another paid pilot. Then freeze implementation/runtime/model settings before independently prepared held-out data.

The historical ten provider errors have no HTTP status and cannot be retrospectively diagnosed. No superiority claim is justified by this pilot.
