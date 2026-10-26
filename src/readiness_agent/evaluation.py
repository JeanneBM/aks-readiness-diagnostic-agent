"""Paired replay with separate labels, persistent errors and no implicit model calls."""
import hashlib
import json
from math import comb
from pathlib import Path
import platform
import time

from .baseline import diagnose
from .llm import PROMPT, SCHEMA
from .models import CAUSES, Bundle


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(cases, model_config=None):
    code = {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))}
    data = {p.relative_to(cases).as_posix(): digest(p.read_bytes())
            for p in sorted(Path(cases).rglob("*.json"))}
    return {"schema": 1, "python": platform.python_version(), "code": code, "data": data,
            "prompt_sha256": digest(PROMPT.encode()),
            "output_schema_sha256": digest(json.dumps(SCHEMA, sort_keys=True).encode()),
            "model_config": model_config}


def load_cases(directory):
    directory = Path(directory)
    evidence = sorted((directory / "evidence").glob("*.json"))
    if not evidence:
        raise ValueError("No evidence cases found")
    if {p.stem for p in evidence} != {p.stem for p in (directory / "labels").glob("*.json")}:
        raise ValueError("Evidence and label case IDs must match")
    cases = []
    for p in evidence:
        bundle = Bundle.parse(json.loads(p.read_text(encoding="utf-8")))
        truth = json.loads((directory / "labels" / p.name).read_text(encoding="utf-8"))
        if set(truth) != {"cause", "required_evidence_ids", "split", "origin"}:
            raise ValueError("Invalid ground-truth contract")
        if truth["cause"] not in CAUSES or truth["split"] not in ("dev", "held-out"):
            raise ValueError("Invalid ground-truth taxonomy or split")
        ids = truth["required_evidence_ids"]
        if (not isinstance(ids, list) or any(not isinstance(i, str) for i in ids)
                or not set(ids) <= {o.id for o in bundle.observations}):
            raise ValueError("Ground truth references missing evidence")
        cases.append((p.stem, bundle, truth))
    return cases


def score(diagnosis, truth):
    correct = diagnosis.cause == truth["cause"]
    supported = bool(truth["required_evidence_ids"]) and set(truth["required_evidence_ids"]) <= set(diagnosis.evidence_ids)
    return {"cause_correct": correct,
            "rubric_evidence_covered": supported,
            "appropriate_abstention": correct if truth["cause"] == "insufficient_evidence" else None,
            "unsupported_conclusion": diagnosis.cause != "insufficient_evidence" and not (correct and supported)}


def paired_comparison(rows, challenger):
    """Exact two-sided McNemar test; errors count as incorrect, never disappear."""
    by_key = {(r["case_id"], r["variant"]): r for r in rows}
    ids = sorted({r["case_id"] for r in rows})
    baseline_only = challenger_only = 0
    for case_id in ids:
        a = by_key[(case_id, "A1")].get("cause_correct", False)
        c = by_key[(case_id, challenger)].get("cause_correct", False)
        baseline_only += bool(a and not c)
        challenger_only += bool(c and not a)
    n = baseline_only + challenger_only
    p = min(1.0, 2 * sum(comb(n, k) for k in range(min(baseline_only, challenger_only) + 1)) / 2**n) if n else 1.0
    return {"pairs": len(ids), "baseline_only_correct": baseline_only,
            "challenger_only_correct": challenger_only, "exact_mcnemar_p": p,
            "accuracy_difference_pp": 100 * (challenger_only - baseline_only) / len(ids)}


def evaluate(cases_path, output, variants, client=None, manifest=None):
    if not variants or len(variants) != len(set(variants)) or not set(variants) <= {"A1", "C1", "H"}:
        raise ValueError("Select distinct variants A1, C1 or H")
    if set(variants) - {"A1"} and client is None:
        raise ValueError("Model variants require an explicitly configured client")
    cases = load_cases(cases_path)
    config = None if client is None else {
        "provider": client.provider, "model": client.model, "api_version": client.api_version,
        "endpoint_sha256": digest(client.endpoint.encode()), "temperature": 0, "max_tokens": 700}
    current = fingerprint(Path(cases_path), config)
    if manifest is not None and json.loads(Path(manifest).read_text()) != current:
        raise ValueError("Frozen manifest differs from code, data, runtime or model configuration")
    if any(t["split"] == "held-out" for _, _, t in cases) and manifest is None:
        raise ValueError("Held-out runs require a matching frozen manifest")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "manifest.json").write_text(json.dumps(current, indent=2) + "\n")
    rows = []
    for case_id, bundle, truth in cases:
        for variant in variants:
            started = time.perf_counter()
            row = {"case_id": case_id, "variant": variant, "split": truth["split"],
                   "ground_truth": truth["cause"], "status": "ERROR", "usage": {}, "model_calls": 0}
            try:
                result = diagnose(bundle) if variant in ("A1", "H") else None
                if result is None or (variant == "H" and result.cause == "insufficient_evidence"):
                    row["model_calls"] = 1
                    result, row["usage"] = client.diagnose(bundle)
                row.update(status="OK", diagnosis=result.to_dict(), **score(result, truth))
            except Exception:
                # Preserve failure without writing provider bodies, raw exceptions or credentials.
                row["error"] = "Diagnosis failed validation or provider execution; inspect configuration locally."
            row["seconds"] = time.perf_counter() - started
            rows.append(row)
            (output / f"{case_id}-{variant}.json").write_text(json.dumps(row, indent=2) + "\n")
    summary = {"schema": 1, "cases": len(cases), "variants": {}}
    lines = ["# Replay results", "", "Automated development results; no live repair or human approval implied.", "",
             "| Variant | Cases | Correct cause | Errors | Unsupported conclusions | Model calls |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for variant in variants:
        data = [x for x in rows if x["variant"] == variant]
        entry = {"cases": len(data), "correct": sum(x.get("cause_correct", False) for x in data),
                 "errors": sum(x["status"] == "ERROR" for x in data),
                 "unsupported_conclusions": sum(x.get("unsupported_conclusion", False) for x in data),
                 "rubric_evidence_covered": sum(x.get("rubric_evidence_covered", False) for x in data),
                 "model_calls": sum(x["model_calls"] for x in data),
                 "seconds_total": sum(x["seconds"] for x in data),
                 "tokens_reported": sum(x["usage"].get("total_tokens", 0) for x in data),
                 "calls_with_usage": sum(bool(x["usage"]) for x in data)}
        entry["by_cause"] = {cause: {
            "cases": sum(x["ground_truth"] == cause for x in data),
            "correct": sum(x["ground_truth"] == cause and x.get("cause_correct", False) for x in data),
            "errors": sum(x["ground_truth"] == cause and x["status"] == "ERROR" for x in data)}
            for cause in sorted({x["ground_truth"] for x in data})}
        summary["variants"][variant] = entry
        lines.append(f"| {variant} | {entry['cases']} | {entry['correct']} | {entry['errors']} | {entry['unsupported_conclusions']} | {entry['model_calls']} |")
    summary["paired_comparisons"] = {v: paired_comparison(rows, v)
                                     for v in variants if v != "A1" and "A1" in variants}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "summary.md").write_text("\n".join(lines) + "\n")
    return summary
