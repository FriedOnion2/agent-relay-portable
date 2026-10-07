import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from relay import health, registry


class HealthTests(unittest.TestCase):
    def test_checks_all_six_without_reading_real_sources_or_claiming_vendor_resume(self):
        with patch.object(registry,'get',side_effect=AssertionError('must not inspect user data')):
            result=health.report()
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['adapters']),6)
        for row in result['adapters']:
            self.assertEqual(row['status'],'passed')
            self.assertIsNone(row['client_version'])
            self.assertEqual(row['native_resume'],'not-tested')

    def test_export_contains_evidence_and_failure_is_not_hidden(self):
        with patch.object(registry._ADAPTERS['codex'],'read',side_effect=ValueError('fixture failure')):
            result=health.report()
        self.assertFalse(result['ok'])
        with tempfile.TemporaryDirectory() as root:
            health.export(result,root)
            self.assertIn('fixture failure',(Path(root)/'index.html').read_text(encoding='utf-8'))
            self.assertEqual(json.loads((Path(root)/'health.json').read_text(encoding='utf-8'))['ok'],False)
