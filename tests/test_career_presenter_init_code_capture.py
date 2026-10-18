"""Owned exception/Ship fixtures; exact E9 source, never invokes a menu."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('presenter_init_owned_support',
                                             ROOT / 'tests/test_hit_consumer_followup.py')
support = importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
spec = importlib.util.spec_from_file_location('presenter_init_profile_test',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
profile = importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
support.c = profile.worker


class PresenterInitTests(support.Tests):
    def test_actual_caller_precedes_declared_metadata_body(self):
        scenario = support.Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            profile.verify_saved(meta, raw)
            self.assertEqual(raw[:5], bytes.fromhex('e99b010000'))
            self.assertEqual(meta['entry_branch'], 'jmp_rel32')
            self.assertEqual(meta['caller_rva'], 0x14C03B0)
            self.assertEqual(meta['callee_rva'], 0x14C0550)
            self.assertEqual(meta['source_drain_sha256'], profile.worker.SOURCE_SHA)
            self.assertEqual(scenario.memories[0].reads[2], (scenario.memories[0].base + 0x14C03B0, 5))
            self.assertEqual(len(scenario.memories[0].reads), meta['budget']['read_calls'] + 1 + 4)
            self.assertEqual(sum(n for _, n in scenario.memories[0].reads), meta['budget']['bytes_requested'] + 5 + 24)
            self.assertLessEqual(meta['budget']['read_calls'] + 1, 32)
            self.assertLessEqual(meta['budget']['bytes_requested'] + 5, 8192)
            self.assertEqual(meta['budget']['max_reads'], 31)
            self.assertEqual(meta['budget']['max_bytes'], 8187)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['native_called']);self.assertFalse(meta['native_written'])
            self.assertNotIn('career_kills', meta);self.assertNotIn('career_deaths', meta)

    def test_prefix_time_counts_before_first_metadata_io(self):
        memory = support.Memory()
        ticks = iter((0, 3, 3))
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            profile.capture(memory, memory.identity, clock=lambda: next(ticks))
        self.assertEqual(memory.reads, [(memory.base + 0x14C03B0, 5)])


if __name__ == '__main__':
    unittest.main()
