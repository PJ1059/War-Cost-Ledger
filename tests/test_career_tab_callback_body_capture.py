"""One owned actual metadata->body range fixture; no preceding groups rerun."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import test_career_tab_callback_metadata_capture as fixture

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_callback_body',ROOT/'tools/career-tab-callback-body-capture.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
PIN,_=probe.material()


class Memory(fixture.Memory):
    def __init__(self):super().__init__();self.begin,self.end=probe.BEGIN,probe.END;self.body_reads_count=0
    def read(self,address,n):
        rva=address-self.game
        if rva not in (probe.BEGIN,probe.RF_RVA,probe.UW_RVA):return super().read(address,n)
        self.reads.append((address,n))
        if rva==probe.RF_RVA:assert n==12;return PIN[:12]
        if rva==probe.UW_RVA:assert n==8;return PIN[12:]
        assert n==293;self.body_reads_count+=1;return b'\x90'*n


class Scenario(fixture.Scenario):
    def __init__(self):super().__init__();self.memory=Memory()


class CallbackBodyTests(unittest.TestCase):
    def test_exact_saved_RF_range_and_fixed_writer28(self):
        with tempfile.TemporaryDirectory() as temp:
            s=Scenario();status=probe.run(Path(temp)/'capture',s.dependencies(),fixture.fixture.fixture.fixture.Clock())
            m=json.loads(Path(status['json_path']).read_text('utf8'))
            self.assertEqual((m['function_begin'],m['function_end']),(0x17A9630,0x17A9755))
            self.assertNotEqual(m['function_end'],0x17A9820)
            self.assertEqual(s.memory.body_reads_count,2);self.assertEqual(s.memory.pin_reads,2)
            self.assertEqual(Path(status['binary_path']).read_bytes(),b'\x90'*293)
            self.assertTrue(m['body_before_after_match']);self.assertTrue(m['parent_RF_UW_before_after_match'])
            self.assertEqual(m['budget']['read_calls'],len(s.memory.reads))
            self.assertEqual(m['budget']['bytes_requested'],8898)
            self.assertFalse(m['normal_tab_input_consumer_proven']);self.assertFalse(m['native_called'])
            self.assertTrue(s.memory.closed)
            print('OWNED '+json.dumps({'status':'PASS','body_bytes':293,'double_read':True,'budget':m['budget']}))

if __name__=='__main__':unittest.main()
