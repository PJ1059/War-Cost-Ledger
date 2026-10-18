"""Pure six-site pending producer for private copies; no Game or native calls.

Normal snapshots remain pending until a new Build or the common parent exit.
Actual physical success wins over that same contact. Existing transport,
catalogue and bounded entity leaves are reused; old profiles stay immutable.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hit_callable_profile as old
import hit_observer_package as observer
from hit_bridge_owned import publish_code, drain_code, PUSH_SI_DI_UNWIND
import hit_world_contact_ap_physical_code_copy as copies

RelocCode, gp, SAVED = old.RelocCode, old.gp, old.SAVED
IDLE, BEGUN, AP_STAGED, NORMAL_PENDING, AMBIGUOUS, PHYSICAL_PENDING = range(6)
ARENA_UNWIND = bytes.fromhex('010704000752037002600130')
COMMIT_UNWIND = bytes.fromhex('010603000642027001600000')
DEFAULT_UNWIND = bytes.fromhex('01130605130310012400087007600650')
SITES = (
    ('contact_begin', 'contact', 0x13AD4E8, 'e8c350efff', 0x12A25B0),
    ('default_delta', 'ap', 0x129CABC, 'f3410f5cc1', None),
    ('custom_curve', 'ap', 0x129CADF, 'e85cfeffff', 0x129C940),
    ('normal_final', 'contact', 0x13AD88B, 'e8a004efff', 0x129DD30),
    ('physical_success', 'physical', 0x13B11D4, '32c088451c', None),
    ('contact_end', 'contact', 0x13B053F, '488b8dc0240000', None))


def commit_code():
    """u32 commit(arena RCX,row RDX): one frozen pending contact, never AP alone."""
    c = RelocCode();c.emit('56 57 48 83 ec 28 48 89 cf 48 89 d6')
    c.emit('83 7e 64 03');c.branch('0f 84', 'normal')
    c.emit('83 7e 64 05');c.branch('0f 85', 'not_pending')
    c.emit('8b 46 58 83 e0 03 83 f8 03');c.branch('0f 85', 'unproved')
    c.branch('e9', 'identity')
    c.label('normal')
    c.emit('8b 46 58 25 bf 00 00 00 3d bf 00 00 00');c.branch('0f 85', 'unproved')
    c.emit('83 7e 38 00');c.branch('0f 85', 'filtered')
    c.label('identity')
    c.emit('48 8b 46 08 48 3b 47 08');c.branch('0f 85', 'filtered')
    c.address('48 b8', 'current_user_global');c.emit('48 8b 00 48 85 c0');c.branch('0f 84', 'filtered')
    c.emit('48 8b 88 98 b3 00 00 48 85 c9');c.branch('0f 84', 'filtered')
    c.emit('48 3b 4e 10');c.branch('0f 85', 'filtered')
    c.emit('48 3b 4f 10');c.branch('0f 85', 'filtered')
    c.address('48 b8', 'bridge');c.emit('48 3b 48 10');c.branch('0f 85', 'filtered')
    # Hostility/source qualification was frozen with the actual contact, before
    # the original damage consumer can remove that target. Never redo a late
    # descriptor lookup at next-Build and discard a killing hit as "absent".
    c.emit('8b 46 58 25 43 01 00 00 3d 43 01 00 00');c.branch('0f 85', 'filtered')
    # Spend before transport even on a full queue: a rejected submission is not
    # retried as a second branch of this contact.
    c.emit('c7 46 64 00 00 00 00')
    c.address('48 b9', 'bridge');c.emit('48 89 f2');c.call('publish')
    c.branch('e9', 'return')
    c.label('unproved');c.emit('f0 48 ff 47 20 31 c0');c.branch('e9', 'spend')
    c.label('filtered');c.address('48 b8', 'bridge');c.emit('f0 48 ff 40 38 b8 02 00 00 00')
    c.label('spend');c.emit('c7 46 64 00 00 00 00');c.branch('e9', 'return')
    c.label('not_pending');c.emit('31 c0')
    c.label('return');c.emit('48 83 c4 28 5f 5e c3')
    return c


def arena_code(operation):
    """Bounded thread/HI/parent-RSP arena. begin/end are commit boundaries."""
    if operation not in ('begin', 'lookup', 'end'):raise ValueError('pending arena operation')
    c = RelocCode();c.emit('53 56 57 48 83 ec 30 48 89 ce 48 89 d7 4c 89 44 24 20')
    c.emit('83 7e 28 01');c.branch('0f 85', 'empty' if operation == 'end' else 'reject')
    c.emit('48 85 ff');c.branch('0f 84', 'empty' if operation == 'end' else 'reject')
    if operation != 'lookup':
        c.emit('4d 85 c0');c.branch('0f 84', 'reject')
    c.emit('65 48 8b 04 25 30 00 00 00 44 8b 48 48')
    c.emit('44 89 cb 8b 06 ff c8 21 c3 41 ba 08 00 00 00')
    c.label('probe');c.emit('4c 69 db 80 02 00 00 4c 03 5e 30 41 8b 43 60 44 39 c8')
    c.branch('0f 84', 'found');c.emit('85 c0')
    if operation == 'begin':
        c.branch('0f 85', 'next');c.emit('f0 45 0f b1 4b 60');c.branch('0f 84', 'found')
        c.emit('44 39 c8');c.branch('0f 84', 'found')
    else:c.branch('0f 84', 'empty' if operation == 'end' else 'reject')
    c.label('next');c.emit('ff c3 8b 06 ff c8 21 c3 41 ff ca');c.branch('0f 85', 'probe')
    c.branch('e9', 'empty' if operation == 'end' else 'reject')
    c.label('found');c.emit('4c 89 db')  # stable row survives nested commit calls
    if operation == 'begin':
        c.emit('83 7b 64 00');c.branch('0f 84', 'fresh')
        c.emit('48 3b 7b 68');c.branch('0f 85', 'reject')
        c.emit('4c 3b 83 70 02 00 00');c.branch('0f 85', 'reject')
        c.emit('48 89 f1 48 89 da');c.call('commit')
        c.label('fresh');c.emit('4c 8b 44 24 20 4c 89 83 70 02 00 00')
        c.emit('c7 43 64 00 00 00 00 c7 43 58 00 00 00 00')
        c.emit('b8 01 00 00 00 f0 48 0f c1 46 18 48 ff c0 49 89 c0 48 c1 e8 20 48 85 c0')
        c.branch('0f 85', 'reject')
        for at in range(0, 96, 8):c.emit('48 c7 43 ' + bytes([at]).hex() + ' 00 00 00 00')
        c.emit('48 8b 46 08 48 89 43 08 4c 89 43 28 48 89 7b 18 48 89 7b 68')
        c.emit('c7 43 70 00 00 00 00')
        for at in (64, 68, 72, 92):c.emit('c7 43 ' + bytes([at]).hex() + ' 00 00 c0 7f')
        c.emit('c7 43 64 01 00 00 00 48 89 d8')
    elif operation == 'lookup':
        c.emit('48 3b 7b 68');c.branch('0f 85', 'reject')
        c.emit('8b 43 64 83 f8 01');c.branch('0f 84', 'ready')
        c.emit('83 f8 02');c.branch('0f 84', 'ready')
        c.emit('83 f8 03');c.branch('0f 84', 'ready')
        c.emit('83 f8 05');c.branch('0f 85', 'reject')
        c.label('ready');c.emit('48 89 d8')
    else:
        c.emit('83 7b 64 00');c.branch('0f 84', 'empty')
        c.emit('48 3b 7b 68');c.branch('0f 85', 'reject')
        c.emit('4c 3b 83 70 02 00 00');c.branch('0f 85', 'reject')
        c.emit('48 89 f1 48 89 da');c.call('commit')
        c.emit('c7 43 64 00 00 00 00 48 c7 43 68 00 00 00 00 48 c7 83 70 02 00 00 00 00 00 00')
        c.emit('c7 43 58 00 00 00 00 b8 01 00 00 00')
    c.branch('e9', 'return')
    c.label('empty');c.emit('b8 01 00 00 00');c.branch('e9', 'return')
    c.label('reject');c.emit('f0 48 ff 46 20 31 c0')
    c.label('return');c.emit('48 83 c4 30 5f 5e 5b c3')
    return c


def hi_arg(c, mode):
    if mode == 'contact_end':c.emit('48 8b 94 24 30 01 00 00 48 81 c2 80 05 00 00')
    else:old.hi_arg(c, mode)


def lookup(c, mode):
    c.address('48 b9', 'arena');hi_arg(c, mode);c.emit('45 31 c0');c.call('lookup')
    c.emit('48 85 c0');c.branch('0f 84', 'restore');c.emit('48 89 c6')


def raw_snapshot(c, mode):
    if mode == 'normal_final':gp(c, False, 10, SAVED[8]);gp(c, False, 11, SAVED[2])
    else:c.emit('4d 89 ea 4c 8b 9c 24 30 01 00 00')
    # Match an existing AP/final tuple before joining another branch of the
    # same HI. Pointer/ordinal alone never certifies a different enemy or part.
    c.emit('83 7e 64 01');c.branch('0f 84', 'identity_ready')
    c.emit('49 8b 82 10 01 00 00 48 3b 46 10');c.branch('0f 85', 'identity_conflict')
    for load, cmp in [('41 8b 42 20', '3b 46 2c'), ('41 8b 82 80 00 00 00', '3b 46 30'),
                      ('41 8b 82 00 01 00 00', '3b 46 34'), ('41 8b 02', '3b 46 50'),
                      ('41 8b 42 50', '3b 46 44')]:
        c.emit(load + ' ' + cmp);c.branch('0f 85', 'identity_conflict')
    c.label('identity_ready')
    if mode == 'normal_final':
        c.emit('83 7e 64 05');c.branch('0f 84', 'restore')
    c.emit('49 8b 82 10 01 00 00 48 89 46 10')
    for load, store in [('41 8b 42 20', '89 46 2c'), ('41 8b 82 80 00 00 00', '89 46 30'),
                        ('41 8b 82 00 01 00 00', '89 46 34'), ('41 8b 02', '89 46 50'),
                        ('41 8b 42 50', '89 46 44'), ('41 8b 43 04', '89 46 48'), ('41 8b 03', '89 46 4c')]:
        c.emit(load + ' ' + store)
    c.emit('83 4e 58 03')
    if mode == 'normal_final':
        c.emit('83 66 38 fc 41 80 7a 73 00');c.branch('0f 84', 'hi_force_ready')
        c.emit('83 4e 38 01');c.label('hi_force_ready')
        gp(c, False, 0, SAVED[0]);c.emit('f6 80 fc 00 00 00 01');c.branch('0f 84', 'projectile_force_ready')
        c.emit('83 4e 38 02');c.label('projectile_force_ready')
        c.emit('83 4e 58 20 c7 46 3c 01 00 00 00 c7 46 64 03 00 00 00')
    else:c.emit('c7 46 3c 02 00 00 00 c7 46 64 05 00 00 00 44 89 7e 20')
    c.emit('8b 46 58 25 40 01 00 00 3d 40 01 00 00');c.branch('0f 84', 'types_ready')
    c.address('48 b9', 'entity_manager_global');c.emit('48 8b 09 48 85 c9');c.branch('0f 84', 'types_ready')
    c.emit('48 89 f2');c.call('qualifier');c.label('types_ready')
    c.branch('e9', 'restore')
    c.label('identity_conflict');c.emit('c7 46 64 04 00 00 00 c7 46 58 00 00 00 00')
    c.address('48 b8', 'arena');c.emit('f0 48 ff 40 20')


def restore(c, mode):
    c.label('restore');c.emit('83 bc 24 d0 00 00 00 01');c.branch('0f 85', 'no_active')
    c.address('48 b8', 'arena');c.emit('f0 ff 48 2c');c.label('no_active')
    c.emit('0f ae 94 24 c0 00 00 00')
    for xmm in range(6):c.emit('0f 28 ' + bytes([0x84+xmm*8, 0x24]).hex(' ') + ' ' + struct.pack('<I',96+16*xmm).hex(' '))
    for reg, at in SAVED.items():
        if reg != 0:gp(c, False, reg, at)
    c.emit('8a 84 24 c9 00 00 00 04 7f 8a a4 24 c8 00 00 00 9e');gp(c, False, 0, SAVED[0])
    if mode == 'physical_success':
        c.emit('4c 8b 94 24 30 01 00 00 32 c0 41 88 42 1c');gp(c, False, 10, SAVED[10])
    c.emit('48 8d a5 20 01 00 00 5f 5e 5d')
    if mode == 'contact_end':c.emit('48 8b 8d c0 24 00 00')
    if mode in ('contact_begin', 'custom_curve', 'normal_final'):c.address('ff 25 00 00 00 00', 'original_' + mode)
    else:c.emit('c3')


def gateway(mode):
    c = RelocCode()
    if mode == 'default_delta':c.emit('f3 41 0f 5c c1')  # real operation precedes save, exactly once
    old.prolog(c)
    if mode in ('contact_begin', 'contact_end'):
        c.address('48 b9', 'arena');hi_arg(c, mode);c.emit('4c 8d 84 24 40 01 00 00')
        c.call('begin' if mode == 'contact_begin' else 'end')
    else:
        lookup(c, mode)
        if mode in ('default_delta', 'custom_curve'):
            value = 1 if mode == 'default_delta' else 2
            c.emit('8b 46 70 85 c0');c.branch('0f 84', 'set_curve')
            c.emit('83 f8 ' + bytes([value]).hex());c.branch('0f 84', 'set_curve')
            c.emit('c7 46 64 04 00 00 00 c7 46 58 00 00 00 00');c.branch('e9', 'restore')
            c.label('set_curve');c.emit('c7 46 70 ' + struct.pack('<I', value).hex(' ') + ' 83 4e 58 10 83 66 38 fb')
            if mode == 'custom_curve':c.emit('83 4e 38 04')
            else:
                # XMM0 and its MXCSR are already post-original-SUBSS. Only bit
                # copies follow; no recomputed subtraction or masked arithmetic.
                c.emit('f3 44 0f 11 56 40 f3 44 0f 11 4e 44 f3 0f 11 46 5c')
                c.emit('48 8b 83 10 01 00 00 48 89 46 10')
                for load, store in [('8b 43 20','89 46 2c'),('8b 83 80 00 00 00','89 46 30'),
                                    ('8b 83 00 01 00 00','89 46 34'),('8b 03','89 46 50')]:c.emit(load+' '+store)
                c.emit('81 4e 58 8c 00 00 00 83 7e 64 01');c.branch('0f 85', 'ap_ready')
                c.emit('c7 46 64 02 00 00 00');c.label('ap_ready')
        else:raw_snapshot(c, mode)
    restore(c, mode);raw = c.finish()
    return {'name':mode, 'code_hex':raw.hex(), 'relocations':c.relocations,
        'unwind_hex':(DEFAULT_UNWIND if mode=='default_delta' else old.GATE_UNWIND).hex(),
        'executable_length':len(raw)-(8 if mode in ('contact_begin','custom_curve','normal_final') else 0),
        'entry_offset':0, 'frame_allocation':old.FRAME_BYTES, 'frame_register':'RBP',
        'original_parent_unwind_unchanged':True, 'default_SUBSS_before_save':mode=='default_delta'}


def entry(name, c, uw):
    raw = c.finish() if isinstance(c, RelocCode) else c
    return {'name':name, 'code_hex':raw.hex(), 'relocations':c.relocations if isinstance(c,RelocCode) else [],
            'unwind_hex':uw.hex(), 'entry_offset':0, 'executable_length':len(raw)}


def pending_pause_code():
    """Disable and discard unfinished tuples while owning configure_lock.

    u32(bridge,arena,epoch64,peer64), same push-SI/DI unwind as the original
    control leaf. A resume cannot observe stale pending rows between disabling
    and clearing them; an active gateway makes this call fail for a later retry.
    Published FIFO records, identity, ordinal and immutable row owners survive.
    """
    c = RelocCode()
    c.emit('56 57 48 89 ce 48 89 d7 31 c0 41 ba 01 00 00 00 f0 44 0f b1 57 38')
    c.branch('0f 85', 'lock_failed')
    for offset, register in [(8, '4c 39 46'), (16, '4c 39 4e'),
                             (8, '4c 39 47'), (16, '4c 39 4f')]:
        c.emit(register + ' ' + bytes([offset]).hex());c.branch('0f 85', 'unlock_failed')
    c.emit('f6 47 3c 01');c.branch('0f 85', 'unlock_failed')
    c.emit('83 7f 28 00');c.branch('0f 84', 'paused')
    c.emit('83 7f 3c fc');c.branch('0f 87', 'unlock_failed')
    c.emit('f0 ff 47 3c c7 47 28 00 00 00 00 f0 ff 47 3c')
    c.label('paused');c.emit('83 7f 2c 00');c.branch('0f 85', 'unlock_failed')
    # This profile owns exactly 32 rows of 640B, never a variable-size scan.
    c.emit('83 3f 20');c.branch('0f 85', 'unlock_failed')
    c.emit('81 7f 04 80 02 00 00');c.branch('0f 85', 'unlock_failed')
    c.emit('4c 8b 5f 30 4d 85 db');c.branch('0f 84', 'unlock_failed')
    c.emit('41 ba 20 00 00 00')
    c.label('clear_row')
    c.emit('41 c7 43 64 00 00 00 00 41 c7 43 58 00 00 00 00')
    c.emit('49 c7 43 68 00 00 00 00 49 c7 83 70 02 00 00 00 00 00 00')
    c.emit('41 c7 43 70 00 00 00 00 49 81 c3 80 02 00 00 41 ff ca')
    c.branch('0f 85', 'clear_row')
    c.emit('b8 01 00 00 00');c.branch('e9', 'unlock')
    c.label('unlock_failed');c.emit('31 c0')
    c.label('unlock');c.emit('c7 47 38 00 00 00 00');c.branch('e9', 'return')
    c.label('lock_failed');c.emit('31 c0')
    c.label('return');c.emit('5f 5e c3')
    return c


def pending_resume_code():
    """Re-enable under the same lock; a failed CAS always returns zero."""
    c = RelocCode()
    c.emit('56 57 48 89 ce 48 89 d7 31 c0 41 ba 01 00 00 00 f0 44 0f b1 57 38')
    c.branch('0f 85', 'lock_failed')
    for offset, register in [(8, '4c 39 46'), (16, '4c 39 4e'),
                             (8, '4c 39 47'), (16, '4c 39 4f')]:
        c.emit(register + ' ' + bytes([offset]).hex());c.branch('0f 85', 'unlock_failed')
    c.emit('f6 47 3c 01');c.branch('0f 85', 'unlock_failed')
    c.emit('83 7f 2c 00');c.branch('0f 85', 'unlock_failed')
    c.emit('83 7f 28 01');c.branch('0f 84', 'success')
    c.emit('83 7f 3c fc');c.branch('0f 87', 'unlock_failed')
    c.emit('f0 ff 47 3c c7 47 28 01 00 00 00 f0 ff 47 3c')
    c.label('success');c.emit('b8 01 00 00 00');c.branch('e9', 'unlock')
    c.label('unlock_failed');c.emit('31 c0')
    c.label('unlock');c.emit('c7 47 38 00 00 00 00');c.branch('e9', 'return')
    c.label('lock_failed');c.emit('31 c0')
    c.label('return');c.emit('5f 5e c3')
    return c


def package():
    raw, source_evidence = copies.load_sources()
    for name, region, rva, pin, callee in SITES:
        start = rva-copies.REGIONS[region][0]
        if raw[region][start:start+len(bytes.fromhex(pin))].hex()!=pin:raise ValueError('PENDING_SITE_PIN:'+name)
    previous = observer.package()
    entries = [gateway(name) for name, *_ in SITES]
    entries += [entry('commit', commit_code(), COMMIT_UNWIND)]
    entries += [entry(name, arena_code(name), ARENA_UNWIND) for name in ('begin','lookup','end')]
    entries += [e for e in previous['entries'] if e['name'] in ('publish','drain','configure','qualifier','resolve','allow')]
    entries += [entry('pause', pending_pause_code(), PUSH_SI_DI_UNWIND), entry('resume', pending_resume_code(), PUSH_SI_DI_UNWIND)]
    result = dict(previous)
    result.update(revision='copy_pending_observer_v1', entries=entries,
        sites=[{'name':name,'region':region,'rva':rva,'pin_hex':pin,'replace_bytes':len(bytes.fromhex(pin)),
                'patch_kind':'OWN_COPY_E8_CALL_NOP','original_rva':callee}
               for name,region,rva,pin,callee in SITES],
        source_code_packets=source_evidence, current_user_global_rva=0x347CEF0,
        peer_source_offset=0xB398, native_pending_merge=True,
        count_contract={'normal_final_publishes':False,'AP_publishes':False,
            'physical_success_publishes':False,'next_begin_and_common_exit_commit_once':True,
            'physical_success_overrides_normal':True,'current_peer_compared_u64':True,
            'enemy_and_personal_source_required':True,'normal_missing_AP_is_rejected':True,
            'pause_discards_unfinished_contacts_under_configure_lock':True},
        pause_contract={'fixed_rows':32,'row_stride':640,'active_must_be_zero':True,
            'pause_and_resume_lock_busy_return':0,
            'clears':['phase','capture_flags','HI','parent_RSP','curve'],
            'preserves':['FIFO','epoch','peer','accepted_sequence','contact_ordinal','row_owner']},
        arena_phases={'idle':0,'begun':1,'AP':2,'normal_pending':3,'ambiguous':4,'physical_pending':5},
        group_identity=['epoch','native_thread','parent_RSP','new_Build_ordinal'],
        original_instruction_offsets_preserved=True, Game_accessed=False, new_RX_executed=False,
        Game_or_exception_safety_proven=False, game_connected=False, coverage_complete=False,
        native_registered=False, owned_replay_verified=False)
    return result


manifest = package
if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    path=p.parse_args().output;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(package(),indent=2)+'\n',encoding='utf8');print(str(path.resolve()))
