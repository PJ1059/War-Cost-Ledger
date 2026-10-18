"""Focused owned8B branch fixtures; no Game/native execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_flow_exe_entry_code_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_noref_branch', ROOT / 'tools/flow-world-no-ref-branch-capture.py')
noref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(noref)
PROLOGUE = (noref.SOURCE / 'consumer.bin').read_bytes()
OWNED_SNIPPET = bytes.fromhex('33c0c3cccccccccc')


class Memory(fixture.Memory):
    def __init__(self, changed_caller=False, changed_prologue=False, **options):
        super().__init__(**options)
        self.changed_caller, self.changed_prologue = changed_caller, changed_prologue

    def query(self, address):
        if address in (self.exe + noref.helper.SOURCE_SEQUENCE_RVA,
                       self.exe + noref.PROLOGUE_RVA, self.exe + noref.BRANCH_TARGET_RVA):
            self.queries.append(address)
            return {'base': self.exe, 'size': noref.helper.profile.EXE_IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
        return super().query(address)

    def read(self, address, size):
        if address == self.exe + noref.helper.SOURCE_SEQUENCE_RVA:
            assert size == 18
            self.reads.append((address, size))
            return bytes(size) if self.changed_caller else bytes.fromhex(noref.helper.SOURCE_SEQUENCE_HEX)
        if address == self.exe + noref.PROLOGUE_RVA:
            assert size == 24
            self.reads.append((address, size))
            return bytes(size) if self.changed_prologue else PROLOGUE
        if address == self.exe + noref.BRANCH_TARGET_RVA:
            assert size == 8
            self.reads.append((address, size))
            return OWNED_SNIPPET
        return super().read(address, size)

    def snippet_reads(self):
        return [(address, size) for address, size in self.reads if address == self.exe + noref.BRANCH_TARGET_RVA]


class Scenario(fixture.Scenario):
    def __init__(self, **options):
        final_change = options.pop('final_change', None)
        super().__init__(final_change=final_change)
        self.memory = Memory(**options)


class NoRefSnippetTests(unittest.TestCase):
    def run_fixture(self, scenario, folder):
        return noref.run(folder, scenario.dependencies(), clock=fixture.Clock())

    def test_frozen_cmp_je_rel32_freshwhole24_and_only8B_target(self):
        source_raw, source = noref.validate_source()
        self.assertEqual(source_raw[:3].hex(), '83fafe')
        self.assertEqual(source['branch_hex'], '0f8445010000')
        self.assertEqual(source['branch_target_rva'], 0x2D478E)
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertEqual(Path(status['binary_path']).read_bytes(), OWNED_SNIPPET)
            self.assertEqual(meta['ranges'], [{'module': 'exe', 'rva': 0x2D478E, 'length': 8, 'binary_offset': 0}])
            self.assertEqual(meta['fresh_whole_prologue']['hex'], PROLOGUE.hex())
            self.assertEqual(meta['budget']['read_calls'], 7)
            self.assertEqual(meta['budget']['query_calls'], 7)
            self.assertEqual(meta['budget']['bytes_requested'], 74)
            self.assertEqual(len(scenario.memory.snippet_reads()), 1)
            self.assertEqual(scenario.resolutions, 2)
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertFalse(meta['function_identity_claimed'])
            self.assertFalse(meta['callback_consumer_proven'])
            self.assertFalse(meta['logical_function_complete'])
            self.assertFalse(meta['nonnil_body_read'])
            self.assertFalse(meta['decoded'])
            self.assertFalse(meta['native_called'])
            self.assertEqual(meta['registry_reads'], 0)

    def test_source_sha_relative_or_profile_change_refuses_before_open(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as parent:
            with patch.object(noref, 'SOURCE_BIN_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                    self.run_fixture(scenario, Path(parent) / 'badsha')
            with patch.object(noref, 'BRANCH_TARGET_RVA', 0x2D478F):
                with self.assertRaisesRegex(ValueError, 'SOURCE_RELATIVE_BRANCH'):
                    self.run_fixture(scenario, Path(parent) / 'badrelative')
            self.assertEqual(scenario.opens, 0)
            folder = Path(parent) / 'source'
            folder.mkdir()
            (folder / 'consumer.bin').write_bytes(PROLOGUE)
            meta = json.loads((noref.SOURCE / 'consumer.json').read_text('utf8'))
            meta['fingerprint']['exe_sha'] = '0' * 64
            altered = json.dumps(meta).encode()
            (folder / 'consumer.json').write_bytes(altered)
            with patch.object(noref, 'SOURCE_META_SHA', hashlib.sha256(altered).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'SOURCE_PROFILE'):
                    noref.validate_source(folder)

    def test_non_ship_or_freshsource_change_never_reads_target(self):
        for options, reason in (({'state': 4}, 'EXPECTS_SHIP'),
                                ({'changed_caller': True}, 'FRESH_CALLER_CHANGED'),
                                ({'changed_prologue': True}, 'FRESH_PROLOGUE_CHANGED')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(**options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assertEqual(scenario.memory.snippet_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertTrue(scenario.memory.closed)

    def test_ship_or_module_change_saves_no_snippet(self):
        for options, reason in (({'after': 4}, 'SHIP_CHANGED'),
                                ({'final_change': ('exe_base', fixture.Memory.exe + 4096)}, 'MODULE_CHANGED'),
                                ({'final_change': ('game_base', fixture.Memory.game + 4096)}, 'MODULE_CHANGED')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(**options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertTrue(scenario.memory.closed)

    def test_lower_byte_read_caps_do_not_expand_or_retry(self):
        for name, limit in (('MAX_READS', 6), ('MAX_BYTES', 73)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario()
                with patch.object(noref.helper.profile, name, limit):
                    with self.assertRaisesRegex(ValueError, 'BUDGET'):
                        self.run_fixture(scenario, Path(parent) / 'capture')
                self.assertEqual(scenario.memory.snippet_reads(), [])
                self.assertEqual(scenario.opens, 1)


if __name__ == '__main__':
    unittest.main()
