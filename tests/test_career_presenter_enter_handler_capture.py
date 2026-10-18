"""Owned E8/PE profile for the proven presenter5 enter-handler candidate."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('presenter_enter_owned_support',
                                             ROOT / 'tests/test_career_presenter_init_code_capture.py')
support = importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
spec = importlib.util.spec_from_file_location('presenter_enter_profile_test',
                                             ROOT / 'tools/career-presenter-enter-handler-capture.py')
profile = importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
support.profile = profile
support.support.c = profile.worker


class EnterTests(support.PresenterInitTests):
    def test_actual_caller_precedes_declared_metadata_body(self):
        scenario = support.support.Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            profile.verify_saved(meta, raw)
            self.assertEqual(raw[:5], bytes.fromhex('e8be48ffff'))
            self.assertEqual(meta['caller_rva'], 0x14C07BD)
            self.assertEqual(meta['callee_rva'], 0x14B5080)
            self.assertEqual(meta['candidate_body']['target_rva'], 0x14B5080)
            self.assertEqual(meta['entry_branch'], 'call_rel32')
            self.assertLessEqual(meta['budget']['read_calls'] + 1, 32)
            self.assertLessEqual(meta['budget']['bytes_requested'] + 5, 8192)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['native_called']);self.assertFalse(meta['native_written'])
            self.assertNotIn('career_kills', meta)

    def test_prefix_time_counts_before_first_metadata_io(self):
        memory = support.support.Memory()
        ticks = iter((0, 3, 3))
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            profile.capture(memory, memory.identity, clock=lambda: next(ticks))
        self.assertEqual(memory.reads, [(memory.base + 0x14C07BD, 5)])


if __name__ == '__main__':
    unittest.main()
