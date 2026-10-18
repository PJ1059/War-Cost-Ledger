"""Fixed ProduceDamage RF ownership metadata, read-only and one attempt.

Only .pdata[63772..63786]180B and those records' standard UNWIND_INFO
headers/codes/CHAIN triples/handler RVA. No language data, code body, handler,
heap or native call/write. At most4 nodes per ownership target; no off-window
ancestry. Private16KiB/128 total read+query/2s budget includes every post gate.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
REVISION='produce_damage_fixed_logical_metadata_v1'
PREVIOUS=ROOT/'tools/hit-copy-tail-scratch-capture.py'
PREVIOUS_SHA='56fb1c6c958732253ff22dd2f85026c5c424cc9fa9c05a0f85f5aedbeffb3d41'
SOURCE=ROOT/'dist/hit-produce-damage-body-20261012/capture/drain.json'
SOURCE_SHA='5c47574cc0f5bed5c3144e844c5c9274bdab1f0882a6726e052b9a4972122186'
SOURCE_BIN=SOURCE.with_name('drain.bin')
SOURCE_BIN_SHA='df173f605c5c12557a7a263cf3b7edd36fda416cbd51e6763fcf4df15b33abae'
PIN_RVA,PIN=0x13AD88B,bytes.fromhex('e8a004efff')
PRIMARY=(0x129DD30,0x129E669,0x24FC4B8)
PRIMARY_HEADER=bytes.fromhex('19340f00')
EXCEPTION_RVA,EXCEPTION_SIZE=0x3FD340C,0x1BF57C
FIRST,LAST=63772,63786
TABLE_RVA,TABLE_BYTES=EXCEPTION_RVA+FIRST*12,180
ANCHORS={63772:bytes.fromhex('30dd290169e62901b8c44f02'),
         63776:bytes.fromhex('8ee72901f2ee29012cc54f02'),
         63785:bytes.fromhex('e7f329010ef42901d4c54f02')}
MAX_BYTES,MAX_IO=16*1024,128
SAVED_BRANCHES=[
    (0x129E14F,'0f8444080000',0x129E999),(0x129E1BA,'0f84d9070000',0x129E999),
    (0x129E1DD,'0f83dc0c0000',0x129EEBF),(0x129E306,'e98e060000',0x129E999),
    (0x129E393,'0f8400060000',0x129E999),(0x129E3BC,'0f84d7050000',0x129E999),
    (0x129E3E0,'0f84b0040000',0x129E896),(0x129E3E8,'0f84b0040000',0x129E89E),
    (0x129E3F5,'e99f050000',0x129E999),(0x129E423,'0f83960a0000',0x129EEBF),
    (0x129E61F,'0f84ad000000',0x129E6D2),(0x129E627,'0f84ad000000',0x129E6DA),
    (0x129E663,'0f8430030000',0x129E999)]


def source():
    if hashlib.sha256(PREVIOUS.read_bytes()).hexdigest()!=PREVIOUS_SHA:
        raise ValueError('PRODUCE_META_FIXED_READER_CHANGED')
    raw=SOURCE.read_bytes();body=SOURCE_BIN.read_bytes()
    if(hashlib.sha256(raw).hexdigest()!=SOURCE_SHA
            or hashlib.sha256(body).hexdigest()!=SOURCE_BIN_SHA
            or len(body)!=2366 or body[:5]!=PIN
            or PIN_RVA+5+struct.unpack_from('<i',PIN,1)[0]!=PRIMARY[0]):
        raise ValueError('PRODUCE_META_SAVED_SOURCE_CHANGED')
    meta=json.loads(raw)
    if(meta['target_rva']!=PRIMARY[0] or meta['function_begin']!=PRIMARY[0]
            or meta['function_end']!=PRIMARY[1]
            or meta['unwind_chain'][0]['header']['raw_hex']!=PRIMARY_HEADER.hex()):
        raise ValueError('PRODUCE_META_SAVED_PRIMARY_CHANGED')
    for index,pin in ANCHORS.items():
        rows=[r for r in meta['exception_records']if r['index']==index]
        if len(rows)!=1 or rows[0]['raw_hex']!=pin.hex():
            raise ValueError('PRODUCE_META_SAVED_ANCHOR_CHANGED')
    for site,hex_raw,target in SAVED_BRANCHES:
        code=bytes.fromhex(hex_raw);at=5+site-PRIMARY[0]
        if(body[at:at+len(code)]!=code
                or site+len(code)+struct.unpack_from('<i',code,len(code)-4)[0]!=target):
            raise ValueError('PRODUCE_META_SAVED_BRANCH_CHANGED')
    spec=importlib.util.spec_from_file_location('_produce_meta_private_reader',PREVIOUS)
    thin=importlib.util.module_from_spec(spec);spec.loader.exec_module(thin)
    thin.MAX_BYTES,thin.MAX_IO=MAX_BYTES,MAX_IO
    locator,reader,_=thin.source()
    return thin,locator,reader


def entry(raw):return struct.unpack('<III',raw)


def table_records(raw,game_size):
    if len(raw)!=TABLE_BYTES:raise ValueError('PRODUCE_META_TABLE_LENGTH')
    records=[];previous_end=0
    for at in range(0,TABLE_BYTES,12):
        index=FIRST+at//12;pin=raw[at:at+12]
        begin,end,uw=entry(pin)
        if(not 0x1000<=begin<end<=0x2110A93 or begin<previous_end
                or not 0<=uw<game_size-4 or uw%4):
            raise ValueError('PRODUCE_META_RF_RANGE_ORDER')
        if index in ANCHORS and pin!=ANCHORS[index]:
            raise ValueError('PRODUCE_META_FRESH_ANCHOR_CHANGED')
        records.append({'index':index,'begin':begin,'end':end,'unwind_rva':uw,
                        'raw_hex':pin.hex(),'rva':TABLE_RVA+at})
        previous_end=end
    return records


def reserve_after(budget,cache,extra_bytes=0,extra_io=0):
    # Fixed post: table180 + call5 + PE/export/getter4186 + Ship12 =4383B.
    # 2+2+6+4+1(creation) =15IO, plus each actually read UW's2IO refresh.
    budget.reserve(4383+sum(len(bytes.fromhex(n['raw_hex']))for n in cache.values())
                   +extra_bytes,15+2*len(cache)+extra_io)


def unwind_node(budget,uw,cache):
    if uw in cache:return cache[uw]
    if len(cache)>=15:raise ValueError('PRODUCE_META_UNIQUE_NODE_CAP')
    # Pre-reserve maximum new node128 + header4 plus its post reread.
    reserve_after(budget,cache,260,6)
    head=budget.read_module(uw,4,'produce_UW_header')
    flags=head[0]>>3
    size=4+4*((head[2]+1)//2)+(12 if flags&4 else 4 if flags&3 else 0)
    node={'unwind_rva':uw,'version':head[0]&7,'flags':flags,'prolog_size':head[1],
          'slot_count':head[2],'frame_register':head[3]&15,
          'frame_offset_bytes':(head[3]>>4)*16,'raw_hex':head.hex(),
          'standard_layout_complete':False,'handler_specific_data_read':False}
    cache[uw]=node
    if(head[0]&7!=1 or flags not in(0,1,2,3,4)or size>128
            or uw+size>budget.identity['game_size']):
        return node
    reserve_after(budget,cache,size*2,size==4 and 0 or 2)
    raw=head if size==4 else budget.read_module(uw,size,'produce_standard_UW_only')
    if raw[:4]!=head:raise ValueError('PRODUCE_META_UW_CHANGED_DURING_READ')
    node.update(raw_hex=raw.hex(),standard_length=size,standard_layout_complete=True,
                code_slots_hex=raw[4:4+4*((head[2]+1)//2)].hex())
    if flags&4:node['chain_entry']=list(entry(raw[-12:]))
    elif flags&3:node['handler_rva']=struct.unpack_from('<I',raw,size-4)[0]
    if uw==PRIMARY[2]and head!=PRIMARY_HEADER:
        raise ValueError('PRODUCE_META_PRIMARY_HEADER_CHANGED')
    return node


def ownership(initial,by_entry,budget,cache):
    current=initial;seen=set();chain=[]
    for _ in range(4):
        if current not in by_entry:return None,chain,'CHAIN_OUTSIDE_FIXED_RF_WINDOW'
        if current in seen:return None,chain,'CHAIN_CYCLE'
        seen.add(current);chain.append(list(current))
        node=unwind_node(budget,current[2],cache)
        if not node['standard_layout_complete']:return None,chain,'UNKNOWN_STANDARD_UW_LAYOUT'
        if not node['flags']&4:return current,chain,None
        current=tuple(node['chain_entry'])
    return None,chain,'CHAIN_NODE_CAP'


def run(output,dependencies=None,clock=time.perf_counter):
    folder=Path(output).resolve()
    if folder.exists():raise ValueError('PRODUCE_META_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    evidence={'source_revision':REVISION,'complete':False,'metadata_only':True,
        'source_sha256':SOURCE_SHA,'source_bin_sha256':SOURCE_BIN_SHA,
        'fixed_RF_indices':[FIRST,LAST],'fixed_RF_rva':TABLE_RVA,'fixed_RF_bytes':TABLE_BYTES,
        'target_primary':list(PRIMARY),'attempts':1,'body_read':False,'heap_reads':0,
        'handler_specific_data_read':False,'handler_body_read':False,
        'native_called':False,'native_written':False,'normal_CFG_complete':False,
        'classification_ready':False,'Game_logic_executed':False}
    budget=None
    try:
        thin,locator,reader=source()
        deps=dependencies if dependencies is not None else reader.profile.load_dependencies()
        stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(thin.EXPECTED_PID,):raise ValueError('PRODUCE_META_EXACT_PID_REQUIRED')
        identity=deps['resolve_game'](pids[0]);deps['validate_identity'](identity,stamps)
        reader.profile.validate_module(identity)
        evidence.update(game_pid=pids[0],identity=identity,fingerprint=reader.profile.FINGERPRINT)
        with deps['Process'](pids[0])as process:
            budget=thin.make_budget(reader)(process,identity,clock)
            creation=budget.creation(deps.get('start_time',thin.process_creation_time))
            before=deps['ship_state'](budget,identity)
            if before['state']!=3:raise ValueError('PRODUCE_META_SHIP_REQUIRED')
            snapshot=locator.snapshot(budget)
            if(snapshot[2].hex()!='85c90f85a2000000488d0581f6ffff48'
                    or struct.unpack_from('<II',snapshot[0],0x110+24+136)!=(EXCEPTION_RVA,EXCEPTION_SIZE)):
                raise ValueError('PRODUCE_META_LOADED_SOURCE_PROFILE')
            pin=budget.read_module(PIN_RVA,5,'produce_caller_PIN',True)
            if pin!=PIN:raise ValueError('PRODUCE_META_FRESH_CALL_PIN')
            table=budget.read_module(TABLE_RVA,TABLE_BYTES,'produce_fixed_RF_window')
            records=table_records(table,identity['game_size'])
            by_entry={(r['begin'],r['end'],r['unwind_rva']):r for r in records}
            if len(by_entry)!=15:raise ValueError('PRODUCE_META_DUPLICATE_RF')
            cache={};same=[];boundary=None;reason=None
            for record in records:
                selected=(record['begin'],record['end'],record['unwind_rva'])
                owner,chain,reason=ownership(selected,by_entry,budget,cache)
                record.update(owner=list(owner)if owner else None,ownership_chain=chain,
                              ownership_proven=reason is None)
                if reason:break
                if owner!=PRIMARY:
                    if boundary is None:boundary=record
                else:same.append(record['index'])
            if reason is None and records[-1]['owner']==list(PRIMARY):
                reason='FINAL_RECORD_STILL_SAME_OWNER_STOP'
            if reason is None and(not same or same[0]!=FIRST):reason='PRIMARY_OWNER_NOT_PROVEN'
            known_targets=sorted({target for _,_,target in SAVED_BRANCHES}|{PRIMARY[1]})
            uncovered=[target for target in known_targets
                if not any(r['index']in same and r['begin']<=target<r['end']for r in records)]
            if reason is None and uncovered:reason='SAVED_NORMAL_SUCCESSOR_OUTSIDE_OWNER_WINDOW'
            # A foreign RF can be interleaved before later same-owner cold fragments.
            # Resolve the whole fixed window; unknowns never extend it.
            reserve_after(budget,cache)
            for node in cache.values():
                raw=bytes.fromhex(node['raw_hex'])
                if budget.read_module(node['unwind_rva'],len(raw),'produce_UW_after')!=raw:
                    raise ValueError('PRODUCE_META_METADATA_CHANGED')
            if budget.read_module(TABLE_RVA,TABLE_BYTES,'produce_fixed_RF_after')!=table:
                raise ValueError('PRODUCE_META_METADATA_CHANGED')
            if budget.read_module(PIN_RVA,5,'produce_caller_PIN_after',True)!=pin:
                raise ValueError('PRODUCE_META_SOURCE_CHANGED')
            snapshot_after=locator.snapshot(budget);after=deps['ship_state'](budget,identity)
            creation_after=budget.creation(deps.get('start_time',thin.process_creation_time))
            if snapshot!=snapshot_after or before!=after or creation!=creation_after:
                raise ValueError('PRODUCE_META_SOURCE_STATE_START_CHANGED')
            final=deps['resolve_game'](pids[0]);deps['validate_identity'](final,stamps)
            if final!=identity or tuple(deps['game_processes']())!=pids:
                raise ValueError('PRODUCE_META_MODULE_PID_CHANGED')
            budget.time_gate()
        payload=bytearray(table);ranges=[{'name':'fixed_RF_window','rva':TABLE_RVA,
                                         'binary_offset':0,'length':TABLE_BYTES}]
        for node in cache.values():
            raw=bytes.fromhex(node['raw_hex']);node['binary_offset']=len(payload)
            ranges.append({'name':'standard_UW_only','rva':node['unwind_rva'],
                           'binary_offset':len(payload),'length':len(raw)})
            payload.extend(raw)
        evidence.update(complete=reason is None,status='complete'if reason is None else'WITHHELD',
            withheld_reason=reason,source_gates_verified=True,creation_filetime=creation,
            ship_before=before,ship_after=after,exception_records=records,
            unwind_nodes=list(cache.values()),same_owner_indices=same,first_foreign_boundary=boundary,
            final_record_foreign=reason is None and records[-1]['owner']!=list(PRIMARY),
            bounded_owner_window_complete=reason is None,
            saved_direct_branch_targets=known_targets,saved_successor_targets_uncovered=uncovered,
            saved_normal_successors_owner_covered=not uncovered,body_envelope_candidate=
                [PRIMARY[0],max(r['end']for r in records if r['index']in same)]if same else None,
            budget=budget.summary(),read_records=budget.records,ranges=ranges,
            binary_sha256=hashlib.sha256(payload).hexdigest(),bytes_written=len(payload),
            captured_at=datetime.now(timezone.utc).isoformat())
        (folder/'metadata.bin').write_bytes(payload)
        report=folder/'metadata.json';report.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
        return {'status':evidence['status'],'json_path':str(report),'binary_path':str(folder/'metadata.bin'),
                'withheld_reason':reason,'budget':evidence['budget']}
    except Exception as error:
        evidence.update(status='failed',error=str(error),partial_binary_saved=False)
        if budget is not None:evidence.update(budget=budget.summary(),read_records=budget.records)
        (folder/'metadata.incomplete.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    try:print(json.dumps(run(parser.parse_args().output),indent=2))
    except(OSError,ValueError)as error:parser.exit(1,str(error)+'\n')
