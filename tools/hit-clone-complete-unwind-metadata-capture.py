"""Fixed World/contact RF+UW packages and actual frame-entry complete UW.

World UW224B/contact UW256B and two9RF108B windows twice, byte-match
source-derived RF fields. Frame4EE6C0 only actualRF lookup and<=4 complete
standardUW nodes, each<=128B; no assumed4EE703 end or sibling/body/callee.
Four existing code PINs before/after, originalPE/state/context/PID/modules.
Private96IO/24KiB/2s; opaque handler formats remain unknown without extension.
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
WRAPPER=ROOT/'tools/hit-contact-handler-common-declaration-capture.py'
WRAPPER_SHA='938931d690b550cd0dd8481d9b10e23c9d2bd084a7e6d24dce6ff8715e6e22e1'
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest()!=WRAPPER_SHA:
    raise ValueError('CLONE_UW_FROZEN_WRAPPER_CHANGED')
spec=importlib.util.spec_from_file_location('_clone_uw_private_source',WRAPPER)
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
v1=parent.v1
REVISION='clone_fixed_world_contact_RF_UW_and_actual_frame_UW_v1'
FRAME=0x4EE6C0
WORLD_UW=(0x24A6DE8,224)
CONTACT_UW=(0x25114C0,256)
WORLD_RF_INDEX,CONTACT_RF_INDEX=43769,68128
RF_BYTES=9*12
RO_BEGIN,RO_END=parent.parent.RO_BEGIN,parent.parent.RO_END
MAX_NODE,MAX_FRAME_NODES=128,4
SOURCES={
 'world_meta':('dist/hit-world-update-logical-metadata-live-20261013-v1/callsite.json',
  '4a69e090cfdb1c802ee15d0b48266124039ee957f7fa7cdaa3a9963d4c59f13a'),
 'contact_meta':('dist/hit-inline-unwind-20261012-117bef92/drain.json',
  '17b6da0c864f89950026e8ec1934dce0f436053462b46c392fb3a26777e7c839'),
 'contact_exit':('dist/hit-contact-exit-metadata-live-20261013-v1/callsite.json',
  'b53789a23c1dd2713c9d05565ea052d927f83f4dbe1291d26fdb353a62ad19d6'),
 'frame':('dist/hit-game-plugin-table-update-live-20261013-v1/plugin-table-update.bin',
  '03b3fd1cd3459fb3c3d6eb71e47a806dd2376ccd7f36dbc1f60f606bd446f546'),
 'world_root':('dist/hit-world-update-root-prefix-live-20261013-v1/callsite.bin',
  '279bbfda6d08a0386022bbc5c7af02ab56f2ff14d15d3074d728d1abb120be89'),
 'contact_root':('dist/hit-contact-parent-fragment-live-20261013-v1/parent104.bin',
  '407a416a17c2b5153b9f81e0261d63e04ac67b05ee4eb557bc493342021ff118'),
 'common':('dist/hit-contact-handler-common-declaration-live-20261013-v1/callsite.bin',
  '2382792da1394fd60d08b8cdc7f97d4a39740c51b1d6907769de838b9590ec31')}


def material(name):
    path,digest=SOURCES[name];raw=(ROOT/path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('CLONE_UW_SOURCE_CHANGED: '+name)
    return raw


def rf(node,index,origin):
    begin,end,uw=(node[k] for k in ('begin','end','unwind_rva'))
    return {'index':index,'rva':v1.frozen.EXCEPTION_RVA+index*12,'begin':begin,'end':end,
            'unwind_rva':uw,'raw_hex':struct.pack('<III',begin,end,uw).hex(),'origin':origin}


def sources():
    world=json.loads(material('world_meta'));contact=json.loads(material('contact_meta'))
    exit_meta=json.loads(material('contact_exit'))
    if any(not m.get('complete') or m.get('fingerprint')!=v1.frozen.profile.FINGERPRINT
           for m in (world,contact,exit_meta)):raise ValueError('CLONE_UW_SOURCE_METADATA_PROFILE')
    csite=next(s for s in contact['sites'] if s['name']=='contact_begin')
    wr=[rf(n,WORLD_RF_INDEX+i,'embedded_chain_RF_fields_position_requires_fresh_check')
        for i,n in enumerate(sorted(world['unwind_chain'][1:],key=lambda n:n['begin']))]
    wr += [rf(next(n for n in world['exception_records'] if n['index']==i),i,'actual_saved_pdata_record')
           for i in range(43772,43778)]
    cr=[rf(n,CONTACT_RF_INDEX+i,'embedded_chain_RF_fields_position_requires_fresh_check')
        for i,n in enumerate(sorted(csite['unwind_chain'][1:],key=lambda n:n['begin']))]
    primary=next(n for n in csite['exception_records'] if n['index']==CONTACT_RF_INDEX)
    if cr[0]['raw_hex']!=primary['raw_hex']:raise ValueError('CLONE_UW_CONTACT_PRIMARY_RF_SOURCE')
    cr[0]['origin']='actual_saved_pdata_record'
    cr += [rf(next(n for n in exit_meta['exception_records'] if n['index']==i),i,'actual_saved_pdata_record')
           for i in range(68131,68137)]
    if len(wr)!=9 or len(cr)!=9:raise ValueError('CLONE_UW_FIXED_NINE_RF_SOURCE')
    pins=[('frame67',FRAME,material('frame')[200:267]),('world_root84',0xAB5000,material('world_root')),
          ('contact_root104',0x13AC1F0,material('contact_root')),('common91',0x21044C0,material('common'))]
    if [len(p[2]) for p in pins]!=[67,84,104,91]:raise ValueError('CLONE_UW_FOUR_CODE_PINS_PROFILE')
    known=[]
    for n in world['unwind_chain']+[node for o in world['ownership'] for node in o['unwind_chain']]:
        for key in ('header','chain_entry'):
            if key in n:known.append(('world',n[key]['rva'],bytes.fromhex(n[key]['raw_hex'])))
    for n in csite['unwind_chain']:
        full=n['complete_unwind'];known.append(('contact',full['rva'],bytes.fromhex(full['raw_hex'])))
    for n in [node for o in exit_meta['ownership'] for node in o['unwind_chain']]:
        for key in ('header','chain_entry'):
            if key in n:known.append(('contact',n[key]['rva'],bytes.fromhex(n[key]['raw_hex'])))
    if sorted(len(n['complete_unwind']['raw_hex'])//2 for n in csite['unwind_chain'])!=[20,20,40,48]:
        raise ValueError('CLONE_UW_CONTACT_FULL_CHAIN_SOURCE')
    known.append(('contact',0x25114C0,parent.parent.source_pins()[0]))
    return wr,cr,pins,known


def validate_source():
    source=parent.validate_source();wr,cr,pins,known=sources()
    source.update(metadata_package_sources={name:{'path':str(ROOT/path),'sha256':digest}
        for name,(path,digest) in SOURCES.items()},
        expected_RF_families={'world':wr,'contact':cr},
        fixed_UW_windows={'world':{'rva':WORLD_UW[0],'length':WORLD_UW[1]},
                          'contact':{'rva':CONTACT_UW[0],'length':CONTACT_UW[1]}},
        known_code_pins=[{'name':name,'rva':rva,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                         for name,rva,raw in pins],
        metadata_package_wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return source


def standard_size(header,reader):
    flags=reader.check_unwind_header(header)
    return 4+2*((header[2]+1)&~1)+(12 if flags&4 else 4 if flags&3 else 0),flags


def parse_uw(raw,rva,reader):
    size,flags=standard_size(raw[:4],reader)
    if len(raw)<size:raise ValueError('CLONE_UW_STANDARD_RECORD_TRUNCATED')
    base=4+2*((raw[2]+1)&~1)
    node={'unwind_rva':rva,'version':raw[0]&7,'flags':flags,'prolog_size':raw[1],
        'slot_count':raw[2],'frame_register':raw[3]&15,'frame_offset_bytes':raw[3]&0xF0,
        'standard_length':size,'raw_hex':raw.hex(),'code_slots_hex':raw[4:base].hex(),
        'handler_data_format_known':not bool(flags&3)}
    if flags&4:
        node['chain_entry']=list(struct.unpack_from('<III',raw,base))
    elif flags&3:
        handler=struct.unpack_from('<I',raw,base)[0];node['handler_rva']=handler
        node['handler_data_rva']=rva+size
        if len(raw)>=size+4:
            prefix=raw[size:size+4];node['opaque_handler_prefix4_hex']=prefix.hex()
            value=struct.unpack('<I',prefix)[0]
            node['known_GS_4B_branch']=handler==0x21044A0 and not value&4
            node['handler_data_format_known']=node['known_GS_4B_branch']
            if node['known_GS_4B_branch']:node['GS_cookie_offset']=struct.unpack('<i',prefix)[0]&~7
    return node


def parse_family(name,raw,start,records,reader):
    nodes=[];unknown_layout=[];known_records={tuple(row[k] for k in ('begin','end','unwind_rva')) for row in records}
    for at in sorted({r['unwind_rva'] for r in records}):
        offset=at-start
        if not 0<=offset<len(raw)-3:
            unknown_layout.append({'rva':at,'reason':'RF_UNWIND_OUTSIDE_FIXED_WINDOW'});continue
        try:size,flags=standard_size(raw[offset:offset+4],reader)
        except ValueError as error:
            unknown_layout.append({'rva':at,'reason':str(error),'header_hex':raw[offset:offset+4].hex()});continue
        if offset+size>len(raw):
            unknown_layout.append({'rva':at,'reason':'STANDARD_UW_EXCEEDS_FIXED_WINDOW',
                                   'standard_length':size,'header_hex':raw[offset:offset+4].hex()});continue
        length=size+(4 if flags&3 and offset+size+4<=len(raw) else 0)
        node=parse_uw(raw[offset:offset+length],at,reader)
        if 'chain_entry' in node:node['chain_target_is_known_family_RF']=tuple(node['chain_entry']) in known_records
        nodes.append(node)
    return {'name':name,'nodes':nodes,
        'unknown_layouts':unknown_layout,
        'unknown_handler_formats':[n['unwind_rva'] for n in nodes if not n['handler_data_format_known']],
        'unresolved_chain_targets':[n['unwind_rva'] for n in nodes
            if 'chain_entry' in n and not n['chain_target_is_known_family_RF']],
        'runtime_unwind_or_clone_execution_proven':False}


def capture(budget,evidence):
    wr,cr,pins,known=sources();reader=v1.frozen.profile.private_reader()
    reader.IMAGE_SIZE=v1.frozen.IMAGE_SIZE;reader.MAX_FUNCTION_BYTES=v1.frozen.CODE_END-v1.frozen.CODE_BEGIN
    reader.EXCEPTION_RVA,reader.EXCEPTION_SIZE=v1.frozen.EXCEPTION_RVA,v1.frozen.EXCEPTION_SIZE
    reader.TARGET_RVA,reader.TARGET_PIN=FRAME,''
    frame={'target_rva':FRAME,'exception_records':[],'unwind_nodes':[]}
    evidence.update(capture_purpose='FIXED_FULL_RF_UW_METADATA_PACKAGE_ONLY',code_only=False,
        metadata_only=True,raw_only=True,frame=frame,extra_callee_reads=0,heap_reads=0,
        new_code_body_reads=0,sibling_code_read=False,handler_body_read=False,
        automatic_handler_or_window_extension=False,runtime_unwind_proven=False,
        clone_execution_proven=False,logical_function_complete=False,classification_ready=False,contract_ready=False)
    POST_BYTES=216+480+12+4*MAX_NODE+346+4120
    POST_CALLS=2+2+1+4+4+4
    def reserve(size=0,calls=0):
        budget.require_capacity(POST_BYTES+size,POST_CALLS+calls)
        if budget.query_calls+POST_CALLS+calls>parent.parent.MAX_READS:
            raise ValueError('CLONE_UW_POST_QUERY_RESERVATION_BUDGET')
    def code_pins():
        for name,rva,raw in pins:
            if budget.read_module(rva,len(raw),'known_'+name+'_pin',True)!=raw:
                raise ValueError('CLONE_UW_FRESH_CODE_PIN_CHANGED: '+name)
    def fixed_rf(records):
        expected=b''.join(bytes.fromhex(r['raw_hex']) for r in records)
        raw=budget.read_module(records[0]['rva'],RF_BYTES,'exception_record')
        if raw!=expected:raise ValueError('CLONE_UW_FRESH_NINE_RF_CHANGED')
        return raw
    def uw_window(name,window):
        raw=budget.read_module(*window,'unwind_metadata')
        for family,rva,pin in known:
            if family==name:
                offset=rva-window[0]
                if raw[offset:offset+len(pin)]!=pin:raise ValueError('CLONE_UW_FRESH_KNOWN_FULL_OR_HEADER_CHANGED: '+name)
        return raw
    def checked(rva,size):
        if not v1.frozen.EXCEPTION_RVA<=rva<rva+size<=v1.frozen.EXCEPTION_RVA+v1.frozen.EXCEPTION_SIZE:
            raise ValueError('CLONE_UW_FRAME_LOOKUP_OUTSIDE_FIXED_PDATA')
        reserve(size,1);return budget.read_module(rva,size,'exception_record')
    reader.checked_metadata_read=lambda b,rva,size:checked(rva,size)
    code_pins();w_rf=fixed_rf(wr);c_rf=fixed_rf(cr)
    w_raw=uw_window('world',WORLD_UW);c_raw=uw_window('contact',CONTACT_UW)
    families=[parse_family('world',w_raw,WORLD_UW[0],wr,reader),parse_family('contact',c_raw,CONTACT_UW[0],cr,reader)]
    evidence['families']=families
    begin,end=reader.find_function(budget,frame['exception_records']);selected=frame['exception_records'][-1]
    if not v1.frozen.CODE_BEGIN<=begin<=FRAME<end<=v1.frozen.CODE_END:
        raise ValueError('CLONE_UW_FRAME_RF_OUTSIDE_CODE_SECTION')
    frame.update(function_begin=begin,function_end=end,selected_record=selected,
        actual_RF_end_was_not_assumed=True,declared_RF_covers_known67=begin<=FRAME and FRAME+67<=end)
    current=(begin,end,selected['unwind_rva']);seen=set();frame_raw=[];frame_reg=None
    frame['unknown_layouts']=[];frame['complete_standard_ancestry']=False
    for level in range(MAX_FRAME_NODES):
        reader.validate_runtime_entry(*current)
        if current in seen:raise ValueError('CLONE_UW_FRAME_CHAIN_CYCLE')
        seen.add(current);at=current[2]
        if not RO_BEGIN<=at<at+4<=RO_END:raise ValueError('CLONE_UW_FRAME_OUTSIDE_KNOWN_RODATA')
        reserve(4,1);header=budget.read_module(at,4,'unwind_metadata')
        try:size,flags=standard_size(header,reader)
        except ValueError as error:
            frame['unknown_layouts'].append({'rva':at,'reason':str(error),'header_hex':header.hex()})
            frame_raw.append((at,header));break
        if size>MAX_NODE or not RO_BEGIN<=at<at+size<=RO_END:
            frame['unknown_layouts'].append({'rva':at,'reason':'COMPLETE_NODE_OVER_128_OR_RODATA',
                'standard_length':size,'header_hex':header.hex()});frame_raw.append((at,header));break
        reserve(size,1);raw=budget.read_module(at,size,'unwind_metadata')
        if raw[:4]!=header:raise ValueError('CLONE_UW_FRAME_HEADER_CHANGED')
        if flags&3 and struct.unpack_from('<I',raw,size-4)[0]==0x21044A0:
            if size+4>MAX_NODE or at+size+4>RO_END:
                frame['unknown_layouts'].append({'rva':at,'reason':'GS_PREFIX_OUTSIDE_128B_NODE_OR_RODATA'})
            else:
                reserve(4,1);raw+=budget.read_module(at+size,4,'unwind_metadata')
        node=parse_uw(raw,at,reader);node.update(begin=current[0],end=current[1])
        if frame_reg is not None and header[3]!=frame_reg:raise ValueError('CLONE_UW_FRAME_CHAIN_FRAME_REGISTER_CHANGED')
        frame_reg=header[3];frame['unwind_nodes'].append(node);frame_raw.append((at,raw))
        if not flags&4:frame['complete_standard_ancestry']=True;break
        if level+1==MAX_FRAME_NODES:
            frame['unknown_layouts'].append({'rva':at,'reason':'CHAIN_REQUIRES_MORE_THAN_FOUR_NODES'});break
        current=tuple(node['chain_entry'])
        if not v1.frozen.CODE_BEGIN<=current[0]<current[1]<=v1.frozen.CODE_END:
            raise ValueError('CLONE_UW_FRAME_CHAIN_OUTSIDE_CODE_SECTION')
    reserve()
    if budget.read_module(selected['rva'],12,'exception_record').hex()!=selected['raw_hex']:
        raise ValueError('CLONE_UW_FRAME_SELECTED_RF_CHANGED')
    for at,raw in frame_raw:
        if budget.read_module(at,len(raw),'unwind_metadata')!=raw:raise ValueError('CLONE_UW_FRAME_FULL_NODE_CHANGED')
    if fixed_rf(wr)!=w_rf or fixed_rf(cr)!=c_rf:raise ValueError('CLONE_UW_FIXED_RF_CHANGED')
    if uw_window('world',WORLD_UW)!=w_raw or uw_window('contact',CONTACT_UW)!=c_raw:
        raise ValueError('CLONE_UW_FIXED_WINDOWS_CHANGED')
    code_pins()
    chunks=[('world_RF9',wr[0]['rva'],w_rf),('contact_RF9',cr[0]['rva'],c_rf),
            ('world_UW224',WORLD_UW[0],w_raw),('contact_UW256',CONTACT_UW[0],c_raw),
            ('frame_actual_RF',selected['rva'],bytes.fromhex(selected['raw_hex']))]
    chunks += [('frame_UW_node_'+str(i),at,raw) for i,(at,raw) in enumerate(frame_raw)]
    binary=b'';ranges=[]
    for name,rva,raw in chunks:
        ranges.append({'name':name,'module':'game','rva':rva,'length':len(raw),'binary_offset':len(binary)})
        binary+=raw
    evidence.update(ranges=ranges,metadata_bytes=len(binary),code_bytes=0,
        fixed_RF_before_after_match=True,fixed_UW_before_after_match=True,
        contact_known_full_chain_and_25C0_match=True,all_four_code_pins_before_after_match=True,
        frame_captured_UW_bytes_before_after_match=True,
        frame_full_standard_UW_ancestry_captured=frame['complete_standard_ancestry'],
        world_RF_records=wr,contact_RF_records=cr,
        unknown_handler_formats=[{'family':f['name'],'rva':at} for f in families for at in f['unknown_handler_formats']]
            +[{'family':'frame','rva':n['unwind_rva']} for n in frame['unwind_nodes'] if not n['handler_data_format_known']],
        boundary_kind='fixed_metadata_package_not_game_unwind_or_clone_execution',
        standard_layouts_complete=frame['complete_standard_ancestry'] and not frame['unknown_layouts']
            and all(not f['unknown_layouts'] and not f['unresolved_chain_targets'] for f in families),
        runtime_unwind_proven=False,clone_execution_proven=False)
    return binary


v1.REVISION,v1.validate_source,v1.capture=REVISION,validate_source,capture


def run(output,dependencies=None,clock=time.perf_counter):return v1.run(output,dependencies,clock)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (OSError,ValueError) as error:parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
