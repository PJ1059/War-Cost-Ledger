"""Offline owned DATA fixtures. Never instantiate a Windows Process adapter."""
import json
from pathlib import Path
import struct
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fire_death_snapshot as snapshot


class Memory:
    base, manager, user = 0x180000000, 0x200000000, 0x210000000
    records, ext, pointers, descriptors = 0x220000000, 0x230000000, 0x240000000, 0x250000000
    peer = 0xFEDCBA9876543210  # Above IEEE754 exact-integer range, kept as u64.
    identity = {'game_base': base, 'game_size': 74727424,
                'game_path': 'fixture.dll', 'exe_path': 'fixture.exe'}

    def __init__(self, count=64):
        self.reads, self.queries, self.counts = [], [], {}
        self.short, self.guard, self.mutate = False, False, None
        self.regions = {}
        header = bytearray(snapshot.H_HEADER_SIZE)
        struct.pack_into('<I', header, 0, 4096)
        struct.pack_into('<II', header, 0x10, count, count)
        struct.pack_into('<Q', header, 0x38, self.pointers)
        struct.pack_into('<Q', header, 0x48, self.records)
        struct.pack_into('<Q', header, 0x50, self.ext)
        self.regions[self.base + snapshot.H_GLOBAL] = struct.pack('<Q', self.manager)
        self.regions[self.manager + snapshot.H_HEADER] = header
        self.regions[self.base + snapshot.LOCAL_USER] = struct.pack('<Q', self.user)
        self.regions[self.user + snapshot.LOCAL_PEER] = struct.pack('<Q', self.peer)
        records, ext, pointers = bytearray(count * snapshot.STRIDE), bytearray(count * snapshot.EXT_STRIDE), bytearray(count * 8)
        for index in range(count):
            struct.pack_into('<Q', records, index * snapshot.STRIDE + 0x38, self.peer)
            struct.pack_into('<I', records, index * snapshot.STRIDE + 0x19C, 2)
            struct.pack_into('<II', ext, index * snapshot.EXT_STRIDE, 2, 1)
            struct.pack_into('<I', ext, index * snapshot.EXT_STRIDE + 12, 2)
            ptr = self.descriptors + index * 0x100
            struct.pack_into('<Q', pointers, index * 8, ptr)
            self.regions[ptr] = bytearray(struct.pack('<QIIII', 0x1122334455667788, 100 + index,
                                                     200 + index, 300 + index, 1))
        self.regions[self.records], self.regions[self.ext], self.regions[self.pointers] = records, ext, pointers

    def query(self, address):
        self.queries.append(address)
        for start, data in self.regions.items():
            if start <= address < start + len(data):
                return {'base': start, 'size': len(data), 'protect': 0x104 if self.guard else 4,
                        'state': 0x1000, 'type': 0x20000}
        raise AssertionError('Query outside owned fixture')

    def read(self, address, size):
        self.reads.append((address, size))
        self.counts[address] = self.counts.get(address, 0) + 1
        for start, data in self.regions.items():
            if start <= address and address + size <= start + len(data):
                raw = bytes(data[address - start:address - start + size])
                if self.mutate is not None:
                    raw = self.mutate(address, size, self.counts[address], raw)
                return raw[:-1] if self.short else raw
        raise AssertionError('Read outside owned fixture')


