"""Owned sparse-memory fixtures only: no game, GUI, account, or native calls."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_ui_fixture', ROOT / 'tools/career-ui-snapshot.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class Memory:
    identity = {'game_base': 0x180000000, 'game_size': reader.IMAGE_SIZE,
                'exe_path': 'owned.exe', 'game_path': 'owned.dll'}
    state_context, dispatch, controller, gui = 0x300000000, 0x300200000, 0x300400000, 0x300800000
    first_node, strings = 0x301000000, 0x302000000

    def __init__(self, nodes=1):
        self.bytes, self.reads, self.queries, self.entered = {}, [], [], 0
        self.guard, self.short, self.changed = None, None, None
        self.states, self.alphas = [3], [1.0]
        self.list = self.controller + reader.CAREER_PANEL + reader.CAREER_LIST
        self.alpha_address = self.controller + reader.CAREER_PANEL + reader.CAREER_TRACK + 84
        self.put(self.identity['game_base'] + reader.STATE_GLOBAL, struct.pack('<Q', self.state_context))
        self.put(self.state_context + reader.STATE_OFFSET, struct.pack('<I', 3))
        self.put(self.identity['game_base'] + reader.DISPATCH_GLOBAL, struct.pack('<Q', self.dispatch))
        self.put(self.dispatch + reader.COUNT, struct.pack('<I', 1))
        self.put(self.dispatch + reader.ROWS, struct.pack('<QII', self.controller, 224, 0))
        self.put(self.alpha_address, struct.pack('<f', 1.0))
        self.widget(self.list, 0, child=self.first_node if nodes else 0)
        for index in range(nodes):
            node = self.first_node + index * 1024
            self.widget(node, self.list, sibling=node + 1024 if index + 1 < nodes else 0)
            self.put(node + reader.LABEL_START, bytes(reader.LABEL_BYTES))
        for rva, pin in reader.PINS:
            self.put(self.identity['game_base'] + rva, bytes.fromhex(pin))

    def put(self, address, raw):
        self.bytes.update((address + i, value) for i, value in enumerate(raw))

    def widget(self, address, parent, *, child=0, sibling=0, context=None, kind=1):
        raw = bytearray(reader.HEADER_BYTES)
        struct.pack_into('<I', raw, 0, 1 | kind << 18)
        struct.pack_into('<QQQQ', raw, reader.CHILD, child, sibling, parent, self.gui if context is None else context)
        self.put(address, raw)

    def label(self, address, key, arguments=(), count=None, kind=8):
        # This fixture deliberately uses the source-proven 24-byte descriptor,
        # never interprets raw type 2/3/4 as a numeric value.
        raw = bytearray(reader.LABEL_BYTES)
        struct.pack_into('<I', raw, 0, key)
        raw[344] = len(arguments) if count is None else count
        for index, (arg_key, arg_type, value) in enumerate(arguments):
            struct.pack_into('<IIQ', raw, 8 + index * 24, arg_key, arg_type, value)
        self.put(address + reader.LABEL_START, raw)
        flags = struct.unpack('<I', bytes(self.bytes[address + i] for i in range(4)))[0]
        self.put(address, struct.pack('<I', flags & ~(15 << 18) | kind << 18))

    def text(self, address, value):
        raw = value.encode('utf8') + b'\0'
        self.put(address, raw.ljust(reader.STRING_BYTES, b'\0'))

    def query(self, address):
        self.queries.append(address)
        base = self.identity['game_base']
        image = base <= address < base + reader.IMAGE_SIZE
        return {'base': base if image else 0x300000000,
                'size': reader.IMAGE_SIZE if image else 0x10000000,
                'state': 0x1000, 'type': 0x1000000 if image else 0x20000,
                'protect': 0x104 if self.guard == address else 0x20 if image else 4}

    def read(self, address, size):
        self.reads.append((address, size))
        if address == self.state_context + reader.STATE_OFFSET:
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            self.put(address, struct.pack('<I', state))
        if address == self.alpha_address:
            alpha = self.alphas.pop(0) if len(self.alphas) > 1 else self.alphas[0]
            self.put(address, struct.pack('<f', alpha))
        if self.changed is not None:
            self.changed(self, address, size)
        try:
            raw = bytes(self.bytes[address + i] for i in range(size))
        except KeyError as error:
            raise AssertionError(f'fixture does not own {address:#x}+{size}') from error
        return raw[:-1] if self.short == address else raw

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *args):
        return False


def deps(memory, pids=None):
    return {'fingerprints': lambda: {}, 'validate_identity': lambda *_: None,
            'game_processes': pids or (lambda: (123,)),
            'resolve_game': lambda _: dict(memory.identity), 'Process': lambda _: memory}


class Tests(unittest.TestCase):
    def budget(self, memory, **options):
        return reader.Budget(memory, memory.identity, clock=lambda: 0, **options)

    def owner(self, memory):
        owner, reason = reader.locate(self.budget(memory))
        self.assertEqual(reason, 'visible_career')
        return owner

    def test_non_ship_reads_only_twelve_bytes_no_registry_code_or_nodes(self):
        for state in (0, 1, 2, 4, 5, 6):
            with self.subTest(state=state):
                memory = Memory(); memory.states = [state]
                owner, reason = reader.locate(self.budget(memory))
                self.assertIsNone(owner); self.assertEqual(reason, 'waiting_ship')
                self.assertEqual(len(memory.reads), 2)
                self.assertEqual(sum(n for _, n in memory.reads), 12)

    def test_known_inline_list_not_controller_pointer_or_whole_hud(self):
        memory = Memory(); owner = self.owner(memory)
        self.assertEqual(owner['list'], memory.list)
        self.assertEqual(owner['controller'], memory.controller)
        self.assertEqual(len(memory.reads), 7)
        self.assertEqual(sum(n for _, n in memory.reads), 300)
        self.assertNotIn((memory.controller + reader.CAREER_PANEL, 8), memory.reads)

    def test_hidden_page_and_registry_bounds_stop_before_children(self):
        memory = Memory(); memory.alphas = [0]
        owner, reason = reader.locate(self.budget(memory))
        self.assertIsNone(owner); self.assertEqual(reason, 'waiting_career')
        self.assertTrue(all(at != memory.first_node for at, _ in memory.reads))
        memory = Memory(); memory.put(memory.dispatch + reader.COUNT, struct.pack('<I', 65))
        with self.assertRaisesRegex(ValueError, 'REGISTRY_COUNT'):
            reader.locate(self.budget(memory))
        self.assertEqual(len(memory.reads), 4)

    def test_strings_are_read_only_for_type_one_and_count_at616(self):
        memory = Memory()
        memory.text(memory.strings, '351,849')
        memory.label(memory.first_node, 0x2BAA24A7,
                     ((0xAB2A7B35, 1, memory.strings), (0xAB2A7B35, 2, 4633)))
        result = reader.label_descriptor(self.budget(memory), memory.first_node)
        self.assertEqual(result['arguments'][0]['text'], '351,849')
        self.assertEqual(result['arguments'][1]['value_raw'], 4633)
        self.assertNotIn('text', result['arguments'][1])
        self.assertFalse(result['numeric_type_proven'])
        self.assertEqual(memory.reads, [(memory.first_node + 272, 345), (memory.strings, 64)])

    def test_count_above14_invalid_pointer_utf8_and_no_nul_never_zero(self):
        memory = Memory(); memory.label(memory.first_node, 0xF68F08B2, count=15)
        value = reader.label_descriptor(self.budget(memory), memory.first_node)
        self.assertFalse(value['valid']); self.assertEqual(len(memory.reads), 1)
        for raw, pointer, expected in ((b'\xff\0', memory.strings, 'invalid_utf8'),
                                       (b'x' * 64, memory.strings, 'string_limit'),
                                       (b'', 0, 'invalid_pointer')):
            with self.subTest(expected=expected):
                memory = Memory(); memory.label(memory.first_node, 0xF68F08B2, ((1, 1, pointer),))
                if pointer:memory.put(pointer, raw.ljust(64, b'\0'))
                result = reader.label_descriptor(self.budget(memory), memory.first_node)
                self.assertEqual(result['arguments'][0]['text_error'], expected)
                self.assertNotIn('text', result['arguments'][0])

    def test_long_list_resumes_with_same_cursor_not_larger_caps(self):
        memory = Memory(nodes=50); owner = self.owner(memory)
        cursor = reader.Cursor(owner); total = {'bytes': 0, 'reads': 0, 'records': []}
        slices = []
        while True:
            budget = self.budget(memory, total=total)
            before = len(cursor.nodes)
            try:done = cursor.step(budget, owner)
            except reader.SliceFull:done = False
            slices.append((len(cursor.nodes) - before, budget.bytes, budget.reads))
            if done:break
        self.assertEqual(len(cursor.nodes), 50); self.assertGreater(len(slices), 1)
        self.assertTrue(all(n <= 32 and size <= 8192 and calls <= 64 for n, size, calls in slices))
        self.assertEqual(len(cursor.seen), 50)

    def test_related_value_keeps_row_ancestry_normal_kind_not_claimed(self):
        memory = Memory(nodes=2)
        child = memory.first_node + 8192
        memory.widget(memory.first_node, memory.list, child=child, sibling=memory.first_node + 1024)
        memory.widget(child, memory.first_node, kind=3)
        memory.label(memory.first_node, 0xF68F08B2, kind=3)
        memory.label(child, 0xC67C7FAF, ((0xAB2A7B35, 1, memory.strings),), kind=3)
        memory.text(memory.strings, '351849')
        cursor = reader.Cursor(self.owner(memory)); cursor.step(self.budget(memory), cursor.owner)
        self.assertEqual(cursor.labels[0]['row'], cursor.labels[1]['row'])
        self.assertEqual(cursor.labels[1]['arguments'][0]['text'], '351849')
        self.assertFalse(cursor.labels[0]['widget_type_proven'])

    def test_parent_context_cycle_and_owner_changes_fail(self):
        for failure in ('parent', 'context', 'cycle', 'owner'):
            with self.subTest(failure=failure):
                memory = Memory(); owner = self.owner(memory)
                cursor = reader.Cursor(owner)
                if failure == 'parent':memory.widget(memory.first_node, memory.list + 8)
                if failure == 'context':memory.widget(memory.first_node, memory.list, context=memory.gui + 8)
                if failure == 'cycle':memory.widget(memory.first_node, memory.list, sibling=memory.first_node)
                if failure == 'owner':owner = dict(owner, controller=owner['controller'] + 8)
                with self.assertRaisesRegex(ValueError, 'NODE_OWNER|TREE_IDENTITY|OWNER_CHANGED'):
                    cursor.step(self.budget(memory), owner)

    def test_label_rebuild_during_read_rejected(self):
        memory = Memory(); memory.label(memory.first_node, 0xF68F08B2)
        count = 0
        def mutate(memory, address, size):
            nonlocal count
            if address == memory.first_node:
                count += 1
                if count == 2:memory.widget(memory.first_node, memory.list, sibling=memory.first_node + 1024, kind=8)
        memory.changed = mutate
        cursor = reader.Cursor(self.owner(memory))
        with self.assertRaisesRegex(ValueError, 'NODE_CHANGED'):
            cursor.step(self.budget(memory), cursor.owner)

    def test_all_limits_gate_before_query_read(self):
        memory = Memory(); budget = self.budget(memory)
        budget.bytes = reader.SLICE_BYTES
        with self.assertRaises(reader.SliceFull):budget.read(memory.first_node, 1)
        self.assertEqual(memory.reads, []); self.assertEqual(memory.queries, [])
        budget.bytes = 0; budget.reads = reader.SLICE_READS
        with self.assertRaises(reader.SliceFull):budget.read(memory.first_node, 1)
        self.assertEqual(memory.reads, []); self.assertEqual(memory.queries, [])
        budget.reads = 0; budget.total['bytes'] = reader.TOTAL_BYTES
        with self.assertRaisesRegex(ValueError, 'TOTAL_BUDGET'):budget.read(memory.first_node, 1)
        self.assertEqual(memory.reads, []); self.assertEqual(memory.queries, [])
        ticks = iter((0, reader.SLICE_SECONDS))
        budget = reader.Budget(memory, memory.identity, clock=lambda: next(ticks))
        with self.assertRaises(reader.SliceFull):budget.read(memory.first_node, 1)
        self.assertEqual(memory.reads, []); self.assertEqual(memory.queries, [])

    def test_short_guard_and_code_pin_fail_are_not_zero(self):
        for failure in ('short', 'guard', 'pin'):
            with self.subTest(failure=failure):
                memory = Memory()
                if failure == 'short':memory.short = memory.first_node
                if failure == 'guard':memory.guard = memory.first_node
                if failure == 'pin':memory.put(memory.identity['game_base'] + reader.PINS[0][0], b'\0')
                with self.assertRaisesRegex(ValueError, 'SHORT_READ|UNREADABLE|CODE_PIN'):
                    if failure == 'pin':reader.verify_code(self.budget(memory))
                    else:self.budget(memory).read(memory.first_node, 256)

    def test_once_complete_keeps_raw_and_marks_diagnostic_not_career_values(self):
        memory = Memory(nodes=2); memory.label(memory.first_node, 0xF68F08B2)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'new'
            result = reader.run(folder, deps=deps(memory), clock=lambda: 0, sleep=lambda _: None)
            status = json.loads((folder / 'status.json').read_text('utf8'))
            self.assertEqual(status['status'], 'complete')
            self.assertEqual(result['active_read_bytes'], sum(n for _, n in memory.reads))
            self.assertEqual(result['active_read_calls'], len(memory.reads))
            self.assertEqual(result['active_read_calls'], len(result['read_records']))
            for flag in ('career_stats_ready', 'account_modified', 'native_called', 'native_written',
                         'normal_label_kind_verified', 'locator_instruction_pin_verified'):
                self.assertFalse(result[flag])
            self.assertTrue(result['label_layout_pins_verified'])
            self.assertNotIn('kills', result); self.assertNotIn('deaths', result)

    def test_wait_past120_seconds_nonship_no_code_and_success_once(self):
        memory = Memory(); memory.states = [2] * 65 + [3]
        sleeps = []
        with tempfile.TemporaryDirectory() as temporary:
            result = reader.run(Path(temporary) / 'new', wait=True, deps=deps(memory),
                                clock=lambda: 0, sleep=sleeps.append)
        self.assertEqual(sleeps, [2] * 65)
        self.assertEqual(result['waiting'], {'polls': 65, 'bytes': 780, 'reads': 130})
        self.assertTrue(all(at in (memory.identity['game_base'] + reader.STATE_GLOBAL,
                                  memory.state_context + reader.STATE_OFFSET) for at, _ in memory.reads[:130]))
        self.assertEqual(memory.entered, 66)

    def test_closed_page_after_rows_fails_once_no_success_output(self):
        memory = Memory(); memory.alphas = [1, 0]; sleeps = []
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'new'
            with self.assertRaisesRegex(ValueError, 'FINAL_OWNER_CHANGED'):
                reader.run(folder, wait=True, deps=deps(memory), clock=lambda: 0, sleep=sleeps.append)
            self.assertEqual(json.loads((folder / 'status.json').read_text('utf8'))['status'], 'failed')
            self.assertFalse((folder / 'career-list.json').exists())
        self.assertEqual(sleeps, []); self.assertEqual(memory.entered, 1)

    def test_existing_output_rejected_before_dependency_process_or_read(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(reader, 'dependencies', side_effect=AssertionError('dependencies')):
            with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
                reader.run(temporary, wait=True)

    def test_build_failure_saved_before_process_or_reads(self):
        memory = Memory(); fixture = deps(memory)
        fixture['fingerprints'] = lambda: (_ for _ in ()).throw(ValueError('OWNED_BUILD_CHANGED'))
        fixture['game_processes'] = lambda: (_ for _ in ()).throw(AssertionError('processes'))
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'new'
            with self.assertRaisesRegex(ValueError, 'BUILD_CHANGED'):
                reader.run(folder, wait=True, deps=fixture)
            self.assertEqual(json.loads((folder / 'status.json').read_text('utf8'))['status'], 'failed')
        self.assertEqual(memory.reads, [])

    def test_readiness_soft_clock_yields_and_counts_partial_reads(self):
        memory = Memory(); now = [0.0]; first = [True]; sleeps = []
        def delay(memory, address, size):
            if first[0] and address == memory.identity['game_base'] + reader.STATE_GLOBAL:
                first[0] = False; now[0] += reader.GATE_SECONDS + .001
        memory.changed = delay
        def sleep(seconds):
            sleeps.append(seconds); now[0] += seconds
        with tempfile.TemporaryDirectory() as temporary:
            result = reader.run(Path(temporary) / 'new', wait=True, deps=deps(memory),
                                clock=lambda: now[0], sleep=sleep)
        self.assertEqual(sleeps, [2])
        self.assertEqual(result['soft_yields']['readiness'], 1)
        self.assertEqual(result['waiting'], {'polls': 1, 'bytes': 8, 'reads': 1})
        self.assertEqual(result['active_read_calls'] + 1, len(memory.reads))
        self.assertEqual(result['active_read_bytes'] + 8, sum(n for _, n in memory.reads))

    def test_work_clock_yields_without_committing_partial_node_twice(self):
        memory = Memory(); now = [0.0]; first = [True]; sleeps = []
        def delay(memory, address, size):
            if first[0] and address == memory.first_node:
                first[0] = False; now[0] += reader.SLICE_SECONDS + .001
        memory.changed = delay
        def sleep(seconds):
            sleeps.append(seconds); now[0] += seconds
        with tempfile.TemporaryDirectory() as temporary:
            result = reader.run(Path(temporary) / 'new', wait=True, deps=deps(memory),
                                clock=lambda: now[0], sleep=sleep)
        self.assertEqual(sleeps, [.25]); self.assertEqual(len(result['nodes']), 1)
        self.assertEqual(sum(at == memory.first_node for at, _ in memory.reads), 2)
        self.assertEqual(result['active_read_calls'], len(memory.reads))

    def test_final_gate_soft_clock_yields_keeps_cursor_and_counts_partial_reads(self):
        memory = Memory(); now = [0.0]; states = [0]; sleeps = []
        def delay(memory, address, size):
            if address == memory.identity['game_base'] + reader.STATE_GLOBAL:
                states[0] += 1
                if states[0] == 2:now[0] += reader.GATE_SECONDS + .001
        memory.changed = delay
        def sleep(seconds):
            sleeps.append(seconds); now[0] += seconds
        with tempfile.TemporaryDirectory() as temporary:
            result = reader.run(Path(temporary) / 'new', wait=True, deps=deps(memory),
                                clock=lambda: now[0], sleep=sleep)
        self.assertEqual(sleeps, [.25]); self.assertEqual(len(result['nodes']), 1)
        self.assertEqual(result['soft_yields']['final_gate'], 1)
        self.assertEqual(sum(at == memory.first_node for at, _ in memory.reads), 1)
        self.assertEqual(result['active_read_calls'], len(memory.reads))
        self.assertEqual(result['active_read_bytes'], sum(n for _, n in memory.reads))

    def test_gate_clock_is_independent_from_ten_ms_node_work(self):
        memory = Memory(); now = [0.0]
        memory.changed = lambda *_: now.__setitem__(0, now[0] + .011)
        budget = reader.Budget(memory, memory.identity, clock=lambda: now[0], seconds=reader.GATE_SECONDS)
        owner, reason = reader.locate(budget)
        self.assertEqual(reason, 'visible_career'); self.assertEqual(owner['list'], memory.list)
        self.assertEqual(len(memory.reads), 7)
        self.assertGreater(now[0], reader.SLICE_SECONDS)


if __name__ == '__main__':
    unittest.main()
