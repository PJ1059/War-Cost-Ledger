"""One focused fake reader group for the fixed selector, never Game/native."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_flow_exe_entry_code_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_collision_selector',
    ROOT/'tools/hit-collision-route-selector-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
RESULTS=[]


class Memory(fixture.Memory):
    def __init__(self,locator,change):
        super().__init__(state=3,after=3)
        self.locator,self.change,self.body_reads=locator,change,0
        self.header=(ROOT/'dist/hit-contact-registration-source-20261013/game-pe-header.bin').read_bytes()
        self.directory=(locator.SOURCE/'original-export.bin').read_bytes()
        self.body=bytes.fromhex('8b420c85c00f95c0c3')
        if change=='external_jump':self.body=b'\xe9'+struct.pack('<i',0x12A2000-(capture.TARGET+5))
        self.uw=0x24FC868
        self.parent_uw=0x24FC884
        self.lookup_records={63814:(0x12A1360,0x12A13C0,self.uw),
            63815:(capture.TARGET,capture.TARGET+len(self.body),self.uw),
            63816:(0x12A1400,0x12A1500,self.uw),63817:(0x12A1500,0x12A15E0,self.uw),
            63818:(0x12A2000,0x12A2400,self.uw),63819:(0x12A2400,0x12A2800,self.uw),
            63820:(0x12A2800,0x12A2900,self.uw),63821:(0x12A2900,0x12A3000,self.uw)}
        self.metadata={self.uw:bytes.fromhex('01000000')}
        if change=='chain':
            self.metadata[self.uw]=bytes.fromhex('21000000')+struct.pack('<III',0x12A1360,0x12A13C0,self.parent_uw)
            self.metadata[self.parent_uw]=bytes.fromhex('01000000')

    def query(self,address):
        if address in (self.game+capture.PIN_RVA,self.game+self.locator.TARGET_RVA,self.game+capture.TARGET):
            self.queries.append(address)
            return dict(base=self.game,size=self.locator.IMAGE_SIZE,state=0x1000,type=0x1000000,protect=0x20)
        return super().query(address)

    def read(self,address,size):
        rva=address-self.game
        fixed={0:self.header,self.locator.EXPORT_RVA:self.directory,
            self.locator.TARGET_RVA:bytes.fromhex('85c90f85a2000000488d0581f6ffff48'),capture.PIN_RVA:capture.PIN}
        if rva in fixed:
            self.reads.append((address,size));assert len(fixed[rva])==size
            return fixed[rva]
        if capture.EXCEPTION_RVA<=rva<rva+size<=capture.EXCEPTION_RVA+capture.EXCEPTION_SIZE:
            self.reads.append((address,size));assert size==12
            index=(rva-capture.EXCEPTION_RVA)//12
            if index in capture.ANCHORS:return capture.ANCHORS[index]
            assert index in self.lookup_records
            return struct.pack('<III',*self.lookup_records[index])
        if rva in self.metadata:
            self.reads.append((address,size));raw=self.metadata[rva]
            assert size in(4,len(raw));return raw[:size]
        if rva==capture.TARGET:
            self.reads.append((address,size));assert size==len(self.body)
            self.body_reads+=1;raw=self.body
            if self.change=='body_changed'and self.body_reads==2:raw=raw[:-1]+bytes((raw[-1]^1,))
            return raw
        return super().read(address,size)


class Scenario(fixture.Scenario):
    def __init__(self,locator,change):super().__init__();self.memory=Memory(locator,change)
    def dependencies(self):
        deps=super().dependencies();deps['start_time']=lambda process:0x123456789
        return deps


class FixedSelectorTests(unittest.TestCase):
    def test_one_fixed_declaration_group(self):
        thin,locator,reader=capture.source();thin.EXPECTED_PID=54321
        for change in(None,'chain','external_jump','body_changed'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as parent:
                scenario=Scenario(locator,change);folder=Path(parent)/'capture'
                with patch.object(capture,'source',return_value=(thin,locator,reader)):
                    if change=='body_changed':
                        with self.assertRaisesRegex(ValueError,'SELECTOR_BODY_CHANGED'):
                            capture.run(folder,scenario.dependencies(),fixture.Clock())
                        result=json.loads((folder/'selector.incomplete.json').read_text())
                        self.assertFalse(result['partial_binary_saved'])
                    else:
                        status=capture.run(folder,scenario.dependencies(),fixture.Clock())
                        result=json.loads(Path(status['json_path']).read_text())
                        self.assertTrue(result['source_gates_verified'])
                        self.assertLessEqual(len(result['exception_records']),4)
                        self.assertTrue(all(63814<=r['index']<63822 for r in result['exception_records']))
                        if change is None:
                            self.assertEqual(status['status'],'complete')
                            self.assertEqual(Path(status['binary_path']).read_bytes(),scenario.memory.body)
                            self.assertTrue(result['normal_CFG']['normal_CFG_closed'])
                            self.assertEqual(scenario.memory.body_reads,2)
                        else:
                            self.assertEqual(status['status'],'WITHHELD')
                            self.assertEqual(list(folder.glob('*.bin')),[])
                            self.assertEqual(scenario.memory.body_reads,0 if change=='chain'else 2)
                            self.assertEqual(result['withheld_reason'],
                                'CHAININFO_BODY_WITHHELD'if change=='chain'else 'UNRESOLVED_NORMAL_CFG_BODY_WITHHELD')
                self.assertLessEqual(result['budget']['io_calls'],64)
                self.assertLessEqual(result['budget']['bytes_requested'],16*1024)
                self.assertEqual(result['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(result['budget']['query_calls'],len(scenario.memory.queries)+(2 if change!='body_changed'else 1))
                self.assertFalse(result['native_called']);self.assertFalse(result['native_written'])
                self.assertTrue(scenario.memory.closed)
                RESULTS.append({'case':change or'success','status':'PASS','budget':result['budget'],
                                'body_reads':scenario.memory.body_reads})


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FixedSelectorTests))
    folder=ROOT/'dist/hit-collision-route-selector-owned-0.4.25'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'verification.json').write_text(json.dumps({'tests':result.testsRun,'passed':result.wasSuccessful(),
        'cases':RESULTS,'Game_accessed':False,'native_API_called':False,
        'tool_sha256':hashlib.sha256((ROOT/'tools/hit-collision-route-selector-capture.py').read_bytes()).hexdigest(),
        'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful()else 1)
