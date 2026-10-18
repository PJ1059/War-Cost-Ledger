"""Pure true reflection-writeback observer; retains the0.4.26 normal guard.

Only the frozen13AE6BC contact point can stage branch2. Every such staging
uses fresh full-peer/catalogue qualification and the actual caller frame/slot.
No allocation, native execution, Game access, source/profile installation.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
GUARD_SHA='bd7bbed22001e43711b0d66b5990867f21a7cfa760820844fc84df860bb6999e'
if hashlib.sha256((HERE/'hit_copy_normal_result_guard.py').read_bytes()).hexdigest()!=GUARD_SHA:
    raise ValueError('REFLECTION_FROZEN_GUARD_CHANGED')
import hit_copy_normal_result_guard as G
P=G.D.P
SITE_RVA,SITE_PIN=0x13AE6BC,bytes.fromhex('f3440f5807')
NODE_OFFSET,HASH_OFFSET=632,636


def normal_gateway():
    """Only this new profile freezes the two missing part keys at normal_final.

Begun/AP stages initialize these keys; normal/reflection pending stages compare
before retaining any existing tuple. The immutable pending generator is intact.
"""
    c=P.RelocCode();P.old.prolog(c);P.lookup(c,'normal_final')
    P.gp(c,False,10,P.SAVED[8])
    c.emit('83 7e 64 03');c.branch('0f 84','compare_part')
    c.emit('83 7e 64 05');c.branch('0f 85','freeze_part')
    c.label('compare_part')
    for load,at in [('41 8b 42 24',NODE_OFFSET),('41 8b 42 7c',HASH_OFFSET)]:
        c.emit(load+' 3b 86 '+struct.pack('<I',at).hex(' '));c.branch('0f 85','tuple_conflict')
    c.label('freeze_part')
    for load,at in [('41 8b 42 24',NODE_OFFSET),('41 8b 42 7c',HASH_OFFSET)]:
        c.emit(load+' 89 86 '+struct.pack('<I',at).hex(' '))
    c.branch('e9','normal_snapshot')
    c.label('tuple_conflict');c.emit('c7 46 64 04 00 00 00 c7 46 58 00 00 00 00')
    c.address('48 b8','arena');c.emit('f0 48 ff 40 20');c.branch('e9','restore')
    c.label('normal_snapshot');P.raw_snapshot(c,'normal_final');P.restore(c,'normal_final')
    result=P.entry('normal_final',c,P.old.GATE_UNWIND)
    result.update(executable_length=len(bytes.fromhex(result['code_hex']))-8,
        frame_allocation=P.old.FRAME_BYTES,frame_register='RBP',
        original_parent_unwind_unchanged=True,freezes_part_keys=True)
    return result


def reflection_gateway():
    c=P.RelocCode()
    c.emit(SITE_PIN.hex(' '))  # the original ADDSS and its MXCSR occur exactly once, before save
    P.old.prolog(c)
    # Proved contact body RBP=parentRSP+100; GW savebase=parentRSP-140.
    c.emit('4c 8b 94 24 30 01 00 00 48 8d 84 24 40 02 00 00 4c 3b d0')
    c.branch('0f 85','frame_reject')
    c.emit('49 8b 42 a8 48 89 c1 48 c1 e9 20 48 85 c9');c.branch('0f 85','frame_reject')
    c.emit('48 89 84 24 e8 00 00 00 48 6b c8 70 49 8d 97 40 30 00 00 48 03 ca 48 3b f9')
    c.branch('0f 85','frame_reject')
    c.address('48 b9','arena');c.emit('49 8d 92 80 05 00 00 45 31 c0');c.call('lookup')
    c.emit('48 85 c0');c.branch('0f 84','restore');c.emit('48 89 c6')
    c.emit('48 8d 84 24 40 01 00 00 48 3b 86 70 02 00 00');c.branch('0f 85','frame_reject')
    # All temporary snapshot writes use the existing per-thread diagnostic spare.
    c.emit('48 8d be a0 00 00 00')
    for at in range(0,96,8):c.emit('48 8b 46 '+bytes([at]).hex()+' 48 89 47 '+bytes([at]).hex())
    c.emit('4c 8b 94 24 30 01 00 00 4d 8d 9a e0 03 00 00 49 81 c2 80 05 00 00')
    c.emit('49 8b 82 10 01 00 00 48 85 c0');c.branch('0f 84','filtered')
    c.emit('48 89 47 10')
    c.address('48 b9','arena');c.emit('48 3b 41 10');c.branch('0f 85','filtered')
    c.emit('48 8b 51 08 48 89 57 08')
    c.address('48 b9','bridge');c.emit('48 3b 41 10');c.branch('0f 85','filtered')
    c.emit('48 3b 51 08');c.branch('0f 85','filtered')
    c.address('48 b9','current_user_global');c.emit('48 8b 09 48 85 c9');c.branch('0f 84','filtered')
    c.emit('48 3b 81 98 b3 00 00');c.branch('0f 85','filtered')
    for load,store in [('41 8b 42 20','89 47 2c'),('41 8b 82 80 00 00 00','89 47 30'),
        ('41 8b 82 00 01 00 00','89 47 34'),('41 8b 02','89 47 50'),
        ('41 8b 42 50','89 47 44'),('41 8b 43 04','89 47 48'),('41 8b 03','89 47 4c')]:
        c.emit(load+' '+store)
    c.emit('4c 89 57 18 8b 84 24 e8 00 00 00 89 47 20')
    c.emit('41 8b 42 24 89 84 24 e0 00 00 00 41 8b 42 7c 89 84 24 e4 00 00 00')
    # No completion/part proof exists for phase1/2. Their AP bytes are only
    # advisory; do not use last-generation tail keys or borrow AP proof bits.
    c.emit('83 7e 64 03');c.branch('0f 84','keep_normal_proof')
    c.emit('83 7e 64 05');c.branch('0f 84','keep_normal_proof')
    c.emit('c7 47 58 03 00 00 00 c7 47 38 00 00 00 00')
    c.emit('41 80 7a 73 00');c.branch('0f 84','proof_ready')
    c.emit('83 4f 38 01');c.branch('e9','proof_ready')
    c.label('keep_normal_proof');c.emit('81 67 58 bf fe ff ff 83 4f 58 03')
    c.label('proof_ready')
    c.emit('83 7f 34 00');c.branch('0f 84','filtered')
    c.emit('83 7f 34 ff');c.branch('0f 84','filtered')
    c.emit('83 7f 50 01');c.branch('0f 87','filtered')
    c.address('48 b9','entity_manager_global');c.emit('48 8b 09 48 85 c9');c.branch('0f 84','filtered')
    c.emit('48 89 fa');c.call('qualifier')
    c.emit('8b 47 58 25 43 01 00 00 3d 43 01 00 00');c.branch('0f 85','filtered')
    c.emit('83 7f 54 01');c.branch('0f 85','filtered')
    c.emit('83 7e 64 01');c.branch('0f 84','stage')
    # The staged AP identity is compared, but it does not have part-key proof.
    # Normal/reflection tuples compare both the raw fields and frozen part keys.
    for load,compare in [('48 8b 47 10','48 3b 46 10'),('8b 47 2c','3b 46 2c'),
        ('8b 47 30','3b 46 30'),('8b 47 34','3b 46 34'),
        ('8b 47 50','3b 46 50'),('8b 47 44','3b 46 44')]:
        c.emit(load+' '+compare);c.branch('0f 85','filtered')
    c.emit('83 7e 64 02');c.branch('0f 84','stage')
    for at,saved in [(NODE_OFFSET,0xE0),(HASH_OFFSET,0xE4)]:
        c.emit('8b 84 24 '+struct.pack('<I',saved).hex(' ')+' 3b 86 '+struct.pack('<I',at).hex(' '))
        c.branch('0f 85','filtered')
    c.emit('83 7e 64 05');c.branch('0f 84','restore')  # already pending this same reflection
    c.label('stage')
    c.emit('c7 47 3c 02 00 00 00')
    for at in range(0,96,8):c.emit('48 8b 47 '+bytes([at]).hex()+' 48 89 46 '+bytes([at]).hex())
    for at,saved in [(NODE_OFFSET,0xE0),(HASH_OFFSET,0xE4)]:
        c.emit('8b 84 24 '+struct.pack('<I',saved).hex(' ')+' 89 86 '+struct.pack('<I',at).hex(' '))
    c.emit('c7 46 64 05 00 00 00');c.branch('e9','restore')
    c.label('filtered');c.address('48 b8','bridge');c.emit('f0 48 ff 40 38');c.branch('e9','restore')
    c.label('frame_reject');c.address('48 b8','arena');c.emit('f0 48 ff 40 20');c.branch('e9','restore')
    P.restore(c,'reflection_writeback')
    result=P.entry('reflection_writeback',c,P.DEFAULT_UNWIND)
    result.update(frame_allocation=P.old.FRAME_BYTES,frame_register='RBP',
        original_parent_unwind_unchanged=True,original_ADDSS_before_save=True,
        original_ADDSS_replayed_once=True,fresh_reflection_qualification=True)
    return result


def package():
    profile=copy.deepcopy(G.package());raw,_=P.copies.load_sources()
    at=SITE_RVA-P.copies.REGIONS['contact'][0]
    if raw['contact'][at:at+5]!=SITE_PIN:raise ValueError('REFLECTION_WRITEBACK_SOURCE_PIN')
    # These actual prologue bytes establish the caller's100-byte frame bias.
    if raw['contact'][:25].hex()!='40554157488dac2478daffffb888260000e8ba83d500482be0':
        raise ValueError('REFLECTION_CONTACT_FRAME_SOURCE')
    profile['entries']=[normal_gateway()if e['name']=='normal_final'else e for e in profile['entries']]
    profile['entries'].append(reflection_gateway())
    profile['sites'].append({'name':'reflection_writeback','region':'contact','rva':SITE_RVA,
        'pin_hex':SITE_PIN.hex(),'replace_bytes':5,'patch_kind':'OWN_COPY_E8_CALL_NOP','original_rva':None})
    profile['count_contract'].update(reflection_writeback_overrides_normal=True,
        reflection_writeback_publishes=False,fresh_reflection_qualification_required=True)
    profile.update(revision='copy_pending_reflection_observer_v1',
        immutable_normal_guard_generator_sha=GUARD_SHA,ricochet_producer_verified=False,
        reflection_writeback_source_verified=True,ordinary_physical_publish=False,
        owned_reflection_replay_verified=False,reflection_writeback_direct_FIFO_publish=False,
        reflection_frame={'parent_RBP_minus_RSP':0x100,'GW_savebase_minus_parentRSP':-0x140,
            'original_RBP_save_offset':0x130,'HI_from_parent_RBP':0x580,'DP_from_parent_RBP':0x3E0,
            'slotindex_from_parent_RBP':-0x58,'slot_from_context':0x3040,'slot_stride':0x70,
            'slotindex_qword_store_rva':0x13AC36F,'slotindex_qword_store_pin':'488945a8',
            'slotindex_u32_load_rva':0x13AC357,'slotindex_u32_load_pin':'428b843b44700e00'},
        reflection_part_keys={'node_HI_offset':0x24,'part_hash_HI_offset':0x7C,
            'row_node_offset':NODE_OFFSET,'row_part_hash_offset':HASH_OFFSET,
            'phase1':'fresh_only','phase2':'AP_tuple_compared_but_AP_proof_not_borrowed',
            'phase3':'full_raw_and_part_keys_compared_preserve_AP_custom_force',
            'phase5':'fresh_full_tuple_compared_duplicate_keeps_pending'},
        reflection_scratch={'offset':160,'bytes':96,'temporary_only':True},
        reflection_qualification={'full_peer_matches':['arena','bridge','current_user'],
            'target_enemy_catalogue':True,'source_personal_catalogue':True,
            'owner_nonzero_and_not_marker':True,'attack_kinds':[0,1],
            'parent_RSP_and_current_slot_checked':True,'cached_type_proof_accepted':False,
            'failure_preserves_normal_row_and_part_keys':True})
    if len(profile['entries'])!=21 or len(profile['sites'])!=8:
        raise ValueError('REFLECTION_FIXED_PACKAGE_SHAPE')
    return profile


manifest=package
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    path=parser.parse_args().output;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(package(),indent=2)+'\n',encoding='utf8');print(path.resolve())
