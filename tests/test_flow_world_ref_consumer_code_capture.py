"""Focused owned unknown-entry/relative-call fixtures; no Game access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_flow_exe_entry_code_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_world_ref_consumer', ROOT / 'tools/flow-world-ref-consumer-code-capture.py')
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)
UNKNOWN_ENTRY = bytes.fromhex('ffeeddccbbaa99887766554433221100')


class Memory(fixture.Memory):
    def __init__(self, bad_caller=False, body_changes=False, **options):
        super().__init__(**options)
        self.bad_caller, self.body_changes = bad_caller, body_changes

    def query(self, address):
        if address == self.exe + consumer.SOURCE_SEQUENCE_RVA:
            self.queries.append(address)
            return {'base': self.exe, 'size': consumer.profile.EXE_IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
        return super().query(address)

    def read(self, address, n):
        if address == self.exe + consumer.SOURCE_SEQUENCE_RVA:
            assert n == 18
            self.reads.append((address, n))
            return bytes(n) if self.bad_caller else bytes.fromhex(consumer.SOURCE_SEQUENCE_HEX)
        if address == self.exe + consumer.TARGET_RVA and n == 16:
            self.reads.append((address, n))
            return UNKNOWN_ENTRY
        raw = super().read(address, n)
        rva = address - self.exe
        offset = consumer.TARGET_RVA - rva
        if self.is_code(rva) and n > 16 and 0 <= offset < offset + 16 <= n:
            output = bytearray(raw)
            prefix = bytearray(UNKNOWN_ENTRY)
            if self.body_changes:
                prefix[-1] ^= 1
            output[offset:offset + 16] = prefix
            return bytes(output)
        return raw


class Scenario(fixture.Scenario):
    def __init__(self, **options):
        final_change = options.pop('final_change', None)
        super().__init__(final_change=final_change)
        self.memory = Memory(**options)


class ConsumerCaptureTests(unittest.TestCase):
    def scenario(self, **options):
        with patch.object(fixture, 'flow', consumer.profile):
            return Scenario(**options)

    def run_fixture(self, scenario, folder):
        with patch.object(fixture, 'flow', consumer.profile):
            return consumer.run(folder, scenario.dependencies(), clock=fixture.Clock())

    def test_frozen_windows_rel32_fresh18_and_unknown_entry_body_consistency(self):
        source = consumer.validate_source()
        self.assertEqual(source['relative_target_rva'], 0x2D4640)
        self.assertEqual(len(source['windows']), 2)
        self.assertEqual(source['call_hex'], 'e876a8f2ff')
        scenario = self.scenario()
        with tempfile.TemporaryDirectory() as parent:
            result = self.run_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(result['json_path']).read_text('utf8'))
            raw = Path(result['binary_path']).read_bytes()
            self.assertEqual(meta['fresh_source_sequence']['hex'], consumer.SOURCE_SEQUENCE_HEX)
            self.assertEqual(meta['fresh_entry_prefix']['hex'], UNKNOWN_ENTRY.hex())
            self.assertEqual(raw[meta['binary_entry_offset']:meta['binary_entry_offset'] + 16], UNKNOWN_ENTRY)
            self.assertTrue(meta['entry_body_consistent'])
            self.assertEqual(meta['target_module'], 'exe')
            self.assertEqual(meta['target_rva'], 0x2D4640)
            self.assertFalse(meta['api_identity_verified'])
            self.assertFalse(meta['callback_consumer_proven'])
            self.assertFalse(meta['native_called'])
            self.assertEqual(meta['registry_reads'], 0)
            self.assertFalse(meta['index_rescanned'])
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertLessEqual(meta['budget']['read_calls'], 40)
            self.assertLessEqual(meta['budget']['query_calls'], 40)
            self.assertLessEqual(meta['budget']['bytes_requested'], 8192)
            self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
            self.assertEqual(hashlib.sha256(consumer.CORE.read_bytes()).hexdigest(), consumer.CORE_SHA)

    def test_source_sha_profile_or_relative_target_change_refuses_before_open(self):
        with tempfile.TemporaryDirectory() as parent:
            scenario = self.scenario()
            with patch.object(consumer, 'SOURCE_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'INDEX_SOURCE_CHANGED'):
                    self.run_fixture(scenario, Path(parent) / 'badsha')
            self.assertEqual(scenario.opens, 0)
            with patch.object(consumer, 'TARGET_RVA', 0x2D4641):
                with self.assertRaisesRegex(ValueError, 'SOURCE_OPCODE_RELATIVE_CALL'):
                    self.run_fixture(scenario, Path(parent) / 'badrelative')
            self.assertEqual(scenario.opens, 0)
            raw = consumer.SOURCE.read_bytes()
            changed = json.loads(raw)
            changed['fingerprint']['exe_sha'] = '0' * 64
            fake = Path(parent) / 'changed-index.json'
            fake.write_text(json.dumps(changed), 'utf8')
            with patch.object(consumer, 'SOURCE_SHA', hashlib.sha256(fake.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'INDEX_SOURCE_PROFILE'):
                    consumer.validate_source(fake)

    def test_non_ship_or_changed_fresh_source_does_not_read_body(self):
        for options, reason in (({'state': 4}, 'EXPECTS_SHIP'),
                                ({'bad_caller': True}, 'FRESH_SOURCE_SEQUENCE_CHANGED')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = self.scenario(**options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assertEqual(scenario.memory.body_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertTrue(scenario.memory.closed)

    def test_entry_body_or_final_module_change_saves_no_partial_binary(self):
        for options, reason in (({'body_changes': True}, 'ENTRY_BODY_CHANGED'),
                                ({'final_change': ('exe_base', fixture.Memory.exe + 4096)}, 'MODULE_CHANGED'),
                                ({'final_change': ('game_base', fixture.Memory.game + 4096)}, 'MODULE_CHANGED')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = self.scenario(**options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assertEqual(list(folder.glob('*.bin')), [])
                failure = json.loads((folder / 'consumer.incomplete.json').read_text('utf8'))
                self.assertFalse(failure['partial_binary_saved'])
                self.assertTrue(scenario.memory.closed)

    def test_low_read_budget_does_not_expand_or_retry(self):
        scenario = self.scenario()
        with tempfile.TemporaryDirectory() as parent:
            folder = Path(parent) / 'capture'
            with patch.object(consumer.profile, 'MAX_READS', 6):
                with self.assertRaisesRegex(ValueError, 'BUDGET'):
                    self.run_fixture(scenario, folder)
            self.assertEqual(scenario.memory.body_reads(), [])
            self.assertLessEqual(len(scenario.memory.reads), 6)
            self.assertEqual(scenario.opens, 1)


if __name__ == '__main__':
    unittest.main()
