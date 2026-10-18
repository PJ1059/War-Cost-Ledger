"""Narrow Unit entry fixtures; reuse existing owned PE/Ship memory provider."""
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
    'owned_unit_event_exe_capture', ROOT / 'tools/flow-exe-unit-event-code-capture.py')
unit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unit)
ORIGINAL_TARGET = (fixture.flow.TARGET_NAME, fixture.flow.TARGET_RVA, fixture.flow.TARGET_PIN)


class UnitEntryTests(unittest.TestCase):
    def run_fixture(self, scenario, folder):
        # The fixture provider's profile is temporary; the production sampler
        # and its private Unit profile are not mutated by these test patches.
        with patch.object(fixture, 'flow', unit.profile):
            return unit.run(folder, scenario.dependencies(), clock=fixture.Clock())

    def scenario(self, **options):
        with patch.object(fixture, 'flow', unit.profile):
            return fixture.Scenario(**options)

    def test_actual_inventory_pin_frozen_core_and_owned_declared_body(self):
        scenario = self.scenario()
        with tempfile.TemporaryDirectory() as parent:
            result = self.run_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(result['json_path']).read_text('utf8'))
            raw = Path(result['binary_path']).read_bytes()
            self.assertEqual(Path(result['binary_path']).name, 'unit-event.bin')
            self.assertEqual(meta['target_module'], 'exe')
            self.assertEqual(meta['target_name'], 'Unit.flow_event')
            self.assertEqual(meta['target_rva'], 0x413070)
            self.assertEqual(meta['target_pin'], '48895c2418574883ec20ba0100000048')
            self.assertEqual(meta['pin_source']['sha256'], unit.profile.INVENTORY_SHA)
            self.assertEqual(raw[meta['binary_pin_offset']:meta['binary_pin_offset'] + 16],
                             bytes.fromhex(unit.TARGET_PIN))
            self.assertEqual(meta['ranges'][0]['name'], 'Unit.flow_event')
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
            self.assertLessEqual(meta['budget']['bytes_requested'], 8192)
            self.assertLessEqual(meta['budget']['read_calls'], 32)
            self.assertEqual(hashlib.sha256(unit.CORE_PATH.read_bytes()).hexdigest(), unit.CORE_SHA)
            self.assertEqual((fixture.flow.TARGET_NAME, fixture.flow.TARGET_RVA,
                              fixture.flow.TARGET_PIN), ORIGINAL_TARGET)
            self.assertFalse(meta['native_called'])
            self.assertFalse(meta['native_written'])
            self.assertFalse(meta['classification_ready'])

    def test_non_ship_or_pin_mismatch_never_reads_body(self):
        for options, reason in (({'state': 4}, 'EXPECTS_SHIP'),
                                ({'bad_pin': True}, 'ENTRY_PIN_MISMATCH')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = self.scenario(**options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assertEqual(scenario.memory.body_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])

    def test_ship_or_exe_game_identity_change_discards_body(self):
        for options in ({'after': 4}, {'final_change': ('exe_base', fixture.Memory.exe + 4096)},
                        {'final_change': ('game_base', fixture.Memory.game + 4096)}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = self.scenario(**options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, 'SHIP_CHANGED|MODULE_CHANGED'):
                    self.run_fixture(scenario, folder)
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertTrue(scenario.memory.closed)

    def test_low_cap_or_inventory_source_change_refuses_no_expansion(self):
        with tempfile.TemporaryDirectory() as parent:
            scenario = self.scenario()
            folder = Path(parent) / 'lowcap'
            with patch.object(unit.profile, 'MAX_READS', 6):
                with self.assertRaisesRegex(ValueError, 'BUDGET'):
                    self.run_fixture(scenario, folder)
            self.assertEqual(scenario.memory.body_reads(), [])
            self.assertEqual(list(folder.glob('*.bin')), [])
            scenario = self.scenario()
            with patch.object(unit.profile, 'INVENTORY_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'INVENTORY_CHANGED'):
                    self.run_fixture(scenario, Path(parent) / 'badsource')
            self.assertEqual(scenario.opens, 0)


if __name__ == '__main__':
    unittest.main()
