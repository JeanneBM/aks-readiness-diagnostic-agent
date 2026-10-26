# Phase 2: evidence before autonomy

This design adopts the experiment-first direction of the supplied phase-2 proposal. It separates implemented diagnostic replay from future action selection and execution. A hypothesis that rules will struggle is not evidence that a model will win.

## Current stage: implemented

Read-only HTTP readiness diagnosis, A1/C1/H replay, separate labels, drift manifests, bounded cluster reads and synthetic development fixtures. No multi-step agent, action executor, identity deployment or cloud provisioning is present.

## Broader incident catalog: planned

| Incident class | Candidate response to evaluate later |
| --- | --- |
| Release regression or removed environment setting | Rollback only if the recorded evidence supports it |
| Configuration-only regression | Restore a versioned configuration; deployment rollback may not help |
| Unavailable dependency or rotated credential | Escalate to the owner with evidence |
| Network policy change | Revert an identified policy change or escalate |
| Insufficient startup-probe budget | Bounded probe adjustment or escalation |
| OOM after release | Rollback or bounded resource adjustment, depending on evidence |
| Expired dependency certificate | Escalation with a supported diagnosis |
| Wrong service address or broken feature flag | Configuration/flag correction or escalation |
| Concurrent causes | Explicit ambiguity rather than the first matching rule |
| Image typo control | Deterministic correction should remain competitive |

No response in this table is implemented as a mutation.

## Additional comparison variants: planned

A0: recent rollout implies rollback, otherwise escalate. C2: a model chooses read-only tools against a recorded snapshot with a step budget. C3: repeated sampling with a frozen agreement rule. These are separate experiments; v1 provides A1, C1 and H only. Give every variant the same recorded information budget.

## Recording requirements before expansion

- Record evidence once, then replay variants offline to limit cloud costs.
- Include item IDs, timestamps, source origin and trust classification.
- Include bounded current/previous logs, Events, revision history/diffs, configuration-change metadata and metrics.
- Never export Secret values. Expose only relevant change metadata when studying credential rotation.
- Keep causes and acceptable/forbidden responses in separate labels.
- Include stale errors, irrelevant events, concurrent causes and injected instructions. Observe how often the attacker-desired recommendation is proposed, not merely whether its syntax is valid.
- Independent held-out creation follows the code/prompt freeze. Reserve unseen incident categories as well as new formulations.

## A future execution gate

The diagnostic output does not authorize execution. A separate executor would require independently verified scope, resourceVersion checks, bounded change size, one action per incident, rate/action budgets, success observation and a tested compensation path. A rollback can itself be incorrect or harmful, including with schema migrations.

Policy should check whether an attempted action is allowed, not encode the correct answer and then attribute that answer to the model. An allowed but wrong action still counts as risk even if automatically reversed. Recommendation quality must therefore be measured before enabling execution.

Only a dedicated shadow/live validation can establish action coverage and executed-action risk. No diagnostic score or p-value alone grants authority to mutate production.

## Stop conditions

Stop or narrow the project if a credible rules baseline is equally useful, explanations fail review, evidence cannot be collected safely, or the time/cost budget is exceeded. Publish a negative result rather than manufacture model advantage by weakening the baseline.
