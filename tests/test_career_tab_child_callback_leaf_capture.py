"""One new fixed32 leaf owned fixture; imported old fixtures are not run."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import test_career_tab_notification_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_tab_child_callback_leaf',ROOT/'tools/career-tab-child-callback-leaf-capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class Memory(fixture.Memory):
    def __init__(self):
        super().__init__('success');self.begin,self.end=probe.BEGIN,probe.END
        self.payload_reads=0;self.body_reads_count=0
    def query(self,address):
        if address in (self.game+probe.parent.CALLER,self.game+probe.PAIR_RVA):
            self.queries.append(address)
            return {'base':self.game,'size':probe.parent.base.IMAGE_SIZE,'state':0x1000,'type':0x1000000,'protect':0x20}
        return super().query(address)
    def read(self,address,n):
        rva=address-self.game
        if rva in (probe.parent.CALLER,probe.PAIR_RVA,probe.RF_RVA,probe.BEGIN):
            self.reads.append((address,n))
            if rva==probe.parent.CALLER:assert n==5;return probe.parent.CALL_PIN
            if rva==probe.PAIR_RVA:assert n==len(probe.PAIR_PIN);return probe.PAIR_PIN
            if rva==probe.RF_RVA:assert n==len(probe.RF_PIN);return probe.RF_PIN
            assert n==32;self.payload_reads+=1;self.body_reads_count+=1;return b'\xC3'+b'\xCC'*31
        return super().read(address,n)


class Scenario(fixture.Scenario):
    def __init__(self):super().__init__('success');self.memory=Memory()


class LeafTests(unittest.TestCase):
    def test_registered_fixed32_only_with_parent_pair_and_rf_boundaries(self):
        with tempfile.TemporaryDirectory()as temp:
            s=Scenario();result=probe.run(Path(temp)/'capture',s.dependencies(),lambda:0.0)
            m=json.loads(Path(result['json_path']).read_text('utf8'));raw=Path(result['binary_path']).read_bytes()
            self.assertEqual(s.memory.payload_reads,2)
            self.assertEqual(raw,probe.RF_PIN+b'\xC3'+b'\xCC'*31)
            self.assertTrue(m['parent_pair_before_after_match']);self.assertTrue(m['RF_boundary_before_after_match'])
            self.assertEqual(m['body']['length'],32)
            self.assertFalse(m['window_is_function_declaration']);self.assertFalse(m['leaf_abi_proven'])
            self.assertFalse(m['foreign_body_read']);self.assertFalse(m['helpers_followed'])
            self.assertFalse(m['native_called']);self.assertFalse(m['native_written']);self.assertTrue(s.memory.closed)
            self.assertEqual(m['budget']['read_calls'],len(s.memory.reads))
            self.assertEqual(m['budget']['query_calls'],len(s.memory.queries))
            self.assertEqual(m['budget']['bytes_requested'],sum(n for a,n in s.memory.reads))
            self.assertLessEqual(m['budget']['bytes_requested'],16384);self.assertLessEqual(m['budget']['read_calls'],64)
            self.assertTrue(all(n==32 for a,n in s.memory.reads if a==s.memory.game+probe.BEGIN))
            self.assertFalse(any(a==s.memory.game+probe.END for a,n in s.memory.reads))
            print('OWNED '+json.dumps({'status':'PASS','budget':m['budget'],'window':[probe.BEGIN,probe.END]}))

if __name__=='__main__':unittest.main()
