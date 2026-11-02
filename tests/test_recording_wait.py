"""Regression for probe failures observed before application startup logs."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def recorder():
    spec = importlib.util.spec_from_file_location("recording_wait", ROOT / "tools/run_local_lab.py")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def bundle(*items):
    return SimpleNamespace(observations=[
        SimpleNamespace(id=id, kind=kind, text=text) for id, kind, text in items
    ])


class RecordingWaitTests(unittest.TestCase):
    def test_probe_event_before_startup_waits_for_real_log(self):
        lab = recorder()
        early = bundle(("probe", "probe_config", "{}"), ("events", "probe_result", "connection refused"))
        ready = bundle(("probe", "probe_config", "{}"), ("events", "probe_result", "connection refused"),
                       ("startup", "app_log", "Uvicorn running on http://0.0.0.0:8080"))
        with patch.object(lab, "collect", side_effect=[early, ready]) as collect, \
                patch.object(lab.time, "sleep") as sleep:
            self.assertIs(lab.collect_recording_evidence("demo", "uvicorn-port", "port"), ready)
            self.assertEqual(collect.call_count, 2)
            sleep.assert_called_once_with(1)
            collect.assert_called_with("kind-demo", lab.NAMESPACE, "uvicorn-port", "api")

    def test_present_log_ids_without_support_do_not_pass(self):
        lab = recorder()
        irrelevant = bundle(("probe", "probe_config", "{}"), ("events", "probe_result", "404"),
                            ("startup", "app_log", "process starting"))
        with patch.object(lab, "collect", return_value=irrelevant), \
                patch.object(lab.time, "monotonic", side_effect=[0, 31]), \
                patch.object(lab.time, "sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "cause-supporting application log"):
                lab.collect_recording_evidence("demo", "uvicorn-path", "path")
            sleep.assert_not_called()

    def test_missing_evidence_times_out_without_accepting_partial_bundle(self):
        lab = recorder()
        with patch.object(lab, "collect", return_value=bundle()), \
                patch.object(lab.time, "monotonic", side_effect=[0, 31]):
            with self.assertRaisesRegex(ValueError, "events, probe, startup"):
                lab.collect_recording_evidence("demo", "go-port", "port")

    def test_dependency_waits_for_supporting_log_and_healthy_needs_only_status(self):
        lab = recorder()
        early = bundle(("events", "probe_result", "503"), ("logs", "app_log", "starting"))
        ready = bundle(("events", "probe_result", "503"),
                       ("logs", "app_log", 'msg="dependency check failed"'))
        with patch.object(lab, "collect", side_effect=[early, ready]), patch.object(lab.time, "sleep"):
            self.assertIs(lab.collect_recording_evidence("demo", "go-dependency", "dependency"), ready)
        healthy = bundle(("status", "pod_status", "Ready=True"))
        with patch.object(lab, "collect", return_value=healthy), patch.object(lab.time, "sleep") as sleep:
            self.assertIs(lab.collect_recording_evidence("demo", "go-healthy", "healthy"), healthy)
            sleep.assert_not_called()

    def test_startup_probe_does_not_follow_injected_readiness_faults(self):
        lab = recorder()
        for framework in ("uvicorn", "go"):
            for scenario in lab.SCENARIOS:
                item = lab.case_document(framework, scenario)["spec"]["containers"][0]
                self.assertEqual(item["startupProbe"]["httpGet"], {"port": 8080, "path": "/live"})
                self.assertEqual(item["readinessProbe"]["httpGet"]["port"], 9090 if scenario == "port" else 8080)
                self.assertEqual(item["readinessProbe"]["httpGet"]["path"],
                                 "/wrong-readiness-path" if scenario == "path" else "/ready")
