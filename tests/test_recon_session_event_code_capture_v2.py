from pathlib import Path
import importlib.util
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
spec = importlib.util.spec_from_file_location('session_writer_v2', ROOT/'tools/recon-session-event-code-capture-v2.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class DeclaredRangeTests(unittest.TestCase):
    def test_actual_saved_metadata_has_exact_adjacent_span(self):
        saved = json.loads((ROOT/'dist/recon-session-event-code-live-20261013-v1/failure.json').read_text(encoding='utf8'))
        self.assertEqual(saved['error'], 'RECON_CODE_CHAIN_CODE_BYTES_LIMIT')
        self.assertEqual(saved['evidence']['unwind_chain'], list(tool.KNOWN))
        metadata = {entry['rva']: bytes.fromhex(entry['raw_hex']) for node in tool.KNOWN
                    for name, entry in node.items() if name in ('header', 'chain_entry')}
        nodes = []
        def read(rva, size):
            raw = metadata[rva]
            self.assertEqual(len(raw), size)
            return raw
        tool.exact_ancestry((0x10833EE, 0x108431E, 0x24D9CFC), read, nodes)
        ranges = tool.reader.ancestry_ranges(nodes)
        self.assertEqual(ranges, (('chat_history_consumer', 0x1083150, 4558),))
        self.assertEqual(tool.reader.MAX_BYTES, 8192)
        self.assertEqual(tool.reader.MAX_READS, 32)
        self.assertEqual(tool.reader.window_capture(ranges).MAX_CHUNK, 4096)

    def test_changed_parent_refused(self):
        metadata = {entry['rva']: bytes.fromhex(entry['raw_hex']) for node in tool.KNOWN
                    for name, entry in node.items() if name in ('header', 'chain_entry')}
        metadata[0x24D9CDC] = bytes.fromhex('19260800')
        with self.assertRaisesRegex(ValueError, 'DECLARED_RANGES_CHANGED'):
            tool.exact_ancestry((0x10833EE, 0x108431E, 0x24D9CFC), lambda r,n: metadata[r], [])


if __name__ == '__main__': unittest.main()
