"""Relocated CALL-profile code runs only in this tool's owned pages."""
import ctypes
import struct
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/native'))
from hit_bridge_owned import OwnedBridge, _Code
from hit_contact_arena_owned import OwnedContactArena, PHASE
from hit_contact_context_owned import ap_call_fixture_code
from hit_entity_resolver_owned import OwnedEntityResolver
from hit_bridge_install_owned import OwnedE8Callsite
from hit_callable_profile import manifest, configure_code, GATE_UNWIND
from hit_physical_profile_owned import snapshot_code,PARENT_UNWIND


def relocated(entry,addresses):
    raw=bytearray.fromhex(entry['code_hex'])
    for item in entry['relocations']:
        assert item['width']==8 and raw[item['offset']:item['offset']+8]==bytes(8)
        struct.pack_into('<Q',raw,item['offset'],addresses[item['address_key']]+item['addend'])
    return bytes(raw)


class OwnedProfile:
    def __init__(self,b):
        self.b=b;self.arena=OwnedContactArena(b);self.resolver=OwnedEntityResolver(b)
        self.resolver.insert(1001,self.resolver.enemies[0],0);self.resolver.insert(1002,self.resolver.sources[0],1)
        self.global_address=b._allocate(8,executable=False);ctypes.c_uint64.from_address(self.global_address).value=self.resolver.manager
        self.original=b._procedure(bytes.fromhex('48 ff 01 48 b8 10 32 54 76 98 ba dc fe c3'),ctypes.c_uint64,
            ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_void_p)
        self.custom_original=b._procedure(bytes.fromhex('48 b8 77 66 55 44 33 22 11 00 c3'),ctypes.c_uint64,
            ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)
        self.addresses={'arena':self.arena.address,'bridge':b.base,'entity_manager_global':self.global_address,
            'qualifier':int(ctypes.cast(self.resolver._qualify,ctypes.c_void_p).value),
            'publish':int(ctypes.cast(b.publisher,ctypes.c_void_p).value),
            'original_contact_begin':int(ctypes.cast(self.original,ctypes.c_void_p).value),
            'original_normal_final':int(ctypes.cast(self.original,ctypes.c_void_p).value),
            'original_custom_curve':int(ctypes.cast(self.custom_original,ctypes.c_void_p).value)}
        self.addresses.update({n:int(ctypes.cast(p,ctypes.c_void_p).value) for n,p in self.arena._calls.items()})
        self.entries={e['name']:e for e in manifest()['entries']};self.functions={}
        for name,e in self.entries.items():
            if name not in ('publish','drain','configure','begin','lookup','end'):
                self.functions[name]=b._procedure(relocated(e,self.addresses),ctypes.c_uint64,
                    ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_void_p,
                    unwind=bytes.fromhex(e['unwind_hex']),executable_length=e['executable_length'])
        self.configure=b._procedure(configure_code(),ctypes.c_uint32,ctypes.c_void_p,ctypes.c_void_p,
            ctypes.c_uint64,ctypes.c_uint64,ctypes.c_uint32,unwind=bytes.fromhex('0102020002700160'))
        self.hit=(ctypes.c_uint8*0x118)();self.calculation=(ctypes.c_uint8*0x24)();self.final=(ctypes.c_uint8*0x24)()
        self.projectile=(ctypes.c_uint8*0x100)();self.count=ctypes.c_uint64()
        ctypes.c_uint64.from_buffer(self.hit,0x110).value=b.local_peer
        ctypes.c_uint32.from_buffer(self.hit,0x20).value=1001;ctypes.c_uint32.from_buffer(self.hit,0x80).value=1002
        ctypes.c_float.from_buffer(self.hit,0x50).value=4
        self.ap_callers={}
        for name in ('default_delta','custom_curve','ap_result'):
            fn=self.functions[name]
            self.ap_callers[name]=b._procedure(ap_call_fixture_code(int(ctypes.cast(fn,ctypes.c_void_p).value)),ctypes.c_uint64,
                ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
                unwind=bytes.fromhex('01170900 17a80400 11980300 0b680200 06a2 0270 0130 0000'))
        self.site=OwnedE8Callsite(b,self.original,projectile_info_from_sixth_arg=True)
        self.site.install(self.functions['normal_final'])
        b._keepalive.append(self)

    def begin(self):return self.functions['contact_begin'](ctypes.addressof(self.count),ctypes.addressof(self.hit),None,0,0,None)

    def ap(self,ap,custom=False):
        f=(ctypes.c_float*3)(ap,4,0.65)
        self.ap_callers['custom_curve' if custom else 'default_delta'](None,ctypes.addressof(self.hit),ctypes.addressof(self.calculation),ctypes.addressof(f))
        self.ap_callers['ap_result'](None,ctypes.addressof(self.hit),ctypes.addressof(self.calculation),ctypes.addressof(f))
        ctypes.memmove(self.final,self.calculation,0x24)

    def final_call(self):return self.site.invoke(ctypes.addressof(self.count),ctypes.addressof(self.final),ctypes.addressof(self.hit),0,123,ctypes.addressof(self.projectile))

    def physical_caller(self):
        c=_Code();c.emit('55 41 55 41 57 48 83 ec 20 48 89 d5 4d 89 c5 4d 89 cf')
        fn=int(ctypes.cast(self.functions['physical_success'],ctypes.c_void_p).value)
        c.emit('48 b8 '+struct.pack('<Q',fn).hex(' '));snapshot_code(c,0);c.emit('ff d0 34 01');snapshot_code(c,512)
        c.emit('48 ff 81 00 04 00 00 48 83 c4 20 41 5f 41 5d 5d c3')
        return self.b._procedure(c.finish(),ctypes.c_uint8,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,unwind=PARENT_UNWIND)


