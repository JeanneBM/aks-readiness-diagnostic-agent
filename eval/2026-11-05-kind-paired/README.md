# Recorded development model pilot — 5 November 2026

## Result

Eight preserved kind development cases, three repetitions each. These are known development data, not held-out validation. The user ran the pilot locally against an Azure deployment (alias redacted), reported as gpt-4.1-nano version 2025-04-14, GlobalStandard. The published manifest records a redacted deployment alias and API settings, not immutable model metadata.

| Variant | Correct attempts | Correct cases (majority) | Provider errors | Model calls | Reported tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| A1 | 24/24 | 8/8 | 0 | 0 | 0 |
| C1 | 9/24 | 3/8 | 10 | 24 | 14,297 |
| H | 24/24 | 8/8 | 0 | 0 | 0 |

H never invoked the model: its result tests the rules path only. C1 returned 14 valid responses: nine correct causes, three wrong causes and two insufficient-evidence answers on healthy snapshots. The ten provider failures remain in the overall denominator; they are not ten wrong diagnoses. The small development sample does not establish generalization or statistical superiority.

## Case review

| Case | Framework / ground truth | C1 outcomes across three attempts |
| --- | --- | --- |
| R001 | Uvicorn / healthy | healthy ×3 |
| R002 | Uvicorn / probe port mismatch | dependency unavailable ×3; wrong cause |
| R003 | Uvicorn / probe path mismatch | correct cause ×3; incomplete rubric evidence coverage |
| R004 | Uvicorn / dependency unavailable | correct cause ×3 |
| R005 | Go / healthy | insufficient evidence ×2, provider error ×1 |
| R006 | Go / probe port mismatch | provider error ×3 |
| R007 | Go / probe path mismatch | provider error ×3 |
| R008 | Go / dependency unavailable | provider error ×3 |

R002 confuses the probe connection refusal with a failed dependency and cites only `events`. R003 identifies the right cause, but cites `probe` and `logs` instead of covering all required rubric groups. The evaluator marks six attempts as unsupported/diagnostic risk: three R002 and three R003. This is a rubric-derived signal, not a human-verified count of hallucinations; a correct cause can still have incomplete citations. Only eight C1 attempts meet rubric evidence coverage.

The final ten C1 calls fail consecutively, starting at R005 repetition 3. This is consistent with a transient provider/rate-limit issue, but no HTTP status or retry-after is preserved. The archive cannot determine whether these were 429 responses or transport/other provider failures. Do not attribute the absent Go diagnoses to model quality.

## Provenance and checks

`sanitized/` contains 77 publication copies: 72 per-attempt records, manifest, run settings, consistency and summaries. All per-attempt files and summary files are byte-identical to the upload; only manifest metadata was redacted. The unmodified source ZIP is not published. No provider calls were made during this review. Summary totals were independently recomputed from per-attempt JSON; all 17 dataset hashes match the published 2026-11-02-kind dataset exactly. All eight code hashes match repository source when encoded with Windows CRLF line endings (the checkout uses LF). This byte-level difference does not indicate a code change.

The source ZIP is identified by `provenance.json`. The deployment alias is replaced with `deployment-redacted` and the endpoint hash is removed from the published manifest. No API key or raw endpoint is present. Source and published hashes plus transformations are recorded in provenance.json. The redacted manifest is historical provenance, not a ready-to-use model configuration or freeze. The reviewed outputs contain generic lab routes, evidence IDs and diagnoses, not raw customer logs. Original error metadata is deliberately preserved without invented details.

Reported pilot usage: 13,036 prompt tokens and 1,261 completion tokens. Ten error attempts have no usage metadata, so this is not a complete billing statement. A later single-call check reported in chat used 682 tokens and returned insufficient_evidence for R005; it is outside this archive and is not included in the pilot metrics or preserved as an original result file.

## Next work — offline first

1. Preserve structured provider diagnostics (HTTP status, bounded retry-after and safe transport category) without response bodies, credentials or URLs; validate with mocked HTTP failures.
2. Review evidence scoring and the R002/R003/R005 explanations; keep cause correctness separate from citation coverage and human semantic assessment.
3. Add configurable request pacing for a future explicitly authorized run; preserve errors and avoid silent retries. Do not rerun paid calls as part of this review.
4. After fair development improvements and an explicitly authorized follow-up pilot, freeze implementation/model settings before independently prepared held-out data.
