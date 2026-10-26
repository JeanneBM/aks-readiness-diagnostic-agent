# Evaluation protocol

## Question and scope

Does model-assisted diagnosis improve top-1 cause accuracy over a credible rules baseline, without increasing unsupported conclusions? This repository evaluates diagnosis, not executed repair or action safety.

The committed 18 synthetic fixtures are regression tests. Recorded Uvicorn/Go cases are development data. Neither is an independent benchmark. Framework conventions alone do not establish a listening port or an enabled endpoint.

## Inputs and labels

Evidence contains schema=1, a generic target and observations with id, kind, source and text. Labels are stored separately. They contain cause, required_evidence_ids, split and origin; optional framework/scenario fields remain outside the model input.

Optional evidence_options lists alternative citation groups: all required_evidence_ids and at least one complete alternative group must be cited. This avoids penalizing an answer that cites an equally valid startup or recent-log observation.

Labels describe the injected setup and require human verification. Missing required evidence makes recording fail rather than silently inventing support.

## Metrics and errors

| Metric | Meaning |
| --- | --- |
| cause_correct | Exact top-1 taxonomy match; abstention is correct only on an ambiguous case |
| rubric_evidence_covered | Required and alternative citation rubric satisfied; null if not applicable |
| rubric_evidence_applicable | Denominator for evidence-rubric coverage, including failed responses on applicable cases |
| unsupported_conclusion | Wrong/non-supported non-abstaining conclusion, or contract-invalid output |
| diagnostic_risk | Conservative composite: unsupported conclusions, invalid output and no completed answer; inspect its separate components |
| PROVIDER_ERROR | HTTP/transport failure without a usable response; counts as incorrect, reported separately from diagnostic risk |
| CONTRACT_ERROR | Invalid or fabricated output; counts as incorrect and diagnostic risk |
| MODEL_NO_ANSWER | Refusal, truncation, filtering or incomplete generation; no completed diagnosis, not labeled an unsupported conclusion |
| EXECUTION_ERROR | Other adapter/runtime failure; counts as incorrect, remains visible |
| usage | Only tokens actually reported; missing usage is not zero cost |
| seconds | Wall time for one diagnosis attempt |

Existing IDs and a matching cause do not prove that prose or recommendations are sound. Human review remains necessary. Recommendations are not executed.

summary.md exposes Invalid output and No answer separately. summary.json additionally reports refusals, truncated_outputs and filtered_outputs. The conservative risk aggregate still includes non-answers to avoid silently relaxing the frozen decision rule. It must not be described as the rate of wrong diagnoses or harmful actions. A later study may preregister separate risk/availability thresholds, but must not change them after observing held-out outcomes.

## Repetitions and paired inference

Use --repetitions 3 for a pilot; supported range is 1–10. Record each attempt separately. C1 and H make independent requests; a maximum of two model calls per case/repetition is possible when both are selected.

consistency.json reports valid-response counts, cause counts, cause agreement and the absolute-majority cause. Agreement is the most frequent valid cause count divided by all attempts. Errors therefore reduce agreement. No absolute majority means the case is incorrect for the primary comparison.

Summary correctness and McNemar use one aggregate result per case, never repeated requests as independent samples. Risk is reported both by attempt and by cases with any risky response. Review per-cause and per-framework breakdowns alongside the aggregate.

## Freeze order and held-out validation

1. Develop and review rules, prompts and scoring on development data, with comparable effort for both variants.
2. Commit the implementation and preserve a schema-2 development freeze manifest before independent held-out preparation.
3. Prepare new evidence and labels independently. Use separate cohorts for new examples of known frameworks and entirely unseen frameworks; do not pool them to claim one kind of generalization.
4. Replay held-out using --manifest pointing to that earlier development freeze. Code, prompt, schema, runtime and provider settings must match. Only data hashes and data_splits may differ.
5. The runner saves the original freeze as preregistration.json and new data hashes as manifest.json. A held-out manifest cannot serve as its own preregistration. Development replays still require full manifest equality.
6. Preserve all results. Tuning after inspection starts a new named experiment.

Legacy schema-1 manifests must be regenerated. Hashes detect accidental drift; they do not prove chronology or independent authorship, prevent data access, or stop someone from deliberately regenerating a development freeze after peeking at held-out.

### Held-out label policy

The current Uvicorn/Go recorder is strictly a development fixture tool, not a held-out generator. For future natural-log cohorts, keep the injected fault as separate metadata and label only what the available evidence supports. A missing readiness-route observation may require insufficient_evidence rather than the hidden injected cause. Do not require held-out applications to emit helper route lines, or discard cases simply because their logs do not match development patterns. Continue collecting other cases while preserving per-case collection failures. That generalized recorder is not implemented yet.

Model configuration includes request parameter names and temperature omission. A deployment name does not pin the provider's immutable model version; preserve deployment metadata separately.

## Proposed decision gate

Before held-out creation, freeze a target of at least +15 percentage points in case-level majority-correct accuracy, no more than +2 percentage points in diagnostic-risk cases, and exact paired McNemar p below 0.05. These are project criteria, not a sample-size or statistical-power guarantee.

Never apply this gate to eight development recordings or the synthetic regression suite. Use a pilot to plan a sufficiently sized independent study. Assess explanation quality separately under blinded human review. A diagnostic win never authorizes live mutation.

## Remaining evidence limits

The collector now retains a bounded startup prefix and recent logs separately, reports empty windows, and sorts Events by timestamps. Original startup may already be rotated away; Pod-level Events may be ambiguous for multi-container Pods. Baseline fault conclusions abstain on that ambiguity.

Reads are sequential, not atomic. Source text remains untrusted. Explicit item-level trust metadata, richer revision histories, previous-container logs and metrics remain future work.
