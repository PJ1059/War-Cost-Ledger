"""One read-only snapshot of the 64 proven inline native chat text rows.

Reads headers and native typed label descriptors only. No string/value pointers
are followed and no discovery/attribution semantics are presumed or emitted.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
PROFILE=Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'mod-research/task-layout/overwatch-hud/Source/inventory-profile.json'
PROFILE_SHA='5cb83ad5735a204e673db686f577f200d91408695f98db2c7d8042837a28cd67'
SOURCE=Path(os.environ.get('HD2_RESEARCH_FIXTURES_ROOT', str(ROOT/'dist')))/'recon-chat-hud-handler-live-20261013-v2/handler.bin'
SOURCE_SHA='ad82ac5125eac0b4d1acc2424abf91b7a7dfb901d4c67f114c830ce3b8ac17b2'
ROW_BASE,ROW_STRIDE,ROW_COUNT=0x4390,0x3D8,64
DISCOVERY_KEYS=(0x92871A58,0xCD539459)
spec=importlib.util.spec_from_file_location('_recon_chat_row_budget',ROOT/'tools/career-ui-snapshot.py')
layout=importlib.util.module_from_spec(spec);spec.loader.exec_module(layout)
layout.TOTAL_BYTES=layout.SLICE_BYTES=65536
layout.TOTAL_READS=layout.SLICE_READS=256
REVISION='recon_chat_fixed_row_descriptors_v1'


def sources():
    raw=PROFILE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROFILE_SHA:raise ValueError('RECON_CHAT_LOCATOR_SOURCE_CHANGED')
    p=json.loads(raw)['chat']
    if p['hud']!=0x346D538 or p['widget']!=0x14498:raise ValueError('RECON_CHAT_LOCATOR_OFFSETS_CHANGED')
    body=SOURCE.read_bytes();meta=json.loads(SOURCE.with_suffix('.json').read_text('utf8'))
    if hashlib.sha256(body).hexdigest()!=SOURCE_SHA:raise ValueError('RECON_CHAT_ROW_SOURCE_CHANGED')
    pins=[]
    # Actual loop: base=chat+4758, each widget=base-3C8, stride3D8, 64 rows.
    for rva,pin in ((0x186042D,'488db75847000041be40000000'),
                    (0x1860455,'488d8e38fcffff'),(0x18604C3,'4881c6d8030000')):
        r=next(r for r in meta['ranges'] if r['rva']<=rva<r['rva']+r['length'])
        at=r['binary_offset']+rva-r['rva']
        if body[at:at+len(bytes.fromhex(pin))].hex()!=pin:raise ValueError('RECON_CHAT_ROW_LAYOUT_SOURCE_CHANGED')
        pins.append((rva,pin))
    return p,tuple(pins)


def identity(raw):
    return {'kind':struct.unpack_from('<I',raw)[0]>>18&15,
            'parent':struct.unpack_from('<Q',raw,0xF0)[0],
            'context':struct.unpack_from('<Q',raw,0xF8)[0]}


def descriptor(raw):
    key=struct.unpack_from('<I',raw)[0];count=raw[344]
    out={'key':key,'key_hex':f'{key:08X}','argument_count':count,
         'layout_valid':count<=14,'discovery_template_match':key in DISCOVERY_KEYS}
    out['arguments']=[]
    if count<=14:
        for i in range(count):
            at=8+24*i;arg_key,kind,value=struct.unpack_from('<IIQ',raw,at)
            out['arguments'].append({'key':arg_key,'key_hex':f'{arg_key:08X}',
                 'type':kind,'value_raw':value,'value_hex':f'{value:016X}',
                 'tail_hex':raw[at+16:at+24].hex(),'value_interpreted':False})
    return out


def snapshot(process,module,clock=time.perf_counter):
    profile,pins=sources();budget=layout.Budget(process,module,clock,seconds=.5)
    # Generic Text descriptor is already code-proven by Career; the chat-specific
    # row identity is independently recorded before and after each descriptor.
    for rva,pin in tuple((p['rva'],p['hex']) for p in profile['pins'][:2])+pins+layout.PINS:
        if budget.read(module['game_base']+rva,len(bytes.fromhex(pin)),image=True,code=True)!=bytes.fromhex(pin):
            raise ValueError('RECON_CHAT_DESCRIPTOR_CODE_PIN_CHANGED')
    state=budget.ptr(module['game_base']+layout.STATE_GLOBAL,image=True)
    if not layout.pointer(state):raise ValueError('RECON_CHAT_STATE_POINTER')
    mode=budget.u32(state+layout.STATE_OFFSET)
    if mode not in (3,4):raise ValueError('RECON_CHAT_EXPECTS_SHIP_OR_MISSION')
    hud=budget.ptr(module['game_base']+profile['hud'],image=True)
    if not layout.pointer(hud):raise ValueError('RECON_CHAT_HUD_POINTER')
    chat=hud+profile['widget'];root=budget.read(chat,256);root_id=identity(root)
    if root_id['kind']!=1 or not layout.pointer(root_id['parent']) or not layout.pointer(root_id['context']):
        raise ValueError('RECON_CHAT_ROOT_IDENTITY')
    rows=[]
    for i in range(ROW_COUNT):
        at=chat+ROW_BASE+i*ROW_STRIDE;raw=budget.read(at,256);who=identity(raw)
        row={'index':i,'address':at,'identity':who,'header_hex':raw.hex()}
        if who['kind']==7 and who['context']==root_id['context'] and layout.pointer(who['parent']):
            label=budget.read(at+272,345)
            after=budget.read(at,256)
            if identity(after)!=who:raise ValueError('RECON_CHAT_ROW_IDENTITY_CHANGED')
            row.update(descriptor=descriptor(label),descriptor_hex=label.hex(),identity_stable=True)
        else:
            row['reason']='not_proven_text_in_same_gui_context'
        rows.append(row)
    if (budget.ptr(module['game_base']+profile['hud'],image=True)!=hud
        or identity(budget.read(chat,256))!=root_id
        or budget.ptr(module['game_base']+layout.STATE_GLOBAL,image=True)!=state
        or budget.u32(state+layout.STATE_OFFSET)!=mode):raise ValueError('RECON_CHAT_CONTEXT_CHANGED')
    return {'status':'complete','source_revision':REVISION,'mode':mode,'hud':hud,'chat':chat,
            'chat_identity':root_id,'rows':rows,'read_records':budget.total['records'],
            'read_calls':budget.reads,'read_bytes':budget.bytes,
            'elapsed_ms':(clock()-budget.started)*1000,'discovery_keys':list(DISCOVERY_KEYS),
            'source_sha256':SOURCE_SHA,'locator_sha256':PROFILE_SHA,
            'discovery_events_emitted':0,'string_pointers_followed':0,
            'native_called':False,'native_written':False,'atomic':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from fire_code_windows import Process,resolve_game
    from probe_session import game_processes
    import fire_code_capture as guard
    sources();stamps=guard.fingerprints()
    if tuple(game_processes())!=(args.pid,):raise ValueError('RECON_CHAT_PID_CHANGED')
    module=resolve_game(args.pid);guard.validate_identity(module,stamps)
    args.output.mkdir(exist_ok=False)
    with Process(args.pid) as process:result=snapshot(process,module)
    final=resolve_game(args.pid);guard.validate_identity(final,stamps)
    if final!=module:raise ValueError('RECON_CHAT_MODULE_CHANGED')
    result.update(game_pid=args.pid,module=module)
    (args.output/'rows.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({'status':result['status'],'mode':result['mode'],'read_bytes':result['read_bytes'],
                      'read_calls':result['read_calls'],'elapsed_ms':result['elapsed_ms'],
                      'text_rows':sum('descriptor' in r for r in result['rows']),
                      'discovery_rows':[r['index'] for r in result['rows'] if r.get('descriptor',{}).get('discovery_template_match')]}))


if __name__=='__main__':main()
