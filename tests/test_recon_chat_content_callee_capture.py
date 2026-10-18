from pathlib import Path
import importlib.util,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('chat_content_capture',ROOT/'tools/recon-chat-content-callee-capture.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)

class ContentCalleeTests(unittest.TestCase):
    def test_real_saved_call_and_fixed_scope(self):
        self.assertEqual(tool.source(),tool.SOURCE_SHA)
        self.assertEqual(tool.reader.MAX_FUNCTION_BYTES,4096)
        self.assertEqual(tool.reader.MAX_BYTES,8192)
        self.assertEqual(tool.reader.MAX_READS,32)
        selected=tool.ranges([{'begin':tool.TARGET,'end':tool.TARGET+64}])
        self.assertEqual(selected[-1],('proven_chat_update_call',tool.CALL_RVA,5))
        self.assertEqual(tool.window(selected).PINS,((tool.CALL_RVA,tool.CALL_PIN),))
    def test_wrong_declared_entry_rejected_before_metadata(self):
        with self.assertRaisesRegex(ValueError,'ENTRY_NOT_DECLARED'):
            tool.ancestry((tool.TARGET-16,tool.TARGET+64,1),lambda *a:self.fail('unexpected read'),[])
    def test_changed_actual_caller_is_refused(self):
        selected=tool.ranges([{'begin':tool.TARGET,'end':tool.TARGET+64}])
        profile=tool.window(selected)
        valid=bytes(64)+bytes.fromhex(tool.CALL_PIN)
        profile.verify_pins(valid)
        with self.assertRaisesRegex(ValueError,'PIN_MISMATCH'):profile.verify_pins(bytes(69))

if __name__=='__main__':unittest.main()
