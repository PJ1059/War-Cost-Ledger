"""Exact named continuation, within original finite PE read budget."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('screen_dispatch_owned_support',
                                             ROOT / 'tests/test_career_screen_enter_code_capture.py')
support = importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
spec = importlib.util.spec_from_file_location('screen_dispatch_profile_test',
                                             ROOT / 'tools/career-screen-dispatch-code-capture.py')
profile = importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
support.profile = profile.probe
support.support.profile = profile.probe
support.support.support.c = profile.worker

class ScreenDispatchTests(support.ScreenEnterTests):
    def test_actual_caller_precedes_declared_metadata_body(self):
        scenario = support.support.support.Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            profile.worker.verify_saved(meta, raw)
            self.assertEqual(raw[:5], bytes.fromhex('e8f7d00500'))
            self.assertEqual(meta['caller_rva'], 0x1438264)
            self.assertEqual(meta['callee_rva'], 0x1495360)
            self.assertEqual(meta['candidate_body']['target_rva'], 0x1495423)
            self.assertEqual(meta['entry_branch'], 'call_rel32')
            self.assertLessEqual(meta['budget']['read_calls'] + 1, 32)
            self.assertLessEqual(meta['budget']['bytes_requested'] + 5, 8192)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['native_called']);self.assertFalse(meta['native_written'])
            self.assertFalse(meta['logical_function_complete'])
            self.assertNotIn('career_kills', meta);self.assertNotIn('career_deaths', meta)

if __name__ == '__main__':
    unittest.main()
