"""Paired replay: independently frozen code, repeated cases and explicit error risk."""
import hashlib
import json
from collections import Counter
from math import comb
from pathlib import Path
import platform
import time

from .baseline import diagnose
from .errors import ContractError, ProviderError
from .llm import PROMPT, SCHEMA
from .models import CAUSES, Bundle, Diagnosis


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(cases, model_config=None):
    code = {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))}
    data = {p.relative_to(cases).as_posix(): digest(p.read_bytes())
            for p in sorted(Path(cases).rglob("*.json"))}
    splits = sorted({json.loads(p.read_text(encoding="utf-8"))["split"]
                     for p in (Path(cases) / "labels").glob("*.json")})
    return {"schema": 2, "python": platform.python_version(), "code": code, "data": data,
            "data_splits": splits, "prompt_sha256": digest(PROMPT.encode()),
            "output_schema_sha256": digest(json.dumps(SCHEMA, sort_keys=True).encode()),
            "model_config": model_config}


def validate_manifest(frozen, current, held_out):
    if frozen.get("schema") != 2:
        raise ValueError("Regenerate legacy manifests with schema 2")
    ignored = {"data", "data_splits"} if held_out else set()
    if {k: v for k, v in frozen.items() if k not in ignored} != {
            k: v for k, v in current.items() if k not in ignored}:
        raise ValueError("Frozen implementation, runtime, model configuration or development data changed")
    if held_out and frozen.get("data_splits") != ["dev"]:
        raise ValueError("Held-out evaluation requires the prior development freeze")


def load_cases(directory):
    directory = Path(directory)
    recording = directory / "recording.json"
    if recording.exists() and json.loads(recording.read_text(encoding="utf-8")).get("status") != "RECORDED":
        raise ValueError("Recording is incomplete; preserve it and start a separate recording")
    evidence = sorted((directory / "evidence").glob("*.json"))
    if not evidence:
        raise ValueError("No evidence cases found")
    if {p.stem for p in evidence} != {p.stem for p in (directory / "labels").glob("*.json")}:
        raise ValueError("Evidence and label case IDs must match")
    cases = []
    for p in evidence:
        bundle = Bundle.parse(json.loads(p.read_text(encoding="utf-8")))
        truth = json.loads((directory / "labels" / p.name).read_text(encoding="utf-8"))
        required = {"cause", "required_evidence_ids", "split", "origin"}
        if not required <= set(truth) or set(truth) - required - {"framework", "scenario", "evidence_options"}:
            raise ValueError("Invalid ground-truth contract")
        if truth["cause"] not in CAUSES or truth["split"] not in ("dev", "held-out"):
            raise ValueError("Invalid ground-truth taxonomy or split")
        ids = truth["required_evidence_ids"]
        if (not isinstance(ids, list) or any(not isinstance(i, str) for i in ids)
                or len(ids) != len(set(ids)) or not set(ids) <= {o.id for o in bundle.observations}):
            raise ValueError("Ground truth references missing or duplicate evidence")
        options = truth.get("evidence_options", [])
        if not isinstance(options, list) or any(not isinstance(group, list) or not group
                or any(not isinstance(i, str) for i in group)
                or not set(group) <= {o.id for o in bundle.observations} for group in options):
            raise ValueError("Invalid alternative evidence rubric")
        cases.append((p.stem, bundle, truth))
    if len({t["split"] for _, _, t in cases}) != 1:
        raise ValueError("Do not mix development and held-out cases in one run")
    return cases


def score(diagnosis, truth):
    correct = diagnosis.cause == truth["cause"]
    ids = set(diagnosis.evidence_ids)
    options = truth.get("evidence_options", [])
    supported = (set(truth["required_evidence_ids"]) <= ids
                 and (not options or any(set(group) <= ids for group in options))
                 if truth["required_evidence_ids"] or options else None)
    unsupported = diagnosis.cause != "insufficient_evidence" and (not correct or supported is False)
    return {"cause_correct": correct, "rubric_evidence_covered": supported,
            "appropriate_abstention": correct if truth["cause"] == "insufficient_evidence" else None,
            "unsupported_conclusion": unsupported, "diagnostic_risk": unsupported}


def paired_comparison(rows, challenger):
    """Exact McNemar on cases, never on pseudoreplicated repeated requests."""
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


def case_consistency(rows):
    result = []
    for case_id, variant in sorted({(r["case_id"], r["variant"]) for r in rows}):
        data = [r for r in rows if r["case_id"] == case_id and r["variant"] == variant]
        counts = Counter(r["diagnosis"]["cause"] for r in data if r["status"] == "OK")
        cause, count = counts.most_common(1)[0] if counts else (None, 0)
        # An absolute majority of all attempts is required; errors do not vanish.
        majority = cause if count > len(data) / 2 else None
        result.append({"case_id": case_id, "variant": variant, "repetitions": len(data),
                       "cause_counts": dict(counts), "valid_responses": sum(counts.values()),
                       "cause_agreement": count / len(data), "majority_cause": majority,
                       "ground_truth": data[0]["ground_truth"],
                       "cause_correct": majority == data[0]["ground_truth"],
                       "any_diagnostic_risk": any(r.get("diagnostic_risk", False) for r in data)})
    return result


def model_configuration(client):
    if client is None:
        return None
    return {"provider": client.provider, "model": client.model, "api_version": client.api_version,
            "endpoint_sha256": digest(client.endpoint.encode()),
            **getattr(client, "request_settings", {"temperature": 0, "max_tokens": 700})}


