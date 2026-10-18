"""Two fixed Career rows only, using owned buffers and saved local evidence."""
import importlib.util
import base64
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

target = load('career_target_fixture', ROOT / 'tools/career-target-rows.py')
prior = load('career_target_owned_memory', ROOT / 'tests/test_career_ui_snapshot.py')


class Memory(prior.Memory):
    def __init__(self):
        super().__init__(nodes=0)
        self.rows = [self.first_node]
        for index in range(8):
            self.rows.append(self.rows[-1] + (0x2000 if index % 2 == 0 else 0x3000))
        self.widget(self.list, 0, child=self.rows[0])
        for index, address in enumerate(self.rows):
            self.widget(address, self.list, sibling=self.rows[index + 1] if index < 8 else 0)
        for index, _, tag_key in target.ROWS:
            row = self.rows[index]
            tag, value = row + target.TAG_OFFSET, row + target.VALUE_OFFSET
            self.widget(tag, row, kind=7);self.widget(value, row, kind=7)
            self.label(tag, tag_key, kind=7)
            self.label(value, 0x2BAA24A7, ((target.COUNT_KEY, 4, 351849 if index == 0 else 4633),), kind=7)


class Tests(unittest.TestCase):
    def capture(self, memory):
        return target.capture(memory, memory.identity, clock=lambda: 0)

    def test_only_two_fixed_rows_before_after_no_dfs_or_stride_guess(self):
        memory = Memory();result = self.capture(memory)
        self.assertEqual(result['active_read_calls'], 54)
        self.assertEqual(result['active_read_bytes'], 6601)
        self.assertEqual(result['row_path_before'], memory.rows)
        self.assertEqual(result['row_path_after'], memory.rows)
        self.assertEqual(result['rows_before']['enemy_kills']['value']['candidate_nonnegative32'], 351849)
        self.assertEqual(result['rows_before']['deaths']['value']['candidate_nonnegative32'], 4633)
        self.assertTrue(result['parent_context_tag_argument_stable'])
        for flag in ('career_stats_ready', 'numeric_type_verified', 'account_modified', 'native_called', 'native_written'):
            self.assertFalse(result[flag])
        for address in memory.rows[1:8]:
            self.assertEqual(sum(at == address + target.layout.NEXT and n == 8 for at, n in memory.reads), 2)
            self.assertNotIn((address, 256), memory.reads)

    def test_nonship_zero_registry_code_rows(self):
        for state in (0, 1, 2, 4, 5):
            memory = Memory();memory.states = [state]
            with self.assertRaises(target.NotVisible):self.capture(memory)
            self.assertEqual(len(memory.reads), 2);self.assertEqual(sum(n for _, n in memory.reads), 12)

    def test_changed_pin_no_row_read(self):
        memory = Memory();memory.put(memory.identity['game_base'] + target.layout.PINS[0][0], b'\0')
        with self.assertRaisesRegex(ValueError, 'CODE_PIN'):self.capture(memory)
        self.assertFalse(any(at in memory.rows for at, _ in memory.reads))

    def test_rebuilt_list_with_same_context_final_gate_rejected(self):
        memory = Memory();count = [0]
        def mutate(memory, address, size):
            if address == memory.list:
                count[0] += 1
                if count[0] == 2:memory.widget(memory.list, 0, child=memory.rows[1])
        memory.changed = mutate
        with self.assertRaisesRegex(ValueError, 'LIST_REBUILT'):self.capture(memory)

    def test_final_row_next_changed_with_same_parent_rejected(self):
        memory = Memory();count = [0]
        def mutate(memory, address, size):
            if address == memory.rows[8]:
                count[0] += 1
                if count[0] == 2:memory.widget(address, memory.list, sibling=memory.rows[7])
        memory.changed = mutate
        with self.assertRaisesRegex(ValueError, 'ROW_REBUILT'):self.capture(memory)

    def test_value_kind_count_key_type_or_high_bits_fail(self):
        for failure in ('kind', 'count', 'key', 'type', 'high'):
            memory = Memory();row = memory.rows[8];address = row + target.VALUE_OFFSET
            if failure == 'kind':memory.widget(address, row, kind=8)
            if failure == 'count':memory.put(address + 616, b'\x02')
            if failure == 'key':memory.put(address + 280, struct.pack('<I', 0))
            if failure == 'type':memory.put(address + 284, struct.pack('<I', 1))
            if failure == 'high':memory.put(address + 288, struct.pack('<Q', 1 << 32 | 4633))
            with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, 'IDENTITY|LABEL_OR_COUNT|ARGUMENT_CHANGED'):
                self.capture(memory)

    def test_raw_value_change_between_two_snapshots_is_not_frozen_stat(self):
        memory = Memory();address = memory.rows[8] + target.VALUE_OFFSET + 272;count = [0]
        def mutate(memory, at, size):
            if at == address:
                count[0] += 1
                if count[0] == 2:memory.put(at + 16, struct.pack('<Q', 4634))
        memory.changed = mutate
        with self.assertRaisesRegex(ValueError, 'VALUE_CHANGED'):self.capture(memory)

    def test_cycle_invalid_pointer_guard_short_or_wrong_parent_fail(self):
        for failure in ('cycle', 'pointer', 'guard', 'short', 'parent'):
            memory = Memory()
            if failure == 'cycle':memory.put(memory.rows[4] + 232, struct.pack('<Q', memory.rows[0]))
            if failure == 'pointer':memory.put(memory.rows[4] + 232, struct.pack('<Q', 17))
            if failure == 'guard':memory.guard = memory.rows[8]
            if failure == 'short':memory.short = memory.rows[8]
            if failure == 'parent':memory.widget(memory.rows[8], memory.list + 8)
            with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, 'ROW_CHAIN|UNREADABLE|SHORT_READ|WIDGET_IDENTITY'):
                self.capture(memory)

    def test_total_limits_are_checked_before_query_or_io(self):
        memory = Memory();budget = target.Budget(memory, memory.identity, clock=lambda: 0)
        budget.total['reads'] = 64
        with self.assertRaisesRegex(ValueError, 'TOTAL_BUDGET'):budget.ptr(memory.list)
        self.assertEqual(memory.queries, []);self.assertEqual(memory.reads, [])
        budget.total['reads'] = 0;budget.total['bytes'] = 8192
        with self.assertRaisesRegex(ValueError, 'TOTAL_BUDGET'):budget.ptr(memory.list)
        self.assertEqual(memory.queries, []);self.assertEqual(memory.reads, [])

    def test_wait_more_than120_seconds_success_once_and_no_sync(self):
        memory = Memory();memory.states = [2] * 65 + [3];sleeps = []
        with tempfile.TemporaryDirectory() as temporary:
            result = target.run(Path(temporary) / 'new', wait=True, deps=prior.deps(memory),
                                clock=lambda: 0, sleep=sleeps.append)
        self.assertEqual(sleeps, [2] * 65)
        self.assertEqual(result['waiting'], {'polls': 65, 'bytes': 780, 'reads': 130})
        self.assertEqual(memory.entered, 66)
        self.assertFalse(result['career_stats_ready']);self.assertFalse(result['account_modified'])

    def test_failure_not_retried_existing_folder_zero_dependency(self):
        memory = Memory();memory.short = memory.list;sleeps = []
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'new'
            with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
                target.run(folder, wait=True, deps=prior.deps(memory), clock=lambda: 0, sleep=sleeps.append)
            self.assertEqual(json.loads((folder / 'status.json').read_text('utf8'))['status'], 'failed')
        self.assertEqual(sleeps, []);self.assertEqual(memory.entered, 1)
        with tempfile.TemporaryDirectory() as temporary, patch.object(target.layout, 'dependencies', side_effect=AssertionError('dependency')):
            with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):target.run(temporary, wait=True)

    def test_actual_partial_bytes_two_rows_match_user_confirmed_values(self):
        path = ROOT / 'tests/fixtures/career-visible-rows.json'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         '8b78e6d5e3e0c7debc72c6613f8ae61c8094e2a05271d81fa910b667caa8f79d')
        fixture = json.loads(path.read_text('utf8'))
        class Owned:
            def __init__(self):
                self.identity = {'game_base': fixture['identity']['game_base'], 'game_size': target.layout.IMAGE_SIZE}
                self.bytes, self.reads = {}, []
                for record in fixture['read_records']:
                    raw = bytes.fromhex(record['raw_hex']) if 'raw_hex' in record else base64.b64decode(record['raw_b64'])
                    self.assert_record(record, raw)
                    self.bytes.update((record['address'] + i, value) for i, value in enumerate(raw))
            @staticmethod
            def assert_record(record, raw):
                if len(raw) != record['length']:raise AssertionError('fixture length')
            def query(self, address):
                base = self.identity['game_base'];image = base <= address < base + target.layout.IMAGE_SIZE
                if image:return {'base': base, 'size': target.layout.IMAGE_SIZE,
                                 'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
                for start, length in fixture['owned_address_regions']:
                    if start <= address < start + length:
                        return {'base': start, 'size': length, 'state': 0x1000, 'type': 0x20000, 'protect': 4}
                raise AssertionError(f'not owned address {address:#x}')
            def read(self, address, length):
                self.reads.append((address, length))
                return bytes(self.bytes[address + i] for i in range(length))
        memory = Owned();result = self.capture(memory)
        self.assertEqual(result['active_read_calls'], 54);self.assertEqual(result['active_read_bytes'], 6729)
        self.assertEqual(result['row_path_before'], [row[0] for row in fixture['row_chain']])
        self.assertEqual(result['rows_before']['enemy_kills']['value']['value_raw'], 351849)
        self.assertEqual(result['rows_before']['deaths']['value']['value_raw'], 4633)
        self.assertFalse(result['career_stats_ready']);self.assertFalse(result['numeric_type_verified'])
        # The source was incomplete; this offline replay is not a live after-
        # snapshot or actual synchronisation proof.
        self.assertFalse(fixture['source_complete'])


if __name__ == '__main__':
    unittest.main()
