"""Owned memory/PE/Ship fixtures for one local-peer UI callee; no game access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('career_local_profile_owned_support',
                                             ROOT / 'tests/test_career_presenter_init_code_capture.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
spec = importlib.util.spec_from_file_location('career_local_profile_test',
                                             ROOT / 'tools/career-local-profile-code-capture.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
support.profile = profile
support.support.c = profile.worker


class LocalProfileTests(support.PresenterInitTests):
    def test_actual_caller_precedes_declared_metadata_body(self):
        scenario = support.support.Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            profile.verify_saved(meta, raw)
            self.assertEqual(raw[:5], bytes.fromhex('e8a38a0b00'))
            self.assertEqual(meta['caller_rva'], 0x18EDEE8)
            self.assertEqual(meta['callee_rva'], 0x19A6990)
            self.assertEqual(meta['candidate_body']['target_rva'], 0x19A6990)
            self.assertEqual(meta['entry_branch'], 'call_rel32')
            self.assertLessEqual(meta['budget']['read_calls'] + 1, 32)
            self.assertLessEqual(meta['budget']['bytes_requested'] + 5, 8192)
            self.assertLessEqual(meta['bytes_planned'], 4096)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['native_called'])
            self.assertFalse(meta['native_written'])
            self.assertNotIn('career_kills', meta)
            self.assertNotIn('career_deaths', meta)

    def test_prefix_time_counts_before_first_metadata_io(self):
        memory = support.support.Memory()
        ticks = iter((0, 3, 3))
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            profile.capture(memory, memory.identity, clock=lambda: next(ticks))
        self.assertEqual(memory.reads, [(memory.base + 0x18EDEE8, 5)])

    def test_owned_actual_source_edge_and_argument_window(self):
        folder = ROOT / 'dist/career-panel-init-20261012-8223909e/capture'
        if not (folder / 'drain.bin').exists():
            self.skipTest('local immutable source not supplied')
        raw = (folder / 'drain.bin').read_bytes()
        meta = json.loads((folder / 'drain.json').read_text('utf8'))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), profile.worker.SOURCE_SHA)
        match = next(r for r in meta['ranges'] if r['rva'] <= 0x18EDEC8
                     and 0x18EDEED <= r['rva'] + r['length'])
        offset = match['binary_offset'] + 0x18EDEC8 - match['rva']
        actual = raw[offset:offset + 0x25]
        self.assertEqual(actual.hex(),
                         '488b1521f0b801488d8f200203004533c9c6442420004533c0488b9298b30000e8a38a0b00')
        self.assertEqual(0x18EDEC8 + 7 + struct.unpack_from('<i', actual, 3)[0], 0x347CEF0)
        self.assertEqual(0x18EDEE8 + 5 + struct.unpack_from('<i', actual, 0x21)[0], 0x19A6990)


if __name__ == '__main__':
    unittest.main()
