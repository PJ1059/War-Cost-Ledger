"""Only84B .pdata68131..68137 and two finite exit ownership chains.

Fixed [409ADB0,409AE04) twice. No new code body, handler, heap/reference,
callee or native Game call/write. Fresh parent104/known150/known tail128
plus original PE/CALL/Title-or-Ship/context/PID/module gates. One shared
24KiB/48RPM-query/2s soft budget in this private new profile only; missing targets or budget withhold without
expanding. UW ownership metadata is not CFG, consumption or lifetime proof.
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
WRAPPER=ROOT/'tools/hit-contact-consume-tail-capture.py'
WRAPPER_SHA='5808096d00556ef13120c9622e1dcb1bac44c90fcf1d56a7e742ddd5b60f6e4f'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest()!=WRAPPER_SHA:
    raise ValueError('EXIT_METADATA_FROZEN_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_contact_exit_private_parent',WRAPPER)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
v1=parent.v1
REVISION='contact_exit_fixed84_exception_ownership_v1'
PACKET=ROOT/'dist/hit-contact-consume-tail-live-20261013-v1'
PACKET_JSON_SHA='ff39be3696c8fb346d766f8481533ef754a529ebd0a89d289f06599c29ebadcb'
TAIL_SHA='e1ed84fdd459689ee1581ddad92fc3082977c035f9af8d5230c066652f44fb13'
WINDOW_RVA,WINDOW_BYTES=0x409ADB0,84
TARGETS=(0x13AFCD1,0x13B053F)
MAX_UNKNOWN_NODES=4
MAX_READS=48
RO_BEGIN,RO_END=0x2111000,0x263BA0C
ANCHORS={68133:'17fd3a01cf023b0158155102',68137:'80053b0156063b01c0155102'}
TAIL_PIN=parent.material(PACKET/'callsite.bin',TAIL_SHA,128)


def validate_source():
    source=parent.validate_source()
    saved=json.loads(parent.material(parent.UNWIND_SOURCE,parent.UNWIND_SHA))
    site=next(s for s in saved['sites'] if s['name']=='contact_begin')
    for index,hexraw in ANCHORS.items():
        rows=[r for r in site['exception_records'] if r['index']==index]
        if len(rows)!=1 or rows[0]['raw_hex']!=hexraw:
            raise ValueError('EXIT_METADATA_SAVED_ANCHOR_PROFILE')
    meta=json.loads(parent.material(PACKET/'callsite.json',PACKET_JSON_SHA))
    if (not meta.get('complete') or meta.get('source_revision')!=parent.REVISION
            or meta.get('fingerprint')!=v1.frozen.profile.FINGERPRINT
            or meta.get('sha256')!=TAIL_SHA or not meta.get('tail_before_after_match')
            or not meta.get('fresh_layout_pins_before_after_match')
            or not meta.get('fresh_unwind_matches_saved_source') or not meta.get('fresh_gates_verified')
            or meta.get('fixed_record_before')!=parent.RECORD_HEX
            or meta.get('fixed_record_after')!=parent.RECORD_HEX
            or meta.get('unwind_chain')!=parent.unwind_source()
            or meta.get('ranges')!=[{'name':'contact_consume_candidate_tail128','module':'game',
                'rva':parent.TAIL_BEGIN,'length':128,'binary_offset':0}]):
        raise ValueError('EXIT_METADATA_ACTUAL_TAIL_SOURCE_PROFILE')
    source.update(actual_tail_source={'directory':str(PACKET.resolve()),'metadata_sha256':PACKET_JSON_SHA,
        'binary_sha256':TAIL_SHA,'fresh_tail128_pin_required':True},
        saved_record_anchors=[{'index':i,'raw_hex':h,'ownership_proven':False} for i,h in ANCHORS.items()],
        exit_metadata_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return source


_base_budget=v1.Budget


class Budget(_base_budget):
    def __init__(self,process,identity,clock=time.perf_counter):
        # v1 is an independently imported private copy; no old file/default changes.
        v1.MAX_READS=MAX_READS
        super().__init__(process,identity,clock)
        v1.frozen.DECLARATION_PURPOSES.add('exit_exception_window')


_original_header=v1.frozen.inspect_header


def inspect_header(budget):
    raw=_original_header(budget)
    at=v1.frozen.PE_OFFSET+24+240+40
    if (struct.unpack_from('<II',raw,at+8)!=(RO_END-RO_BEGIN,RO_BEGIN)
            or struct.unpack_from('<I',raw,at+36)[0]!=0x40000040):
        raise ValueError('EXIT_METADATA_RODATA_SECTION_CHANGED')
    return raw


def capture(budget,evidence):
    parent_pin,field_pin=parent.layout_source()
    expected=parent.unwind_source()
    reader=v1.frozen.profile.private_reader()
    reader.IMAGE_SIZE=v1.frozen.IMAGE_SIZE
    reader.MAX_FUNCTION_BYTES=v1.frozen.CODE_END-v1.frozen.CODE_BEGIN
    source_known={tuple(n[k] for k in ('begin','end','unwind_rva')):i for i,n in enumerate(expected)}
    known_bytes={(n[key]['rva'],len(bytes.fromhex(n[key]['raw_hex']))):bytes.fromhex(n[key]['raw_hex'])
                 for n in expected for key in ('header','chain_entry') if key in n}
    cache,nodes_cache={},{}
    evidence.update(capture_purpose='FIXED84B_EXIT_STATEMENT_OWNERSHIP_METADATA_ONLY',
        target_rva=WINDOW_RVA,code_only=False,metadata_only=True,new_code_body_reads=0,
        heap_reads=0,handler_scope_read=False,extra_callee_reads=0,pdata_search_performed=False,
        ownership=[],metadata_cache_reuses=0,normal_CFG_closed=False,
        count_clear_or_consume_timing_proven=False,runtime_object_lifetime_proven=False,
        logical_function_complete=False,classification_ready=False,contract_ready=False)
    POST_BYTES,POST_CALLS=382+84+4120,8
    def reserve(size=0,calls=0):
        budget.require_capacity(POST_BYTES+size,POST_CALLS+calls)
        if budget.query_calls+POST_CALLS+calls>v1.MAX_READS:
            raise ValueError('EXIT_METADATA_POST_QUERY_RESERVATION_BUDGET')
    def source_pins():
        return (budget.read_module(parent.PARENT_RVA,104,'known_parent104_pin',True),
            budget.read_module(parent.FIELD_RVA,150,'known_ESI_count_row_pin',True),
            budget.read_module(parent.TAIL_BEGIN,128,'known_consume_tail128_pin',True))
    # Three code gates + window + seven known UW IO + eight post gates.
    budget.require_capacity(382*2+84*2+52+4120,19)
    if budget.query_calls+19>v1.MAX_READS:
        raise ValueError('EXIT_METADATA_BASELINE_QUERY_BUDGET')
    before=source_pins()
    if before!=(parent_pin,field_pin,TAIL_PIN):
        raise ValueError('EXIT_METADATA_FRESH_CODE_PIN_CHANGED')
    raw=budget.read_module(WINDOW_RVA,84,'exit_exception_window')
    if raw[:12].hex()!=parent.RECORD_HEX:
        raise ValueError('EXIT_METADATA_FRESH_FIRST_RECORD_CHANGED')
    records=[]
    for i in range(7):
        begin,end,unwind=struct.unpack_from('<III',raw,i*12)
        reader.validate_runtime_entry(begin,end,unwind)
        if not v1.frozen.CODE_BEGIN<=begin<end<=v1.frozen.CODE_END or records and records[-1]['end']>begin:
            raise ValueError('EXIT_METADATA_FIXED_RECORD_SCOPE_OR_ORDER')
        records.append({'index':parent.RECORD_INDEX+i,'rva':WINDOW_RVA+i*12,
                        'raw_hex':raw[i*12:(i+1)*12].hex(),'begin':begin,'end':end,'unwind_rva':unwind})
    evidence['exception_records']=records
    for row in records:
        if row['index'] in ANCHORS and row['raw_hex']!=ANCHORS[row['index']]:
            raise ValueError('EXIT_METADATA_FRESH_SAVED_RECORD_ANCHOR_CHANGED')
    def metadata(rva,size):
        if not RO_BEGIN<=rva<rva+size<=RO_END:
            raise ValueError('EXIT_METADATA_UW_OUTSIDE_KNOWN_RODATA')
        key=rva,size
        if key in cache:
            evidence['metadata_cache_reuses']+=1
            return cache[key]
        reserve(size,1)
        data=budget.read_module(rva,size,'unwind_metadata')
        if key in known_bytes and data!=known_bytes[key]:
            raise ValueError('EXIT_METADATA_FRESH_KNOWN_UW_CHANGED')
        cache[key]=data
        return data
    known=[]
    reader.unwind_ancestry(parent.DECLARATION,metadata,known)
    if known!=expected:raise ValueError('EXIT_METADATA_FRESH_PRIMARY_CHAIN_CHANGED')
    evidence['unwind_chain']=known
    for node in known:nodes_cache[tuple(node[k] for k in ('begin','end','unwind_rva'))]=node
    primary=tuple(known[-1][k] for k in ('begin','end','unwind_rva'))
    for target in TARGETS:
        hits=[r for r in records if r['begin']<=target<r['end']]
        if len(hits)!=1:raise ValueError('EXIT_METADATA_TARGET_NOT_IN_FIXED_WINDOW: '+hex(target))
        row=hits[0];current=tuple(row[k] for k in ('begin','end','unwind_rva'))
        chain,seen,seen_unwind,unknown,frame=[],set(),set(),0,None
        while True:
            reader.validate_runtime_entry(*current)
            if not v1.frozen.CODE_BEGIN<=current[0]<current[1]<=v1.frozen.CODE_END:
                raise ValueError('EXIT_METADATA_CHAIN_OUTSIDE_CODE_SECTION')
            if current in seen or current[2] in seen_unwind:raise ValueError('EXIT_METADATA_UW_CYCLE')
            seen.add(current);seen_unwind.add(current[2])
            if current in source_known:
                tail=known[source_known[current]:]
                if frame is not None and any(bytes.fromhex(n['header']['raw_hex'])[3]!=frame for n in tail):
                    raise ValueError('EXIT_METADATA_UW_FRAME_MISMATCH')
                chain.extend(tail);evidence['metadata_cache_reuses']+=len(tail);break
            unknown+=1
            if unknown>MAX_UNKNOWN_NODES:raise ValueError('EXIT_METADATA_UNKNOWN_UW_NODE_LIMIT')
            if current in nodes_cache:
                node=nodes_cache[current];evidence['metadata_cache_reuses']+=1
            else:
                begin,end,unwind=current;header=metadata(unwind,4)
                flags=reader.check_unwind_header(header)
                node={'begin':begin,'end':end,'unwind_rva':unwind,'header':{'rva':unwind,'raw_hex':header.hex()}}
                if flags&4:
                    at=unwind+4+2*((header[2]+1)&~1)
                    chained=metadata(at,12)
                    node['chain_entry']={'rva':at,'raw_hex':chained.hex()}
                nodes_cache[current]=node
            header=bytes.fromhex(node['header']['raw_hex'])
            if frame is not None and frame!=header[3]:raise ValueError('EXIT_METADATA_UW_FRAME_MISMATCH')
            frame=header[3];chain.append(node)
            if 'chain_entry' not in node:break
            current=struct.unpack('<III',bytes.fromhex(node['chain_entry']['raw_hex']))
        terminal=tuple(chain[-1][k] for k in ('begin','end','unwind_rva'))
        ownership={'target_rva':target,'record_index':row['index'],'declaration_begin':row['begin'],
            'declaration_end':row['end'],'unwind_chain':chain,'unknown_node_count':unknown,
            'terminal_primary':list(terminal),'same_contact_primary':terminal==primary,
            'statement_ownership_only':True,'CFG_or_runtime_object_proven':False}
        evidence['ownership'].append(ownership)
        if terminal!=primary:raise ValueError('EXIT_METADATA_PRIMARY_OWNER_DIFFERS')
    after=budget.read_module(WINDOW_RVA,84,'exit_exception_window')
    if after!=raw or source_pins()!=before:raise ValueError('EXIT_METADATA_WINDOW_OR_SOURCE_CHANGED')
    evidence.update(exception_window_before_after_match=True,full_known_source_pins_before_after_match=True,
        fresh_primary_chain_verified=True,fixed_record_verified_before_after=True,
        ranges=[{'name':'contact_hot_and_next6_exception_records','module':'game','rva':WINDOW_RVA,
                 'length':84,'binary_offset':0}],code_bytes=0,metadata_bytes=84,
        max_unknown_UW_nodes_per_target=4,boundary_kind='statement_ownership_not_full_exit_CFG',
        declared_code_complete=False,unwind_scope_tables_read=False,unwind_full_codes_captured=False)
    return raw


v1.REVISION,v1.validate_source,v1.Budget,v1.capture=REVISION,validate_source,Budget,capture
v1.frozen.inspect_header=inspect_header


def run(output,dependencies=None,clock=time.perf_counter):return v1.run(output,dependencies,clock)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as error:parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
