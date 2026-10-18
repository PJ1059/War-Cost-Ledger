"""One focused owned group for the fixed AP/physical metadata reader."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_hit_world_update_contact_callsite_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_AP_physical_fixed',
    ROOT/'tools/hit-ap-physical-clone-metadata-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
PINS,PREFIX,KNOWN=capture.sources()
OLD_LIMITS=(fixture.callsite.MAX_BYTES,fixture.callsite.MAX_READS,
            fixture.existing.forwarder.MAX_BYTES,fixture.existing.forwarder.MAX_READS)
DISPATCH_UW=0x2513000
ACTUAL_END=0x129DD20  # Deliberately neither213B code end nor244B envelope end.
RESULTS=[]


def physical_fixture():
    entries=[(0x13B0BD0,0x13B0CAC,0x2511668),(0x13B0CAC,0x13B0D0F,0x2511684),
             (0x13B0D0F,0x13B0D63,0x25116A8),(0x13B0D63,0x13B0E00,0x25116BC),
             (0x13B0E00,0x13B1084,0x25116D0),(0x13B1084,0x13B1162,0x25116F0),
             (0x13B1162,0x13B11E0,0x251170C)]
    records=b''.join(struct.pack('<III',*row)for row in entries)
    raw=bytearray(capture.PHYSICAL_UW[1])
    for i,row in enumerate(entries):
        at=row[2]-capture.PHYSICAL_UW[0]
        node=b'\x21\0\0\0'+struct.pack('<III',*entries[2 if i==5 else 0])
        raw[at:at+len(node)]=node
    for at,pin in KNOWN:
        off=at-capture.PHYSICAL_UW[0];raw[off:off+len(pin)]=pin
    assert len(raw)==180
    for index,pin in capture.ANCHORS.items():
        at=(index-capture.PHYSICAL_RF_INDEX)*12;assert records[at:at+12].hex()==pin
    return records,bytes(raw)


class Memory(fixture.Memory):
    def __init__(self,change=None):
        super().__init__(state=3);self.change=change;self.counts={};self.fixed_reads=[]
        rf,uw=physical_fixture()
        self.fixed={(capture.PHYSICAL_RF_RVA,84):rf,capture.PHYSICAL_UW:uw,
            **{(rva,len(raw)):raw for _,rva,raw,_ in PINS}}
        self.dispatcher=PREFIX+bytes(range(20))
        self.dispatch_uw=b'\x01\x10\x03\0\x10\x68\x02\0\x04\x62\0\0'
        if change=='unknown128':self.dispatch_uw=b'\x01\x10\x40\0'
        self.code_pins={rva for _,rva,raw,executable in PINS if executable}|{capture.DISPATCH_BEGIN}

    def query(self,address):
        if address-self.game in self.code_pins:
            self.queries.append(address)
            if self.clock:self.clock.value+=self.delay
            return {'base':self.game,'size':capture.v1.frozen.IMAGE_SIZE,
                    'state':0x1000,'type':0x1000000,'protect':0x20}
        return super().query(address)

    def read(self,address,size):
        rva=address-self.game;key=(rva,size);frozen=capture.v1.frozen
        table=frozen.EXCEPTION_RVA<=rva<rva+size<=frozen.EXCEPTION_RVA+frozen.EXCEPTION_SIZE
        if not(key in self.fixed or rva in (capture.DISPATCH_BEGIN,DISPATCH_UW)or table):
            return super().read(address,size)
        self.reads.append((address,size));self.fixed_reads.append(key)
        if self.clock:self.clock.value+=self.delay
        self.counts[key]=self.counts.get(key,0)+1
        if key in self.fixed:
            raw=self.fixed[key]
            if self.counts[key]==2:
                if self.change=='source_post'and key==capture.AP_UW:raw=bytes((raw[0]^1,))+raw[1:]
                if self.change=='window_post'and key==capture.PHYSICAL_UW:
                    raw=raw[:29]+bytes((raw[29]^1,))+raw[30:]
            return raw
        if rva==capture.DISPATCH_BEGIN:
            assert size==244;return self.dispatcher
        if rva==DISPATCH_UW:
            assert size in (4,len(self.dispatch_uw));return self.dispatch_uw[:size]
        assert size==12
        index=(rva-frozen.EXCEPTION_RVA)//12
        begin,end=(index+1)*0x100,(index+2)*0x100
        if begin==capture.DISPATCH_BEGIN&~0xFF:begin,end=capture.DISPATCH_BEGIN,ACTUAL_END
        return struct.pack('<III',begin,end,DISPATCH_UW)


class Scenario(fixture.fixture.Scenario):
    def __init__(self,change=None):super().__init__();self.memory=Memory(change)


class FixedAPPhysicalTests(unittest.TestCase):
    def test_fixed_packet_source_changes_and_unknown_node_bound(self):
        for name,change,reason in (('success',None,None),('post_source','source_post','FRESH_SOURCE_PIN_CHANGED'),
                ('post_window','window_post','FIXED_WINDOWS_CHANGED'),('unknown_128','unknown128',None),
                ('source_SHA_before_open','sourceSHA','SOURCE_CHANGED')):
            with self.subTest(case=name),tempfile.TemporaryDirectory()as temp:
                scenario=Scenario(change);folder=Path(temp)/'capture';clock=fixture.fixture.Clock()
                if change=='sourceSHA':
                    path,_,size=capture.SOURCES['A_bin']
                    with patch.dict(capture.SOURCES,{'A_bin':(path,'0'*64,size)}):
                        with self.assertRaisesRegex(ValueError,reason):capture.run(folder,scenario.dependencies(),clock)
                    self.assertEqual(scenario.opens,0)
                    meta=json.loads((folder/'callsite.incomplete.json').read_text('utf8'))
                    self.assertFalse(meta['complete']);self.assertEqual(list(folder.glob('*.bin')),[])
                    RESULTS.append({'case':name,'status':'PASS','process_opens':0,'binary_saved':False})
                    continue
                if reason:
                    with self.assertRaisesRegex(ValueError,reason):capture.run(folder,scenario.dependencies(),clock)
                    self.assertEqual(list(folder.glob('*.bin')),[])
                    meta=json.loads((folder/'callsite.incomplete.json').read_text('utf8'))
                    self.assertFalse(meta['complete']);self.assertFalse(meta['partial_binary_saved'])
                else:
                    result=capture.run(folder,scenario.dependencies(),clock)
                    meta=json.loads(Path(result['json_path']).read_text('utf8'))
                    raw=Path(result['binary_path']).read_bytes()
                    self.assertEqual(raw[:244],scenario.memory.dispatcher)
                    self.assertEqual(meta['dispatcher']['function_end'],ACTUAL_END)
                    self.assertNotEqual(ACTUAL_END,capture.DISPATCH_BEGIN+213)
                    self.assertNotEqual(ACTUAL_END,capture.DISPATCH_BEGIN+244)
                    self.assertTrue(meta['dispatcher']['actual_RF_end_was_not_assumed'])
                    self.assertEqual(len(meta['physical']['runtime_functions']),7)
                    self.assertTrue(meta['physical']['all_seven_standard_ancestries_closed'])
                    for key in ('dispatcher_fixed244_before_after_match','dispatcher_selected_RF_and_full_UW_before_after_match',
                            'physical_RF_UW_windows_before_after_match','all_known_AP_physical_contact_pins_before_after_match',
                            'AP_existing_complete_UW48_only_verified','fresh_gates_verified'):
                        self.assertTrue(meta[key])
                    for row in meta['ranges'][1:3]:
                        self.assertEqual(raw[row['binary_offset']:row['binary_offset']+row['length']],
                                         scenario.memory.fixed[(row['rva'],row['length'])])
                    if change=='unknown128':
                        self.assertFalse(meta['standard_layouts_complete'])
                        self.assertEqual(meta['metadata_copy_readiness'],'WITHHELD_UNKNOWN_LAYOUT')
                        self.assertEqual([n for r,n in scenario.memory.fixed_reads if r==DISPATCH_UW],[4,4])
                    else:self.assertTrue(meta['standard_layouts_complete'])
                    self.assertEqual(scenario.memory.counts[(capture.DISPATCH_BEGIN,244)],2)
                    self.assertEqual(scenario.memory.counts[(capture.PHYSICAL_RF_RVA,84)],2)
                    self.assertEqual(scenario.memory.counts[capture.PHYSICAL_UW],2)
                budget=meta['budget']
                self.assertEqual(budget['read_calls'],len(scenario.memory.reads))
                self.assertEqual(budget['query_calls'],len(scenario.memory.queries))
                self.assertEqual(budget['bytes_requested'],sum(n for _,n in scenario.memory.reads))
                self.assertLessEqual(budget['read_calls'],96);self.assertLessEqual(budget['query_calls'],96)
                self.assertLessEqual(budget['bytes_requested'],24576)
                self.assertEqual(budget['max_bytes'],24576);self.assertEqual(budget['max_reads'],96)
                for key in ('logical_function_complete','clone_execution_proven','runtime_unwind_proven',
                        'classification_ready','contract_ready','native_called','native_written','handler_body_read',
                        'handler_data_extended','automatic_handler_or_window_extension','source_PIDs_used_as_current_identity'):
                    self.assertFalse(meta[key])
                self.assertEqual(meta['heap_reads'],0);self.assertEqual(meta['extra_callee_reads'],0)
                self.assertTrue(scenario.memory.closed)
                self.assertEqual((fixture.callsite.MAX_BYTES,fixture.callsite.MAX_READS,
                    fixture.existing.forwarder.MAX_BYTES,fixture.existing.forwarder.MAX_READS),OLD_LIMITS)
                RESULTS.append({'case':name,'status':'PASS','binary_saved':not bool(reason),'budget':budget,
                    'ranges':meta.get('ranges',[]),'metadata_copy_readiness':meta.get('metadata_copy_readiness')})
                print('OWNED '+json.dumps(RESULTS[-1]))


if __name__=='__main__':unittest.main()
