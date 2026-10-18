"""Four-word owned memory fixtures plus offline pinned LuaDLL exports."""
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
spec = importlib.util.spec_from_file_location(
    'owned_flow_iat_capture', ROOT / 'tools/flow-exe-iat-target-capture.py')
iat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iat)
ship = runpy.run_path(str(ROOT / 'tools/career-cache-capture.py'))


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class Memory:
    exe, game, lua, context = 0x140000000, 0x180000000, 0x700000000, 0x1011ED90A0

    def __init__(self, export_rows, state=3, after=3, bad_pin=False):
        self.identity = {'exe_base': self.exe, 'exe_size': iat.flow.EXE_IMAGE_SIZE,
                         'exe_path': 'fixture/helldivers2.exe',
                         'game_base': self.game, 'game_size': iat.flow.GAME_IMAGE_SIZE,
                         'game_path': 'fixture/game.dll',
                         'lua_base': self.lua, 'lua_size': iat.LUA_IMAGE_SIZE,
                         'lua_path': str(iat.LUA_PATH.resolve())}
        names = ('lua_touserdata', 'lua_pushvalue', 'luaL_ref', 'luaL_unref')
        by_name = {row['name']: row for row in export_rows}
        self.words = {slot: self.lua + by_name[name]['rva'] for (_, slot), name in zip(iat.CALLS, names)}
        self.names, self.state, self.after, self.bad_pin = names, state, after, bad_pin
        self.state_reads, self.closed = 0, False
        self.reads, self.queries = [], []
        self.clock, self.delay = None, 0.0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def query(self, address):
        self.queries.append(address)
        if self.clock:
            self.clock.value += self.delay
        if self.context <= address < self.context + 0x100000:
            return {'base': self.context, 'size': 0x100000, 'state': 0x1000,
                    'type': 0x20000, 'protect': 4}
        for role, base, size in (('exe', self.exe, iat.flow.EXE_IMAGE_SIZE),
                                 ('game', self.game, iat.flow.GAME_IMAGE_SIZE)):
            if base <= address < base + size:
                return {'base': base, 'size': size, 'state': 0x1000, 'type': 0x1000000,
                        'protect': 0x20 if address == self.exe + iat.flow.TARGET_RVA else 2}
        raise AssertionError('No query of Lua target body or other memory allowed')

    def read(self, address, n):
        self.reads.append((address, n))
        if self.clock:
            self.clock.value += self.delay
        if address == self.game + ship['STATE_GLOBAL']:
            assert n == 8
            return struct.pack('<Q', self.context)
        if address == self.context + ship['STATE_OFFSET']:
            assert n == 4
            value = self.state if self.state_reads == 0 else self.after
            self.state_reads += 1
            return struct.pack('<I', value)
        if address == self.exe + iat.flow.TARGET_RVA:
            assert n == 16
            return bytes(n) if self.bad_pin else bytes.fromhex(iat.flow.TARGET_PIN)
        if address - self.exe in self.words:
            assert n == 8
            return struct.pack('<Q', self.words[address - self.exe])
        raise AssertionError('Read outside four slots, setter PIN or Ship')

    def slot_reads(self):
        return [(at - self.exe, n) for at, n in self.reads if at - self.exe in self.words]


class Scenario:
    def __init__(self, exports, final_change=None, final_pid_change=False, **options):
        self.memory = Memory(exports, **options)
        self.final_change, self.final_pid_change = final_change, final_pid_change
        self.opens = self.resolutions = self.enumerations = self.fingerprints = 0

    def dependencies(self):
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

        def fingerprint():
            self.fingerprints += 1
            return dict(iat.flow.FINGERPRINT)

        def open_process(pid):
            assert pid == 54321
            self.opens += 1
            return self.memory

        return {'fingerprints': fingerprint, 'resolve_game': resolve,
                'game_processes': processes, 'Process': open_process,
                'validate_identity': lambda identity, stamps: None,
                'ship_state': ship['ship_state']}


class FourSlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua_file = iat.load_lua_file()
        cls.exports = cls.lua_file['exports']['named_exports']

    def run_fixture(self, scenario, folder, clock=None):
        return iat.run(folder, scenario.dependencies(), clock=clock or Clock())

    def test_four_exact_words_map_to_real_offline_exports_and_total72bytes(self):
        scenario = Scenario(self.exports)
        with tempfile.TemporaryDirectory() as parent:
            result = self.run_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual(meta['resolved'], 4)
            self.assertTrue(meta['identity_ready'])
            self.assertEqual([row['names'] for row in meta['rows']], [[name] for name in scenario.memory.names])
            self.assertEqual([row['binary_offset'] for row in meta['rows']], [0, 8, 16, 24])
            self.assertEqual(scenario.memory.slot_reads(), [(slot, 8) for _, slot in iat.CALLS])
            self.assertEqual(meta['budget']['read_calls'], 9)
            self.assertEqual(meta['budget']['query_calls'], 9)
            self.assertEqual(meta['budget']['bytes_requested'], 72)
            self.assertEqual(len(scenario.memory.reads), 9)
            self.assertEqual(len(Path(result['binary_path']).read_bytes()), 32)
            lua_copy = Path(meta['lua_file_copy']).read_bytes()
            self.assertEqual(len(lua_copy), 469080)
            self.assertEqual(hashlib.sha256(lua_copy).hexdigest(), iat.LUA_SHA)
            self.assertEqual(scenario.resolutions, 2)
            self.assertEqual(scenario.opens, 1)
            self.assertTrue(scenario.memory.closed)
            self.assertFalse(meta['native_called'])
            self.assertFalse(meta['native_written'])
            self.assertFalse(meta['contract_ready'])
            self.assertEqual(meta['target_code_reads'], 0)
            self.assertFalse(meta['source']['body_fresh_rechecked'])

    def test_marker_unmapped_unexported_and_forwarder_do_not_acquire_names(self):
        identity = Memory(self.exports).identity
        for pointer, reason in ((0, 'INVALID_OR_MARKER_POINTER'),
                                (0xCCCCCCCCCCCCCCCC, 'INVALID_OR_MARKER_POINTER'),
                                (Memory.exe + 0x1234, 'OUTSIDE_PINNED_LUA_IMAGE'),
                                (Memory.lua + 0x1010, 'NO_EXACT_PUBLIC_EXPORT')):
            with self.subTest(reason=reason):
                row = iat.identify(pointer, identity, self.lua_file['exports'])
                self.assertEqual(row['status'], 'unknown')
                self.assertEqual(row['reason'], reason)
                self.assertEqual(row['names'], [])
        forwarded = {'named_exports': [{'name': 'synthetic_forwarder', 'rva': 0x69000,
                                        'forwarded': True, 'executable_file_section': False}]}
        self.assertEqual(iat.identify(Memory.lua + 0x69000, identity, forwarded)['reason'],
                         'FORWARDER_NOT_FOLLOWED')
        scenario = Scenario(self.exports)
        scenario.memory.words[iat.CALLS[0][1]] = 0xCCCCCCCCCCCCCCCC
        with tempfile.TemporaryDirectory() as parent:
            result = self.run_fixture(scenario, Path(parent) / 'capture')
            meta = json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertTrue(meta['complete'])
            self.assertEqual(meta['resolved'], 3)
            self.assertFalse(meta['identity_ready'])
            self.assertEqual(meta['rows'][0]['names'], [])

    def test_source_or_lua_file_change_refuses_before_process_dependencies(self):
        with tempfile.TemporaryDirectory() as parent:
            source = Path(parent) / 'source'
            source.mkdir()
            (source / 'setter.bin').write_bytes((iat.SOURCE / 'setter.bin').read_bytes()[:-1] + b'\x00')
            (source / 'setter.json').write_bytes((iat.SOURCE / 'setter.json').read_bytes())
            scenario = Scenario(self.exports)
            with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                iat.run(Path(parent) / 'badsource', scenario.dependencies(), source=source)
            self.assertEqual(scenario.fingerprints, 0)
            self.assertEqual(scenario.opens, 0)
            lua_bad = Path(parent) / 'lua51.dll'
            raw = bytearray(self.lua_file['raw'])
            raw[-1] ^= 1
            lua_bad.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'LUA_FILE_HASH'):
                iat.run(Path(parent) / 'badlua', scenario.dependencies(), lua_path=lua_bad)
            self.assertEqual(scenario.fingerprints, 0)
            self.assertEqual(scenario.opens, 0)
        with self.assertRaisesRegex(ValueError, 'LUA_DOS'):
            iat.parse_exports(b'\x00' * 64)

    def test_non_ship_or_bad_current_pin_never_reads_slots(self):
        for options, reason in (({'state': 4}, 'EXPECTS_SHIP'), ({'bad_pin': True}, 'PIN_MISMATCH')):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(self.exports, **options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, reason):
                    self.run_fixture(scenario, folder)
                self.assertEqual(scenario.memory.slot_reads(), [])
                self.assertEqual(list(folder.glob('*.bin')), [])
                self.assertTrue(scenario.memory.closed)

    def test_ship_or_any_source_generation_change_withholds_names_no_bin(self):
        for options in ({'after': 4}, {'final_change': ('exe_base', Memory.exe + 4096)},
                        {'final_change': ('game_base', Memory.game + 4096)},
                        {'final_change': ('lua_base', Memory.lua + 4096)},
                        {'final_change': ('lua_size', 4096)},
                        {'final_change': ('lua_path', 'wrong.dll')}, {'final_pid_change': True}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(self.exports, **options)
                folder = Path(parent) / 'capture'
                with self.assertRaisesRegex(ValueError, 'CHANGED|MODULE_INVALID'):
                    self.run_fixture(scenario, folder)
                self.assertEqual(list(folder.glob('*.bin')), [])
                failure = json.loads((folder / 'iat.incomplete.json').read_text('utf8'))
                self.assertFalse(failure['identity_ready'])
                self.assertEqual(failure['resolved'], 0)
                self.assertTrue(all(row['status'] == 'withheld' and not row['names'] for row in failure['rows']))
                self.assertTrue(scenario.memory.closed)

    def test_lower_read_byte_soft_caps_and_existing_folder_stop_once(self):
        for key, value in (('MAX_READS', 8), ('MAX_BYTES', 71)):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as parent:
                scenario = Scenario(self.exports)
                folder = Path(parent) / 'capture'
                with patch.object(iat.flow, key, value):
                    with self.assertRaisesRegex(ValueError, 'BUDGET'):
                        self.run_fixture(scenario, folder)
                self.assertEqual(scenario.memory.slot_reads(), [])
                self.assertEqual(scenario.opens, 1)
                self.assertEqual(list(folder.glob('*.bin')), [])
        scenario, clock = Scenario(self.exports), Clock()
        scenario.memory.clock, scenario.memory.delay = clock, 0.4
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaisesRegex(ValueError, 'TIME_BUDGET'):
                self.run_fixture(scenario, Path(parent) / 'capture', clock)
            self.assertEqual(scenario.opens, 1)
            self.assertEqual(scenario.memory.slot_reads(), [])
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(iat, 'validate_source', side_effect=AssertionError('no read')):
                with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
                    iat.run(folder)

    def test_single_module_snapshot_keeps_exact_lua_exe_game(self):
        rows = [{'name': name, 'base': base, 'size': size, 'path': path} for name, base, size, path in (
            ('helldivers2.exe', Memory.exe, iat.flow.EXE_IMAGE_SIZE, 'fixture/helldivers2.exe'),
            ('game.dll', Memory.game, iat.flow.GAME_IMAGE_SIZE, 'fixture/game.dll'),
            ('lua51.dll', Memory.lua, iat.LUA_IMAGE_SIZE, str(iat.LUA_PATH.resolve())))]
        calls = []
        identity = iat.resolve_sources(54321, lambda pid: calls.append(pid) or rows)
        self.assertEqual(calls, [54321])
        self.assertEqual(identity, Memory(self.exports).identity)
        with self.assertRaisesRegex(FileNotFoundError, 'EXACT_LUA_MODULE'):
            iat.resolve_sources(54321, lambda _: rows[:-1])
        with self.assertRaisesRegex(FileNotFoundError, 'EXACT_LUA_MODULE'):
            iat.resolve_sources(54321, lambda _: rows + [rows[-1]])


if __name__ == '__main__':
    unittest.main()