class CallableProfileTests(unittest.TestCase):
    def test_full_normal_pipeline_uses_dynamic_native_row_and_preserves_original_return(self):
        with OwnedBridge() as b:
            p=OwnedProfile(b)
            for ap in (3,4,5):
                self.assertEqual(p.begin(),0xFEDCBA9876543210);p.ap(ap)
                self.assertEqual(p.final_call(),0xFEDCBA9876543210);p.final_call()
            records=b.drain();self.assertEqual(len(records),3)
            self.assertEqual([r.ap_delta for r in records],[-1,0,1])
            self.assertTrue(all(r.capture_flags==0x1FF and r.creditor==b.local_peer for r in records))
            self.assertEqual([r.contact_ordinal for r in records],[1,2,3]);self.assertEqual(p.count.value,9)

    def test_custom_force_unknown_source_and_changed_identity_do_not_gain_normal_class(self):
        with OwnedBridge() as b:
            p=OwnedProfile(b);p.begin();p.ap(5,custom=True);p.final_call()
            self.assertEqual(b.drain()[0].effect_flags,4)
            p.begin();p.ap(5);p.projectile[0xFC]=1;p.final_call();self.assertEqual(b.drain()[0].effect_flags,2)
            p.projectile[0xFC]=0;p.begin();p.ap(5)
            ctypes.c_uint32.from_buffer(p.hit,0x80).value=9999;p.final_call()
            self.assertNotEqual(b.drain()[0].capture_flags,0x1FF)

    def test_begin_tail_keeps_all_unknown_original_stack_arguments_and_return(self):
        with OwnedBridge() as b:
            p=OwnedProfile(b);out=(ctypes.c_uint64*8)();c=_Code()
            for i in range(8):
                c.emit('48 8b 84 24 '+struct.pack('<I',0x28+8*i).hex(' '))
                c.emit('48 89 81 '+struct.pack('<I',8*i).hex(' '))
            c.emit('48 b8 88 77 66 55 44 33 22 11 c3')
            args=(ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_uint64]*10))
            original=b._procedure(c.finish(),ctypes.c_uint64,*args)
            addresses=dict(p.addresses);addresses['original_contact_begin']=int(ctypes.cast(original,ctypes.c_void_p).value)
            entry=p.entries['contact_begin']
            wrapper=b._procedure(relocated(entry,addresses),ctypes.c_uint64,*args,
                unwind=bytes.fromhex(entry['unwind_hex']),executable_length=entry['executable_length'])
            values=[0xFEDCBA9876543200+i for i in range(10)]
            self.assertEqual(wrapper(ctypes.addressof(out),ctypes.addressof(p.hit),*values),0x1122334455667788)
            self.assertEqual(list(out),values[2:])

    def test_physical_call_replay_preserves_all_gp_xmm_mxcsr_and_real_original_xor(self):
        with OwnedBridge() as b:
            p=OwnedProfile(b);p.begin();out=b._allocate(1040,executable=False);caller=p.physical_caller()
            p.final[0x1C]=1
            caller(out,ctypes.addressof(p.final),ctypes.addressof(p.hit),17)
            raw=ctypes.string_at(out,1040);before,after=raw[:512],raw[512:1024]
            first,last=struct.unpack_from('<16Q',before),struct.unpack_from('<16Q',after)
            self.assertEqual(last[0],(first[0]&~0xFF)|1);self.assertEqual(first[1:],last[1:])
            self.assertEqual(before[136:140],after[136:140]);self.assertEqual(before[160:416],after[160:416])
            self.assertEqual(after[128]&0xC5,0);self.assertEqual(after[129],0);self.assertEqual(p.final[0x1C],0)
            records=b.drain();self.assertEqual(len(records),1)
            self.assertEqual((records[0].native_branch,records[0].capture_flags,records[0].projectile_slot),(2,0x143,17))
            caller(out,ctypes.addressof(p.final),ctypes.addressof(p.hit),17);self.assertEqual(b.drain(),[])

    def test_missing_baseline_and_disabled_arena_preserve_original_without_counting(self):
        with OwnedBridge() as b:
            p=OwnedProfile(b);p.final_call();self.assertEqual(b.drain(),[])
            self.assertEqual(p.configure(b.base,p.arena.address,2,b.local_peer,0),1)
            self.assertEqual(p.begin(),0xFEDCBA9876543210);p.ap(5);p.final_call()
            self.assertEqual(b.drain(),[]);self.assertEqual(ctypes.c_uint32.from_address(p.arena.address+44).value,0)

    def test_nonlocal_low_or_high_peer_skips_qualifier_and_local_four_classes_still_match(self):
        with OwnedBridge() as b:
            p=OwnedProfile(b);count=ctypes.c_uint64()
            c=_Code();c.emit('48 b8 '+struct.pack('<Q',ctypes.addressof(count)).hex(' ')+' f0 48 ff 00 ff 25 00 00 00 00')
            real=int(ctypes.cast(p.resolver._qualify,ctypes.c_void_p).value);c.emit(struct.pack('<Q',real).hex(' '))
            counting=b._procedure(c.finish(),ctypes.c_uint32,ctypes.c_void_p,ctypes.c_void_p,unwind=bytes.fromhex('01000000'),executable_length=len(c.finish())-8)
            addresses=dict(p.addresses);addresses['qualifier']=int(ctypes.cast(counting,ctypes.c_void_p).value)
            for name in ('normal_final','physical_success'):
                e=p.entries[name]
                p.functions[name]=b._procedure(relocated(e,addresses),ctypes.c_uint64,
                    ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_void_p,
                    unwind=bytes.fromhex(e['unwind_hex']),executable_length=e['executable_length'])
            p.site.restore();p.site.install(p.functions['normal_final'])
            output=b._allocate(1040,executable=False);physical=p.physical_caller()
            for peer in [b.local_peer^1,b.local_peer^(1<<32)]:
                ctypes.c_uint64.from_buffer(p.hit,0x110).value=peer
                p.begin();p.ap(5);p.final_call();p.begin()
                physical(output,ctypes.addressof(p.final),ctypes.addressof(p.hit),17)
                self.assertEqual(count.value,0);self.assertEqual(b.drain(),[])
            self.assertEqual(b.stats()['filtered'],4)
            ctypes.c_uint64.from_buffer(p.hit,0x110).value=b.local_peer
            for ap in [3,4,5]:p.begin();p.ap(ap);p.final_call()
            p.begin();physical(output,ctypes.addressof(p.final),ctypes.addressof(p.hit),17)
            records=b.drain();self.assertEqual(len(records),4);self.assertEqual(count.value,4)
            self.assertEqual([(v.native_branch,v.capture_flags) for v in records],[(1,0x1FF)]*3+[(2,0x143)])

    def test_end_reads_original_parent_stack_and_preserves_incoming_carry(self):
        with OwnedBridge() as b:
            p=OwnedProfile(b);out=b._allocate(1040,executable=False);counter=ctypes.c_uint64()
            c=_Code();c.emit('55 56 57 48 81 ec 80 00 00 00 48 89 ce 48 89 d7 4c 89 44 24 40 48 8d af 80 fa ff ff')
            c.emit('c7 44 24 74 2a 00 00 00 48 8b 4c 24 40 48 89 fa')
            begin=int(ctypes.cast(p.functions['contact_begin'],ctypes.c_void_p).value)
            end=int(ctypes.cast(p.functions['iteration_end'],ctypes.c_void_p).value)
            c.emit('48 b8 '+struct.pack('<Q',begin).hex(' ')+' ff d0 48 89 f1 48 b8 '+struct.pack('<Q',end).hex(' ')+' f9')
            snapshot_code(c,0);c.emit('ff d0');snapshot_code(c,512)
            c.emit('48 81 c4 80 00 00 00 5f 5e 5d c3')
            caller=b._procedure(c.finish(),ctypes.c_uint64,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
                unwind=bytes.fromhex('010a0500 0a011000 0370 0260 0150 0000'))
            self.assertEqual(caller(out,ctypes.addressof(p.hit),ctypes.addressof(counter)),43)
            raw=ctypes.string_at(out,1024);before,after=raw[:512],raw[512:]
            first,last=struct.unpack_from('<16Q',before),struct.unpack_from('<16Q',after)
            self.assertEqual(last[0],43);self.assertEqual(first[1:],last[1:]);self.assertEqual(after[128]&1,1)
            self.assertEqual(before[136:140],after[136:140]);self.assertEqual(before[160:416],after[160:416])
            self.assertEqual(p.arena.invoke('lookup',p.hit),0);self.assertEqual(counter.value,1)

    def test_ap_extra_subss_masks_snan_and_restores_original_full_mxcsr(self):
        with OwnedBridge() as b:
            p=OwnedProfile(b);p.begin()
            get=b._procedure(bytes.fromhex('0f ae 19 c3'),None,ctypes.c_void_p)
            set_=b._procedure(bytes.fromhex('0f ae 11 c3'),None,ctypes.c_void_p)
            initial=ctypes.c_uint32();get(ctypes.addressof(initial))
            desired=ctypes.c_uint32((initial.value&~0xBF)|0x2000)
            floats=(ctypes.c_float*3)(0,4,0.65);ctypes.c_uint32.from_buffer(floats).value=0x7F800001
            try:
                set_(ctypes.addressof(desired))
                p.ap_callers['ap_result'](None,ctypes.addressof(p.hit),ctypes.addressof(p.calculation),ctypes.addressof(floats))
                after=ctypes.c_uint32();get(ctypes.addressof(after));self.assertEqual(after.value,desired.value)
                row=p.arena.invoke('lookup',p.hit);self.assertTrue(row)
                self.assertNotEqual(p.arena.record(row).ap_delta,p.arena.record(row).ap_delta)
            finally:set_(ctypes.addressof(initial))

    def test_configure_clears_ring_rows_and_rejects_busy_native_observer_without_spinning(self):
        with OwnedBridge() as b:
            p=OwnedProfile(b);p.begin();p.ap(5);p.final_call()
            flags=(ctypes.c_uint32*2)()
            hold=b._procedure(bytes.fromhex('f0 ff 41 2c c7 02 01 00 00 00 83 7a 04 01 75 fa f0 ff 49 2c c3'),None,ctypes.c_void_p,ctypes.c_void_p)
            worker=threading.Thread(target=lambda:hold(p.arena.address,ctypes.addressof(flags)));worker.start()
            deadline=time.monotonic()+2
            while not flags[0] and time.monotonic()<deadline:time.sleep(0.001)
            self.assertEqual(flags[0],1)
            self.assertEqual(p.configure(b.base,p.arena.address,2,b.local_peer,1),0)
            self.assertEqual(ctypes.c_uint32.from_address(p.arena.address+40).value,0)
            self.assertEqual(b.stats()['accepted'],1)
            flags[1]=1;worker.join(2);self.assertFalse(worker.is_alive())
            self.assertEqual(p.configure(b.base,p.arena.address,2,b.local_peer,1),1)
            self.assertEqual(b.drain(),[]);self.assertEqual(b.stats()['accepted'],1)
            self.assertEqual(ctypes.c_uint64.from_address(b.base+8).value,2)
            self.assertEqual(bytes(ctypes.string_at(p.arena.rows,p.arena.capacity*640)),bytes(p.arena.capacity*640))

    def test_every_gateway_has_real_frame_unwind_for_body_and_all_epilog_instructions(self):
        sys.path.insert(0,'external/hd2-fire-analysis-deps')
        from capstone import Cs,CS_ARCH_X86,CS_MODE_64
        with OwnedBridge() as b:
            p=OwnedProfile(b);decoder=Cs(CS_ARCH_X86,CS_MODE_64)
            for name,fn in p.functions.items():
                addr=int(ctypes.cast(fn,ctypes.c_void_p).value);e=p.entries[name]
                ins=list(decoder.disasm(bytes.fromhex(e['code_hex'])[:e['executable_length']],addr))
                self.assertEqual(sum(i.size for i in ins),e['executable_length'])
                epilog=next(i.address-addr for i in ins if i.mnemonic=='lea' and i.op_str=='rsp, [rbp + 0x120]')
                for instruction in ins:
                    pc=instruction.address-addr
                    with self.subTest(name=name,pc=pc):
                        context_raw=ctypes.create_string_buffer(0x4D0+16);ctx=(ctypes.addressof(context_raw)+15)&~15;b.nt.RtlCaptureContext(ctx)
                        stack=ctypes.create_string_buffer(2048+16);initial=((ctypes.addressof(stack)+15)&~15)+1024+8
                        frame=initial-312;returned=addr
                        wanted={0xA0:0xFEDCBA9876543205,0xA8:0xFEDCBA9876543206,0xB0:0xFEDCBA9876543207}
                        for i,off in enumerate((0xA0,0xA8,0xB0),1):ctypes.c_uint64.from_address(initial-i*8).value=wanted[off]
                        ctypes.c_uint64.from_address(initial).value=returned
                        rsp=frame;rbp=frame
                        for off,value in wanted.items():ctypes.c_uint64.from_address(ctx+off).value=value
                        if pc<14:
                            pushed=sum(1 for k in ins if k.address-addr<pc and k.mnemonic=='push')
                            allocated=any(k.address-addr<pc and k.mnemonic=='lea' and k.op_str=='rsp, [rsp - 0x120]' for k in ins)
                            rsp=initial-pushed*8-(288 if allocated else 0);rbp=wanted[0xA0]
                        if pc>epilog:
                            rsp=initial-24
                            popped=sum(1 for k in ins if epilog<k.address-addr<pc and k.mnemonic=='pop')
                            rsp+=popped*8
                            if popped>=3:rbp=wanted[0xA0]
                            for j,off in enumerate((0xB0,0xA8,0xA0)):
                                if popped>j:ctypes.c_uint64.from_address(ctx+off).value=wanted[off]
                        ctypes.c_uint64.from_address(ctx+0x98).value=rsp;ctypes.c_uint64.from_address(ctx+0xA0).value=rbp
                        ctypes.c_uint64.from_address(ctx+0xF8).value=instruction.address
                        image,entry=b.unwind_lookup(fn,pc);handler,est=ctypes.c_void_p(),ctypes.c_uint64()
                        b.nt.RtlVirtualUnwind(0,image,instruction.address,entry,ctx,ctypes.byref(handler),ctypes.byref(est),None)
                        self.assertEqual(ctypes.c_uint64.from_address(ctx+0x98).value,initial+8)
                        self.assertEqual(ctypes.c_uint64.from_address(ctx+0xF8).value,returned)
                        for off,value in wanted.items():self.assertEqual(ctypes.c_uint64.from_address(ctx+off).value,value)


if __name__=='__main__':unittest.main(verbosity=2)
