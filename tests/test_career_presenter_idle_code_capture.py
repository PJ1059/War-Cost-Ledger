"""Owned exact idle-path profile with the original entry's fresh E9."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('presenter_idle_owned_support',
                                             ROOT / 'tests/test_career_presenter_init_body_capture.py')
support = importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
spec = importlib.util.spec_from_file_location('presenter_idle_profile_test',
                                             ROOT / 'tools/career-presenter-idle-code-capture.py')
profile = importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
support.profile = profile
support.support.profile = profile.probe
support.support.support.c = profile.worker


class IdleTests(support.BodyTests):
    def test_actual_caller_precedes_declared_metadata_body(self):
        scenario = support.support.support.Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            profile.worker.verify_saved(meta, raw)
            self.assertEqual(raw[:5], bytes.fromhex('e99b010000'))
            self.assertEqual(meta['caller_rva'], 0x14C03B0)
            self.assertEqual(meta['callee_rva'], 0x14C0550)
            self.assertEqual(meta['candidate_body']['target_rva'], 0x14C0604)
            self.assertEqual(meta['entry_branch'], 'jmp_rel32')
            self.assertLessEqual(meta['budget']['read_calls'] + 1, 32)
            self.assertLessEqual(meta['budget']['bytes_requested'] + 5, 8192)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['native_called']);self.assertFalse(meta['native_written'])
            self.assertFalse(meta['logical_function_complete'])
            self.assertNotIn('career_kills', meta)


if __name__ == '__main__':
    unittest.main()
