"""Pure bounded two-tail diagnostic profile; never accesses Game or native APIs.

The original pending generator and its ordinary classifications stay immutable.
Diagnostic tags are not game enums and are never submitted to the ordinary FIFO.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PENDING = HERE / 'hit_copy_pending_observer.py'
PENDING_SHA = '95b7a98c4d1c1b7201049b9fc31af71a981f68c9e0d16db540955277240aef0e'
if hashlib.sha256(PENDING.read_bytes()).hexdigest() != PENDING_SHA:
    raise ValueError('TAIL_DIAGNOSTIC_PENDING_SOURCE_CHANGED')
import hit_copy_pending_observer as P

ALT_RVA, ALT_PIN = 0x13B11C8, bytes.fromhex('b00188451c')
DIAG_UNWIND = bytes.fromhex('010704000772037002600130')
CONTRACT = {'revision':1,'head_offset':128,'head_bytes':32,'scratch_offset':160,
    'record_offset':256,'record_bytes':96,'capacity':16,'alt_tag':3,'true_tag':4}


def helper():
    """GW-only u32(arena,HI,DP,tag); counts precede full-peer/type filtering.

    Existing GW active/generation admission surrounds this leaf. It finds an
    already-owned row without claiming it or changing ordinary rejection state.
    Only private diagnostic scratch, head and single-publication slots are written.
    R15D is the original physical slot, preserved by these gateways and this leaf.
    """
    c=P.RelocCode();c.emit('53 56 57 48 83 ec 40 48 89 ce 48 89 d7 4c 89 c3 44 89 4c 24 20')
    c.emit('83 3e 20');c.branch('0f 85','fail')
    c.emit('81 7e 04 80 02 00 00');c.branch('0f 85','fail')
    c.emit('4c 8b 56 30 4d 85 d2');c.branch('0f 84','fail')
    c.emit('49 81 c2 80 00 00 00 48 8b 46 08 49 89 42 18')
    c.emit('41 83 f9 03');c.branch('0f 84','alt')
    c.emit('41 83 f9 04');c.branch('0f 85','fail')
    c.emit('f0 49 ff 42 08');c.branch('e9','identity')
    c.label('alt');c.emit('f0 49 ff 02')
    c.label('identity')
    c.emit('48 8b 87 10 01 00 00 48 85 c0');c.branch('0f 84','fail')
    c.emit('48 3b 46 10');c.branch('0f 85','fail')
    c.address('48 b9','bridge');c.emit('48 3b 41 10');c.branch('0f 85','fail')
    c.address('48 b9','bridge');c.emit('48 8b 56 08 48 3b 51 08');c.branch('0f 85','fail')
    c.address('48 b9','current_user_global');c.emit('48 8b 09 48 85 c9');c.branch('0f 84','fail')
    c.emit('48 3b 81 98 b3 00 00');c.branch('0f 85','fail')
    c.emit('65 48 8b 04 25 30 00 00 00 44 8b 48 48 44 89 ca 83 e2 1f 41 ba 08 00 00 00')
    c.label('probe');c.emit('48 69 c2 80 02 00 00 48 03 46 30 44 39 48 60')
    c.branch('0f 84','row');c.emit('83 78 60 00');c.branch('0f 84','fail')
    c.emit('ff c2 83 e2 1f 41 ff ca');c.branch('0f 85','probe');c.branch('e9','fail')
    c.label('row');c.emit('48 3b 78 68');c.branch('0f 85','fail')
    c.emit('48 89 44 24 28 4c 8d 90 a0 00 00 00 4c 89 54 24 30')
    # Clone ordinary raw fields into separate scratch; no source field is spent.
    for at in range(0,96,8):
        c.emit('4c 8b 58 '+bytes([at]).hex()+' 4d 89 5a '+bytes([at]).hex())
    c.emit('8b 48 64 41 89 4a 24 48 8b 4e 08 49 89 4a 08')
    c.emit('48 8b 8f 10 01 00 00 49 89 4a 10 49 89 7a 18 45 89 7a 20')
    for load,store in [('8b 4f 20','41 89 4a 2c'),('8b 8f 80 00 00 00','41 89 4a 30'),
                       ('8b 8f 00 01 00 00','41 89 4a 34'),('8b 4f 50','41 89 4a 44'),
                       ('8b 4b 04','41 89 4a 48'),('8b 0b','41 89 4a 4c'),('8b 0f','41 89 4a 50')]:
        c.emit(load+' '+store)
    c.emit('8b 4c 24 20 41 89 4a 3c 41 c7 42 54 00 00 00 00 41 c7 42 58 0b 00 00 00')
    # AP/delta and effects are advisory copies of pending state, without AP/force
    # proof bits. Fresh current HI supplies identity/armor; qualifier supplies
    # enemy/personal-projectile bits only to this independent scratch record.
    c.address('48 b9','entity_manager_global');c.emit('48 8b 09 48 85 c9');c.branch('0f 84','fail')
    c.emit('4c 89 d2');c.call('qualifier')
    c.emit('4c 8b 54 24 30 41 8b 42 58 25 43 01 00 00 3d 43 01 00 00');c.branch('0f 85','fail')
    c.emit('41 83 7a 54 01');c.branch('0f 85','fail')
    c.emit('48 8b 56 30 48 81 c2 80 00 00 00 8b 42 10 83 f8 10');c.branch('0f 83','fail')
    c.emit('44 8d 48 01 f0 44 0f b1 4a 10');c.branch('0f 85','fail')
    c.emit('89 44 24 38 44 89 c9 49 89 0a 4c 69 d8 80 02 00 00 4c 03 5e 30 49 81 c3 00 01 00 00')
    for at in range(0,96,8):
        c.emit('49 8b 42 '+bytes([at]).hex()+' 49 89 43 '+bytes([at]).hex())
    c.emit('8b 4c 24 38 f0 0f ab 4a 14 b8 01 00 00 00');c.branch('e9','return')
    c.label('fail');c.emit('31 c0')
    c.label('return');c.emit('48 83 c4 40 5f 5e 5b c3')
    return c


def diagnose(c,tag):
    c.address('48 b9','arena');c.emit('4c 89 ea 4c 8b 84 24 30 01 00 00 41 b9 '+struct.pack('<I',tag).hex(' '))
    c.call('tail_diagnostic')


def gateway(alt=False):
    c=P.RelocCode();P.old.prolog(c);diagnose(c,3 if alt else 4)
    if alt:
        P.restore(c,'physical_alt_tail')
        epilog=bytes.fromhex('488da5200100005f5e5dc3')
        if c.code[-len(epilog):]!=epilog:raise ValueError('DIAG_ALT_RESTORE_TEMPLATE')
        # Replay before the canonical epilog, while the GW save area still
        # exists. MOV changes no incoming flags; restore its temporary R10.
        del c.code[-len(epilog):]
        c.emit('4c 8b 94 24 30 01 00 00 b0 01 41 88 42 1c')
        P.gp(c,False,10,P.SAVED[10]);c.emit(epilog.hex(' '))
    else:
        P.lookup(c,'physical_success');P.raw_snapshot(c,'physical_success');P.restore(c,'physical_success')
    result=P.entry('physical_alt_tail' if alt else 'physical_success',c,P.old.GATE_UNWIND)
    result.update(frame_allocation=P.old.FRAME_BYTES,frame_register='RBP',
        original_parent_unwind_unchanged=True,diagnostic_only_alt=alt)
    return result


def package():
    profile=copy.deepcopy(P.package());raw,_=P.copies.load_sources()
    at=ALT_RVA-P.copies.REGIONS['physical'][0]
    if raw['physical'][at:at+5]!=ALT_PIN:raise ValueError('DIAG_ALT_SOURCE_PIN')
    profile['entries']=[gateway() if e['name']=='physical_success' else e for e in profile['entries']]
    profile['entries'] += [gateway(True),P.entry('tail_diagnostic',helper(),DIAG_UNWIND)]
    profile['sites'].append({'name':'physical_alt_tail','region':'physical','rva':ALT_RVA,
        'pin_hex':ALT_PIN.hex(),'replace_bytes':5,'patch_kind':'OWN_COPY_E8_CALL_NOP','original_rva':None})
    profile.update(revision='copy_pending_tail_diagnostic_v1',tail_diagnostic=CONTRACT,
        immutable_pending_generator_sha=PENDING_SHA,diagnostic_FIFO_publish=False,
        diagnostic_tags_are_game_enums=False,diagnostic_AP_fields_are_advisory=True,
        diagnostic_qualification='full_peer_and_fresh_enemy_personal_projectile',
        diagnostic_raw_generation_field='pending_phase',diagnostic_raw_sequence_field='diagnostic_slot_plus_one',
        diagnostic_counts_before_identity_filter=True,diagnostic_reserved_spare_bytes=[128,624],
        diagnostic_epoch_reset='existing_quiescent_configure_clears_whole_rows',
        diagnostic_pause_preserves_samples=True,diagnostic_flight_before_after_captured=False,
        ordinary_classification_rules_unchanged=True,owned_diagnostic_replay_verified=False)
    return profile


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    path=parser.parse_args().output;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(package(),indent=2)+'\n',encoding='utf8');print(path.resolve())
