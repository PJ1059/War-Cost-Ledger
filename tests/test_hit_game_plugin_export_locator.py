"""Three tiny named-export owned fixtures, no process/native Game access."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_flow_exe_entry_code_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_plugin_export_locator', ROOT / 'tools/hit-game-plugin-export-locator.py')
locator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(locator)
PREFIX = bytes(range(16))  # Owned unknown loaded bytes, not original packed PIN.
HEADER = (ROOT / 'dist/hit-contact-registration-source-20261013/game-pe-header.bin').read_bytes()
DIRECTORY = (locator.SOURCE / 'original-export.bin').read_bytes()


class Memory(fixture.Memory):
    def __init__(self, state=2, after=None, change=None):
        super().__init__(state=state, after=state if after is None else after)
        self.change, self.prefix_reads, self.header_reads = change, 0, 0

    def query(self, address):
        if address == self.game + locator.TARGET_RVA:
            self.queries.append(address)
            return {'base': self.game, 'size': locator.IMAGE_SIZE, 'state': 0x1000,
                    'type': 0x1000000, 'protect': 0x20}
        return super().query(address)

    def read(self, address, n):
        rva = address - self.game
        if rva in (0, locator.EXPORT_RVA, locator.TARGET_RVA):
            self.reads.append((address, n))
            if rva == 0:
                assert n == 4096
                self.header_reads += 1
                raw = bytearray(HEADER)
                if self.change == 'header' and self.header_reads > 1:
                    raw[-1] ^= 1
                return bytes(raw)
            if rva == locator.EXPORT_RVA:
                assert n == 74
                raw = bytearray(DIRECTORY)
                if self.change == 'name': raw[49] ^= 1
                if self.change == 'target': struct.pack_into('<I', raw, 66, locator.TARGET_RVA + 16)
                if self.change == 'forwarder': struct.pack_into('<I', raw, 66, locator.EXPORT_RVA + 49)
                if self.change == 'outside_table': struct.pack_into('<I', raw, 32, locator.EXPORT_RVA + 74)
                return bytes(raw)
            assert n == 16
            self.prefix_reads += 1
            return bytes(n) if self.change == 'prefix' and self.prefix_reads > 1 else PREFIX
        return super().read(address, n)


class Scenario(fixture.Scenario):
    def __init__(self, final_change=None, **options):
        super().__init__(final_change=final_change)
        self.memory = Memory(**options)


class PluginLocatorTests(unittest.TestCase):
    def test_actual_internal_export_parser_unknown_loaded_prefix_title_ship(self):
        source = locator.validate_source()
        self.assertFalse(source['original_packed_bytes_used_as_pin'])
        self.assertEqual(locator.parse_export(DIRECTORY), {'name': 'get_plugin_api', 'ordinal': 1,
            'rva': 0x4EEAD0, 'forwarder': False, 'all_tables_strings_inside_directory': True})
        for state in (2, 3):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(state=state)
                result = locator.run(Path(parent) / 'capture', scenario.dependencies(), clock=fixture.Clock())
                m = json.loads(Path(result['json_path']).read_text('utf8'))
                self.assertEqual(Path(result['binary_path']).read_bytes(), PREFIX)
                self.assertEqual(m['target_prefix_hex'], PREFIX.hex())
                self.assertEqual(m['state_before'], m['state_after'])
                self.assertEqual(m['state_before']['state'], state)
                self.assertEqual(m['budget']['read_calls'], 10)
                self.assertEqual(m['budget']['query_calls'], 10)
                self.assertEqual(m['budget']['bytes_requested'], 8396)
                self.assertEqual(scenario.memory.prefix_reads, 2)
                self.assertFalse(m['body_read'])
                self.assertFalse(m['native_called'])
                self.assertFalse(m['native_written'])
                self.assertFalse(m['plugin_table_contract_proven'])
                self.assertTrue(scenario.memory.closed)

    def test_changed_name_target_internal_bounds_or_state_withhold_without_following(self):
        options = (({'change': 'name'}, 'NAME_OR_ORDINAL_CHANGED'),
                   ({'change': 'target'}, 'TARGET_CHANGED'),
                   ({'change': 'forwarder'}, 'FORWARDER_UNSUPPORTED'),
                   ({'change': 'outside_table'}, 'OUTSIDE_DIRECTORY'),
                   ({'change': 'header'}, 'LOADED_SOURCE_CHANGED'),
                   ({'change': 'prefix'}, 'LOADED_SOURCE_CHANGED'),
                   ({'after': 3}, 'STATIC_STATE_CHANGED'),
                   ({'state': 4}, 'EXPECTS_STATIC'),
                   ({'final_change': ('game_base', fixture.Memory.game + 4096)}, 'MODULE_CHANGED'))
        for opts, reason in options:
            with self.subTest(opts=opts), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**opts), Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    locator.run(folder, scenario.dependencies(), clock=fixture.Clock())
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertTrue(scenario.memory.closed)
                if opts.get('change') in ('name', 'target', 'forwarder', 'outside_table') or opts.get('state') == 4:
                    self.assertEqual(scenario.memory.prefix_reads, 0)
        with tempfile.TemporaryDirectory() as parent:
            scenario = Scenario()
            with patch.object(locator, 'SOURCE_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'STATIC_SOURCE_CHANGED'):
                    locator.run(Path(parent) / 'capture', scenario.dependencies(), clock=fixture.Clock())
            self.assertEqual(scenario.opens, 0)

    def test_reduced_hard_budget_refuses_without_retry_or_partial_binary(self):
        for cap, limit in (('MAX_READS', 3), ('MAX_BYTES', 4200)):
            with self.subTest(cap=cap), tempfile.TemporaryDirectory() as parent:
                reader = locator.private_reader()
                setattr(reader, cap, limit)
                scenario, folder = Scenario(), Path(parent) / 'capture'
                with patch.object(locator, 'private_reader', return_value=reader):
                    with self.assertRaisesRegex(ValueError, 'BUDGET'):
                        locator.run(folder, scenario.dependencies(), clock=fixture.Clock())
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertEqual(scenario.opens, 1)
                self.assertTrue(scenario.memory.closed)
                self.assertLessEqual(len(scenario.memory.reads), limit if cap == 'MAX_READS' else 24)


if __name__ == '__main__':
    unittest.main()
