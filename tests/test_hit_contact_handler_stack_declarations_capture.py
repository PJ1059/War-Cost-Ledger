"""Only new two-target declaration cases; no Game or old-suite run."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import test_hit_contact_consume_tail_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_handler_stack',
    ROOT/'tools/hit-contact-handler-stack-declarations-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
OLD_LIMITS=(fixture.capture.v1.frozen.MAX_READS,fixture.capture.v1.frozen.MAX_BYTES)
BASES=(0x2104400,0x2104500)


class Memory(fixture.Memory):
    def __init__(self,change=None):
        super().__init__(state=3);self.change=change;self.body_reads=0;self.body_windows=[]

    def query(self,address):
        if address-self.game in BASES:
            self.queries.append(address)
            if self.clock:self.clock.value+=self.delay
            return {'base':self.game,'size':capture.v1.frozen.IMAGE_SIZE,'state':0x1000,
                    'type':0x1000000,'protect':0x20}
        return super().query(address)

    def read(self,address,size):
        rva=address-self.game;frozen=capture.v1.frozen
        table=frozen.EXCEPTION_RVA<=rva<rva+size<=frozen.EXCEPTION_RVA+frozen.EXCEPTION_SIZE
        custom=(rva,size)==(capture.parent.BEGIN,24) or table or rva in (0x2513000,0x2513040) or rva in BASES
        if not custom:return super().read(address,size)
        self.reads.append((address,size));self.custom_reads.append((rva,size))
        if self.clock:self.clock.value+=self.delay
        if (rva,size)==(capture.parent.BEGIN,24):return capture.PREFIX
        if table:
            assert size==12;index=(rva-frozen.EXCEPTION_RVA)//12
            begin=(index+1)*0x100;end=begin+0x100;unwind=0x2513000
            if begin==BASES[0] and self.change=='large_declaration':end=begin+1280
            if begin==BASES[1]:
                unwind=0x2513040
                if self.change=='missing_stack_record':begin=end;end+=0x100
            raw=struct.pack('<III',begin,end,unwind)
            if self.change=='metadata_after' and self.body_reads==4 and begin==BASES[0]:
                return raw[:8]+struct.pack('<I',unwind+4)
            return raw
        if rva in (0x2513000,0x2513040):
            assert size==4;return b'\x01\0\0\0'
        assert rva in BASES and size==256
        self.body_reads+=1;self.body_windows.append((rva,size))
        raw=b'\x90'*255+b'\xc3'
        return raw[:-1]+b'\x90' if self.change=='body_after' and self.body_reads==2 else raw


class Scenario(fixture.previous.fixture.Scenario):
    def __init__(self,change=None):super().__init__();self.memory=Memory(change)


class HandlerStackTests(unittest.TestCase):
    def test_two_declared_bodies_or_changes_and_missing_boundaries_withhold(self):
        source=capture.validate_source()
        self.assertEqual([row['rva'] for row in source['exact_targets']],[0x21044A0,0x21045C0])
        for name,change,reason,body_reads in (
                ('success',None,None,4),('body_change','body_after','DECLARED_BODY_CHANGED',2),
                ('record_change','metadata_after','SELECTED_RECORD_CHANGED',4),
                ('over_1024','large_declaration','DECLARATION_SCOPE_OR_1024B_CAP',0),
                ('stack_without_record','missing_stack_record','FUNCTION_NOT_FOUND',0)):
            with self.subTest(case=name),tempfile.TemporaryDirectory() as temp:
                scenario=Scenario(change);folder=Path(temp)/'capture'
                if reason:
                    with self.assertRaisesRegex(ValueError,reason):
                        capture.run(folder,scenario.dependencies(),fixture.previous.fixture.Clock())
                    self.assertEqual(list(folder.glob('*.bin')),[])
                    meta=json.loads((folder/'callsite.incomplete.json').read_text('utf8'))
                    self.assertFalse(meta['complete']);self.assertFalse(meta['partial_binary_saved'])
                else:
                    status=capture.run(folder,scenario.dependencies(),fixture.previous.fixture.Clock())
                    meta=json.loads(Path(status['json_path']).read_text('utf8'))
                    self.assertEqual(Path(status['binary_path']).read_bytes(),(b'\x90'*255+b'\xc3')*2)
                    self.assertEqual(meta['ranges'],[{'name':name,'module':'game','rva':begin,
                        'length':256,'binary_offset':offset} for (name,_),begin,offset in
                        zip(capture.TARGETS,BASES,(0,256))])
                    self.assertTrue(meta['fixed_source_pins_before_after_match'])
                    self.assertTrue(meta['selected_records_before_after_match'])
                    self.assertTrue(meta['unwind_headers_and_chains_before_after_match'])
                    self.assertTrue(meta['fresh_gates_verified'])
                    self.assertEqual(meta['ship_before'],meta['ship_after'])
                    self.assertTrue(all(row['declared_code_complete'] for row in meta['targets']))
                self.assertEqual(scenario.memory.body_reads,body_reads)
                self.assertTrue(all(size<=1024 for _,size in scenario.memory.body_windows))
                self.assertEqual(scenario.memory.tail_reads,0)
                self.assertEqual(meta['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(meta['budget']['query_calls'],len(scenario.memory.queries))
                self.assertEqual(meta['budget']['bytes_requested'],sum(size for _,size in scenario.memory.reads))
                self.assertLessEqual(meta['budget']['read_calls'],96)
                self.assertLessEqual(meta['budget']['bytes_requested'],24576)
                self.assertEqual(meta['budget']['max_reads'],96);self.assertEqual(meta['budget']['max_bytes'],24576)
                for row in meta['targets']:self.assertLessEqual(len(row['exception_records']),20)
                for key in ('target_symbol_identity_proven','stackprobe_identity_proven','GS_handler_identity_proven',
                            'sibling_code_read','handler_data_extended','logical_function_complete','normal_CFG_closed',
                            'classification_ready','contract_ready','native_called','native_written'):
                    self.assertFalse(meta[key])
                self.assertEqual(meta['heap_reads'],0);self.assertEqual(meta['extra_callee_reads'],0)
                self.assertTrue(scenario.memory.closed)
                self.assertEqual((fixture.capture.v1.frozen.MAX_READS,fixture.capture.v1.frozen.MAX_BYTES),OLD_LIMITS)
                print('OWNED_BUDGET '+json.dumps({'case':name,'Game_accessed':False,'old_suites_run':False,
                    'body_reads':body_reads,'binary_saved':not bool(reason),'budget':meta['budget']}))


if __name__=='__main__':unittest.main()
