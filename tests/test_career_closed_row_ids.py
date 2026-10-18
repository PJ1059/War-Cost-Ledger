"""Local sparse fixtures only; never open a process or invoke a native API.

Headers, locale descriptors and the NEXT path come from saved real UI bytes.
Catalog/backref/constructor/count/peer/stat-ID fields below are SYNTHETIC owned
fixtures, not claims that this closed-page catalog has been observed live.
"""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_closed_owned_fixture', ROOT / 'tools/career-closed-row-ids.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
FIXTURE = ROOT / 'tests/fixtures/career-visible-rows.json'
FIXTURE_SHA = '8b78e6d5e3e0c7debc72c6613f8ae61c8094e2a05271d81fa910b667caa8f79d'


class Memory:
    def __init__(self):
        source = FIXTURE.read_bytes()
        assert hashlib.sha256(source).hexdigest() == FIXTURE_SHA
        fixture = json.loads(source)
        self.fixture_source_sha = fixture['source_sha256']
        self.bytes, self.regions, self.reads, self.queries = {}, [], [], []
        self.guard = self.short = self.changed = None
        self.state, self.entered, self.calls = 3, 0, {}
        self.region_override = None
        for record in fixture['read_records']:
            raw = (bytes.fromhex(record['raw_hex']) if 'raw_hex' in record
                   else base64.b64decode(record['raw_b64']))
            assert len(raw) == record['length']
            self.put(record['address'], raw)
        original = fixture['identity']
        self.identity = {'game_base': original['game_base'], 'game_size': reader.layout.IMAGE_SIZE,
                         'game_path': 'owned-game.dll', 'exe_path': 'owned-helldivers2.exe'}
        self.state_context = original['state_context']
        self.armory, self.list = original['controller'], original['list']
        self.row0, self.row8 = (fixture['rows'][i]['address'] for i in range(2))
        self.owner, self.local_user = 0x303000000, 0x304000000
        # Everything in this block is synthetic, including these invented IDs.
        self.put(self.identity['game_base'] + reader.CATALOG, struct.pack('<Q', self.owner))
        self.put(self.owner + reader.ARMORY_SLOT, struct.pack('<Q', self.armory))
        self.put(self.armory + reader.BACKREF, struct.pack('<Q', self.owner))
        self.put(self.armory + reader.BLOCK + reader.CONSTRUCTED, b'\x01')
        self.put(self.list + reader.FILLED_COUNT, struct.pack('<I', 30))
        self.put(self.identity['game_base'] + reader.LOCAL_USER, struct.pack('<Q', self.local_user))
        self.put(self.local_user + reader.LOCAL_PEER, struct.pack('<Q', 0xFEDCBA9876543210))
        self.put(self.row0 + reader.META, struct.pack('<II', 0x13579BDF, 123))
        self.put(self.row8 + reader.META, struct.pack('<II', 0x2468ACE0, 456))
        self.code_regions = []
        for rva, pin in reader.PINS:
            at, raw = self.identity['game_base'] + rva, bytes.fromhex(pin)
            self.put(at, raw)
            self.code_regions.append((at, len(raw)))

    def put(self, address, raw):
        self.bytes.update((address + index, byte) for index, byte in enumerate(raw))
        self.regions.append((address, len(raw)))

    def query(self, address):
        self.queries.append(address)
        base = self.identity['game_base']
        image = base <= address < base + reader.layout.IMAGE_SIZE
        code = any(at <= address < at + n for at, n in self.code_regions)
        if image:
            region_base, size = base, reader.layout.IMAGE_SIZE
        else:
            matches = [(at, n) for at, n in self.regions if at <= address < at + n]
            assert matches, f'query outside owned fixture: {address:#x}'
            region_base, size = max(matches, key=lambda pair: pair[1])
        result = {'base': region_base, 'size': size, 'state': 0x1000,
                  'type': 0x1000000 if image else 0x20000,
                  'protect': 0x20 if code else 4}
        if self.guard == address:
            result['protect'] |= 0x100
        if self.region_override:
            self.region_override(result, address)
        return result

    def read(self, address, size):
        self.reads.append((address, size))
        self.calls[address] = self.calls.get(address, 0) + 1
        if address == self.state_context + reader.layout.STATE_OFFSET:
            self.put(address, struct.pack('<I', self.state))
        if self.changed:
            self.changed(self, address, size, self.calls[address])
        try:
            raw = bytes(self.bytes[address + i] for i in range(size))
        except KeyError as error:
            raise AssertionError(f'unowned fixture read: {address:#x}+{size}') from error
        return raw[:-1] if self.short == address else raw

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *_):
        return False


