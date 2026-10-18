"""Reuse owned PE/Ship fixtures with a private named presenter profile."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('presenter_owned_support',
                                             ROOT / 'tests/test_career_format_code_followup.py')
support = importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
spec = importlib.util.spec_from_file_location('presenter_profile_test',
                                             ROOT / 'tools/career-presenter-code-capture.py')
presenter = importlib.util.module_from_spec(spec);spec.loader.exec_module(presenter)
support.career, support.worker, support.reader = presenter, presenter.worker, presenter.worker.session.reader


class PresenterTests(support.CareerFormatTests):
    def test_named_native_pin_in_declared_body_without_impact_prefix(self):
        scenario = support.Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            presenter.verify_saved(meta, raw)
            self.assertEqual(support.reader.TARGET_RVA, 0x14C0350)
            self.assertEqual(support.reader.TARGET_PIN, '48895c24084889742410574883ec208b')
            self.assertEqual(raw[0x50:0x60], bytes.fromhex(presenter.TARGET_PIN))
            self.assertEqual(meta['target_rva'], presenter.TARGET_RVA)
            self.assertEqual(meta['source_revision'], presenter.REVISION)
            self.assertEqual(meta['bytes_written'], 256)
            self.assertNotIn('caller_rva', meta)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['native_called']);self.assertFalse(meta['native_written'])
            memory = scenario.memories[-1]
            self.assertEqual(memory.code_reads(), [(memory.begin, 256)])
            self.assertEqual(len(memory.reads), meta['budget']['read_calls'] + 4)
            self.assertEqual(sum(n for _, n in memory.reads), meta['budget']['bytes_requested'] + 24)
            self.assertLessEqual(meta['budget']['read_calls'], 32)
            self.assertLessEqual(meta['budget']['bytes_requested'], 8192)
            self.assertTrue(memory.closed)
            self.assert_profiles_unchanged()


if __name__ == '__main__':
    unittest.main()
