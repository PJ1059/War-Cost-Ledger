"""One new actual317 callback focused group; no Game or old-test execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import test_career_tab_child_callback_leaf_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_tab_callback_actual317',ROOT/'tools/career-tab-child-callback-implementation-capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
RESULTS=[]


class Memory(fixture.Memory):
    def __init__(self,mode):
        super().__init__();self.mode=mode;self.begin,self.end=probe.BEGIN,probe.END
        self.payload_reads,self.body_reads_count=0,0
    def query(self,address):
        if address==self.game+probe.JMP_RVA:
            self.queries.append(address)
            return {'base':self.game,'size':probe.parent.base.IMAGE_SIZE,'state':0x1000,'type':0x1000000,'protect':0x20}
        return super().query(address)
    def read(self,address,n):
        rva=address-self.game;uw=dict(probe.UW_PINS)
        if rva in (probe.JMP_RVA,probe.PAIR_RVA,probe.RF_RVA,probe.BEGIN)or rva in uw:
            self.reads.append((address,n))
            if rva==probe.JMP_RVA:assert n==5;return probe.JMP_PIN
            if rva==probe.PAIR_RVA:
                assert n==31;return bytes(31)if self.mode=='PIN_rejected'else probe.PAIR_PIN
            if rva==probe.RF_RVA:assert n==24;return probe.RF_PIN
            if rva in uw:assert n==16;return uw[rva]
            assert n==317;self.payload_reads+=1;self.body_reads_count+=1;return b'\x90'*316+b'\xC3'
        return super().read(address,n)


class Scenario(fixture.Scenario):
    def __init__(self,mode):super().__init__();self.memory=Memory(mode);self.start_queries=0
    def dependencies(self):
        deps=super().dependencies();resolve,process=deps['resolve_game'],deps['Process']
        def fresh(pid):
            assert pid==1632;return {**resolve(27268),'exe_path':probe.EXPECTED_PATH}
        def creation(pid):
            assert pid==1632;self.start_queries+=1;return probe.EXPECTED_CREATION_TICK
        deps.update(game_processes=lambda:(1632,),resolve_game=fresh,Process=lambda _:process(27268),
                    process_creation_tick=creation)
        return deps


class ImplementationTests(unittest.TestCase):
    def test_only_actual317_body_and_registered_pair_PIN_rejection(self):
        for mode in ('success','PIN_rejected'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory()as temp:
                s=Scenario(mode);out=Path(temp)/'capture'
                if mode=='PIN_rejected':
                    with self.assertRaisesRegex(ValueError,'PARENT_PAIR_CHANGED'):
                        probe.run(out,s.dependencies(),lambda:0.0)
                    self.assertFalse((out/'metadata.bin').exists());self.assertEqual(s.memory.payload_reads,0)
                    m=json.loads((out/'metadata.incomplete.json').read_text('utf8'))
                else:
                    result=probe.run(out,s.dependencies(),lambda:0.0)
                    m=json.loads(Path(result['json_path']).read_text('utf8'));raw=Path(result['binary_path']).read_bytes()
                    self.assertEqual(s.memory.payload_reads,2);self.assertEqual(raw[56:],b'\x90'*316+b'\xC3')
                    self.assertTrue(m['RF_UW_before_after_match']);self.assertTrue(m['body_before_after_match'])
                    self.assertEqual(m['identity']['process_creation_time_filetime'],probe.EXPECTED_CREATION_TICK)
                    self.assertEqual(s.start_queries,2);self.assertEqual(m['selected_RF_index'],96794)
                self.assertFalse(m['native_called']);self.assertFalse(m['native_written']);self.assertTrue(s.memory.closed)
                self.assertEqual(m['budget']['read_calls'],len(s.memory.reads))
                self.assertEqual(m['budget']['query_calls'],len(s.memory.queries))
                self.assertEqual(m['budget']['bytes_requested'],sum(n for a,n in s.memory.reads))
                self.assertLessEqual(m['budget']['bytes_requested'],16384);self.assertLessEqual(m['budget']['read_calls'],64)
                self.assertFalse(any(a==s.memory.game+0x17AF160 for a,n in s.memory.reads))
                RESULTS.append({'case':mode,'status':'PASS','budget':m['budget'],'creation_queries':s.start_queries})
        print('OWNED '+json.dumps(RESULTS))

if __name__=='__main__':unittest.main()
