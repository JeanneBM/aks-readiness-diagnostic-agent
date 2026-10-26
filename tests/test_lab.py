import asyncio
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

class LabTests(unittest.TestCase):
    def test_lab_faults_change_probe_not_application_port(self):
        lab = module(ROOT / "tools/run_local_lab.py", "local_lab")
        port = lab.case_document("uvicorn", "port")["spec"]["containers"][0]
        self.assertEqual(port["readinessProbe"]["httpGet"]["port"], 9090)
        self.assertEqual(port["ports"][0]["containerPort"], 8080)
        self.assertEqual(lab.dependency_resources()["items"][0]["kind"], "Deployment")

    def test_local_mutations_require_flag(self):
        lab = module(ROOT / "tools/run_local_lab.py", "local_lab_gate")
        with patch.object(lab, "preflight") as preflight, patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(lab.main(["record", "--output", "not-created"]), 2)
            preflight.assert_not_called()

    def test_asgi_readiness_checks_dependency_but_liveness_does_not(self):
        app = module(ROOT / "lab/uvicorn/app.py", "asgi_lab")
        async def response(path):
            messages = []
            async def send(value):
                messages.append(value)
            await app.app({"type": "http", "path": path}, None, send)
            return messages[0]["status"]
        with patch.object(app, "dependency_ready", return_value=False) as check:
            self.assertEqual(asyncio.run(response("/live")), 200)
            check.assert_not_called()
            self.assertEqual(asyncio.run(response("/ready")), 503)
            self.assertEqual(asyncio.run(response("/wrong")), 404)
        with patch.object(app, "dependency_ready", return_value=True):
            self.assertEqual(asyncio.run(response("/ready")), 200)

