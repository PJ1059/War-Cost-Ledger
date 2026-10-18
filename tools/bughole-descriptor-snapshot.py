"""One read-only fixed Destructible API snapshot after an already sealed hole.

No polling, heap search, Game call, account update or process write. Reads only
the upstream manager's bounded descriptor/index arrays, descriptor24, and the
12-byte records of known holes / the eight already saved diagnostic indices.
Includes the native dynamic record range below 0x17C00, proven by both local
and network enqueue caller bounds; 0x17000 is only the static-stage split.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('_hole_snapshot_budget', ROOT/'tools/career-ui-snapshot.py')
layout = importlib.util.module_from_spec(spec); spec.loader.exec_module(layout)
layout.TOTAL_BYTES = layout.SLICE_BYTES = 65536
layout.TOTAL_READS = layout.SLICE_READS = 1280
MANAGER, WORLD, RECORDS = 0x3326550, 0x346D528, 0xC5F78
MAX_RECORDS = 0x17C00
PINS = ((0x526646,'488b1d03ffdf02'),(0x526691,'ff430c'),
        (0x5266F0,'4f8994c130400000'),(0x88330B,'418984b630600000'),
        (0x8835CB,'8b500c'),(0x88384C,'8b5008'),(0x13E1B64,'4c8b1dbdb90802'),
        (0x13E1512,'4181f8007c0100'),(0xBBA67E,'4181f8007c0100'))
REVISION = 'bughole_known_descriptor_snapshot_v2_dynamic_record_bound'


def sources():
    text = (ROOT/'src/demolition-world.lua').read_text('utf8')
    holes = dict(re.findall(r"\['([0-9A-F]{16})'\]='([^']+)'", text))
    if len(holes) != 15: raise ValueError('HOLE_KIND_SOURCE_CHANGED')
    account = Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'bughole-live-0.4.31/account-after-own-hole.json'
    raw = account.read_bytes(); diagnostic = json.loads(raw)['native_demolition_diagnostic']
    prior = diagnostic['unknown_records']
    if len(prior) != 8 or any(not 0 <= r['record_index'] < MAX_RECORDS for r in prior):
        raise ValueError('HOLE_PRIOR_SAMPLE_CHANGED')
    return holes, prior, hashlib.sha256(raw).hexdigest()


def bulk(budget, address, size):
    return b''.join(budget.read(address+at,min(4096,size-at)) for at in range(0,size,4096))


def state_record(raw):
    return {'unit':struct.unpack_from('<I',raw)[0],
            'definition':struct.unpack_from('<H',raw,4)[0],
            'stage':raw[7],'flags':raw[8],'registered':bool(raw[8]&1),'raw_hex':raw.hex()}


def snapshot(process, module, clock=time.perf_counter):
    holes, prior, prior_sha = sources()
    budget = layout.Budget(process,module,clock,seconds=3)
    base=module['game_base']
    for rva,pin in PINS:
        if budget.read(base+rva,len(bytes.fromhex(pin)),image=True,code=True)!=bytes.fromhex(pin):
            raise ValueError('HOLE_DESCRIPTOR_PIN_CHANGED')
    state=budget.ptr(base+layout.STATE_GLOBAL,image=True)
    if not layout.pointer(state): raise ValueError('HOLE_STATE_POINTER')
    mode=budget.u32(state+layout.STATE_OFFSET)
    if mode not in (3,4): raise ValueError('HOLE_EXPECTS_SHIP_OR_MISSION')
    manager=budget.ptr(base+MANAGER,image=True); world=budget.ptr(base+WORLD,image=True)
    if not layout.pointer(manager) or not layout.pointer(world): raise ValueError('HOLE_GLOBAL_POINTER')
    if mode==3 and any(item['world']!=world for item in prior):
        return {'status':'previous_mission_world_unavailable','mode':mode,'world':world,
                'count':None,'holes':None,'read_bytes':budget.bytes,'read_calls':budget.reads,
                'read_records':budget.total['records'],'elapsed_ms':(clock()-budget.started)*1000,
                'native_called':False,'native_written':False,'ribbons_emitted':0}
    count=budget.u32(manager+12)
    if not 0<=count<=1024: raise ValueError('HOLE_DESCRIPTOR_COUNT')
    pointers=bulk(budget,manager+0x4030,count*8)
    indices=bulk(budget,manager+0x6030,count*4)
    rows=[]; selected=[]
    prior_indices={r['record_index'] for r in prior}
    for i in range(count):
        address=struct.unpack_from('<Q',pointers,i*8)[0]
        index=struct.unpack_from('<I',indices,i*4)[0]
        row={'slot':i,'address':address,'record_index':index}
        if not layout.pointer(address) or not 0<=index<MAX_RECORDS:
            row['reason']='outside_proven_descriptor_or_record_index'
            rows.append(row); continue
        raw=budget.read(address,24)
        resource,entity,unit=struct.unpack_from('<QII',raw)
        resource=f'{resource:016X}'
        row.update(resource=resource,entity=entity,unit=unit,
                   kind=holes.get(resource),descriptor_hex=raw.hex(),
                   prior_sample=index in prior_indices)
        if row['kind'] and len(selected)<64 or row['prior_sample']:
            at=world+RECORDS+12*index
            record=budget.read(at,12)
            row.update(record=state_record(record),record_matches_unit=struct.unpack_from('<I',record)[0]==unit)
            selected.append((row,raw,record))
        rows.append(row)
    for row,raw,record in selected:
        after=budget.read(world+RECORDS+12*row['record_index'],12)
        after_descriptor=budget.read(row['address'],24)
        row.update(record_after=state_record(after),record_stable=record==after,
                   descriptor_stable=raw==after_descriptor)
    # Eight fixed already captured records are also useful when they are scenery
    # and consequently absent from the Destructible entity manager.
    previous=[]
    for item in prior:
        if item['world']!=world:
            previous.append({'record_index':item['record_index'],'same_world':False})
            continue
        raw=budget.read(world+RECORDS+12*item['record_index'],12)
        previous.append({'record_index':item['record_index'],'prior_unit':item['unit'],
                         'same_world':item['world']==world,'record':state_record(raw),
                         'in_descriptor_manager':any(r['record_index']==item['record_index'] for r in rows)})
    if (bulk(budget,manager+0x4030,count*8)!=pointers
        or bulk(budget,manager+0x6030,count*4)!=indices
        or budget.u32(manager+12)!=count
        or budget.ptr(base+MANAGER,image=True)!=manager
        or budget.ptr(base+WORLD,image=True)!=world
        or budget.ptr(base+layout.STATE_GLOBAL,image=True)!=state
        or budget.u32(state+layout.STATE_OFFSET)!=mode):
        raise ValueError('HOLE_DESCRIPTOR_IDENTITY_CHANGED')
    return {'status':'complete','source_revision':REVISION,'manager':manager,'world':world,'mode':mode,
            'count':count,'holes':sum(bool(r.get('kind')) for r in rows),'rows':rows,
            'previous_samples':previous,'prior_sample_sha256':prior_sha,
            'read_bytes':budget.bytes,'read_calls':budget.reads,'read_records':budget.total['records'],
            'elapsed_ms':(clock()-budget.started)*1000,'native_called':False,'native_written':False,
            'atomic':False,'ribbons_emitted':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid',required=True,type=int);p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    from fire_code_windows import Process,resolve_game
    from probe_session import game_processes
    import fire_code_capture as guard
    sources(); stamps=guard.fingerprints()
    if tuple(game_processes())!=(args.pid,): raise ValueError('HOLE_PID_CHANGED')
    module=resolve_game(args.pid);guard.validate_identity(module,stamps)
    args.output.mkdir(exist_ok=False)
    with Process(args.pid) as process: result=snapshot(process,module)
    final=resolve_game(args.pid);guard.validate_identity(final,stamps)
    if final!=module:raise ValueError('HOLE_MODULE_CHANGED')
    result.update(game_pid=args.pid,module=module)
    (args.output/'descriptors.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({k:result[k] for k in ('status','count','holes','world','read_bytes','read_calls','elapsed_ms')}))


if __name__=='__main__':main()
