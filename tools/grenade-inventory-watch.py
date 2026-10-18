"""Bounded external read-only sample of the local native throwable resource/count.

No hooks, native calls, game writes, input injection or account changes. Run only
when requested for a user-operated throw; output is private diagnostic evidence.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('_grenade_watch_base',ROOT/'tools/grenade-hud-snapshot.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
DOMAIN=Path('external/HD2Runtime/domains/player_equipment.lua')
DOMAIN_SHA='413f61776e94aea78917a20ebe76d7558090346b3af60a9b6329be109c2079ad'
PROOFS=(79,80,81,82,83,84,85,86,87,95,96,97,98,99,100,101,102,103,104)


def pins():
    raw=DOMAIN.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DOMAIN_SHA:raise ValueError('GRENADE_DOMAIN_CHANGED')
    found=re.findall(r'\["rva"\]=(\d+),\["hex"\]="([0-9A-Fa-f]+)"',raw.decode('utf8'))
    return [(int(found[n-1][0]),bytes.fromhex(found[n-1][1])) for n in PROOFS]


def snapshot(process,module,clock=time.perf_counter):
    b=base.layout.Budget(process,module,clock,seconds=.5);game=module['game_base']
    state=b.ptr(game+base.layout.STATE_GLOBAL,image=True)
    if not base.layout.pointer(state) or b.u32(state+base.layout.STATE_OFFSET)!=4:
        raise ValueError('GRENADE_EXPECTS_MISSION')
    for at,raw in pins():
        if b.read(game+at,len(raw),image=True,code=True)!=raw:raise ValueError('GRENADE_CODE_PIN_CHANGED')
    player=base.local_player(b)
    manager=b.ptr(game+base.INVENTORY_GLOBAL,image=True)
    index=base.lookup(b,manager+40,player['avatar'],65536)
    if index is None:raise ValueError('GRENADE_AVATAR_UNMAPPED')
    descriptors=b.ptr(manager+64);descriptor=b.ptr(descriptors+index*8)
    who=b.read(descriptor,24)
    if base.u32(who,8)!=player['avatar'] or base.u32(who,20)%2!=1:
        raise ValueError('GRENADE_AVATAR_OWNERSHIP')
    records,counts=b.ptr(manager+80),b.ptr(manager+88)
    resource_at,count_at=records+48*index+40,counts+8*index
    resource,count=b.read(resource_at,8),b.read(count_at,4)
    if not 0<=base.u32(count)<=10000 or base.u64(resource)==0:raise ValueError('GRENADE_INVALID_STOCK')
    if (b.read(resource_at,8)!=resource or b.read(count_at,4)!=count or b.read(descriptor,24)!=who
        or b.ptr(manager+80)!=records or b.ptr(manager+88)!=counts
        or b.ptr(manager+64)!=descriptors or b.ptr(descriptors+index*8)!=descriptor
        or b.ptr(game+base.INVENTORY_GLOBAL,image=True)!=manager
        or base.local_player(b)!=player or b.u32(state+base.layout.STATE_OFFSET)!=4):
        raise ValueError('GRENADE_INVENTORY_CHANGED')
    return {'resource':f'{base.u64(resource):016X}','count':base.u32(count),
        'player':player,'reads':b.reads,'bytes':b.bytes,
        'captured_at':datetime.now(timezone.utc).isoformat(),'native_written':False}


def run(output,pid,seconds):
    output=Path(output).resolve()
    if output.exists():raise ValueError('GRENADE_OUTPUT_EXISTS')
    if not 0<=seconds<=60:raise ValueError('GRENADE_DURATION_LIMIT')
    deps=base.layout.dependencies();pids=tuple(deps['game_processes']())
    if pids!=(pid,):raise ValueError('GRENADE_PID_MISMATCH')
    stamps=deps['fingerprints']();module=deps['resolve_game'](pid);deps['validate_identity'](module,stamps)
    output.mkdir(parents=True)
    rows=[];started=time.perf_counter();first=True
    with deps['Process'](pid) as process:
        while first or time.perf_counter()-started<seconds:
            first=False
            try:
                value=snapshot(process,module);rows.append(value)
                if len(rows)==1:print(json.dumps({'ready':True,'resource':value['resource'],'count':value['count']}) ,flush=True)
            except Exception as exc:rows.append({'captured_at':datetime.now(timezone.utc).isoformat(),'error':str(exc)})
            if seconds==0:break
            time.sleep(.2)
    final=deps['resolve_game'](pid);deps['validate_identity'](final,stamps)
    if final!=module or tuple(deps['game_processes']())!=pids:raise ValueError('GRENADE_MODULE_CHANGED')
    result={'revision':'native_throwable_inventory_v1','game_pid':pid,'identity':module,
            'samples':rows,'diagnostic_only':True,'native_written':False,'account_modified':False}
    (output/'grenade-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    distinct=[]
    for row in rows:
        key=(row.get('resource'),row.get('count'),row.get('error'))
        if not distinct or distinct[-1]!=key:distinct.append(key)
    print(json.dumps({'samples':len(rows),'transitions':distinct},ensure_ascii=False),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',required=True,type=int);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--seconds',type=float,default=0)
    args=parser.parse_args();run(args.output,args.pid,args.seconds)
