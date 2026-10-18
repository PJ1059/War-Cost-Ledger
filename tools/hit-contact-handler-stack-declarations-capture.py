"""Two source-derived targets, each actual declaration<=1024B twice.

Only handler21044A0 from frozenUW20 and prologue CALL21045C0.
Known UW24/parent104 and current selected.pdata/UW-header/chain pre/post
plus originalPE/CALL/Title-or-Ship/context/PID/module gates. One private
24KiB/96IO/2s profile. No callee, sibling, handler-data extension, heap,
native invocation or Game modification. Missing declarations withhold.
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
WRAPPER=ROOT/'tools/hit-contact-primary-handler-prefix-capture.py'
WRAPPER_SHA='74df57b47cd01f3d3682e9a72b5e1c7cf4436edf7b6eec745d0860a897331e0d'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest()!=WRAPPER_SHA:
    raise ValueError('HANDLER_STACK_FROZEN_WRAPPER_CHANGED')
spec=importlib.util.spec_from_file_location('_handler_stack_private_source',WRAPPER)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
v1=parent.v1
REVISION='contact_source_derived_handler_stack_actual_declarations_v1'
PACKET=ROOT/'dist/hit-contact-primary-handler-prefix-live-20261013-v1'
BIN_SHA='a5ec01933cb6b9d392b80ea4f508958aa6fb070ee4f9e35d16a9f222aa60147a'
JSON_SHA='4e45d24503b65c5197f8b2ceac35dc12e3d29cd416f34614de7ddc8c6df330c2'
PREFIX=parent.parent.material(PACKET/'callsite.bin',BIN_SHA,24)
TARGETS=(('contact_exception_handler',0x21044A0),('contact_prologue_call_candidate',0x21045C0))
MAX_BODY,MAX_READS=1024,96
RO_BEGIN,RO_END=0x2111000,0x263BA0C
POST_MAX_BYTES,POST_MAX_CALLS=24+104+128+4120,2+14+2+4


def source_pins():return PREFIX,parent.parent.layout_source()[0]


def validate_source():
    source=parent.validate_source();known24,code=source_pins()
    meta=json.loads(parent.parent.material(PACKET/'callsite.json',JSON_SHA))
    call_at=0x13AC201-0x13AC1F0
    if (not meta.get('complete') or meta.get('source_revision')!=parent.REVISION
            or meta.get('sha256')!=BIN_SHA or not meta.get('known20_before_after_match')
            or not meta.get('primary_prefix_before_after_match') or not meta.get('fresh_gates_verified')
            or meta.get('fingerprint')!=v1.frozen.profile.FINGERPRINT
            or known24[:20]!=parent.KNOWN or struct.unpack_from('<I',known24,16)[0]!=TARGETS[0][1]
            or code[call_at:call_at+5].hex()!='e8ba83d500'
            or 0x13AC201+5+struct.unpack_from('<i',code,call_at+1)[0]!=TARGETS[1][1]):
        raise ValueError('HANDLER_STACK_ACTUAL_SOURCE_PROFILE')
    source.update(actual_primary_prefix_packet={'directory':str(PACKET),'metadata_sha256':JSON_SHA,
        'binary_sha256':BIN_SHA,'fixed24_hex':known24.hex()},
        exact_targets=[{'name':name,'rva':rva,'symbol_identity_proven':False} for name,rva in TARGETS],
        prologue_call_pin={'rva':0x13AC201,'hex':'e8ba83d500','target_rva':0x21045C0},
        handler_stack_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return source


_base_budget=v1.Budget


class Budget(_base_budget):
    def __init__(self,process,identity,clock=time.perf_counter):
        v1.MAX_READS=MAX_READS  # Private imports only; old32IO files stay unchanged.
        super().__init__(process,identity,clock)
        v1.frozen.DECLARATION_PURPOSES.add('fixed_target_declared_body')


_header=v1.frozen.inspect_header


def inspect_header(budget):
    raw=_header(budget);at=v1.frozen.PE_OFFSET+24+240+40
    if (struct.unpack_from('<II',raw,at+8)!=(RO_END-RO_BEGIN,RO_BEGIN)
            or struct.unpack_from('<I',raw,at+36)[0]!=0x40000040):
        raise ValueError('HANDLER_STACK_RODATA_SECTION_CHANGED')
    return raw


def capture(budget,evidence):
    expected=source_pins();entries=[];metadata={}
    reader=v1.frozen.profile.private_reader();reader.IMAGE_SIZE=v1.frozen.IMAGE_SIZE
    reader.EXCEPTION_RVA,reader.EXCEPTION_SIZE=v1.frozen.EXCEPTION_RVA,v1.frozen.EXCEPTION_SIZE
    reader.MAX_FUNCTION_BYTES=v1.frozen.CODE_END-v1.frozen.CODE_BEGIN
    def reserve(size=0,calls=0):
        budget.require_capacity(4*MAX_BODY+POST_MAX_BYTES+size,4+POST_MAX_CALLS+calls)
        if budget.query_calls+4+POST_MAX_CALLS+calls>MAX_READS:
            raise ValueError('HANDLER_STACK_POST_QUERY_RESERVATION_BUDGET')
    def checked(rva,size):
        table=v1.frozen.EXCEPTION_RVA<=rva<rva+size<=v1.frozen.EXCEPTION_RVA+v1.frozen.EXCEPTION_SIZE
        if not table and not RO_BEGIN<=rva<rva+size<=RO_END:
            raise ValueError('HANDLER_STACK_UW_OUTSIDE_KNOWN_RODATA')
        reserve(size,1)
        raw=budget.read_module(rva,size,'exception_record' if table else 'unwind_metadata')
        if not table:
            key=rva,size
            if key in metadata and metadata[key]!=raw:raise ValueError('HANDLER_STACK_UW_CHANGED_DURING_DISCOVERY')
            metadata[key]=raw
        return raw
    reader.checked_metadata_read=lambda b,rva,size:checked(rva,size)
    def pins():
        raw=(budget.read_module(parent.BEGIN,24,'known_primary_UW24_pin'),
             budget.read_module(parent.parent.PARENT_RVA,104,'known_parent104_pin',True))
        if raw!=expected:raise ValueError('HANDLER_STACK_FRESH_SOURCE_PIN_CHANGED')
        return raw
    evidence.update(capture_purpose='TWO_SOURCE_DERIVED_ACTUAL_DECLARATIONS_ONLY',targets=entries,
        metadata_only=False,code_only=True,raw_only=True,pdata_search_performed=True,
        target_symbol_identity_proven=False,stackprobe_identity_proven=False,GS_handler_identity_proven=False,
        sibling_code_read=False,extra_callee_reads=0,heap_reads=0,handler_data_extended=False,
        logical_function_complete=False,normal_CFG_closed=False,classification_ready=False,contract_ready=False)
    pins()
    for name,target in TARGETS:
        reader.TARGET_RVA,reader.TARGET_PIN=target,''  # No fabricated instruction-prefix PIN.
        journal=[];entry={'name':name,'target_rva':target,'exception_records':journal,'unwind_chain':[]}
        entries.append(entry)
        begin,end=reader.find_function(budget,journal)
        if not v1.frozen.CODE_BEGIN<=begin<=target<end<=v1.frozen.CODE_END or end-begin>MAX_BODY:
            raise ValueError('HANDLER_STACK_DECLARATION_SCOPE_OR_1024B_CAP')
        row=journal[-1]
        reader.unwind_ancestry((begin,end,row['unwind_rva']),checked,entry['unwind_chain'])
        if any(not v1.frozen.CODE_BEGIN<=node['begin']<node['end']<=v1.frozen.CODE_END for node in entry['unwind_chain']):
            raise ValueError('HANDLER_STACK_ANCESTRY_OUTSIDE_CODE_SECTION')
        entry.update(function_begin=begin,function_end=end,selected_record=row,
            target_is_declared_begin=target==begin,declared_code_bytes=end-begin,
            declared_code_complete=False,logical_function_complete=False)
    post_calls=2+len(metadata)+2+4
    post_bytes=24+sum(size for _,size in metadata)+128+4120
    body_bytes=2*sum(entry['declared_code_bytes'] for entry in entries)
    budget.require_capacity(body_bytes+post_bytes,4+post_calls)
    if budget.query_calls+4+post_calls>MAX_READS:raise ValueError('HANDLER_STACK_PRE_BODY_POST_QUERY_RESERVATION_BUDGET')
    chunks=[];ranges=[];offset=0
    for entry in entries:
        begin,length=entry['function_begin'],entry['declared_code_bytes']
        raw=budget.read_module(begin,length,'fixed_target_declared_body',True)
        after=budget.read_module(begin,length,'fixed_target_declared_body',True)
        if raw!=after:raise ValueError('HANDLER_STACK_DECLARED_BODY_CHANGED: '+entry['name'])
        entry.update(body_before_after_match=True,declared_code_complete=True)
        chunks.append(raw);ranges.append({'name':entry['name'],'module':'game','rva':begin,
            'length':length,'binary_offset':offset});offset+=length
    for entry in entries:
        record=entry['selected_record']
        after=budget.read_module(record['rva'],12,'exception_record')
        if after.hex()!=record['raw_hex']:raise ValueError('HANDLER_STACK_SELECTED_RECORD_CHANGED')
    for (rva,size),raw in metadata.items():
        if budget.read_module(rva,size,'unwind_metadata')!=raw:raise ValueError('HANDLER_STACK_AFTER_UW_CHANGED')
    pins()
    evidence.update(ranges=ranges,code_bytes=offset,declared_code_complete=True,
        fixed_source_pins_before_after_match=True,selected_records_before_after_match=True,
        unwind_headers_and_chains_before_after_match=True,metadata_only_ancestry=True,
        max_body_per_target=MAX_BODY,max_unwind_nodes_per_target=4,
        unwind_scope_tables_read=False,unwind_full_codes_captured=False,
        boundary_kind='two_actual_declarations_not_recursive_or_logically_complete')
    return b''.join(chunks)


v1.REVISION,v1.validate_source,v1.Budget,v1.capture=REVISION,validate_source,Budget,capture
v1.frozen.inspect_header=inspect_header


def run(output,dependencies=None,clock=time.perf_counter):return v1.run(output,dependencies,clock)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as error:parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
