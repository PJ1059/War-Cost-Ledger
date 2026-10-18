"""One new body-only owned group; no metadata group rerun or Game access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import test_career_tab_initializer_metadata_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_career_tab_body',ROOT/'tools/career-tab-initializer-body-capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
PIN,_=probe.material()
RESULTS=[]


class Memory(fixture.Memory):
    def __init__(self,mode):
        super().__init__('success');self.mode=mode;self.begin,self.end=probe.BEGIN,probe.END
        self.counts={};self.body=b'\x90'*probe.BODY_BYTES
    def read(self,address,n):
        rva=address-self.game
        if rva not in (probe.RF_RVA,probe.UW_RVA,probe.BEGIN):return super().read(address,n)
        self.reads.append((address,n));self.counts[rva]=self.counts.get(rva,0)+1
        if rva==probe.RF_RVA:
            assert n==12;raw=PIN[:12]
            if self.mode=='RF_post_changed'and self.counts[rva]==2:raw=raw[:-1]+bytes((raw[-1]^1,))
        elif rva==probe.UW_RVA:
            assert n==52;raw=PIN[12:]
            if self.mode=='UW_PIN_changed':raw=bytes((raw[0]^1,))+raw[1:]
        else:
            assert n==3163;raw=self.body
            if self.mode=='body_post_changed'and self.counts[rva]==2:raw=bytes((raw[0]^1,))+raw[1:]
        return raw


class Scenario(fixture.Scenario):
    def __init__(self,mode):super().__init__('success');self.memory=Memory(mode)


class TabBodyTests(unittest.TestCase):
    def test_fixed_double_body_and_parent_gates(self):
        for mode,reason in (('success',None),('UW_PIN_changed','UW_PIN_CHANGED_BEFORE'),
                            ('RF_post_changed','RF_CHANGED_AFTER'),('body_post_changed','BODY_CHANGED_AFTER')):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temp:
                s=Scenario(mode);out=Path(temp)/'capture'
                if reason:
                    with self.assertRaisesRegex(ValueError,reason):probe.run(out,s.dependencies(),fixture.fixture.fixture.Clock())
                    self.assertEqual(list(out.glob('*.bin')),[])
                    m=json.loads((out/'metadata.incomplete.json').read_text('utf8'))
                else:
                    status=probe.run(out,s.dependencies(),fixture.fixture.fixture.Clock())
                    m=json.loads(Path(status['json_path']).read_text('utf8'))
                    self.assertEqual(Path(status['binary_path']).read_bytes(),s.memory.body)
                    self.assertTrue(m['body_before_after_match']);self.assertTrue(m['parent_RF_UW_before_after_match'])
                    self.assertEqual((m['function_begin'],m['function_end']),(probe.BEGIN,probe.END))
                    self.assertEqual(m['ranges'],[{'kind':'actual_initializer_body','rva':probe.BEGIN,'length':3163,'binary_offset':0}])
                reads=[(a-s.memory.game,n)for a,n in s.memory.reads if a==s.memory.game+probe.BEGIN]
                self.assertEqual(reads,[]if mode=='UW_PIN_changed'else[(probe.BEGIN,3163)]*2)
                self.assertFalse(any(a==s.memory.game+probe.UW_RVA+52 for a,n in s.memory.reads))
                self.assertTrue(s.memory.closed)
                budget=m['budget'];self.assertEqual(budget['read_calls'],len(s.memory.reads))
                self.assertEqual(budget['query_calls'],len(s.memory.queries))
                self.assertEqual(budget['bytes_requested'],sum(n for a,n in s.memory.reads))
                self.assertLessEqual(budget['read_calls'],64);self.assertLessEqual(budget['bytes_requested'],16384)
                self.assertFalse(m['native_called']);self.assertFalse(m['native_written'])
                RESULTS.append({'case':mode,'status':'PASS','body_reads':reads,'budget':budget})
        print('OWNED '+json.dumps(RESULTS))


if __name__=='__main__':unittest.main()
