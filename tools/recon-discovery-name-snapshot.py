"""Read the already captured discovery row's proven NAME string and 4-person roster.

No type10 pointer is followed; no attribution is assumed from authority/colour.
The row descriptor must remain identical to the saved real discovery sample.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_recon_name_child_source', ROOT / 'tools/recon-chat-row-child-descriptor-snapshot.py')
child = importlib.util.module_from_spec(spec); spec.loader.exec_module(child)
reader, layout = child.reader, child.reader.layout
layout.TOTAL_BYTES = layout.SLICE_BYTES = 4096
layout.TOTAL_READS = layout.SLICE_READS = 64
SOURCE = Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'recon-chat-row-child-descriptors-discovery-20261013-v2/rows.json'
SOURCE_SHA = '09b8e0008e67f3e5fecb2ef294d5f39bc52ea260ae25c4382a7fd7e2c6bab7ca'
ROSTER_GLOBAL, USER_GLOBAL, LOCAL_PEER = 0x347CED8, 0x347CEF0, 0xB398
STRING_BYTES, ROSTER_STRIDE = 64, 0xC0


def source():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA: raise ValueError('RECON_NAME_SOURCE_CHANGED')
    d = json.loads(raw); row = d['rows'][0]; descriptor = row['descriptor']
    args = descriptor['arguments']
    if (row['index'] != 0 or row['identity']['kind'] != 8
        or descriptor['key'] != 0x92871A58 or descriptor['argument_count'] != 2
        or args[0]['key'] != 0x341F7711 or args[0]['type'] != 1
        or args[1]['key'] != 0x38237B81 or args[1]['type'] != 10):
        raise ValueError('RECON_NAME_SOURCE_CONTRACT')
    return d, bytes.fromhex(row['descriptor_hex'])


def string(raw):
    end = raw.find(b'\0')
    if end < 0: raise ValueError('RECON_NAME_STRING_LIMIT')
    return raw[:end].decode('utf8')


def snapshot(process, module, clock=time.perf_counter):
    captured, expected = source(); profile, pins = child.source()
    budget = layout.Budget(process, module, clock, seconds=1.5)
    for rva, pin in tuple((p['rva'], p['hex']) for p in profile['pins'][:2]) + pins + layout.PINS:
        if budget.read(module['game_base'] + rva, len(bytes.fromhex(pin)), image=True, code=True) != bytes.fromhex(pin):
            raise ValueError('RECON_NAME_CODE_PIN')
    state = budget.ptr(module['game_base'] + layout.STATE_GLOBAL, image=True)
    if not layout.pointer(state): raise ValueError('RECON_NAME_STATE_POINTER')
    mode = budget.u32(state + layout.STATE_OFFSET)
    if mode not in (3, 4): raise ValueError('RECON_NAME_EXPECTS_SHIP_OR_MISSION')
    hud = budget.ptr(module['game_base'] + profile['hud'], image=True)
    if not layout.pointer(hud): raise ValueError('RECON_NAME_HUD')
    chat = hud + profile['widget']; root = budget.read(chat, 256); root_id = reader.identity(root)
    at = chat + reader.ROW_BASE; raw = budget.read(at, child.COMPOSITE_BYTES)
    frame_id = reader.identity(raw[:256]); text = raw[child.CHILD:child.CHILD + 256]; text_id = reader.identity(text)
    original = captured['rows'][0]
    # In Ship this is an old notification only if the *current* native owner
    # still has the same row/descriptor. Never dereference its saved NAME first.
    if (hud != captured['hud'] or chat != captured['chat'] or root_id != captured['chat_identity']
        or at != original['container'] or at + child.CHILD != original['address']
        or frame_id != original['container_identity'] or text_id != original['identity']):
        raise ValueError('RECON_NAME_SOURCE_OWNER_CHANGED')
    if (root_id['kind'] != 1 or frame_id['kind'] != 1 or frame_id['parent'] != chat + child.ROW_PARENT
        or frame_id['context'] != root_id['context'] or text_id['kind'] != 8 or text_id['parent'] != at
        or text_id['context'] != root_id['context'] or struct.unpack_from('<Q', raw, 0xE0)[0] != at + child.CHILD
        or raw[child.CHILD + 272:] != expected):
        raise ValueError('RECON_NAME_DISCOVERY_ROW_CHANGED')
    name_pointer = struct.unpack_from('<Q', expected, 16)[0]
    if not layout.pointer(name_pointer, False): raise ValueError('RECON_NAME_POINTER')
    name_raw = budget.read(name_pointer, STRING_BYTES); name = string(name_raw)
    if not name: raise ValueError('RECON_NAME_EMPTY')
    roster = budget.ptr(module['game_base'] + ROSTER_GLOBAL, image=True)
    user = budget.ptr(module['game_base'] + USER_GLOBAL, image=True)
    if not layout.pointer(roster) or not layout.pointer(user): raise ValueError('RECON_NAME_ROSTER_POINTER')
    local_peer = budget.read(user + LOCAL_PEER, 8)
    if local_peer == bytes(8): raise ValueError('RECON_NAME_LOCAL_PEER')
    roster_raw = [budget.read(roster + i * ROSTER_STRIDE, 72) for i in range(4)]
    names = []
    for i, entry in enumerate(roster_raw):
        peer = entry[:8]
        if peer == bytes(8): continue
        try: display_name = string(entry[8:])
        except (ValueError, UnicodeDecodeError): display_name = None
        names.append({'slot': i, 'peer': peer[::-1].hex().upper(), 'name': display_name,
                      'local': peer == local_peer, 'exact_match': display_name == name})
    # Data and owner snapshots are compared, without claiming atomicity.
    if (budget.read(at + child.CHILD + 272, 345) != expected
        or budget.read(at + 0xE0, 52) != raw[0xE0:0xE0 + 52]
        or budget.read(at + child.CHILD + 0xF0, 16) != text[0xF0:0x100]
        or budget.read(name_pointer, STRING_BYTES) != name_raw
        or [budget.read(roster + i * ROSTER_STRIDE, 72) for i in range(4)] != roster_raw
        or budget.ptr(module['game_base'] + ROSTER_GLOBAL, image=True) != roster
        or budget.ptr(module['game_base'] + USER_GLOBAL, image=True) != user
        or budget.read(user + LOCAL_PEER, 8) != local_peer
        or budget.ptr(module['game_base'] + profile['hud'], image=True) != hud
        or reader.identity(budget.read(chat, 256)) != root_id
        or budget.ptr(module['game_base'] + layout.STATE_GLOBAL, image=True) != state
        or budget.u32(state + layout.STATE_OFFSET) != mode):
        raise ValueError('RECON_NAME_IDENTITY_CHANGED')
    matches = [r for r in names if r['exact_match']]
    return {'status': 'complete', 'mode': mode, 'source_sha256': SOURCE_SHA, 'source_game_pid': captured['game_pid'],
            'name': name, 'name_pointer': name_pointer, 'players': names,
            'unique_peer_match': matches[0]['peer'] if len(matches) == 1 else None,
            'unique_local_match': len(matches) == 1 and matches[0]['local'],
            'read_bytes': budget.bytes, 'read_calls': budget.reads, 'read_records': budget.total['records'],
            'elapsed_ms': (clock() - budget.started) * 1000, 'discovery_events_emitted': 0,
            'type10_followed': False, 'native_called': False, 'native_written': False, 'atomic': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from fire_code_windows import Process, resolve_game
    from probe_session import game_processes
    import fire_code_capture as guard
    captured, _ = source(); child.source(); stamps = guard.fingerprints()
    if args.pid != captured['game_pid'] or tuple(game_processes()) != (args.pid,):
        raise ValueError('RECON_NAME_PID_CHANGED')
    module = resolve_game(args.pid); guard.validate_identity(module, stamps)
    args.output.mkdir(exist_ok=False)
    with Process(args.pid) as process: result = snapshot(process, module)
    final = resolve_game(args.pid); guard.validate_identity(final, stamps)
    if final != module: raise ValueError('RECON_NAME_MODULE_CHANGED')
    result.update(game_pid=args.pid, module=module)
    (args.output / 'name.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf8')
    print(json.dumps({key: result[key] for key in ('status', 'name', 'unique_local_match', 'unique_peer_match', 'read_bytes', 'read_calls', 'elapsed_ms')}, ensure_ascii=False))


if __name__ == '__main__': main()
