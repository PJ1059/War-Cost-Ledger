"""One targeted owned fixture group; no Game process access."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import test_hit_contact_forwarder_code_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_career_tab_metadata',ROOT/'tools/career-tab-initializer-metadata-capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
OLD_LIMITS=(fixture.forwarder.MAX_READS,fixture.forwarder.MAX_BYTES)
RESULTS=[]


class Memory(fixture.Memory):
    def __init__(self,mode):
        super().__init__(state=2 if mode=='not_ship' else 3)
        self.mode,self.pin_reads=mode,0
        self.begin,self.end=probe.TARGET_RVA-0x20,probe.TARGET_RVA+0x690
        self.uw={0x2513000:b'\x21\0\0\0'+struct.pack('<III',self.begin-0x200,self.begin-0x100,0x2513100),
                 0x2513100:b'\x09\0\0\0'+struct.pack('<I',0x21044A0)}

    def query(self,address):
        if address==self.game+probe.CALLER:
            self.queries.append(address)
            return {'base':self.game,'size':probe.base.IMAGE_SIZE,'state':0x1000,'type':0x1000000,'protect':0x20}
        return super().query(address)

    def read(self,address,n):
        rva=address-self.game
        pdata=probe.base.EXCEPTION_RVA<=rva<rva+n<=probe.base.EXCEPTION_RVA+probe.base.EXCEPTION_SIZE
        if rva==probe.CALLER or pdata or rva in self.uw:
            self.reads.append((address,n))
            if rva==probe.CALLER:
                assert n==5;self.pin_reads+=1
                return bytes(5) if self.mode=='changed_pin' and self.pin_reads==2 else probe.CALL_PIN
            if rva in self.uw:
                assert n in (4,len(self.uw[rva]));return self.uw[rva][:n]
            assert n==12
            index=(rva-probe.base.EXCEPTION_RVA)//12
            begin,end=(index+1)*0x100,(index+2)*0x100
            if begin==probe.TARGET_RVA&~0xFF:begin,end=self.begin,self.end
            return struct.pack('<III',begin,end,0x2513000)
        return super().read(address,n)


class Scenario(fixture.Scenario):
    def __init__(self,mode):super().__init__();self.memory=Memory(mode)
    def dependencies(self):
        deps=super().dependencies();resolve,open_process=deps['resolve_game'],deps['Process']
        deps.update(game_processes=lambda:(probe.EXPECTED_PID,),
                    resolve_game=lambda pid:resolve(54321) if pid==probe.EXPECTED_PID else None,
                    Process=lambda pid:open_process(54321) if pid==probe.EXPECTED_PID else None)
        return deps


class TabMetadataTests(unittest.TestCase):
    def test_only_metadata_and_call_ship_gates(self):
        for mode,reason in (('success',None),('changed_pin','SOURCE_CHANGED_AFTER'),('not_ship','EXPECTS_SHIP_ONLY')):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                s=Scenario(mode);out=Path(temp)/'capture'
                if reason:
                    with self.assertRaisesRegex(ValueError,reason):probe.run(out,s.dependencies(),fixture.fixture.Clock())
                    self.assertFalse((out/'metadata.bin').exists())
                    meta=json.loads((out/'metadata.incomplete.json').read_text('utf8'))
                    self.assertFalse(meta['complete'])
                else:
                    status=probe.run(out,s.dependencies(),fixture.fixture.Clock())
                    meta=json.loads(Path(status['json_path']).read_text('utf8'));raw=Path(status['binary_path']).read_bytes()
                    self.assertEqual((meta['function_begin'],meta['function_end']),(s.memory.begin,s.memory.end))
                    self.assertEqual(len(raw),12+16+8)
                    self.assertEqual(len(meta['unwind_nodes']),2)
                    self.assertEqual(meta['unwind_nodes'][1]['handler_rva'],0x21044A0)
                    self.assertEqual(meta['metadata_readiness'],'WITHHELD_UNKNOWN_LAYOUT')
                    self.assertEqual(meta['unknowns'],[{'rva':0x2513108,'reason':'OPAQUE_HANDLER_DATA_NOT_READ'}])
                    for key in ('initializer_instructions_read','handler_code_read','opaque_handler_data_read',
                                'callback_registration_proven','normal_tab_input_consumer_proven','logical_function_complete'):
                        self.assertFalse(meta[key])
                    self.assertTrue(meta['fresh_gates_verified'])
                self.assertEqual(s.memory.body_reads(),[])
                self.assertFalse(any(a==s.memory.game+0x2513108 for a,n in s.memory.reads))
                self.assertTrue(s.memory.closed)
                budget=meta['budget']
                self.assertEqual(budget['read_calls'],len(s.memory.reads))
                self.assertEqual(budget['query_calls'],len(s.memory.queries))
                self.assertEqual(budget['bytes_requested'],sum(n for a,n in s.memory.reads))
                self.assertLessEqual(budget['read_calls'],64);self.assertLessEqual(budget['query_calls'],64)
                self.assertLessEqual(budget['bytes_requested'],16384)
                self.assertEqual((fixture.forwarder.MAX_READS,fixture.forwarder.MAX_BYTES),OLD_LIMITS)
                RESULTS.append({'case':mode,'status':'PASS','budget':budget,'binary_saved':not bool(reason)})
        print('OWNED '+json.dumps(RESULTS))


if __name__=='__main__':unittest.main()
