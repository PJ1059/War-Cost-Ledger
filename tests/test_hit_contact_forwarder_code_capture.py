"""Focused owned fixed-JMP declaration fixtures; never opens Game."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_flow_exe_entry_code_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_contact_forwarder',
    ROOT / 'tools/hit-contact-forwarder-code-capture.py')
forwarder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forwarder)


class Memory(fixture.Memory):
    def __init__(self, state=2, after=None, bad_jmp=False, body_jmp_change=False,
                 large_body=False, header_change=False, guard=False):
        super().__init__(state=state, after=state if after is None else after)
        self.bad_jmp, self.body_jmp_change = bad_jmp, body_jmp_change
        self.header_change, self.guard = header_change, guard
        self.header_reads = 0
        # Deliberately not the saved window start or the JMP point.
        self.begin = forwarder.TARGET_RVA - 0x35
        self.end = self.begin + (4097 if large_body else 0x3A)
        self.nodes = [(self.begin, self.end, 0x2513000)]
        self.header = (ROOT / 'dist/hit-contact-registration-source-20261013/game-pe-header.bin').read_bytes()

    def query(self, address):
        self.queries.append(address)
        if self.clock:
            self.clock.value += self.delay
        if self.context <= address < self.context + 0x100000:
            return {'base': self.context, 'size': 0x100000, 'state': 0x1000,
                    'type': 0x20000, 'protect': 4}
        if self.game <= address < self.game + forwarder.IMAGE_SIZE:
            code = self.begin <= address - self.game < self.end
            return {'base': self.game, 'size': forwarder.IMAGE_SIZE, 'state': 0x1000,
                    'type': 0x1000000, 'protect': (0x120 if self.guard else 0x20) if code else 2}
        raise AssertionError('Outside owned image and declared FSM context')

    def read(self, address, n):
        self.reads.append((address, n))
        if self.clock:
            self.clock.value += self.delay
        if address == self.game + fixture.ship_reader['STATE_GLOBAL']:
            return struct.pack('<Q', self.context)
        if address == self.context + fixture.ship_reader['STATE_OFFSET']:
            value = self.state if self.state_reads == 0 else self.after
            self.state_reads += 1
            return struct.pack('<I', value)
        rva = address - self.game
        if rva == 0:
            assert n == 4096
            self.header_reads += 1
            raw = bytearray(self.header)
            if self.header_change and self.header_reads > 1:
                raw[-1] ^= 1
            return bytes(raw)
        if rva == forwarder.TARGET_RVA and n == 5:
            return bytes(n) if self.bad_jmp else bytes.fromhex(forwarder.TARGET_PIN)
        if forwarder.EXCEPTION_RVA <= rva < forwarder.EXCEPTION_RVA + forwarder.EXCEPTION_SIZE:
            assert n == 12
            index = (rva - forwarder.EXCEPTION_RVA) // 12
            b, e = (index + 1) * 0x100, (index + 2) * 0x100
            if b == forwarder.TARGET_RVA & ~0xFF:
                b, e = self.begin, self.end
            return struct.pack('<III', b, e, 0x2513000)
        if rva == 0x2513000:
            assert n == 4
            return bytes((1, 0, 0, 0))
        if rva == self.begin and n == self.end - self.begin:
            raw = bytearray(b'\x90' * n)
            at = forwarder.TARGET_RVA - self.begin
            raw[at:at + 5] = bytes(5) if self.body_jmp_change else bytes.fromhex(forwarder.TARGET_PIN)
            return bytes(raw)
        raise AssertionError('Outside fixed header/JMP/exception/unwind/body/FSM reads')

    def body_reads(self):
        return [(a - self.game, n) for a, n in self.reads if a == self.game + self.begin]


class Scenario(fixture.Scenario):
    def __init__(self, final_change=None, final_pid_change=False, **options):
        super().__init__(final_change=final_change, final_pid_change=final_pid_change)
        self.memory = Memory(**options)


class ForwarderTests(unittest.TestCase):
    def run_fixture(self, scenario, folder, clock=None):
        return forwarder.run(folder, scenario.dependencies(), clock=clock or fixture.Clock())

    def test_frozen_source_and_actual_declaration_title_and_ship(self):
        source = forwarder.validate_source()
        self.assertEqual(source['relative_target_rva'], 0x13AC1F0)
        self.assertEqual(source['candidate_rva'], 0x13F76D5)
        self.assertEqual(hashlib.sha256(forwarder.CORE.read_bytes()).hexdigest(), forwarder.CORE_SHA)
        for state in (2, 3):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(state=state)
                result = self.run_fixture(scenario, Path(parent) / 'capture')
                m = json.loads(Path(result['json_path']).read_text('utf8'))
                raw = Path(result['binary_path']).read_bytes()
                self.assertEqual(m['function_begin'], scenario.memory.begin)
                self.assertEqual(m['function_end'], scenario.memory.end)
                self.assertNotEqual(m['function_begin'], source['window_rva'])
                self.assertEqual(raw[m['binary_jmp_offset']:m['binary_jmp_offset'] + 5].hex(), forwarder.TARGET_PIN)
                self.assertEqual(m['target_module'], 'game')
                self.assertEqual(m['ship_before'], m['ship_after'])
                self.assertEqual(m['ship_before']['state'], state)
                self.assertEqual(m['ship_before']['name'], 'TitleScreen' if state == 2 else 'Ship')
                self.assertTrue(m['declared_code_complete'])
                self.assertFalse(m['logical_function_complete'])
                self.assertFalse(m['additional_ancestry_code_read'])
                self.assertFalse(m['registered_callback_proven'])
                self.assertFalse(m['native_called'])
                self.assertFalse(m['native_written'])
                self.assertEqual(m['extra_callee_reads'], 0)
                self.assertEqual(scenario.memory.body_reads(), [(scenario.memory.begin, 0x3A)])
                self.assertEqual(m['budget']['read_calls'], len(scenario.memory.reads))
                self.assertEqual(m['budget']['query_calls'], len(scenario.memory.queries))
                self.assertLessEqual(m['budget']['bytes_requested'], 16384)
                self.assertLessEqual(m['budget']['declaration_bytes_requested'], 8192)
                self.assertTrue(scenario.memory.closed)

    def test_changed_source_sha_or_relative_target_refuses_before_open(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as parent:
            with patch.object(forwarder, 'SOURCE_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'INDEX_SOURCE_CHANGED'):
                    self.run_fixture(scenario, Path(parent) / 'sha')
            with patch.object(forwarder, 'JMP_DESTINATION', 0x13AC1F1):
                with self.assertRaisesRegex(ValueError, 'SOURCE_PROFILE'):
                    self.run_fixture(scenario, Path(parent) / 'target')
        self.assertEqual(scenario.opens, 0)

    def test_fresh_jmp_guard_or_oversized_declaration_reads_no_body(self):
        for opts, reason in (({'bad_jmp': True}, 'FRESH_JMP_CHANGED'),
                             ({'guard': True}, 'REGION_UNREADABLE'),
                             ({'large_body': True}, 'FUNCTION_TOO_LARGE')):
            with self.subTest(opts=opts), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**opts), Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assertEqual(scenario.memory.body_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertTrue(scenario.memory.closed)

    def test_mission_refuses_and_phase_header_body_or_module_changes_withhold(self):
        options = (({'state': 4}, 'EXPECTS_STATIC'), ({'after': 3}, 'STATIC_STATE_CHANGED'),
                   ({'body_jmp_change': True}, 'BODY_JMP_CHANGED'),
                   ({'header_change': True}, 'SOURCE_CHANGED_DURING_CAPTURE'),
                   ({'final_change': ('game_base', fixture.Memory.game + 4096)}, 'MODULE_CHANGED'),
                   ({'final_pid_change': True}, 'MODULE_CHANGED'))
        for opts, reason in options:
            with self.subTest(opts=opts), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**opts), Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertFalse(json.loads((folder / 'forwarder.incomplete.json').read_text())['partial_binary_saved'])
                self.assertTrue(scenario.memory.closed)
                if opts.get('state') == 4:
                    self.assertEqual(len(scenario.memory.reads), 2)
                    self.assertEqual(scenario.memory.body_reads(), [])

    def test_hard_total_declaration_and_soft_time_caps_do_not_expand(self):
        for cap, limit in (('MAX_BYTES', 4200), ('MAX_READS', 5),
                           ('MAX_DECLARATION_BYTES', 12), ('MAX_DECLARATION_READS', 1)):
            with self.subTest(cap=cap), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(), Path(parent) / 'capture'
                with patch.object(forwarder, cap, limit):
                    with self.assertRaisesRegex(ValueError, 'BUDGET'):
                        self.run_fixture(scenario, folder)
                self.assertEqual(scenario.memory.body_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertEqual(scenario.opens, 1)
        with tempfile.TemporaryDirectory() as parent:
            scenario, clock = Scenario(), fixture.Clock()
            scenario.memory.clock, scenario.memory.delay = clock, 0.4
            with self.assertRaisesRegex(ValueError, 'TIME_BUDGET'):
                self.run_fixture(scenario, Path(parent) / 'capture', clock)
            self.assertEqual(scenario.memory.body_reads(), [])


if __name__ == '__main__':
    unittest.main()
