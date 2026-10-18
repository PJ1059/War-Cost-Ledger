"""One focused bounded metadata fixture group; no Game or native API."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_flow_exe_entry_code_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_produce_metadata',
    ROOT/'tools/hit-produce-damage-logical-metadata-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
RESULTS=[]


class Memory(fixture.Memory):
    def __init__(self,locator,change):
        super().__init__(state=3,after=3)
        self.locator,self.change=locator,change
        self.header=(ROOT/'dist/hit-contact-registration-source-20261013/game-pe-header.bin').read_bytes()
        self.directory=(locator.SOURCE/'original-export.bin').read_bytes()
        spans=[(0x129DD30,0x129E669),(0x129E669,0x129E6D2),
            (0x129E6D2,0x129E720),(0x129E720,0x129E78E),
            (0x129E78E,0x129EEF2),(0x129EEF2,0x129EF90),
            (0x129EF90,0x129F040),(0x129F040,0x129F0D0),
            (0x129F0D0,0x129F170),(0x129F170,0x129F200),
            (0x129F200,0x129F2A0),(0x129F2A0,0x129F330),
            (0x129F330,0x129F3E7),(0x129F3E7,0x129F40E),
            (0x129F410,0x129F460)]
        table=bytearray();self.metadata={}
        for offset,(begin,end)in enumerate(spans):
            index=capture.FIRST+offset;uw=0x24FD000+offset*16
            if index in capture.ANCHORS:
                begin,end,uw=capture.entry(capture.ANCHORS[index])
            table.extend(struct.pack('<III',begin,end,uw))
            if offset==0:
                self.metadata[uw]=capture.PRIMARY_HEADER+bytes(32)+struct.pack('<I',0x21044A0)
            elif(offset==14 and change!='last_sameowner')or(change=='interleaved_foreign'and offset==5):
                self.metadata[uw]=bytes.fromhex('01000000')
            else:self.metadata[uw]=bytes.fromhex('21000000')+struct.pack('<III',*capture.PRIMARY)
            if change=='unknown_layout'and index==63776:
                self.metadata[uw]=bytes.fromhex('02000000')
        self.table=bytes(table)

    def query(self,address):
        if address in(self.game+capture.PIN_RVA,self.game+self.locator.TARGET_RVA):
            self.queries.append(address)
            return dict(base=self.game,size=self.locator.IMAGE_SIZE,state=0x1000,type=0x1000000,protect=0x20)
        return super().query(address)

    def read(self,address,size):
        rva=address-self.game
        fixed={0:self.header,self.locator.EXPORT_RVA:self.directory,
            self.locator.TARGET_RVA:bytes.fromhex('85c90f85a2000000488d0581f6ffff48'),
            capture.PIN_RVA:capture.PIN,capture.TABLE_RVA:self.table}
        if rva in fixed:
            self.reads.append((address,size));assert len(fixed[rva])==size
            return fixed[rva]
        if rva in self.metadata:
            self.reads.append((address,size));raw=self.metadata[rva]
            assert size in(4,len(raw));return raw[:size]
        return super().read(address,size)


class Scenario(fixture.Scenario):
    def __init__(self,locator,change):super().__init__();self.memory=Memory(locator,change)
    def dependencies(self):
        deps=super().dependencies();deps['start_time']=lambda process:0x123456789
        return deps


class LogicalMetadataTests(unittest.TestCase):
    def test_interleaved_foreign_keeps_later_sameowner(self):
        thin,locator,reader=capture.source();thin.EXPECTED_PID=54321
        with tempfile.TemporaryDirectory()as parent:
            scenario=Scenario(locator,'interleaved_foreign')
            with patch.object(capture,'source',return_value=(thin,locator,reader)):
                status=capture.run(Path(parent)/'capture',scenario.dependencies(),fixture.Clock())
            result=json.loads(Path(status['json_path']).read_text())
            self.assertEqual(status['status'],'complete')
            self.assertEqual(result['first_foreign_boundary']['index'],63777)
            self.assertEqual(result['same_owner_indices'],list(range(63772,63777))+list(range(63778,63786)))
            self.assertTrue(result['final_record_foreign'])
            self.assertTrue(result['bounded_owner_window_complete'])
            self.assertEqual(result['saved_successor_targets_uncovered'],[])
            self.assertFalse(result['normal_CFG_complete'])
            self.assertEqual(len(result['unwind_nodes']),15)
            self.assertTrue(all(r['ownership_proven']for r in result['exception_records']))
            self.assertEqual(result['body_envelope_candidate'],[0x129DD30,0x129F40E])
            self.assertEqual(result['budget']['io_calls'],116)
            self.assertLessEqual(result['budget']['bytes_requested'],16*1024)
            self.assertFalse(result['body_read']);self.assertFalse(result['handler_specific_data_read'])
            self.assertTrue(scenario.memory.closed)
            RESULTS.append({'case':'interleaved_foreign','status':'PASS','budget':result['budget'],
                            'unwind_nodes':len(result['unwind_nodes'])})

    def test_fixed_window_ownership_group(self):
        thin,locator,reader=capture.source();thin.EXPECTED_PID=54321
        for change in(None,'last_sameowner','unknown_layout'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as parent:
                scenario=Scenario(locator,change)
                with patch.object(capture,'source',return_value=(thin,locator,reader)):
                    status=capture.run(Path(parent)/'capture',scenario.dependencies(),fixture.Clock())
                result=json.loads(Path(status['json_path']).read_text())
                self.assertTrue(result['source_gates_verified'])
                self.assertEqual(len(result['exception_records']),15)
                self.assertEqual(Path(status['binary_path']).read_bytes()[:180],scenario.memory.table)
                if change is None:
                    self.assertEqual(status['status'],'complete')
                    self.assertEqual(result['same_owner_indices'],list(range(63772,63786)))
                    self.assertEqual(result['first_foreign_boundary']['index'],63786)
                    self.assertEqual(result['body_envelope_candidate'],[0x129DD30,0x129F40E])
                else:
                    self.assertEqual(status['status'],'WITHHELD')
                    self.assertFalse(result['bounded_owner_window_complete'])
                    self.assertEqual(status['withheld_reason'],
                        'FINAL_RECORD_STILL_SAME_OWNER_STOP'if change=='last_sameowner'else'UNKNOWN_STANDARD_UW_LAYOUT')
                self.assertLessEqual(result['budget']['io_calls'],128)
                self.assertLessEqual(result['budget']['bytes_requested'],16*1024)
                self.assertEqual(result['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(result['budget']['query_calls'],len(scenario.memory.queries)+2)
                self.assertLessEqual(len(result['unwind_nodes']),15)
                for record in result['exception_records']:
                    if 'ownership_chain'in record:self.assertLessEqual(len(record['ownership_chain']),4)
                expected={capture.TABLE_RVA,capture.PIN_RVA,0,locator.EXPORT_RVA,locator.TARGET_RVA,
                          *scenario.memory.metadata}
                # Native-state global and its one4B context field are the existing phase gates.
                unknown=[(at,size)for at,size in scenario.memory.reads
                    if at-scenario.memory.game not in expected
                    and at!=scenario.memory.game+fixture.ship_reader['STATE_GLOBAL']
                    and at!=scenario.memory.context+fixture.ship_reader['STATE_OFFSET']]
                self.assertEqual(unknown,[])
                self.assertFalse(result['body_read']);self.assertFalse(result['handler_specific_data_read'])
                self.assertFalse(result['native_called']);self.assertFalse(result['native_written'])
                self.assertTrue(scenario.memory.closed)
                RESULTS.append({'case':change or'success','status':'PASS','budget':result['budget'],
                                'unwind_nodes':len(result['unwind_nodes'])})


if __name__=='__main__':
    focused='--interleaved-only'in sys.argv
    suite=unittest.TestSuite([LogicalMetadataTests('test_interleaved_foreign_keeps_later_sameowner')])if focused else unittest.defaultTestLoader.loadTestsFromTestCase(LogicalMetadataTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    folder=ROOT/'dist/hit-produce-damage-logical-metadata-owned-0.4.25'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/('verification-interleaved.json'if focused else'verification.json')).write_text(json.dumps({'tests':result.testsRun,'passed':result.wasSuccessful(),
        'cases':RESULTS,'Game_accessed':False,'native_API_called':False,
        'tool_sha256':hashlib.sha256((ROOT/'tools/hit-produce-damage-logical-metadata-capture.py').read_bytes()).hexdigest(),
        'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf8')
    raise SystemExit(0 if result.wasSuccessful()else 1)