def deps(memory, pids=None, resolve=None, validate=None):
    return {'fingerprints': lambda: {}, 'validate_identity': validate or (lambda *_: None),
            'game_processes': pids or (lambda: (123,)),
            'resolve_game': resolve or (lambda _: dict(memory.identity)),
            'Process': lambda _: memory}


class Tests(unittest.TestCase):
    def capture(self, memory, **options):
        return reader.capture(memory, memory.identity, clock=options.pop('clock', lambda: 0), **options)[0]

    def rejected(self, memory, reason, **options):
        with self.assertRaisesRegex(reader.CaptureError, reason) as caught:
            self.capture(memory, **options)
        return caught.exception.evidence

    def test_saved_ui_bytes_plus_explicit_synthetic_fields_map_only_ids(self):
        memory = Memory(); result = self.capture(memory)
        self.assertEqual(result['stat_id_label_mapping'], [
            {'row_index': 0, 'role': 'enemy_kills', 'label_key': 0xF68F08B2, 'stat_id': 0x13579BDF},
            {'row_index': 8, 'role': 'deaths', 'label_key': 0x32C9CF0D, 'stat_id': 0x2468ACE0}])
        self.assertEqual((result['active_read_calls'], result['active_read_bytes']), (58, 2888))
        self.assertEqual(len(memory.reads), 58)
        self.assertEqual(result['row_path_before'], result['row_path_after'])
        self.assertEqual(result['rows_before'], result['rows_after'])
        self.assertEqual(result['owner_before'], result['owner_after'])
        self.assertTrue(result['diagnostic_only'])
        for key in ('liveness_proven', 'server_ready', 'backend_ready', 'career_stats_ready',
                    'values_fresh', 'account_modified', 'native_written', 'native_called'):
            self.assertIs(result[key], False)
        self.assertNotIn('kills', result); self.assertNotIn('deaths', result)
        self.assertEqual(result['rows_after']['enemy_kills']['value_raw'], 123)
        self.assertNotIn((memory.row0 + 0x1390, 256), memory.reads)
        self.assertNotIn((memory.identity['game_base'] + reader.layout.DISPATCH_GLOBAL, 8), memory.reads)
        self.assertTrue(all(size <= 256 for _, size in memory.reads))

    def test_source_hashes_and_pin_bytes_are_real_saved_code(self):
        for source, (rva, expected) in zip(reader.SOURCES, reader.PINS):
            path = ROOT / source['path']; binary = path.read_bytes()
            self.assertEqual(hashlib.sha256(binary).hexdigest(), source['sha256'])
            meta = json.loads(path.with_suffix('.json').read_text('utf8'))
            ranges = [r for r in meta['ranges'] if r['rva'] <= rva and
                      rva + len(bytes.fromhex(expected)) <= r['rva'] + r['length']]
            self.assertEqual(len(ranges), 1)
            at = ranges[0]['binary_offset'] + rva - ranges[0]['rva']
            self.assertEqual(binary[at:at + len(bytes.fromhex(expected))].hex(), expected)

    def test_not_ship_stops_before_code_catalog_and_peer(self):
        memory = Memory(); memory.state = 2
        evidence = self.rejected(memory, 'NOT_SHIP')
        self.assertEqual((evidence['active_read_calls'], evidence['active_read_bytes']), (2, 12))

    def test_pin_failure_and_second_pin_drift_stop(self):
        memory = Memory(); address = memory.identity['game_base'] + reader.PINS[0][0]
        memory.put(address, bytes(5)); self.rejected(memory, 'CODE_PIN')
        memory = Memory()
        memory.changed = lambda m, at, n, call: m.put(at, bytes(n)) if at == address and call == 2 else None
        self.rejected(memory, 'CODE_PIN')

    def test_backref_and_constructor_rejected(self):
        memory = Memory(); memory.put(memory.armory + reader.BACKREF, struct.pack('<Q', memory.owner + 8))
        self.rejected(memory, 'BACKREF')
        memory = Memory(); memory.put(memory.armory + reader.BLOCK + reader.CONSTRUCTED, b'\0')
        self.rejected(memory, 'NOT_CONSTRUCTED')

    def test_filled_count_not_constructed_capacity(self):
        for count, reason in ((0, 'FILLED_COUNT'), (31, 'FILLED_COUNT'), (1, 'ROW8_NOT_FILLED'), (8, 'ROW8_NOT_FILLED')):
            with self.subTest(count=count):
                memory = Memory(); memory.put(memory.list + reader.FILLED_COUNT, struct.pack('<I', count))
                self.rejected(memory, reason)
                self.assertNotIn((memory.row0 + reader.layout.NEXT, 8), memory.reads)
        memory = Memory(); memory.put(memory.list + reader.FILLED_COUNT, struct.pack('<I', 9))
        self.assertEqual(self.capture(memory)['owner_before']['filled_count'], 9)

    def test_chain_is_next_with_independent_inline_array_crosscheck(self):
        memory = Memory(); memory.put(memory.list + reader.layout.CHILD, struct.pack('<Q', memory.row0 + 8))
        self.rejected(memory, 'INLINE_FIRST_ROW')
        memory = Memory(); memory.put(memory.row0 + reader.layout.NEXT, struct.pack('<Q', memory.row8))
        self.rejected(memory, 'NEXT_ARRAY_MISMATCH')
        memory = Memory(); memory.put(memory.row0 + reader.layout.NEXT, struct.pack('<Q', memory.row0))
        self.rejected(memory, 'NEXT_ARRAY_MISMATCH')

    def test_row_and_label_parent_context_kind_checked(self):
        for address_name, offset, value in (('row0', reader.layout.PARENT, 0),
                                           ('row8', reader.layout.CONTEXT, 0)):
            memory = Memory(); memory.put(getattr(memory, address_name) + offset, struct.pack('<Q', value))
            self.rejected(memory, 'WIDGET_OWNER')
        memory = Memory(); memory.put(memory.row8 + reader.TAG, struct.pack('<I', 1 | 8 << 18))
        self.rejected(memory, 'WIDGET_OWNER')
        memory = Memory(); memory.put(memory.row0 + reader.TAG + reader.layout.PARENT, struct.pack('<Q', memory.row8))
        self.rejected(memory, 'WIDGET_OWNER')

    def test_wrong_label_and_duplicate_metadata_id_rejected(self):
        memory = Memory(); memory.put(memory.row0 + reader.TAG + reader.layout.LABEL_START, struct.pack('<I', 0))
        self.rejected(memory, 'LABEL_MISMATCH')
        memory = Memory(); memory.put(memory.row8 + reader.META, struct.pack('<II', 0x13579BDF, 456))
        self.rejected(memory, 'STAT_ID_AMBIGUOUS')

    def test_before_after_full_header_metadata_peer_chain_changes_rejected(self):
        for mode in ('header', 'metadata', 'peer', 'chain', 'count', 'backref', 'catalog'):
            with self.subTest(mode=mode):
                memory = Memory()
                fields = {
                    'header': (memory.row0, lambda m, at: m.put(at + 4, b'\x01')),
                    'metadata': (memory.row8 + reader.META, lambda m, at: m.put(at + 4, struct.pack('<I', 457))),
                    'peer': (memory.local_user + reader.LOCAL_PEER, lambda m, at: m.put(at, struct.pack('<Q', 99))),
                    'chain': (memory.row0 + reader.layout.NEXT, lambda m, at: m.put(at, struct.pack('<Q', memory.row0))),
                    'count': (memory.list + reader.FILLED_COUNT, lambda m, at: m.put(at, struct.pack('<I', 29))),
                    'backref': (memory.armory + reader.BACKREF, lambda m, at: m.put(at, struct.pack('<Q', 0))),
                    'catalog': (memory.identity['game_base'] + reader.CATALOG, lambda m, at: m.put(at, struct.pack('<Q', 0))),
                }
                target, mutate = fields[mode]
                memory.changed = lambda m, at, n, call: mutate(m, at) if at == target and call == 2 else None
                evidence = self.rejected(memory, 'CAREER_CLOSED_')
                self.assertNotIn('stat_id_label_mapping', evidence)

    def test_guard_short_private_commit_and_region_boundary_fail_closed(self):
        for mode in ('guard', 'short', 'mapped', 'reserved', 'boundary', 'execute_heap'):
            with self.subTest(mode=mode):
                memory = Memory(); target = memory.row0
                if mode == 'guard': memory.guard = target
                elif mode == 'short': memory.short = target
                else:
                    def override(region, at):
                        if at != target: return
                        if mode == 'mapped': region['type'] = 0x40000
                        elif mode == 'reserved': region['state'] = 0x2000
                        elif mode == 'boundary': region['size'] = 255
                        else: region['protect'] = 0x20
                    memory.region_override = override
                evidence = self.rejected(memory, 'SHORT_READ' if mode == 'short' else 'UNREADABLE')
                self.assertLessEqual(evidence['active_read_calls'], reader.MAX_READS)
                self.assertLessEqual(evidence['active_read_bytes'], reader.MAX_BYTES)

    def test_executable_module_globals_readable_but_executable_heap_rejected(self):
        for protection in (0x20, 0x40, 0x80):
            with self.subTest(protection=protection):
                memory = Memory()
                def override(region, at):
                    if region['type'] == 0x1000000:
                        region['protect'] = protection
                memory.region_override = override
                result = self.capture(memory)
                self.assertEqual((result['active_read_calls'], result['active_read_bytes']), (58, 2888))
                memory = Memory()
                def reject_heap(region, at):
                    if at == memory.row0:
                        region['protect'] = protection
                memory.region_override = reject_heap
                self.rejected(memory, 'UNREADABLE')

    def test_whole_budget_and_soft_clock_include_query_and_read(self):
        memory = Memory(); budget = reader.Budget(memory, memory.identity, clock=lambda: 0)
        budget.total['reads'] = reader.MAX_READS
        with self.assertRaisesRegex(ValueError, 'TOTAL_BUDGET'): budget.read(memory.row0, 1)
        self.assertFalse(memory.queries)
        budget.total['reads'], budget.total['bytes'] = 0, reader.MAX_BYTES
        with self.assertRaisesRegex(ValueError, 'TOTAL_BUDGET'): budget.read(memory.row0, 1)
        ticks = iter((0, 0, 0, 1.01))
        memory = Memory(); evidence = self.rejected(memory, 'SOFT_BUDGET', clock=lambda: next(ticks))
        self.assertLessEqual(evidence['active_read_calls'], 1)
        now = [0.0]; memory = Memory()
        memory.changed = lambda *_: now.__setitem__(0, 1.01)
        evidence = self.rejected(memory, 'SOFT_BUDGET', clock=lambda: now[0])
        self.assertEqual(evidence['active_read_calls'], 1)

    def test_output_exists_rejected_before_dependencies(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(reader.layout, 'dependencies', side_effect=AssertionError('no dependencies')):
            with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'): reader.run(folder)

    def test_once_success_saves_raw_bin_offsets_and_diagnostic_status(self):
        memory = Memory()
        with tempfile.TemporaryDirectory() as parent:
            folder = Path(parent) / 'once'
            result = reader.run(folder, deps=deps(memory), clock=lambda: 0)
            self.assertEqual(memory.entered, 1)
            status = json.loads((folder / 'status.json').read_text())
            raw = (folder / 'drain.bin').read_bytes()
            self.assertEqual(len(raw), 2888)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), status['binary_sha256'])
            self.assertEqual(hashlib.sha256((folder / 'drain.json').read_bytes()).hexdigest(), status['json_sha256'])
            for record in result['read_records']:
                at = record['binary_offset']
                self.assertEqual(raw[at:at + record['received']].hex(), record['raw_hex'])
            self.assertEqual(status['status'], 'complete')
            self.assertIs(status['liveness_proven'], False)
            self.assertIs(status['server_ready'], False)

    def test_negative_result_is_saved_once_with_no_mapping(self):
        memory = Memory(); memory.put(memory.row8 + reader.TAG + reader.layout.LABEL_START, struct.pack('<I', 0))
        with tempfile.TemporaryDirectory() as parent:
            folder = Path(parent) / 'negative'
            with self.assertRaisesRegex(reader.CaptureError, 'LABEL_MISMATCH'):
                reader.run(folder, deps=deps(memory), clock=lambda: 0)
            self.assertEqual(memory.entered, 1)
            status = json.loads((folder / 'status.json').read_text())
            evidence = json.loads((folder / 'drain.json').read_text())
            self.assertEqual(status['status'], 'failed')
            self.assertNotIn('stat_id_label_mapping', evidence)
            self.assertTrue(evidence['read_records'])
            self.assertEqual(len((folder / 'drain.bin').read_bytes()), evidence['bytes_written'])

    def test_pid_build_path_change_or_late_soft_timeout_never_writes_complete(self):
        for mode in ('pid', 'identity', 'path', 'clock'):
            with self.subTest(mode=mode):
                memory = Memory(); calls = [0]; now = [0.0]
                def resolve(_):
                    calls[0] += 1
                    result = deepcopy(memory.identity)
                    if calls[0] == 2:
                        if mode == 'identity': result['game_base'] += 4096
                        elif mode == 'path': result['game_path'] = 'different.dll'
                        elif mode == 'clock': now[0] = 1.01
                    return result
                def pids(): return (124,) if mode == 'pid' and calls[0] == 2 else (123,)
                with tempfile.TemporaryDirectory() as parent:
                    folder = Path(parent) / 'stop'
                    with self.assertRaisesRegex(ValueError, 'MODULE_OR_PID_CHANGED|SOFT_BUDGET'):
                        reader.run(folder, deps=deps(memory, pids=pids, resolve=resolve), clock=lambda: now[0])
                    status = json.loads((folder / 'status.json').read_text())
                    evidence = json.loads((folder / 'drain.json').read_text())
                    self.assertEqual(status['status'], 'failed')
                    self.assertEqual(evidence['status'], 'failed')
                    self.assertNotIn('stat_id_label_mapping', evidence)

    def test_no_game_module_failure_no_retry_or_process_open(self):
        for mode in ('no_game', 'bad_build'):
            memory = Memory()
            def bad_validate(*_): raise ValueError('owned build rejected')
            with tempfile.TemporaryDirectory() as parent:
                with self.assertRaises(ValueError):
                    reader.run(Path(parent) / 'stop', deps=deps(memory,
                               pids=(lambda: ()) if mode == 'no_game' else None,
                               validate=bad_validate if mode == 'bad_build' else None), clock=lambda: 0)
                self.assertEqual(memory.entered, 0)
                self.assertFalse(memory.reads)


if __name__ == '__main__':
    unittest.main()
