"""One focused owned group. Extra provider/mode/ID fields are synthetic.

Imports only the old sparse-memory class, never runs its tests or live code.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load('career_provider_association_owned', ROOT / 'tools/career-provider-association.py')
prior = load('career_provider_association_sparse_memory', ROOT / 'tests/test_career_target_rows.py')


class Memory(prior.Memory):
    local_user, candidate = 0x303000000, 0x304000000
    peer = 0xFEDCBA0987654321  # identity token, not a pointer followed by the reader

    def __init__(self):
        super().__init__()
        base = self.identity['game_base']
        panel = self.controller + reader.layout.CAREER_PANEL
        self.put(base + reader.LOCAL_USER, struct.pack('<Q', self.local_user))
        self.put(self.local_user + reader.LOCAL_PEER, struct.pack('<Q', self.peer))
        self.put(self.controller + reader.UI_PEER, struct.pack('<Q', self.peer))
        self.put(self.list + reader.FILLED_COUNT, struct.pack('<I', 30))
        blob = struct.pack('<11I', 351849, 0x261C4A52, 0x4657CFB3, 0x61B31723,
                           9, 4633, 10, 20, 0, 0, 0)
        self.put(base + reader.CANDIDATE, struct.pack('<Q', self.candidate))
        self.put(self.candidate + reader.CANDIDATE_FIELDS, blob)
        self.put(panel + reader.MODE, struct.pack('<I', 1) + blob)
        for index, stat_id, value in ((0, 1, 351849), (8, 2, 4633)):
            self.put(self.rows[index] + reader.ROW_META, struct.pack('<II', stat_id, value))
        for rva, pin in reader.PINS:
            self.put(base + rva, bytes.fromhex(pin))


def dependencies(memory, ticks=None):
    values = iter((123456, 123456) if ticks is None else ticks)
    return {**prior.prior.deps(memory), 'process_creation_tick': lambda _: next(values)}


class Tests(unittest.TestCase):
    def test_focused_association_and_withhold_boundaries(self):
        # Actual frozen source PINs are checked offline; heap extras below are
        # owned fixture values, never evidence for the actual game's provider.
        source = reader.validate_source()
        self.assertEqual(len(source), 6)
        scenarios = []
        memory = Memory()
        with tempfile.TemporaryDirectory() as temporary:
            result = reader.run(Path(temporary) / 'complete', pid=123,
                                deps=dependencies(memory), clock=lambda: 0)
            packet = json.loads((Path(temporary) / 'complete/association.json').read_text('utf8'))
            self.assertEqual(packet['status'], 'complete')
        self.assertEqual(result['active_read_calls'], 94)
        self.assertEqual(result['active_query_calls'], 94)
        self.assertEqual(result['active_read_bytes'], 7060)
        self.assertEqual(result['association_before'], result['association_after'])
        fields = result['association_before']
        self.assertEqual(fields['mode_u32'], 1)
        self.assertTrue(fields['panel_copy_equals_candidate'])
        self.assertEqual(fields['rows']['enemy_kills']['row_id'], 1)
        self.assertEqual(fields['rows']['deaths']['candidate_field_u32'], 4633)
        self.assertTrue(all(value['stored_equals_display'] for value in fields['rows'].values()))
        for key in ('candidate_owner_verified', 'candidate_career_semantics_verified',
                    'provider_refresh_verified', 'mode_enum_verified', 'career_stats_ready',
                    'account_modified', 'native_written', 'native_called'):
            self.assertFalse(result[key])
        self.assertNotIn((memory.candidate, 8), memory.reads)
        self.assertEqual(sum(address == memory.candidate + reader.CANDIDATE_FIELDS
                             and size == 44 for address, size in memory.reads), 2)
        scenarios.append({'case': 'stable_owned_association', 'pass': True,
                          'rpm': 94, 'queries': 94, 'bytes': 7060})

        for failure, expected in (('peer', 'NOT_LOCAL_PEER'), ('candidate_changed', 'FIELDS_CHANGED'),
                                  ('mode_changed', 'FIELDS_CHANGED'), ('process_start', 'PROCESS_OR_MODULE_CHANGED')):
            with self.subTest(case=failure), tempfile.TemporaryDirectory() as temporary:
                memory = Memory()
                if failure == 'peer':
                    memory.put(memory.controller + reader.UI_PEER, bytes(8))
                elif failure in ('candidate_changed', 'mode_changed'):
                    address = (memory.candidate + reader.CANDIDATE_FIELDS if failure == 'candidate_changed'
                               else memory.controller + reader.layout.CAREER_PANEL + reader.MODE)
                    count = [0]
                    def mutate(memory, at, size):
                        if at == address:
                            count[0] += 1
                            if count[0] == 2:
                                memory.put(at, struct.pack('<I', 2))
                    memory.changed = mutate
                folder = Path(temporary) / 'rejected'
                ticks = (123456, 123457) if failure == 'process_start' else None
                with self.assertRaisesRegex(ValueError, expected):
                    reader.run(folder, pid=123, deps=dependencies(memory, ticks), clock=lambda: 0)
                self.assertFalse((folder / 'association.json').exists())
                self.assertEqual(json.loads((folder / 'status.json').read_text('utf8'))['status'], 'failed')
                self.assertEqual(memory.entered, 1)  # no retry/wait loop
                if failure == 'peer':
                    self.assertNotIn((memory.candidate + reader.CANDIDATE_FIELDS, 44), memory.reads)
                scenarios.append({'case': failure, 'pass': True, 'packet_withheld': True})

        memory = Memory()
        budget = reader.Budget(memory, memory.identity, clock=lambda: 0)
        budget.queries = reader.MAX_IO
        with self.assertRaisesRegex(ValueError, 'TOTAL_BUDGET'):
            budget.read(memory.candidate + reader.CANDIDATE_FIELDS, 44)
        self.assertEqual(memory.queries, [])
        self.assertEqual(memory.reads, [])
        budget.queries = 0
        budget.total['bytes'] = reader.MAX_BYTES
        with self.assertRaisesRegex(ValueError, 'TOTAL_BUDGET'):
            budget.read(memory.candidate + reader.CANDIDATE_FIELDS, 44)
        self.assertEqual(memory.queries, [])
        with patch.object(reader, 'MAX_IO', 93):
            memory = Memory()
            with self.assertRaisesRegex(ValueError, 'TOTAL_BUDGET'):
                reader.capture(memory, memory.identity, clock=lambda: 0)
            self.assertEqual(len(memory.queries), 93)
        memory = Memory()
        budget = reader.Budget(memory, memory.identity, clock=lambda: 0)
        budget.clock = lambda: 1.0
        with self.assertRaisesRegex(ValueError, 'SOFT_BUDGET'):
            budget.read(memory.candidate + reader.CANDIDATE_FIELDS, 44)
        self.assertEqual(memory.queries, [])
        scenarios.append({'case': 'byte_query_time_caps_before_io', 'pass': True})
        print(json.dumps({'focused_group': 1, 'cases': scenarios, 'game_access': False,
                          'synthetic_extra_fields': ['mode', 'row_id', 'row_value', 'candidate44', 'ui_peer']}, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