def evaluate(cases_path, output, variants, client=None, manifest=None, repetitions=1):
    if not variants or len(variants) != len(set(variants)) or not set(variants) <= {"A1", "C1", "H"}:
        raise ValueError("Select distinct variants A1, C1 or H")
    if type(repetitions) is not int or not 1 <= repetitions <= 10:
        raise ValueError("Repetitions must be between 1 and 10")
    if set(variants) - {"A1"} and client is None:
        raise ValueError("Model variants require an explicitly configured client")
    cases = load_cases(cases_path)
    held_out = cases[0][2]["split"] == "held-out"
    current = fingerprint(Path(cases_path), model_configuration(client))
    frozen = json.loads(Path(manifest).read_text(encoding="utf-8")) if manifest else None
    if held_out and frozen is None:
        raise ValueError("Held-out runs require the prior development freeze")
    if frozen is not None:
        validate_manifest(frozen, current, held_out)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    save("manifest.json", current)
    if frozen is not None:
        save("preregistration.json", frozen)
    save("run.json", {"variants": variants, "repetitions": repetitions, "split": cases[0][2]["split"],
                      "aggregation": "absolute majority of all attempts per case; errors remain in denominator"})
    rows = []
    for case_id, bundle, truth in cases:
        for repetition in range(1, repetitions + 1):
            for variant in variants:
                started = time.perf_counter()
                row = {"case_id": case_id, "variant": variant, "repetition": repetition,
                       "split": truth["split"], "framework": truth.get("framework", "unspecified"),
                       "ground_truth": truth["cause"], "status": "ERROR", "usage": {}, "model_calls": 0,
                       "rubric_evidence_covered": False if truth["required_evidence_ids"] or truth.get("evidence_options") else None,
                       "diagnostic_risk": False, "unsupported_conclusion": False}
                try:
                    result = diagnose(bundle) if variant in ("A1", "H") else None
                    if result is None or (variant == "H" and result.cause == "insufficient_evidence"):
                        row["model_calls"] = 1
                        result, row["usage"] = client.diagnose(bundle)
                        try:
                            result = Diagnosis.parse(result.to_dict(), bundle)
                        except (ValueError, TypeError, AttributeError):
                            raise ContractError("Invalid diagnostic result") from None
                    row.update(status="OK", diagnosis=result.to_dict(), **score(result, truth))
                except ContractError:
                    row.update(error_kind="CONTRACT_ERROR", diagnostic_risk=True, unsupported_conclusion=True)
                except ProviderError:
                    row["error_kind"] = "PROVIDER_ERROR"
                except Exception:
                    row["error_kind"] = "EXECUTION_ERROR"
                row["seconds"] = time.perf_counter() - started
                rows.append(row)
                save(f"{case_id}-{variant}-r{repetition:03d}.json", row)
    consistent = case_consistency(rows)
    save("consistency.json", consistent)
    summary = {"schema": 2, "cases": len(cases), "repetitions": repetitions, "variants": {}}
    lines = ["# Replay results", "", "Recorded diagnostic results; no live repair or human approval implied.", "",
             "| Variant | Cases | Majority-correct | Attempts | Errors | Diagnostic risk attempts | Model calls |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for variant in variants:
        data = [x for x in rows if x["variant"] == variant]
        cases_data = [x for x in consistent if x["variant"] == variant]
        entry = {"cases": len(cases_data), "attempts": len(data),
                 "correct": sum(x["cause_correct"] for x in cases_data),
                 "correct_attempts": sum(x.get("cause_correct", False) for x in data),
                 "errors": sum(x["status"] == "ERROR" for x in data),
                 "contract_errors": sum(x.get("error_kind") == "CONTRACT_ERROR" for x in data),
                 "provider_errors": sum(x.get("error_kind") == "PROVIDER_ERROR" for x in data),
                 "unsupported_conclusions": sum(x["unsupported_conclusion"] for x in data),
                 "diagnostic_risk_attempts": sum(x["diagnostic_risk"] for x in data),
                 "diagnostic_risk_cases": sum(x["any_diagnostic_risk"] for x in cases_data),
                 "rubric_evidence_covered": sum(x.get("rubric_evidence_covered") is True for x in data),
                 "rubric_evidence_applicable": sum(x.get("rubric_evidence_covered") is not None for x in data),
                 "model_calls": sum(x["model_calls"] for x in data),
                 "seconds_total": sum(x["seconds"] for x in data),
                 "tokens_reported": sum(x["usage"].get("total_tokens", 0) for x in data),
                 "calls_with_usage": sum(bool(x["usage"]) for x in data)}
        entry["by_cause"] = {cause: {
            "cases": sum(x["ground_truth"] == cause for x in cases_data),
            "correct": sum(x["ground_truth"] == cause and x["cause_correct"] for x in cases_data)}
            for cause in sorted({x["ground_truth"] for x in cases_data})}
        entry["by_framework"] = {framework: {
            "attempts": sum(x["framework"] == framework for x in data),
            "correct_attempts": sum(x["framework"] == framework and x.get("cause_correct", False) for x in data)}
            for framework in sorted({x["framework"] for x in data})}
        summary["variants"][variant] = entry
        lines.append(f"| {variant} | {entry['cases']} | {entry['correct']} | {entry['attempts']} | {entry['errors']} | {entry['diagnostic_risk_attempts']} | {entry['model_calls']} |")
    summary["paired_comparisons"] = {v: paired_comparison(consistent, v)
                                     for v in variants if v != "A1" and "A1" in variants}
    save("summary.json", summary)
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
