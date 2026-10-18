"""Owned synthetic PE fixtures only; no game process or code execution."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('inline_uw_tests',ROOT/'tools/hit-inline-unwind-capture.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)

class Memory:
    base=0x10000000
    identity={'game_base':base,'game_size':profile.reader.IMAGE_SIZE}
    def __init__(self):
        self.reads=[];self.queries=[];self.bad_pin=False;self.bad_header=False
    def query(self,address):
        self.queries.append(address)
        return {'state':0x1000,'type':0x1000000,'protect':0x20,
                'base':self.base,'size':profile.reader.IMAGE_SIZE}
    def read(self,address,length):
        rva=address-self.base;self.reads.append((rva,length))
        for _,site,pin in profile.SITES:
            if rva==site and length==len(bytes.fromhex(pin)):
                return bytes(length) if self.bad_pin else bytes.fromhex(pin)
        # A single large declared parent proves that no body length policy is
        # relevant here, and the shared cache prevents six repeated table reads.
        if profile.reader.EXCEPTION_RVA<=rva<profile.reader.EXCEPTION_RVA+profile.reader.EXCEPTION_SIZE:
            return struct.pack('<III',0x1200000,0x1400000,0x3000000)
        if rva==0x3000000 and length==4:
            return bytes.fromhex('ff000000' if self.bad_header else '01000000')
        raise AssertionError(f'undeclared read {rva:#x}/{length}')

class InlineUnwindTests(unittest.TestCase):
    def test_six_pins_shared_budget_only_metadata(self):
        mem=Memory();raw,meta=profile.capture(mem,mem.identity)
        self.assertEqual(len(raw),55)
        self.assertEqual(meta['code_bytes'],31)
        self.assertEqual(mem.reads[:6],[(rva,len(bytes.fromhex(pin)))for _,rva,pin in profile.SITES])
        self.assertEqual(len(mem.reads),8)
        self.assertEqual(meta['budget']['read_calls'],8)
        self.assertEqual(meta['budget']['max_reads'],192)
        self.assertEqual(meta['budget']['max_bytes'],8192)
        self.assertFalse(meta['native_written']);self.assertFalse(meta['native_called'])
        profile.verify_saved(meta,raw)
        with self.assertRaises(ValueError):profile.verify_saved(meta,raw[:-1])
    def test_pin_mismatch_stops_before_any_metadata(self):
        mem=Memory();mem.bad_pin=True
        with self.assertRaisesRegex(ValueError,'PIN_MISMATCH'):profile.capture(mem,mem.identity)
        self.assertEqual(len(mem.reads),1)
    def test_unknown_unwind_header_stops(self):
        mem=Memory();mem.bad_header=True
        with self.assertRaisesRegex(ValueError,'UNWIND_FORMAT'):profile.capture(mem,mem.identity)
    def test_query_budget_and_time_bound_remain(self):
        mem=Memory();budget=profile.reader.Budget(mem,mem.identity,clock=lambda:0)
        budget.query_calls=192
        with self.assertRaisesRegex(ValueError,'QUERY_BUDGET'):budget.query(mem.base)
        ticks=iter((0,3));budget=profile.reader.Budget(mem,mem.identity,clock=lambda:next(ticks))
        with self.assertRaisesRegex(ValueError,'TIME_BUDGET'):budget.read(mem.base,1)

if __name__=='__main__':unittest.main()
