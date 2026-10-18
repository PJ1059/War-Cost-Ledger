"""Single bounded read of native local grenade stock and inventory identities.

Diagnostic only: no polling, game writes/calls, account changes or billing. The
five inventory fields are reported as candidates, not presumed grenade slots.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'dist/mod-research/task-layout/overwatch-hud/Source/inventory-profile.json'
PROFILE_SHA = '5cb83ad5735a204e673db686f577f200d91408695f98db2c7d8042837a28cd67'
spec = importlib.util.spec_from_file_location('_grenade_snapshot_layout', ROOT / 'tools/career-ui-snapshot.py')
layout = importlib.util.module_from_spec(spec); spec.loader.exec_module(layout)
layout.TOTAL_BYTES = layout.SLICE_BYTES = 16384
layout.TOTAL_READS = layout.SLICE_READS = 192
REVISION = 'local_grenade_hud_inventory_v1'
GAS_RESOURCE = '0416984F4922757B'
HUD_GLOBAL, HUD_BUILT, SELF_PANEL = 0x346D538, 0x24E334, 0x24E3A0
PLAYER_GLOBAL, USER_GLOBAL, USER_PEER = 0x3326468, 0x347CEF0, 0xB398
ENTITY_GLOBAL, NET_MAP, ENTITY_BASE = 0x346BF98, 0xF22EC8, 0xF32F20
ENTITY_MAP, DESCRIPTOR_BASE = 0xF1AEB0, 0xF32F18
INVENTORY_GLOBAL, INVENTORY_MAP, INVENTORY_RECORDS = 0x3326738, 40, 80


def sources():
    raw = PROFILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROFILE_SHA:
        raise ValueError('GRENADE_PROFILE_CHANGED')
    result = json.loads(raw)
    if result['inventory']['grenade_widget'] != 0x20B8 or result['throwable_ui']['texture_cache'] != 0x56B8:
        raise ValueError('GRENADE_PROFILE_OFFSETS')
    return result


def u32(raw, at=0): return struct.unpack_from('<I', raw, at)[0]
def u64(raw, at=0): return struct.unpack_from('<Q', raw, at)[0]


def lookup(budget, address, key, max_index):
    header = budget.read(address, 20)
    buckets, cap, empty, factor = struct.unpack('<QIII', header)
    if not layout.pointer(buckets) or cap < 1 or cap > 1048576 or cap & (cap-1):
        raise ValueError('GRENADE_HASH_HEADER')
    start = (key * factor) & 0xFFFFFFFF
    for probe in range(min(cap, 32)):
        at = buckets + (start+probe) % cap * 8
        row = budget.read(at, 8); found, index = struct.unpack('<II', row)
        if found in (key, empty):
            if budget.read(address, 20) != header or budget.read(at, 8) != row:
                raise ValueError('GRENADE_HASH_CHANGED')
            if found == empty or index == 0xFFFFFFFF: return None
            if index >= max_index: raise ValueError('GRENADE_HASH_INDEX')
            return index
    raise ValueError('GRENADE_HASH_PROBE_LIMIT')


def local_player(budget):
    base = budget.identity['game_base']
    user = budget.ptr(base+USER_GLOBAL, image=True)
    if not layout.pointer(user): raise ValueError('GRENADE_LOCAL_USER')
    peer = budget.ptr(user+USER_PEER)
    manager = budget.ptr(base+PLAYER_GLOBAL, image=True)
    if not peer or not layout.pointer(manager): raise ValueError('GRENADE_PLAYER_MANAGER')
    count = budget.u32(manager+132)
    if not 1 <= count <= 4: raise ValueError('GRENADE_PLAYER_COUNT')
    matches = []
    for slot in range(count):
        raw = budget.read(manager+712+slot*56, 56)
        if u64(raw) == peer: matches.append((slot, u32(raw, 24)))
    if len(matches) != 1: raise ValueError('GRENADE_LOCAL_PLAYER_AMBIGUOUS')
    slot, life = matches[0]
    if life != 3: raise ValueError('GRENADE_LOCAL_PLAYER_NOT_SPAWNED')
    network = budget.u32(manager+936+slot*32)
    if network == 32767: raise ValueError('GRENADE_LOCAL_AVATAR_MISSING')
    entities = budget.ptr(base+ENTITY_GLOBAL, image=True)
    if not layout.pointer(entities): raise ValueError('GRENADE_ENTITIES')
    index = lookup(budget, entities+NET_MAP, network, 1048576)
    if index is None: raise ValueError('GRENADE_AVATAR_NETWORK_UNMAPPED')
    avatar = budget.u32(entities+ENTITY_BASE+24*index)
    if avatar == 0: raise ValueError('GRENADE_AVATAR_ZERO')
    return {'peer': f'{peer:016X}', 'slot': slot, 'lifecycle': life, 'avatar': avatar,
            'network': network, 'user': user, 'manager': manager, 'entities': entities}


def identity(raw):
    return {'kind': u32(raw) >> 18 & 15, 'parent': u64(raw, 0xF0), 'context': u64(raw, 0xF8)}


def pair(raw, profile):
    count = raw[profile['count']]
    if count > 14: raise ValueError('GRENADE_SHADER_COUNT')
    found = {}
    for i in range(count):
        key, kind, value = struct.unpack_from('<III', raw, profile['first']+i*profile['stride'])
        if key in (profile['current_key'], profile['maximum_key']):
            if kind % 4096 != 4 or key in found: raise ValueError('GRENADE_SHADER_TYPE')
            found[key] = value
    current, maximum = found.get(profile['current_key']), found.get(profile['maximum_key'])
    if current is None or maximum is None or not 0 <= current <= maximum <= 10000 or maximum == 0:
        raise ValueError('GRENADE_SHADER_VALUES')
    return {'current': current, 'maximum': maximum}


def snapshot(process, module, clock=time.perf_counter):
    profile = sources(); p, t = profile['inventory'], profile['throwable_ui']
    budget = layout.Budget(process, module, clock, seconds=.5); game = module['game_base']
    state = budget.ptr(game+layout.STATE_GLOBAL, image=True)
    if not layout.pointer(state) or budget.u32(state+layout.STATE_OFFSET) != 4:
        raise ValueError('GRENADE_EXPECTS_MISSION')
    for pin in p['pins']+t['pins']:
        raw = bytes.fromhex(pin['hex'])
        if budget.read(game+pin['rva'], len(raw), image=True, code=True) != raw:
            raise ValueError('GRENADE_CODE_PIN_CHANGED')
    player = local_player(budget)
    hud = budget.ptr(game+HUD_GLOBAL, image=True)
    if not layout.pointer(hud):
        raise ValueError('GRENADE_HUD_NOT_BUILT')
    built = budget.read(hud+HUD_BUILT, 1)
    if built == b'\0':
        raise ValueError('GRENADE_HUD_NOT_BUILT')
    panel = hud+SELF_PANEL
    offsets = (0, t['outer'], t['parent'], t['picture'], p['grenade_widget'])
    headers = {offset: budget.read(panel+offset, 0x100) for offset in offsets}
    identities = {offset: identity(raw) for offset, raw in headers.items()}
    context = identities[0]['context']
    if not layout.pointer(context): raise ValueError('GRENADE_HUD_CONTEXT')
    for offset, parent, kind in ((t['outer'],panel,1),(t['parent'],panel+t['outer'],1),(t['picture'],panel+t['parent'],3)):
        who = identities[offset]
        if who != {'kind':kind,'parent':parent,'context':context}:
            raise ValueError('GRENADE_HUD_OWNERSHIP')
    widget = panel+p['grenade_widget']
    if identities[p['grenade_widget']]['context'] != context:
        raise ValueError('GRENADE_STOCK_CONTEXT')
    dictionary = budget.read(widget+p['dictionary'], p['count']+1)
    stock = pair(dictionary, p)
    texture = budget.read(panel+t['texture_cache'], 8)
    if texture == b'\0'*8 or budget.read(panel+t['picture']+0x150, 8) != texture:
        raise ValueError('GRENADE_TEXTURE_CACHE')
    # Five existing native inventory fields, with no assumed slot semantics.
    inventory = budget.ptr(game+INVENTORY_GLOBAL, image=True)
    if not layout.pointer(inventory): raise ValueError('GRENADE_INVENTORY_MANAGER')
    index = lookup(budget, inventory+INVENTORY_MAP, player['avatar'], 65536)
    if index is None: raise ValueError('GRENADE_INVENTORY_AVATAR')
    records = budget.ptr(inventory+INVENTORY_RECORDS)
    if not layout.pointer(records): raise ValueError('GRENADE_INVENTORY_RECORDS')
    record_at = records+48*index; record = budget.read(record_at, 48)
    candidates = []
    for offset in range(0,20,4):
        entity = u32(record,offset)
        item = {'offset':offset,'entity':entity,'slot_semantics_proven':False}
        if entity not in (0,0xFFFFFFFF,player['avatar']):
            ix = lookup(budget, player['entities']+ENTITY_MAP, entity, 1048576)
            if ix is not None:
                address = player['entities']+DESCRIPTOR_BASE+24*ix
                descriptor = budget.read(address,24)
                if u32(descriptor,8) != entity or budget.read(address,24) != descriptor:
                    raise ValueError('GRENADE_ENTITY_IDENTITY_CHANGED')
                item.update(resource=f'{u64(descriptor):016X}',descriptor_hex=descriptor.hex())
        candidates.append(item)
    for offset, raw in headers.items():
        if identity(budget.read(panel+offset,256)) != identity(raw):
            raise ValueError('GRENADE_HUD_REBUILT')
    if (budget.read(widget+p['dictionary'],p['count']+1) != dictionary
        or budget.read(panel+t['texture_cache'],8) != texture
        or budget.read(panel+t['picture']+0x150,8) != texture
        or budget.read(record_at,48) != record
        or budget.ptr(game+INVENTORY_GLOBAL,image=True) != inventory
        or budget.ptr(inventory+INVENTORY_RECORDS) != records
        or budget.ptr(game+HUD_GLOBAL,image=True) != hud
        or budget.read(hud+HUD_BUILT,1) != built
        or budget.ptr(game+layout.STATE_GLOBAL,image=True) != state
        or budget.u32(state+layout.STATE_OFFSET) != 4
        or local_player(budget) != player):
        raise ValueError('GRENADE_SNAPSHOT_CHANGED')
    return {'source_revision':REVISION,'stock':stock,'texture':f'{u64(texture):016X}',
        'player':player,'inventory_candidates':candidates,
        'gas_resource_present':any(x.get('resource')==GAS_RESOURCE for x in candidates),
        'inventory_record_hex':record.hex(),'dictionary_hex':dictionary.hex(),
        'headers':{str(k):v.hex() for k,v in headers.items()},
        'active_read_bytes':budget.bytes,'active_read_calls':budget.reads,'queries':budget.queries,
        'read_records':budget.total['records'],'captured_at':datetime.now(timezone.utc).isoformat(),
        'atomic':False,'diagnostic_only':True,'throwable_type_binding_proven':False,
        'native_written':False,'native_called':False,'account_modified':False}


def run(folder, expected_pid, deps=None):
    folder=Path(folder).resolve()
    if folder.exists():raise ValueError('GRENADE_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    deps=layout.dependencies() if deps is None else deps
    pids=tuple(deps['game_processes']())
    if pids != (expected_pid,):raise ValueError('GRENADE_PID_MISMATCH')
    stamps=deps['fingerprints']();module=deps['resolve_game'](expected_pid)
    deps['validate_identity'](module,stamps)
    with deps['Process'](expected_pid) as process:result=snapshot(process,module)
    final=deps['resolve_game'](expected_pid);deps['validate_identity'](final,stamps)
    if final != module or tuple(deps['game_processes']()) != pids:raise ValueError('GRENADE_MODULE_CHANGED')
    result.update(status='complete',game_pid=expected_pid,identity=module)
    (folder/'grenade-hud.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',required=True,type=int);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    result=run(args.output,args.pid)
    print(json.dumps({k:result[k] for k in ('status','stock','texture','gas_resource_present','active_read_bytes','active_read_calls')}))
