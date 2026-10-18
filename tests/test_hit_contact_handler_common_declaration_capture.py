"""Only the new anchored-middle/common-body profile cases, no Game."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import test_hit_contact_consume_tail_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_common_handler',
    ROOT/'tools/hit-contact-handler-common-declaration-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
OLD_LIMITS=(fixture.capture.v1.frozen.MAX_READS,fixture.capture.v1.frozen.MAX_BYTES)
COMMON_END,UW=0x210451C,0x263A8B8


class Memory(fixture.Memory):
    def __init__(self,change=None):
        super().__init__(state=3);self.change=change;self.body_reads=0;self.table_reads=0
        middle=struct.pack('<III',capture.TARGET,COMMON_END,UW)
        if change=='middle_gap':middle=struct.pack('<III',capture.TARGET+4,COMMON_END,UW)
        self.table=bytes.fromhex(capture.ANCHORS[152455])+middle+bytes.fromhex(capture.ANCHORS[152457])
        self.body=b'\x90'*(COMMON_END-capture.TARGET-1)+b'\xc3'

    def query(self,address):
        if address-self.game in (capture.HANDLER_RVA,capture.TARGET):
            self.queries.append(address)
            if self.clock:self.clock.value+=self.delay
            return {'base':self.game,'size':capture.v1.frozen.IMAGE_SIZE,'state':0x1000,
                    'type':0x1000000,'protect':0x20}
        return super().query(address)

    def read(self,address,size):
        rva=address-self.game
        custom=((rva,size) in ((0x25114C0,24),(capture.HANDLER_RVA,29),
            (capture.WINDOW_RVA,36),(UW,4),(capture.TARGET,len(self.body))))
        if not custom:return super().read(address,size)
        self.reads.append((address,size));self.custom_reads.append((rva,size))
        if self.clock:self.clock.value+=self.delay
        if (rva,size)==(0x25114C0,24):return capture.parent.source_pins()[0]
        if rva==capture.HANDLER_RVA:return capture.source()
        if rva==UW:return b'\x01\0\0\0'
        if rva==capture.WINDOW_RVA:
            self.table_reads+=1
            if self.change=='anchor':return bytes((self.table[0]^1,))+self.table[1:]
            return self.table
        self.body_reads+=1
        return self.body[:-1]+b'\x90' if self.change=='body_after' and self.body_reads==2 else self.body


class Scenario(fixture.previous.fixture.Scenario):
    def __init__(self,change=None):super().__init__();self.memory=Memory(change)


class CommonHandlerTests(unittest.TestCase):
    def test_fixed_middle_and_body_or_anchor_scope_changes_withhold(self):
        self.assertEqual(capture.validate_source()['common_handler_source']['target_rva'],capture.TARGET)
        for name,change,reason,body_reads in (
                ('success',None,None,2),('anchor_change','anchor','FRESH_ANCHOR_CHANGED',0),
                ('middle_not_containing_target','middle_gap','MIDDLE_TARGET_SCOPE_OR_1024B_CAP',0),
                ('body_change','body_after','BODY_CHANGED_DURING_CAPTURE',2)):
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
                    self.assertEqual(Path(status['binary_path']).read_bytes(),scenario.memory.body)
                    self.assertEqual(meta['ranges'],[{'name':'contact_handler_common_actual_declaration',
                        'module':'game','rva':capture.TARGET,'length':92,'binary_offset':0}])
                    self.assertEqual(meta['selected_record']['index'],152456)
                    self.assertTrue(meta['known_source_pins_before_after_match'])
                    self.assertTrue(meta['window_before_after_match'])
                    self.assertTrue(meta['unwind_headers_and_chains_before_after_match'])
                    self.assertTrue(meta['body_before_after_match']);self.assertTrue(meta['fresh_gates_verified'])
                    self.assertEqual(scenario.memory.table_reads,2)
                    self.assertEqual(meta['budget']['read_calls'],20)
                    self.assertEqual(meta['budget']['bytes_requested'],8818)
                self.assertEqual(scenario.memory.body_reads,body_reads)
                self.assertEqual(scenario.memory.tail_reads,0)
                tables=[(rva,size) for rva,size in scenario.memory.custom_reads
                    if capture.v1.frozen.EXCEPTION_RVA<=rva<capture.v1.frozen.EXCEPTION_RVA+capture.v1.frozen.EXCEPTION_SIZE]
                self.assertEqual(tables,[(capture.WINDOW_RVA,36)]*scenario.memory.table_reads)
                self.assertEqual(meta['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(meta['budget']['query_calls'],len(scenario.memory.queries))
                self.assertEqual(meta['budget']['bytes_requested'],sum(size for _,size in scenario.memory.reads))
                self.assertEqual(meta['budget']['max_reads'],96);self.assertEqual(meta['budget']['max_bytes'],24576)
                for key in ('pdata_search_performed','sibling_code_read','handler_data_extended',
                            'GS_handler_identity_proven','logical_function_complete','normal_CFG_closed',
                            'classification_ready','contract_ready','native_called','native_written'):
                    self.assertFalse(meta[key])
                self.assertEqual(meta['heap_reads'],0);self.assertEqual(meta['extra_callee_reads'],0)
                self.assertTrue(scenario.memory.closed)
                self.assertEqual((fixture.capture.v1.frozen.MAX_READS,fixture.capture.v1.frozen.MAX_BYTES),OLD_LIMITS)
                print('OWNED_BUDGET '+json.dumps({'case':name,'Game_accessed':False,'old_suites_run':False,
                    'body_reads':body_reads,'binary_saved':not bool(reason),'budget':meta['budget']}))


if __name__=='__main__':unittest.main()
