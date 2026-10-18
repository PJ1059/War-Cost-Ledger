"""Combined discovery snapshot: bounded names, stable roster and actual row types."""
from pathlib import Path
import importlib.util
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
import test_recon_chat_row_child_descriptor_snapshot as prior
spec = importlib.util.spec_from_file_location('recon_combined_source', ROOT / 'tools/recon-discovery-row-source-snapshot.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)


def string(value):
    raw = value.encode('utf8') + b'\0'
    return raw + bytes(64 - len(raw))


class Memory(prior.Memory):
    def __init__(self, discoveries=1, arguments=2):
        super().__init__()
        self.roster, self.user = 0x240000000, 0x250000000
        self.cells[self.module['game_base'] + tool.ROSTER_GLOBAL] = struct.pack('<Q', self.roster)
        self.cells[self.module['game_base'] + tool.USER_GLOBAL] = struct.pack('<Q', self.user)
        self.peer = struct.pack('<Q', 123)
        self.cells[self.user + tool.LOCAL_PEER] = self.peer
        for i in range(4): self.cells[self.roster + i * tool.ROSTER_STRIDE] = bytes(72)
        self.cells[self.roster] = self.peer + string('本地玩家')
        self.cells[self.state + tool.layout.STATE_OFFSET] = struct.pack('<I', 4)
        for i, (at, raw) in enumerate(self.composites.items()):
            label = bytearray(345)
            if i < discoveries:
                struct.pack_into('<I', label, 0, 0x92871A58 if arguments == 2 else 0xCD539459)
                label[344] = arguments
                pointer = 0x330100000 + i * 64
                self.cells[pointer] = string('本地玩家')
                struct.pack_into('<IIQ', label, 8, tool.NAME_KEY, 1, pointer)
                struct.pack_into('<IIQ', label, 32, tool.DISCOVERY_KEY, 10, 0)
                struct.pack_into('<Q', label, 48, 0x333333333333)
                if arguments == 3: struct.pack_into('<IIQ', label, 56, 0xE119745E, 99, 0)
            else:
                struct.pack_into('<I', label, 0, 0x14DCC78A)
            raw[tool.child.CHILD + 272:] = label


class CombinedTests(unittest.TestCase):
    def snapshot(self, memory): return tool.snapshot(memory, memory.module, clock=lambda: 0)

    def test_real_template_attributes_unique_name_and_leaves_type10_raw(self):
        memory = Memory(); result = self.snapshot(memory)
        source = result['rows'][0]['discovery_source']
        self.assertTrue(source['resolved'] and source['local_player'])
        self.assertEqual(source['peer'], '000000000000007B')
        self.assertFalse(source['type10_followed'])
        self.assertEqual(result['names_attempted'], 1)
        self.assertEqual(result['discovery_events_emitted'], 0)
        self.assertNotIn(0x333333333333, [at for at, _ in memory.reads])

    def test_64_discoveries_keep_original_global_budgets(self):
        memory = Memory(64, 3); result = self.snapshot(memory)
        self.assertEqual(result['names_attempted'], 8)
        self.assertEqual((result['read_bytes'], result['read_calls']), (64214, 255))
        self.assertEqual(sum(r['discovery_source']['resolved'] for r in result['rows']), 8)
        self.assertTrue(all(r['discovery_source']['reason'] == 'eight_name_budget' for r in result['rows'][8:]))
        self.assertLessEqual(result['read_bytes'], 65536)
        self.assertLessEqual(result['read_calls'], 256)

    def test_duplicate_roster_names_do_not_attribute(self):
        memory = Memory()
        memory.cells[memory.roster + tool.ROSTER_STRIDE] = struct.pack('<Q', 456) + string('本地玩家')
        source = self.snapshot(memory)['rows'][0]['discovery_source']
        self.assertFalse(source['resolved'])
        self.assertEqual(source['reason'], 'ambiguous_roster_name')
        self.assertNotIn('local_player', source)

    def test_name_mutation_during_row_refuses_whole_snapshot(self):
        memory = Memory(); original = memory.read; calls = [0]
        def read(at, size):
            if at == 0x330100000:
                calls[0] += 1
                if calls[0] == 2: return string('变化后的名字')
            return original(at, size)
        memory.read = read
        with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED_DURING_ROW'): self.snapshot(memory)

    def test_no_template_no_name_reads_even_if_roster_imitates_discovery(self):
        memory = Memory(0)
        memory.cells[memory.roster] = memory.peer + string('本人已发现轻型巢穴')
        result = self.snapshot(memory)
        self.assertEqual(result['names_attempted'], 0)
        self.assertTrue(all('discovery_source' not in r for r in result['rows']))

    def test_nonterminated_name_stays_unknown_without_read_expansion(self):
        memory = Memory(); memory.cells[0x330100000] = b'a' * 64
        result = self.snapshot(memory)
        source = result['rows'][0]['discovery_source']
        self.assertFalse(source['resolved'])
        self.assertEqual(source['reason'], 'name_not_terminated_within64')
        self.assertEqual([n for at, n in memory.reads if at == 0x330100000], [64, 64])


if __name__ == '__main__': unittest.main()
