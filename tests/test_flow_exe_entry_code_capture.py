"""Owned two-image/PE/Ship fixtures; never opens or reads a Game process."""
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import recon_chat_code_capture as original_recon
import fire_code_capture as original_fire

RECON_BEFORE = (original_recon.REVISION, original_recon.TARGET_RVA,
                original_recon.TARGET_PIN, original_recon.IMAGE_SIZE,
                original_recon.EXCEPTION_RVA, original_recon.EXCEPTION_SIZE)
FIRE_BEFORE = (original_fire.REVISION, original_fire.RANGES,
               original_fire.PINS, original_fire.TOTAL_BYTES)
spec = importlib.util.spec_from_file_location(
    'owned_flow_exe_capture', ROOT / 'tools/flow-exe-entry-code-capture.py')
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)
ship_reader = runpy.run_path(str(ROOT / 'tools/career-cache-capture.py'))


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class Memory:
    exe = 0x140000000
    game = 0x180000000
    context = 0x1011ED90A0
    identity = {'exe_base': exe, 'exe_size': flow.EXE_IMAGE_SIZE,
                'exe_path': 'fixture/helldivers2.exe',
                'game_base': game, 'game_size': flow.GAME_IMAGE_SIZE,
                'game_path': 'fixture/game.dll'}

    def __init__(self, state=3, after=3, bad_pin=False, short_table=False,
                 large_body=False, guard=False, pe_change=False, chain=False,
                 pin_changes_after_read=False, bad_unwind=False):
        self.state, self.after, self.state_reads = state, after, 0
        self.bad_pin, self.short_table, self.guard = bad_pin, short_table, guard
        self.pe_change, self.pin_changes_after_read = pe_change, pin_changes_after_read
        self.bad_unwind = bad_unwind
        self.begin = flow.TARGET_RVA & ~0xFF
        self.end = self.begin + (4097 if large_body else 0x100)
        self.nodes = [(self.begin, self.end, 0x27D0100)]
        self.metadata = {0x27D0100: bytes((1, 0, 0, 0))}
        if chain:
            self.nodes.append((self.begin - 0x200, self.begin - 0x180, 0x27D0200))
            self.metadata = {0x27D0100: bytes((0x21, 15, 6, 0)),
                             0x27D0110: struct.pack('<III', *self.nodes[1]),
                             0x27D0200: bytes((1, 15, 6, 0))}
        self.reads, self.queries, self.closed = [], [], False
        self.clock, self.delay = None, 0.0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def is_code(self, rva):
        return any(b <= rva < e for b, e, _ in self.nodes)

    def query(self, address):
        self.queries.append(address)
        if self.clock:
            self.clock.value += self.delay
        if self.context <= address < self.context + 0x100000:
            return {'base': self.context, 'size': 0x100000, 'state': 0x1000,
                    'type': 0x20000, 'protect': 4}
        if self.game <= address < self.game + flow.GAME_IMAGE_SIZE:
            return {'base': self.game, 'size': flow.GAME_IMAGE_SIZE, 'state': 0x1000,
                    'type': 0x1000000, 'protect': 2}
        if self.exe <= address < self.exe + flow.EXE_IMAGE_SIZE:
            code = self.is_code(address - self.exe)
            return {'base': self.exe, 'size': flow.EXE_IMAGE_SIZE, 'state': 0x1000,
                    'type': 0x1000000,
                    'protect': (0x120 if self.guard else 0x20) if code else 2}
        raise AssertionError('Query outside owned two images and declared Ship context')

    def read(self, address, length):
        self.reads.append((address, length))
        if self.clock:
            self.clock.value += self.delay
        if address == self.game + ship_reader['STATE_GLOBAL']:
            return struct.pack('<Q', self.context)
        if address == self.context + ship_reader['STATE_OFFSET']:
            value = self.state if self.state_reads == 0 else self.after
            self.state_reads += 1
            return struct.pack('<I', value)
        rva = address - self.exe
        if rva == 0:
            assert length == 64
            raw = bytearray(64)
            raw[:2] = b'MZ'
            struct.pack_into('<I', raw, 60, flow.PE_OFFSET)
            return bytes(raw)
        if rva == flow.PE_OFFSET:
            assert length == 24
            raw = bytearray(24)
            raw[:4] = b'PE\0\0'
            struct.pack_into('<H', raw, 4, 0x8664)
            struct.pack_into('<H', raw, 20, flow.OPTIONAL_SIZE)
            return bytes(raw)
        if rva == flow.PE_OFFSET + 24:
            assert length == flow.OPTIONAL_SIZE
            raw = bytearray(length)
            struct.pack_into('<H', raw, 0, 0x20B)
            struct.pack_into('<I', raw, 56, flow.EXE_IMAGE_SIZE)
            struct.pack_into('<I', raw, 108, 16)
            struct.pack_into('<II', raw, 136,
                             flow.EXCEPTION_RVA + (12 if self.pe_change else 0), flow.EXCEPTION_SIZE)
            return bytes(raw)
        if flow.EXCEPTION_RVA <= rva < flow.EXCEPTION_RVA + flow.EXCEPTION_SIZE:
            assert length == 12
            index = (rva - flow.EXCEPTION_RVA) // 12
            begin, end = (index + 1) * 0x100, (index + 2) * 0x100
            if begin == self.begin:
                begin, end = self.begin, self.end
            raw = struct.pack('<III', begin, end, 0x27D0100)
            return raw[:-1] if self.short_table else raw
        if rva in self.metadata:
            raw = self.metadata[rva]
            assert len(raw) == length
            return bytes(length) if self.bad_unwind else raw
        if any(b <= rva < rva + length <= e for b, e, _ in self.nodes):
            raw = bytearray(length)
            pin = bytes.fromhex(flow.TARGET_PIN)
            offset = flow.TARGET_RVA - rva
            if 0 <= offset and offset + len(pin) <= length:
                corrupt = self.bad_pin or (self.pin_changes_after_read and length > 16)
                raw[offset:offset + len(pin)] = bytes(len(pin)) if corrupt else pin
            return bytes(raw)
        raise AssertionError('Read outside declared headers/exception/unwind/PIN/code/Ship')

    def body_reads(self):
        return [(address - self.exe, n) for address, n in self.reads
                if self.is_code(address - self.exe) and n > 16]


