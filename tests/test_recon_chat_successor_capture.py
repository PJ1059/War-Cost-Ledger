from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import recon_chat_code_capture as v2
import recon_chat_successor_capture as tool

BASE = 0x180000000
IDENTITY = {'game_base': BASE, 'game_size': v2.IMAGE_SIZE,
            'game_path': 'owned/game.dll', 'exe_path': 'owned/helldivers2.exe'}


class OwnedMemory:
    def __init__(self, successor_count=4):
        self.blocks, self.reads, self.queries = {}, [], []
        self.protect, self.state, self.kind = 0x20, 0x1000, 0x1000000
        self.short = False
        for index, begin, end, unwind in tool.ENTRIES:
            self.blocks[v2.EXCEPTION_RVA + index * 12] = struct.pack('<III', begin, end, unwind)
        self.blocks[0x24DB604] = bytes.fromhex('010a0400')
        self.blocks[0x24DB610] = bytes.fromhex('210f0600')
        root = struct.pack('<III', *tool.ENTRIES[0][1:])
        self.blocks[0x24DB620] = root
        self.blocks[0x24DB62C] = bytes((0x21, 0x0A, successor_count, 0))
        self.blocks[0x24DB62C + 4 + 2 * ((successor_count + 1) & ~1)] = struct.pack('<III', *tool.ENTRIES[1][1:])
        code = bytearray([0x90] * (tool.CODE_END - tool.CODE_BEGIN))
        offset = v2.TARGET_RVA - tool.CODE_BEGIN
        code[offset:offset + 12] = bytes.fromhex(v2.TARGET_PIN)
        self.blocks[tool.CODE_BEGIN] = bytes(code)

    def query(self, address):
        self.queries.append(address)
        return {'base': BASE, 'size': v2.IMAGE_SIZE, 'state': self.state,
                'type': self.kind, 'protect': self.protect}

    def read(self, address, size):
        rva = address - BASE
        self.reads.append((rva, size))
        data = self.blocks.get(rva)
        if data is None or len(data) != size:
            raise AssertionError(('unplanned read', hex(rva), size))
        return data[:-1] if self.short else data

    def code_read(self):
        return any(rva == tool.CODE_BEGIN for rva, _ in self.reads)


