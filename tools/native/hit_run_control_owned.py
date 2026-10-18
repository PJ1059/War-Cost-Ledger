"""Pause/resume the owned observer without clearing pending records or identity."""
import argparse
import ctypes
import json
from pathlib import Path

from hit_bridge_owned import OwnedBridge, PUSH_SI_DI_UNWIND, _Code


def control_code(resume=False):
    # u32(bridge,arena,epoch64,peer64); no calls, allocation or waiting loop.
    c = _Code()
    c.emit('56 57 48 89 ce 48 89 d7 31 c0 41 ba 01 00 00 00 f0 44 0f b1 57 38')
    c.branch('0f 85', 'failed')
    for offset, register in [(8, '4c 39 46'), (16, '4c 39 4e')]:
        c.emit(register + ' ' + bytes([offset]).hex()); c.branch('0f 85', 'unlock_failed')
    for offset, register in [(8, '4c 39 47'), (16, '4c 39 4f')]:
        c.emit(register + ' ' + bytes([offset]).hex()); c.branch('0f 85', 'unlock_failed')
    c.emit('f6 47 3c 01'); c.branch('0f 85', 'unlock_failed')
    if resume:
        c.emit('83 7f 2c 00'); c.branch('0f 85', 'unlock_failed')
        c.emit('83 7f 28 01'); c.branch('0f 84', 'success')
    else:
        c.emit('83 7f 28 00'); c.branch('0f 84', 'paused')
    c.emit('83 7f 3c fc'); c.branch('0f 87', 'unlock_failed')
    c.emit('f0 ff 47 3c c7 47 28 ' + ('01' if resume else '00') + ' 00 00 00 f0 ff 47 3c')
    if not resume:
        c.label('paused'); c.emit('83 7f 2c 00'); c.branch('0f 85', 'unlock_failed')
    c.label('success'); c.emit('b8 01 00 00 00'); c.branch('e9', 'unlock')
    c.label('unlock_failed'); c.emit('31 c0')
    c.label('unlock'); c.emit('c7 47 38 00 00 00 00')
    c.label('failed'); c.emit('5f 5e c3')
    return c.finish()


def manifest():
    return {'revision': 'hit_run_control_v1', 'signature': 'uint32_t(void*,void*,uint64_t,uint64_t)',
        'preserves_queue': True, 'preserves_identity': True,
        'entries': [{'name': name, 'code_hex': raw.hex(), 'unwind_hex': PUSH_SI_DI_UNWIND.hex(),
                     'entry_offset': 0, 'executable_length': len(raw), 'relocations': []}
                    for name, raw in [('pause', control_code()), ('resume', control_code(True))]]}


def owned_check():
    from hit_contact_arena_owned import OwnedContactArena
    from hit_callable_profile import configure_code
    with OwnedBridge(capacity=8) as bridge:
        arena = OwnedContactArena(bridge)
        configure = bridge._procedure(configure_code(), ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32,
            unwind=PUSH_SI_DI_UNWIND)
        assert configure(bridge.base, arena.address, bridge.epoch, bridge.local_peer, 1) == 1
        pause, resume = [bridge._procedure(control_code(enable), ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, unwind=PUSH_SI_DI_UNWIND)
            for enable in [False, True]]
        record = bridge.record()
        # Producer records belong to this own fixture, never a game event.
        assert bridge.publish(record)
        before = ctypes.string_at(bridge.base, 64)
        assert pause(bridge.base, arena.address, bridge.epoch, bridge.local_peer) == 1
        assert ctypes.string_at(bridge.base, 64) == before
        assert ctypes.c_uint32.from_address(arena.address + 40).value == 0
        assert pause(bridge.base, arena.address, bridge.epoch, bridge.local_peer) == 1
        assert resume(bridge.base, arena.address, bridge.epoch, bridge.local_peer) == 1
        assert ctypes.string_at(bridge.base, 64) == before
        assert ctypes.c_uint32.from_address(arena.address + 40).value == 1
        ctypes.c_uint32.from_address(arena.address + 44).value = 1
        assert pause(bridge.base, arena.address, bridge.epoch, bridge.local_peer) == 0
        assert ctypes.c_uint32.from_address(arena.address + 40).value == 0
        assert resume(bridge.base, arena.address, bridge.epoch, bridge.local_peer) == 0
        ctypes.c_uint32.from_address(arena.address + 44).value = 0
        assert pause(bridge.base, arena.address, bridge.epoch, bridge.local_peer) == 1
        assert resume(bridge.base, arena.address, bridge.epoch + 1, bridge.local_peer) == 0
        assert resume(bridge.base, arena.address, bridge.epoch, bridge.local_peer + 1) == 0
        assert ctypes.c_uint32.from_address(arena.address + 40).value == 0
        assert len(bridge.drain()) == 1
    return {'status': 'PASS', 'origin': 'own_process_only', 'game_access': False,
            'checks': ['queue_and_sequence_preserved', 'identity_preserved', 'idempotent_pause',
                       'active_pause_is_busy_and_disables', 'resume_busy_or_wrong_identity_refused',
                       'paused_queue_drains']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', required=True, type=Path)
    args = p.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    report = owned_check()
    (args.output / 'profile-manifest.json').write_text(json.dumps(manifest(), indent=2), encoding='utf8')
    (args.output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report))
