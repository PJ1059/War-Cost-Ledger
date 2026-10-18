"""Three tiny owned CALL-window groups; no Game, native call, or old suite."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_hit_contact_forwarder_code_capture as existing

fixture = existing.fixture
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_contact_callsite', ROOT / 'tools/hit-world-update-contact-callsite-capture.py')
callsite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(callsite)
ORIGINAL_LIMITS = (existing.forwarder.MAX_BYTES, existing.forwarder.MAX_READS,
                   existing.forwarder.MAX_SECONDS, existing.forwarder.MAX_CODE_BYTES)


class Memory(fixture.Memory):
    def __init__(self, state=2, after=None, declaration='normal', bad_pin=False,
                 window_pin_change=False, after_context_change=False):
        super().__init__(state=state, after=state if after is None else after)
        self.bad_pin, self.window_pin_change = bad_pin, window_pin_change
        self.after_context_change, self.context_reads = after_context_change, 0
        self.begin, self.end = callsite.TARGET_RVA - 0x200, callsite.TARGET_RVA + 0x100
        if declaration == 'boundary12':
            self.begin, self.end = callsite.PIN_RVA, callsite.TARGET_RVA + 5
        elif declaration == 'large':
            self.end = self.begin + 8192
        elif declaration == 'cuts_prefix':
            self.begin, self.end = callsite.PIN_RVA + 1, callsite.TARGET_RVA + 5
        elif declaration == 'cuts_call':
            self.end = callsite.TARGET_RVA + 4
        elif declaration != 'normal':
            raise AssertionError('Unexpected declaration fixture')
        self.header = (ROOT / 'dist/hit-contact-registration-source-20261013/game-pe-header.bin').read_bytes()
        self.payload_reads = []

    def query(self, address):
        self.queries.append(address)
        if self.clock:
            self.clock.value += self.delay
        if self.context <= address < self.context + 0x100000:
            return {'base': self.context, 'size': 0x100000, 'state': 0x1000,
                    'type': 0x20000, 'protect': 4}
        if self.game <= address < self.game + callsite.frozen.IMAGE_SIZE:
            rva = address - self.game
            # The independently frozen 12-byte PIN is a gate, not a code window.
            code = self.begin <= rva < self.end or rva == callsite.PIN_RVA
            return {'base': self.game, 'size': callsite.frozen.IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 0x20 if code else 2}
        raise AssertionError('Query outside owned image and declared FSM context')

    def read(self, address, size):
        self.reads.append((address, size))
        if self.clock:
            self.clock.value += self.delay
        if address == self.game + fixture.ship_reader['STATE_GLOBAL']:
            self.context_reads += 1
            changed = self.after_context_change and self.context_reads > 1
            return struct.pack('<Q', self.context + (0x1000 if changed else 0))
        if address in (self.context + fixture.ship_reader['STATE_OFFSET'],
                       self.context + 0x1000 + fixture.ship_reader['STATE_OFFSET']):
            value = self.state if self.state_reads == 0 else self.after
            self.state_reads += 1
            return struct.pack('<I', value)
        rva = address - self.game
        if rva == 0:
            assert size == 4096
            return self.header
        if (callsite.frozen.EXCEPTION_RVA <= rva <
                callsite.frozen.EXCEPTION_RVA + callsite.frozen.EXCEPTION_SIZE):
            assert size == 12
            index = (rva - callsite.frozen.EXCEPTION_RVA) // 12
            begin, end = (index + 1) * 0x100, (index + 2) * 0x100
            if begin == callsite.TARGET_RVA & ~0xFF:
                begin, end = self.begin, self.end
            return struct.pack('<III', begin, end, 0x2513000)
        if rva == 0x2513000:
            assert size == 4
            return bytes((1, 0, 0, 0))
        if rva == callsite.PIN_RVA and size == 12:
            return bytes(size) if self.bad_pin else bytes.fromhex(callsite.PIN_HEX)
        prefix = (self.begin, min(self.end, self.begin + 64))
        window = (max(self.begin, callsite.TARGET_RVA - 32),
                  min(self.end, callsite.TARGET_RVA + 5 + 16))
        intervals = sorted((prefix, window))
        if intervals[1][0] <= intervals[0][1]:
            allowed = [(intervals[0][0], max(intervals[0][1], intervals[1][1]))]
        else:
            allowed = intervals
        if (rva, rva + size) not in allowed:
            raise AssertionError('Read outside exact declaration-clipped windows/PIN/metadata/FSM')
        assert self.begin <= rva < rva + size <= self.end
        assert size <= callsite.MAX_CODE_BYTES
        self.payload_reads.append((rva, size))
        raw = bytearray(b'\x90' * size)
        offset = callsite.PIN_RVA - rva
        if 0 <= offset and offset + 12 <= size:
            raw[offset:offset + 12] = (bytes(12) if self.window_pin_change
                                       else bytes.fromhex(callsite.PIN_HEX))
        return bytes(raw)


class Scenario(fixture.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class CallsiteTests(unittest.TestCase):
    def run_fixture(self, scenario, folder, clock=None):
        return callsite.run(folder, scenario.dependencies(), clock=clock or fixture.Clock())

    def assert_failed_without_binary(self, folder):
        self.assertEqual(list(folder.glob('*.bin')), [])
        failure = json.loads((folder / 'callsite.incomplete.json').read_text('utf8'))
        self.assertFalse(failure['complete'])
        self.assertFalse(failure['partial_binary_saved'])
        return failure

    def assert_original_limits_unchanged(self):
        self.assertEqual((existing.forwarder.MAX_BYTES, existing.forwarder.MAX_READS,
                          existing.forwarder.MAX_SECONDS, existing.forwarder.MAX_CODE_BYTES),
                         ORIGINAL_LIMITS)

    def test_normal_exact_boundary_and_large_declaration_read_only_windows(self):
        self.assertEqual(callsite.validate_source()['relative_target_rva'], 0x13AC1F0)
        self.assertEqual(hashlib.sha256(callsite.FROZEN.read_bytes()).hexdigest(), callsite.FROZEN_SHA)
        for state, declaration in ((2, 'normal'), (3, 'normal'),
                                   (2, 'boundary12'), (2, 'large')):
            with self.subTest(state=state, declaration=declaration), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(state=state, declaration=declaration)
                status = self.run_fixture(scenario, Path(parent) / 'capture')
                meta = json.loads(Path(status['json_path']).read_text('utf8'))
                raw = Path(status['binary_path']).read_bytes()
                self.assertEqual((meta['function_begin'], meta['function_end']),
                                 (scenario.memory.begin, scenario.memory.end))
                self.assertEqual(raw[meta['binary_pin_offset']:meta['binary_pin_offset'] + 12].hex(),
                                 callsite.PIN_HEX)
                self.assertEqual(raw[meta['binary_call_offset']:meta['binary_call_offset'] + 5].hex(),
                                 callsite.CALL_HEX)
                self.assertEqual(meta['code_bytes'], len(raw))
                self.assertEqual(meta['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(meta['ship_before'], meta['ship_after'])
                self.assertEqual(meta['ship_before']['state'], state)
                self.assertLessEqual(len(raw), 117)
                self.assertLessEqual(meta['requested_current_declaration_prefix']['length'], 64)
                expected_window = {'rva': max(scenario.memory.begin, callsite.TARGET_RVA - 32),
                    'length': min(scenario.memory.end, callsite.TARGET_RVA + 21)
                              - max(scenario.memory.begin, callsite.TARGET_RVA - 32)}
                self.assertEqual(meta['requested_callsite_window'], expected_window)
                for row in meta['ranges']:
                    self.assertTrue(scenario.memory.begin <= row['rva'] <
                                    row['rva'] + row['length'] <= scenario.memory.end)
                    self.assertEqual(row['module'], 'game')
                if declaration == 'boundary12':
                    self.assertEqual(len(raw), 12)
                    self.assertEqual(len(meta['ranges']), 1)
                    self.assertEqual(meta['ranges'][0]['rva'], callsite.PIN_RVA)
                    self.assertEqual(meta['ranges'][0]['length'], 12)
                else:
                    self.assertEqual(scenario.memory.payload_reads,
                        [(scenario.memory.begin, 64), (callsite.TARGET_RVA - 32, 53)])
                    self.assertEqual(len(raw), 117)
                self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
                self.assertEqual(meta['budget']['query_calls'], len(scenario.memory.queries))
                self.assertEqual(meta['budget']['bytes_requested'], sum(n for _, n in scenario.memory.reads))
                self.assertLessEqual(meta['budget']['read_calls'], 32)
                self.assertLessEqual(meta['budget']['query_calls'], 32)
                self.assertLessEqual(meta['budget']['bytes_requested'], 24576)
                for key in ('declared_code_complete', 'logical_function_complete',
                            'additional_ancestry_code_read', 'instruction_boundary_verified',
                            'caller_entry_proven', 'global_context_argument_proven',
                            'registered_callback_proven', 'native_called', 'native_written'):
                    self.assertFalse(meta[key])
                self.assertEqual(meta['extra_callee_reads'], 0)
                self.assertTrue(scenario.memory.closed)
                self.assert_original_limits_unchanged()

    def test_source_pin_window_declaration_or_state_changes_withhold_binary(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as parent:
            folder = Path(parent) / 'changed_source'
            with patch.object(callsite, 'SOURCE_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'INDEX_SOURCE_CHANGED'):
                    self.run_fixture(scenario, folder)
            self.assertEqual(scenario.opens, 0)
            self.assert_failed_without_binary(folder)
        cases = (({'bad_pin': True}, 'FRESH_PIN_CHANGED', True),
                 ({'window_pin_change': True}, 'WINDOW_PIN_CHANGED', False),
                 ({'declaration': 'cuts_prefix'}, 'PIN_OUTSIDE_CURRENT_DECLARATION', True),
                 ({'declaration': 'cuts_call'}, 'PIN_OUTSIDE_(FUNCTION|CURRENT_DECLARATION)', True),
                 ({'state': 4}, 'EXPECTS_STATIC', True),
                 ({'after': 3}, 'STATIC_STATE_CHANGED', False),
                 ({'after_context_change': True}, 'STATIC_STATE_CHANGED', False))
        for options, reason, no_payload in cases:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**options), Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assert_failed_without_binary(folder)
                if no_payload:
                    self.assertEqual(scenario.memory.payload_reads, [])
                if options.get('state') == 4:
                    self.assertEqual(len(scenario.memory.reads), 2)
                self.assertTrue(scenario.memory.closed)
                self.assert_original_limits_unchanged()

    def test_total_byte_read_and_time_caps_fail_closed_without_window_expansion(self):
        for cap, limit in (('MAX_BYTES', 4200), ('MAX_READS', 5)):
            with self.subTest(cap=cap), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(), Path(parent) / 'capture'
                with patch.object(callsite, cap, limit):
                    with self.assertRaisesRegex(ValueError, 'BUDGET'):
                        self.run_fixture(scenario, folder)
                meta = self.assert_failed_without_binary(folder)
                self.assertEqual(scenario.memory.payload_reads, [])
                self.assertLessEqual(meta['budget']['bytes_requested'], limit if cap == 'MAX_BYTES' else 24576)
                self.assertLessEqual(meta['budget']['read_calls'], limit if cap == 'MAX_READS' else 32)
                self.assertLessEqual(meta['budget']['query_calls'], limit if cap == 'MAX_READS' else 32)
                self.assertEqual(scenario.opens, 1)
                self.assertTrue(scenario.memory.closed)
                self.assert_original_limits_unchanged()
        with tempfile.TemporaryDirectory() as parent:
            scenario, clock = Scenario(), fixture.Clock()
            scenario.memory.clock, scenario.memory.delay = clock, 0.4
            folder = Path(parent) / 'capture'
            with self.assertRaisesRegex(ValueError, 'TIME_BUDGET'):
                self.run_fixture(scenario, folder, clock)
            self.assert_failed_without_binary(folder)
            self.assertEqual(scenario.memory.payload_reads, [])
            self.assertTrue(scenario.memory.closed)
            self.assert_original_limits_unchanged()


if __name__ == '__main__':
    unittest.main()
