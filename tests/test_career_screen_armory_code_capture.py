"""Owned PE fixtures for the exact presenter5 screen-dispatch branch."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('screen_armory_owned_support',
                                             ROOT / 'tests/test_career_presenter_init_code_capture.py')
support = importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
spec = importlib.util.spec_from_file_location('screen_armory_profile_test',
                                             ROOT / 'tools/career-screen-armory-code-capture.py')
profile = importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
support.profile = profile
support.support.c = profile.worker


class ScreenArmoryTests(support.PresenterInitTests):
    def test_actual_caller_precedes_declared_metadata_body(self):
        scenario = support.support.Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            profile.verify_saved(meta, raw)
            self.assertEqual(raw[:5], bytes.fromhex('e93330f8ff'))
            self.assertEqual(meta['caller_rva'], 0x14B5178)
            self.assertEqual(meta['callee_rva'], 0x14381B0)
            self.assertEqual(meta['candidate_body']['target_rva'], 0x14381B0)
            self.assertEqual(meta['entry_branch'], 'jmp_rel32')
            self.assertLessEqual(meta['budget']['read_calls'] + 1, 32)
            self.assertLessEqual(meta['budget']['bytes_requested'] + 5, 8192)
            self.assertLessEqual(meta['bytes_planned'], 4096)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['native_called']);self.assertFalse(meta['native_written'])
            self.assertNotIn('career_kills', meta);self.assertNotIn('career_deaths', meta)

    def test_prefix_time_counts_before_first_metadata_io(self):
        memory = support.support.Memory()
        ticks = iter((0, 3, 3))
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            profile.capture(memory, memory.identity, clock=lambda: next(ticks))
        self.assertEqual(memory.reads, [(memory.base + 0x14B5178, 5)])

    def test_real_owned_source_switch_entry(self):
        path = ROOT / 'dist/career-enter-wait-20261012-183f5369/evidence/capture/drain.bin'
        if not path.exists():
            self.skipTest('local immutable source not supplied')
        import hashlib, struct
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), profile.worker.SOURCE_SHA)
        body = raw[5:]
        self.assertEqual(struct.unpack_from('<I', body, 0x14B59E4 - 0x14B5080)[0], 0x14B515C)
        self.assertEqual(body[0x14B5178 - 0x14B5080:0x14B517D - 0x14B5080], bytes.fromhex(profile.worker.CALL_PIN))


if __name__ == '__main__':
    unittest.main()
