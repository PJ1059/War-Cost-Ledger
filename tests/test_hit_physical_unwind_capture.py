"""Owned PE and metadata fixtures; no game process or native call."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
spec=importlib.util.spec_from_file_location('physical_uw_fixture_support',
                                         ROOT/'tests/test_hit_queue_consumer_code_capture.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
spec=importlib.util.spec_from_file_location('physical_uw_profile',ROOT/'tools/hit-physical-unwind-capture.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
support.drain=profile.session

class Memory(support.Memory):
    def read(self,address,length):
        if address-self.base==0x3000000 and length>4:
            self.reads.append((address,length))
            return self.metadata[0x3000000]+bytes(length-4)
        return super().read(address,length)

class PhysicalUnwindTests(unittest.TestCase):
    def test_only_success_pin_and_complete_metadata_no_body_scan(self):
        memory=Memory();raw,meta=profile.capture(memory,memory.identity)
        self.assertEqual(raw[:5],bytes.fromhex('32c088451c'))
        self.assertEqual(len(raw),9)
        self.assertEqual(memory.body_reads(),[(0x13B11D4,5)])
        self.assertEqual(meta['unwind_chain'][0]['complete_unwind']['length'],4)
        self.assertEqual(meta['budget']['read_calls'],len(memory.reads))
        self.assertLessEqual(meta['budget']['read_calls'],32)
        self.assertLessEqual(meta['budget']['bytes_requested'],8192)
        profile.verify_saved(meta,raw)
        with self.assertRaises(ValueError):profile.verify_saved(meta,raw[:-1])

    def test_full_slot_array_and_padding_are_saved(self):
        memory=Memory();memory.metadata[0x3000000]=bytes.fromhex('01040100')
        raw,meta=profile.capture(memory,memory.identity)
        self.assertEqual(len(raw),13)
        self.assertEqual(meta['unwind_chain'][0]['complete_unwind']['slot_count'],1)
        self.assertEqual(memory.body_reads(),[(0x13B11D4,5)])

    def test_handler_requires_in_image_rva_and_no_scope_table(self):
        memory=Memory();memory.metadata[0x3000000]=bytes.fromhex('09000000')
        with self.assertRaisesRegex(ValueError,'HANDLER_OUTSIDE_IMAGE'):
            profile.capture(memory,memory.identity)
        self.assertEqual(memory.reads[-1],(memory.base+0x3000000,8))

    def test_pin_mismatch_and_bad_header_refuse(self):
        memory=Memory(bad_pin=True)
        with self.assertRaisesRegex(ValueError,'PIN_MISMATCH'):profile.capture(memory,memory.identity)
        memory=Memory();memory.metadata[0x3000000]=bytes.fromhex('ff000000')
        with self.assertRaisesRegex(ValueError,'UNWIND_FORMAT'):profile.capture(memory,memory.identity)
        self.assertEqual(memory.body_reads(),[])

if __name__=='__main__':unittest.main()
