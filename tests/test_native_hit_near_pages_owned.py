import ctypes
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/native'))
from hit_bridge_owned import OwnedBridge
from hit_near_pages_owned import allocate_owned_near


class NearPagesTests(unittest.TestCase):
    def test_public_bounded_current_process_allocation_and_rva_rel32(self):
        with OwnedBridge() as b:
            image_size=0x4744000
            base=b._allocate(image_size,executable=False)
            address,contract=allocate_owned_near(b,base,image_size)
            self.assertGreaterEqual(address,base+image_size)
            self.assertLess(address+4096-base,2**31)
            self.assertEqual(address%contract['alignment'],0)
            self.assertEqual(contract['allocation_calls'],1)
            self.assertEqual(ctypes.string_at(address,32),bytes(32))
            for rva in (0x13AD4E8,0x129CABC,0x129CADF,0x129CB61,0x13AD88B,0x13B11D4):
                self.assertTrue(-(2**31)<=address-(base+rva+5)<2**31)

    def test_foreign_base_closed_or_unbounded_requests_are_rejected(self):
        with OwnedBridge() as b:
            base=b._allocate(4096,executable=False)
            for size in (0,1,0x200000):
                with self.assertRaises(ValueError):allocate_owned_near(b,base,4096,size=size)
            with self.assertRaises(ValueError):allocate_owned_near(b,1,4096)
        with self.assertRaises(ValueError):allocate_owned_near(b,base,4096)


if __name__=='__main__':unittest.main(verbosity=2)
