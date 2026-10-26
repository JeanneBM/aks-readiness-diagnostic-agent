import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from readiness_agent.baseline import diagnose
from readiness_agent.cli import main, write_new
from readiness_agent.collector import collect, redact
from readiness_agent.evaluation import evaluate, fingerprint, load_cases, paired_comparison
from readiness_agent.llm import ModelClient
from readiness_agent.models import Bundle, Diagnosis

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/dev"


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load_cases(CASES)[0][1]

    def test_ground_truth_cannot_enter_bundle(self):
        value = self.bundle.to_dict()
        value["cause"] = "probe_port_mismatch"
        with self.assertRaises(ValueError):
            Bundle.parse(value)

    def test_duplicate_ids_rejected(self):
        value = self.bundle.to_dict()
        value["observations"].append(value["observations"][0])
        with self.assertRaises(ValueError):
            Bundle.parse(value)

    def test_fabricated_citation_rejected(self):
        value = diagnose(self.bundle).to_dict()
        value["evidence_ids"] = ["invented"]
        with self.assertRaises(ValueError):
            Diagnosis.parse(value, self.bundle)

    def test_unsupported_output_fields_rejected(self):
        value = diagnose(self.bundle).to_dict()
        value["execute"] = "kubectl delete pod"
        with self.assertRaises(ValueError):
            Diagnosis.parse(value, self.bundle)

    def test_conclusion_requires_citations(self):
        value = diagnose(self.bundle).to_dict()
        value["evidence_ids"] = []
        with self.assertRaises(ValueError):
            Diagnosis.parse(value, self.bundle)

    def test_empty_bundle_abstains(self):
        empty = Bundle.parse({"schema": 1, "target": "demo/api", "observations": []})
        self.assertEqual(diagnose(empty).cause, "insufficient_evidence")


