"""Only [13AF1BE,13AF23E)128B twice, without assuming queue consumption.

Fresh parent104 and known150B ESI/count/row code pins, fixed .pdata68131
and its four saved UW headers/chain entries before/after. Original loaded
PE/CALL/Title-or-Ship/context/PID/module gates share24KiB/32RPM-query/2s.
No new predecessor/callee/handler body, heap/reference, invocation, write,
retry or count-proportional work. Only the unknown128B is saved.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT/'tools/hit-world-update-contact-callsite-capture.py'
WRAPPER_SHA = 'a46b04f2851687fd719a7162f1ecf3bb183e833f2b07f0df6f4d25280ce6ec67'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest() != WRAPPER_SHA:
    raise ValueError('CONSUME_TAIL_FROZEN_WRAPPER_CHANGED')
spec = importlib.util.spec_from_file_location('_consume_tail_private_callsite', WRAPPER)
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)
REVISION = 'contact_fixed_consume_tail128_readonly_v1'
TAIL_BEGIN, TAIL_END = 0x13AF1BE, 0x13AF23E
TAIL_BYTES = TAIL_END-TAIL_BEGIN
RECORD_INDEX, RECORD_RVA = 68131, 0x409ADB0
RECORD_HEX = 'dbc23a01d1fc3a0114155102'
DECLARATION = (0x13AC2DB, 0x13AFCD1, 0x2511514)
PARENT_RVA, FIELD_RVA = 0x13AC1F0, 0x13AC2C9
UNWIND_SOURCE = ROOT/'dist/hit-inline-unwind-20261012-117bef92/drain.json'
UNWIND_SHA = '17b6da0c864f89950026e8ec1934dce0f436053462b46c392fb3a26777e7c839'
PARENT_SOURCE = ROOT/'dist/hit-contact-parent-fragment-live-20261013-v1/parent104.bin'
PARENT_SHA = '407a416a17c2b5153b9f81e0261d63e04ac67b05ee4eb557bc493342021ff118'
GAP_SOURCE = ROOT/'dist/hit-contact-parent-gap-live-20261013-v1/parent-gap168.bin'
GAP_SHA = 'bcb1016a4a899f2132cda5c6ca72629e38a02c64310a63200d320371eb11b151'
OWNER_SOURCE = ROOT/'dist/hit-owner-prefix-20261012/drain.bin'
OWNER_SHA = '1776ae47d88e6f4dfa95d4b077709e5693f810e72284bbf05be74b08316a4b8a'


def material(path, digest, length=None):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest or (length is not None and len(raw) != length):
        raise ValueError('CONSUME_TAIL_FIXED_SOURCE_CHANGED: '+path.name)
    return raw


def layout_source():
    parent = material(PARENT_SOURCE, PARENT_SHA, 104)
    gap = material(GAP_SOURCE, GAP_SHA, 168)
    owner = material(OWNER_SOURCE, OWNER_SHA, 4396)
    # All150 bytes already exist: gap113..168 + owner-body0..95.
    fields = gap[113:]+owner[12:107]
    if (len(fields) != 150 or fields[:2].hex() != '33f6'
            or parent[62:65].hex() != '4c8bf9' or parent[87:91].hex() != '80792800'
            or fields[109:116].hex() != '4139b740700e00'
            or fields[131:135].hex() != '48c1e305'
            or fields[142:150].hex() != '428b843b44700e00'):
        raise ValueError('CONSUME_TAIL_EXISTING_LAYOUT_PINS_CHANGED')
    return parent, fields


def unwind_source():
    meta = json.loads(material(UNWIND_SOURCE, UNWIND_SHA))
    if not meta.get('complete') or meta.get('fingerprint') != v1.frozen.profile.FINGERPRINT:
        raise ValueError('CONSUME_TAIL_UNWIND_SOURCE_PROFILE')
    site = next(row for row in meta['sites'] if row['name']=='contact_begin')
    record = next(row for row in site['exception_records'] if row['index']==RECORD_INDEX)
    nodes = site['unwind_chain']
    if (record['rva'] != RECORD_RVA or record['raw_hex'] != RECORD_HEX
            or tuple(record[k] for k in ('begin','end','unwind_rva')) != DECLARATION
            or RECORD_RVA != v1.frozen.EXCEPTION_RVA+RECORD_INDEX*12
            or struct.unpack('<III', bytes.fromhex(RECORD_HEX)) != DECLARATION
            or len(nodes) != 4
            or tuple(nodes[0][k] for k in ('begin','end','unwind_rva')) != DECLARATION
            or tuple(nodes[-1][k] for k in ('begin','end','unwind_rva')) != (0x13AC1F0,0x13AC258,0x25114C0)
            or not DECLARATION[0] <= TAIL_BEGIN < TAIL_END <= DECLARATION[1]
            or TAIL_BYTES != 128):
        raise ValueError('CONSUME_TAIL_FIXED_DECLARATION_PROFILE')
    return [{k:node[k] for k in ('begin','end','unwind_rva','header','chain_entry') if k in node}
            for node in nodes]


_original_source = v1.validate_source


def validate_source():
    source = _original_source()
    parent, fields = layout_source()
    nodes = unwind_source()
    source.update(consume_tail_source={'unwind_metadata_path':str(UNWIND_SOURCE.resolve()),
        'unwind_metadata_sha256':UNWIND_SHA, 'record_index':RECORD_INDEX,
        'record_rva':RECORD_RVA, 'record_hex':RECORD_HEX, 'unwind_chain':nodes,
        'parent104_sha256':PARENT_SHA, 'gap168_sha256':GAP_SHA, 'owner_prefix_sha256':OWNER_SHA,
        'fresh_known_code_pins':[{'rva':PARENT_RVA,'bytes':len(parent),'sha256':hashlib.sha256(parent).hexdigest()},
            {'rva':FIELD_RVA,'bytes':len(fields),'sha256':hashlib.sha256(fields).hexdigest()}],
        'unknown_tail_rva':TAIL_BEGIN,'unknown_tail_bytes':TAIL_BYTES,
        'count_clear_or_consume_timing_proven':False,'runtime_object_lifetime_proven':False},
        consume_tail_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return source


def capture(budget, evidence):
    parent, fields = layout_source()
    expected = unwind_source()
    reader = v1.frozen.profile.private_reader()
    reader.IMAGE_SIZE = v1.frozen.IMAGE_SIZE
    reader.MAX_FUNCTION_BYTES = v1.frozen.CODE_END-v1.frozen.CODE_BEGIN
    known_metadata = {}
    for node in expected:
        for key in ('header','chain_entry'):
            if key in node:
                item=node[key];raw=bytes.fromhex(item['raw_hex'])
                known_metadata[(item['rva'],len(raw))]=raw
    def metadata(rva,size):
        if (rva,size) not in known_metadata:
            raise ValueError('CONSUME_TAIL_UW_READ_OUTSIDE_SAVED_CHAIN')
        raw=budget.read_module(rva,size,'unwind_metadata')
        if raw != known_metadata[(rva,size)]:
            raise ValueError('CONSUME_TAIL_FRESH_UW_CHANGED')
        return raw
    def snapshot():
        p=budget.read_module(PARENT_RVA,104,'known_parent104_pin',True)
        f=budget.read_module(FIELD_RVA,150,'known_ESI_count_row_pin',True)
        if p != parent or f != fields:
            raise ValueError('CONSUME_TAIL_FRESH_LAYOUT_PIN_CHANGED')
        record=budget.read_module(RECORD_RVA,12,'exception_record')
        if record.hex() != RECORD_HEX:
            raise ValueError('CONSUME_TAIL_FRESH_RECORD_CHANGED')
        nodes=[]
        reader.unwind_ancestry(DECLARATION,metadata,nodes)
        if nodes != expected:
            raise ValueError('CONSUME_TAIL_FRESH_CHAIN_CHANGED')
        return {'record_hex':record.hex(),'unwind_chain':nodes}
    evidence.update(capture_purpose='FIXED128B_CONTACT_LOOP_TAIL_AND_DIRECT_SUCCESSOR_ONLY',
        target_rva=TAIL_BEGIN, declared_begin=DECLARATION[0],declared_end=DECLARATION[1],
        code_only=True,pdata_search_performed=False,new_unknown_code_bytes=128,
        handler_scope_read=False,extra_callee_reads=0,heap_reads=0,row_refs_followed=0,
        count_clear_or_consume_timing_proven=False,runtime_object_lifetime_proven=False,
        normal_CFG_closed=False,logical_function_complete=False,
        classification_ready=False,contract_ready=False)
    # 2 source-code reads + record + 7 UW IO on each side, 2 unknown reads,
    # plus original post header/CALL/state8+4 =26 remainingIO/5012B.
    budget.require_capacity(254*2+12*2+52*2+128*2+4120,26)
    if budget.query_calls+26 > v1.MAX_READS:
        raise ValueError('CONSUME_TAIL_POST_QUERY_RESERVATION_BUDGET')
    before=snapshot()
    # Immediately reserve both unknown reads and all14 remaining post gates.
    budget.require_capacity(128*2+254+12+52+4120,16)
    if budget.query_calls+16 > v1.MAX_READS:
        raise ValueError('CONSUME_TAIL_POST_QUERY_RESERVATION_BUDGET')
    raw=budget.read_module(TAIL_BEGIN,128,'fixed_consume_tail128',True)
    after=budget.read_module(TAIL_BEGIN,128,'fixed_consume_tail128',True)
    if after != raw:
        raise ValueError('CONSUME_TAIL_WINDOW_CHANGED_DURING_CAPTURE')
    after_meta=snapshot()
    if after_meta != before:
        raise ValueError('CONSUME_TAIL_METADATA_CHANGED_DURING_CAPTURE')
    evidence.update(fresh_layout_pins_before_after_match=True,
        fixed_record_verified_before_after=True,fresh_unwind_matches_saved_source=True,
        unwind_chain=before['unwind_chain'], fixed_record_before=before['record_hex'],
        fixed_record_after=after_meta['record_hex'],tail_before_after_match=True,
        ranges=[{'name':'contact_consume_candidate_tail128','module':'game','rva':TAIL_BEGIN,
                 'length':128,'binary_offset':0}],code_bytes=128,
        declared_code_complete=False,boundary_kind='fixed128B_tail_window_not_full_successor_or_function',
        offline_decoding_required=True)
    return raw


v1.REVISION,v1.validate_source,v1.capture=REVISION,validate_source,capture


def run(output,dependencies=None,clock=time.perf_counter):
    return v1.run(output,dependencies,clock)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as error:parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
