"""Owned composite rows, including worst-case 64 Text children and rebuilds."""
from pathlib import Path
import importlib.util
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
import test_recon_chat_row_descriptor_snapshot as prior
spec = importlib.util.spec_from_file_location('recon_chat_child_snapshot', ROOT / 'tools/recon-chat-row-child-descriptor-snapshot.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class Memory(prior.Memory):
    def __init__(self):
        super().__init__()
        self.break_relation = False
        self.break_identity = False
        self.composites = {}
        for i in range(64):
            at = self.chat + tool.reader.ROW_BASE + i * tool.reader.ROW_STRIDE
            old_label = self.cells.pop(at + 272)
            raw = bytearray(tool.COMPOSITE_BYTES)
            raw[:256] = prior.header(1, self.chat + tool.ROW_PARENT, self.context)
            struct.pack_into('<QQ', raw, 0xE0, at + tool.CHILD, at + tool.reader.ROW_STRIDE if i < 63 else 0)
            raw[tool.CHILD:tool.CHILD + 256] = prior.header(8, at, self.context)
            raw[tool.CHILD + 272:] = old_label
            self.cells.pop(at)
            self.composites[at] = raw

    def read(self, at, length):
        for base, raw in self.composites.items():
            if base <= at < at + length <= base + len(raw):
                self.reads.append((at, length))
                result = bytes(raw[at - base:at - base + length])
                if self.break_relation and length == 52:
                    result = bytes(52)
                if self.break_identity and length == 16:
                    result = bytes(16)
                return result
        return super().read(at, length)


class ChildTests(unittest.TestCase):
    def test_all_64_text_children_are_inside_original_budget(self):
        memory = Memory()
        result = tool.snapshot(memory, memory.module, clock=lambda: 0)
        self.assertEqual(sum('descriptor' in r for r in result['rows']), 64)
        self.assertEqual([r['index'] for r in result['rows'] if r['descriptor']['discovery_template_match']], [17])
        self.assertEqual(result['read_calls'], 209)
        self.assertEqual(result['read_bytes'], 61918)
        self.assertLessEqual(result['read_bytes'], 65536)
        self.assertLessEqual(result['read_calls'], 256)
        self.assertEqual(result['string_pointers_followed'], 0)
        self.assertEqual(result['discovery_events_emitted'], 0)
        self.assertFalse(result['atomic'])

    def test_direct_child_relation_is_required(self):
        for offset, value in ((0xE0, 0x330000000), (0xF0, 0x330000000)):
            memory = Memory()
            raw = next(iter(memory.composites.values()))
            struct.pack_into('<Q', raw, offset, value)
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'CHILD_RELATION_CHANGED'):
                tool.snapshot(memory, memory.module, clock=lambda: 0)

    def test_wrong_child_kind_or_context_is_reported_without_descriptor(self):
        for offset, fmt, value in ((tool.CHILD, '<I', 7 << 18), (tool.CHILD + 0xF8, '<Q', 0x230000000)):
            memory = Memory()
            raw = next(iter(memory.composites.values()))
            struct.pack_into(fmt, raw, offset, value)
            result = tool.snapshot(memory, memory.module, clock=lambda: 0)
            self.assertNotIn('descriptor', result['rows'][0])
            self.assertEqual(sum('descriptor' in r for r in result['rows']), 63)

    def test_rebuild_after_main_read_stops(self):
        for attr in ('break_relation', 'break_identity'):
            memory = Memory()
            setattr(memory, attr, True)
            with self.subTest(attr=attr), self.assertRaisesRegex(ValueError, 'CHILD_IDENTITY_CHANGED'):
                tool.snapshot(memory, memory.module, clock=lambda: 0)

    def test_combat_scheduler_delay_only_relaxes_wall_clock(self):
        def delayed_clock(delay):
            calls = [0]
            def clock():
                calls[0] += 1
                return 0 if calls[0] == 1 else delay
            return clock
        memory = Memory()
        result = tool.snapshot(memory, memory.module, clock=delayed_clock(1.0))
        self.assertEqual((result['read_bytes'], result['read_calls']), (61918, 209))
        memory = Memory()
        with self.assertRaises(tool.reader.layout.SliceFull):
            tool.snapshot(memory, memory.module, clock=delayed_clock(1.5))
        self.assertEqual(memory.reads, [])


if __name__ == '__main__':
    unittest.main()
