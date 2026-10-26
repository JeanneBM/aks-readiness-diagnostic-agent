# Evaluation protocol

## Research question

Does model-assisted diagnosis improve top-1 cause accuracy over a credible rules baseline on independently prepared evidence, without increasing unsupported conclusions?

This version evaluates diagnosis only. A recommended action is not executed. Therefore action coverage, executed-action risk, reversibility and rollback effectiveness cannot be measured here.

## Data contract

An evidence JSON contains schema=1, a generic target and observations. Each observation has a unique id, kind, source and text. Supported kinds: pod_status, probe_config, probe_result, app_log and limitation. Text is bounded per item and per bundle.

Keep the matching label in labels, with cause, required_evidence_ids, split and origin. Filenames join evidence and labels; labels are not passed to the model. Do not put the ground truth in the target, observation IDs or sources.

Development fixtures are transparent and synthetic. They deliberately exercise supported patterns, contradictions, missing context and injected instructions. They are not unseen cases and not a realistic benchmark.

## Scoring

| Field | Meaning |
| --- | --- |
| cause_correct | Exact taxonomy match against ground truth; abstention is correct only for an ambiguous case |
| rubric_evidence_covered | All required evidence IDs were cited; a proxy, not semantic entailment |
| appropriate_abstention | Whether an ambiguous case received insufficient_evidence; null on other cases |
| unsupported_conclusion | A non-abstaining conclusion with the wrong cause or missing required citations |
| ERROR | Provider/contract failure, including fabricated evidence IDs; never scored as a successful abstention |
| seconds | End-to-end diagnosis time for the variant on the recorded bundle |
| usage | Token totals actually reported by the provider; missing usage is not proof of zero cost |

Contract validation rejects unknown/duplicate citations, unknown causes and extra output fields. Recommendations remain unvalidated text. A correct cause and valid references do not guarantee that the prose or recommendation is sound. A human reviewer must judge that separately.

Summary JSON includes per-cause results and paired A1/C1 or A1/H comparisons. The exact two-sided McNemar calculation tests paired cause correctness, with errors counted as incorrect. It does not test safety, action risk or recommendation quality. Do not search many subsets and report only a favorable p-value.

## Freeze order

1. Develop fixtures, rules and prompts on data/dev. Use comparable effort for A1 and model prompts.
2. Review the cause taxonomy, label rubric and thresholds before the final evaluation.
3. Commit the frozen implementation and preserve a development freeze manifest.
4. Have an independent preparer create new held-out evidence and labels after that freeze. Include unknown formulations, noisy/stale messages, healthy controls and cases where there is insufficient evidence.
5. Produce a second run manifest over the held-out data. Verify that code/prompt/config hashes match the earlier freeze; only dataset hashes should differ. Preserve both manifests.
6. Run the held-out comparison once. Preserve every error and result. Any tuning afterward starts a separately named experiment.

The CLI requires a matching manifest if labels say held-out. It does not enforce independent authorship, prevent local dataset access or cryptographically prove chronology. Those are procedural requirements, not implemented guarantees.

## Proposed decision rule for the diagnostic stage

Freeze these thresholds before held-out preparation: C1 or H should improve cause accuracy by at least 15 percentage points over A1, increase unsupported conclusions by no more than 2 percentage points, and have paired exact McNemar p below 0.05. Also inspect evidence support and every high-impact incorrect recommendation.

These are proposed project criteria, not a statistical power guarantee. Choose sample size after a pilot and paired-disagreement assessment. Eighteen development fixtures cannot establish this result.

If diagnosis does not improve but explanations are useful under blinded human review, consider an explanation-only tool. If neither improves, retain rules and stop expansion. Passing this gate never enables live mutation: action safety requires a separate experiment.

## Evidence provenance and remaining work

The collector records selected sources but v1 does not include item timestamps, trust classifications, previous logs, revision diffs or metrics. It also cannot isolate which container produced a Pod-level readiness Event in a multi-container Pod. Use single-container demo Pods for the initial live replay.

Kubernetes API origin does not make log or Event text trustworthy. Explicit provenance, chronology and stronger snapshot recording are prerequisites for the broader phase-2 study. Treat current bundles as diagnostic inputs, not signed incident records.
