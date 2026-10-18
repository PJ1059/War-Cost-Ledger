"""One fixed8 ownership fixture reusing prior pure memory gate."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import test_career_tab_notification_capture as fixture
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_tab_fixed8_closure',ROOT/'tools/career-tab-notification-metadata-closure.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

class Memory(fixture.Memory):
    def __init__(self):
        super().__init__('success');self.nodes=[probe.ENTRY,(0x17AC401,0x17AC49C,0x256F8D8),(0x17AC49C,0x17AC4B0,0x256F8E8)]
        self.nodes += [(0x17AC4B0+i*0x80,0x17AC530+i*0x80,0x256F900+i*0x10)for i in range(5)]
        self.window=b''.join(struct.pack('<III',*node)for node in self.nodes)
        self.data={probe.ENTRY[2]:probe.ENTRY_UW}
        for b,e,u in self.nodes[1:]:self.data[u]=b'\x21\0\0\0'+struct.pack('<III',*probe.ENTRY)if b<0x17AC4B0 else b'\x01\0\0\0'
    def read(self,address,n):
        rva=address-self.game
        if rva==probe.RF_RVA or rva in self.data:
            self.reads.append((address,n))
            if rva==probe.RF_RVA:assert n==96;return self.window
            raw=self.data[rva];assert n in (4,len(raw));return raw[:n]
        return super().read(address,n)

class Scenario(fixture.Scenario):
    def __init__(self):super().__init__('success');self.memory=Memory()

class ClosureTests(unittest.TestCase):
    def test_fixed8_two_targets_same_entry_and_first_foreign(self):
        with tempfile.TemporaryDirectory() as temp:
            s=Scenario();result=probe.run(Path(temp)/'capture',s.dependencies(),fixture.fixture.fixture.fixture.Clock())
            m=json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual(m['same_entry_ranges_within_fixed8'],[[0x17AC3E0,0x17AC4B0]])
            self.assertEqual(m['first_foreign_RF']['begin'],0x17AC4B0)
            self.assertTrue(m['all_known_targets_same_entry']);self.assertEqual(len(m['exception_records']),8)
            self.assertEqual(s.memory.body_reads_count,0);self.assertTrue(m['metadata_only'])
            self.assertFalse(m['helpers_followed']);self.assertFalse(m['native_called'])
            self.assertEqual(m['budget']['read_calls'],len(s.memory.reads));self.assertEqual(m['budget']['query_calls'],len(s.memory.queries))
            self.assertLessEqual(m['budget']['bytes_requested'],16384);self.assertLessEqual(m['budget']['read_calls'],64)
            self.assertTrue(s.memory.closed);print('OWNED '+json.dumps({'status':'PASS','ranges':m['same_entry_ranges_within_fixed8'],'budget':m['budget']}))

if __name__=='__main__':unittest.main()
