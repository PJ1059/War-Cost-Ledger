"""Owned PE/Ship/short-JE fixtures; no game process or native execution."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('match_fragment_owned_support',
                                             ROOT / 'tests/test_hit_consumer_followup.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
spec = importlib.util.spec_from_file_location('match_fragment_private_profile',
                                             ROOT / 'tools/career-local-profile-match-fragment-capture.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
support.c = profile.worker
BaseMemory = support.Memory


class Memory(BaseMemory):
    def __init__(self, *, bad_edge=False, **options):
        super().__init__(**options)
        self.bad_edge = bad_edge
        self.begin, self.end = profile.TARGET_RVA, profile.TARGET_RVA + 0x100

    def read(self, address, length):
        if address == self.base + profile.EDGE_RVA:
            self.reads.append((address, length))
            raw = b'\x74\x12' if self.bad_edge else bytes.fromhex(profile.EDGE_PIN)
            return raw[:-1] if self.short else raw
        return super().read(address, length)


support.Memory = Memory


class MatchFragmentTests(unittest.TestCase):
    def test_actual_guard_then_declared_fragment_shared_io_budget(self):
        scenario = support.Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = scenario.run(parent)
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            profile.verify_saved(meta, raw)
            self.assertEqual(raw[:2].hex(), '7413')
            self.assertEqual(meta['target_rva'], 0x19A69FD)
            self.assertEqual(meta['function_begin'], 0x19A69FD)
            self.assertEqual(meta['entry_branch'], 'short_je_rel8')
            self.assertTrue(meta['fragment_only'])
            self.assertFalse(meta['native_called'])
            self.assertFalse(meta['native_written'])
            self.assertFalse(meta['logical_function_complete'])
            reads = scenario.memories[0].reads
            self.assertEqual(reads[2], (Memory.base + profile.EDGE_RVA, 2))
            self.assertEqual(len(reads), meta['budget']['read_calls'] + 4)
            self.assertEqual(sum(n for _, n in reads), meta['budget']['bytes_requested'] + 24)
            self.assertLessEqual(meta['budget']['read_calls'], 32)
            self.assertLessEqual(meta['budget']['bytes_requested'], 8192)

    def test_bad_guard_stops_before_metadata(self):
        memory = Memory(bad_edge=True)
        with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
            profile.capture(memory, memory.identity, clock=lambda: 0)
        self.assertEqual(memory.reads, [(Memory.base + profile.EDGE_RVA, 2)])

    def test_short_guard_and_body_rejected(self):
        memory = Memory(); memory.short = True
        with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
            profile.capture(memory, memory.identity, clock=lambda: 0)
        memory = Memory(short_body=True)
        with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
            profile.capture(memory, memory.identity, clock=lambda: 0)

    def test_time_limit_before_first_physical_io(self):
        memory = Memory(); ticks = iter((0, 3, 3))
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            profile.capture(memory, memory.identity, clock=lambda: next(ticks))
        self.assertEqual(memory.reads, [])

    def test_guard_time_is_not_reset_by_inner_pe_reader(self):
        memory = Memory(); ticks = iter((0, 0, 0, 3, 3, 3, 3))
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            profile.capture(memory, memory.identity, clock=lambda: next(ticks, 3))
        self.assertEqual(memory.reads, [(Memory.base + profile.EDGE_RVA, 2)])

    def test_guard_is_inside_total_byte_and_read_limits(self):
        memory = Memory()
        with patch.object(profile.reader, 'MAX_BYTES', 13):
            with self.assertRaisesRegex(ValueError, 'READ_BUDGET'):
                profile.capture(memory, memory.identity, clock=lambda: 0)
        self.assertEqual(memory.reads, [(Memory.base + profile.EDGE_RVA, 2)])
        memory = Memory()
        with patch.object(profile.reader, 'MAX_READS', 2):
            with self.assertRaisesRegex(ValueError, 'BUDGET'):
                profile.capture(memory, memory.identity, clock=lambda: 0)
        self.assertEqual(len(memory.reads), 2)

    def test_declared_unwind_ancestor_replayed_as_fragment(self):
        memory = Memory(); memory.configure_chain(parents=1)
        raw, meta = profile.capture(memory, memory.identity, clock=lambda: 0)
        profile.verify_saved(meta, raw)
        self.assertEqual(len(meta['unwind_chain']), 2)
        self.assertEqual(meta['boundary_kind'], 'target_range_plus_bounded_unwind_ancestry')
        self.assertFalse(meta['all_sibling_fragments_captured'])
        self.assertFalse(meta['logical_function_complete'])
        self.assertEqual(len(raw[2:]), 256 + 0x80)

    def test_nonship_and_changed_ship_not_success(self):
        for options, reason in [({'stages': (4,)}, 'EXPECTS_SHIP'),
                                ({'after': 4}, 'SHIP_CHANGED')]:
            scenario = support.Scenario(**options)
            with tempfile.TemporaryDirectory() as parent:
                with self.assertRaisesRegex(ValueError, reason):scenario.run(parent)
                if reason == 'EXPECTS_SHIP':
                    self.assertEqual(sum(n for _, n in scenario.memories[0].reads), 12)

    def test_oversized_declared_fragment_does_not_read_body(self):
        memory = Memory(); memory.end = memory.begin + 4097
        with self.assertRaisesRegex(ValueError, 'FUNCTION_TOO_LARGE'):
            profile.capture(memory, memory.identity, clock=lambda: 0)
        self.assertFalse(any(at == memory.base + memory.begin for at, _ in memory.reads))

    def test_source_edge_is_parent_end_and_original_tools_unchanged(self):
        source = profile.verify_source()
        self.assertEqual(source['parent_end'], profile.TARGET_RVA)
        self.assertEqual(profile.edge_target(bytes.fromhex('7413')), profile.TARGET_RVA)
        self.assertEqual(support.OLD, (support.old_reader.TARGET_RVA, support.old_reader.TARGET_PIN,
                         support.old_reader.REVISION, support.old_fire.RANGES,
                         support.old_fire.PINS, support.old_fire.REVISION))

    def test_saved_guard_boundary_and_budget_tampering_rejected(self):
        memory = Memory(); raw, meta = profile.capture(memory, memory.identity, clock=lambda: 0)
        for mutate in [lambda m:m.update(entry_branch='call_rel32'),
                       lambda m:m['source_parent'].update(parent_end=0x19A6C30),
                       lambda m:m['candidate_body'].update(function_begin=0x19A6990),
                       lambda m:m['budget'].update(read_calls=33)]:
            bad = copy.deepcopy(meta); mutate(bad)
            with self.assertRaises(ValueError):profile.verify_saved(bad, raw)
        with self.assertRaises(ValueError):profile.verify_saved(meta, raw[:-1])


if __name__ == '__main__':
    unittest.main()
