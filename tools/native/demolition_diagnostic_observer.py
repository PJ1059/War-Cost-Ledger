"""Owned-copy destruction diagnostic extension; pure generation, no Game access."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
import hit_callable_profile as old
import hit_copy_reflection_observer as prior
sys.path.insert(0,'external/hd2-fire-analysis-deps')
import capstone
from capstone.x86 import X86_OP_MEM,X86_REG_RIP

RelocCode=old.RelocCode
CAPTURE_OWNED=224
INPUT_WORLD=232
APPEND_START=240
DISPATCH_RVA=0x13F7BA0
DISPATCH_SIZE=1532
CALL_RVA=0x13F7D46

def memory(c,opcode,at):c.emit(opcode+' '+struct.pack('<I',at).hex(' '))

def save_volatile(c):
    for reg,at in old.SAVED.items():old.gp(c,True,reg,at)
    for xmm in range(6):memory(c,'0f 29 '+bytes([0x84+xmm*8,0x24]).hex(' '),old.XMM+xmm*16)
    c.emit('0f ae 9c 24 c0 00 00 00 9f 88 a4 24 c8 00 00 00 0f 90 84 24 c9 00 00 00')

def restore_volatile(c):
    c.emit('0f ae 94 24 c0 00 00 00')
    for xmm in range(6):memory(c,'0f 28 '+bytes([0x84+xmm*8,0x24]).hex(' '),old.XMM+xmm*16)
    for reg,at in old.SAVED.items():
        if reg!=0:old.gp(c,False,reg,at)
    c.emit('8a 84 24 c9 00 00 00 04 7f 8a a4 24 c8 00 00 00 9e')
    old.gp(c,False,0,old.SAVED[0])

def original_call(c):
    # Indirect CALL through an inline literal preserves every argument register.
    # Its normal return executes only the short JMP across that literal.
    c.address('ff 15 02 00 00 00 eb 08','original_demolition_consumer')

def wrapper_entry():
    c=RelocCode()
    # Same known unwindable gateway frame; all GPR/XMM/flags saves precede gates.
    c.emit('55 56 57 48 8d a4 24 e0 fe ff ff 48 89 e5')
    save_volatile(c)
    c.emit('c7 84 24 d0 00 00 00 00 00 00 00 c7 84 24 e0 00 00 00 00 00 00 00')
    old.gp(c,False,0,old.SAVED[1]);old.gp(c,True,0,INPUT_WORLD)
    c.address('48 b8','arena')
    c.emit('8b 50 3c f6 c2 01');c.branch('0f 85','before_original')
    c.emit('89 94 24 d8 00 00 00 83 78 28 01');c.branch('0f 85','before_original')
    c.emit('f0 ff 40 2c 3b 50 3c');c.branch('0f 85','lost_entry')
    c.emit('83 78 28 01');c.branch('0f 85','lost_entry')
    c.emit('c7 84 24 d0 00 00 00 01 00 00 00')
    old.gp(c,False,7,INPUT_WORLD)
    c.address('48 b8','destruction_world_global');c.emit('48 3b 38');c.branch('0f 85','before_original')
    c.address('48 b8','current_user_global');c.emit('48 8b 00 48 85 c0');c.branch('0f 84','before_original')
    c.emit('48 8b 90 98 b3 00 00 48 85 d2');c.branch('0f 84','before_original')
    c.address('48 b8','arena');c.emit('48 3b 50 10');c.branch('0f 85','before_original')
    c.address('48 be','demolition_diagnostic')
    c.emit('83 3e 20');c.branch('0f 85','before_original')
    c.emit('81 7e 04 80 00 00 00');c.branch('0f 85','before_original')
    c.emit('31 c0 41 b8 01 00 00 00 f0 44 0f b1 46 1c');c.branch('0f 85','busy')
    c.emit('c7 84 24 e0 00 00 00 01 00 00 00')
    # A mission can end before Lua drains the final batch. Once this private
    # lock is owned, retire an old epoch/peer batch before testing capacity.
    c.address('48 b8','arena');c.emit('48 8b 48 08 48 3b 4e 08');c.branch('0f 85','new_context')
    c.emit('48 3b 56 10');c.branch('0f 84','same_context')
    c.label('new_context');c.emit('c7 46 18 00 00 00 00 c7 46 30 00 00 00 00 48 89 4e 08 48 89 56 10')
    c.label('same_context')
    # Continue an undrained batch across frames. Only the true 32-row limit
    # blocks later candidates; one scenery record must not block a later hole.
    # Keep the starting row in this invocation's existing stack frame, so old
    # receipts' post-state bytes are never sampled again or overwritten.
    c.emit('8b 46 18 83 f8 20');c.branch('0f 83','full')
    memory(c,'89 84 24',APPEND_START)
    c.emit('89 46 30 c7 46 34 00 00 00 00')
    c.address('48 b8','arena');c.emit('48 8b 40 08 48 89 46 08 48 89 56 10')
    c.emit('44 8b 97 84 af 1e 00 41 81 fa 00 02 00 00');c.branch('0f 87','invalid')
    c.emit('45 31 c0 4c 8d 9f 78 2f 1e 00')
    c.label('pre_loop');c.emit('45 39 d0');c.branch('0f 83','before_original')
    c.emit('ff 46 34 41 80 7b 38 00');c.branch('0f 85','pre_next')
    c.emit('45 8b 4b 18 41 81 f9 00 70 01 00');c.branch('0f 83','pre_next')
    c.emit('49 6b d1 0c 48 8d 94 17 78 5f 0c 00 f6 42 08 01');c.branch('0f 84','pre_next')
    c.emit('80 7a 07 00');c.branch('0f 85','pre_next')
    c.emit('83 3a 00');c.branch('0f 84','pre_next')
    c.emit('8b 46 30 83 f8 20');c.branch('0f 83','truncated')
    c.emit('48 c1 e0 07 48 8d 4c 06 40 48 89 39 48 8b 46 10 48 89 41 08')
    for at in range(0,64,8):c.emit('49 8b 43 '+bytes([at]).hex()+' 48 89 41 '+bytes([at+16]).hex())
    c.emit('48 8b 02 48 89 41 50 8b 42 08 89 41 58')
    c.emit('48 c7 41 5c 00 00 00 00 c7 41 64 00 00 00 00 ff 46 20 8b 46 20 89 41 68')
    c.emit('c7 41 6c 00 00 00 00 48 c7 41 70 00 00 00 00 48 c7 41 78 00 00 00 00 ff 46 30')
    c.label('pre_next');c.emit('41 ff c0 49 83 c3 40');c.branch('e9','pre_loop')
    c.label('truncated');c.emit('ff 46 24');c.branch('e9','before_original')
    c.label('invalid');c.emit('ff 46 28');c.branch('e9','discard_pre')
    c.label('full');c.emit('ff 46 24')
    c.label('discard_pre');c.emit('c7 46 1c 00 00 00 00 c7 84 24 e0 00 00 00 00 00 00 00');c.branch('e9','before_original')
    c.label('busy');c.emit('f0 ff 46 24');c.branch('e9','before_original')
    c.label('lost_entry');c.emit('f0 ff 48 2c')
    c.label('before_original')
    # Release the shared hit arena BEFORE calling the original consumer. An
    # original exception must never leave the normal hit session active count
    # stuck. Only this diagnostic's private lock spans the original call.
    c.emit('83 bc 24 d0 00 00 00 01');c.branch('0f 85','pre_released')
    c.address('48 b8','arena');c.emit('f0 ff 48 2c c7 84 24 d0 00 00 00 00 00 00 00')
    c.label('pre_released')
    restore_volatile(c)
    c.emit('48 8b b4 24 28 01 00 00 48 8b bc 24 20 01 00 00')
    original_call(c)
    save_volatile(c)
    c.emit('83 bc 24 e0 00 00 00 01');c.branch('0f 85','return')
    c.address('48 be','demolition_diagnostic')
    # Re-enter only the same enabled arena generation after original return.
    c.address('48 b8','arena');c.emit('8b 50 3c 3b 94 24 d8 00 00 00');c.branch('0f 85','discard_post')
    c.emit('f6 c2 01');c.branch('0f 85','discard_post')
    c.emit('83 78 28 01');c.branch('0f 85','discard_post')
    c.emit('f0 ff 40 2c 3b 50 3c');c.branch('0f 85','post_lost')
    c.emit('83 78 28 01');c.branch('0f 85','post_lost')
    c.emit('c7 84 24 d0 00 00 00 01 00 00 00')
    c.emit('48 8b 50 08 48 3b 56 08');c.branch('0f 85','discard_post')
    c.emit('48 8b 50 10 48 3b 56 10');c.branch('0f 85','discard_post')
    old.gp(c,False,7,INPUT_WORLD)
    c.address('48 b8','destruction_world_global');c.emit('48 3b 38');c.branch('0f 85','discard_post')
    c.address('48 b8','current_user_global');c.emit('48 8b 00 48 85 c0');c.branch('0f 84','discard_post')
    c.emit('48 3b 90 98 b3 00 00');c.branch('0f 85','discard_post')
    c.emit('44 8b 56 30 41 83 fa 20');c.branch('0f 87','discard_post')
    memory(c,'44 8b 84 24',APPEND_START)
    c.emit('45 39 d0');c.branch('0f 87','discard_post')
    c.emit('4c 89 c0 48 c1 e0 07 48 8d 4c 06 40')
    c.label('post_loop');c.emit('45 39 d0');c.branch('0f 83','publish')
    c.emit('8b 41 28 48 6b d0 0c 48 8d 94 17 78 5f 0c 00')
    c.emit('48 8b 02 48 89 41 5c 8b 42 08 89 41 64 41 ff c0 48 81 c1 80 00 00 00');c.branch('e9','post_loop')
    c.label('publish');c.emit('44 89 56 18 ff 46 2c');c.branch('e9','unlock')
    c.label('post_lost');c.emit('f0 ff 48 2c')
    c.label('discard_post');c.emit('ff 46 28 c7 46 30 00 00 00 00')
    c.label('unlock');c.emit('c7 46 1c 00 00 00 00')
    c.label('return');c.emit('83 bc 24 d0 00 00 00 01');c.branch('0f 85','post_released')
    c.address('48 b8','arena');c.emit('f0 ff 48 2c')
    c.label('post_released');restore_volatile(c)
    c.emit('48 8d a5 20 01 00 00 5f 5e 5d c3')
    raw=c.finish()
    return {'name':'demolition_consumer_wrapper','entry_offset':0,'code_hex':raw.hex(),
            'executable_length':len(raw),'relocations':c.relocations,'unwind_hex':old.GATE_UNWIND.hex()}

def drain_entry():
    # u32 drain(diag RCX,dst RDX,max R8D), no Game reads/calls. One try-lock,
    # all-or-nothing batch transfer (caller passes max32), no partial reordering.
    c=RelocCode();c.emit('56 57 48 89 ce 48 89 d7 31 c0')
    c.emit('83 3e 20');c.branch('0f 85','done')
    c.emit('81 7e 04 80 00 00 00');c.branch('0f 85','done')
    c.emit('41 83 f8 20');c.branch('0f 87','done')
    c.emit('48 85 ff');c.branch('0f 84','done')
    c.emit('41 b9 01 00 00 00 f0 44 0f b1 4e 1c');c.branch('0f 85','busy')
    c.emit('44 8b 56 18 41 83 fa 20');c.branch('0f 87','unlock')
    c.emit('45 39 c2');c.branch('0f 87','unlock')
    c.emit('44 89 d1 c1 e1 04 48 8d 56 40 49 89 f3 48 89 d6 fc f3 48 a5 4c 89 de')
    c.emit('c7 46 18 00 00 00 00 c7 46 30 00 00 00 00 44 89 d0');c.branch('e9','release')
    c.label('unlock');c.emit('31 c0')
    c.label('release');c.emit('c7 46 1c 00 00 00 00');c.branch('e9','done')
    c.label('busy');c.emit('31 c0')
    c.label('done');c.emit('5f 5e c3')
    raw=c.finish()
    return {'name':'demolition_drain','entry_offset':0,'code_hex':raw.hex(),
            'executable_length':len(raw),'relocations':[],'unwind_hex':'0102020002700160'}

def dispatch_entry():
    directory=ROOT/'dist/bughole-consumer-caller-live-20261013-v1'
    raw=(directory/'drain.bin').read_bytes()
    if len(raw)!=1532 or hashlib.sha256(raw).hexdigest()!='2699cbc7b3609dff364c0aafe3f6ed31dddd2c65d463d2a4226ea0220b298e42':
        raise ValueError('DEMOLITION_DISPATCH_SOURCE_CHANGED')
    uw=(ROOT/'dist/bughole-dispatch-unwind-live-20261013-v1/drain.bin').read_bytes()
    if len(uw)!=64 or hashlib.sha256(uw).hexdigest()!='8a596a94d3b402ef2673819085eb96b6064c6cc9ee1e48e92b5375b8e7282111':
        raise ValueError('DEMOLITION_DISPATCH_UW_CHANGED')
    out=bytearray(raw);relocs=[];md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
    instructions=list(md.disasm(raw,DISPATCH_RVA))
    if sum(i.size for i in instructions)!=len(raw):raise ValueError('DEMOLITION_DISPATCH_DECODE')
    boundaries={i.address for i in instructions}
    for i in instructions:
        offset=i.address-DISPATCH_RVA
        if i.group(capstone.CS_GRP_BRANCH_RELATIVE):
            target=i.operands[0].imm
            if DISPATCH_RVA<=target<DISPATCH_RVA+len(raw):
                if target not in boundaries:raise ValueError('DEMOLITION_DISPATCH_INTERNAL_BRANCH')
                continue
            if i.imm_size!=4:raise ValueError('DEMOLITION_DISPATCH_EXTERNAL_REL_WIDTH')
            r={'offset':offset+i.imm_offset,'width':4,'next_offset':offset+i.size}
            if i.address==CALL_RVA:
                if i.bytes.hex()!='e875a0feff':raise ValueError('DEMOLITION_CONSUMER_CALL_PIN')
                r['address_key']='demolition_consumer_wrapper'
            else:r['target_rva']=target
            relocs.append(r)
        for operand in i.operands:
            if operand.type==X86_OP_MEM and operand.mem.base==X86_REG_RIP:
                if i.disp_size!=4:raise ValueError('DEMOLITION_DISPATCH_RIP_WIDTH')
                relocs.append({'offset':offset+i.disp_offset,'width':4,'next_offset':offset+i.size,
                               'target_rva':i.address+i.size+operand.mem.disp})
    for r in relocs:out[r['offset']:r['offset']+4]=bytes(4)
    return {'name':'demolition_dispatch','entry_offset':0,'code_hex':out.hex(),
            'executable_length':len(out),'relocations':[],
            'copy_rel32_relocations':relocs,'unwind_hex':uw.hex()},raw,uw

def package():
    result=copy.deepcopy(prior.package())
    dispatch,source,uw=dispatch_entry()
    result['entries'] += [wrapper_entry(),drain_entry(),dispatch]
    result['demolition_diagnostic']={'revision':1,'header_bytes':64,'record_bytes':128,'capacity':32}
    result['demolition_site']={'name':'demolition_dispatch','region':'world','rva':0xAB5FFE,
        'pin_hex':'e89d1b9400','replace_bytes':5,'original_rva':DISPATCH_RVA}
    result['demolition_source']=[{'rva':DISPATCH_RVA,'hex':source.hex()},
        {'rva':0x409DA80,'hex':'a07b3f019c813f01dc615102'}, {'rva':0x25161DC,'hex':uw.hex()}]
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    path=p.parse_args().output;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(package(),indent=2)+'\n','utf8');print(path.resolve())
