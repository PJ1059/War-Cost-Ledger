"""Owned fixed world/reference path fixtures; no Game process APIs."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_flow_exe_iat_target_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_world_reference', ROOT / 'tools/flow-world-reference-capture.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


class Memory(fixture.Memory):
    app, array, game_world, state_container, old_l = (0x1100000000, 0x1101000000,
                                                    0x1102000000, 0x1105000000, 0x10140000)
    other_world = 0x1103000000

    def __init__(self, exports, count=3, duplicate=False, missing=False,
                 bad_world=False, change_ref=False, change_array=False,
                 change_world=False, change_count=False, guard_fields=False, **options):
        super().__init__(exports, **options)
        self.count, self.duplicate, self.missing, self.bad_world = count, duplicate, missing, bad_world
        self.change_ref, self.change_array = change_ref, change_array
        self.change_world, self.change_count, self.guard_fields = change_world, change_count, guard_fields
        self.ref_reads = self.array_reads = self.world_reads = self.count_reads = 0
        self.field_regions = ((self.app, 0x1000), (self.array, 0x1000),
                              (self.game_world, world.WORLD_STATE_REF_OFFSET + 0x100),
                              (self.state_container, 0x1000))

    def query(self, address):
        # No read or query of the other World's data is permitted.
        if address == self.other_world:
            raise AssertionError('Other World dereference')
        for base, size in self.field_regions:
            if base <= address < base + size:
                self.queries.append(address)
                return {'base': base, 'size': size, 'state': 0x1000,
                        'type': 0x20000, 'protect': 0x104 if self.guard_fields else 4}
        if any(address == self.exe + rva for rva, _ in world.WORLD_PINS):
            self.queries.append(address)
            return {'base': self.exe, 'size': world.iat.flow.EXE_IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
        return super().query(address)

    def read(self, address, n):
        raw = None
        if address == self.context + world.GAME_WORLD_OFFSET:
            self.world_reads += 1
            raw = struct.pack('<Q', 0x12345 if self.bad_world else
                              self.other_world if self.change_world and self.world_reads > 1 else self.game_world)
        elif address == self.exe + world.APPLICATION_GLOBAL:
            raw = struct.pack('<Q', self.app)
        elif address == self.app + world.WORLD_COUNT_OFFSET:
            self.count_reads += 1
            raw = struct.pack('<I', self.count + 1 if self.change_count and self.count_reads > 1 else self.count)
        elif address == self.app + world.WORLD_ARRAY_OFFSET:
            raw = struct.pack('<Q', self.array)
        elif address == self.array:
            self.array_reads += 1
            entries = [self.other_world] * (n // 8)
            if not self.missing:
                entries[0] = self.game_world
            if self.duplicate and len(entries) > 1:
                entries[1] = self.game_world
            if self.change_array and self.array_reads > 1:
                entries[-1] = 0
            raw = struct.pack('<' + 'Q' * len(entries), *entries)
        elif address == self.game_world + world.WORLD_STATE_REF_OFFSET:
            self.ref_reads += 1
            raw = struct.pack('<Qi', self.state_container, 42 if self.change_ref and self.ref_reads > 1 else 41)
        elif address == self.state_container:
            raw = struct.pack('<Q', self.old_l)
        else:
            for rva, pin in world.WORLD_PINS:
                if address == self.exe + rva:
                    raw = bytes.fromhex(pin)
                    break
        if raw is not None:
            self.reads.append((address, n))
            assert len(raw) == n
            return raw
        return super().read(address, n)


class Scenario(fixture.Scenario):
    def __init__(self, exports, final_change=None, **options):
        super().__init__(exports, final_change=final_change)
        self.memory = Memory(exports, **options)


class WorldReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = world.iat.load_lua_file()
        cls.exports = cls.lua['exports']['named_exports']

    def run_fixture(self, scenario, folder):
        return world.run(folder, scenario.dependencies(), clock=fixture.Clock())

    def test_unique_game_world_two_identical_path_reads_pointer_only_oldl(self):
        scenario = Scenario(self.exports)
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertTrue(meta['complete'])
            self.assertTrue(meta['fields_ready'])
            self.assertTrue(meta['path_snapshots_match'])
            self.assertEqual(meta['observation']['game_world'], Memory.game_world)
            self.assertEqual(meta['observation']['world_count'], 3)
            self.assertEqual(meta['observation']['matched_index_one_based'], 1)
            self.assertEqual(meta['observation']['reference_i32'], 41)
            self.assertEqual(meta['observation']['old_l_pointer_candidate'], Memory.old_l)
            self.assertEqual(meta['observation']['old_l_candidate_status'], 'pointer_shape_only')
            self.assertFalse(meta['observation']['old_l_type_verified'])
            self.assertFalse(meta['observation']['registry_identity_verified'])
            self.assertFalse(meta['callback_ready'])
            self.assertFalse(meta['native_called'])
            self.assertEqual(meta['registry_reads'], 0)
            self.assertEqual(meta['other_world_fields_read'], 0)
            self.assertEqual(meta['budget']['read_calls'], 23)
            self.assertEqual(meta['budget']['query_calls'], 23)
            self.assertEqual(meta['budget']['bytes_requested'], 209)
            self.assertEqual(len(scenario.memory.reads), 23)
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertEqual(scenario.memory.ref_reads, 2)
            self.assertEqual(scenario.memory.array_reads, 2)
            self.assertTrue(scenario.memory.closed)

    def test_duplicate_missing_bad_world_and_out_of_range_count_refuse(self):
        for options, reason in (({'duplicate': True}, 'UNIQUE_GAME_WORLD'),
                                ({'missing': True}, 'UNIQUE_GAME_WORLD'),
                                ({'bad_world': True}, 'POINTER_INVALID'),
                                ({'count': 65}, 'COUNT_LIMIT'),
                                ({'guard_fields': True}, 'FIELD_UNREADABLE')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(self.exports, **options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assertEqual(list(folder.glob('world-reference.json')), [])
                failure = json.loads((folder / 'world-reference.incomplete.json').read_text('utf8'))
                self.assertTrue(failure['results_withheld'])
                self.assertFalse(failure['fields_ready'])
                self.assertNotIn('observation', failure)
                self.assertTrue(scenario.memory.closed)

    def test_non_ship_reads_no_path_or_pins(self):
        scenario = Scenario(self.exports, state=4)
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP'):
                self.run_fixture(scenario, Path(parent) / 'capture')
            self.assertEqual(len(scenario.memory.reads), 2)
            self.assertEqual(scenario.memory.world_reads, 0)

    def test_reference_world_count_array_or_module_change_withholds_all(self):
        options = ({'change_ref': True}, {'change_world': True}, {'change_count': True},
                   {'change_array': True}, {'after': 4},
                   {'final_change': ('lua_base', Memory.lua + 4096)},
                   {'final_change': ('exe_base', Memory.exe + 4096)},
                   {'final_change': ('game_base', Memory.game + 4096)})
        for choice in options:
            with self.subTest(choice=choice), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(self.exports, **choice)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, 'CHANGED|UNIQUE_GAME_WORLD'):
                    self.run_fixture(scenario, folder)
                failure = json.loads((folder / 'world-reference.incomplete.json').read_text('utf8'))
                self.assertFalse(failure['fields_ready'])
                self.assertNotIn('observation', failure)
                self.assertTrue(scenario.memory.closed)

    def test_array64_limit_and_low_cap_are_bounded(self):
        scenario = Scenario(self.exports, count=64)
        with tempfile.TemporaryDirectory() as parent:
            status = self.run_fixture(scenario, Path(parent) / 'max')
            meta = json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertEqual(meta['budget']['bytes_requested'], 1185)
            self.assertEqual(meta['budget']['read_calls'], 23)
            self.assertEqual([n for at, n in scenario.memory.reads if at == Memory.array], [512, 512])
            scenario = Scenario(self.exports)
            with patch.object(world.iat.flow, 'MAX_READS', 10):
                with self.assertRaisesRegex(ValueError, 'BUDGET'):
                    self.run_fixture(scenario, Path(parent) / 'low')
            self.assertLessEqual(len(scenario.memory.reads), 10)
            self.assertTrue(scenario.memory.closed)


if __name__ == '__main__':
    unittest.main()
