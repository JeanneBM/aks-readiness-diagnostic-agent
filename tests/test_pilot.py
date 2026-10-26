import asyncio
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from readiness_agent.baseline import diagnose
from readiness_agent.collector import collect, event_time, read_prefix
from readiness_agent.errors import ContractError, ProviderError
from readiness_agent.evaluation import case_consistency, evaluate, fingerprint, score
from readiness_agent.llm import ModelClient
from readiness_agent.models import Bundle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/dev"


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class PilotTests(unittest.TestCase):
    def test_held_out_accepts_new_data_but_frozen_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            held = root / "held"
            shutil.copytree(DATA, held)
            for p in (held / "labels").glob("*.json"):
                label = json.loads(p.read_text())
                label["split"] = "held-out"
                p.write_text(json.dumps(label))
            freeze = fingerprint(DATA)
            (root / "freeze.json").write_text(json.dumps(freeze))
            summary = evaluate(held, root / "run", ["A1"], manifest=root / "freeze.json")
            self.assertEqual(summary["variants"]["A1"]["correct"], 18)
            self.assertTrue((root / "run/preregistration.json").exists())
            freeze["code"]["baseline.py"] = "changed-after-freeze"
            (root / "bad.json").write_text(json.dumps(freeze))
            with self.assertRaises(ValueError):
                evaluate(held, root / "bad-run", ["A1"], manifest=root / "bad.json")

    def test_held_out_cannot_preregister_itself(self):
        from readiness_agent.evaluation import validate_manifest
        value = fingerprint(DATA)
        value["data_splits"] = ["held-out"]
        with self.assertRaises(ValueError):
            validate_manifest(value, value, True)

    def test_contract_failure_counts_in_risk(self):
        class Client:
            provider, model, api_version, endpoint = "azure", "test", "test", "https://example.openai.azure.com"
            def diagnose(self, bundle):
                raise ContractError("fabricated-evidence-id")
        with tempfile.TemporaryDirectory() as temp:
            result = evaluate(DATA, Path(temp) / "run", ["C1"], Client())
        row = result["variants"]["C1"]
        self.assertEqual(row["contract_errors"], 18)
        self.assertEqual(row["diagnostic_risk_attempts"], 18)
        self.assertEqual(row["diagnostic_risk_cases"], 18)

    def test_provider_failure_is_not_model_risk(self):
        class Client:
            provider, model, api_version, endpoint = "azure", "test", "test", "https://example.openai.azure.com"
            def diagnose(self, bundle):
                raise ProviderError("429")
        with tempfile.TemporaryDirectory() as temp:
            result = evaluate(DATA, Path(temp) / "run", ["C1"], Client())
        row = result["variants"]["C1"]
        self.assertEqual(row["provider_errors"], 18)
        self.assertEqual(row["correct"], 0)
        self.assertEqual(row["diagnostic_risk_attempts"], 0)

    def test_repeated_pairs_do_not_inflate_sample_size(self):
        class Client:
            provider, model, api_version, endpoint = "azure", "test", "test", "https://example.openai.azure.com"
            def diagnose(self, bundle):
                return diagnose(bundle), {}
        with tempfile.TemporaryDirectory() as temp:
            result = evaluate(DATA, Path(temp) / "run", ["A1", "C1"], Client(), repetitions=3)
            consistent = json.loads((Path(temp) / "run/consistency.json").read_text())
        self.assertEqual(result["variants"]["C1"]["attempts"], 54)
        self.assertEqual(result["paired_comparisons"]["C1"]["pairs"], 18)
        self.assertTrue(all(x["cause_agreement"] == 1 for x in consistent))

    def test_errors_remain_in_agreement_denominator(self):
        rows = [{"case_id": "x", "variant": "C1", "ground_truth": "healthy", "status": "OK",
                 "diagnosis": {"cause": "healthy"}},
                {"case_id": "x", "variant": "C1", "ground_truth": "healthy", "status": "ERROR"}]
        result = case_consistency(rows)[0]
        self.assertEqual(result["cause_agreement"], .5)
        self.assertIsNone(result["majority_cause"])
        self.assertFalse(result["cause_correct"])

    def test_evidence_denominator_excludes_not_applicable(self):
        with tempfile.TemporaryDirectory() as temp:
            result = evaluate(DATA, Path(temp) / "run", ["A1"])
        self.assertEqual(result["variants"]["A1"]["rubric_evidence_covered"], 11)
        self.assertEqual(result["variants"]["A1"]["rubric_evidence_applicable"], 11)

    def test_alternative_valid_citations_are_accepted(self):
        from readiness_agent.evaluation import load_cases
        _, bundle, truth = load_cases(DATA)[0]
        truth["required_evidence_ids"] = ["probe", "events"]
        truth["evidence_options"] = [["logs"], ["status"]]
        self.assertTrue(score(diagnose(bundle), truth)["rubric_evidence_covered"])

    def test_initial_prefix_is_not_tail(self):
        prefix, truncated = read_prefix([sys.executable, "-c", "import sys;sys.stdout.write('START'+('x'*50000)+'END')"], limit=20)
        self.assertTrue(truncated)
        self.assertTrue(prefix.startswith("START"))
        self.assertEqual(len(prefix), 20)

    def test_prefix_timeout(self):
        value, _ = read_prefix([sys.executable, "-c", "import time;time.sleep(2)"], timeout=.02)
        self.assertIsNone(value)

    def test_event_order_is_timestamp_order(self):
        events = [{"lastTimestamp": "2026-10-26T10:00:00Z"},
                  {"eventTime": "2026-10-26T09:30:00+02:00"}, {}]
        self.assertEqual(sorted(events, key=event_time), [events[2], events[1], events[0]])

    def test_empty_recent_window_is_explicit_and_startup_retained(self):
        def run(command, **kwargs):
            if "get" in command and "pod" in command:
                value = {"metadata": {"uid": "test"}, "spec": {"containers": [{"name": "api"}]}}
                return subprocess.CompletedProcess(command, 0, json.dumps(value), "")
            if "get" in command:
                return subprocess.CompletedProcess(command, 0, '{"items":[]}', "")
            return subprocess.CompletedProcess(command, 0, "", "")
        bundle = collect("lab", "lab", "api", "api", run,
                         prefix_reader=lambda command: ("Uvicorn running on http://0.0.0.0:8080", False))
        observations = {x.id: x for x in bundle.observations}
        self.assertIn("ten-minute window", observations["logs-limit"].text)
        self.assertIn("Uvicorn", observations["startup"].text)

    def test_framework_conventions_without_listener_evidence_do_not_suffice(self):
        bundle = Bundle.parse({"schema": 1, "target": "demo/api", "observations": [
            {"id": "logs", "kind": "app_log", "source": "app", "text": "Spring application with actuator"},
            {"id": "events", "kind": "probe_result", "source": "events", "text": "statuscode: 404"}]})
        self.assertEqual(diagnose(bundle).cause, "insufficient_evidence")

    def test_development_framework_formats_have_equivalent_baseline_rules(self):
        for text in ("INFO: Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)",
                     'time=2026-10-26T12:00:00Z level=INFO msg="starting HTTP server" address=:8080 readiness_path=/ready role=api'):
            bundle = Bundle.parse({"schema": 1, "target": "demo/api", "observations": [
                {"id": "probe", "kind": "probe_config", "source": "spec", "text": '{"port":9090,"path":"/ready"}'},
                {"id": "events", "kind": "probe_result", "source": "events", "text": "Readiness probe failed: connection refused"},
                {"id": "startup", "kind": "app_log", "source": "app", "text": text}]})
            self.assertEqual(diagnose(bundle).cause, "probe_port_mismatch")

    def test_adapter_can_omit_temperature_and_change_token_parameter(self):
        client = ModelClient("https://example.openai.azure.com", "test", "test",
                             token_parameter="max_completion_tokens", temperature=None)
        self.assertEqual(client.request_settings, {"max_completion_tokens": 700})




if __name__ == "__main__":
    unittest.main()
