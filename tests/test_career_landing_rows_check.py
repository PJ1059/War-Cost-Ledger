"""Saved real row layout in owned memory; no game access or UI operations."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

old = load('landing_saved_memory', ROOT / 'tests/test_career_hidden_cache_check.py')
checker = load('landing_checker', ROOT / 'tools/career-landing-rows-check.py')

def memory():
    m = old.Memory(alpha=0)
    base = m.identity['game_base']
    # Add only the proven VPM presenter fields to the isolated fixture.
    ui, user = 0x30000000, 0x31000000
    m.put(base + 0x347CE28, struct.pack('<Q', ui))
    m.put(base + 0x347CEF0, struct.pack('<Q', user))
    m.put(ui + 0x4288 + 12, struct.pack('<I', 5) + bytes(4) + struct.pack('<I', 5) + bytes(16) + struct.pack('<I', 1))
    m.put(user + 0xB398, struct.pack('<Q', 0x123456789ABCDEF0))
    ref = old.checker.reference(old.REFERENCE)
    filled_at = ref['owner_before']['list'] + 0x2F0F4
    m.put(filled_at, struct.pack('<I', 30))
    original_query = m.query
    def query(at):
        for start, size in [(ui + 0x4288 + 12, 32), (user + 0xB398, 8), (filled_at, 4)]:
            if start <= at < start + size:
                return {'base': start, 'size': size, 'state': 0x1000, 'type': 0x20000, 'protect': 4}
        return original_query(at)
    m.query = query
    return m

class Tests(unittest.TestCase):
    def test_hidden_rows_candidate_without_trusting_or_syncing(self):
        m = memory(); r = checker.capture(m, m.identity, clock=lambda: 0)
        self.assertEqual(r['status'], 'candidate_rows_unverified')
        self.assertEqual(r['rows_after']['enemy_kills']['value']['candidate_nonnegative32'], 351849)
        self.assertEqual(r['rows_after']['deaths']['value']['candidate_nonnegative32'], 4633)
        self.assertLessEqual(r['active_read_bytes'], 8192)
        self.assertLessEqual(r['active_read_calls'], 64)
        self.assertFalse(r['career_stats_ready'] or r['account_modified'] or r['native_called'])

    def test_empty_rows_are_observed_without_following_a_stale_pointer(self):
        m = memory(); ref = old.checker.reference(old.REFERENCE)
        at = ref['owner_before']['list'] + old.checker.private_target().layout.CHILD
        m.put(at, bytes(8))
        r = checker.capture(m, m.identity, clock=lambda: 0)
        self.assertEqual(r['status'], 'empty_rows')
        self.assertEqual(r['rows_after'], {})
        self.assertLess(r['active_read_calls'], 32)

    def test_detailed_page_is_the_wrong_diagnostic_condition(self):
        m = memory(); m.put(m.alpha_address, struct.pack('<f', 1))
        with self.assertRaisesRegex(ValueError, 'DETAIL_PAGE_VISIBLE'):
            checker.capture(m, m.identity, clock=lambda: 0)

    def test_preconstructed_slots_are_not_populated_totals(self):
        m = memory(); ref = old.checker.reference(old.REFERENCE)
        m.put(ref['owner_before']['list'] + 0x2F0F4, bytes(4))
        r = checker.capture(m, m.identity, clock=lambda: 0)
        self.assertEqual(r['status'], 'rows_not_filled')
        self.assertEqual(r['rows_after'], {})

    def test_other_presenter_is_refused(self):
        m = memory(); m.put(0x30000000 + 0x4288 + 12, struct.pack('<I', 0))
        with self.assertRaisesRegex(ValueError, 'ARMORY_NOT_ACTIVE'):
            checker.capture(m, m.identity, clock=lambda: 0)

    def test_module_change_prevents_success_artifact(self):
        m = memory(); deps = old.dependencies(m); calls = [0]
        def resolve(_):
            calls[0] += 1
            value = dict(m.identity)
            if calls[0] == 2: value['game_base'] += 4096
            return value
        deps['resolve_game'] = resolve
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'new'
            with self.assertRaisesRegex(ValueError, 'MODULE_CHANGED'):
                checker.run(out, deps=deps, clock=lambda: 0)
            self.assertFalse((out / 'landing-rows.json').exists())

if __name__ == '__main__': unittest.main()
