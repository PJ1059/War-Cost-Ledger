"""Focused offline contract checks for the two-target index, no process access."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bughole_reference_index', ROOT / 'tools/bughole-code-reference-index.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BugHoleCodeReferenceIndex(unittest.TestCase):
    def test_exact_targets_only(self):
        start = 0x123400
        raw = bytearray(b'\x90' * 128)
        for at, op, target in ((3, 0xE8, 0x13E15C0), (23, 0xE9, 0x13E1DC0),
                              (48, 0xE8, 0x13E15C1), (70, 0xE8, 0x13E1850)):
            raw[at:at + 5] = bytes([op]) + struct.pack('<i', target - start - at - 5)
        raw[100:108] = struct.pack('<Q', 0x140000000 + 0x13E15C0)
        raw[-2:] = b'\xe8\x00'  # An incomplete opcode never becomes a candidate.
        found = list(module.byte_matches(raw, start, 'code', b'ignored'))
        self.assertEqual([(x[0], x[1]) for x in found], [(3, 5), (23, 5)])
        self.assertIn('destruction_enqueue', found[0][2])
        self.assertIn('destruction_consumer', found[1][2])

    def test_data_scope_refused(self):
        with self.assertRaisesRegex(ValueError, 'CODE_ONLY'):
            module.byte_matches(b'\x90' * 8, 0, 'declared_ro_data', b'')

    def test_saved_sources_and_frozen_limits(self):
        index = module.private_index()
        self.assertEqual(len(index.SECTIONS), 1)
        self.assertEqual(index.SECTIONS[0]['index'], 0)
        self.assertEqual(index.MAX_BYTES, 48 * 1024 * 1024)
        self.assertEqual(index.MAX_READS, 256)
        self.assertEqual(index.MAX_SECONDS, 2.0)
        self.assertEqual(index.MAX_CANDIDATES, 64)
        self.assertEqual(index.PIN_RVA, 0x13E15C0)
        self.assertEqual(index.PIN_HEX, module.PIN_HEX)
        self.assertTrue(index.validate_sources()['consumer_entry_actual_declaration'])

    def test_chunk_boundary_is_once_and_targets_are_correct(self):
        index = module.private_index()
        index.CHUNK_BYTES = 96
        section = dict(index.SECTIONS[0])
        section['end_exclusive'] = section['rva'] + 192
        data = bytearray(b'\x90' * 192)
        for at, target in ((94, 0x13E15C0), (132, 0x13E1DC0)):
            data[at:at + 5] = b'\xe8' + struct.pack('<i', target - section['rva'] - at - 5)

        class Budget:
            identity = {'game_base': 0x140000000}
            def query(self, address):
                return {'base': self.identity['game_base'] + section['rva'], 'size': len(data),
                        'state': 0x1000, 'type': 0x1000000, 'protect': 0x20}
            def read(self, address, size, purpose):
                at = address - self.identity['game_base'] - section['rva']
                return bytes(data[at:at + size])
            def require_capacity(self, size, calls=1):
                pass
            def time_gate(self):
                pass

        evidence = {}
        result = index.stream_index(Budget(), [section], evidence)
        self.assertTrue(result['complete'])
        self.assertEqual(result['payload_reads'], 2)
        self.assertEqual([r['target_rva'] for r in result['candidates']], [0x13E15C0, 0x13E1DC0])
        self.assertEqual([r['rva'] for r in result['candidates']], [section['rva'] + 94, section['rva'] + 132])
        self.assertTrue(all(r['window_bytes'] <= 64 and not r['instruction_boundary_verified']
                            for r in result['candidates']))
        self.assertEqual(evidence['target_rvas'], [0x13E15C0, 0x13E1DC0])


if __name__ == '__main__':
    unittest.main()
