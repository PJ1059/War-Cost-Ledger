"""True JMP gateway, original-frame CHAININFO, own objects only."""
import ctypes
import struct
import sys
import threading
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/native'))
from hit_bridge_owned import OwnedBridge
from hit_contact_context_owned import OwnedContactContext
from hit_entity_resolver_owned import OwnedEntityResolver
from hit_physical_profile_owned import OwnedPhysicalProfile


class PhysicalProfileTests(unittest.TestCase):
    @staticmethod
    def fixture(b):
        resolver=OwnedEntityResolver(b)
        resolver.insert(1001,resolver.enemies[0],0)
        resolver.insert(1002,resolver.sources[0],1)
        ctx=OwnedContactContext(b)
        hit=(ctypes.c_uint8*0x118)()
        values=(ctypes.c_uint8*0x24)()
        ctypes.c_uint64.from_buffer(hit,0x110).value=b.local_peer
        ctypes.c_uint32.from_buffer(hit,0x20).value=1001
        ctypes.c_uint32.from_buffer(hit,0x80).value=1002
        ctypes.c_uint32.from_buffer(hit,0x100).value=12345
        ctypes.c_float.from_buffer(hit,0x50).value=4
        ctypes.c_float.from_buffer(values,4).value=0.65
        values[0x1c]=1
        physical=OwnedPhysicalProfile(b,ctx,resolver)
        b._keepalive.extend([hit,values])
        return resolver,ctx,hit,values,physical

    def assert_snapshots_transparent(self,physical):
        before,after,count=physical.snapshots()
        first=struct.unpack_from('<16Q',before)
        last=struct.unpack_from('<16Q',after)
        self.assertEqual(last[0],(first[0]&~0xff)|1)  # actual original XOR AL semantics
        self.assertEqual(first[1:],last[1:])  # every other incoming GP, including RSP, preserved
        self.assertEqual(before[136:140],after[136:140])  # full MXCSR
        self.assertEqual(before[160:416],after[160:416])  # all XMM0..15
        self.assertEqual(after[128]&0xC5,0)  # SF/ZF/PF/CF clear for XOR result1; AF unspecified
        self.assertEqual(after[129],0)  # OF clear
        return count

    def test_actual_inline_jump_binding_and_true_success_record_once(self):
        with OwnedBridge() as b:
            resolver,ctx,hit,values,physical=self.fixture(b)
            ctx.begin(hit)
            self.assertEqual(physical.invoke(hit,values,17),1)
            self.assertEqual(values[0x1c],0)
            record=b.drain()[0]
            self.assertEqual((record.native_branch,record.capture_flags,record.target_kind),(2,0x143,1))
            self.assertEqual((record.source,record.target,record.creditor,record.owner,record.projectile_slot),
                (1002,1001,b.local_peer,12345,17))
            self.assertEqual(self.assert_snapshots_transparent(physical),1)
            physical.invoke(hit,values,17)
            self.assertEqual(b.drain(),[])
            self.assertEqual(self.assert_snapshots_transparent(physical),2)

    def test_same_target_new_contact_has_new_identity_and_all_registers_preserved(self):
        with OwnedBridge() as b:
            resolver,ctx,hit,values,physical=self.fixture(b)
            for slot in (1,2,3):
                ctx.begin(hit)
                physical.invoke(hit,values,slot)
                self.assert_snapshots_transparent(physical)
            records=b.drain()
            self.assertEqual([r.sequence for r in records],[1,2,3])
            self.assertEqual([r.contact_ordinal for r in records],[1,2,3])
            self.assertEqual([r.projectile_slot for r in records],[1,2,3])

    def test_unknown_target_source_and_nonlocal_peer_do_not_gain_classification(self):
        with OwnedBridge() as b:
            resolver,ctx,hit,values,physical=self.fixture(b)
            ctypes.c_uint32.from_buffer(hit,0x20).value=9999
            ctx.begin(hit);physical.invoke(hit,values)
            self.assertEqual(b.drain()[0].capture_flags,0x103)
            ctypes.c_uint32.from_buffer(hit,0x20).value=1001
            resolver.insert(1002,0xE90F771A36FB441E,1)
            ctx.begin(hit);physical.invoke(hit,values)
            self.assertEqual(b.drain()[0].capture_flags,0x43)
            ctypes.c_uint64.from_buffer(hit,0x110).value=b.local_peer-1
            ctx.begin(hit);physical.invoke(hit,values)
            self.assertEqual(b.drain(),[])
            self.assertEqual(b.stats()['filtered'],1)
            self.assert_snapshots_transparent(physical)

    def test_thread_or_pointer_mismatch_bypasses_observation_but_replays_original(self):
        with OwnedBridge() as b:
            resolver,ctx,hit,values,physical=self.fixture(b)
            ctx.begin(hit)
            other=(ctypes.c_uint8*0x118)()
            physical.invoke(other,values)
            self.assertEqual(b.drain(),[])
            self.assert_snapshots_transparent(physical)
            worker=threading.Thread(target=lambda:physical.invoke(hit,values))
            worker.start();worker.join()
            self.assertEqual(b.drain(),[])
            self.assert_snapshots_transparent(physical)
            physical.invoke(hit,values)
            self.assertEqual(len(b.drain()),1)

    def test_full_queue_drops_record_but_original_success_remains(self):
        with OwnedBridge(capacity=1) as b:
            resolver,ctx,hit,values,physical=self.fixture(b)
            for _ in range(2):ctx.begin(hit);physical.invoke(hit,values)
            self.assertEqual((b.stats()['accepted'],b.stats()['dropped']),(1,1))
            self.assertEqual(self.assert_snapshots_transparent(physical),2)

    def test_real_rtl_virtual_unwind_chains_original_parent_at_all_gateway_instructions(self):
        sys.path.insert(0,r'external/hd2-fire-analysis-deps')
        from capstone import Cs,CS_ARCH_X86,CS_MODE_64
        with OwnedBridge() as b:
            resolver,ctx,hit,values,physical=self.fixture(b)
            decoder=Cs(CS_ARCH_X86,CS_MODE_64)
            instructions=list(decoder.disasm(physical.code,physical.address))
            self.assertEqual(sum(i.size for i in instructions),len(physical.code))
            for instruction in instructions:
                with self.subTest(pc=hex(instruction.address)):
                    aligned=ctypes.create_string_buffer(0x4D0+16)
                    context=(ctypes.addressof(aligned)+15)&~15
                    b.nt.RtlCaptureContext(context)
                    stack=ctypes.create_string_buffer(1024+16)
                    rsp=((ctypes.addressof(stack)+15)&~15)+512
                    values_={32:0xFEDCBA987654321F,40:0xFEDCBA987654321D,48:0xFEDCBA9876543215,56:physical.parent_address}
                    for off,value in values_.items():ctypes.c_uint64.from_address(rsp+off).value=value
                    ctypes.c_uint64.from_address(context+0x98).value=rsp
                    ctypes.c_uint64.from_address(context+0xF8).value=instruction.address
                    image,entry=b.unwind_lookup(physical.gateway,instruction.address-physical.address)
                    self.assertEqual(image,physical.image_base)
                    handler,establisher=ctypes.c_void_p(),ctypes.c_uint64()
                    b.nt.RtlVirtualUnwind(0,image,instruction.address,entry,context,
                        ctypes.byref(handler),ctypes.byref(establisher),None)
                    for off,wanted in [(0x98,rsp+64),(0xF8,physical.parent_address),(0xA0,values_[48]),
                                       (0xE0,values_[40]),(0xF0,values_[32])]:
                        self.assertEqual(ctypes.c_uint64.from_address(context+off).value,wanted)
            self.assertGreater(len(instructions),100)

    def test_close_prevents_calls_and_snapshot_reads(self):
        b=OwnedBridge();resolver,ctx,hit,values,physical=self.fixture(b);b.close()
        with self.assertRaises(ValueError):physical.invoke(hit,values)
        with self.assertRaises(ValueError):physical.snapshots()

    def test_modified_object_addresses_reject_before_compiling_or_reading_foreign_memory(self):
        with OwnedBridge() as b:
            resolver,ctx,hit,values,physical=self.fixture(b)
            for owner,field,bad in [(ctx,'address',1),(ctx,'get_thread_id',1),
                                    (resolver,'manager',1),(resolver,'_qualify',ctypes.c_void_p(1))]:
                with self.subTest(field=field):
                    previous=getattr(owner,field)
                    try:
                        setattr(owner,field,bad)
                        with self.assertRaises(ValueError):OwnedPhysicalProfile(b,ctx,resolver)
                    finally:setattr(owner,field,previous)


if __name__=='__main__':unittest.main(verbosity=2)
