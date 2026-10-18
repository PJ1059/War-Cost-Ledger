"""Focused new owned tail/source/metadata/reservation fixtures; no Game."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_hit_world_update_contact_callsite_capture as previous

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_consume_tail128',ROOT/'tools/hit-contact-consume-tail-capture.py')
capture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
PARENT_PIN,FIELD_PIN=capture.layout_source()
UW={}
for node in capture.unwind_source():
    for key in ('header','chain_entry'):
        if key in node:
            raw=bytes.fromhex(node[key]['raw_hex']);UW[(node[key]['rva'],len(raw))]=raw
TAIL=b'\x90'*127+b'\xC3'
RESULTS=[]
ORIGINAL_LIMITS=(previous.existing.forwarder.MAX_BYTES,previous.existing.forwarder.MAX_READS,
                 previous.existing.forwarder.MAX_SECONDS)


class Memory(previous.Memory):
    def __init__(self,state=2,changed=None,guard=False):
        super().__init__(state=state)
        self.changed,self.tail_guard=changed,guard
        self.tail_reads=0;self.custom_reads=[];self.seen={}
        self.allowed={(capture.PARENT_RVA,104):PARENT_PIN,(capture.FIELD_RVA,150):FIELD_PIN,
                      (capture.RECORD_RVA,12):bytes.fromhex(capture.RECORD_HEX),**UW}

    def query(self,address):
        rva=address-self.game
        if rva in (capture.PARENT_RVA,capture.FIELD_RVA,capture.TAIL_BEGIN):
            self.queries.append(address)
            if self.clock:self.clock.value+=self.delay
            return {'base':self.game,'size':capture.v1.frozen.IMAGE_SIZE,'state':0x1000,
                    'type':0x1000000,'protect':0x120 if self.tail_guard and rva==capture.TAIL_BEGIN else 0x20}
        return super().query(address)

    def read(self,address,size):
        rva=address-self.game
        if rva==capture.TAIL_BEGIN or (rva,size) in self.allowed:
            self.reads.append((address,size));self.custom_reads.append((rva,size))
            if self.clock:self.clock.value+=self.delay
            self.seen[(rva,size)]=self.seen.get((rva,size),0)+1
            if rva==capture.TAIL_BEGIN:
                assert size==128
                self.tail_reads+=1
                raw=TAIL
                change=self.changed=='tail_after' and self.tail_reads==2
            else:
                raw=self.allowed[(rva,size)]
                change=(self.changed=='layout_before' and rva==capture.FIELD_RVA
                        or self.changed=='record_before' and rva==capture.RECORD_RVA
                        or self.changed=='uw_after' and (rva,size)==(capture.DECLARATION[2],4) and self.tail_reads==2
                        or self.changed=='layout_after' and rva==capture.PARENT_RVA and self.tail_reads==2)
            return bytes((raw[0]^1,))+raw[1:] if change else raw
        if (capture.v1.frozen.EXCEPTION_RVA<=rva<capture.v1.frozen.EXCEPTION_RVA+capture.v1.frozen.EXCEPTION_SIZE
                or 0x2511400<=rva<0x2511600):
            raise AssertionError('No metadata scan or new UW address allowed')
        return super().read(address,size)


class Scenario(previous.fixture.Scenario):
    def __init__(self,**options):
        super().__init__();self.memory=Memory(**options)


class ConsumeTailTests(unittest.TestCase):
    def inspect_failure(self,folder,scenario,name,reason):
        with self.assertRaisesRegex(ValueError,reason):
            capture.run(folder,scenario.dependencies(),previous.fixture.Clock())
        self.assertEqual(list(folder.glob('*.bin')),[])
        meta=json.loads((folder/'callsite.incomplete.json').read_text('utf8'))
        self.assertFalse(meta['complete']);self.assertFalse(meta['partial_binary_saved'])
        self.assertFalse(meta['native_called']);self.assertFalse(meta['native_written'])
        self.assertTrue(scenario.memory.closed)
        self.assertLessEqual(len(scenario.memory.reads),32)
        self.assertLessEqual(sum(size for _,size in scenario.memory.reads),24576)
        RESULTS.append({'case':name,'status':'PASS','error':meta['error'],
                        'tail_reads':scenario.memory.tail_reads,'binary_saved':False})

    def test_fixed128_title_and_ship_and_unchanged_original_limits(self):
        for state in (2,3):
            with self.subTest(state=state),tempfile.TemporaryDirectory() as parent:
                scenario=Scenario(state=state)
                result=capture.run(Path(parent)/'capture',scenario.dependencies(),previous.fixture.Clock())
                meta=json.loads(Path(result['json_path']).read_text('utf8'))
                self.assertEqual(Path(result['binary_path']).read_bytes(),TAIL)
                self.assertEqual(scenario.memory.tail_reads,2)
                self.assertEqual(meta['ranges'],[{'name':'contact_consume_candidate_tail128','module':'game',
                                  'rva':0x13AF1BE,'length':128,'binary_offset':0}])
                self.assertEqual(meta['ship_before'],meta['ship_after'])
                self.assertEqual(meta['ship_before']['state'],state)
                self.assertEqual(meta['budget']['read_calls'],30)
                self.assertEqual(meta['budget']['query_calls'],30)
                self.assertEqual(meta['budget']['bytes_requested'],9132)
                self.assertEqual(meta['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(meta['budget']['query_calls'],len(scenario.memory.queries))
                self.assertEqual(meta['budget']['bytes_requested'],sum(size for _,size in scenario.memory.reads))
                self.assertEqual(meta['budget']['max_reads'],32);self.assertEqual(meta['budget']['max_bytes'],24576)
                self.assertTrue(meta['tail_before_after_match'])
                self.assertTrue(meta['fresh_layout_pins_before_after_match'])
                self.assertTrue(meta['fresh_unwind_matches_saved_source'])
                for key in ('normal_CFG_closed','logical_function_complete','classification_ready','contract_ready',
                            'count_clear_or_consume_timing_proven','runtime_object_lifetime_proven','native_called','native_written'):
                    self.assertFalse(meta[key])
                self.assertEqual(meta['heap_reads'],0);self.assertEqual(meta['extra_callee_reads'],0)
                self.assertEqual({(rva,size) for rva,size in scenario.memory.custom_reads},
                                 set(scenario.memory.allowed)|{(capture.TAIL_BEGIN,128)})
                self.assertTrue(scenario.memory.closed)
                self.assertEqual((previous.existing.forwarder.MAX_BYTES,previous.existing.forwarder.MAX_READS,
                                  previous.existing.forwarder.MAX_SECONDS),ORIGINAL_LIMITS)
                RESULTS.append({'case':'static_state_'+str(state),'status':'PASS','budget':meta['budget'],
                                'ranges':meta['ranges'],'tail_reads':2})

    def test_source_record_and_post_metadata_are_real_gates(self):
        for name,reason,body_reads in (
                ('layout_before','FRESH_LAYOUT_PIN_CHANGED',0),('record_before','FRESH_RECORD_CHANGED',0),
                ('uw_after','FRESH_UW_CHANGED',2),('layout_after','FRESH_LAYOUT_PIN_CHANGED',2)):
            with self.subTest(case=name),tempfile.TemporaryDirectory() as parent:
                scenario=Scenario(changed=name)
                self.inspect_failure(Path(parent)/'capture',scenario,name,reason)
                self.assertEqual(scenario.memory.tail_reads,body_reads)

    def test_window_match_readability_and_upfront_reservation(self):
        for name,options,reason,limit in (
                ('tail_after',{'changed':'tail_after'},'WINDOW_CHANGED_DURING_CAPTURE',None),
                ('tail_guard',{'guard':True},'REGION_UNREADABLE',None),
                ('reserve_29IO',{},'READ_BUDGET',29)):
            with self.subTest(case=name),tempfile.TemporaryDirectory() as parent:
                scenario=Scenario(**options);folder=Path(parent)/'capture'
                if limit is not None:
                    with patch.object(capture.v1,'MAX_READS',limit):
                        self.inspect_failure(folder,scenario,name,reason)
                    self.assertEqual(scenario.memory.tail_reads,0)
                else:self.inspect_failure(folder,scenario,name,reason)


def tearDownModule():
    folder=ROOT/'dist/hit-contact-consume-tail-owned-20261013-v1'
    folder.mkdir(exist_ok=True)
    out={'status':'PASS' if len(RESULTS)==9 else 'FAIL','groups':3,'cases':RESULTS,
         'tool_sha256':hashlib.sha256((ROOT/'tools/hit-contact-consume-tail-capture.py').read_bytes()).hexdigest(),
         'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'Game_accessed':False,'old_suites_run':False,'production_modified':False}
    (folder/'verification.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')


if __name__=='__main__':unittest.main()
