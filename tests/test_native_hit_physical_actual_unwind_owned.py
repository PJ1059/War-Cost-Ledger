"""Replay the immutable game's UW metadata on a wholly owned image/stack.

Only RtlVirtualUnwind runs; no actual game instruction or process is accessed.
"""
import ctypes
import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/native'))
from hit_bridge_owned import OwnedBridge,RuntimeFunction
from hit_near_pages_owned import allocate_owned_near

SAMPLE=ROOT/'dist/hit-physical-unwind-20261012-a2417acf'
WHOLE_SHA='ec10e06d8a697fb4860dc6fae0ff5c225e4976a2e11a675d5e4c01642a94ddbb'


class ActualUnwindOnOwnedFrame(unittest.TestCase):
    def test_actual_three_level_chain_restores_e0_frame_rbx_and_xmm12(self):
        raw=(SAMPLE/'drain.bin').read_bytes()
        meta=json.loads((SAMPLE/'drain.json').read_text())
        self.assertEqual(hashlib.sha256(raw).hexdigest(),WHOLE_SHA)
        self.assertEqual(meta['sha256'],WHOLE_SHA)
        self.assertEqual(raw[:5],bytes.fromhex('32c088451c'))
        self.assertEqual([n['begin'] for n in meta['unwind_chain']],[0x13B1162,0x13B0D0F,0x13B0BD0])
        with OwnedBridge() as b:
            # Virtual pages are owned, sparsely touched; not a game DLL mapping.
            image_size=meta['identity']['game_size']
            base=b._allocate(image_size,executable=False)
            for node in meta['unwind_chain']:
                part=node['complete_unwind']
                data=raw[part['binary_offset']:part['binary_offset']+part['length']]
                self.assertEqual(data.hex(),part['raw_hex'])
                ctypes.memmove(base+node['unwind_rva'],data,len(data))
            leaf=meta['unwind_chain'][0]
            gateway,contract=allocate_owned_near(b,base,image_size)
            gateway_rva=gateway-base
            self.assertGreaterEqual(gateway_rva,image_size)
            ctypes.memmove(gateway,b'\x90',1)  # never executed
            secondary=bytes.fromhex('21000000')+struct.pack('<III',leaf['begin'],leaf['end'],leaf['unwind_rva'])
            ctypes.memmove(gateway+0x800,secondary,len(secondary))
            old=ctypes.c_uint32()
            self.assertTrue(b.kernel.VirtualProtect(gateway,4096,0x20,ctypes.byref(old)))
            self.assertTrue(b.kernel.FlushInstructionCache(b.kernel.GetCurrentProcess(),gateway,1))
            entry=RuntimeFunction(gateway_rva,gateway_rva+1,gateway_rva+0x800)
            self.assertTrue(b.nt.RtlAddFunctionTable(ctypes.byref(entry),1,base))
            b._function_tables.append((base,entry))
            aligned=ctypes.create_string_buffer(0x4D0+16)
            context=(ctypes.addressof(aligned)+15)&~15
            b.nt.RtlCaptureContext(context)
            stack=ctypes.create_string_buffer(4096+16)
            rsp=((ctypes.addressof(stack)+15)&~15)+1024
            gp=[(0xF0,0xE0),(0xE8,0xE8),(0xE0,0xF0),(0xD8,0xF8),
                (0xB0,0x100),(0xA8,0x108),(0xA0,0x110),(0x90,0x128)]
            expected={}
            for i,(context_offset,stack_offset) in enumerate(gp):
                expected[context_offset]=0xFEDCBA9876543200+i
                ctypes.c_uint64.from_address(rsp+stack_offset).value=expected[context_offset]
                ctypes.c_uint64.from_address(context+context_offset).value=0
            expected_xmm=bytes.fromhex('112233445566778899aabbccddeeff00')
            ctypes.memmove(rsp+0x70,expected_xmm,16)
            ctypes.memmove(context+0x1A0+12*16,bytes(16),16)
            returned=base+0x13B0BD0
            ctypes.c_uint64.from_address(rsp+0x118).value=returned
            ctypes.c_uint64.from_address(context+0x98).value=rsp
            ctypes.c_uint64.from_address(context+0xF8).value=base+gateway_rva
            handler,establisher=ctypes.c_void_p(),ctypes.c_uint64()
            b.nt.RtlVirtualUnwind(0,base,base+gateway_rva,ctypes.byref(entry),context,
                ctypes.byref(handler),ctypes.byref(establisher),None)
            self.assertEqual(ctypes.c_uint64.from_address(context+0x98).value,rsp+0x120)
            self.assertEqual(ctypes.c_uint64.from_address(context+0xF8).value,returned)
            for offset,value in expected.items():self.assertEqual(ctypes.c_uint64.from_address(context+offset).value,value)
            self.assertEqual(ctypes.string_at(context+0x1A0+12*16,16),expected_xmm)


if __name__=='__main__':unittest.main(verbosity=2)