class Tests(unittest.TestCase):
    def capture(self, memory=None):
        memory = memory or OwnedMemory()
        binary, meta = tool.capture(memory, IDENTITY, clock=lambda: 0.0)
        return memory, binary, meta

    def test_fixed_ranges_pin_budget_and_globals(self):
        memory, binary, meta = self.capture()
        self.assertEqual(len(binary), 692)
        self.assertEqual(meta['source_revision'], tool.REVISION)
        self.assertEqual(meta['budget']['read_calls'], 9)
        self.assertEqual(meta['budget']['query_calls'], 9)
        self.assertEqual(meta['budget']['bytes_requested'], 764)
        self.assertEqual(meta['budget']['max_reads'], 10)
        self.assertEqual(meta['budget']['max_bytes'], 4096)
        self.assertFalse(meta['logical_function_complete'])
        self.assertFalse(meta['all_sibling_fragments_captured'])
        self.assertFalse(meta['native_written'])
        self.assertFalse(meta['native_called'])
        self.assertEqual(meta['chat_messages_read'], 0)
        self.assertEqual(memory.reads[-1], (tool.CODE_BEGIN, 692))
        self.assertEqual(v2.REVISION, 'recon_chat_history_code_v2')
        self.assertEqual(v2.MAX_READS, 32)
        self.assertEqual(v2.MAX_BYTES, 8192)
        tool.verify_saved(meta, binary)

    def test_exact_table_tuple_reject_before_code(self):
        for position in range(3):
            with self.subTest(position=position):
                memory = OwnedMemory()
                index, begin, end, unwind = tool.ENTRIES[position]
                memory.blocks[v2.EXCEPTION_RVA + index * 12] = struct.pack('<III', begin, end + 1, unwind)
                with self.assertRaisesRegex(ValueError, 'TABLE_CHANGED'):
                    self.capture(memory)
                self.assertFalse(memory.code_read())

    def test_unknown_or_mixed_unwind_flags_reject(self):
        for header in ('23100600', '29100600', '010f0600', '250f0600'):
            with self.subTest(header=header):
                memory = OwnedMemory()
                memory.blocks[0x24DB62C] = bytes.fromhex(header)
                with self.assertRaises(ValueError):
                    self.capture(memory)
                self.assertFalse(memory.code_read())

    def test_wrong_parent_does_not_follow(self):
        memory = OwnedMemory()
        memory.blocks[0x24DB638] = struct.pack('<III', 0x1097C74, 0x1097C83, 0x24DB644)
        with self.assertRaisesRegex(ValueError, 'NOT_KNOWN_PARENT'):
            self.capture(memory)
        self.assertFalse(memory.code_read())
        self.assertEqual(len(memory.reads), 8)

    def test_saved_live_transitive_chain_uses_only_known_records(self):
        evidence = __import__('json').loads((ROOT / 'dist/interface-code-followup-v2/recon-v3/status.json').read_text(encoding='utf8'))['evidence']
        tool.verify_metadata(evidence['exception_records'], evidence['unwind_chain'])
        memory, _, meta = self.capture()
        self.assertEqual(meta['exception_records'], evidence['exception_records'])
        self.assertEqual(meta['unwind_chain'], evidence['unwind_chain'])
        self.assertEqual(len(memory.reads), 9)

    def test_odd_count_alignment(self):
        memory, _, meta = self.capture(OwnedMemory(successor_count=3))
        self.assertEqual(meta['unwind_chain'][2]['chain_entry']['rva'], 0x24DB638)
        self.assertIn((0x24DB638, 12), memory.reads)

    def test_count_cap_and_frame_mismatch(self):
        for header in ('210f4100', '210f0601'):
            memory = OwnedMemory()
            memory.blocks[0x24DB62C] = bytes.fromhex(header)
            with self.assertRaises(ValueError):
                self.capture(memory)
            self.assertFalse(memory.code_read())

    def test_known_root_and_target_headers_pinned(self):
        for rva, raw in ((0x24DB604, '010a0300'), (0x24DB610, '210f0500')):
            memory = OwnedMemory()
            memory.blocks[rva] = bytes.fromhex(raw)
            with self.assertRaises(ValueError):
                self.capture(memory)
            self.assertFalse(memory.code_read())

    def test_pin_short_read_and_page_rejection(self):
        memory = OwnedMemory()
        memory.blocks[tool.CODE_BEGIN] = b'\x90' * 692
        with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
            self.capture(memory)
        memory = OwnedMemory()
        memory.short = True
        with self.assertRaisesRegex(ValueError, 'SHORT_READ'):
            self.capture(memory)
        for attribute, value in (('protect', 0x120), ('kind', 0x20000), ('state', 0x2000)):
            memory = OwnedMemory()
            setattr(memory, attribute, value)
            with self.assertRaises(ValueError):
                self.capture(memory)
            self.assertEqual(memory.reads, [])

    def test_budget_gates_before_io(self):
        for reads, requested in ((10, 0), (0, 4090)):
            memory = OwnedMemory()
            budget = tool.session.Budget(memory, IDENTITY, lambda: 0.0)
            budget.read_calls, budget.bytes_requested = reads, requested
            with self.assertRaisesRegex(ValueError, 'READ_BUDGET'):
                budget.read(BASE + tool.CODE_BEGIN, 692)
            self.assertEqual(memory.reads, [])
        memory = OwnedMemory()
        budget = tool.session.Budget(memory, IDENTITY, lambda: 0.0)
        budget.query_calls = 10
        with self.assertRaisesRegex(ValueError, 'QUERY_BUDGET'):
            budget.query(BASE + tool.CODE_BEGIN)
        self.assertEqual(memory.queries, [])

    def test_time_before_first_io(self):
        ticks = iter((0.0, 2.1))
        memory = OwnedMemory()
        with self.assertRaisesRegex(ValueError, 'TIME_BUDGET'):
            tool.capture(memory, IDENTITY, clock=lambda: next(ticks, 2.1))
        self.assertEqual(memory.reads, [])
        self.assertEqual(memory.queries, [])

    def test_cache_tampering_rejected(self):
        _, binary, meta = self.capture()
        for alter in (
            lambda m: m.update(source_revision='recon_chat_history_code_v2'),
            lambda m: m['ranges'][0].update(length=691),
            lambda m: m['exception_records'][2].update(index=54628),
            lambda m: m['unwind_chain'][2]['chain_entry'].update(rva=0x24DB640),
            lambda m: m['budget'].update(read_calls=11),
        ):
            bad = copy.deepcopy(meta)
            alter(bad)
            with self.assertRaises(ValueError):
                tool.verify_saved(bad, binary)
        bad = copy.deepcopy(meta)
        bad['binary_sha256'] = hashlib.sha256(binary[:-1]).hexdigest()
        with self.assertRaisesRegex(ValueError, 'CACHE_HASH'):
            tool.verify_saved(bad, binary)


if __name__ == '__main__':
    unittest.main()
