"""Owned PE/Ship fixtures only; no live process or native call is used."""
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

ORIGINAL_RECON = (original_recon.REVISION, original_recon.TARGET_RVA,
                  original_recon.TARGET_PIN, original_recon.SOURCE_REFERENCE)
ORIGINAL_FIRE = (original_fire.REVISION, original_fire.RANGES,
                 original_fire.PINS, original_fire.TOTAL_BYTES)
spec = importlib.util.spec_from_file_location(
    'review_queue_drain', ROOT / 'tools/hit-queue-consumer-code-capture.py')
drain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drain)
ship_reader = runpy.run_path(str(ROOT / 'tools/career-cache-capture.py'))


class Memory:
    base = 0x180000000
    context = 0x1011ED90A0
    identity = {'game_base': base, 'game_size': drain.reader.IMAGE_SIZE,
                'game_path': 'fixture/game.dll', 'exe_path': 'fixture/helldivers2.exe'}

    def __init__(self, state=3, after=3, *, short_table=False,
                 guard_body=False, bad_pin=False, chain=False):
        self.state, self.after, self.state_reads = state, after, 0
        self.short_table, self.guard_body, self.bad_pin = short_table, guard_body, bad_pin
        self.begin = drain.TARGET_RVA & ~0xff
        self.end = self.begin + 0x100
        self.reads, self.closed = [], False
        self.nodes = [(self.begin, self.end, 0x3000000)]
        self.metadata = {0x3000000: bytes((1, 0, 0, 0))}
        if chain:
            self.nodes.append((self.begin - 0x200, self.begin - 0x180, 0x3000100))
            self.metadata = {0x3000000: bytes((0x21, 15, 6, 0)),
                             0x3000010: struct.pack('<III', *self.nodes[1]),
                             0x3000100: bytes((1, 15, 6, 0))}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def is_body(self, rva):
        return any(begin <= rva < end for begin, end, _ in self.nodes)

    def query(self, address):
        if self.context <= address < self.context + 0x100000:
            return {'base': self.context, 'size': 0x100000, 'state': 0x1000,
                    'type': 0x20000, 'protect': 4}
        return {'base': self.base, 'size': drain.reader.IMAGE_SIZE,
                'state': 0x1000, 'type': 0x1000000,
                'protect': 0x120 if self.guard_body and self.is_body(address - self.base) else 0x20}

    def read(self, address, length):
        self.reads.append((address, length))
        rva = address - self.base
        if rva == ship_reader['STATE_GLOBAL']:
            return struct.pack('<Q', self.context)
        if address == self.context + ship_reader['STATE_OFFSET']:
            value = self.state if self.state_reads == 0 else self.after
            self.state_reads += 1
            return struct.pack('<I', value)
        if rva in self.metadata:
            raw = self.metadata[rva]
            if length != len(raw):
                raise AssertionError('Unexpected metadata read size')
            return raw
        reader = drain.reader
        if reader.EXCEPTION_RVA <= rva < reader.EXCEPTION_RVA + reader.EXCEPTION_SIZE:
            if length != 12:
                raise AssertionError('Exception search must read one record')
            index = (rva - reader.EXCEPTION_RVA) // 12
            begin, end = (index + 1) * 0x100, (index + 2) * 0x100
            if begin == self.begin:
                begin, end = self.begin, self.end
            raw = struct.pack('<III', begin, end, 0x3000000)
            return raw[:-1] if self.short_table else raw
        if self.is_body(rva) and any(b <= rva and rva + length <= e for b, e, _ in self.nodes):
            raw = bytearray(length)
            pin = bytes.fromhex(drain.TARGET_PIN)
            offset = drain.TARGET_RVA - rva
            if 0 <= offset and offset + len(pin) <= length:
                raw[offset:offset + len(pin)] = bytes(len(pin)) if self.bad_pin else pin
            return bytes(raw)
        raise AssertionError('Read outside Ship, exception table, ancestry metadata or declared code')

    def body_reads(self):
        return [(address - self.base, length) for address, length in self.reads
                if self.is_body(address - self.base)]


class Scenario:
    def __init__(self, **options):
        self.memory = Memory(**options)
        self.enumerations = self.resolutions = self.fingerprint_calls = self.opens = 0

    def processes(self):
        self.enumerations += 1
        return (61204,)

    def resolve(self, pid):
        if pid != 61204:
            raise AssertionError('Unexpected fixture PID')
        self.resolutions += 1
        return dict(self.memory.identity)

    def fingerprint(self):
        self.fingerprint_calls += 1
        return {'exe_sha': ('fixture/exe', 1, 2), 'dll_sha': ('fixture/dll', 3, 4)}

    def open(self, pid):
        if pid != 61204:
            raise AssertionError('Unexpected fixture PID')
        self.opens += 1
        return self.memory

    def dependencies(self):
        return {'fingerprints': self.fingerprint,
                'validate_identity': lambda identity, stamps: None,
                'game_processes': self.processes, 'resolve_game': self.resolve,
                'Process': self.open, 'ship_state': ship_reader['ship_state']}


