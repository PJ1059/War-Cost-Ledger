"""Owned-process ABI/queue replay only; never enumerates or opens the game."""
from __future__ import annotations
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import demolition_diagnostic_observer as profile
from hit_bridge_owned import OwnedBridge,_Code
from hit_contact_arena_owned import OwnedContactArena
from hit_physical_profile_owned import gp_memory

def addr(fn):return ctypes.cast(fn,ctypes.c_void_p).value
def relocated(entry,addresses):
    raw=bytearray.fromhex(entry['code_hex'])
    for r in entry['relocations']:
        assert r['width']==8 and raw[r['offset']:r['offset']+8]==bytes(8)
        struct.pack_into('<Q',raw,r['offset'],addresses[r['address_key']]+r['addend'])
    return bytes(raw)

def stub_code():
    c=_Code();c.emit('48 ff 01 48 89 49 08 f3 0f 11 49 10 44 8b 91 84 af 1e 00 45 31 c0')
    c.emit('4c 8d 99 78 2f 1e 00')
    c.label('loop');c.emit('45 39 d0');c.branch('0f 83','end')
    c.emit('41 80 7b 38 00');c.branch('0f 85','next')
    c.emit('45 8b 4b 18 41 81 f9 00 70 01 00');c.branch('0f 83','next')
    c.emit('49 6b d1 0c 48 8d 94 11 78 5f 0c 00 41 8a 43 28 88 42 07 80 4a 08 02 41 c6 43 38 01')
    c.label('next');c.emit('41 ff c0 49 83 c3 40');c.branch('e9','loop')
    c.label('end');c.emit('c7 81 84 af 1e 00 00 00 00 00 66 0f ef c0 83 f8 11 48 b8 88 77 66 55 44 33 22 11 c3')
    return c.finish()

def harness(target):
    c=_Code();c.emit('41 55 57 48 83 ec 28 4d 89 c5')
    # libffi puts this harness's address in RDI, which differs between the two
    # distinct callable pages. Give both calls the same preserved input.
    c.emit('48 bf 38 37 36 35 34 33 32 31')
    # Set reproducible volatile input lanes and GPR arguments for both calls.
    c.emit('66 0f ef d2 66 0f ef db 66 0f ef e4 66 0f ef ed')
    c.emit('48 ba 01 02 03 04 05 06 07 08 49 ba 10 11 12 13 14 15 16 17 49 bb 20 21 22 23 24 25 26 27')
    c.emit('48 b8 '+struct.pack('<Q',target).hex(' ')+' ff d0')
    for reg in range(16):gp_memory(c,store=True,register=reg,base=13,displacement=reg*8)
    c.emit('9f 41 88 a5 80 00 00 00 41 0f 90 85 81 00 00 00 41 0f ae 9d 88 00 00 00')
    for xmm in range(6):c.emit('f3 41 0f 7f '+bytes([0x85+xmm*8]).hex()+' '+struct.pack('<I',160+xmm*16).hex(' '))
    c.emit('48 83 c4 28 5f 41 5d c3')
    return c.finish()

