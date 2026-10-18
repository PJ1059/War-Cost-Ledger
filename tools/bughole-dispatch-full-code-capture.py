"""One full512B same-owner dispatch body, twice, without discovering new bounds.

Fixed three saved RFs36B and complete contiguous UW72B before/after; parent
CALL5 before/after; source entry155 verified inside full body. Ship27268 gates,
16KiB/64IO-query/2s. No .pdata search, extraUW node, gap, callee/heap/value,
Game call/write or retry. A CFG outside512B is refused during offline analysis.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
FROZEN=ROOT/'tools/bughole-dispatch-boundary-metadata-capture.py'
FROZEN_SHA='c2e4cef0278a31fe26de4016eff78e9e36f0ef0916d8e4b68157f169d54553d2'
SOURCE=ROOT/'dist/bughole-dispatch-boundary-live-20261013-v1'
BIN_SHA='98410145f4e85ad5cd49dc8f1b3227b87ca13d3effa5f0b50fac0013f1da6ad7'
META_SHA='3a73463bd8bea92a88db9e2650f89217c8bf1605e9778fe43b84256d26cfbcc8'
REVISION='bughole_dispatch_same_owner_full512_double_read_v1'
ENTRY,SIZE,CALL,CALL_HEX=0x13D8B10,512,0x13E2097,'e8746affff'
if hashlib.sha256(FROZEN.read_bytes()).hexdigest()!=FROZEN_SHA:
    raise ValueError('BUGHOLE_FULL_FROZEN_BOUNDARY_CHANGED')
spec=importlib.util.spec_from_file_location('_bughole_full_private_boundary',FROZEN)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
encoded=(SOURCE/'drain.json').read_bytes();raw=(SOURCE/'drain.bin').read_bytes();saved=json.loads(encoded)
if hashlib.sha256(raw).hexdigest()!=BIN_SHA or len(raw)!=96 or hashlib.sha256(encoded).hexdigest()!=META_SHA:
    raise ValueError('BUGHOLE_FULL_BOUNDARY_BIN_CHANGED')
if (not saved.get('complete') or not saved.get('metadata_only') or saved.get('new_code_body_reads')!=0
        or not saved.get('source_pins_before_after_match') or not saved.get('fixed_RF_table_before_after_match')
        or not saved.get('full_UW_codes_and_trailers_before_after_match')
        or saved['code_read_plan']!={'begin':ENTRY,'end':ENTRY+SIZE,'bytes':SIZE,'body_not_read':True,'normal_CFG_proven':False}
        or saved['fingerprint']!=parent.worker.session.tail['FINGERPRINT']):
    raise ValueError('BUGHOLE_FULL_BOUNDARY_CONTRACT')
rows=saved['same_entry_contiguous_declarations']
if len(rows)!=3 or [(r['begin'],r['end']) for r in rows]!=[(ENTRY,0x13D8BAB),(0x13D8BAB,0x13D8D07),(0x13D8D07,ENTRY+SIZE)]:
    raise ValueError('BUGHOLE_FULL_DECLARED512_PLAN_CHANGED')
RF_RVA,RF_PIN=rows[0]['rva'],raw[:36]
pieces={}
for owner in saved['ownership']:
    if owner['record_index'] not in [r['index'] for r in rows]:continue
    if not owner['same_entry_primary']:raise ValueError('BUGHOLE_FULL_OWNER_CHANGED')
    for node in owner['chain']:
        for at,data in [(node['unwind_rva'],bytes.fromhex(node['full_codes_hex']))]+(
                [(node['chain_entry']['rva'],bytes.fromhex(node['chain_entry']['raw_hex']))] if 'chain_entry' in node else []):
            if (at,len(data)) in pieces and pieces[at,len(data)]!=data:raise ValueError('BUGHOLE_FULL_UW_DUPLICATE_CONFLICT')
            pieces[at,len(data)]=data
UW_RVA,UW_BYTES=0x2513C00,72
assembled=bytearray(UW_BYTES);present=set()
for (at,size),data in pieces.items():
    o=at-UW_RVA
    if not 0<=o<o+size<=UW_BYTES:raise ValueError('BUGHOLE_FULL_UW_OUTSIDE_FIXED72')
    for i,b in enumerate(data):
        if o+i in present and assembled[o+i]!=b:raise ValueError('BUGHOLE_FULL_UW_OVERLAP')
        assembled[o+i]=b;present.add(o+i)
if len(present)!=UW_BYTES:raise ValueError('BUGHOLE_FULL_UW72_NOT_COMPLETE')
UW_PIN=bytes(assembled)
worker=parent.worker
worker.REVISION=worker.session.REVISION=worker.session.reader.REVISION=REVISION


def capture(process,identity,clock=time.perf_counter,evidence=None):
    reader=worker.session.reader;reader.validate_module(identity)
    budget=reader.Budget(process,identity,clock)
    def gates():
        p=reader.window_capture((('actual_dispatch_parent_CALL_PIN',CALL,5),));p.PINS=((CALL,CALL_HEX),)
        call,_=p.capture(budget,identity,sleep=lambda _:None)
        rf=reader.checked_metadata_read(budget,RF_RVA,36)
        uw=reader.checked_metadata_read(budget,UW_RVA,UW_BYTES)
        if rf!=RF_PIN or uw!=UW_PIN:raise ValueError('BUGHOLE_FULL_FIXED_RF_OR_UW_CHANGED')
        return call,rf,uw
    before=gates()
    code=reader.window_capture((('actual_same_owner_dispatch_full512',ENTRY,SIZE),))
    code.PINS=((ENTRY,parent.entry_body.hex()),)
    first,metadata=code.capture(budget,identity,sleep=lambda _:None)
    second,_=code.capture(budget,identity,sleep=lambda _:None)
    if first!=second:raise ValueError('BUGHOLE_FULL_BODY_DOUBLE_READ_CHANGED')
    if gates()!=before:raise ValueError('BUGHOLE_FULL_SOURCE_OR_METADATA_CHANGED')
    budget.time_gate()
    metadata.update(source_revision=REVISION,complete=True,code_only=True,
        native_written=False,native_called=False,classification_ready=False,destruction_credit_proven=False,
        complete_stream=False,logical_function_complete=False,normal_CFG_proven=False,
        actual_same_owner_declarations_complete=True,body_double_read_match=True,
        parent_CALL_before_after_match=True,known_entry155_full_pin_verified=True,
        three_RF_before_after_match=True,full_UW72_before_after_match=True,
        declared_range={'begin':ENTRY,'end':ENTRY+SIZE,'bytes':SIZE},body_bytes=SIZE,
        source_boundary_binary_sha256=BIN_SHA,source_boundary_metadata_sha256=hashlib.sha256(encoded).hexdigest(),
        fixed_RF={'rva':RF_RVA,'bytes':36,'raw_hex':RF_PIN.hex()},
        fixed_UW={'rva':UW_RVA,'bytes':72,'raw_hex':UW_PIN.hex()},
        new_metadata_searches=0,new_UW_nodes=0,gap_reads=0,extra_callee_reads=0,heap_event_reads=0,
        budget=budget.summary())
    if evidence is not None:evidence.update(metadata)
    return first,metadata

worker.capture=capture

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(worker.run(a.output),ensure_ascii=False,indent=2))
    except(OSError,ValueError)as error:p.exit(1,str(error)+'\n')
