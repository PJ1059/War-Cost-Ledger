"""Only common21044C0: source29B CALL and exact middle.pdata record.

Known152455/152457 anchors plus middle152456 form one36B window twice.
Only the actual containing declaration<=1024B twice; bounded UW ancestry
is metadata only. Keep existing source/PE/Title-or-Ship/context/PID/module
gates and private24KiB/96IO/2s; no sibling/callee/heap/native Game action.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
WRAPPER=ROOT/'tools/hit-contact-handler-stack-declarations-capture.py'
WRAPPER_SHA='1ec46d668101d4117a168f187f0f5f68d53d0e421dc78df8c6dc9375824f74ad'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest()!=WRAPPER_SHA:
    raise ValueError('COMMON_HANDLER_FROZEN_WRAPPER_CHANGED')
spec=importlib.util.spec_from_file_location('_common_handler_private_source',WRAPPER)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
v1=parent.v1
REVISION='contact_handler_common_fixed_neighbor_declared_code_v1'
PACKET=ROOT/'dist/hit-contact-handler-stack-declarations-live-20261013-v1'
BIN_SHA='c4d64ef411d03adc422ac0430088d36e3480316ad44460271c3fdda635fa531c'
JSON_SHA='4debed027d186daf7f74f7abed9f496e9f369f64d4f030699d280c6258a124d7'
TARGET,WINDOW_RVA,WINDOW_BYTES=0x21044C0,0x4191E60,36
HANDLER_RVA,HANDLER_BYTES=0x21044A0,29
ANCHORS={152455:'a0441002bd441002b4a86302',152457:'1c451002a1451002bca86302'}
MAX_BODY=1024


def source():
    raw=parent.parent.parent.material(PACKET/'callsite.bin',BIN_SHA,110)
    meta=json.loads(parent.parent.parent.material(PACKET/'callsite.json',JSON_SHA))
    handler=raw[:HANDLER_BYTES];entries=meta.get('targets',[])
    if (not meta.get('complete') or meta.get('source_revision')!=parent.REVISION
            or meta.get('sha256')!=BIN_SHA or meta.get('fingerprint')!=v1.frozen.profile.FINGERPRINT
            or not meta.get('fixed_source_pins_before_after_match')
            or not meta.get('selected_records_before_after_match')
            or not meta.get('unwind_headers_and_chains_before_after_match') or not meta.get('fresh_gates_verified')
            or len(entries)!=2 or entries[0]['function_begin']!=HANDLER_RVA
            or entries[0]['function_end']!=HANDLER_RVA+HANDLER_BYTES
            or meta['ranges'][0]!={'name':'contact_exception_handler','module':'game','rva':HANDLER_RVA,
                'length':HANDLER_BYTES,'binary_offset':0}
            or not entries[0]['body_before_after_match'] or handler[14:19].hex()!='e80d000000'
            or 0x21044AE+5+struct.unpack_from('<i',handler,15)[0]!=TARGET
            or WINDOW_RVA!=v1.frozen.EXCEPTION_RVA+152455*12):
        raise ValueError('COMMON_HANDLER_ACTUAL_110B_SOURCE_PROFILE')
    for index,pin in ANCHORS.items():
        rows=[r for entry in entries for r in entry['exception_records'] if r['index']==index]
        if not rows or any(row['rva']!=WINDOW_RVA+(index-152455)*12 or row['raw_hex']!=pin for row in rows):
            raise ValueError('COMMON_HANDLER_SAVED_NEIGHBOR_ANCHOR_CHANGED')
    return handler


def validate_source():
    inherited=parent.validate_source();handler=source()
    inherited.update(common_handler_source={'directory':str(PACKET),'metadata_sha256':JSON_SHA,
        'binary_sha256':BIN_SHA,'handler_rva':HANDLER_RVA,'known_handler29_hex':handler.hex(),
        'caller_rva':0x21044AE,'caller_hex':'e80d000000','target_rva':TARGET,
        'neighbor_anchors':[{'index':i,'raw_hex':raw} for i,raw in ANCHORS.items()],
        'middle_record_index':152456,'middle_record_not_previously_read':True},
        common_handler_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return inherited


def capture(budget,evidence):
    handler=source();known24,known104=parent.source_pins();known_metadata={}
    reader=v1.frozen.profile.private_reader();reader.IMAGE_SIZE=v1.frozen.IMAGE_SIZE
    reader.MAX_FUNCTION_BYTES=v1.frozen.CODE_END-v1.frozen.CODE_BEGIN
    def pins():
        fresh=(budget.read_module(0x25114C0,24,'known_primary_UW24_pin'),
            budget.read_module(0x13AC1F0,104,'known_parent104_pin',True),
            budget.read_module(HANDLER_RVA,HANDLER_BYTES,'known_handler29_call_pin',True))
        if fresh!=(known24,known104,handler):raise ValueError('COMMON_HANDLER_FRESH_SOURCE_PIN_CHANGED')
    def table():
        raw=budget.read_module(WINDOW_RVA,WINDOW_BYTES,'exception_record')
        rows=[]
        for i in range(3):
            begin,end,unwind=struct.unpack_from('<III',raw,i*12)
            reader.validate_runtime_entry(begin,end,unwind)
            if not v1.frozen.CODE_BEGIN<=begin<end<=v1.frozen.CODE_END or rows and rows[-1]['end']>begin:
                raise ValueError('COMMON_HANDLER_WINDOW_SCOPE_OR_ORDER')
            index=152455+i;piece=raw[i*12:(i+1)*12].hex()
            if index in ANCHORS and piece!=ANCHORS[index]:raise ValueError('COMMON_HANDLER_FRESH_ANCHOR_CHANGED')
            rows.append({'index':index,'rva':WINDOW_RVA+i*12,'raw_hex':piece,
                         'begin':begin,'end':end,'unwind_rva':unwind})
        return raw,rows
    def metadata(rva,size):
        if not parent.RO_BEGIN<=rva<rva+size<=parent.RO_END:
            raise ValueError('COMMON_HANDLER_UW_OUTSIDE_KNOWN_RODATA')
        # Preserve both body reads and largest15IO post set before each new UW read.
        budget.require_capacity(2*MAX_BODY+157+36+52+4120+size,2+3+1+7+4+1)
        if budget.query_calls+18>parent.MAX_READS:raise ValueError('COMMON_HANDLER_POST_QUERY_RESERVATION_BUDGET')
        raw=budget.read_module(rva,size,'unwind_metadata');known_metadata[(rva,size)]=raw
        return raw
    evidence.update(capture_purpose='ONE_SOURCE_DERIVED_COMMON_HANDLER_DECLARATION_ONLY',target_rva=TARGET,
        raw_only=True,code_only=True,metadata_only=False,pdata_search_performed=False,
        sibling_code_read=False,extra_callee_reads=0,heap_reads=0,handler_data_extended=False,
        GS_handler_identity_proven=False,logical_function_complete=False,normal_CFG_closed=False,
        classification_ready=False,contract_ready=False,exception_records=[],unwind_chain=[])
    budget.require_capacity(157*2+36*2+52*2+2*MAX_BODY+4120,28)
    if budget.query_calls+28>parent.MAX_READS:raise ValueError('COMMON_HANDLER_INITIAL_POST_QUERY_BUDGET')
    pins();before,rows=table();evidence['exception_records']=rows;selected=rows[1]
    begin,end,unwind=selected['begin'],selected['end'],selected['unwind_rva']
    if not begin<=TARGET<end or end-begin>MAX_BODY:
        raise ValueError('COMMON_HANDLER_MIDDLE_TARGET_SCOPE_OR_1024B_CAP')
    reader.unwind_ancestry((begin,end,unwind),metadata,evidence['unwind_chain'])
    if any(not v1.frozen.CODE_BEGIN<=n['begin']<n['end']<=v1.frozen.CODE_END for n in evidence['unwind_chain']):
        raise ValueError('COMMON_HANDLER_ANCESTRY_OUTSIDE_CODE_SECTION')
    post_bytes=157+36+sum(size for _,size in known_metadata)+4120
    post_calls=3+1+len(known_metadata)+4
    budget.require_capacity(2*(end-begin)+post_bytes,2+post_calls)
    if budget.query_calls+2+post_calls>parent.MAX_READS:raise ValueError('COMMON_HANDLER_PRE_BODY_POST_QUERY_BUDGET')
    raw=budget.read_module(begin,end-begin,'fixed_target_declared_body',True)
    after=budget.read_module(begin,end-begin,'fixed_target_declared_body',True)
    if after!=raw:raise ValueError('COMMON_HANDLER_BODY_CHANGED_DURING_CAPTURE')
    after_table,_=table()
    if after_table!=before:raise ValueError('COMMON_HANDLER_WINDOW_CHANGED_DURING_CAPTURE')
    for (rva,size),pin in known_metadata.items():
        if budget.read_module(rva,size,'unwind_metadata')!=pin:raise ValueError('COMMON_HANDLER_AFTER_UW_CHANGED')
    pins()
    evidence.update(function_begin=begin,function_end=end,target_is_declared_begin=begin==TARGET,
        selected_record=selected,known_source_pins_before_after_match=True,window_before_after_match=True,
        unwind_headers_and_chains_before_after_match=True,body_before_after_match=True,
        declared_code_complete=True,max_body=MAX_BODY,metadata_only_ancestry=True,
        ranges=[{'name':'contact_handler_common_actual_declaration','module':'game','rva':begin,
                 'length':end-begin,'binary_offset':0}],code_bytes=end-begin,
        unwind_scope_tables_read=False,unwind_full_codes_captured=False,
        boundary_kind='one_actual_declaration_not_sibling_or_recursive_capture')
    return raw


v1.REVISION,v1.validate_source,v1.capture=REVISION,validate_source,capture


def run(output,dependencies=None,clock=time.perf_counter):return v1.run(output,dependencies,clock)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as error:parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