def main(output):
    checks=[]
    with OwnedBridge() as b:
        arena=OwnedContactArena(b)
        world=b._allocate(0x1EC000,executable=False)
        global_world=b._allocate(8,executable=False);ctypes.c_uint64.from_address(global_world).value=world
        user=b._allocate(0xB3A0,executable=False);ctypes.c_uint64.from_address(user+0xB398).value=b.local_peer
        global_user=b._allocate(8,executable=False);ctypes.c_uint64.from_address(global_user).value=user
        diag=b._allocate(64+32*128,executable=False)
        out=b._allocate(1024,executable=False)
        stub=b._procedure(stub_code(),ctypes.c_uint64,ctypes.c_void_p,ctypes.c_float,unwind=bytes.fromhex('01000000'))
        entry=profile.wrapper_entry()
        keys={'arena':arena.address,'destruction_world_global':global_world,'current_user_global':global_user,
              'demolition_diagnostic':diag,'original_demolition_consumer':addr(stub)}
        wrapper=b._procedure(relocated(entry,keys),ctypes.c_uint64,ctypes.c_void_p,ctypes.c_float,
                             unwind=bytes.fromhex(entry['unwind_hex']))
        direct_run=b._procedure(harness(addr(stub)),None,ctypes.c_void_p,ctypes.c_float,ctypes.c_void_p,
                                unwind=bytes.fromhex('010703000742037002d00000'))
        wrapped_run=b._procedure(harness(addr(wrapper)),None,ctypes.c_void_p,ctypes.c_float,ctypes.c_void_p,
                                 unwind=bytes.fromhex('010703000742037002d00000'))
        drainentry=profile.drain_entry()
        drain=b._procedure(bytes.fromhex(drainentry['code_hex']),ctypes.c_uint32,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,
                           unwind=bytes.fromhex(drainentry['unwind_hex']))
        destination=b._allocate(32*128,executable=False)
        def u32(at):return ctypes.c_uint32.from_address(at)
        def queue(first,count):
            u32(world+0x1EAF84).value=count
            ctypes.memset(world+0x1E2F78,0,min(count,512)*64)
            for i in range(min(count,512)):
                at=world+0x1E2F78+i*64;record=world+0xC5F78+(first+i)*12
                ctypes.memset(record,0,12)
                u32(at+0x18).value=first+i
                ctypes.c_ubyte.from_address(at+0x28).value=1
                ctypes.c_uint64.from_address(at+0x30).value=b.local_peer
                u32(record).value=900+first+i;ctypes.c_ubyte.from_address(record+8).value=1
        def reset(count=1,enabled=True):
            ctypes.memset(world,0,0x1EC000);ctypes.memset(diag,0,64+32*128)
            u32(diag).value=32;u32(diag+4).value=128
            ctypes.c_uint64.from_address(global_world).value=world
            ctypes.c_uint64.from_address(user+0xB398).value=b.local_peer
            arena.reset_after_owned_calls_return(enabled=enabled)
            queue(0,count)
        def returned_clean(calls=1):
            assert u32(world).value==calls,'original called !=1 per invocation'
            assert ctypes.c_uint64.from_address(world+8).value==world
            assert ctypes.c_float.from_address(world+16).value==3.25
            assert u32(arena.address+44).value==0,'shared arena active leak'
        reset();direct_run(world,3.25,out);reference=ctypes.string_at(out,256)
        reset();wrapped_run(world,3.25,out);actual=ctypes.string_at(out,256);returned_clean()
        # RSI/RDI/RBP and all other GPR outputs are identical; RSP is the same
        # owned harness call site. RAX is stored before LAHF by the harness.
        assert actual==reference,('GPR/XMM0..5/MXCSR/arithmetic flags changed',
            [(hex(i),reference[i:i+8].hex(),actual[i:i+8].hex())for i in range(0,256,8)if actual[i:i+8]!=reference[i:i+8]])
        assert u32(diag+24).value==1 and u32(diag+28).value==0
        raw=ctypes.string_at(diag+64,128)
        assert struct.unpack_from('<QQ',raw)==(world,b.local_peer)
        assert raw[0x48]==0 and raw[0x57]==0 and raw[0x63]==1
        assert struct.unpack_from('<Q',raw,0x40)[0]==b.local_peer
        checks.append('enabled wrapper: original once, unchanged outputs and exact pre/post receipt')
        assert drain(diag,destination,32)==1 and u32(diag+24).value==0
        assert ctypes.string_at(destination,128)==raw
        assert drain(diag,destination,32)==0
        checks.append('owned drain transfers one batch once and clears published count')
        reset(40);wrapped_run(world,3.25,out);returned_clean()
        assert u32(diag+24).value==32 and u32(diag+36).value==1
        assert drain(diag,destination,31)==0 and u32(diag+24).value==32 and u32(diag+28).value==0
        assert drain(diag,destination,32)==32
        checks.append('32 row cap and all-or-nothing drain preserve queue order')
        # Regression for the real first-scenery-record barrier: several native
        # frames append before the 1 Hz Lua drain. Previous post bytes remain
        # byte-identical even when their live persistent stage later changes.
        reset();wrapped_run(world,3.25,out);returned_clean()
        first_row=ctypes.string_at(diag+64,128)
        ctypes.c_ubyte.from_address(world+0xC5F78+7).value=7
        queue(1,2);wrapped_run(world,3.25,out);returned_clean(2)
        assert u32(diag+24).value==3 and u32(diag+36).value==0
        assert ctypes.string_at(diag+64,128)==first_row,'prior receipt was rewritten'
        first_three=ctypes.string_at(diag+64,3*128)
        queue(3,29);wrapped_run(world,3.25,out);returned_clean(3)
        assert u32(diag+24).value==32 and u32(diag+36).value==0
        assert ctypes.string_at(diag+64,3*128)==first_three
        completed=ctypes.string_at(diag+64,32*128)
        queue(32,1);wrapped_run(world,3.25,out);returned_clean(4)
        assert u32(diag+24).value==32 and u32(diag+36).value==1
        assert ctypes.string_at(diag+64,32*128)==completed
        assert drain(diag,destination,32)==32
        result=ctypes.string_at(destination,32*128)
        assert [struct.unpack_from('<I',result,i*128+0x28)[0]for i in range(32)]==list(range(32))
        assert [struct.unpack_from('<I',result,i*128+0x68)[0]for i in range(32)]==list(range(1,33))
        checks.append('successive 1+2+29 frame batches append to 32; prior post bytes and sequence preserved')
        reset(30);wrapped_run(world,3.25,out);returned_clean()
        prior_rows=ctypes.string_at(diag+64,30*128)
        queue(30,5);wrapped_run(world,3.25,out);returned_clean(2)
        assert u32(diag+24).value==32 and u32(diag+36).value==1 and u32(diag+32).value==32
        assert ctypes.string_at(diag+64,30*128)==prior_rows
        assert ctypes.c_ubyte.from_address(world+0xC5F78+34*12+7).value==1,'uncaptured original event suppressed'
        assert drain(diag,destination,32)==32
        checks.append('remaining capacity 2 appends only 2 of 5 new rows; original consumes all 5 exactly once')
        reset();wrapped_run(world,3.25,out);returned_clean()
        previous=ctypes.string_at(diag+64,128)
        queue(1,0);wrapped_run(world,3.25,out);returned_clean(2)
        assert u32(diag+24).value==1 and ctypes.string_at(diag+64,128)==previous
        assert u32(diag+36).value==0 and drain(diag,destination,32)==1
        checks.append('empty later native frame retains the prior undrained receipt without marking a drop')
        for changed in ('epoch','peer'):
            reset();u32(diag+24).value=32;u32(diag+48).value=32
            ctypes.c_uint64.from_address(diag+8).value=ctypes.c_uint64.from_address(arena.address+8).value
            ctypes.c_uint64.from_address(diag+16).value=b.local_peer
            at=diag+(8 if changed=='epoch'else 16)
            ctypes.c_uint64.from_address(at).value^=1
            wrapped_run(world,3.25,out);returned_clean()
            assert u32(diag+24).value==1 and u32(diag+28).value==0,changed
            assert ctypes.c_uint64.from_address(diag+8).value==ctypes.c_uint64.from_address(arena.address+8).value
            assert ctypes.c_uint64.from_address(diag+16).value==b.local_peer
        checks.append('an undrained old epoch/peer batch is retired under the private lock')
        for kind in ('disabled','wrong_world','wrong_peer','processed','index_boundary','unregistered','closed','full','busy','count_invalid'):
            reset(enabled=kind!='disabled')
            if kind=='wrong_world':ctypes.c_uint64.from_address(global_world).value=world+64
            if kind=='wrong_peer':ctypes.c_uint64.from_address(user+0xB398).value=b.local_peer^(1<<40)
            if kind=='processed':ctypes.c_ubyte.from_address(world+0x1E2F78+0x38).value=1
            if kind=='index_boundary':u32(world+0x1E2F78+0x18).value=0x17000
            if kind=='unregistered':ctypes.c_ubyte.from_address(world+0xC5F78+8).value=0
            if kind=='closed':ctypes.c_ubyte.from_address(world+0xC5F78+7).value=1
            if kind=='full':
                u32(diag+24).value=32
                ctypes.c_uint64.from_address(diag+8).value=ctypes.c_uint64.from_address(arena.address+8).value
                ctypes.c_uint64.from_address(diag+16).value=b.local_peer
            if kind=='busy':u32(diag+28).value=1
            if kind=='count_invalid':u32(world+0x1EAF84).value=513
            wrapped_run(world,3.25,out);returned_clean()
            assert u32(diag+24).value==(32 if kind=='full'else 0),kind
            assert u32(diag+28).value==(1 if kind=='busy'else 0),kind
        checks.append('10 rejection/bypass cases still execute original exactly once and release shared active')
        reset();u32(diag+28).value=1;assert drain(diag,destination,32)==0 and u32(diag+28).value==1
        u32(diag+28).value=0;u32(diag+24).value=33
        assert drain(diag,destination,32)==0 and u32(diag+28).value==0
        assert drain(diag,destination,33)==0
        checks.append('drain busy/corrupt count/invalid max cannot copy or clear another owner lock')
        # Registered unwind lookup and owned synthetic stack for the wrapper's
        # full established frame (RBP = frame base, push RBP/RSI/RDI + 0x120).
        image,rf=b.unwind_lookup(wrapper,200);assert rf
        context=ctypes.create_string_buffer(0x4E0);ca=(ctypes.addressof(context)+15)&~15
        stack=ctypes.create_string_buffer(0x400);sp=(ctypes.addressof(stack)+15)&~15
        b.nt.RtlCaptureContext(ca)
        for offset,value in ((0x120,0x12345678),(0x128,0x23456789),(0x130,0x34567890),(0x138,addr(wrapper))):
            ctypes.c_uint64.from_address(sp+offset).value=value
        for offset,value in ((0x98,sp),(0xA0,sp),(0xF8,addr(wrapper)+200)):
            ctypes.c_uint64.from_address(ca+offset).value=value
        handler,frame=ctypes.c_void_p(),ctypes.c_uint64()
        b.nt.RtlVirtualUnwind(0,image,addr(wrapper)+200,rf,ca,ctypes.byref(handler),ctypes.byref(frame),None)
        for offset,value in ((0x98,sp+0x140),(0xA0,0x34567890),(0xA8,0x23456789),(0xB0,0x12345678),(0xF8,addr(wrapper))):
            assert ctypes.c_uint64.from_address(ca+offset).value==value,('unwind',hex(offset))
        checks.append('wrapper original frame metadata restores RSP/RBP/RSI/RDI/RIP on owned stack')
    package=profile.package();old=profile.prior.package()
    assert package['revision']==old['revision']and package['sites']==old['sites']
    assert package['entries'][:-3]==old['entries'],'normal hit entries changed'
    dispatch=package['entries'][-1];code=bytearray.fromhex(dispatch['code_hex'])
    source=bytes.fromhex(package['demolition_source'][0]['hex'])
    for r in dispatch['copy_rel32_relocations']:
        target=r.get('target_rva',0x13E1DC0)
        struct.pack_into('<i',code,r['offset'],target-(profile.DISPATCH_RVA+r['next_offset']))
    assert bytes(code)==source,'only fixed rel32 fields may differ from original dispatch'
    checks.append('39 relocation fields round-trip full dispatch; old normal-hit entries/sites byte-identical')
    report={'status':'PASS','checks':checks,'Game_accessed':False,'captured_Game_code_executed':False,
            'registered_wrapper_and_drain':True,'source':str(Path(__file__).relative_to(profile.ROOT)),
            'generator_sha256':hashlib.sha256(Path(profile.__file__).read_bytes()).hexdigest()}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n','utf8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args().output)
