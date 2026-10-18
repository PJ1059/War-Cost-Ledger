"""Fixed read-only 13AD5BD ->12A13E0 selector declaration, not a new hook.

Fresh two stored RF anchors bound lookup to63814..63821. Only one selected
declaration, <=4KiB, is eligible for a double body read; CHAIN, unknown split,
external/indirect jump or insufficient private16KiB/64IO/2s budget withholds.
No heap, block values, helper bodies, Game calls/writes, retries or installation.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
REVISION='collision_route_selector_single_declaration_v1'
PREVIOUS=ROOT/'tools/hit-copy-tail-scratch-capture.py'
PREVIOUS_SHA='56fb1c6c958732253ff22dd2f85026c5c424cc9fa9c05a0f85f5aedbeffb3d41'
SOURCE=ROOT/'dist/hit-source-constructor-output-20261012/capture/drain.json'
SOURCE_SHA='4aead07fdc9fa876e1d35c5f140c05d4afcb056816552245e3cbba573c727500'
CONTACT=ROOT/'dist/hit-contact-whole-envelope-live-20261013-v1/callsite.bin'
CONTACT_SHA='4ab318e231a62b61db540c7e8b3d7fa7159d97839edbf9c1a7fa34b963daaafb'
TARGET=0x12A13E0
PIN_RVA,PIN=0x13AD5B6,bytes.fromhex('488d95e0040000e81e3eefff')
EXCEPTION_RVA,EXCEPTION_SIZE=0x3FD340C,0x1BF57C
ANCHORS={63813:bytes.fromhex('16132a0157132a0150c84f02'),
         63822:bytes.fromhex('c0302a01bb312a01f8c84f02')}


def source():
    if hashlib.sha256(PREVIOUS.read_bytes()).hexdigest()!=PREVIOUS_SHA:
        raise ValueError('SELECTOR_FIXED_READER_CHANGED')
    raw=SOURCE.read_bytes();contact=CONTACT.read_bytes()
    if(hashlib.sha256(raw).hexdigest()!=SOURCE_SHA
            or hashlib.sha256(contact).hexdigest()!=CONTACT_SHA
            or contact[PIN_RVA-0x13AC1F0:PIN_RVA-0x13AC1F0+12]!=PIN
            or 0x13AD5BD+5+struct.unpack_from('<i',PIN,8)[0]!=TARGET):
        raise ValueError('SELECTOR_SAVED_SOURCE_CHANGED')
    meta=json.loads(raw)
    for index,pin in ANCHORS.items():
        records=[r for r in meta['exception_records']if r['index']==index]
        if len(records)!=1 or records[0]['raw_hex']!=pin.hex():
            raise ValueError('SELECTOR_SAVED_ANCHOR_CHANGED')
    spec=importlib.util.spec_from_file_location('_selector_private_scratch_reader',PREVIOUS)
    thin=importlib.util.module_from_spec(spec);spec.loader.exec_module(thin)
    thin.MAX_BYTES,thin.MAX_IO=16*1024,64
    locator,reader,_=thin.source()
    return thin,locator,reader


def function(raw):return struct.unpack('<III',raw)


def code_graph(raw,begin):
    # Only saved/read selected bytes; CALL callees and exception edges excluded.
    sys.path.insert(0,'external/hd2-fire-analysis-deps')
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_OP_IMM
    md=Cs(CS_ARCH_X86,CS_MODE_64);md.detail=True
    decoded={i.address:i for i in md.disasm(raw,begin)}
    work=[TARGET];seen=set();issues=[];returns=[];calls=[]
    while work:
        at=work.pop()
        if at in seen:continue
        ins=decoded.get(at)
        if ins is None:issues.append({'rva':at,'reason':'MISSING_INSTRUCTION'});continue
        seen.add(at);next_pc=at+ins.size
        if ins.mnemonic.startswith('ret'):returns.append(at);continue
        if ins.mnemonic in('int3','ud2'):issues.append({'rva':at,'reason':'TRAP'});continue
        if ins.mnemonic=='call':calls.append(at)
        if ins.mnemonic.startswith('j')or ins.mnemonic.startswith('loop'):
            if len(ins.operands)!=1 or ins.operands[0].type!=CS_OP_IMM:
                issues.append({'rva':at,'reason':'UNRESOLVED_INDIRECT_JUMP'});continue
            target=ins.operands[0].imm
            if target not in decoded:issues.append({'rva':at,'target':target,'reason':'OUTSIDE_SELECTED_DECLARATION'})
            else:work.append(target)
            if ins.mnemonic=='jmp':continue
        if next_pc not in decoded:issues.append({'rva':at,'target':next_pc,'reason':'FALLTHROUGH_OUTSIDE_DECLARATION'})
        else:work.append(next_pc)
    return {'normal_CFG_closed':not issues and bool(returns),'issues':issues,
        'reachable_instruction_count':len(seen),'normal_RET_sites':sorted(returns),
        'opaque_CALL_sites':sorted(calls),'callees_followed':False,'exceptions_analyzed':False}


def run(output,dependencies=None,clock=time.perf_counter):
    folder=Path(output).resolve()
    if folder.exists():raise ValueError('SELECTOR_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    evidence={'source_revision':REVISION,'complete':False,'native_called':False,'native_written':False,
        'target_rva':TARGET,'source_pin_rva':PIN_RVA,'source_pin_hex':PIN.hex(),
        'actual_block_values_read':False,'heap_reads':0,'callee_reads':0,'attempts':1,
        'source_sha256':SOURCE_SHA,'contact_sha256':CONTACT_SHA,'body_single_declaration_only':True}
    budget=None
    try:
        thin,locator,reader=source()
        deps=dependencies if dependencies is not None else reader.profile.load_dependencies()
        stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(thin.EXPECTED_PID,):raise ValueError('SELECTOR_EXACT_PID_REQUIRED')
        identity=deps['resolve_game'](pids[0]);deps['validate_identity'](identity,stamps)
        reader.profile.validate_module(identity)
        evidence.update(game_pid=pids[0],identity=identity,fingerprint=reader.profile.FINGERPRINT)
        with deps['Process'](pids[0])as process:
            budget=thin.make_budget(reader)(process,identity,clock)
            creation=budget.creation(deps.get('start_time',thin.process_creation_time))
            before=deps['ship_state'](budget,identity)
            if before['state']!=3:raise ValueError('SELECTOR_SHIP_REQUIRED')
            snapshot=locator.snapshot(budget)
            if (snapshot[2].hex()!='85c90f85a2000000488d0581f6ffff48'
                    or struct.unpack_from('<II',snapshot[0],0x110+24+136)!=(EXCEPTION_RVA,EXCEPTION_SIZE)):
                raise ValueError('SELECTOR_LOADED_SOURCE_PROFILE')
            pin=budget.read_module(PIN_RVA,12,'selector_call_and_argument_pin',True)
            if pin!=PIN:raise ValueError('SELECTOR_FRESH_CALL_PIN')
            anchors={i:budget.read_module(EXCEPTION_RVA+i*12,12,'selector_RF_anchor')for i in ANCHORS}
            if anchors!=ANCHORS:raise ValueError('SELECTOR_FRESH_RF_ANCHOR')
            low,high=63814,63822;records=[];selected=None
            while low<high:
                if len(records)>=4:raise ValueError('SELECTOR_BOUNDED_RF_LOOKUP')
                index=(low+high)//2
                raw=budget.read_module(EXCEPTION_RVA+index*12,12,'selector_RF_lookup')
                begin,end,uw=function(raw)
                if not 0x1000<=begin<end<=0x2110A93 or not 0<=uw<identity['game_size']-4:
                    raise ValueError('SELECTOR_RF_RANGE')
                records.append({'index':index,'raw_hex':raw.hex(),'begin':begin,'end':end,'unwind_rva':uw})
                if TARGET<begin:high=index
                elif TARGET>=end:low=index+1
                else:selected=records[-1];break
            if selected is None:raise ValueError('SELECTOR_NO_DECLARATION_WITHIN_ANCHORS')
            nodes=[];entry=(selected['begin'],selected['end'],selected['unwind_rva'])
            reason=None;visited=set()
            for _ in range(4):
                begin,end,uw=entry
                if uw in visited:raise ValueError('SELECTOR_UNWIND_CYCLE')
                visited.add(uw)
                # Post fixed gates19IO + exact already-read node refreshes.
                budget.reserve(4300+128*(len(nodes)+1),19+2*(len(nodes)+1)+4)
                head=budget.read_module(uw,4,'selector_UW_header')
                flags=head[0]>>3;count=head[2]
                length=4+4*((count+1)//2)+(12 if flags&4 else 4 if flags&3 else 0)
                if head[0]&7!=1 or flags not in(0,1,2,3,4)or length>128:
                    nodes.append({'begin':begin,'end':end,'unwind_rva':uw,'raw_hex':head.hex(),
                                  'standard_layout_complete':False});reason='UNKNOWN_UW_LAYOUT';break
                budget.reserve(4300+128*(len(nodes)+1)+length,19+2*(len(nodes)+1)+2)
                raw=head if length==4 else budget.read_module(uw,length,'selector_complete_standard_UW')
                if raw[:4]!=head:raise ValueError('SELECTOR_UW_CHANGED_DURING_READ')
                nodes.append({'begin':begin,'end':end,'unwind_rva':uw,'raw_hex':raw.hex(),
                              'standard_layout_complete':True,'flags':flags})
                if not flags&4:break
                reason='CHAININFO_BODY_WITHHELD'
                entry=function(raw[-12:])
                if not 0x1000<=entry[0]<entry[1]<=0x2110A93 or entry[2]>identity['game_size']-4:
                    raise ValueError('SELECTOR_CHAIN_RANGE')
            else:reason='UNWIND_NODE_CAP_BODY_WITHHELD'
            evidence.update(exception_records=records,selected_RF=selected,unwind_nodes=nodes)
            body=None;graph=None
            if reason is None:
                size=selected['end']-selected['begin']
                if selected['begin']!=TARGET:reason='TARGET_NOT_DECLARED_ENTRY'
                elif size>4096:reason='DECLARATION_OVER_4K'
                else:
                    post_bytes=4300+sum(len(bytes.fromhex(n['raw_hex']))for n in nodes)
                    budget.reserve(size*2+post_bytes,4+19+2*len(nodes))
                    body=budget.read_module(selected['begin'],size,'selector_declared_body_before',True)
                    second=budget.read_module(selected['begin'],size,'selector_declared_body_after',True)
                    if body!=second:raise ValueError('SELECTOR_BODY_CHANGED')
                    graph=code_graph(body,selected['begin'])
                    if not graph['normal_CFG_closed']:reason='UNRESOLVED_NORMAL_CFG_BODY_WITHHELD'
            for node in nodes:
                raw=bytes.fromhex(node['raw_hex'])
                if budget.read_module(node['unwind_rva'],len(raw),'selector_UW_after')!=raw:
                    raise ValueError('SELECTOR_METADATA_CHANGED')
            selected_raw=budget.read_module(EXCEPTION_RVA+selected['index']*12,12,'selector_RF_after')
            if selected_raw.hex()!=selected['raw_hex']:raise ValueError('SELECTOR_METADATA_CHANGED')
            for index,raw in anchors.items():
                if budget.read_module(EXCEPTION_RVA+index*12,12,'selector_RF_anchor_after')!=raw:
                    raise ValueError('SELECTOR_METADATA_CHANGED')
            if budget.read_module(PIN_RVA,12,'selector_call_pin_after',True)!=pin:
                raise ValueError('SELECTOR_SOURCE_CHANGED')
            snap_after=locator.snapshot(budget);after=deps['ship_state'](budget,identity)
            creation_after=budget.creation(deps.get('start_time',thin.process_creation_time))
            if snapshot!=snap_after or before!=after or creation!=creation_after:
                raise ValueError('SELECTOR_SOURCE_STATE_START_CHANGED')
            final=deps['resolve_game'](pids[0]);deps['validate_identity'](final,stamps)
            if final!=identity or tuple(deps['game_processes']())!=pids:raise ValueError('SELECTOR_MODULE_PID_CHANGED')
            budget.time_gate()
        evidence.update(complete=reason is None,status='complete'if reason is None else'WITHHELD',
            withheld_reason=reason,source_gates_verified=True,creation_filetime=creation,
            ship_before=before,ship_after=after,budget=budget.summary(),read_records=budget.records,
            normal_CFG=graph,captured_at=datetime.now(timezone.utc).isoformat(),
            selector_semantics_proven=False,handler_data_semantics_proven=False,Game_logic_executed=False)
        if reason is None:
            evidence.update(body_sha256=hashlib.sha256(body).hexdigest(),body_bytes=len(body))
            (folder/'selector.bin').write_bytes(body)
        elif body is not None:evidence.update(withheld_body_sha256=hashlib.sha256(body).hexdigest(),body_bytes_read=len(body))
        report=folder/'selector.json';report.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
        return {'status':evidence['status'],'json_path':str(report),'withheld_reason':reason,
                'binary_path':str(folder/'selector.bin')if reason is None else None}
    except Exception as error:
        evidence.update(status='failed',error=str(error),partial_binary_saved=False)
        if budget is not None:evidence.update(budget=budget.summary(),read_records=budget.records)
        (folder/'selector.incomplete.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    try:print(json.dumps(run(parser.parse_args().output),indent=2))
    except(OSError,ValueError)as error:parser.exit(1,str(error)+'\n')
