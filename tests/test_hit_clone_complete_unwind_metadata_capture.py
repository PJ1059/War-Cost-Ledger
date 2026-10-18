"""One necessary metadata-package group; no Game or old-suite execution."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import test_hit_contact_consume_tail_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_clone_UW_package',
    ROOT/'tools/hit-clone-complete-unwind-metadata-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
WR,CR,PINS,KNOWN=capture.sources()
FRAME_UW=0x2513000
FRAME_END=0x4EE705  # Deliberately different from the observed code-PIN end.
OLD_LIMITS=(fixture.capture.v1.frozen.MAX_READS,fixture.capture.v1.frozen.MAX_BYTES)


def window(name,span,records):
    raw=bytearray(span[1]);reader=capture.v1.frozen.profile.private_reader()
    starts={r['unwind_rva'] for r in records}
    headers={rva:pin[:4] for family,rva,pin in KNOWN if family==name and rva in starts}
    for row in records:
        at=row['unwind_rva'];header=headers.get(at,b'\x21\0\0\0');offset=at-span[0]
        size,flags=capture.standard_size(header,reader);raw[offset:offset+4]=header
        base=4+2*((header[2]+1)&~1)
        if flags&4:
            raw[offset+base:offset+size]=bytes.fromhex(records[0]['raw_hex'])
        elif flags&3:
            raw[offset+base:offset+size]=struct.pack('<I',0x21044A0)
            raw[offset+size:offset+size+4]=struct.pack('<I',0x6D0 if name=='world' else 0x25C0)
    for family,at,pin in KNOWN:
        if family==name:raw[at-span[0]:at-span[0]+len(pin)]=pin
    assert len(raw)==span[1]
    return bytes(raw)


class Memory(fixture.Memory):
    def __init__(self,change=None):
        super().__init__(state=3);self.change=change;self.package_reads=[];self.counts={}
        self.fixed={(WR[0]['rva'],108):b''.join(bytes.fromhex(r['raw_hex']) for r in WR),
                    (CR[0]['rva'],108):b''.join(bytes.fromhex(r['raw_hex']) for r in CR),
                    capture.WORLD_UW:window('world',capture.WORLD_UW,WR),
                    capture.CONTACT_UW:window('contact',capture.CONTACT_UW,CR)}
        self.code_pins={(rva,len(raw)):raw for _,rva,raw in PINS}
        self.frame_raw=b'\x01\x10\x03\0\x10\x68\x02\0\x04\x62\0\0'
        if change=='frame_over128':self.frame_raw=b'\x01\x10\x40\0'

    def query(self,address):
        if address-self.game in {rva for rva,_ in self.code_pins}:
            self.queries.append(address)
            if self.clock:self.clock.value+=self.delay
            return {'base':self.game,'size':capture.v1.frozen.IMAGE_SIZE,'state':0x1000,
                    'type':0x1000000,'protect':0x20}
        return super().query(address)

    def read(self,address,size):
        rva=address-self.game;key=rva,size;frozen=capture.v1.frozen
        table=frozen.EXCEPTION_RVA<=rva<rva+size<=frozen.EXCEPTION_RVA+frozen.EXCEPTION_SIZE
        custom=key in self.fixed or key in self.code_pins or rva==FRAME_UW or table
        if not custom:return super().read(address,size)
        self.reads.append((address,size));self.package_reads.append(key)
        if self.clock:self.clock.value+=self.delay
        self.counts[key]=self.counts.get(key,0)+1
        if key in self.code_pins:return self.code_pins[key]
        if key in self.fixed:
            raw=self.fixed[key]
            if self.change=='RF_before' and key==(WR[0]['rva'],108):return bytes((raw[0]^1,))+raw[1:]
            if self.change=='UW_after' and key==capture.WORLD_UW and self.counts[key]==2:
                return raw[:-1]+bytes((raw[-1]^1,))
            return raw
        if rva==FRAME_UW:
            assert size in (4,len(self.frame_raw));return self.frame_raw[:size]
        assert size==12;index=(rva-frozen.EXCEPTION_RVA)//12
        begin,end=(index+1)*0x100,(index+2)*0x100
        if begin==capture.FRAME&~0xFF:begin,end=capture.FRAME,FRAME_END
        return struct.pack('<III',begin,end,FRAME_UW)


class Scenario(fixture.previous.fixture.Scenario):
    def __init__(self,change=None):super().__init__();self.memory=Memory(change)


class CloneMetadataTests(unittest.TestCase):
    def test_fixed_packages_frame_actual_end_changes_and_node_cap_unknown(self):
        source=capture.validate_source()
        self.assertEqual(len(source['expected_RF_families']['world']),9)
        for name,change,reason in (('success',None,None),('RF_change','RF_before','FRESH_NINE_RF_CHANGED'),
                ('UW_change','UW_after','FIXED_WINDOWS_CHANGED'),('frame128_cap','frame_over128',None)):
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
                    raw=Path(status['binary_path']).read_bytes()
                    for row in meta['ranges']:
                        expected=scenario.memory.fixed.get((row['rva'],row['length']))
                        if expected is not None:self.assertEqual(raw[row['binary_offset']:row['binary_offset']+row['length']],expected)
                    self.assertEqual(meta['frame']['function_end'],FRAME_END)
                    self.assertNotEqual(meta['frame']['function_end'],capture.FRAME+67)
                    self.assertTrue(meta['frame']['actual_RF_end_was_not_assumed'])
                    self.assertTrue(meta['all_four_code_pins_before_after_match'])
                    self.assertTrue(meta['contact_known_full_chain_and_25C0_match'])
                    self.assertTrue(meta['fixed_RF_before_after_match']);self.assertTrue(meta['fixed_UW_before_after_match'])
                    self.assertTrue(meta['frame_captured_UW_bytes_before_after_match'])
                    self.assertTrue(meta['fresh_gates_verified'])
                    if change=='frame_over128':
                        self.assertFalse(meta['frame_full_standard_UW_ancestry_captured'])
                        self.assertFalse(meta['standard_layouts_complete'])
                        self.assertEqual(meta['frame']['unknown_layouts'][0]['standard_length'],132)
                        self.assertEqual([size for rva,size in scenario.memory.package_reads if rva==FRAME_UW],[4,4])
                    else:
                        self.assertTrue(meta['frame_full_standard_UW_ancestry_captured'])
                        self.assertTrue(meta['standard_layouts_complete'])
                        self.assertEqual(len(meta['families'][0]['nodes']),9)
                        self.assertEqual(len(meta['families'][1]['nodes']),9)
                        self.assertEqual(meta['unknown_handler_formats'],[])
                self.assertEqual(meta['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(meta['budget']['query_calls'],len(scenario.memory.queries))
                self.assertEqual(meta['budget']['bytes_requested'],sum(size for _,size in scenario.memory.reads))
                self.assertLessEqual(meta['budget']['read_calls'],96);self.assertLessEqual(meta['budget']['bytes_requested'],24576)
                self.assertEqual(meta['budget']['max_reads'],96);self.assertEqual(meta['budget']['max_bytes'],24576)
                for key in ('sibling_code_read','handler_body_read','automatic_handler_or_window_extension',
                            'runtime_unwind_proven','clone_execution_proven','logical_function_complete',
                            'classification_ready','contract_ready','native_called','native_written'):
                    self.assertFalse(meta[key])
                self.assertEqual(meta['new_code_body_reads'],0);self.assertEqual(meta['extra_callee_reads'],0)
                self.assertEqual(meta['heap_reads'],0);self.assertEqual(scenario.memory.tail_reads,0)
                self.assertTrue(scenario.memory.closed)
                self.assertEqual((fixture.capture.v1.frozen.MAX_READS,fixture.capture.v1.frozen.MAX_BYTES),OLD_LIMITS)
                print('OWNED_BUDGET '+json.dumps({'case':name,'Game_accessed':False,'old_suites_run':False,
                    'binary_saved':not bool(reason),'budget':meta['budget']}))


if __name__=='__main__':unittest.main()
