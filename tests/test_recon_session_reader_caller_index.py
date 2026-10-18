from pathlib import Path
import importlib.util,json,struct,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests')]
import test_hit_contact_registration_index as fixture
spec=importlib.util.spec_from_file_location('session_reader_calls',ROOT/'tools/recon-session-reader-caller-index.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)

class CallerIndexTests(unittest.TestCase):
    def test_known_leaf_entry_and_budget(self):
        source=tool.validate_source();index=tool.private_index()
        self.assertEqual(source['reader_bytes'],56)
        self.assertEqual(index.TARGET_RVA,0x1350EF0)
        self.assertEqual(len(bytes.fromhex(index.PIN_HEX)),16)
        self.assertEqual(index.MAX_CANDIDATES,64)
        self.assertEqual(index.MAX_BYTES,48*1024*1024)
    def test_owned_full_index_only_exact_calls(self):
        index=tool.private_index();code=bytearray(b'\x90'*256)
        for at,target in ((62,tool.TARGET),(120,tool.TARGET+1),(180,tool.TARGET)):
            code[at:at+5]=b'\xe8'+struct.pack('<i',target-(0x1000+at+5))
        with tempfile.TemporaryDirectory() as folder,patch.object(fixture,'indexer',index):
            result=fixture.ContactReferenceTests().run_small(fixture.Scenario(bytes(code),b''),Path(folder)/'capture')
            saved=json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual([r['rva'] for r in saved['candidates']],[0x103E,0x10B4])
            self.assertFalse(saved['native_called']);self.assertFalse(saved['native_written'])

if __name__=='__main__':unittest.main()