class ReplayTests(unittest.TestCase):
    def test_exact_paired_comparison(self):
        rows = []
        for i in range(6):
            rows.extend([{"case_id": str(i), "variant": "A1", "cause_correct": False},
                         {"case_id": str(i), "variant": "C1", "cause_correct": True}])
        result = paired_comparison(rows, "C1")
        self.assertEqual(result["challenger_only_correct"], 6)
        self.assertEqual(result["exact_mcnemar_p"], 0.03125)
        self.assertEqual(result["accuracy_difference_pp"], 100)

    def test_development_ground_truth(self):
        for case_id, bundle, truth in load_cases(CASES):
            with self.subTest(case=case_id):
                answer = diagnose(bundle)
                self.assertEqual(answer.cause, truth["cause"])
                self.assertTrue(set(truth["required_evidence_ids"]) <= set(answer.evidence_ids))

    def test_model_errors_remain_errors(self):
        class Broken:
            provider = "azure"
            model = "test"
            api_version = "test"
            endpoint = "https://example.openai.azure.com"

            def diagnose(self, bundle):
                raise ValueError("sensitive-provider-body")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            result = evaluate(CASES, output, ["A1", "C1"], Broken())
            self.assertEqual(result["variants"]["C1"]["errors"], 18)
            self.assertEqual(result["variants"]["A1"]["correct"], 18)
            self.assertNotIn("sensitive-provider-body", (output / "D001-C1.json").read_text())

    def test_cascade_calls_only_on_rule_abstention(self):
        class Echo:
            provider = "azure"
            model = "test"
            api_version = "test"
            endpoint = "https://example.openai.azure.com"
            calls = 0

            def diagnose(self, bundle):
                self.calls += 1
                return diagnose(bundle), {"total_tokens": 12}
        client = Echo()
        with tempfile.TemporaryDirectory() as temp:
            result = evaluate(CASES, Path(temp) / "run", ["H"], client)
        self.assertEqual(client.calls, 7)
        self.assertEqual(result["variants"]["H"]["tokens_reported"], 84)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            evaluate(CASES, output, ["A1"])
            with self.assertRaises(FileExistsError):
                evaluate(CASES, output, ["A1"])

    def test_manifest_mismatch_blocks_run(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "frozen.json"
            value = fingerprint(CASES)
            value["python"] = "changed"
            manifest.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                evaluate(CASES, Path(temp) / "run", ["A1"], manifest=manifest)
            self.assertFalse((Path(temp) / "run").exists())

    def test_matching_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / "frozen.json"
            manifest.write_text(json.dumps(fingerprint(CASES)))
            result = evaluate(CASES, Path(temp) / "run", ["A1"], manifest=manifest)
            self.assertEqual(result["variants"]["A1"]["correct"], 18)

    def test_model_calls_require_explicit_flag(self):
        with patch("sys.stderr", new=io.StringIO()), patch("readiness_agent.cli.ModelClient.from_env") as factory:
            self.assertEqual(main(["diagnose", "not-opened.json", "--variant", "C1"]), 2)
            factory.assert_not_called()

    def test_cluster_reads_require_explicit_flag(self):
        with patch("sys.stderr", new=io.StringIO()), patch("readiness_agent.cli.collect") as collector:
            self.assertEqual(main(["collect", "--context", "lab", "--namespace", "lab", "--pod", "pod",
                                   "--container", "api", "--output", "unused.json"]), 2)
            collector.assert_not_called()


class CollectorTests(unittest.TestCase):
    def test_reads_only_allowlisted_resources_and_redacts(self):
        calls = []
        snapshot = {"metadata": {"uid": "synthetic-uid"},
                    "spec": {"containers": [{"name": "api", "env": [{"name": "PASSWORD", "value": "do-not-export"}],
                        "ports": [{"name": "http", "containerPort": 8080}],
                        "readinessProbe": {"httpGet": {"port": "http", "path": "/ready"}}}]},
                    "status": {"conditions": [{"type": "Ready", "status": "False"}]}}

        def run(command, **kwargs):
            calls.append(command)
            if "get" in command and "pod" in command:
                data = json.dumps(snapshot)
            elif "events" in command:
                data = json.dumps({"items": [{"message": "Readiness probe failed: connection refused"},
                                            {"message": "Liveness probe failed: unrelated"}]})
            else:
                data = "Listening on 0.0.0.0:9000\npassword=confidential\n"
            return subprocess.CompletedProcess(command, 0, data, "")
        bundle = collect("lab", "readiness-lab", "pod", "api", run)
        serialized = json.dumps(bundle.to_dict())
        self.assertNotIn("do-not-export", serialized)
        self.assertNotIn("confidential", serialized)
        self.assertNotIn("Liveness", serialized)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("get" in c or "logs" in c for c in calls))
        self.assertEqual(diagnose(bundle).cause, "probe_port_mismatch")

    def test_bad_target_rejected_before_subprocess(self):
        with self.assertRaises(ValueError):
            collect("lab", "lab", "--all", "api", lambda *a, **k: self.fail("called"))

    def test_failed_read_does_not_expose_stderr(self):
        def run(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 1, "", "sensitive-path-or-token")
        with self.assertRaisesRegex(ValueError, "kubectl read failed") as error:
            collect("lab", "lab", "pod", "api", run)
        self.assertNotIn("sensitive-path-or-token", str(error.exception))

    def test_redaction_examples(self):
        self.assertNotIn("abc123", redact("api_key=abc123"))
        self.assertNotIn("person@example.test", redact("person@example.test"))
        self.assertNotIn("secret-value", redact("Bearer secret-value"))


class ModelTests(unittest.TestCase):
    def test_endpoint_constraints(self):
        for endpoint in ("http://example.openai.azure.com", "https://attacker.invalid",
                         "https://example.openai.azure.com/?key=secret"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                ModelClient(endpoint, "test-key", "test-model")

    def test_request_contains_no_ground_truth(self):
        bundle = load_cases(CASES)[0][1]
        answer = diagnose(bundle).to_dict()
        payload = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}],
                   "usage": {"total_tokens": 42}}
        response = io.BytesIO(json.dumps(payload).encode())
        with patch("readiness_agent.llm.build_opener") as opener:
            opener.return_value.open.return_value = response
            result, usage = ModelClient("https://example.openai.azure.com", "test-key", "test-model").diagnose(bundle)
            request = opener.return_value.open.call_args.args[0]
            sent = json.loads(request.data)["messages"][1]["content"]
            self.assertNotIn("required_evidence_ids", sent)
            self.assertNotIn("ground_truth", sent)
            self.assertNotIn("labels", sent)
            self.assertEqual(result.cause, answer["cause"])
            self.assertEqual(usage["total_tokens"], 42)

    def test_provider_fabrication_fails_validation(self):
        bundle = load_cases(CASES)[0][1]
        answer = diagnose(bundle).to_dict()
        answer["evidence_ids"] = ["invented"]
        response = io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}]}).encode())
        with patch("readiness_agent.llm.build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(ValueError):
                ModelClient("https://example.openai.azure.com", "test-key", "test-model").diagnose(bundle)


if __name__ == "__main__":
    unittest.main()
