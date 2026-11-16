"""Offline checks for the preregistered phase-2 design (docs/phase-2-protocol.md).

Nothing here is a phase-2 result. These tests pin the matrix, the cohort labels, the
baseline's expected behaviour on each cohort, the H fallback wiring and the gate's
decision rule, so that a recorded run is judged by the rule that was committed first.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from readiness_agent.baseline import diagnose
from readiness_agent.errors import ProviderError
from readiness_agent.evaluation import evaluate, load_cases
from readiness_agent.models import Bundle, Diagnosis, RECOMMENDATIONS

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC = ROOT / "data/dev-phase2-synthetic"


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def lab():
    return module(ROOT / "tools/run_local_lab.py", "phase2_lab")


def gate():
    return module(ROOT / "tools/phase2_gate.py", "phase2_gate")


class ScriptedClient:
    """Answers from a function of the bundle; counts calls. Never contacts a provider."""
    provider, model, api_version, endpoint = "azure", "scripted", "test", "https://example.openai.azure.com"
    request_settings = {"temperature": 0, "max_tokens": 700}

    def __init__(self, answers, failing=()):
        self.answers, self.failing, self.calls = answers, set(failing), 0

    def diagnose(self, bundle):
        self.calls += 1
        if self.calls in self.failing:
            raise ProviderError("Provider HTTP error 500; no automatic retry", http_status=500)
        cause, ids = self.answers(bundle)
        return Diagnosis(cause, "scripted", tuple(ids), RECOMMENDATIONS[cause], "scripted"), {"total_tokens": 1}


def truthful(cases):
    """A model that answers exactly what the label supports, citing the required IDs."""
    table = {json.dumps(bundle.to_dict(), sort_keys=True): truth for _, bundle, truth in cases}
    def answer(bundle):
        truth = table[json.dumps(bundle.to_dict(), sort_keys=True)]
        ids = list(truth["required_evidence_ids"]) + [g[0] for g in truth.get("evidence_options", [])[:1]]
        return truth["cause"], ids
    return answer


class Phase2DesignTests(unittest.TestCase):
    def test_matrix_matches_preregistered_cohorts(self):
        m = lab()
        plan = m.MATRICES["phase2"]
        self.assertEqual(len(plan), 13)
        counts = {}
        for profile, scenario in plan:
            counts[m.cohort(profile, scenario)] = counts.get(m.cohort(profile, scenario), 0) + 1
        self.assertEqual(counts, {"in-pattern": 3, "out-of-pattern": 6, "control": 4})
        self.assertEqual(m.MATRICES["dev-v1"], [(f, s) for f in ("uvicorn", "go")
                                                for s in ("healthy", "port", "path", "dependency")])

    def test_profiles_only_change_logging_or_timing_not_the_fault(self):
        m = lab()
        for profile, scenario in m.MATRICES["phase2"]:
            item = m.case_document(profile, scenario)["spec"]["containers"][0]
            self.assertEqual(item["startupProbe"]["httpGet"], {"port": 8080, "path": "/live"})
            self.assertEqual(item["readinessProbe"]["httpGet"]["port"], 9090 if scenario == "port" else 8080)
            self.assertEqual(item["readinessProbe"]["httpGet"]["path"],
                             "/wrong-readiness-path" if scenario == "path" else "/ready")
            env = {e["name"]: e["value"] for e in item["env"]}
            self.assertEqual("READY_DELAY_SECONDS" in env, scenario == "timeout")
            self.assertEqual(item.get("args") is not None, profile == "uvicorn-quiet")
        self.assertIn("--log-level", m.case_document("uvicorn-quiet", "port")["spec"]["containers"][0]["args"])

    def test_label_follows_evidence_not_injection(self):
        m = lab()
        quiet = Bundle.parse({"schema": 1, "target": "t", "observations": [
            {"id": "status", "kind": "pod_status", "source": "s", "text": "Ready=False"},
            {"id": "probe", "kind": "probe_config", "source": "s", "text": '{"path": "/ready", "port": 9090, "scheme": "HTTP"}'},
            {"id": "events", "kind": "probe_result", "source": "s", "text": "Readiness probe failed: connection refused"},
            {"id": "logs-limit", "kind": "limitation", "source": "collector", "text": "No log lines."}]})
        label = m.label_for(quiet, "uvicorn-quiet", "port")
        self.assertEqual((label["cause"], label["cohort"], label["injected_fault"]),
                         ("insufficient_evidence", "control", "port"))
        self.assertEqual(label["required_evidence_ids"], [])
        node = Bundle.parse({"schema": 1, "target": "t", "observations": [
            {"id": "status", "kind": "pod_status", "source": "s", "text": "Ready=False"},
            {"id": "probe", "kind": "probe_config", "source": "s", "text": '{"path": "/ready", "port": 9090, "scheme": "HTTP"}'},
            {"id": "events", "kind": "probe_result", "source": "s", "text": "Readiness probe failed: connection refused"},
            {"id": "startup", "kind": "app_log", "source": "s",
             "text": (ROOT / "tests/golden/node-dependency-up.log").read_text()}]})
        label = m.label_for(node, "node", "port")
        self.assertEqual((label["cause"], label["cohort"]), ("probe_port_mismatch", "out-of-pattern"))
        self.assertEqual(label["evidence_options"], [["startup"]])
        with self.assertRaisesRegex(ValueError, "absent"):
            m.label_for(quiet, "node", "port")

    def test_committed_node_captures_match_source_and_are_unknown_to_the_rules(self):
        m = lab()
        source = hashlib.sha256((ROOT / "lab/node/server.js").read_bytes()).hexdigest()
        for run in ("dependency-down", "dependency-up", "ready-delay"):
            provenance = json.loads((ROOT / f"tests/golden/node-{run}.provenance.json").read_text())
            raw = (ROOT / f"tests/golden/node-{run}.log").read_bytes()
            self.assertEqual(provenance["source_sha256"], source, run)
            self.assertEqual(provenance["log_sha256"], hashlib.sha256(raw).hexdigest(), run)
        down = (ROOT / "tests/golden/node-dependency-down.log").read_text()
        for scenario in ("port", "path", "dependency"):
            bundle = Bundle.parse({"schema": 1, "target": "t", "observations": [
                {"id": "status", "kind": "pod_status", "source": "s", "text": "Ready=False"},
                {"id": "probe", "kind": "probe_config", "source": "s", "text": json.dumps(
                    {"path": "/unknown" if scenario == "path" else "/ready", "port": 1 if scenario == "port" else 8080, "scheme": "HTTP"})},
                {"id": "events", "kind": "probe_result", "source": "s", "text": {
                    "port": "Readiness probe failed: connection refused", "path": "Readiness probe failed: HTTP probe failed with statuscode: 404",
                    "dependency": "Readiness probe failed: HTTP probe failed with statuscode: 503"}[scenario]},
                {"id": "startup", "kind": "app_log", "source": "s", "text": down}]})
            self.assertEqual(diagnose(bundle).cause, "insufficient_evidence", scenario)
            self.assertEqual(m.supporting_log_options(bundle, scenario, "node"), [["startup"]], scenario)


class Phase2ReplayTests(unittest.TestCase):
    def test_synthetic_fixtures_regenerate_identically(self):
        gen = module(ROOT / "tools/generate_phase2_fixtures.py", "phase2_fixtures")
        with tempfile.TemporaryDirectory() as temp:
            gen.generate(Path(temp) / "out")
            for folder in ("evidence", "labels"):
                for path in sorted((SYNTHETIC / folder).glob("*.json")):
                    self.assertEqual(path.read_text(), (Path(temp) / "out" / folder / path.name).read_text(), path.name)

    def test_rules_solve_in_pattern_and_abstain_elsewhere(self):
        with tempfile.TemporaryDirectory() as temp:
            summary = evaluate(SYNTHETIC, Path(temp) / "run", ["A1"], repetitions=3)
        by = summary["variants"]["A1"]["by_cohort"]
        self.assertEqual({k: v["correct"] for k, v in by.items()}, {"in-pattern": 3, "out-of-pattern": 0, "control": 4})
        self.assertEqual(summary["variants"]["A1"]["unsupported_conclusions"], 0)
        self.assertEqual(summary["variants"]["A1"]["model_calls"], 0)

    def test_fallback_consults_the_model_only_when_rules_abstain(self):
        cases = load_cases(SYNTHETIC)
        client = ScriptedClient(truthful(cases))
        with tempfile.TemporaryDirectory() as temp:
            summary = evaluate(SYNTHETIC, Path(temp) / "run", ["A1", "C1", "H"], client, repetitions=3)
        h, c1 = summary["variants"]["H"], summary["variants"]["C1"]
        self.assertEqual(h["by_cohort"]["in-pattern"]["model_calls"], 0)
        self.assertEqual(h["by_cohort"]["out-of-pattern"]["model_calls"], 18)
        self.assertEqual(h["by_cohort"]["control"]["model_calls"], 12)
        self.assertEqual(c1["model_calls"], 39)
        self.assertEqual({k: v["correct"] for k, v in h["by_cohort"].items()}, {"in-pattern": 3, "out-of-pattern": 6, "control": 4})
        verdict = gate().decide(summary)
        self.assertEqual(verdict["verdict"], "SUITABLE_STANDALONE")
        self.assertTrue(verdict["design_matches_protocol"])

    def test_gate_counts_unsupported_control_conclusions_against_the_model(self):
        cases = load_cases(SYNTHETIC)
        honest = truthful(cases)
        def overconfident(bundle):
            cause, ids = honest(bundle)
            events = next((o.text for o in bundle.observations if o.id == "events"), "")
            if cause == "insufficient_evidence" and "context deadline" in events:
                return "dependency_unavailable", ["events"]  # decoy taken on both timeout controls
            return cause, ids
        with tempfile.TemporaryDirectory() as temp:
            summary = evaluate(SYNTHETIC, Path(temp) / "run", ["A1", "C1", "H"], ScriptedClient(overconfident), repetitions=3)
        verdict = gate().decide(summary)
        self.assertEqual(summary["variants"]["H"]["by_cohort"]["control"]["diagnostic_risk_cases"], 2)
        self.assertEqual(verdict["verdict"], "NOT_SUITABLE")
        self.assertFalse([x for x in verdict["fallback_checks"] if "control" in x["check"]][0]["passed"])

    def test_gate_is_inconclusive_when_the_provider_fails(self):
        cases = load_cases(SYNTHETIC)
        failing = range(1, 80, 4)  # every fourth call fails: 25% > 10%
        with tempfile.TemporaryDirectory() as temp:
            summary = evaluate(SYNTHETIC, Path(temp) / "run", ["A1", "C1", "H"],
                               ScriptedClient(truthful(cases), failing), repetitions=3)
        verdict = gate().decide(summary)
        self.assertEqual(verdict["verdict"], "INCONCLUSIVE")
        self.assertGreater(summary["variants"]["H"]["provider_errors"], 0)

    def test_gate_refuses_incomplete_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            summary = evaluate(SYNTHETIC, Path(temp) / "run", ["A1"], repetitions=3)
        with self.assertRaisesRegex(ValueError, "A1, C1 and H"):
            gate().decide(summary)
        cases = load_cases(SYNTHETIC)
        with tempfile.TemporaryDirectory() as temp:
            summary = evaluate(SYNTHETIC, Path(temp) / "run", ["A1", "C1", "H"], ScriptedClient(truthful(cases)))
        with self.assertRaisesRegex(ValueError, "three repetitions"):
            gate().decide(summary)


if __name__ == "__main__":
    unittest.main()
