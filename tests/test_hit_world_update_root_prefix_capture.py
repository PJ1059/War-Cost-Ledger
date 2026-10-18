"""One focused owned 84-byte root-prefix group; never runs previous suites."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_hit_world_update_contact_callsite_hint_capture as previous

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'owned_world_root_prefix', ROOT / 'tools/hit-world-update-root-prefix-capture.py')
prefix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prefix)
SOURCE_CHAIN = prefix.validate_packet()['unwind_chain']
METADATA = {node[key]['rva']: bytes.fromhex(node[key]['raw_hex'])
            for node in SOURCE_CHAIN for key in ('header', 'chain_entry') if key in node}
ROOT_PATTERN = bytes((index * 17 + 3) & 255 for index in range(84))
RESULTS = []


class Memory(previous.Memory):
    def __init__(self, wrong_unwind=False, changed_prefix=False):
        super().__init__()
        self.wrong_unwind, self.changed_prefix = wrong_unwind, changed_prefix
        self.root_reads, self.unwind_reads = [], []

    def query(self, address):
        if self.game + prefix.ROOT_BEGIN <= address < self.game + prefix.ROOT_END:
            self.queries.append(address)
            if self.clock:
                self.clock.value += self.delay
            return {'base': self.game, 'size': prefix.v1.frozen.IMAGE_SIZE,
                    'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
        return super().query(address)

    def read(self, address, size):
        rva = address - self.game
        if rva in METADATA or rva == prefix.ROOT_BEGIN:
            self.reads.append((address, size))
            if self.clock:
                self.clock.value += self.delay
            if rva in METADATA:
                raw = bytearray(METADATA[rva])
                assert size == len(raw)
                if self.wrong_unwind and rva == SOURCE_CHAIN[0]['header']['rva']:
                    raw[3] ^= 1
                self.unwind_reads.append({'rva': rva, 'length': size, 'raw_hex': bytes(raw).hex()})
                return bytes(raw)
            assert size == 84
            self.root_reads.append((rva, size))
            raw = bytearray(ROOT_PATTERN)
            if self.changed_prefix and len(self.root_reads) > 1:
                raw[-1] ^= 1
            return bytes(raw)
        if (prefix.v1.frozen.CODE_BEGIN <= rva < prefix.v1.frozen.CODE_END
                and (rva, size) != (prefix.v1.PIN_RVA, 12)):
            raise AssertionError('No child code, gap, callee, or partial ancestor read')
        return super().read(address, size)


class Scenario(previous.previous.fixture.Scenario):
    def __init__(self, **options):
        super().__init__()
        self.memory = Memory(**options)


class RootPrefixTests(unittest.TestCase):
    def test_fresh_four_node_chain_root84_post_change_and_packet_sha(self):
        self.assertEqual((prefix.ROOT_BEGIN, prefix.ROOT_END), (0xAB5000, 0xAB5054))
        self.assertEqual(len(SOURCE_CHAIN), 4)
        self.assertEqual(len(METADATA), 7)
        self.assertEqual(sum(len(raw) for raw in METADATA.values()), 52)
        for name, options, reason in (
                ('correct_chain', {}, None),
                ('wrong_fresh_unwind', {'wrong_unwind': True}, 'UNWIND'),
                ('changed_root84_after', {'changed_prefix': True}, 'CODE_CHANGED_DURING_CAPTURE'),
                ('packet_source_sha', {}, 'COMPLETE_PACKET_CHANGED')):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as parent:
                scenario, folder = Scenario(**options), Path(parent) / 'capture'
                clock = previous.previous.fixture.Clock()
                if name == 'packet_source_sha':
                    with patch.object(prefix, 'PACKET_JSON_SHA', '0' * 64):
                        with self.assertRaisesRegex(ValueError, reason):
                            prefix.run(folder, scenario.dependencies(), clock)
                elif reason:
                    with self.assertRaisesRegex(ValueError, reason):
                        prefix.run(folder, scenario.dependencies(), clock)
                else:
                    status = prefix.run(folder, scenario.dependencies(), clock)
                    meta = json.loads(Path(status['json_path']).read_text('utf8'))
                    raw = Path(status['binary_path']).read_bytes()
                    self.assertEqual(raw, ROOT_PATTERN)
                    self.assertEqual(meta['code_bytes'], 84)
                    self.assertEqual(meta['child_code_bytes'], 0)
                    self.assertEqual(meta['unwind_chain'], SOURCE_CHAIN)
                    self.assertTrue(meta['fresh_unwind_matches_complete_source'])
                    self.assertTrue(meta['root_prefix_code_before_after_match'])
                    self.assertTrue(meta['fixed_record_verified_before_after'])
                    self.assertFalse(meta['binary_search_performed'])
                    self.assertEqual(scenario.memory.hint_reads, 2)
                    self.assertEqual(scenario.memory.root_reads,
                                     [(prefix.ROOT_BEGIN, 84), (prefix.ROOT_BEGIN, 84)])
                    self.assertEqual(scenario.memory.payload_reads, [])
                    self.assertEqual([(row['rva'], row['length'], row['binary_offset'])
                                      for row in meta['ranges']],
                                     [(0xAB5000, 44, 0), (0xAB502C, 27, 44), (0xAB5047, 13, 71)])
                    self.assertEqual({row['rva']: bytes.fromhex(row['raw_hex'])
                                      for row in scenario.memory.unwind_reads}, METADATA)
                    self.assertEqual(len(scenario.memory.unwind_reads), 7)
                    self.assertEqual(meta['budget']['read_calls'], len(scenario.memory.reads))
                    self.assertEqual(meta['budget']['query_calls'], len(scenario.memory.queries))
                    self.assertEqual(meta['budget']['bytes_requested'], sum(n for _, n in scenario.memory.reads))
                    self.assertLessEqual(meta['budget']['read_calls'], 32)
                    self.assertLessEqual(meta['budget']['query_calls'], 32)
                    self.assertLessEqual(meta['budget']['bytes_requested'], 24576)
                    for key in ('r14_initial_definition_proven', 'root_prefix_unchanged_at_call_proven',
                                'instruction_boundary_verified', 'registered_callback_proven',
                                'native_called', 'native_written'):
                        self.assertFalse(meta[key])
                    self.assertTrue(scenario.memory.closed)
                    RESULTS.append({'case': name, 'status': 'PASS', 'ranges': meta['ranges'],
                        'code_bytes': len(raw), 'child_code_bytes': meta['child_code_bytes'],
                        'root_reads': scenario.memory.root_reads, 'unwind_reads': scenario.memory.unwind_reads,
                        'hint_record_reads': scenario.memory.hint_reads, 'budget': meta['budget'],
                        'synthetic_root_sha256': hashlib.sha256(raw).hexdigest()})
                    continue
                self.assertEqual(list(folder.glob('*.bin')), [])
                meta = json.loads((folder / 'callsite.incomplete.json').read_text('utf8'))
                self.assertFalse(meta['complete'])
                self.assertFalse(meta['partial_binary_saved'])
                self.assertEqual(scenario.memory.payload_reads, [])
                if name == 'packet_source_sha':
                    self.assertEqual(scenario.opens, 0)
                    self.assertEqual(scenario.memory.reads, [])
                else:
                    self.assertTrue(scenario.memory.closed)
                    self.assertEqual(scenario.memory.root_reads, [] if name == 'wrong_fresh_unwind'
                                     else [(prefix.ROOT_BEGIN, 84), (prefix.ROOT_BEGIN, 84)])
                RESULTS.append({'case': name, 'status': 'PASS', 'error': meta['error'],
                    'opens': scenario.opens, 'root_reads': scenario.memory.root_reads,
                    'binary_saved': False, 'budget': meta.get('budget')})


if __name__ == '__main__':
    unittest.main()