class Scenario:
    def __init__(self, final_change=None, final_pid_change=False, **options):
        self.memory = Memory(**options)
        self.opens = self.resolutions = self.enumerations = self.fingerprints = 0
        self.validations = []
        self.final_change, self.final_pid_change = final_change, final_pid_change

    def dependencies(self):
        def fingerprint():
            self.fingerprints += 1
            return {'exe_sha': ('fixture/exe', 1, 2), 'dll_sha': ('fixture/dll', 3, 4)}

        def processes():
            self.enumerations += 1
            return (54321,) if not self.final_pid_change or self.enumerations == 1 else ()

        def resolve(pid):
            assert pid == 54321
            self.resolutions += 1
            identity = dict(self.memory.identity)
            if self.final_change and self.resolutions > 1:
                key, value = self.final_change
                identity[key] = value
            return identity

        def open_process(pid):
            assert pid == 54321
            self.opens += 1
            return self.memory

        def validate(identity, stamps):
            assert set(stamps) == {'exe_sha', 'dll_sha'}
            self.validations.append(dict(identity))

        return {'fingerprints': fingerprint, 'validate_identity': validate,
                'game_processes': processes, 'resolve_game': resolve,
                'Process': open_process, 'ship_state': ship_reader['ship_state']}


class FlowExeCaptureTests(unittest.TestCase):
    def assert_profiles_unchanged(self):
        self.assertEqual((original_recon.REVISION, original_recon.TARGET_RVA,
                          original_recon.TARGET_PIN, original_recon.IMAGE_SIZE,
                          original_recon.EXCEPTION_RVA, original_recon.EXCEPTION_SIZE), RECON_BEFORE)
        self.assertEqual((original_fire.REVISION, original_fire.RANGES,
                          original_fire.PINS, original_fire.TOTAL_BYTES), FIRE_BEFORE)

    def run_fixture(self, scenario, folder, clock=None):
        return flow.run(folder, scenario.dependencies(), clock=clock or Clock())

    def test_module_snapshot_retains_distinct_exe_and_game(self):
        rows = [{'name': 'GAME.DLL', 'base': Memory.game, 'size': flow.GAME_IMAGE_SIZE,
                 'path': 'fixture/game.dll'},
                {'name': 'helldivers2.exe', 'base': Memory.exe, 'size': flow.EXE_IMAGE_SIZE,
                 'path': 'fixture/helldivers2.exe'},
                {'name': 'lua51.dll', 'base': 0x700000000, 'size': 4096, 'path': 'fixture/lua51.dll'}]
        calls = []
        identity = flow.resolve_sources(54321, lambda pid: calls.append(pid) or rows)
        self.assertEqual(calls, [54321])
        self.assertEqual(identity, Memory.identity)
        with self.assertRaisesRegex(FileNotFoundError, 'EXACT_MODULE'):
            flow.resolve_sources(54321, lambda _: rows + [rows[1]])
        with self.assertRaisesRegex(FileNotFoundError, 'EXACT_MODULE'):
            flow.resolve_sources(54321, lambda _: rows[1:])

    def test_explicit_exe_body_and_single_total_budget(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            self.assertEqual(status['status'], 'complete')
            self.assertEqual(meta['target_module'], 'exe')
            self.assertEqual(meta['pin_source']['sha256'], flow.INVENTORY_SHA)
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertEqual(meta['pe_declaration']['header_bytes_read'], 328)
            self.assertEqual(meta['fresh_pin']['hex'], flow.TARGET_PIN)
            self.assertEqual(raw[meta['binary_pin_offset']:meta['binary_pin_offset'] + 16],
                             bytes.fromhex(flow.TARGET_PIN))
            self.assertEqual(meta['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(meta['ranges'], [{'name': flow.TARGET_NAME, 'module': 'exe',
                                              'rva': scenario.memory.begin, 'length': 256,
                                              'binary_offset': 0}])
            self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
            self.assertEqual(meta['budget']['query_calls'], len(scenario.memory.queries))
            self.assertEqual(meta['budget']['bytes_requested'], sum(n for _, n in scenario.memory.reads))
            self.assertLessEqual(meta['budget']['read_calls'], 32)
            self.assertLessEqual(meta['budget']['bytes_requested'], 8192)
            self.assertEqual(scenario.memory.body_reads(), [(scenario.memory.begin, 256)])
            exe_reads = [row for row in meta['read_records'] if row['purpose'] != 'ship']
            self.assertTrue(all(row['module'] == 'exe' for row in exe_reads))
            self.assertEqual(scenario.opens, 1)
            self.assertEqual(scenario.resolutions, 2)
            self.assertEqual(len(scenario.validations), 2)
            self.assertTrue(scenario.memory.closed)
            self.assertTrue(meta['declared_code_complete'])
            self.assertFalse(meta['logical_function_complete'])
            self.assertFalse(meta['native_written'])
            self.assertFalse(meta['native_called'])
            self.assertFalse(meta['classification_ready'])
            self.assert_profiles_unchanged()

    def test_missing_or_wrong_exe_identity_refuses_before_open(self):
        for key, value in (('exe_base', None), ('exe_size', flow.GAME_IMAGE_SIZE),
                           ('game_size', flow.EXE_IMAGE_SIZE)):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario()
                scenario.memory.identity = {**Memory.identity, key: value}
                with self.assertRaisesRegex(ValueError, 'MODULE_INVALID'):
                    self.run_fixture(scenario, Path(parent) / 'capture')
                self.assertEqual(scenario.opens, 0)

    def test_non_ship_reads_only_ship_and_never_exe(self):
        for state in (2, 4, 5):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(state=state)
                with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP'):
                    self.run_fixture(scenario, Path(parent) / 'capture')
                self.assertEqual(len(scenario.memory.reads), 2)
                self.assertEqual(sum(n for _, n in scenario.memory.reads), 12)
                self.assertEqual(scenario.memory.body_reads(), [])

    def test_pe_change_or_exe_pin_mismatch_stops_before_table_or_code(self):
        for options, error in (({'pe_change': True}, 'OPTIONAL_PROFILE'),
                               ({'bad_pin': True}, 'ENTRY_PIN_MISMATCH'),
                               ({'guard': True}, 'TARGET_REGION_UNREADABLE')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(**options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, error):
                    self.run_fixture(scenario, folder)
                self.assertFalse(any(flow.EXCEPTION_RVA <= a - Memory.exe <
                                     flow.EXCEPTION_RVA + flow.EXCEPTION_SIZE
                                     for a, _ in scenario.memory.reads))
                self.assertEqual(scenario.memory.body_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])

    def test_partial_metadata_oversize_or_unknown_unwind_never_reads_body(self):
        for options, error in (({'short_table': True}, 'SHORT_READ'),
                               ({'large_body': True}, 'FUNCTION_TOO_LARGE'),
                               ({'bad_unwind': True}, 'UNWIND_FORMAT_UNKNOWN')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(**options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, error):
                    self.run_fixture(scenario, folder)
                self.assertEqual(scenario.memory.body_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])
                failure = json.loads((folder / 'setter.incomplete.json').read_text('utf8'))
                self.assertFalse(failure['partial_binary_saved'])
                self.assertTrue(scenario.memory.closed)

    def test_ship_module_or_current_pid_change_discards_code(self):
        options = ({'after': 4}, {'final_change': ('exe_base', Memory.exe + 0x1000)},
                   {'final_change': ('game_base', Memory.game + 0x1000)},
                   {'final_change': ('exe_path', 'other.exe')},
                   {'final_change': ('game_path', 'other.dll')}, {'final_pid_change': True})
        for option in options:
            with self.subTest(option=option), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(**option)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, 'SHIP_CHANGED|MODULE_CHANGED'):
                    self.run_fixture(scenario, folder)
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertEqual(len(scenario.memory.body_reads()), 1)
                self.assertTrue(scenario.memory.closed)

    def test_body_pin_change_rejects_without_saved_partial(self):
        scenario = Scenario(pin_changes_after_read=True)
        with tempfile.TemporaryDirectory() as parent:
            folder = Path(parent) / 'capture'
            with self.assertRaisesRegex(ValueError, 'BODY_PIN_CHANGED'):
                self.run_fixture(scenario, folder)
            self.assertEqual(list(folder.glob('*.bin')), [])

    def test_bounded_ancestry_keeps_binary_offsets_and_no_gaps(self):
        scenario = Scenario(chain=True)
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertEqual(scenario.memory.body_reads(),
                             [(scenario.memory.begin - 0x200, 128), (scenario.memory.begin, 256)])
            self.assertEqual([row['binary_offset'] for row in meta['ranges']], [0, 128])
            self.assertEqual(meta['binary_pin_offset'], 128 + 0x60)
            self.assertEqual(meta['code_bytes'], 384)
            self.assert_profiles_unchanged()

    def test_maximum_declared_body_keeps_total_caps(self):
        scenario = Scenario()
        scenario.memory.end = scenario.memory.begin + 4096
        scenario.memory.nodes = [(scenario.memory.begin, scenario.memory.end, 0x27D0100)]
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertEqual(meta['code_bytes'], 4096)
            self.assertEqual(scenario.memory.body_reads(), [(scenario.memory.begin, 4096)])
            self.assertLessEqual(meta['budget']['read_calls'], 32)
            self.assertLessEqual(meta['budget']['bytes_requested'], 8192)

    def test_low_read_byte_and_soft_time_caps_fail_closed(self):
        for budget_name, limit in (('MAX_READS', 6), ('MAX_BYTES', 355)):
            with self.subTest(budget=budget_name), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario()
                folder = Path(parent) / 'capture'
                with patch.object(flow, budget_name, limit):
                    with self.assertRaisesRegex(ValueError, 'BUDGET'):
                        self.run_fixture(scenario, folder)
                meta = json.loads((folder / 'setter.incomplete.json').read_text('utf8'))
                self.assertLessEqual(meta['budget']['read_calls'], limit if budget_name == 'MAX_READS' else 32)
                self.assertLessEqual(meta['budget']['bytes_requested'], limit if budget_name == 'MAX_BYTES' else 8192)
                self.assertEqual(scenario.memory.body_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])
        scenario, clock = Scenario(), Clock()
        scenario.memory.clock, scenario.memory.delay = clock, 0.4
        with tempfile.TemporaryDirectory() as parent:
            folder = Path(parent) / 'capture'
            with self.assertRaisesRegex(ValueError, 'TIME_BUDGET'):
                self.run_fixture(scenario, folder, clock)
            self.assertEqual(scenario.memory.body_reads(), [])
            self.assertEqual(list(folder.glob('*.bin')), [])

    def test_module_range_gate_and_cross_region_refuse_before_read(self):
        memory = Memory()
        budget = flow.Budget(memory, memory.identity, Clock())
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_TARGET_MODULE'):
            budget.read_module(flow.EXE_IMAGE_SIZE - 8, 16, 'entry_pin', True)
        self.assertEqual(memory.queries, [])
        self.assertEqual(memory.reads, [])
        with patch.object(memory, 'query', return_value={'base': Memory.exe, 'size': 8,
                         'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}):
            with self.assertRaisesRegex(ValueError, 'TARGET_REGION_UNREADABLE'):
                budget.read_module(0, 16, 'entry_pin', True)
        self.assertEqual(memory.reads, [])

    def test_existing_output_refuses_before_dependency_or_inventory_io(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel = Path(folder) / 'keep.txt'
            sentinel.write_text('untouched', 'utf8')
            with patch.object(flow, 'load_dependencies', side_effect=AssertionError('must not load')):
                with patch.object(flow, 'validate_inventory', side_effect=AssertionError('must not read')):
                    with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
                        flow.run(folder)
            self.assertEqual(list(Path(folder).iterdir()), [sentinel])


if __name__ == '__main__':
    unittest.main()
