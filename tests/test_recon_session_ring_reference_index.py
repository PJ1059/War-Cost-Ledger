from pathlib import Path
import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'tests')]
import test_hit_contact_registration_index as fixture
spec = importlib.util.spec_from_file_location('recon_session_ring_index', ROOT/'tools/recon-session-ring-reference-index.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class RingIndexTests(unittest.TestCase):
    def test_exact_readonly_code_scope_and_source(self):
        source = tool.validate_source()
        self.assertEqual(source['record_base_offset'], 0x1F038)
        self.assertFalse(source['discovery_type_proven'])
        index = tool.private_index()
        self.assertEqual(len(index.SECTIONS), 1)
        self.assertEqual(index.PIN_RVA, 0x108351A)
        self.assertEqual(len(bytes.fromhex(index.PIN_HEX)), 16)
        self.assertEqual(index.MAX_BYTES, 48 * 1024 * 1024)
        self.assertEqual(index.MAX_READS, 256)
        self.assertEqual(index.MAX_CANDIDATES, 64)

    def test_only_record_base_matches_omitting_repeated_next_slot(self):
        data = struct.pack('<IIII',0x1F038,0x1F838,0x1F048,0x1F038)
        found = list(tool.byte_matches(data,0,'code',0))
        self.assertEqual([row[0] for row in found], [0,12])
        with self.assertRaisesRegex(ValueError, 'CODE_ONLY'):
            list(tool.byte_matches(data,0,'data',0))

    def test_full_owned_capture_handles_chunk_boundary_and_pin(self):
        index = tool.private_index()
        code = bytearray(b'\x90'*256)
        for at, value in ((62, 0x1F038), (128, 0x1F838)):
            code[at:at+4] = struct.pack('<I', value)
        scenario = fixture.Scenario(bytes(code), b'')
        with tempfile.TemporaryDirectory() as folder, patch.object(fixture, 'indexer', index):
            result = fixture.ContactReferenceTests().run_small(scenario, Path(folder)/'capture')
            saved = json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual([r['offset'] for r in saved['candidates']], [0x1F038])
            self.assertEqual(saved['ship_before'], saved['ship_after'])
            self.assertFalse(saved['discovery_type_proven'])
            self.assertFalse(saved['whole_binary_saved'])


if __name__ == '__main__': unittest.main()
