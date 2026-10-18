"""Only new writer28/PC and independently selected declaration, owned."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import test_career_tab_initializer_metadata_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_tab_callback_metadata',ROOT/'tools/career-tab-callback-metadata-capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
RESULTS=[]


class Memory(fixture.Memory):
    def __init__(self):
        super().__init__('success');self.begin,self.end=probe.TARGET-0x30,probe.TARGET+0x14D
        self.pin_reads=0;self.uw={0x2513000:b'\x01\0\0\0'}
    def query(self,address):
        if address==self.game+probe.WRITER:
            self.queries.append(address)
            return {'base':self.game,'size':probe.parent.base.IMAGE_SIZE,'state':0x1000,'type':0x1000000,'protect':0x20}
        return super().query(address)
    def read(self,address,n):
        rva=address-self.game
        pdata=probe.parent.base.EXCEPTION_RVA<=rva<rva+n<=probe.parent.base.EXCEPTION_RVA+probe.parent.base.EXCEPTION_SIZE
        if rva==probe.WRITER or pdata:
            self.reads.append((address,n))
            if rva==probe.WRITER:
                assert n==28;self.pin_reads+=1;return probe.WRITER_PIN
            assert n==12
            index=(rva-probe.parent.base.EXCEPTION_RVA)//12
            b,e=(index+1)*0x100,(index+2)*0x100
            if b==probe.TARGET&~0xFF:b,e=self.begin,self.end
            return struct.pack('<III',b,e,0x2513000)
        return super().read(address,n)


class Scenario(fixture.Scenario):
    def __init__(self):super().__init__('success');self.memory=Memory()


class CallbackMetadataTests(unittest.TestCase):
    def test_writer28_source_target_and_actual_range(self):
        source=probe.validate_source()
        self.assertEqual(source['stored_function_RVA'],0x17A9630)
        self.assertEqual(len(bytes.fromhex(source['writer_pin_hex'])),28)
        with tempfile.TemporaryDirectory() as temp:
            s=Scenario();out=Path(temp)/'capture'
            result=probe.run(out,s.dependencies(),fixture.fixture.fixture.Clock())
            m=json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual((m['function_begin'],m['function_end']),(s.memory.begin,s.memory.end))
            self.assertNotEqual(m['function_end'],0x17A9820)
            self.assertEqual(s.memory.pin_reads,2);self.assertEqual(s.memory.body_reads(),[])
            self.assertEqual(len(Path(result['binary_path']).read_bytes()),16)
            RESULTS.append({'case':'new_writer28_and_RF_range','status':'PASS','budget':m['budget']})
        with tempfile.TemporaryDirectory() as temp,patch.object(probe,'SOURCE_BIN_SHA','0'*64):
            s=Scenario()
            with self.assertRaisesRegex(ValueError,'INITIALIZER_SOURCE_CHANGED'):
                probe.run(Path(temp)/'capture',s.dependencies(),fixture.fixture.fixture.Clock())
            self.assertEqual(s.opens,0)
            RESULTS.append({'case':'new_source_SHA_before_open','status':'PASS'})
        print('OWNED '+json.dumps(RESULTS))

if __name__=='__main__':unittest.main()
