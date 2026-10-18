"""Only the new target/source and fixed8-to-body transition, owned memory."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import test_career_tab_notification_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_tab_child_registration',ROOT/'tools/career-tab-child-registration-capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
RESULTS=[]


class Memory(fixture.Memory):
    def __init__(self,mode):
        super().__init__('success');self.mode=mode
        self.begin,self.end=probe.TARGET,probe.TARGET+0x100
        self.index=(probe.TARGET&~0xFF)//0x100-1
        self.rf_rva=probe.parent.base.EXCEPTION_RVA+self.index*12
        self.nodes=[(self.begin,self.end,0x2516000)]
        self.nodes += [(self.end+i*0x100,self.end+(i+1)*0x100,0x2516100+i*4)for i in range(7)]
        self.window=b''.join(struct.pack('<III',*row)for row in self.nodes)
        self.uw={u:b'\x01\0\0\0'for b,e,u in self.nodes}
        self.source_reads,self.body_reads_count=0,0
    def query(self,address):
        if address==self.game+probe.CALLER:
            self.queries.append(address)
            return {'base':self.game,'size':probe.parent.base.IMAGE_SIZE,'state':0x1000,'type':0x1000000,'protect':0x20}
        return super().query(address)
    def read(self,address,n):
        rva=address-self.game
        pdata=probe.parent.base.EXCEPTION_RVA<=rva<rva+n<=probe.parent.base.EXCEPTION_RVA+probe.parent.base.EXCEPTION_SIZE
        if rva==probe.CALLER or pdata or rva in self.uw or rva==self.begin:
            self.reads.append((address,n))
            if rva==probe.CALLER:
                assert n==5;self.source_reads+=1
                return bytes(5)if self.mode=='source_changed'and self.source_reads==2 else probe.CALL_PIN
            if rva in self.uw:assert n==4;return self.uw[rva]
            if rva==self.begin:
                assert n==0x100;self.body_reads_count+=1;return b'\x90'*0xFF+b'\xC3'
            if n==96:assert rva==self.rf_rva;return self.window
            assert n==12
            index=(rva-probe.parent.base.EXCEPTION_RVA)//12
            b,e,u=(index+1)*0x100,(index+2)*0x100,0x2516000
            if index==self.index:b,e,u=self.nodes[0]
            return struct.pack('<III',b,e,u)
        return super().read(address,n)


class Scenario(fixture.Scenario):
    def __init__(self,mode):super().__init__('success');self.memory=Memory(mode)


class ChildRegistrationTests(unittest.TestCase):
    def test_new_source_fixed8_boundary_then_only_own_body(self):
        for mode in ('success','source_changed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                s=Scenario(mode);out=Path(temp)/'capture'
                if mode=='source_changed':
                    with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_AFTER'):
                        probe.run(out,s.dependencies(),lambda:0.0)
                    self.assertFalse((out/'metadata.bin').exists())
                    m=json.loads((out/'metadata.incomplete.json').read_text('utf8'))
                else:
                    result=probe.run(out,s.dependencies(),lambda:0.0)
                    m=json.loads(Path(result['json_path']).read_text('utf8'))
                    raw=Path(result['binary_path']).read_bytes()
                    self.assertTrue(m['body_captured']);self.assertTrue(m['full_fixed_RF_UW_after_body_match'])
                    self.assertEqual(m['same_entry_ranges_within_fixed8'],[[probe.TARGET,probe.TARGET+0x100]])
                    self.assertEqual(m['first_foreign_RF']['begin'],probe.TARGET+0x100)
                    self.assertEqual(m['selected_runtime_function']['index'],s.memory.index)
                    self.assertEqual(raw[m['body']['binary_offset']:],b'\x90'*0xFF+b'\xC3')
                    self.assertEqual(m['source']['target_rva'],probe.TARGET)
                    self.assertEqual(m['caller_pin_before_after'],probe.CALL_PIN.hex())
                self.assertEqual(s.memory.body_reads_count,2)
                self.assertFalse(m['native_called']);self.assertFalse(m['native_written'])
                self.assertFalse(m['helpers_followed']);self.assertFalse(m['input_values_read'])
                self.assertFalse(m['logical_function_complete']);self.assertTrue(s.memory.closed)
                self.assertEqual(m['budget']['read_calls'],len(s.memory.reads))
                self.assertEqual(m['budget']['query_calls'],len(s.memory.queries))
                self.assertLessEqual(m['budget']['bytes_requested'],32768)
                self.assertLessEqual(m['budget']['read_calls'],128)
                self.assertLessEqual(m['budget']['query_calls'],128)
                self.assertFalse(any(a==s.memory.game+s.memory.end and n>12 for a,n in s.memory.reads))
                RESULTS.append({'case':mode,'status':'PASS','budget':m['budget'],'binary_saved':mode=='success'})
        print('OWNED '+json.dumps(RESULTS))

if __name__=='__main__':unittest.main()
