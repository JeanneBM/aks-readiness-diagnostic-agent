"""Apply the preregistered phase-2 decision rule to a replay summary.

The thresholds live here and in docs/phase-2-protocol.md; both were committed before
any phase-2 model request. The tool prints a verdict and every check that led to it.
It does not change thresholds, drop cases or pick a variant after the fact.
"""
import argparse
import json
from pathlib import Path
import sys

PROTOCOL = "docs/phase-2-protocol.md (preregistered 2026-11-16)"
EXPECTED_COHORTS = {"in-pattern": 3, "out-of-pattern": 6, "control": 4}
MIN_OUT_OF_PATTERN_CORRECT = 5
MAX_CONTROL_RISK_CASES = 1
MAX_PROVIDER_ERROR_SHARE = 0.10


def cohort(summary, variant, name):
    return summary["variants"][variant].get("by_cohort", {}).get(name, {
        "cases": 0, "correct": 0, "diagnostic_risk_cases": 0, "attempts": 0,
        "provider_errors": 0, "model_calls": 0})


def precondition(summary, variant):
    entry = summary["variants"][variant]
    calls = entry["model_calls"]
    errors = entry["provider_errors"]
    share = errors / calls if calls else 0.0
    return {"check": "provider_errors_share", "variant": variant, "provider_errors": errors,
            "model_calls": calls, "share": round(share, 3), "limit": MAX_PROVIDER_ERROR_SHARE,
            "passed": calls > 0 and share <= MAX_PROVIDER_ERROR_SHARE}


def fallback_checks(summary):
    a1_in = cohort(summary, "A1", "in-pattern")
    h_in, h_out, h_ctl = (cohort(summary, "H", c) for c in ("in-pattern", "out-of-pattern", "control"))
    return [
        {"check": "H out-of-pattern majority-correct", "value": h_out["correct"], "cases": h_out["cases"],
         "minimum": MIN_OUT_OF_PATTERN_CORRECT, "passed": h_out["correct"] >= MIN_OUT_OF_PATTERN_CORRECT},
        {"check": "H control diagnostic-risk cases", "value": h_ctl["diagnostic_risk_cases"], "cases": h_ctl["cases"],
         "maximum": MAX_CONTROL_RISK_CASES, "passed": h_ctl["diagnostic_risk_cases"] <= MAX_CONTROL_RISK_CASES},
        {"check": "H in-pattern equals A1", "value": h_in["correct"], "a1": a1_in["correct"], "cases": h_in["cases"],
         "passed": h_in["correct"] == a1_in["correct"] == h_in["cases"] and h_in["model_calls"] == 0},
    ]


def standalone_checks(summary):
    c_in, c_out, c_ctl = (cohort(summary, "C1", c) for c in ("in-pattern", "out-of-pattern", "control"))
    return [
        {"check": "C1 in-pattern majority-correct", "value": c_in["correct"], "cases": c_in["cases"],
         "minimum": c_in["cases"], "passed": c_in["correct"] == c_in["cases"] and c_in["cases"] > 0},
        {"check": "C1 out-of-pattern majority-correct", "value": c_out["correct"], "cases": c_out["cases"],
         "minimum": MIN_OUT_OF_PATTERN_CORRECT, "passed": c_out["correct"] >= MIN_OUT_OF_PATTERN_CORRECT},
        {"check": "C1 control diagnostic-risk cases", "value": c_ctl["diagnostic_risk_cases"], "cases": c_ctl["cases"],
         "maximum": MAX_CONTROL_RISK_CASES, "passed": c_ctl["diagnostic_risk_cases"] <= MAX_CONTROL_RISK_CASES},
    ]


def decide(summary):
    variants = set(summary.get("variants", {}))
    if not {"A1", "C1", "H"} <= variants:
        raise ValueError("The phase-2 gate needs one run with variants A1, C1 and H")
    if summary.get("repetitions") != 3:
        raise ValueError("The protocol specifies three repetitions")
    cohorts = {name: cohort(summary, "A1", name)["cases"] for name in EXPECTED_COHORTS}
    design_matches = cohorts == EXPECTED_COHORTS
    pre_h, pre_c = precondition(summary, "H"), precondition(summary, "C1")
    fallback, standalone = fallback_checks(summary), standalone_checks(summary)
    h_ok = pre_h["passed"] and all(x["passed"] for x in fallback)
    c_ok = pre_c["passed"] and all(x["passed"] for x in standalone)
    if not pre_h["passed"]:
        verdict = "INCONCLUSIVE"
    elif c_ok:
        verdict = "SUITABLE_STANDALONE"
    elif h_ok:
        verdict = "SUITABLE_AS_FALLBACK"
    else:
        verdict = "NOT_SUITABLE"
    return {"protocol": PROTOCOL, "verdict": verdict,
            "design_matches_protocol": design_matches, "cohort_cases": cohorts,
            "preconditions": [pre_h, pre_c], "fallback_checks": fallback, "standalone_checks": standalone,
            "paired_comparisons": summary.get("paired_comparisons", {}),
            "caveat": ("Project decision rule on a 13-case development study; not a powered inference "
                       "and not a held-out result. A SUITABLE verdict authorizes displaying template "
                       "recommendations only.")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="Replay output directory containing summary.json")
    parser.add_argument("--output", help="Write the verdict JSON to this new file as well")
    args = parser.parse_args(argv)
    try:
        summary = json.loads((Path(args.run) / "summary.json").read_text(encoding="utf-8"))
        result = decide(summary)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Gate not applied: {error}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
    if not result["design_matches_protocol"]:
        print("Warning: cohort sizes differ from the preregistered matrix; the verdict is not protocol-valid.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
