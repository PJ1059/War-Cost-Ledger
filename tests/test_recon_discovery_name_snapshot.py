"""Owned source-string/roster fixtures only, never game process reads."""
from pathlib import Path
import importlib.util
import struct
import sys
import unittest
from unittest.mock import patch
import copy

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
import test_recon_chat_row_child_descriptor_snapshot as prior
spec = importlib.util.spec_from_file_location('recon_discovery_name', ROOT / 'tools/recon-discovery-name-snapshot.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)


def name_raw(value):
    data = value.encode('utf8') + b'\0'
    assert len(data) <= 64
    return data + bytes(64 - len(data))


class Memory(prior.Memory):
    def __init__(self):
        super().__init__()
        captured, expected = tool.source()
        raw = next(iter(self.composites.values()))
        raw[tool.child.CHILD + 272:] = expected
        self.cells[self.state + tool.layout.STATE_OFFSET] = struct.pack('<I', 4)
        self.name_pointer = struct.unpack_from('<Q', expected, 16)[0]
        self.cells[self.name_pointer] = name_raw('本地玩家')
        self.roster, self.user = 0x240000000, 0x250000000
        self.cells[self.module['game_base'] + tool.ROSTER_GLOBAL] = struct.pack('<Q', self.roster)
        self.cells[self.module['game_base'] + tool.USER_GLOBAL] = struct.pack('<Q', self.user)
        self.peer = struct.pack('<Q', 123)
        self.cells[self.user + tool.LOCAL_PEER] = self.peer
        for i in range(4): self.cells[self.roster + i * tool.ROSTER_STRIDE] = bytes(72)
        self.cells[self.roster] = self.peer + name_raw('本地玩家')
        self.captured = copy.deepcopy(captured)
        self.expected = expected
        self.captured.update(hud=self.hud, chat=self.chat, chat_identity=tool.reader.identity(self.cells[self.chat]))
        at = next(iter(self.composites))
        self.captured['rows'][0].update(container=at, address=at + tool.child.CHILD,
            container_identity=tool.reader.identity(raw[:256]),
            identity=tool.reader.identity(raw[tool.child.CHILD:tool.child.CHILD + 256]))


class NameTests(unittest.TestCase):
    def snapshot(self, memory):
        with patch.object(tool, 'source', return_value=(memory.captured, memory.expected)):
            return tool.snapshot(memory, memory.module, clock=lambda: 0)

    def test_exact_name_matches_local_peer_without_type10_follow(self):
        memory = Memory(); result = self.snapshot(memory)
        self.assertEqual(result['name'], '本地玩家')
        self.assertTrue(result['unique_local_match'])
        self.assertEqual(result['unique_peer_match'], '000000000000007B')
        self.assertFalse(result['type10_followed'])
        self.assertEqual(result['discovery_events_emitted'], 0)
        self.assertLessEqual(result['read_bytes'], 4096)
        self.assertLessEqual(result['read_calls'], 64)

    def test_duplicate_name_or_other_player_never_attributes_to_local(self):
        memory = Memory()
        memory.cells[memory.roster + tool.ROSTER_STRIDE] = struct.pack('<Q', 456) + name_raw('本地玩家')
        result = self.snapshot(memory)
        self.assertIsNone(result['unique_peer_match'])
        self.assertFalse(result['unique_local_match'])
        memory.cells[memory.roster] = memory.peer + name_raw('其他名字')
        result = self.snapshot(memory)
        self.assertEqual(result['unique_peer_match'], '00000000000001C8')
        self.assertFalse(result['unique_local_match'])

    def test_changed_template_stops_before_name_read(self):
        memory = Memory(); raw = next(iter(memory.composites.values()))
        struct.pack_into('<I', raw, tool.child.CHILD + 272, 0)
        with self.assertRaisesRegex(ValueError, 'DISCOVERY_ROW_CHANGED'): self.snapshot(memory)
        self.assertNotIn(memory.name_pointer, [at for at, _ in memory.reads])

    def test_nonterminated_name_does_not_read_more(self):
        memory = Memory(); memory.cells[memory.name_pointer] = b'a' * 64
        with self.assertRaisesRegex(ValueError, 'STRING_LIMIT'): self.snapshot(memory)
        self.assertEqual([n for at, n in memory.reads if at == memory.name_pointer], [64])

    def test_ship_only_reads_when_original_notification_owner_survives(self):
        memory = Memory()
        memory.cells[memory.state + tool.layout.STATE_OFFSET] = struct.pack('<I', 3)
        result = self.snapshot(memory)
        self.assertEqual(result['mode'], 3)
        self.assertTrue(result['unique_local_match'])
        self.assertEqual(result['discovery_events_emitted'], 0)
        memory = Memory()
        memory.captured['chat_identity']['parent'] += 8
        with self.assertRaisesRegex(ValueError, 'SOURCE_OWNER_CHANGED'): self.snapshot(memory)
        self.assertNotIn(memory.name_pointer, [at for at, _ in memory.reads])

    def test_state_transition_during_read_refuses_result(self):
        memory = Memory(); original = memory.read; times = [0]
        def read(at, length):
            if at == memory.state + tool.layout.STATE_OFFSET:
                times[0] += 1
                if times[0] == 2: return struct.pack('<I', 3)
            return original(at, length)
        memory.read = read
        with self.assertRaisesRegex(ValueError, 'IDENTITY_CHANGED'): self.snapshot(memory)


if __name__ == '__main__': unittest.main()
