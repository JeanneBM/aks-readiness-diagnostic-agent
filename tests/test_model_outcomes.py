import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from readiness_agent.errors import ModelNoAnswer
from readiness_agent.evaluation import evaluate, load_cases
from readiness_agent.llm import ModelClient

DATA = Path(__file__).resolve().parents[1] / "data/dev"


class OutcomeTests(unittest.TestCase):
    def test_refusal_and_truncation_are_classified_before_json_parsing(self):
        bundle = load_cases(DATA)[0][1]
        for reason, choice in [
            ("refusal", {"finish_reason": "stop", "message": {"refusal": "declined", "content": None}}),
            ("truncated", {"finish_reason": "length", "message": {"content": '{"cause":'}}),
            ("filtered", {"finish_reason": "content_filter", "message": {"content": None}})]:
            with self.subTest(reason=reason), patch("readiness_agent.llm.build_opener") as opener:
                opener.return_value.open.return_value = io.BytesIO(json.dumps({"choices": [choice]}).encode())
                with self.assertRaises(ModelNoAnswer) as error:
                    ModelClient("https://example.openai.azure.com", "test", "test").diagnose(bundle)
                self.assertEqual(error.exception.reason, reason)

    def test_no_answer_is_not_reported_as_invalid_diagnosis(self):
        class Client:
            provider, model, api_version, endpoint = "azure", "test", "test", "https://example.openai.azure.com"
            def diagnose(self, bundle):
                raise ModelNoAnswer("truncated")
        with tempfile.TemporaryDirectory() as temp:
            result = evaluate(DATA, Path(temp) / "run", ["C1"], Client())["variants"]["C1"]
            markdown = (Path(temp) / "run/summary.md").read_text()
        self.assertEqual(result["model_no_answers"], 18)
        self.assertEqual(result["truncated_outputs"], 18)
        self.assertEqual(result["contract_errors"], 0)
        self.assertEqual(result["unsupported_conclusions"], 0)
        self.assertEqual(result["diagnostic_risk_attempts"], 18)
        self.assertIn("No answer", markdown)
