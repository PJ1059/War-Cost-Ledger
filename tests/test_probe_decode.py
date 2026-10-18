"""Binary fixtures verify independent native slots and strict file bounds."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from probe_decode import decode_binary, read_binary, MAX_SIZE


def pack(metadata=None, main=None, sources=b'', code=(b'', b'')):
    if metadata is None:
        metadata = {'version': '0.3.1', 'id': 'a' * 32, 'label': '测试', 'time': 123,
            'mission': True, 'build': 25480438, 'player_entity': 42,
            'capacity': 2, 'empty': 0xFFFFFFFF, 'score_index': 0}
    if main is None:
        main = struct.pack('<IifB7x', 7, -3, 2.5, 2) + struct.pack('<IifB7x', metadata['empty'], 0, 0, 0)
    segments = [json.dumps(metadata, ensure_ascii=False).encode('utf8'), main, sources, *code]
    return struct.pack('<8s5I', b'HD2STAT1', *(len(segment) for segment in segments)) + b''.join(segments)


class DecodeTests(unittest.TestCase):
    def test_independent_slots_empty_main_and_duplicate_source_blocks(self):
        sources = bytearray(64 * 328)
        for block, integer in [(0, 8), (3, 19)]:
            struct.pack_into('<II', sources, block * 328, 0x89ABCDEF, 0x01234567)
            struct.pack_into('<IifB7x', sources, block * 328 + 8, 7, integer, 4.25, 0)
            # Slot after the terminator is deliberately ignored.
            struct.pack_into('<IifB7x', sources, block * 328 + 8 + 40, 99, 4, 8.0, 1)
        result = decode_binary(pack(sources=bytes(sources)))
        self.assertEqual(result['stats']['main'], [{'slot': 0, 'key': 7, 'i32': -3, 'f32': 2.5,
            'f32_valid': True, 'float_bits': 0x40200000, 'bool': True, 'bool_byte': 2}])
        expected = [{'block': block, 'type': '0123456789ABCDEF', 'entries': [
            {'slot': 0, 'key': 7, 'i32': integer, 'f32': 4.25, 'f32_valid': True,
             'float_bits': 0x40880000, 'bool': False, 'bool_byte': 0}]} for block, integer in [(0, 8), (3, 19)]]
        self.assertEqual(result['stats']['sources'], expected)
        self.assertEqual(result['stats']['player_entity'], 42)
        self.assertEqual(result['stats']['score_index'], 0)
        self.assertEqual(result['stats']['capacity'], 2)
        self.assertEqual(result['label'], '测试')

    def test_nonfinite_float_omitted_bits_preserved(self):
        for bits in [0x7F800000, 0xFF800000, 0x7FC00001]:
            with self.subTest(bits=bits):
                main = struct.pack('<IiIB7x', 7, 13, bits, 255) + struct.pack('<IifB7x', 0xFFFFFFFF, 0, 0, 0)
                entry = decode_binary(pack(main=main))['stats']['main'][0]
                self.assertNotIn('f32', entry)
                self.assertFalse(entry['f32_valid'])
                self.assertEqual(entry['float_bits'], bits)
                self.assertEqual(entry['i32'], 13)
                self.assertTrue(entry['bool'])
                json.dumps(entry, allow_nan=False)

    def test_zero_capacity_and_sources_allowed(self):
        result = decode_binary(pack({'player_entity': 0, 'score_index': 3, 'capacity': 0, 'empty': 0}, b''))
        self.assertEqual(result['stats']['main'], [])
        self.assertEqual(result['stats']['sources'], [])

    def test_code_hex_and_unreadable_ranges(self):
        metadata = {'player_entity': 42, 'score_index': 0, 'capacity': 0, 'empty': 0,
            'code_ranges': [{'rva': 0x630130, 'size': 2}, {'rva': 0xBF9810, 'size': 3, 'error': 'unreadable'}]}
        result = decode_binary(pack(metadata, b'', code=(b'\x01\xFE', b'')))
        self.assertEqual(result['code'], [{'rva': 0x630130, 'size': 2, 'hex': '01FE'},
            {'rva': 0xBF9810, 'size': 3, 'error': 'unreadable'}])

    def test_truncated_magic_extra_bytes_and_size_rejected(self):
        valid = pack()
        for invalid in [b'', valid[:27], b'INVALID!' + valid[8:], valid[:-1], valid + b'x', b'x' * (MAX_SIZE + 1)]:
            with self.subTest(length=len(invalid)):
                with self.assertRaises(ValueError):
                    decode_binary(invalid)

    def test_capacity_and_table_length_rejected(self):
        metadata = {'player_entity': 42, 'score_index': 0, 'capacity': 0, 'empty': 0}
        for values, main, sources in [({'capacity': 4097}, b'', b''), ({'capacity': True}, b'', b''),
            ({'capacity': 3}, b'\0' * 60, b''), ({'capacity': 1}, b'', b''),
            ({'empty': -1}, b'', b''), ({'score_index': 4}, b'', b''),
            ({'player_entity': -1}, b'', b''), ({}, b'', b'x' * 328)]:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    decode_binary(pack({**metadata, **values}, main, sources))

    def test_metadata_and_code_failures_rejected(self):
        for metadata_bytes in [b'[]', b'null', b'{broken', b'\xff']:
            with self.subTest(metadata_bytes=metadata_bytes):
                data = struct.pack('<8s5I', b'HD2STAT1', len(metadata_bytes), 0, 0, 0, 0) + metadata_bytes
                with self.assertRaises(ValueError):
                    decode_binary(data)
        metadata = {'player_entity': 42, 'score_index': 0, 'capacity': 0, 'empty': 0}
        for code_metadata, code in [({}, (b'a', b'')), ({'code_ranges': []}, (b'', b'')),
            ({'code_ranges': [{'rva': 1, 'size': 2}, {'rva': 2, 'size': 1}]}, (b'a', b'b')),
            ({'code_ranges': [{'rva': 1, 'size': 1}, {'rva': 2, 'size': 1}]}, (b'', b'b'))]:
            with self.assertRaises(ValueError):
                decode_binary(pack({**metadata, **code_metadata}, b'', code=code))

    def test_read_binary_never_writes_or_uses_metadata_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            malicious = root / 'unexpected.json'
            metadata = {'player_entity': 42, 'score_index': 0, 'capacity': 0, 'empty': 0, 'path': str(malicious)}
            source = root / 'capture.bin'
            source.write_bytes(pack(metadata, b''))
            result = read_binary(source)
            self.assertEqual(result['path'], str(malicious))
            self.assertFalse(malicious.exists())
            self.assertEqual(list(root.iterdir()), [source])

    def test_full_bounded_table_and_position_metadata_are_retained(self):
        metadata = {'player_entity': 42, 'score_index': 1, 'capacity': 4096, 'empty': 0xFFFFFFFF,
            'game_state': 4, 'game_mode': 1, 'host': False, 'player_lifecycle': 2,
            'avatar': 1042, 'position': {'x': 1.25, 'y': 8.5, 'z': -2}}
        main = b''.join(struct.pack('<IifB7x', key + 1, key, key / 8, key % 2) for key in range(4096))
        sources = bytearray(64 * 328)
        for block in range(64):
            struct.pack_into('<II', sources, block * 328, block + 1, 0x01234567)
            for slot in range(16):
                struct.pack_into('<IifB7x', sources, block * 328 + 8 + slot * 20, slot + 1, slot, slot / 2, 0)
        result = decode_binary(pack(metadata, main, bytes(sources)))
        self.assertEqual(len(result['stats']['main']), 4096)
        self.assertEqual(sum(len(source['entries']) for source in result['stats']['sources']), 1024)
        self.assertEqual(result['stats']['main'][4095]['slot'], 4095)
        self.assertEqual(result['position'], metadata['position'])
        self.assertFalse(result['host'])
        self.assertEqual(result['avatar'], 1042)
        json.dumps(result, allow_nan=False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
