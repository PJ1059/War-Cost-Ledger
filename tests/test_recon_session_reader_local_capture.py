from pathlib import Path
import importlib.util
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('session_reader_local',ROOT/'tools/recon-session-reader-local-capture.py')
tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

class LocalReaderTests(unittest.TestCase):
    def test_saved_windows_bound_only_154_bytes(self):
        tool.validate_source()
        self.assertEqual(tool.END-tool.BEGIN,154)
        self.assertEqual(tool.reader.TOTAL_BYTES,154)
        self.assertTrue(tool.BEGIN<=tool.PIN_RVA<tool.END)
    def test_real_saved_pin_is_required(self):
        data=bytearray(154)
        offset=tool.PIN_RVA-tool.BEGIN
        data[offset:offset+len(bytes.fromhex(tool.PIN))]=bytes.fromhex(tool.PIN)
        tool.reader.verify_pins(bytes(data))
        data[offset]=0
        with self.assertRaisesRegex(ValueError,'PIN_MISMATCH'):
            tool.reader.verify_pins(bytes(data))

if __name__=='__main__': unittest.main()