class SnapshotTests(unittest.TestCase):
    def test_maximum_bound_single_arrays_u64_peer_no_backfill(self):
        memory = Memory()
        raw, meta = snapshot.capture(memory, memory.identity)
        self.assertEqual(len(raw), 32224)
        self.assertEqual(meta['bytes_planned_max'], 32224)
        self.assertEqual(sum(size for _, size in memory.reads), len(raw))
        self.assertEqual(meta['candidate_count'], 16)
        self.assertEqual(meta['eligible_local_creditor_deaths_first64'], 64)
        self.assertTrue(meta['header_identity_stable'])
        self.assertFalse(meta['atomic'])
        self.assertFalse(meta['updates_ledger'])
        self.assertFalse(meta['corpse_backfill'])
        self.assertEqual(meta['local_peer'], 'FEDCBA9876543210')
        self.assertTrue(all(c['stable'] for c in meta['candidates']))
        self.assertTrue(all(not c['killer_attribution_proven'] for c in meta['candidates']))
        self.assertEqual([n for addr, n in memory.reads if addr == memory.records], [28160])
        for chunk in meta['chunks']:
            self.assertEqual(len(raw[chunk['binary_offset']:chunk['binary_offset'] + chunk['length']]), chunk['length'])
            self.assertGreaterEqual(chunk['read_ms'], 0)
        json.dumps(meta)

    def test_budget_and_pid_reject_before_any_query(self):
        for options in ({'pid': 1}, {'budget': 32223}, {'budget': 65537}):
            memory = Memory()
            with self.assertRaises(ValueError):
                snapshot.capture(memory, memory.identity, **options)
            self.assertEqual(memory.reads, [])
            self.assertEqual(memory.queries, [])

    def test_guard_and_short_read_stop_no_retry(self):
        for field, error in (('guard', 'REGION_UNREADABLE'), ('short', 'SHORT_READ')):
            memory = Memory(); setattr(memory, field, True)
            with self.assertRaisesRegex(ValueError, error):
                snapshot.capture(memory, memory.identity)
            self.assertLessEqual(len(memory.reads), 1)

    def test_empty_header_no_array_reads(self):
        memory = Memory(0)
        raw, meta = snapshot.capture(memory, memory.identity)
        self.assertEqual(len(raw), 224)
        self.assertEqual(meta['candidate_count'], 0)
        self.assertTrue(meta['header_identity_stable'])

    def test_larger_scene_stays_first64_and_does_not_expand(self):
        memory = Memory(70)
        raw, meta = snapshot.capture(memory, memory.identity)
        self.assertEqual(meta['header']['live'], 70)
        self.assertEqual(meta['sampled_record_count'], 64)
        self.assertEqual(meta['eligible_local_creditor_deaths_first64'], 64)
        self.assertEqual(len(raw), 32224)
        self.assertTrue(all(c['index'] < 64 for c in meta['candidates']))

    def test_header_bounds_reject_before_arrays(self):
        memory = Memory()
        struct.pack_into('<I', memory.regions[memory.manager + snapshot.H_HEADER], 0x14, 65)
        with self.assertRaisesRegex(ValueError, 'HEADER_BOUNDS'):
            snapshot.capture(memory, memory.identity)
        self.assertEqual(len(memory.reads), 2)

    def test_nonlocal_and_nonterminal_do_not_become_candidates(self):
        memory = Memory(3)
        struct.pack_into('<Q', memory.regions[memory.records], 0x38, 0)
        struct.pack_into('<Q', memory.regions[memory.records], snapshot.STRIDE + 0x38, 1)
        struct.pack_into('<I', memory.regions[memory.records], 2 * snapshot.STRIDE + 0x19C, 1)
        _, meta = snapshot.capture(memory, memory.identity)
        self.assertEqual(meta['candidate_count'], 0)

    def test_each_candidate_field_mismatch_mark_unstable_not_counted(self):
        for field in ('life', 'creditor', 'pointer', 'ext', 'descriptor'):
            memory = Memory(1)
            address = {'life': memory.records + 0x19C, 'creditor': memory.records + 0x38,
                       'pointer': memory.pointers, 'ext': memory.ext,
                       'descriptor': memory.descriptors}[field]
            minimum = 2 if field in ('pointer', 'ext', 'descriptor') else 1
            def mutate(a, size, count, raw):
                return bytes([raw[0] ^ 1]) + raw[1:] if a == address and count >= minimum else raw
            memory.mutate = mutate
            _, meta = snapshot.capture(memory, memory.identity)
            self.assertFalse(meta['candidates'][0]['stable'])

    def test_global_header_peer_or_pointer_change_marks_all_unstable(self):
        for address in (Memory.base + snapshot.H_GLOBAL, Memory.manager + snapshot.H_HEADER,
                        Memory.base + snapshot.LOCAL_USER, Memory.user + snapshot.LOCAL_PEER):
            memory = Memory(1)
            memory.mutate = lambda a, size, count, raw: bytes([raw[0] ^ 1]) + raw[1:] if a == address and count == 2 else raw
            _, meta = snapshot.capture(memory, memory.identity)
            self.assertFalse(meta['header_identity_stable'])
            self.assertFalse(meta['candidates'][0]['stable'])

    def test_identity_contract_rejects_different_pid_module_or_base(self):
        expected = Memory.identity
        snapshot.validate_identity(snapshot.FIXED_PID, expected, expected)
        for pid, actual in ((1, expected), (snapshot.FIXED_PID, dict(expected, game_size=1)),
                            (snapshot.FIXED_PID, dict(expected, game_base=1))):
            with self.assertRaises(ValueError):
                snapshot.validate_identity(pid, actual, expected)


if __name__ == '__main__':
    unittest.main()
