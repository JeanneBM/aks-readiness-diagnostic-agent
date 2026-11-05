import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from readiness_agent.errors import ProviderError
from readiness_agent.evaluation import evaluate, load_cases, score
from readiness_agent.llm import ModelClient
from readiness_agent.models import Diagnosis

DATA = Path(__file__).resolve().parents[1] / 'data/dev'


class ProviderDiagnosticsTests(unittest.TestCase):
    def client(self, **kwargs):
        return ModelClient('https://example.openai.azure.com', 'secret-key', 'test', **kwargs)

    def test_http_details_are_saved_without_sensitive_body_or_header(self):
        error = HTTPError('https://private.invalid', 429, 'secret-message',
                          {'Retry-After': '30', 'Authorization': 'secret-key'}, io.BytesIO(b'secret-body'))
        with tempfile.TemporaryDirectory() as temp, patch('readiness_agent.llm.build_opener') as opener:
            opener.return_value.open.side_effect = error
            output = Path(temp) / 'run'
            summary = evaluate(DATA, output, ['C1'], self.client())
            row = json.loads((output / 'D001-C1-r001.json').read_text())
            self.assertEqual(row['provider_error'], {'http_status': 429, 'retry_after_seconds': 30})
            self.assertEqual(summary['variants']['C1']['provider_errors'], 18)
            self.assertEqual(opener.return_value.open.call_count, 18)  # no retry
            for p in output.glob('*.json'):
                self.assertNotIn('secret-', p.read_text())
                self.assertNotIn('private.invalid', p.read_text())

    def test_untrusted_retry_after_is_not_saved(self):
        bundle = load_cases(DATA)[0][1]
        for value in ('secret-key', '9999', '-1', '12.5'):
            with self.subTest(value=value), patch('readiness_agent.llm.build_opener') as opener:
                opener.return_value.open.side_effect = HTTPError('url', 429, 'reason', {'Retry-After': value}, None)
                with self.assertRaises(ProviderError) as caught:
                    self.client().diagnose(bundle)
                self.assertEqual(caught.exception.details, {'http_status': 429})

    def test_transport_is_categorized_without_raw_exception(self):
        for error, category in [(TimeoutError('secret'), 'timeout'),
                                (URLError(TimeoutError('secret')), 'timeout'),
                                (URLError('secret-host'), 'connection')]:
            with self.subTest(category=category), patch('readiness_agent.llm.build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(ProviderError) as caught:
                    self.client().diagnose(load_cases(DATA)[0][1])
                self.assertEqual(caught.exception.details, {'transport_category': category})
                self.assertNotIn('secret', str(caught.exception))

    def test_pacing_includes_failed_calls_without_retry(self):
        client = self.client(min_request_interval_seconds=5)
        bundle = load_cases(DATA)[0][1]
        with patch('readiness_agent.llm.time.monotonic', side_effect=[10, 12, 15]), \
             patch('readiness_agent.llm.time.sleep') as sleep, \
             patch('readiness_agent.llm.build_opener') as opener:
            opener.return_value.open.side_effect = TimeoutError()
            for _ in range(2):
                with self.assertRaises(ProviderError):
                    client.diagnose(bundle)
            sleep.assert_called_once_with(3)
            self.assertEqual(opener.return_value.open.call_count, 2)

    def test_invalid_intervals_fail_before_network(self):
        for interval in (-1, 61, float('nan'), float('inf'), True):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                self.client(min_request_interval_seconds=interval)

    def test_correct_cause_can_have_citation_gap(self):
        root = DATA.parents[1] / 'eval/2026-11-05-kind-paired/sanitized'
        row = json.loads((root / 'R003-C1-r001.json').read_text())
        cases = DATA.parent / 'recorded-dev/2026-11-02-kind'
        _, bundle, truth = next(x for x in load_cases(cases) if x[0] == 'R003')
        result = score(Diagnosis.parse(row['diagnosis'], bundle), truth)
        self.assertTrue(result['cause_correct'])
        self.assertFalse(result['cause_mismatch'])
        self.assertTrue(result['citation_coverage_gap'])
        self.assertTrue(result['diagnostic_risk'])
