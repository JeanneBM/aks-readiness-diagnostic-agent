# Phase 2 protocol: is a model suitable for readiness diagnosis?

Preregistered on 16 November 2026, before any phase-2 evidence was recorded and before any phase-2 model request. The commit that introduces this file is the freeze point; `tools/phase2_gate.py` applies the decision rule below mechanically, so the thresholds cannot drift after the results are seen.

## Question

The first pilot answered a narrow question: on evidence the rules were written for, do rules suffice? They did (A1 24/24). That says nothing about the question this repository actually exists to answer:

**When the evidence does not match the rules' patterns, does a model recover the diagnosis without inventing one where the evidence supports none?**

Two sub-questions, decided separately:

1. **Fallback (H).** Rules first; the model is asked only when the rules abstain. Does the model add coverage without adding unsupported conclusions?
2. **Standalone (C1).** One model request per case, no rules. Does the model match the rules where the rules work, and keep abstaining where nothing supports a cause?

## Design

Thirteen recorded kind cases (`python tools/run_local_lab.py record --matrix phase2`), three repetitions each, variants A1, C1 and H on identical bundles. Applications are the real lab services; faults are injected the same way as in the first pilot.

| # | Profile | Injection | Cohort | Labelled cause | Why it is here |
| --- | --- | --- | --- | --- | --- |
| R001 | go-json | none | in-pattern | healthy | Ready=True needs no log parsing |
| R002 | go-json | probe port 9090 | out-of-pattern | probe_port_mismatch | Listener logged as `"address":":8080"`; rules parse the text handler only |
| R003 | go-json | probe path wrong | out-of-pattern | probe_path_mismatch | Route logged as `"readiness_path":"/ready"` |
| R004 | go-json | dependency scaled to 0 | out-of-pattern | dependency_unavailable | Failure logged as JSON |
| R005 | node | none | in-pattern | healthy | |
| R006 | node | probe port 9090 | out-of-pattern | probe_port_mismatch | Unseen runtime; `server listening on http://0.0.0.0:8080` |
| R007 | node | probe path wrong | out-of-pattern | probe_path_mismatch | `routes mounted: GET /live, GET /ready` plus a logged 404 |
| R008 | node | dependency scaled to 0 | out-of-pattern | dependency_unavailable | `readiness check failed: inventory unreachable (ECONNREFUSED …)` |
| R009 | node | readiness handler sleeps 10 s | control | insufficient_evidence | Probe deadline error; outside the taxonomy |
| R010 | uvicorn-quiet | probe port 9090 | control | insufficient_evidence | `--log-level warning`: no listener line exists |
| R011 | uvicorn-quiet | probe path wrong | control | insufficient_evidence | 404 with no route evidence |
| R012 | uvicorn-quiet | dependency scaled to 0 | in-pattern | dependency_unavailable | The one ERROR line is a known pattern |
| R013 | go | readiness handler sleeps 10 s | control | insufficient_evidence | Deadline error; listener and route are correct |

The cohort describes the **evidence form**, not difficulty. The label follows what the recorded bundle supports (held-out label policy in `docs/evaluation.md`): a fault whose supporting log never reaches the bundle is labelled `insufficient_evidence`, and the injection is kept as `injected_fault` metadata. Recording fails rather than labelling an out-of-pattern case whose supporting line is absent.

Expected A1 behaviour, verified offline before recording: correct on in-pattern, abstains on out-of-pattern (by construction), abstains on control (correctly). H therefore reaches the model on the ten out-of-pattern and control cases and never on the three in-pattern cases.

### The decoys are real

Three cases carry surface signals that point at the wrong cause. Node's dependency failure logs `ECONNREFUSED`, which resembles a port mismatch. Both timeout controls log a correct listener and a correct route next to a probe failure. The quiet 404 looks like a path mismatch to anyone who assumes `/ready` is conventional. A model that pattern-matches on vocabulary rather than on the taxonomy's evidence requirements will produce unsupported conclusions here, and those count.

## Metrics

