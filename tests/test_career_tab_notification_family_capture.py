"""One new family-scope fixture reusing fixed8 fake; no old-group run."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import test_career_tab_notification_metadata_closure as fixture
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_notification_family',ROOT/'tools/career-tab-notification-family-capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
RAW,META=probe.material()

class Memory(fixture.Memory):
    def __init__(self):
        super().__init__();self.begin,self.end=probe.BEGIN,probe.END;self.window=RAW[:96]
        self.data={n['unwind_rva']:bytes.fromhex(n['raw_hex'])for n in META['unwind_nodes']}
    def read(self,address,n):
        if address==self.game+probe.BEGIN:
            self.reads.append((address,n));assert n==194;self.body_reads_count+=1;return b'\x90'*n
        return super().read(address,n)

class Scenario(fixture.Scenario):
    def __init__(self):super().__init__();self.memory=Memory()

class FamilyTests(unittest.TestCase):
    def test_only_exact194_family_twice_and_complete_metadata_post(self):
        with tempfile.TemporaryDirectory() as temp:
            s=Scenario();result=probe.run(Path(temp)/'capture',s.dependencies(),fixture.fixture.fixture.fixture.fixture.Clock())
            m=json.loads(Path(result['json_path']).read_text('utf8'));raw=Path(result['binary_path']).read_bytes()
            self.assertEqual(s.memory.body_reads_count,2);self.assertEqual(m['body']['length'],194)
            self.assertEqual(raw[m['body']['binary_offset']:],b'\x90'*194)
            self.assertTrue(m['full_fixed_RF_UW_after_body_match'])
            self.assertFalse(m['foreign_body_read']);self.assertFalse(m['unproven_gap_read'])
            self.assertEqual(m['budget']['read_calls'],45);self.assertEqual(m['budget']['bytes_requested'],9354)
            self.assertEqual(m['budget']['read_calls'],len(s.memory.reads));self.assertTrue(s.memory.closed)
            print('OWNED '+json.dumps({'status':'PASS','body_bytes':194,'budget':m['budget']}))

if __name__=='__main__':unittest.main()