class QueueDrainTests(unittest.TestCase):
    def assert_profiles_unchanged(self):
        self.assertEqual((original_recon.REVISION, original_recon.TARGET_RVA,
                          original_recon.TARGET_PIN, original_recon.SOURCE_REFERENCE), ORIGINAL_RECON)
        self.assertEqual((original_fire.REVISION, original_fire.RANGES,
                          original_fire.PINS, original_fire.TOTAL_BYTES), ORIGINAL_FIRE)
        self.assertIsNot(drain.reader, original_recon)
        self.assertIs(drain.reader.capture.__globals__, drain.reader.__dict__)

    def test_private_profile_and_real_capture_are_isolated(self):
        self.assertEqual(drain.reader.TARGET_RVA, 0x12A6F17)
        self.assertEqual(drain.reader.TARGET_PIN, '8b8120112000')
        memory = Memory()
        raw, meta = drain.reader.capture(memory, memory.identity)
        self.assertEqual(len(raw), 0x100)
        self.assertEqual(raw[0x17:0x1d], bytes.fromhex('8b8120112000'))
        self.assertEqual(meta['source_revision'], drain.REVISION)
        self.assertEqual(meta['target_rva'], drain.TARGET_RVA)
        self.assertEqual(meta['pins'], [{'rva': drain.TARGET_RVA,
                                         'range': 'chat_history_consumer', 'matched': True}])
        self.assertLessEqual(meta['budget']['read_calls'], 32)
        self.assertLessEqual(meta['budget']['bytes_requested'], 8192)
        drain.reader.verify_saved(meta, raw)
        self.assert_profiles_unchanged()

    def test_ship_wrapper_success_and_budget_includes_extra_gate_reads(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = drain.run(Path(parent) / 'new', scenario.dependencies())
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            raw = Path(status['binary_path']).read_bytes()
            self.assertEqual(status['status'], 'complete')
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertEqual(meta['ship_before']['state'], 3)
            self.assertEqual(meta['ship_reads'], 4)
            self.assertEqual(meta['ship_bytes_read'], 24)
            self.assertEqual(len(scenario.memory.reads), meta['budget']['read_calls'] + 4)
            self.assertEqual(sum(n for _, n in scenario.memory.reads),
                             meta['budget']['bytes_requested'] + 24)
            self.assertEqual(scenario.opens, 1)
            self.assertTrue(scenario.memory.closed)
            self.assertEqual(scenario.memory.body_reads(), [(scenario.memory.begin, 256)])
            self.assertFalse(meta['native_written'])
            self.assertFalse(meta['native_called'])
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['logical_function_complete'])
            drain.reader.verify_saved(meta, raw)
            self.assert_profiles_unchanged()

    def test_non_ship_never_calls_capture_and_reads_no_code(self):
        for state in (2, 4, 5):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(state=state)
                with patch.object(drain.reader, 'capture', side_effect=AssertionError('no capture allowed')):
                    with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP'):
                        drain.run(Path(parent) / 'new', scenario.dependencies())
                self.assertEqual(scenario.memory.body_reads(), [])
                self.assertEqual(len(scenario.memory.reads), 2)
                self.assertEqual(sum(n for _, n in scenario.memory.reads), 12)
                self.assertTrue(scenario.memory.closed)

    def test_ship_change_rejects_without_bin(self):
        scenario = Scenario(after=4)
        with tempfile.TemporaryDirectory() as parent:
            folder = Path(parent) / 'new'
            with self.assertRaisesRegex(ValueError, 'SHIP_CHANGED'):
                drain.run(folder, scenario.dependencies())
            self.assertEqual(len(scenario.memory.body_reads()), 1)
            self.assertEqual(list(folder.glob('*.bin')), [])
            self.assertTrue(scenario.memory.closed)
            self.assertEqual(json.loads((folder / 'status.json').read_text('utf8'))['status'], 'failed')

    def test_existing_folder_refuses_before_zero_dependencies(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel = Path(folder) / 'keep.txt'
            sentinel.write_text('untouched', 'utf8')
            with patch.dict(drain.tail, {'load_dependencies': lambda: self.fail('No dependency load')}):
                with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
                    drain.run(folder)
            self.assertEqual(sentinel.read_text('utf8'), 'untouched')
            self.assertEqual(list(Path(folder).iterdir()), [sentinel])

    def test_short_table_or_guarded_code_fail_without_saved_partial(self):
        for options, error in (({'short_table': True}, 'SHORT_READ'),
                               ({'guard_body': True}, 'REGION_UNREADABLE')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(**options)
                folder = Path(parent) / 'new'
                with self.assertRaisesRegex(ValueError, error):
                    drain.run(folder, scenario.dependencies())
                self.assertEqual(scenario.memory.body_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])
                meta = json.loads((folder / 'drain.incomplete.json').read_text('utf8'))
                self.assertFalse(meta['partial_binary_saved'])
                self.assertEqual(scenario.opens, 1)

    def test_pin_mismatch_saves_failure_not_code(self):
        scenario = Scenario(bad_pin=True)
        with tempfile.TemporaryDirectory() as parent:
            folder = Path(parent) / 'new'
            with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
                drain.run(folder, scenario.dependencies())
            self.assertEqual(list(folder.glob('*.bin')), [])
            self.assertEqual(scenario.opens, 1)
            self.assert_profiles_unchanged()

    def test_bounded_chain_only_reads_declared_target_and_parent(self):
        memory = Memory(chain=True)
        raw, meta = drain.reader.capture(memory, memory.identity)
        self.assertEqual(len(raw), 384)
        self.assertEqual(memory.body_reads(), [(memory.begin - 0x200, 128), (memory.begin, 256)])
        self.assertEqual(len(meta['unwind_chain']), 2)
        self.assertFalse(meta['all_sibling_fragments_captured'])
        self.assertFalse(meta['logical_function_complete'])
        drain.reader.verify_saved(meta, raw)
        self.assert_profiles_unchanged()


if __name__ == '__main__':
    unittest.main()
