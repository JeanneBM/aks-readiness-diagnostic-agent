import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from readiness_agent.baseline import diagnose
from readiness_agent.evaluation import load_cases, source_digest, validate_manifest
from readiness_agent.llm import ModelClient, schema_for_bundle
from readiness_agent.models import Bundle, RECOMMENDATIONS
from tools.rescore_recorded_pilot import rescore

ROOT = Path(__file__).resolve().parents[1]


class ReviewFixTests(unittest.TestCase):
    def test_source_hash_is_independent_of_newlines_but_detects_code_change(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b, c = [Path(temp) / x for x in ('lf.py', 'crlf.py', 'changed.py')]
            a.write_bytes(b'x = 1\nprint(x)\n')
            b.write_bytes(b'x = 1\r\nprint(x)\r\n')
            c.write_bytes(b'x = 2\nprint(x)\n')
            self.assertEqual(source_digest(a), source_digest(b))
            self.assertNotEqual(source_digest(a), source_digest(c))

    def test_python_patch_version_stays_strict(self):
        frozen = {'schema': 2, 'python': '3.12.7'}
        with self.assertRaises(ValueError):
            validate_manifest(frozen, {'schema': 2, 'python': '3.12.8'}, False)

    def test_bundle_schema_does_not_leak_ids_between_requests(self):
        bundles = [Bundle.parse({'schema': 1, 'target': 'test', 'observations': [
            {'id': name, 'kind': 'app_log', 'source': 'test', 'text': 'untrusted'}]})
            for name in ('first', 'second')]
        for bundle, name in zip(bundles, ('first', 'second')):
            self.assertEqual(schema_for_bundle(bundle)['properties']['evidence_ids']['items']['enum'], [name])
        empty = Bundle.parse({'schema': 1, 'target': 'test', 'observations': []})
        self.assertEqual(schema_for_bundle(empty)['properties']['evidence_ids']['maxItems'], 0)

    def test_provider_advice_is_replaced_even_if_schema_is_bypassed(self):
        bundle = load_cases(ROOT / 'data/dev')[0][1]
        answer = diagnose(bundle).to_dict()
        answer['recommendation'] = 'kubectl delete namespace production'
        payload = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(answer)}}]}
        with patch('readiness_agent.llm.build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(json.dumps(payload).encode())
            result, _ = ModelClient('https://example.openai.azure.com', 'test', 'test').diagnose(bundle)
            request = json.loads(opener.return_value.open.call_args.args[0].data)
        self.assertEqual(result.recommendation, RECOMMENDATIONS[result.cause])
        schema = request['response_format']['json_schema']['schema']
        self.assertEqual(set(schema['properties']['recommendation']['enum']), set(RECOMMENDATIONS.values()))
        self.assertEqual(set(schema['properties']['evidence_ids']['items']['enum']),
                         {o.id for o in bundle.observations})

    def test_posthoc_rescore_preserves_errors_accuracy_and_originals(self):
        base = ROOT / 'eval/2026-11-05-kind-paired'
        before = {p.name: p.read_bytes() for p in (base / 'sanitized').iterdir()}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'rescore.json'
            result = rescore(base / 'sanitized', ROOT / 'data/recorded-dev/2026-11-02-kind',
                             base / 'rubric-v2', output)
            c1 = result['variants']['C1']
            self.assertEqual((c1['correct_attempts'], c1['errors']), (9, 10))
            self.assertEqual((c1['original_risk_attempts'], c1['revised_risk_attempts']), (6, 3))
            with self.assertRaises(FileExistsError):
                rescore(base / 'sanitized', ROOT / 'data/recorded-dev/2026-11-02-kind',
                        base / 'rubric-v2', output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (base / 'sanitized').iterdir()})
