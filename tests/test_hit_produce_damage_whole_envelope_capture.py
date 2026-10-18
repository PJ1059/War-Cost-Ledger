"""One focused4546B body fixture group; no Game or native API."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_hit_produce_damage_logical_metadata_capture as previous_fixture
import test_flow_exe_entry_code_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_produce_body',
    ROOT/'tools/hit-produce-damage-whole-envelope-capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
RESULTS=[]


class Memory(previous_fixture.Memory):
    def __init__(self,locator,previous,table,nodes,prefix,change):
        super().__init__(locator,None)
        self.previous,self.table,self.change=previous,table,change
        self.metadata={n['unwind_rva']:bytes.fromhex(n['raw_hex'])for n in nodes}
        self.body=prefix+b'\x90'*(capture.SIZE-len(prefix)-1)+b'\xc3'
        if change=='prefix_changed':self.body=bytes((self.body[0]^1,))+self.body[1:]
        self.body_calls=0

    def query(self,address):
        if self.game+capture.BEGIN<=address<self.game+capture.END:
            self.queries.append(address)
            return dict(base=self.game,size=self.locator.IMAGE_SIZE,state=0x1000,type=0x1000000,protect=0x20)
        return super().query(address)

    def read(self,address,size):
        rva=address-self.game
        if capture.BEGIN<=rva<rva+size<=capture.END:
            self.reads.append((address,size));self.body_calls+=1
            assert size in(4096,450)
            return self.body[rva-capture.BEGIN:rva-capture.BEGIN+size]
        return super().read(address,size)


class Scenario(fixture.Scenario):
    def __init__(self,locator,previous,table,nodes,prefix,change):
        super().__init__();self.memory=Memory(locator,previous,table,nodes,prefix,change)
    def dependencies(self):
        deps=super().dependencies();deps['start_time']=lambda process:0x123456789
        return deps


class WholeEnvelopeTests(unittest.TestCase):
    def test_fixed4546_body_group(self):
        prepared=capture.source();previous,thin,locator,reader,table,nodes,prefix=prepared
        thin.EXPECTED_PID=54321
        for change in(None,'prefix_changed'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as parent:
                scenario=Scenario(locator,previous,table,nodes,prefix,change)
                folder=Path(parent)/'capture'
                with patch.object(capture,'source',return_value=prepared):
                    if change:
                        with self.assertRaisesRegex(ValueError,'PRODUCE_BODY_PRIMARY_PREFIX_CHANGED'):
                            capture.run(folder,scenario.dependencies(),fixture.Clock())
                        result=json.loads((folder/'body.incomplete.json').read_text())
                        self.assertFalse(result['partial_binary_saved'])
                        self.assertEqual(list(folder.glob('*.bin')),[])
                        self.assertEqual(scenario.memory.body_calls,2)
                    else:
                        status=capture.run(folder,scenario.dependencies(),fixture.Clock())
                        result=json.loads(Path(status['json_path']).read_text())
                        self.assertEqual(Path(status['binary_path']).read_bytes(),scenario.memory.body)
                        self.assertEqual(scenario.memory.body_calls,4)
                        self.assertTrue(result['source_gates_verified'])
                        self.assertEqual(result['prefix_bytes_verified'],2361)
                        self.assertEqual(result['budget']['io_calls'],58)
                self.assertLessEqual(result['budget']['io_calls'],64)
                self.assertLessEqual(result['budget']['bytes_requested'],24*1024)
                self.assertEqual(result['budget']['read_calls'],len(scenario.memory.reads))
                self.assertEqual(result['budget']['query_calls'],len(scenario.memory.queries)+(1 if change else 2))
                self.assertFalse(result['normal_CFG_complete']);self.assertFalse(result['handler_specific_data_read'])
                self.assertFalse(result['native_called']);self.assertFalse(result['native_written'])
                self.assertTrue(scenario.memory.closed)
                RESULTS.append({'case':change or'success','status':'PASS','budget':result['budget'],
                                'body_chunk_reads':scenario.memory.body_calls})


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WholeEnvelopeTests))
    folder=ROOT/'dist/hit-produce-damage-whole-envelope-owned-0.4.25'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'verification.json').write_text(json.dumps({'tests':result.testsRun,'passed':result.wasSuccessful(),
        'cases':RESULTS,'Game_accessed':False,'native_API_called':False,
        'tool_sha256':hashlib.sha256((ROOT/'tools/hit-produce-damage-whole-envelope-capture.py').read_bytes()).hexdigest(),
        'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf8')
    raise SystemExit(0 if result.wasSuccessful()else 1)
