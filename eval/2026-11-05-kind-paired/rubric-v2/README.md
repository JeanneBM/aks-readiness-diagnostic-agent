# Post-hoc citation review — rubric v2

This is an offline reanalysis of preserved responses, performed after inspecting model output. It is not a new model run or preregistered validation. Original labels, observations and result files are unchanged.

## Change and rationale

Only R003 citation requirements change: require `probe`, plus either `logs` or `startup`. Both recorded log observations contain the registered `/ready` route and an actual 404 request for `/wrong-readiness-path`. Requiring the duplicate failure Event in addition to that log evidence was unnecessary. This does not authorize treating any arbitrary access log as proof of a readiness-route mismatch. Ground truth, cause taxonomy and scoring implementation are unchanged for this reanalysis.

| C1 metric | Original | Revised |
| --- | ---: | ---: |
| Correct attempts | 9/24 | 9/24 |
| Provider failures | 10 | 10 |
| Conservative risk flags | 6 | 3 |

The remaining three flags are the R002 wrong-cause answers. A1/H remain 24/24 with no risk flags. Risk flags are rubric-derived, not a complete human assessment of claims or recommendation safety. No significance test is rerun or superiority inferred.

`rescore.json` records original attempt hashes, revised rubric hash and per-attempt scores. Reproduce from the repository root with a fresh output path:

```bash
python tools/rescore_recorded_pilot.py --output .local/review/rubric-v2.json
```

No cluster or model configuration is required. The historical responses are scored as recorded; new fixed recommendation templates are not applied retroactively.
