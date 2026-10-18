"""One new owned group: whole-body or fragment/budget withholding."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import test_career_tab_initializer_metadata_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_tab_notification',ROOT/'tools/career-tab-notification-capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
RESULTS=[]


class Memory(fixture.Memory):
    def __init__(self,mode):
        super().__init__('success');self.mode=mode
        self.begin,self.end=probe.TARGET,probe.TARGET+(4096 if mode=='budget' else 0x120)
        self.uw={0x2513000:b'\x01\0\0\0'};self.body_reads_count=0
        if mode=='chain':
            self.uw={0x2513000:b'\x21\0\0\0'+struct.pack('<III',self.begin-0x100,self.begin-0x80,0x2513100),
                     0x2513100:b'\x01\0\0\0'}
    def query(self,address):
        if address==self.game+probe.CALLER:
            self.queries.append(address)
            return {'base':self.game,'size':probe.parent.base.IMAGE_SIZE,'state':0x1000,'type':0x1000000,'protect':0x20}
        return super().query(address)
    def read(self,address,n):
        rva=address-self.game
        pdata=probe.parent.base.EXCEPTION_RVA<=rva<rva+n<=probe.parent.base.EXCEPTION_RVA+probe.parent.base.EXCEPTION_SIZE
        if rva==probe.CALLER or pdata or rva==self.begin:
            self.reads.append((address,n))
            if rva==probe.CALLER:assert n==5;return probe.CALL_PIN
            if rva==self.begin:assert n==self.end-self.begin;self.body_reads_count+=1;return b'\x90'*n
            assert n==12
            index=(rva-probe.parent.base.EXCEPTION_RVA)//12;b,e=(index+1)*0x100,(index+2)*0x100
            if b==probe.TARGET&~0xFF:b,e=self.begin,self.end
            return struct.pack('<III',b,e,0x2513000)
        return super().read(address,n)


class Scenario(fixture.Scenario):
    def __init__(self,mode):super().__init__('success');self.memory=Memory(mode)
    def dependencies(self):
        deps=super().dependencies();resolve,process=deps['resolve_game'],deps['Process']
        deps.update(game_processes=lambda:(27268,),resolve_game=lambda _:resolve(67988),Process=lambda _:process(67988))
        return deps


class NotificationTests(unittest.TestCase):
    def test_only_complete_single_body_and_metadata_on_withholding(self):
        for mode in ('success','chain','budget'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                s=Scenario(mode);status=probe.run(Path(temp)/'capture',s.dependencies(),fixture.fixture.fixture.Clock())
                m=json.loads(Path(status['json_path']).read_text('utf8'));raw=Path(status['binary_path']).read_bytes()
                self.assertTrue(m['complete']);self.assertTrue(m['fresh_gates_verified'])
                self.assertEqual((m['function_begin'],m['function_end']),(s.memory.begin,s.memory.end))
                if mode=='success':
                    self.assertTrue(m['body_captured']);self.assertEqual(s.memory.body_reads_count,2)
                    self.assertEqual(raw[m['body']['binary_offset']:],b'\x90'*0x120)
                    self.assertTrue(m['RF_UW_before_after_body_match'])
                else:
                    self.assertFalse(m['body_captured']);self.assertEqual(s.memory.body_reads_count,0)
                    self.assertTrue(m['metadata_only'])
                    self.assertEqual(m['body_readiness'],'WITHHELD_FRAGMENT_OR_STANDARD_BOUNDARY'if mode=='chain'else'WITHHELD_BODY_BUDGET')
                self.assertFalse(m['native_called']);self.assertFalse(m['native_written'])
                self.assertFalse(m['input_values_read']);self.assertFalse(m['helpers_followed'])
                self.assertEqual(m['budget']['read_calls'],len(s.memory.reads));self.assertEqual(m['budget']['query_calls'],len(s.memory.queries))
                self.assertLessEqual(m['budget']['bytes_requested'],16384);self.assertTrue(s.memory.closed)
                RESULTS.append({'case':mode,'status':'PASS','body_readiness':m['body_readiness'],'budget':m['budget']})
        print('OWNED '+json.dumps(RESULTS))

if __name__=='__main__':unittest.main()
