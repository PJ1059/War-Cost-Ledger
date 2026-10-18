"""External session lifecycle tests; all files/processes/clocks are fake."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
import struct
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('probe_session', ROOT / 'tools/probe_session.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class FakeWorld:
    def __init__(self):
        self.now = 0.0
        self.pids = ()
        self.process_checks = 0
        self.launches = 0

    def processes(self):
        self.process_checks += 1
        return self.pids

    def launch(self):
        self.launches += 1


class ProbeSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.world = FakeWorld()
        self.session = probe.Session(self.folder, self.world.processes, self.world.launch,
            lambda: self.world.now, lambda: 'fake-%d' % self.world.now, self.folder / 'performance_logs')
        self.store = self.folder / probe.STORE_NAME
        self.write(self.store, {'probe_enabled': False, 'last_mission': {'kills': 8}, 'other': [1, 2]})

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data), encoding='utf8')

    @staticmethod
    def read(path):
        return json.loads(path.read_text(encoding='utf8'))

    def ready(self):
        self.assertTrue(self.session.start())
        self.world.pids = (101,)
        self.world.now = 2
        self.session.tick()
        self.world.now = 32
        self.session.tick()
        self.assertIsNotNone(self.session.pending)

    def answer(self, error=None, stats=None):
        item = self.session.pending
        data = {'id': item['id'], 'mission': True,
            'stats': {'main': [], 'sources': []} if stats is None and error is None else stats,
            'error': error}
        if error is None and item['include_code']:
            data['code'] = [{'rva': 123, 'hex': 'AB'}]
        self.write(Path(item['path']), data)
        self.session.request_path.unlink(missing_ok=True)

    def test_waiting_enables_backs_up_and_launches_without_request(self):
        original = self.store.read_bytes()
        self.assertTrue(self.session.start())
        self.assertEqual(self.session.state, 'waiting')
        self.assertEqual(self.world.launches, 1)
        self.assertFalse(self.session.request_path.exists())
        self.assertTrue(self.read(self.store)['probe_enabled'])
        backups = list(self.folder.glob('*.bak.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(self.read(self.store)['last_mission'], {'kills': 8})
        index = self.read(self.session.index_path)
        self.assertEqual(index['state'], 'waiting')
        self.assertEqual(index['captures'], [])

    def test_initial_delay_then_baseline_and_30_second_shared_timer(self):
        self.assertTrue(self.session.start(False))
        self.world.pids = (101,)
        self.world.now = 2
        self.session.tick()
        self.world.now = 31
        self.session.tick()
        self.assertFalse(self.session.request_path.exists())
        self.world.now = 32
        self.session.tick()
        first = self.read(self.session.request_path)
        self.assertEqual(first['label'], 'baseline')
        self.assertTrue(first['include_code'])
        self.answer()
        self.world.now = 33
        self.session.tick()
        self.assertEqual(self.session.captures[0]['status'], 'saved')
        self.assertTrue(self.session.captures[0]['has_code'])
        self.world.now = 61
        self.session.tick()
        self.assertEqual(len(self.session.captures), 1)
        self.world.now = 62
        self.session.tick()
        second = self.read(self.session.request_path)
        self.assertEqual(second['label'], 'auto-02')
        self.assertFalse(second['include_code'])
        self.assertNotEqual(second['id'], first['id'])

    def test_pending_never_repeated_and_120_second_first_timeout(self):
        self.ready()
        original = self.session.request_path.read_bytes()
        self.world.now = 77
        self.session.tick()
        self.assertEqual(self.session.request_path.read_bytes(), original)
        self.assertEqual(len(self.session.captures), 1)
        self.world.now = 151
        self.session.tick()
        self.assertEqual(self.session.state, 'running')
        self.world.now = 152
        self.session.tick()
        self.assertEqual(self.session.state, 'error')
        self.assertIn('120 秒', self.session.last_error)
        self.assertFalse(self.session.request_path.exists())
        self.assertEqual(self.session.captures[0]['status'], 'error')
        self.world.now = 200
        self.session.tick()
        self.assertEqual(len(self.session.captures), 1)
        self.assertTrue(self.read(self.store)['probe_enabled'])

    def test_followup_times_out_at_45_seconds(self):
        self.ready()
        self.answer()
        self.world.now = 33
        self.session.tick()
        self.world.now = 62
        self.session.tick()
        self.world.now = 106
        self.session.tick()
        self.assertEqual(self.session.state, 'running')
        self.world.now = 107
        self.session.tick()
        self.assertEqual(self.session.state, 'error')
        self.assertIn('45 秒', self.session.last_error)

    def test_not_ready_can_retry_once_code_is_available(self):
        self.ready()
        self.answer('local player unavailable')
        self.world.now = 33
        self.session.tick()
        self.assertEqual(self.session.state, 'running')
        self.assertEqual(self.session.captures[0]['status'], 'error')
        self.world.now = 62
        self.session.tick()
        self.assertIsNone(self.session.pending)
        self.world.now = 63
        self.session.tick()
        self.assertEqual(self.session.pending['label'], 'baseline')
        self.assertTrue(self.session.pending['include_code'])
        self.answer()
        self.world.now = 64
        self.session.tick()
        self.assertEqual(self.session.captures[1]['status'], 'saved')
        index = self.read(self.session.index_path)
        self.assertEqual(len(index['captures']), 2)
        self.assertTrue(index['captures'][1]['has_code'])

    def test_unknown_error_stops_automatic(self):
        self.ready()
        self.answer('MAIN_CAPACITY_LIMIT_OR_INVALID')
        self.world.now = 33
        self.session.tick()
        self.assertEqual(self.session.state, 'error')
        self.assertIn('MAIN_CAPACITY_LIMIT_OR_INVALID', self.session.last_error)
        self.world.now = 63
        self.session.tick()
        self.assertEqual(len(self.session.captures), 1)

    def test_manual_label_while_idle_never_writes_running_store(self):
        self.write(self.store, {'probe_enabled': True, 'last_mission': {'kills': 17}})
        original = self.store.read_bytes()
        self.world.pids = (101,)
        self.assertTrue(self.session.capture('提供辅助装弹后'))
        self.assertEqual(self.store.read_bytes(), original)
        self.assertEqual(self.session.pending['label'], '提供辅助装弹后')
        self.assertEqual(len(self.session.pending['id']), 32)
        self.assertFalse(self.session.capture('重复'))
        self.assertEqual(len(self.session.captures), 1)
        self.answer()
        self.world.now = 1
        self.session.tick()
        self.assertEqual(self.read(self.session.index_path)['captures'][0]['status'], 'saved')

    def test_start_running_checks_enabled_without_store_writes(self):
        self.world.pids = (101,)
        original = self.store.read_bytes()
        self.assertFalse(self.session.start())
        self.assertEqual(self.store.read_bytes(), original)
        self.assertEqual(self.world.launches, 0)
        self.write(self.store, {'probe_enabled': True, 'last_mission': {'kills': 8}})
        original = self.store.read_bytes()
        self.assertTrue(self.session.start())
        self.assertEqual(self.session.state, 'running')
        self.assertEqual(self.store.read_bytes(), original)
        self.assertEqual(self.world.launches, 0)

    def test_stop_cancels_only_owned_request_and_waits_for_exit(self):
        self.ready()
        original = self.store.read_bytes()
        self.assertTrue(self.session.stop())
        self.assertFalse(self.session.request_path.exists())
        self.assertEqual(self.session.captures[0]['status'], 'cancelled')
        self.assertEqual(self.store.read_bytes(), original)
        self.write(self.store, {'probe_enabled': True, 'last_mission': {'kills': 200}, 'new': {'cost': 123}})
        self.world.pids = ()
        self.world.now = 34
        self.session.tick()
        latest = self.read(self.store)
        self.assertFalse(latest['probe_enabled'])
        self.assertEqual(latest['last_mission'], {'kills': 200})
        self.assertEqual(latest['new'], {'cost': 123})
        self.assertEqual(self.session.state, 'completed')
        self.assertFalse(self.session.enabled)

    def test_stop_preserves_foreign_request_and_store(self):
        self.ready()
        foreign = {'id': 'f' * 32, 'label': 'other', 'include_code': False}
        self.write(self.session.request_path, foreign)
        original = self.store.read_bytes()
        self.assertTrue(self.session.stop())
        self.assertEqual(self.read(self.session.request_path), foreign)
        self.assertEqual(self.store.read_bytes(), original)

    def test_pending_before_start_is_never_overwritten(self):
        foreign = {'id': 'f' * 32, 'label': 'other'}
        self.write(self.session.request_path, foreign)
        original = self.store.read_bytes()
        self.assertFalse(self.session.start())
        self.assertEqual(self.read(self.session.request_path), foreign)
        self.assertEqual(self.store.read_bytes(), original)
        self.assertEqual(self.world.launches, 0)

    def test_wait_timeout_disables_preserves_data(self):
        self.assertTrue(self.session.start(False))
        self.world.now = 300
        self.session.tick()
        self.assertEqual(self.session.state, 'error')
        self.assertFalse(self.read(self.store)['probe_enabled'])
        self.assertEqual(self.read(self.store)['last_mission'], {'kills': 8})
        self.assertFalse(self.session.request_path.exists())

    def test_process_poll_is_throttled_to_two_seconds(self):
        before = self.world.process_checks
        self.session.tick()
        self.assertEqual(self.world.process_checks - before, 1)
        for now in [0.25, 0.5, 1, 1.99]:
            self.world.now = now
            self.session.tick()
        self.assertEqual(self.world.process_checks - before, 1)
        self.world.now = 2
        self.session.tick()
        self.assertEqual(self.world.process_checks - before, 2)

    def test_manual_and_auto_share_31_capture_cap(self):
        self.write(self.store, {'probe_enabled': True})
        self.world.pids = (101,)
        self.assertTrue(self.session.start(False))
        # Manual captures during warm-up all count against the same budget.
        for index in range(probe.MAX_CAPTURES):
            self.assertTrue(self.session.capture('manual-%02d' % index))
            self.answer()
            self.session.tick()
        self.assertEqual(len(self.session.captures), 31)
        self.assertFalse(self.session.capture('too many'))
        self.session.tick()
        self.assertEqual(self.session.state, 'completed')
        self.assertFalse(self.session.request_path.exists())
        self.assertEqual(len(self.read(self.session.index_path)['captures']), 31)

    def test_delayed_tick_does_not_catch_up_past_15_minutes(self):
        self.ready()
        self.answer()
        self.world.now = 1000
        self.session.tick()
        self.assertEqual(self.session.state, 'completed')
        self.assertEqual(len(self.session.captures), 1)
        self.assertFalse(self.session.request_path.exists())

    def test_bad_label_and_duplicate_start_keep_healthy_session(self):
        self.ready()
        original = self.session.request_path.read_bytes()
        self.assertFalse(self.session.start())
        self.assertEqual(self.session.request_path.read_bytes(), original)
        self.assertEqual(self.session.state, 'running')
        self.answer()
        self.world.now = 33
        self.session.tick()
        self.assertFalse(self.session.capture('中' * 54))
        self.assertEqual(self.session.state, 'running')
        self.assertIsNone(self.session.pending)

    def test_malformed_result_id_stops_and_cancels_own_request(self):
        self.ready()
        self.write(Path(self.session.pending['path']), {'id': 'wrong', 'stats': {}})
        self.world.now = 33
        self.session.tick()
        self.assertEqual(self.session.state, 'error')
        self.assertIn('id 不匹配', self.session.last_error)
        self.assertFalse(self.session.request_path.exists())
        self.assertEqual(self.session.captures[0]['status'], 'error')

    def test_normal_game_exit_cancels_pending_and_preserves_latest_ledger(self):
        self.ready()
        self.write(self.store, {'probe_enabled': True, 'last_mission': {'kills': 71}, 'new': 'kept'})
        self.world.pids = ()
        self.world.now = 34
        self.session.tick()
        self.assertEqual(self.session.state, 'completed')
        self.assertFalse(self.session.request_path.exists())
        self.assertFalse(self.read(self.store)['probe_enabled'])
        self.assertEqual(self.read(self.store)['new'], 'kept')

    def test_binary_request_and_external_decode_preserve_json_path(self):
        self.ready()
        request = self.read(self.session.request_path)
        self.assertEqual(request['format'], 'binary')
        metadata = {'version': '0.3.1', 'id': request['id'], 'label': request['label'],
            'player_entity': 42, 'score_index': 0, 'capacity': 1, 'empty': 0xFFFFFFFF,
            'mission': True, 'build': 25480438, 'time': 123,
            'code_ranges': [{'rva': 1, 'size': 2}, {'rva': 2, 'size': 3, 'error': 'unreadable'}]}
        segments = [json.dumps(metadata).encode('utf8'), struct.pack('<IifB7x', 22, 7, 1.5, 1), b'', b'AB', b'']
        binary = struct.pack('<8s5I', b'HD2STAT1', *(len(item) for item in segments)) + b''.join(segments)
        path = Path(self.session.pending['path'])
        path.with_suffix('.bin').write_bytes(binary)
        self.world.now = 33
        self.session.tick()
        response = self.read(path)
        self.assertEqual(response['stats']['main'][0]['i32'], 7)
        self.assertEqual(response['stats']['main'][0]['f32'], 1.5)
        self.assertEqual(response['code'][0]['hex'], '4142')
        self.assertEqual(response['code'][1]['error'], 'unreadable')
        item = self.session.captures[0]
        self.assertEqual(item['status'], 'saved')
        self.assertEqual(item['binary_path'], str(path.with_suffix('.bin')))
        self.assertGreaterEqual(item['external_decode_ms'], 0)
        self.assertGreaterEqual(item['external_json_ms'], 0)
        self.assertEqual(item['path'], str(path))

    def test_binary_wrong_id_does_not_publish_json(self):
        self.ready()
        metadata = {'id': 'f' * 32, 'player_entity': 42, 'score_index': 0, 'capacity': 0, 'empty': 0xFFFFFFFF}
        segments = [json.dumps(metadata).encode('utf8'), b'', b'', b'', b'']
        binary = struct.pack('<8s5I', b'HD2STAT1', *(len(item) for item in segments)) + b''.join(segments)
        path = Path(self.session.pending['path'])
        path.with_suffix('.bin').write_bytes(binary)
        self.world.now = 33
        self.session.tick()
        self.assertEqual(self.session.state, 'error')
        self.assertFalse(path.exists())

    def test_valid_full_binary_can_expand_past_one_mib_outside_game(self):
        self.ready()
        item = self.session.pending
        metadata = {'id': item['id'], 'label': item['label'], 'player_entity': 42,
            'score_index': 0, 'capacity': 4096, 'empty': 0xFFFFFFFF}
        main = b''.join(struct.pack('<IifB7x', key + 1, key, key / 8, key % 2) for key in range(4096))
        sources = bytearray(64 * 328)
        for block in range(64):
            struct.pack_into('<II', sources, block * 328, block + 1, 0x01234567)
            for slot in range(16):
                struct.pack_into('<IifB7x', sources, block * 328 + 8 + slot * 20, slot + 1, slot, slot / 2, 0)
        segments = [json.dumps(metadata).encode('utf8'), main, sources, b'', b'']
        binary = struct.pack('<8s5I', b'HD2STAT1', *(len(segment) for segment in segments)) + b''.join(segments)
        path = Path(item['path'])
        path.with_suffix('.bin').write_bytes(binary)
        self.world.now = 33
        self.session.tick()
        self.assertEqual(item['status'], 'saved')
        self.assertEqual(len(self.read(path)['stats']['main']), 4096)
        self.assertGreater(path.stat().st_size, 1048576)

    def test_performance_index_references_only_matching_session_or_pid(self):
        self.session._wall_clock = lambda: '2026-10-09T13:00:00+00:00'
        logs = self.session.performance_folder
        logs.mkdir()
        unrelated = logs / 'HD2Performance-20261008T120000Z-999-1.log'
        matching_pid = logs / 'HD2Performance-20261009T120000Z-101-1.log'
        matching_time = logs / 'HD2Performance-20261009T130001Z-222-1.log'
        unknown_format = logs / 'HD2Performance-other.log'
        for log in [unrelated, matching_pid, matching_time, unknown_format]:
            log.write_text('existing recorder', encoding='utf8')
        self.ready()
        self.session.stop()
        references = self.read(self.session.index_path)['performance_logs']
        self.assertEqual({item['path'] for item in references}, {str(matching_pid), str(matching_time)})
        self.assertEqual(len(list(logs.iterdir())), 4)
        self.assertTrue(all(item['size'] == len('existing recorder') for item in references))
        self.assertEqual(self.read(self.session.index_path)['ended_at'], '2026-10-09T13:00:00+00:00')


if __name__ == '__main__':
    unittest.main(verbosity=2)
