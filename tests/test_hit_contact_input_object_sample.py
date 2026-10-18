"""One finite contact object owned group, never executes previous suites."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import test_hit_world_update_r14_remainder_capture as previous

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_contact_input_sample', ROOT / 'tools/hit-contact-input-object-sample.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
Clock = previous.Clock
ROW = struct.pack('<QQQQ', 0, 0xFFFF800000000000, 0x1234, 0xFFFFFFFFFFFFFFFF)
RESULTS = []


class Memory(previous.Memory):
    def __init__(self, count=1, changed_payload=False, noncanonical=False,
                 changed_base=False, changed_source=False):
        super().__init__()
        self.count, self.changed_payload = count, changed_payload
        self.noncanonical, self.changed_base = noncanonical, changed_base
        self.changed_caller_source = changed_source
        self.base = self.context  # The original phase gate shares Game+3326340.
        self.contact = self.base + reader.CONTACT_OFFSET
        self.source_reads, self.global_reads, self.object_reads = [], [], []
        self.block_reads = 0

    def query(self, address):
        allowed = (self.contact + reader.ENABLE_OFFSET, self.contact + reader.BLOCK_OFFSET)
        if address in allowed:
            self.queries.append(address)
            if self.clock:
                self.clock.value += self.delay
            return {'base': self.contact, 'size': 0x100000, 'state': 0x1000,
                    'type': 0x20000, 'protect': 4}
        if self.contact <= address < self.contact + 0x100000:
            raise AssertionError('No row reference, pool, Actor, or expanded object query')
        return super().query(address)

    def read(self, address, size):
        rva = address - self.game
        if rva == reader.SOURCE_RVA or rva == reader.GLOBAL_RVA or address in (
                self.contact + reader.ENABLE_OFFSET, self.contact + reader.BLOCK_OFFSET):
            self.reads.append((address, size))
            if self.clock:
                self.clock.value += self.delay
            if rva == reader.SOURCE_RVA:
                assert size == 9852
                self.source_reads.append((rva, size))
                raw = bytearray(reader.FULL_PIN)
                if self.changed_caller_source and len(self.source_reads) > 1:
                    raw[-1] ^= 1
                return bytes(raw)
            if rva == reader.GLOBAL_RVA:
                assert size == 8
                self.global_reads.append((rva, size))
                value = 0 if self.noncanonical and len(self.global_reads) == 2 else self.base
                if self.changed_base and len(self.global_reads) == 3:
                    value += 0x1000
                return struct.pack('<Q', value)
            offset = address - self.contact
            self.object_reads.append((offset, size))
            if offset == reader.ENABLE_OFFSET:
                assert size == 1
                return b'\x01'
            assert (offset, size) == (reader.BLOCK_OFFSET, 36)
            self.block_reads += 1
            changed = self.changed_payload and self.block_reads > 1
            raw_row = ROW[:-1] + bytes((ROW[-1] ^ 1,)) if changed else ROW
            return struct.pack('<I', self.count + (1 if changed else 0)) + raw_row
        if self.contact <= address < self.contact + 0x100000:
            raise AssertionError('No expanded object read or row reference following')
        return super().read(address, size)


class Scenario(previous.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class ContactInputSampleTests(unittest.TestCase):
    def test_fixed_raw_samples_count_payload_canonical_base_and_source(self):
        self.assertEqual(len(reader.FULL_PIN), 9852)
        self.assertEqual((reader.SOURCE_RVA, reader.GLOBAL_RVA, reader.CONTACT_OFFSET),
                         (0xAB5000, 0x3326340, 0x44F7E30))
        for name, options, reason in (
                ('max_count_fixed_scope_raw_only', {'count': 0xFFFFFFFF}, None),
                ('zero_count_not_a_hit', {'count': 0}, None),
                ('mutable_payload_retained', {'changed_payload': True}, None),
                ('noncanonical_base_no_object_read', {'noncanonical': True}, 'NONCANONICAL_PROVEN_BASE'),
                ('base_post_changed_no_bin', {'changed_base': True}, 'BASE_OR_CALLER_SOURCE_CHANGED'),
                ('caller_pin_post_changed_no_bin', {'changed_source': True}, 'BASE_OR_CALLER_SOURCE_CHANGED')):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**options), Path(parent) / 'capture'
                if reason:
                    with self.assertRaisesRegex(ValueError, reason):
                        reader.run(folder, scenario.dependencies(), Clock())
                    self.assertEqual(list(folder.glob('*.bin')), [])
                    meta = json.loads((folder / 'callsite.incomplete.json').read_text('utf8'))
                    self.assertFalse(meta['partial_binary_saved'])
                    if name == 'noncanonical_base_no_object_read':
                        self.assertEqual(scenario.memory.object_reads, [])
                        self.assertEqual(meta['object_range_queries'], [])
                    else:
                        self.assertEqual(scenario.memory.object_reads,
                            [(reader.ENABLE_OFFSET, 1), (reader.BLOCK_OFFSET, 36)] * 2)
                    RESULTS.append({'case': name, 'status': 'PASS', 'error': meta['error'],
                        'object_reads': scenario.memory.object_reads, 'binary_saved': False,
                        'budget': meta['budget']})
                else:
                    status = reader.run(folder, scenario.dependencies(), Clock())
                    meta = json.loads(Path(status['json_path']).read_text('utf8'))
                    raw = Path(status['binary_path']).read_bytes()
                    count = scenario.memory.count
                    first = b'\x01' + struct.pack('<I', count) + ROW
                    second = (b'\x01' + struct.pack('<I', count + 1) + ROW[:-1] + bytes((ROW[-1] ^ 1,))
                              if scenario.memory.changed_payload else first)
                    self.assertEqual(raw, first + second)
                    self.assertEqual(len(raw), 74)
                    self.assertEqual(meta['object_payload_identical'], first == second)
                    self.assertEqual(scenario.memory.object_reads,
                        [(reader.ENABLE_OFFSET, 1), (reader.BLOCK_OFFSET, 36)] * 2)
                    self.assertEqual(scenario.memory.source_reads, [(reader.SOURCE_RVA, 9852)] * 2)
                    # Object before/after plus original phase before/after use the same global.
                    self.assertEqual(scenario.memory.global_reads, [(reader.GLOBAL_RVA, 8)] * 4)
                    self.assertEqual([(row['object_offset'], row['length'], row['binary_offset'])
                        for row in meta['ranges']], [(0x28, 1, 0), (0xE7040, 36, 1),
                                                   (0x28, 1, 37), (0xE7040, 36, 38)])
                    self.assertTrue(meta['full_9852_source_pin_before_after_match'])
                    self.assertTrue(meta['proven_global_base_before_after_match'])
                    self.assertTrue(meta['object_ranges_readable_and_canonical'])
                    for sample in meta['samples']:
                        self.assertFalse(sample['first_row_interpreted_as_hit'])
                        self.assertEqual(sample['first_row_status'], 'count_zero_raw_only'
                            if sample['count_u32'] == 0 else 'semantics_unproven_raw_only')
                    for key in ('samples_atomic', 'callback_relative_timing_proven', 'capacity_proven',
                                'hit_producer_proven', 'classification_ready', 'contract_ready',
                                'object_type_or_owner_proven', 'native_called', 'native_written'):
                        self.assertFalse(meta[key])
                    self.assertEqual((meta['row_refs_followed'], meta['Actor_pool_reads']), (0, 0))
                    self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
                    self.assertEqual(meta['budget']['query_calls'], len(scenario.memory.queries))
                    self.assertEqual(meta['budget']['bytes_requested'], sum(n for _, n in scenario.memory.reads))
                    self.assertLessEqual(meta['budget']['read_calls'], 32)
                    self.assertLessEqual(meta['budget']['query_calls'], 32)
                    self.assertLessEqual(meta['budget']['bytes_requested'], 32768)
                    RESULTS.append({'case': name, 'status': 'PASS', 'ranges': meta['ranges'],
                        'samples': meta['samples'], 'object_payload_identical': meta['object_payload_identical'],
                        'object_reads': scenario.memory.object_reads, 'budget': meta['budget'],
                        'capacity_proven': False, 'row_refs_followed': 0, 'Actor_pool_reads': 0})
                self.assertTrue(scenario.memory.closed)


if __name__ == '__main__':
    unittest.main()
