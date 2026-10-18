"""One fixed contact primary UW24B profile: known20B plus opaque4B.

Reuse the frozen source/PE/CALL/Title-or-Ship/context/PID/module and
known contact declaration/UW-chain pre/post gates,24KiB/32IO/2s.
No Game code/handler execution or modification, callee/body/heap reads,
format-based extension, or assumption that the next UW is handler-data end.
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
    raise ValueError('PRIMARY_PREFIX_FROZEN_WRAPPER_CHANGED')
spec=importlib.util.spec_from_file_location('_primary_prefix_private_source',WRAPPER)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
v1=parent.v1
REVISION='contact_primary_fixed_UW24_known20_opaque4_v1'
BEGIN,END=0x25114C0,0x25114D8
KNOWN_HEX='1933060022f85d021901d10404f00250a0441002'
KNOWN=bytes.fromhex(KNOWN_HEX)
SOURCE_BIN=ROOT/'dist/hit-inline-unwind-20261012-117bef92/drain.bin'
SOURCE_BIN_SHA='47486b1672e7f9cebb26e150f4e98657659df7a3976d35f06ec7d3fe8fa35c1a'


def validate_source():
    source=parent.validate_source()
    meta=json.loads(parent.material(parent.UNWIND_SOURCE,parent.UNWIND_SHA))
    site=next(row for row in meta['sites'] if row['name']=='contact_begin')
    primary=site['unwind_chain'][-1];complete=primary['complete_unwind']
    raw=parent.material(SOURCE_BIN,SOURCE_BIN_SHA)
    if (tuple(primary[k] for k in ('begin','end','unwind_rva'))!=(0x13AC1F0,0x13AC258,BEGIN)
            or complete['rva']!=BEGIN or complete['binary_offset']!=139 or complete['length']!=20
            or complete['raw_hex']!=KNOWN_HEX or raw[139:159]!=KNOWN
            or primary['handler_rva']!=0x21044A0 or struct.unpack_from('<I',KNOWN,16)[0]!=0x21044A0
            or primary['header']['raw_hex']!='19330600'
            or site['unwind_chain'][-2]['unwind_rva']!=END):
        raise ValueError('PRIMARY_PREFIX_KNOWN20_SOURCE_PROFILE')
    source.update(primary_known20_source={'json_path':str(parent.UNWIND_SOURCE),
        'json_sha256':parent.UNWIND_SHA,'binary_path':str(SOURCE_BIN),'binary_sha256':SOURCE_BIN_SHA,
        'binary_offset':139,'rva':BEGIN,'length':20,'hex':KNOWN_HEX,
        'handler_rva':0x21044A0,'next_saved_unwind_rva':END,
        'next_unwind_does_not_prove_handler_data_length':True},
        requested_fixed_profile={'rva':BEGIN,'length':24,'known_bytes':20,'new_opaque_bytes':4},
        primary_prefix_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return source


def capture(budget,evidence):
    pins=parent.layout_source();expected=parent.unwind_source()
    reader=v1.frozen.profile.private_reader();reader.IMAGE_SIZE=v1.frozen.IMAGE_SIZE
    reader.MAX_FUNCTION_BYTES=v1.frozen.CODE_END-v1.frozen.CODE_BEGIN
    known={(node[key]['rva'],len(bytes.fromhex(node[key]['raw_hex']))):bytes.fromhex(node[key]['raw_hex'])
        for node in expected for key in ('header','chain_entry') if key in node}
    def metadata(rva,size):
        if (rva,size) not in known:raise ValueError('PRIMARY_PREFIX_UW_OUTSIDE_KNOWN_CHAIN')
        raw=budget.read_module(rva,size,'unwind_metadata')
        if raw!=known[(rva,size)]:raise ValueError('PRIMARY_PREFIX_FRESH_UW_CHANGED')
        return raw
    def snapshot():
        fresh=(budget.read_module(parent.PARENT_RVA,104,'known_parent104_pin',True),
               budget.read_module(parent.FIELD_RVA,150,'known_ESI_count_row_pin',True))
        if fresh!=pins:raise ValueError('PRIMARY_PREFIX_FRESH_LAYOUT_PIN_CHANGED')
        record=budget.read_module(parent.RECORD_RVA,12,'exception_record')
        if record.hex()!=parent.RECORD_HEX:raise ValueError('PRIMARY_PREFIX_FRESH_RECORD_CHANGED')
        nodes=[];reader.unwind_ancestry(parent.DECLARATION,metadata,nodes)
        if nodes!=expected:raise ValueError('PRIMARY_PREFIX_FRESH_CHAIN_CHANGED')
        return {'record_hex':record.hex(),'unwind_chain':nodes}
    evidence.update(capture_purpose='FIXED_PRIMARY_UW_KNOWN20_AND_OPAQUE4_ONLY',target_rva=BEGIN,
        code_only=False,metadata_only=True,raw_only=True,new_unknown_code_bytes=0,new_opaque_bytes=4,
        handler_body_read=False,complete_handler_data=False,handler_data_format_proven=False,
        structured_scope_table_decoded=False,heap_reads=0,extra_callee_reads=0,pdata_search_performed=False,
        logical_function_complete=False,normal_CFG_closed=False,classification_ready=False,contract_ready=False)
    # Two10IO snapshots,2 fixed reads,and original4 post gates:26 remainingIO.
    budget.require_capacity(254*2+12*2+52*2+24*2+4120,26)
    if budget.query_calls+26>v1.MAX_READS:raise ValueError('PRIMARY_PREFIX_POST_QUERY_RESERVATION_BUDGET')
    before=snapshot()
    budget.require_capacity(24*2+254+12+52+4120,16)
    if budget.query_calls+16>v1.MAX_READS:raise ValueError('PRIMARY_PREFIX_POST_QUERY_RESERVATION_BUDGET')
    raw=budget.read_module(BEGIN,24,'fixed_primary_unwind_prefix24')
    if raw[:20]!=KNOWN:raise ValueError('PRIMARY_PREFIX_FRESH_KNOWN20_CHANGED')
    after=budget.read_module(BEGIN,24,'fixed_primary_unwind_prefix24')
    if after[:20]!=KNOWN:raise ValueError('PRIMARY_PREFIX_AFTER_KNOWN20_CHANGED')
    if after!=raw:raise ValueError('PRIMARY_PREFIX_OPAQUE4_CHANGED_DURING_CAPTURE')
    after_meta=snapshot()
    if after_meta!=before:raise ValueError('PRIMARY_PREFIX_METADATA_CHANGED_DURING_CAPTURE')
    evidence.update(primary_prefix_before_after_match=True,known20_before_after_match=True,
        opaque4_hex=raw[20:].hex(),fresh_layout_pins_before_after_match=True,
        fixed_record_verified_before_after=True,fresh_unwind_matches_saved_source=True,
        unwind_chain=before['unwind_chain'],fixed_record_before=before['record_hex'],
        fixed_record_after=after_meta['record_hex'],
        ranges=[{'name':'contact_primary_known20_opaque4_prefix','module':'game','rva':BEGIN,
                 'length':24,'binary_offset':0}],code_bytes=0,metadata_bytes=24,
        handler_data_length_proven=False,next_unwind_does_not_prove_handler_data_length=True,
        boundary_kind='fixed24B_raw_prefix_not_complete_handler_contract',
        native_called=False,native_written=False)
    return raw


v1.REVISION,v1.validate_source,v1.capture=REVISION,validate_source,capture


def run(output,dependencies=None,clock=time.perf_counter):return v1.run(output,dependencies,clock)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as error:parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
