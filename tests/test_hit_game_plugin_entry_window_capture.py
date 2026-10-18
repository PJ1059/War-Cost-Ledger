"""One tiny owned fixed-window smoke group; no Game/default live CLI."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_hit_game_plugin_export_locator as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_plugin_entry_window',
    ROOT / 'tools/hit-game-plugin-entry-window-capture.py')
window = importlib.util.module_from_spec(spec)
spec.loader.exec_module(window)


class Memory(fixture.Memory):
    def __init__(self, changed_prefix=False):
        super().__init__()
        self.changed_prefix = changed_prefix
        self.window_reads = 0

    def read(self, address, n):
        if address == self.game + window.TARGET_RVA:
            self.reads.append((address, n))
            if n == 16:
                self.prefix_reads += 1
                return bytes(n) if self.changed_prefix else bytes.fromhex(window.PIN_HEX)
            assert n == 256
            self.window_reads += 1
            return bytes.fromhex(window.PIN_HEX) + b'\x90' * 240
        return super().read(address, n)


class Scenario(fixture.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class PluginWindowSmokeTests(unittest.TestCase):
    def test_fixed_window_real_prefix_no_declaration_and_failures(self):
        with tempfile.TemporaryDirectory() as parent:
            scenario = Scenario()
            result = window.run(Path(parent) / 'normal', scenario.dependencies(), clock=fixture.fixture.Clock())
            meta = json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual(len(Path(result['binary_path']).read_bytes()), 256)
            self.assertEqual(meta['budget']['read_calls'], 11)
            self.assertEqual(meta['budget']['query_calls'], 11)
            self.assertEqual(meta['budget']['bytes_requested'], 8652)
            self.assertEqual(scenario.memory.window_reads, 1)
            self.assertEqual(scenario.memory.prefix_reads, 2)
            self.assertFalse(meta['declared_code_complete'])
            self.assertFalse(meta['logical_function_complete'])
            self.assertFalse(meta['pdata_read'])
            self.assertFalse(meta['native_called'])
            self.assertEqual(meta['state_before'], meta['state_after'])
            self.assertEqual(meta['state_before']['state'], 2)
            self.assertEqual(meta['source']['metadata_sha256'], window.SOURCE_SHA)
            scenario = Scenario(changed_prefix=True)
            with self.assertRaisesRegex(ValueError, 'ACTUAL_ENTRY_PIN_CHANGED'):
                window.run(Path(parent) / 'changed', scenario.dependencies(), clock=fixture.fixture.Clock())
            self.assertEqual(scenario.memory.window_reads, 0)
            self.assertEqual(list((Path(parent) / 'changed').glob('*.bin')), [])
            locator = window.private_locator()
            reader = locator.private_reader()
            reader.MAX_BYTES = 4200
            locator.private_reader = lambda: reader
            scenario = Scenario()
            with patch.object(window, 'private_locator', return_value=locator):
                with self.assertRaisesRegex(ValueError, 'BUDGET'):
                    window.run(Path(parent) / 'cap', scenario.dependencies(), clock=fixture.fixture.Clock())
            self.assertEqual(scenario.memory.window_reads, 0)
            self.assertLessEqual(sum(n for _, n in scenario.memory.reads), 4200)
            budget = reader.Budget(scenario.memory, scenario.memory.identity, fixture.fixture.Clock())
            with self.assertRaisesRegex(ValueError, 'OUTSIDE_GAME_IMAGE'):
                budget.read_module(reader.IMAGE_SIZE - 128, 256, 'fixed_named_entry_code_window', True)


if __name__ == '__main__':
    unittest.main()