All from `summary.json`, per variant and per cohort (`by_cohort`), as already defined in `docs/evaluation.md`:

- **Majority-correct cases**: absolute majority of three attempts matches the label; provider errors stay in the denominator.
- **Diagnostic-risk cases**: any attempt with an unsupported conclusion, invalid output or no answer.
- **Provider errors**: attempts with no usable response.
- **Model calls**: cost proxy.
- Exact paired McNemar H vs A1 and C1 vs A1 over all 13 cases, reported, not gated.

## Decision rule

Thresholds are project criteria for a 13-case development study. They are not powered inference, and the gate says so in its output.

**Precondition.** Provider errors ≤ 10% of model attempts for the variant being judged. Otherwise the result for that variant is `INCONCLUSIVE`: a model that cannot be reached cannot be judged, and the first pilot's ten unexplained failures must not be repeated as a verdict on quality.

**H is a suitable fallback** when all hold:

1. out-of-pattern majority-correct ≥ 5 of 6;
2. control diagnostic-risk cases ≤ 1 of 4;
3. in-pattern majority-correct equals A1 (3 of 3; H cannot differ there, and the gate checks that it did not).

**C1 is suitable standalone** when all hold:

1. in-pattern majority-correct = 3 of 3;
2. out-of-pattern majority-correct ≥ 5 of 6;
3. control diagnostic-risk cases ≤ 1 of 4.

Verdicts, in order of precedence:

| Verdict | Condition |
| --- | --- |
| `SUITABLE_STANDALONE` | C1 criteria hold (H criteria then hold too, or the run is examined for a recording fault) |
| `SUITABLE_AS_FALLBACK` | H criteria hold, C1 criteria do not |
| `NOT_SUITABLE` | H criteria fail with the precondition met |
| `INCONCLUSIVE` | Precondition fails for H |

A `NOT_SUITABLE` result is published with the same prominence as a positive one. The baseline is not weakened, the controls are not removed and the thresholds are not revisited after the fact. Improving the prompt after seeing phase-2 outputs starts a new named experiment with new recordings.

## Model and run configuration

- One preregistered primary deployment, named in `eval/<date>-kind-phase2/provenance.json` before the run. Temperature 0, `max_tokens` 700, strict JSON schema with bundle-specific citation IDs, three repetitions, `READINESS_MIN_REQUEST_INTERVAL_SECONDS` ≥ 1.
- A second model is a second named run under the same protocol, never a replacement chosen after comparing results. The first pilot's `gpt-4.1-nano` is eligible; its 3-of-8 standalone result on in-pattern cases is a reason to expect C1 to fail there, not a reason to exclude it.
- Order of operations: merge this protocol → commit a schema-2 freeze of code, prompt and schema → record the matrix in kind → replay A1 three times (free) and commit the recording → one paid run with `--variants A1,C1,H --repetitions 3 --manifest <freeze>` → run the gate → commit results, gate output and provenance unchanged.

## What this cannot establish

- **Not held-out.** The author of the Node lab and the go-json profile had read the baseline. The log vocabulary follows common conventions and was not tuned against the regexes, but that is a claim, not a control. An independent cohort authored without reading `baseline.py` is still required before any generalization claim.
- **Small.** Six out-of-pattern cases cannot distinguish 5/6 from 3/6 statistically. The gate is a project decision rule.
- **One fault family.** HTTP readiness probes on single-container Pods, four causes, two decoy types. Nothing here speaks to exec/TCP/gRPC probes, multi-container Pods, rollouts or resource pressure.
- **Diagnosis only.** A suitable verdict authorizes displaying a template recommendation, never executing anything. `docs/phase-2.md` keeps the execution gate separate.
- **One snapshot in time.** Model deployments change underneath a deployment name; the provenance file records what is knowable, not an immutable model version.

## Stop conditions

Stop and publish if: the recording cannot produce all 13 labelled cases without manual edits; the provider precondition fails twice; or the paid budget set in `provenance.json` is exhausted. Do not substitute synthetic fixtures for a failed recording in the reported result; `data/dev-phase2-synthetic` exists for offline regression only.
