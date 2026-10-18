"""Owned exact screen constructor E8 and private exception profile."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('screen_constructor_owned_support',
                                             ROOT / 'tests/test_career_presenter_init_code_capture.py')
support = importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
spec = importlib.util.spec_from_file_location('screen_constructor_profile_test',
                                             ROOT / 'tools/career-screen-constructor-code-capture.py')
profile = importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
support.profile = profile
support.support.c = profile.worker

class ScreenConstructorTests(support.PresenterInitTests):
    def test_actual_caller_precedes_declared_metadata_body(self):
        scenario = support.support.Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            profile.verify_saved(meta, raw)
            self.assertEqual(raw[:5], bytes.fromhex('e80bfaffff'))
            self.assertEqual(meta['caller_rva'], 0x14381D0)
            self.assertEqual(meta['callee_rva'], 0x1437BE0)
            self.assertEqual(meta['candidate_body']['target_rva'], 0x1437BE0)
            self.assertEqual(meta['entry_branch'], 'call_rel32')
            self.assertLessEqual(meta['budget']['read_calls'] + 1, 32)
            self.assertLessEqual(meta['budget']['bytes_requested'] + 5, 8192)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['native_called']);self.assertFalse(meta['native_written'])
            self.assertNotIn('career_kills', meta);self.assertNotIn('career_deaths', meta)

    def test_prefix_time_counts_before_first_metadata_io(self):
        memory = support.support.Memory()
        ticks = iter((0, 3, 3))
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            profile.capture(memory, memory.identity, clock=lambda: next(ticks))
        self.assertEqual(memory.reads, [(memory.base + 0x14381D0, 5)])

    def test_owned_actual_source_edge(self):
        import hashlib
        folder = ROOT / 'dist/career-screen-armory-code-20261012-a5f63383/capture'
        if not (folder / 'drain.bin').exists():
            self.skipTest('local immutable source not supplied')
        raw = (folder / 'drain.bin').read_bytes()
        meta = json.loads((folder / 'drain.json').read_text('utf8'))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), profile.worker.SOURCE_SHA)
        match = next(r for r in meta['ranges'] if r['rva'] <= 0x14381D0 < r['rva'] + r['length'])
        offset = match['binary_offset'] + 0x14381D0 - match['rva']
        self.assertEqual(raw[offset:offset + 5], bytes.fromhex(profile.worker.CALL_PIN))

if __name__ == '__main__':
    unittest.main()
