"""One proved same-owner4546B ProduceDamage envelope, read-only double read.

Five fresh RFs/standard UWs and caller5B before/after. Saved2361B primary
prefix must match body byteexact. No foreign body/callee/handler data/heap.
Two fixed <=4096B reads per body sample share24KiB/64 totalIO/2s gates.
Declared owner envelope is not a proof of normalCFG/DP/HI/feedback semantics.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
REVISION='produce_damage_same_owner_whole_envelope_v1'
PREVIOUS=ROOT/'tools/hit-produce-damage-logical-metadata-capture.py'
PREVIOUS_SHA='86aaa848a356ce345a4eb3f61322391d9377391437ba2b7a18475bf2a8738886'
SOURCE=ROOT/'dist/hit-produce-damage-logical-metadata-live-0.4.25-v2/metadata.json'
SOURCE_SHA='d9720576131d9f461938883d283e095a6b89c6a3c30e9abcfe3bc0277c0cfeec'
SOURCE_BIN_SHA='207bda5ede4ea2a6562049b5f382ecb2c4564542af896e705b2d10127b1b0749'
BEGIN,END=0x129DD30,0x129EEF2
SIZE=END-BEGIN


def source():
    if hashlib.sha256(PREVIOUS.read_bytes()).hexdigest()!=PREVIOUS_SHA:
        raise ValueError('PRODUCE_BODY_FROZEN_READER_CHANGED')
    meta_raw=SOURCE.read_bytes();raw=SOURCE.with_name('metadata.bin').read_bytes()
    if(hashlib.sha256(meta_raw).hexdigest()!=SOURCE_SHA
            or hashlib.sha256(raw).hexdigest()!=SOURCE_BIN_SHA):
        raise ValueError('PRODUCE_BODY_METADATA_SOURCE_CHANGED')
    meta=json.loads(meta_raw)
    if(not meta['bounded_owner_window_complete']or meta['saved_successor_targets_uncovered']
            or meta['same_owner_indices']!=list(range(63772,63777))
            or meta['body_envelope_candidate']!=[BEGIN,END]):
        raise ValueError('PRODUCE_BODY_FIXED_OWNER_SOURCE')
    records=[r for r in meta['exception_records']if r['index']in meta['same_owner_indices']]
    table=b''.join(bytes.fromhex(r['raw_hex'])for r in records)
    nodes=[n for n in meta['unwind_nodes']if n['unwind_rva']in{r['unwind_rva']for r in records}]
    if(len(table)!=60 or len(nodes)!=5 or sum(n['standard_length']for n in nodes)!=128
            or records[0]['begin']!=BEGIN or records[-1]['end']!=END
            or any(a['end']!=b['begin']for a,b in zip(records,records[1:]))):
        raise ValueError('PRODUCE_BODY_FIXED_METADATA_LAYOUT')
    for node in nodes:
        at,length=node['binary_offset'],node['standard_length']
        if(raw[at:at+length].hex()!=node['raw_hex']or node['handler_specific_data_read']):
            raise ValueError('PRODUCE_BODY_STANDARD_SOURCE_RANGE')
    if raw[:60]!=table:raise ValueError('PRODUCE_BODY_RF_SOURCE_RANGE')
    spec=importlib.util.spec_from_file_location('_produce_body_private_reader',PREVIOUS)
    previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
    old_raw=previous.SOURCE.read_bytes();old_bin=previous.SOURCE_BIN.read_bytes()
    if(hashlib.sha256(old_raw).hexdigest()!=previous.SOURCE_SHA
            or hashlib.sha256(old_bin).hexdigest()!=previous.SOURCE_BIN_SHA
            or len(old_bin)!=2366 or old_bin[:5]!=previous.PIN
            or previous.PIN_RVA+5+previous.struct.unpack_from('<i',previous.PIN,1)[0]!=BEGIN
            or hashlib.sha256(previous.PREVIOUS.read_bytes()).hexdigest()!=previous.PREVIOUS_SHA):
        raise ValueError('PRODUCE_BODY_OLD_PREFIX_SOURCE_CHANGED')
    # Reuse only the frozen budget/identity+named-export reader. Current formal
    # observer docs are mutable during0.4.26 build and not a body-read source.
    spec=importlib.util.spec_from_file_location('_produce_body_private_budget',previous.PREVIOUS)
    thin=importlib.util.module_from_spec(spec);spec.loader.exec_module(thin)
    if hashlib.sha256(thin.LOCATOR.read_bytes()).hexdigest()!=thin.LOCATOR_SHA:
        raise ValueError('PRODUCE_BODY_LOCATOR_SOURCE_CHANGED')
    spec=importlib.util.spec_from_file_location('_produce_body_private_locator',thin.LOCATOR)
    locator=importlib.util.module_from_spec(spec);spec.loader.exec_module(locator)
    locator.validate_source();reader=locator.private_reader()
    thin.MAX_BYTES,thin.MAX_IO=24*1024,64
    return previous,thin,locator,reader,table,nodes,old_bin[5:]


def metadata(budget,previous,table,nodes,suffix):
    if budget.read_module(previous.TABLE_RVA,60,'produce_five_RF_'+suffix)!=table:
        raise ValueError('PRODUCE_BODY_FRESH_RF_CHANGED')
    for node in nodes:
        raw=bytes.fromhex(node['raw_hex'])
        if budget.read_module(node['unwind_rva'],len(raw),'produce_standard_UW_'+suffix)!=raw:
            raise ValueError('PRODUCE_BODY_FRESH_UW_CHANGED')
    pin=budget.read_module(previous.PIN_RVA,5,'produce_caller_PIN_'+suffix,True)
    if pin!=previous.PIN:raise ValueError('PRODUCE_BODY_FRESH_CALL_CHANGED')


def body(budget,suffix):
    return b''.join(budget.read_module(BEGIN+offset,min(4096,SIZE-offset),
                    'produce_owner_body_'+suffix,True)for offset in range(0,SIZE,4096))


def run(output,dependencies=None,clock=time.perf_counter):
    folder=Path(output).resolve()
    if folder.exists():raise ValueError('PRODUCE_BODY_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    evidence={'source_revision':REVISION,'complete':False,'attempts':1,
        'source_sha256':SOURCE_SHA,'source_bin_sha256':SOURCE_BIN_SHA,
        'range':[BEGIN,END],'declared_code_bytes':SIZE,'same_owner_RF_indices':list(range(63772,63777)),
        'normal_CFG_complete':False,'HI_write_semantics_proven':False,'DP_bit_semantics_proven':False,
        'classification_ready':False,'native_called':False,'native_written':False,
        'heap_reads':0,'handler_specific_data_read':False,'callee_reads':0}
    budget=None
    try:
        previous,thin,locator,reader,table,nodes,prefix=source()
        deps=dependencies if dependencies is not None else reader.profile.load_dependencies()
        stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(thin.EXPECTED_PID,):raise ValueError('PRODUCE_BODY_EXACT_PID_REQUIRED')
        identity=deps['resolve_game'](pids[0]);deps['validate_identity'](identity,stamps)
        reader.profile.validate_module(identity)
        evidence.update(game_pid=pids[0],identity=identity,fingerprint=reader.profile.FINGERPRINT)
        with deps['Process'](pids[0])as process:
            budget=thin.make_budget(reader)(process,identity,clock)
            creation=budget.creation(deps.get('start_time',thin.process_creation_time))
            before=deps['ship_state'](budget,identity)
            if before['state']!=3:raise ValueError('PRODUCE_BODY_SHIP_REQUIRED')
            snapshot=locator.snapshot(budget)
            if(snapshot[2].hex()!='85c90f85a2000000488d0581f6ffff48'
                    or previous.struct.unpack_from('<II',snapshot[0],0x110+24+136)
                    !=(previous.EXCEPTION_RVA,previous.EXCEPTION_SIZE)):
                raise ValueError('PRODUCE_BODY_LOADED_SOURCE_PROFILE')
            metadata(budget,previous,table,nodes,'before')
            #2body samples8IO + metadata14IO, PE/export/getter6IO,
            #Ship4IO + creation1IO =>33 remainingIO, bytes9092+4391.
            budget.reserve(SIZE*2+4391,33)
            first=body(budget,'before')
            if first[:len(prefix)]!=prefix:raise ValueError('PRODUCE_BODY_PRIMARY_PREFIX_CHANGED')
            second=body(budget,'after')
            if first!=second:raise ValueError('PRODUCE_BODY_CHANGED')
            metadata(budget,previous,table,nodes,'after')
            snapshot_after=locator.snapshot(budget);after=deps['ship_state'](budget,identity)
            creation_after=budget.creation(deps.get('start_time',thin.process_creation_time))
            if snapshot!=snapshot_after or before!=after or creation!=creation_after:
                raise ValueError('PRODUCE_BODY_SOURCE_STATE_START_CHANGED')
            final=deps['resolve_game'](pids[0]);deps['validate_identity'](final,stamps)
            if final!=identity or tuple(deps['game_processes']())!=pids:
                raise ValueError('PRODUCE_BODY_MODULE_PID_CHANGED')
            budget.time_gate()
        evidence.update(complete=True,status='complete',source_gates_verified=True,
            creation_filetime=creation,ship_before=before,ship_after=after,
            prefix_source_sha256=previous.SOURCE_BIN_SHA,prefix_bytes_verified=len(prefix),
            standard_UW_only=True,body_sha256=hashlib.sha256(first).hexdigest(),
            budget=budget.summary(),read_records=budget.records,
            captured_at=datetime.now(timezone.utc).isoformat())
        (folder/'body.bin').write_bytes(first)
        report=folder/'body.json';report.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
        return {'status':'complete','json_path':str(report),'binary_path':str(folder/'body.bin'),
                'budget':evidence['budget']}
    except Exception as error:
        evidence.update(status='failed',error=str(error),partial_binary_saved=False)
        if budget is not None:evidence.update(budget=budget.summary(),read_records=budget.records)
        (folder/'body.incomplete.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    try:print(json.dumps(run(parser.parse_args().output),indent=2))
    except(OSError,ValueError)as error:parser.exit(1,str(error)+'\n')
