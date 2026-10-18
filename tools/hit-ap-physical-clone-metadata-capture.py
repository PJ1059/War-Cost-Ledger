"""One fixed dispatcher244 / physical7RF+UW180 clone-input packet.

Only dispatcher129DC30..129DD24 is read as the explicitly authorized
code+table envelope; its actual RF.End is independently looked up, never
inferred from213/244. AP843/RF12/UW48, physical1552 and two contact CALLs
are known before/after gates. Unknown formats stay raw/WITHHELD without
handler/body/window extension. Private24KiB/96IO/2s; no native invocation.
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
FROZEN=ROOT/'tools/hit-clone-complete-unwind-metadata-capture.py'
FROZEN_SHA='d477421aff993f349a75bf208d1e582a502ffae947d102b59c28885232863b59'
if hashlib.sha256(FROZEN.read_bytes()).hexdigest()!=FROZEN_SHA:
    raise ValueError('AP_PHYSICAL_FROZEN_READER_CHANGED')
spec=importlib.util.spec_from_file_location('_ap_physical_fixed_private',FROZEN)
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
v1=previous.v1
_validate=v1.validate_source
REVISION='fixed_AP_dispatcher244_and_physical7_RF_UW_v1'
MAX_BYTES,MAX_READS,MAX_SECONDS=24576,96,2.0
DISPATCH_BEGIN,DISPATCH_BYTES=0x129DC30,244
PHYSICAL_BEGIN,PHYSICAL_END=0x13B0BD0,0x13B11E0
PHYSICAL_RF_INDEX,PHYSICAL_RF_RVA,PHYSICAL_RF_BYTES=68146,0x409AE64,84
PHYSICAL_UW=(0x2511668,180)
AP_BEGIN,AP_BYTES,AP_RF_RVA,AP_UW=0x129C9F0,843,0x408E078,(0x24FC2E0,48)
AP_RF_HEX='f0c929013bcd2901e0c24f02'
MAX_NODES,MAX_NODE=4,128
RO_BEGIN,RO_END=previous.RO_BEGIN,previous.RO_END
ANCHORS={68146:'d00b3b01ac0c3b0168165102',68151:'84103b0162113b01f0165102',
         68152:'62113b01e0113b010c175102'}
SOURCES={
 'A_bin':('dist/hit-code-capture/hit-classification-code-20261011T103354Z-6ac80883.bin','c062eb498383dd15c9e4c22bdc2668eda732db8e737cf8bee11b7f97076408e4',14976),
 'A_json':('dist/hit-code-capture/hit-classification-code-20261011T103354Z-6ac80883.json','ed6c6705e7aeb7eec8d1bcde4cd6ce85c56e4d6c6cf99bb0d48de640dca9cb80',None),
 'B_bin':('dist/hit-owner-prefix-20261012/drain.bin','1776ae47d88e6f4dfa95d4b077709e5693f810e72284bbf05be74b08316a4b8a',4396),
 'B_json':('dist/hit-owner-prefix-20261012/drain.json','ed79e3550b29f021aa5757154ff70b2260288441cf133d4b3a2ac08888de24f6',None),
 'C_bin':('dist/hit-inline-unwind-20261012-117bef92/drain.bin','47486b1672e7f9cebb26e150f4e98657659df7a3976d35f06ec7d3fe8fa35c1a',559),
 'C_json':('dist/hit-inline-unwind-20261012-117bef92/drain.json','17b6da0c864f89950026e8ec1934dce0f436053462b46c392fb3a26777e7c839',None),
 'D_bin':('dist/hit-physical-unwind-20261012-a2417acf/drain.bin','ec10e06d8a697fb4860dc6fae0ff5c225e4976a2e11a675d5e4c01642a94ddbb',69),
 'D_json':('dist/hit-physical-unwind-20261012-a2417acf/drain.json','b68084a5f320f063c25339753d113e74cdbdfd1ab47cb9504870d0ad6f28cc5a',None),
 'contact_bin':('dist/hit-contact-whole-envelope-live-20261013-v1/callsite.bin','4ab318e231a62b61db540c7e8b3d7fa7159d97839edbf9c1a7fa34b963daaafb',17266),
 'contact_json':('dist/hit-contact-whole-envelope-live-20261013-v1/callsite.json','6539a0d848537754a029fa5bb10be580c220d13f4d0ad25dff7f8c778a8c3d7f',None)}


def material(name):
    path,digest,size=SOURCES[name];raw=(ROOT/path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest or size is not None and len(raw)!=size:
        raise ValueError('AP_PHYSICAL_SOURCE_CHANGED: '+name)
    return raw


def sources():
    data={name:material(name) for name in SOURCES}
    metas={name:json.loads(data[name]) for name in SOURCES if name.endswith('_json')}
    for name,m in metas.items():
        if not m.get('complete') or m.get('sha256',m.get('binary_sha256'))!=SOURCES[name[:-5]+'_bin'][1]:
            raise ValueError('AP_PHYSICAL_SOURCE_PACKET_PROFILE: '+name)
    A,B,C,D=data['A_bin'],data['B_bin'],data['C_bin'],data['D_bin']
    ap=A[560:1403];dispatcher=A[5232:5456];physical=B[4364:4396]+A[13440:14960]
    for raw,digest in ((ap,'c4cd5aeee139cffadf9c4e8e83a3b024a92ffff5ac20025f5b4f346b7a5e3662'),
            (dispatcher,'cb467e79ecc8621994b44ca61e28c378c49b141fcc71f0beb917b091503c3f52'),
            (physical,'d1f99ab9a04dd4a2cc852bbd9e2e94f1dff54c392ecf832859d1e22beeb541d0')):
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('AP_PHYSICAL_SOURCE_SLICES')
    csite=next(s for s in metas['C_json']['sites'] if s['name']=='default_delta')
    apnode=csite['unwind_chain'][0]['complete_unwind']
    apuw=C[159:207]
    if (apnode['rva'],apnode['length'],apnode['binary_offset'],apnode['raw_hex'])!=(AP_UW[0],48,159,apuw.hex()):
        raise ValueError('AP_PHYSICAL_AP_FULL_UW_SOURCE')
    row=next(r for r in csite['exception_records'] if r['index']==63753)
    if row['rva']!=AP_RF_RVA or row['raw_hex']!=AP_RF_HEX:raise ValueError('AP_PHYSICAL_AP_RF_SOURCE')
    known=[]
    for node in metas['D_json']['unwind_chain']:
        full=node['complete_unwind'];raw=D[full['binary_offset']:full['binary_offset']+full['length']]
        if raw.hex()!=full['raw_hex']:raise ValueError('AP_PHYSICAL_KNOWN_UW_SOURCE')
        known.append((full['rva'],raw))
    if sorted((rva,len(raw))for rva,raw in known)!=[(0x2511668,28),(0x25116A8,20),(0x251170C,16)]:
        raise ValueError('AP_PHYSICAL_KNOWN_THREE_NOT_FULL_SEVEN')
    for index,pin in ANCHORS.items():
        row=next(r for r in metas['D_json']['exception_records']if r['index']==index)
        if row['raw_hex']!=pin or row['rva']!=PHYSICAL_RF_RVA+(index-PHYSICAL_RF_INDEX)*12:
            raise ValueError('AP_PHYSICAL_KNOWN_RF_ANCHOR_SOURCE')
    pins=[('known_AP843',AP_BEGIN,ap,True),('known_AP_RF',AP_RF_RVA,bytes.fromhex(AP_RF_HEX),False),
          ('known_AP_UW48',AP_UW[0],apuw,False),('known_physical1552',PHYSICAL_BEGIN,physical,True)]
    for pc,target in ((0x13AD7C8,DISPATCH_BEGIN),(0x13AD751,PHYSICAL_BEGIN)):
        raw=data['contact_bin'][pc-0x13AC1F0:pc-0x13AC1F0+5]
        if len(raw)!=5 or raw[0]!=0xE8 or pc+5+struct.unpack_from('<i',raw,1)[0]!=target:
            raise ValueError('AP_PHYSICAL_SOURCE_CONTACT_CALL')
        pins.append(('known_contact_CALL_'+hex(pc),pc,raw,True))
    if PHYSICAL_RF_RVA!=v1.frozen.EXCEPTION_RVA+PHYSICAL_RF_INDEX*12:
        raise ValueError('AP_PHYSICAL_RF_POSITION_PROFILE')
    return pins,dispatcher,known


def validate_source():
    result=_validate();pins,dispatcher,known=sources()
    result.update(AP_physical_fixed_sources={name:{'path':str(ROOT/path),'sha256':digest,'bytes':size}
        for name,(path,digest,size) in SOURCES.items()},
        known_before_after_pins=[{'name':name,'rva':rva,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            for name,rva,raw,_ in pins],dispatcher_known_prefix224_sha256=hashlib.sha256(dispatcher).hexdigest(),
        dispatcher_code213_sha256=hashlib.sha256(dispatcher[:213]).hexdigest(),
        physical_known_three_UW=[{'rva':rva,'length':len(raw),'raw_hex':raw.hex()}for rva,raw in known],
        fixed_reader_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_PIDs_used_as_current_identity=False)
    return result


_base_budget=v1.Budget
class Budget(_base_budget):
    def __init__(self,process,identity,clock=time.perf_counter):
        v1.MAX_BYTES,v1.MAX_READS,v1.MAX_SECONDS=MAX_BYTES,MAX_READS,MAX_SECONDS
        super().__init__(process,identity,clock)


def standard_size(header,reader):
    if header[0]&7!=1:raise ValueError('AP_PHYSICAL_UNWIND_VERSION_NOT_V1')
    return previous.standard_size(header,reader)


def family(raw,records,reader):
    nodes={};issues=[];rowset={tuple(r[k]for k in ('begin','end','unwind_rva'))for r in records}
    for at in sorted({r['unwind_rva']for r in records}):
        off=at-PHYSICAL_UW[0]
        if not 0<=off<=len(raw)-4:issues.append({'rva':at,'reason':'RF_UW_OUTSIDE_FIXED180'});continue
        try:
            size,_=standard_size(raw[off:off+4],reader)
            if off+size>len(raw):raise ValueError('STANDARD_UW_OUTSIDE_FIXED180')
            node=previous.parse_uw(raw[off:off+size],at,reader);nodes[at]=node
        except ValueError as error:issues.append({'rva':at,'reason':str(error)});continue
        if not node['handler_data_format_known']:issues.append({'rva':at,'reason':'HANDLER_DATA_FORMAT_UNKNOWN_NOT_EXTENDED'})
    for row in records:
        current=tuple(row[k]for k in ('begin','end','unwind_rva'));seen=set();frame=None
        while True:
            if current in seen:issues.append({'rva':current[2],'reason':'FAMILY_CHAIN_CYCLE'});break
            seen.add(current)
            node=nodes.get(current[2])
            if node is None:issues.append({'rva':current[2],'reason':'FAMILY_NODE_NOT_COMPLETE_IN_FIXED180'});break
            value=node['frame_register']|node['frame_offset_bytes']
            if frame is not None and value!=frame:issues.append({'rva':current[2],'reason':'CHAIN_FRAME_REGISTER_MISMATCH'});break
            frame=value
            if 'chain_entry'not in node:break
            current=tuple(node['chain_entry'])
            if current not in rowset:issues.append({'rva':node['unwind_rva'],'reason':'CHAIN_TARGET_OUTSIDE_FIXED_SEVEN_RF','target':current});break
    return {'name':'physical','runtime_functions':records,'nodes':list(nodes.values()),'unknown_layouts':issues,
            'all_seven_standard_ancestries_closed':not issues,'runtime_unwind_or_clone_execution_proven':False}


def capture(budget,evidence):
    pins,dispatcher,known=sources();reader=v1.frozen.profile.private_reader()
    reader.IMAGE_SIZE=v1.frozen.IMAGE_SIZE;reader.MAX_FUNCTION_BYTES=v1.frozen.CODE_END-v1.frozen.CODE_BEGIN
    reader.EXCEPTION_RVA,reader.EXCEPTION_SIZE=v1.frozen.EXCEPTION_RVA,v1.frozen.EXCEPTION_SIZE
    reader.TARGET_RVA,reader.TARGET_PIN=DISPATCH_BEGIN,''
    entry={'target_rva':DISPATCH_BEGIN,'exception_records':[],'unwind_nodes':[],'unknown_layouts':[],
           'actual_RF_end_was_not_assumed':True,'complete_standard_ancestry':False}
    evidence.update(capture_purpose='FIXED_DISPATCHER_TABLE_AND_PHYSICAL_RF_UW_PACKAGE',dispatcher=entry,
        code_only=False,metadata_only=False,raw_only=True,AP_new_evidence_reads=0,
        source_PIDs_used_as_current_identity=False,extra_callee_reads=0,heap_reads=0,
        handler_body_read=False,handler_data_extended=False,sibling_code_read=False,
        automatic_handler_or_window_extension=False,logical_function_complete=False,
        clone_execution_proven=False,runtime_unwind_proven=False,classification_ready=False,contract_ready=False)
    pin_bytes=sum(len(raw)for _,_,raw,_ in pins)
    post_bytes=pin_bytes+PHYSICAL_RF_BYTES+PHYSICAL_UW[1]+DISPATCH_BYTES+12+MAX_NODES*MAX_NODE+4120
    post_calls=len(pins)+2+1+1+MAX_NODES+4
    def reserve(size=0,calls=0):
        budget.require_capacity(post_bytes+size,post_calls+calls)
        if budget.query_calls+post_calls+calls>MAX_READS:raise ValueError('AP_PHYSICAL_POST_QUERY_RESERVATION_BUDGET')
    def pin_gates():
        for name,rva,raw,exe in pins:
            if budget.read_module(rva,len(raw),name,exe)!=raw:raise ValueError('AP_PHYSICAL_FRESH_SOURCE_PIN_CHANGED: '+name)
    def physical_rf():
        raw=budget.read_module(PHYSICAL_RF_RVA,PHYSICAL_RF_BYTES,'exception_record');records=[]
        for i in range(7):
            begin,end,uw=struct.unpack_from('<III',raw,i*12);index=PHYSICAL_RF_INDEX+i
            reader.validate_runtime_entry(begin,end,uw);piece=raw[i*12:i*12+12].hex()
            if not PHYSICAL_BEGIN<=begin<end<=PHYSICAL_END or records and records[-1]['end']>begin:
                raise ValueError('AP_PHYSICAL_SEVEN_RF_SCOPE_OR_ORDER')
            if index in ANCHORS and piece!=ANCHORS[index]:raise ValueError('AP_PHYSICAL_FRESH_RF_ANCHOR_CHANGED')
            records.append({'index':index,'rva':PHYSICAL_RF_RVA+i*12,'begin':begin,'end':end,'unwind_rva':uw,'raw_hex':piece})
        return raw,records
    def physical_uw():
        raw=budget.read_module(*PHYSICAL_UW,'unwind_metadata')
        for at,pin in known:
            off=at-PHYSICAL_UW[0]
            if raw[off:off+len(pin)]!=pin:raise ValueError('AP_PHYSICAL_FRESH_KNOWN_THREE_UW_CHANGED')
        return raw
    def fixed_dispatcher():
        raw=budget.read_module(DISPATCH_BEGIN,DISPATCH_BYTES,'fixed_dispatcher244',True)
        if raw[:224]!=dispatcher:raise ValueError('AP_PHYSICAL_DISPATCHER_KNOWN224_CHANGED')
        return raw
    def checked(rva,size):
        if not v1.frozen.EXCEPTION_RVA<=rva<rva+size<=v1.frozen.EXCEPTION_RVA+v1.frozen.EXCEPTION_SIZE:
            raise ValueError('AP_PHYSICAL_LOOKUP_OUTSIDE_FIXED_PDATA')
        reserve(size,1);return budget.read_module(rva,size,'exception_record')
    reader.checked_metadata_read=lambda b,rva,size:checked(rva,size)
    reserve(pin_bytes+PHYSICAL_RF_BYTES+PHYSICAL_UW[1]+DISPATCH_BYTES,len(pins)+3)
    pin_gates();rf_raw,records=physical_rf();uw_raw=physical_uw()
    evidence['physical']=family(uw_raw,records,reader)
    body=fixed_dispatcher()
    begin,end=reader.find_function(budget,entry['exception_records']);selected=entry['exception_records'][-1]
    if not v1.frozen.CODE_BEGIN<=begin<=DISPATCH_BEGIN<end<=v1.frozen.CODE_END:
        raise ValueError('AP_PHYSICAL_DISPATCHER_RF_OUTSIDE_CODE')
    entry.update(function_begin=begin,function_end=end,selected_record=selected)
    current=(begin,end,selected['unwind_rva']);seen=set();raw_nodes=[];frame=None
    for level in range(MAX_NODES):
        reader.validate_runtime_entry(*current)
        if current in seen:entry['unknown_layouts'].append({'rva':current[2],'reason':'CHAIN_CYCLE'});break
        seen.add(current);at=current[2]
        if not RO_BEGIN<=at<at+4<=RO_END:
            entry['unknown_layouts'].append({'rva':at,'reason':'UW_OUTSIDE_KNOWN_RODATA'});break
        reserve(4,1);header=budget.read_module(at,4,'unwind_metadata')
        try:
            size,flags=standard_size(header,reader)
            if size>MAX_NODE or at+size>RO_END:raise ValueError('COMPLETE_NODE_OVER_128_OR_RODATA')
        except ValueError as error:
            entry['unknown_layouts'].append({'rva':at,'reason':str(error),'header_hex':header.hex()})
            raw_nodes.append((at,header));break
        reserve(size,1);raw=budget.read_module(at,size,'unwind_metadata')
        if raw[:4]!=header:raise ValueError('AP_PHYSICAL_DISPATCHER_UW_HEADER_CHANGED')
        node=previous.parse_uw(raw,at,reader);node.update(begin=current[0],end=current[1])
        entry['unwind_nodes'].append(node);raw_nodes.append((at,raw))
        if frame is not None and header[3]!=frame:
            entry['unknown_layouts'].append({'rva':at,'reason':'CHAIN_FRAME_REGISTER_MISMATCH'});break
        frame=header[3]
        if flags&3:entry['unknown_layouts'].append({'rva':at,'reason':'HANDLER_DATA_FORMAT_UNKNOWN_NOT_EXTENDED'})
        if not flags&4:entry['complete_standard_ancestry']=True;break
        if level+1==MAX_NODES:
            entry['unknown_layouts'].append({'rva':at,'reason':'CHAIN_REQUIRES_MORE_THAN_FOUR_NODES'});break
        current=tuple(node['chain_entry'])
        if not v1.frozen.CODE_BEGIN<=current[0]<current[1]<=v1.frozen.CODE_END:
            entry['unknown_layouts'].append({'rva':at,'reason':'CHAIN_RF_OUTSIDE_CODE_SECTION'});break
    reserve()
    if fixed_dispatcher()!=body:raise ValueError('AP_PHYSICAL_DISPATCHER244_CHANGED_DURING_CAPTURE')
    if budget.read_module(selected['rva'],12,'exception_record').hex()!=selected['raw_hex']:
        raise ValueError('AP_PHYSICAL_DISPATCHER_SELECTED_RF_CHANGED')
    for at,raw in raw_nodes:
        if budget.read_module(at,len(raw),'unwind_metadata')!=raw:raise ValueError('AP_PHYSICAL_DISPATCHER_FULL_UW_CHANGED')
    after_rf,_=physical_rf();after_uw=physical_uw()
    if after_rf!=rf_raw or after_uw!=uw_raw:raise ValueError('AP_PHYSICAL_FIXED_WINDOWS_CHANGED_DURING_CAPTURE')
    pin_gates()
    chunks=[('dispatcher_fixed244',DISPATCH_BEGIN,body),('physical_RF7',PHYSICAL_RF_RVA,rf_raw),
            ('physical_UW180',PHYSICAL_UW[0],uw_raw),('dispatcher_actual_RF',selected['rva'],bytes.fromhex(selected['raw_hex']))]
    chunks += [('dispatcher_UW_node_'+str(i),at,raw)for i,(at,raw)in enumerate(raw_nodes)]
    binary=b'';ranges=[]
    for name,rva,raw in chunks:
        ranges.append({'name':name,'module':'game','rva':rva,'length':len(raw),'binary_offset':len(binary)})
        binary+=raw
    layouts=entry['complete_standard_ancestry']and not entry['unknown_layouts']and evidence['physical']['all_seven_standard_ancestries_closed']
    evidence.update(ranges=ranges,code_bytes=DISPATCH_BYTES,metadata_bytes=len(binary)-DISPATCH_BYTES,
        dispatcher_fixed244_before_after_match=True,dispatcher_known224_before_after_match=True,
        dispatcher_selected_RF_and_full_UW_before_after_match=True,physical_RF_UW_windows_before_after_match=True,
        all_known_AP_physical_contact_pins_before_after_match=True,AP_existing_complete_UW48_only_verified=True,
        physical_known_three_not_assumed_full_family=True,dispatcher_unknown_tail_bytes=20,
        standard_layouts_complete=bool(layouts),metadata_copy_readiness='STANDARD_METADATA_CAPTURED'if layouts else'WITHHELD_UNKNOWN_LAYOUT',
        fixed_dispatcher_envelope_is_not_assumed_RF_end=True,all_function_bodies_complete=False,
        boundary_kind='fixed_metadata_and_dispatcher_table_inputs_not_clone_or_unwind_execution')
    return binary


v1.REVISION,v1.validate_source,v1.Budget,v1.capture=REVISION,validate_source,Budget,capture
def run(output,dependencies=None,clock=time.perf_counter):return v1.run(output,dependencies,clock)
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (OSError,ValueError)as error:parser.exit(1,str(error)+'\n')
if __name__=='__main__':main()
