"""Regression on supplied real output and optional freshly compiled process output."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest

from readiness_agent.baseline import diagnose
from readiness_agent.models import Bundle

ROOT = Path(__file__).resolve().parents[1]


def recorder():
    spec = importlib.util.spec_from_file_location("lab_recorder", ROOT / "tools/run_local_lab.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def bundle(log, port, scenario):
    failed = {"port": "connection refused", "path": "statuscode: 404", "dependency": "statuscode: 503"}[scenario]
    return Bundle.parse({"schema": 1, "target": "demo/api", "observations": [
        {"id": "status", "kind": "pod_status", "source": "snapshot", "text": "Ready=False"},
        {"id": "probe", "kind": "probe_config", "source": "spec", "text": json.dumps({
            "port": 1 if scenario == "port" and port != 1 else port,
            "path": "/unknown" if scenario == "path" else "/ready"})},
        {"id": "events", "kind": "probe_result", "source": "test-probe", "text": failed},
        {"id": "startup", "kind": "app_log", "source": "real-go-process", "text": log}]})


class GoLogTests(unittest.TestCase):
    def test_supplied_real_default_startup_is_supported(self):
        log = (ROOT / "tests/golden/go-default-startup.log").read_text()
        evidence = bundle(log, 8080, "port")
        self.assertEqual(diagnose(evidence).cause, "probe_port_mismatch")
        self.assertEqual(recorder().supporting_log_options(evidence, "port"), [["startup"]])

    @unittest.skipUnless(os.environ.get("READINESS_GO_CAPTURE"), "requires fresh native Go capture; CI provides it")
    def test_actual_current_binary_output(self):
        directory = Path(os.environ["READINESS_GO_CAPTURE"])
        provenance = json.loads((directory / "provenance.json").read_text())
        raw = (directory / "server.log").read_bytes()
        self.assertEqual(provenance["status"], "RECORDED")
        self.assertEqual(provenance["source_sha256"], hashlib.sha256((ROOT / "lab/go/main.go").read_bytes()).hexdigest())
        self.assertEqual(provenance["log_sha256"], hashlib.sha256(raw).hexdigest())
        log = raw.decode()
        self.assertIn('msg="starting HTTP server"', log)
        self.assertIn('msg="dependency check failed"', log)
        expected = {"port": "probe_port_mismatch", "path": "probe_path_mismatch", "dependency": "dependency_unavailable"}
        for scenario, cause in expected.items():
            with self.subTest(scenario=scenario):
                evidence = bundle(log, provenance["port"], scenario)
                self.assertEqual(diagnose(evidence).cause, cause)
                self.assertEqual(recorder().supporting_log_options(evidence, scenario), [["startup"]])
