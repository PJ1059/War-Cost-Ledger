"""Owned 64-row UI fixtures; no game process attachment or pointer chasing."""
from pathlib import Path
import importlib.util
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('recon_row_snapshot', ROOT / 'tools/recon-chat-row-descriptor-snapshot.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def header(kind, parent, context):
    raw = bytearray(256)
    struct.pack_into('<I', raw, 0, kind << 18)
    struct.pack_into('<QQ', raw, 0xF0, parent, context)
    return bytes(raw)


class Memory:
    def __init__(self):
        self.module = {'game_base': 0x180000000, 'game_size': tool.layout.IMAGE_SIZE}
        self.state, self.hud, self.context = 0x200000000, 0x210000000, 0x220000000
        self.chat = self.hud + 0x14498
        self.cells, self.reads = {}, []
        self.changed_row = None
        profile, pins = tool.sources()
        for rva, pin in tuple((p['rva'], p['hex']) for p in profile['pins'][:2]) + pins + tool.layout.PINS:
            self.cells[self.module['game_base'] + rva] = bytes.fromhex(pin)
        self.cells[self.module['game_base'] + tool.layout.STATE_GLOBAL] = struct.pack('<Q', self.state)
        self.cells[self.state + tool.layout.STATE_OFFSET] = struct.pack('<I', 3)
        self.cells[self.module['game_base'] + profile['hud']] = struct.pack('<Q', self.hud)
        self.cells[self.chat] = header(1, self.hud, self.context)
        for i in range(tool.ROW_COUNT):
            at = self.chat + tool.ROW_BASE + i * tool.ROW_STRIDE
            self.cells[at] = header(7, self.chat, self.context)
            label = bytearray(345)
            struct.pack_into('<I', label, 0, tool.DISCOVERY_KEYS[0] if i == 17 else 0)
            label[344] = 2
            # Including pointer-looking values is intentional: this tool may
            # preserve their type/value, never dereference or infer a player.
            struct.pack_into('<IIQ', label, 8, 0xAA11, 1, 0x330000008)
            struct.pack_into('<IIQ', label, 32, 0xBB22, 0xDEAD, 0x330000010)
            self.cells[at + 272] = bytes(label)

    def query(self, at):
        return {'base': at, 'size': 4096, 'state': 0x1000, 'protect': 0x20, 'type': 0x1000000}

    def read(self, at, length):
        self.reads.append((at, length))
        if at == self.changed_row and self.reads.count((at, length)) == 2:
            return header(7, self.chat + 8, self.context)
        raw = self.cells[at]
        if len(raw) != length:
            raise AssertionError((hex(at), length, len(raw)))
        return raw


class ChatRowTests(unittest.TestCase):
    def snapshot(self, memory):
        return tool.snapshot(memory, memory.module, clock=lambda: 0)

    def test_exact_rows_and_raw_arguments_without_pointer_chasing(self):
        memory = Memory()
        result = self.snapshot(memory)
        self.assertEqual(len(result['rows']), 64)
        self.assertEqual([r['index'] for r in result['rows'] if r['descriptor']['discovery_template_match']], [17])
        args = result['rows'][17]['descriptor']['arguments']
        self.assertEqual(args[0]['type'], 1)
        self.assertEqual(args[1]['type'], 0xDEAD)
        self.assertEqual(args[1]['value_raw'], 0x330000010)
        self.assertTrue(all(a['value_interpreted'] is False for a in args))
        self.assertNotIn(0x330000008, [a for a, _ in memory.reads])
        self.assertLessEqual(result['read_bytes'], 65536)
        self.assertLessEqual(result['read_calls'], 256)
        self.assertEqual(result['discovery_events_emitted'], 0)
        self.assertEqual(result['string_pointers_followed'], 0)

    def test_nontext_or_foreign_context_skips_descriptor(self):
        memory = Memory()
        for i, kind, context in ((0, 1, memory.context), (1, 7, memory.context + 8)):
            at = memory.chat + tool.ROW_BASE + i * tool.ROW_STRIDE
            memory.cells[at] = header(kind, memory.chat, context)
            del memory.cells[at + 272]
        result = self.snapshot(memory)
        self.assertTrue(all('descriptor' not in r for r in result['rows'][:2]))
        self.assertEqual(sum('descriptor' in r for r in result['rows']), 62)

    def test_identity_mutation_rejects_snapshot(self):
        memory = Memory()
        memory.changed_row = memory.chat + tool.ROW_BASE
        with self.assertRaisesRegex(ValueError, 'ROW_IDENTITY_CHANGED'):
            self.snapshot(memory)

    def test_code_pin_and_non_gameplay_mode_stop_before_rows(self):
        memory = Memory()
        first = next(iter(memory.cells))
        memory.cells[first] = bytes(len(memory.cells[first]))
        with self.assertRaisesRegex(ValueError, 'CODE_PIN_CHANGED'):
            self.snapshot(memory)
        self.assertEqual(len(memory.reads), 1)
        memory = Memory()
        memory.cells[memory.state + tool.layout.STATE_OFFSET] = struct.pack('<I', 1)
        with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP_OR_MISSION'):
            self.snapshot(memory)
        self.assertNotIn(memory.chat, [a for a, _ in memory.reads])

    def test_count_above_actual_capacity_never_decodes_more(self):
        memory = Memory()
        at = memory.chat + tool.ROW_BASE + 272
        label = bytearray(memory.cells[at]); label[344] = 255
        memory.cells[at] = bytes(label)
        row = self.snapshot(memory)['rows'][0]['descriptor']
        self.assertFalse(row['layout_valid'])
        self.assertEqual(row['arguments'], [])


if __name__ == '__main__':
    unittest.main()
