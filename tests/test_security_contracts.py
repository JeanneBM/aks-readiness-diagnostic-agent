"""Prevent accidental broadening of the collector's example permissions."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SecurityContractsTests(unittest.TestCase):
    def test_collector_is_namespaced_and_read_only(self):
        items = json.loads((ROOT / 'k8s/collector-readonly.json').read_text())['items']
        self.assertEqual({x['kind'] for x in items}, {'ServiceAccount', 'Role', 'RoleBinding'})
        self.assertTrue(all(x['metadata']['namespace'] == 'readiness-diag-lab' for x in items))
        sa = next(x for x in items if x['kind'] == 'ServiceAccount')
        self.assertIs(sa['automountServiceAccountToken'], False)
        role = next(x for x in items if x['kind'] == 'Role')
        permissions = set()
        for rule in role['rules']:
            self.assertEqual(rule['apiGroups'], [''])
            for resource in rule['resources']:
                for verb in rule['verbs']:
                    permissions.add((resource, verb))
        self.assertEqual(permissions, {('pods', 'get'), ('pods/log', 'get'), ('events', 'list')})
        binding = next(x for x in items if x['kind'] == 'RoleBinding')
        self.assertEqual(binding['roleRef']['kind'], 'Role')
        self.assertEqual(binding['roleRef']['name'], role['metadata']['name'])
        self.assertEqual(binding['subjects'], [{'kind': 'ServiceAccount', 'name': sa['metadata']['name'],
                                              'namespace': sa['metadata']['namespace']}])

    def test_all_workflow_action_references_are_commit_pinned(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            text = path.read_text()
            self.assertNotIn('pull_request_target:', text)
            for action in re.findall(r'^\s*(?:-\s*)?uses:\s*(\S+)', text, re.M):
                with self.subTest(path=path.name, action=action):
                    self.assertRegex(action, r'^[\w.-]+/[\w./-]+@[0-9a-f]{40}$')
