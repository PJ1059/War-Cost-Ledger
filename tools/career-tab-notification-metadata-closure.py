"""Fixed8RF metadata ownership only for entry17AC3E0; no further code reads."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'tools/career-tab-notification-capture.py'
PARENT_SHA='7b0cba1a9ce845114cc3da9ebe5deae5e3e82982659beeaeadcd6e7d5ced1484'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('TAB_CLOSURE_PARENT_CHANGED')
spec=importlib.util.spec_from_file_location('_tab_notification_metadata_closure_private',PARENT)
source_reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(source_reader)
parent=source_reader.parent
PACKET=ROOT/'dist/career-tab-notification-live-20261013-v1'
BIN_SHA='5064fbf8433186520bbcea000c252fdaf89623d6cbf3473cc0e4249e0c151714'
JSON_SHA='9e86e1de8f312bb674cc7a70a6355170c2366416861264bce970cb21c4e73bb7'
RF_INDEX,RF_RVA,RF_BYTES=96757,0x40EEB88,96
ENTRY=(0x17AC3E0,0x17AC401,0x256F8D0)
ENTRY_RF=bytes.fromhex('e0c37a0101c47a01d0f85602')
ENTRY_UW=bytes.fromhex('0106020006320270')
TARGETS=(0x17AC401,0x17AC49C)
_validate=source_reader.validate_source


def validate_source():
    result=_validate();raw=(PACKET/'metadata.bin').read_bytes();report=(PACKET/'metadata.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BIN_SHA or hashlib.sha256(report).hexdigest()!=JSON_SHA:
        raise ValueError('TAB_CLOSURE_ENTRY_PACKET_CHANGED')
    m=json.loads(report)
    if (not m.get('complete') or not m.get('fresh_gates_verified') or not m.get('RF_UW_before_after_body_match')
            or (m.get('function_begin'),m.get('function_end'))!=ENTRY[:2]
            or m['selected_runtime_function'].get('index')!=RF_INDEX
            or raw[:20]!=ENTRY_RF+ENTRY_UW or RF_RVA!=parent.base.EXCEPTION_RVA+12*RF_INDEX):
        raise ValueError('TAB_CLOSURE_ENTRY_PACKET_PROFILE')
    result['closure_source']={'path':str(PACKET),'BIN_SHA256':BIN_SHA,'JSON_SHA256':JSON_SHA,
        'entry_triple':list(ENTRY),'fixed_RF_index':RF_INDEX,'fixed_RF_bytes':RF_BYTES,
        'known_branch_or_fallthrough_targets':list(TARGETS),'source_PID_is_current_identity':False}
    return result


def capture(budget,evidence):
    reader=parent.base.profile.private_reader();reader.IMAGE_SIZE=parent.base.IMAGE_SIZE
    reader.MAX_FUNCTION_BYTES=parent.base.CODE_END-parent.base.CODE_BEGIN
    cache={}
    def reserve(n):
        post_bytes=96+4096+5+12+sum(node['length']for node in cache.values())
        post_calls=5+len(cache)
        budget.require_capacity(n+post_bytes,1+post_calls)
        if budget.query_calls+1+post_calls>64:raise ValueError('TAB_CLOSURE_POST_QUERY_RESERVE')
    def read(rva,n,purpose):
        if purpose=='unwind_metadata'and not parent.RO_BEGIN<=rva<rva+n<=parent.RO_END:
            raise ValueError('TAB_CLOSURE_UW_NOT_READONLY_METADATA')
        reserve(n);return budget.read_module(rva,n,purpose)
    window=read(RF_RVA,RF_BYTES,'exception_record')
    if window[:12]!=ENTRY_RF:raise ValueError('TAB_CLOSURE_ENTRY_RF_CHANGED')
    rows=[]
    for index in range(8):
        b,e,u=struct.unpack_from('<III',window,index*12)
        reader.validate_runtime_entry(b,e,u)
        if not parent.base.CODE_BEGIN<=b<e<=parent.base.CODE_END:raise ValueError('TAB_CLOSURE_RF_NOT_CODE')
        if rows and b<rows[-1]['end']:raise ValueError('TAB_CLOSURE_RF_UNSORTED_OR_OVERLAP')
        rows.append({'index':RF_INDEX+index,'rva':RF_RVA+index*12,'begin':b,'end':e,'unwind_rva':u,
                     'raw_hex':window[index*12:index*12+12].hex()})
    evidence.update(exception_records=rows,unwind_nodes=[],ownership=[],metadata_only=True,
        function_begin=ENTRY[0],function_end=ENTRY[1],selected_runtime_function=rows[0],
        body_captured=False,extra_code_reads=0,helpers_followed=False,input_values_read=False,
        capture_purpose='FIXED8_RF_AND_STANDARD_UW_OWNERSHIP_ONLY',
        metadata_closure_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    def node(at):
        if at in cache:return cache[at]
        if at%4:raise ValueError('TAB_CLOSURE_UW_ALIGNMENT')
        value={'unwind_rva':at,'length':4};cache[at]=value
        header=read(at,4,'unwind_metadata');value.update(raw_hex=header.hex(),header_hex=header.hex())
        flags=reader.check_unwind_header(header)
        if header[0]&7!=1:raise ValueError('TAB_CLOSURE_STANDARD_VERSION_UNKNOWN')
        slots_end=4+2*((header[2]+1)&~1);size=slots_end+(12 if flags&4 else 4 if flags&3 else 0)
        if size>128:raise ValueError('TAB_CLOSURE_NODE_EXCEEDS128')
        value['length']=size;raw=read(at,size,'unwind_metadata')
        if raw[:4]!=header:raise ValueError('TAB_CLOSURE_HEADER_CHANGED')
        value.update(raw_hex=raw.hex(),flags=flags,frame_byte=header[3],version=1,slot_count=header[2])
        if flags&4:value['chain_entry']=list(struct.unpack_from('<III',raw,slots_end))
        elif flags&3:value.update(handler_rva=struct.unpack_from('<I',raw,slots_end)[0],handler_data_unread=True)
        if at==ENTRY[2]and raw!=ENTRY_UW:raise ValueError('TAB_CLOSURE_ENTRY_UW_CHANGED')
        evidence['unwind_nodes'].append(value)
        return value
    for row in rows:
        current=tuple(row[k]for k in ('begin','end','unwind_rva'));seen=set();frame=None;chain=[]
        for _ in range(4):
            if current in seen:raise ValueError('TAB_CLOSURE_CHAIN_CYCLE')
            seen.add(current);b,e,u=current;reader.validate_runtime_entry(b,e,u)
            if not parent.base.CODE_BEGIN<=b<e<=parent.base.CODE_END:raise ValueError('TAB_CLOSURE_CHAIN_RF_NOT_CODE')
            value=node(u)
            if frame is not None and value['frame_byte']!=frame:raise ValueError('TAB_CLOSURE_FRAME_MISMATCH')
            frame=value['frame_byte'];chain.append(list(current))
            if 'chain_entry'not in value:
                row.update(primary_entry=list(current),same_entry=current==ENTRY,chain=chain);break
            current=tuple(value['chain_entry'])
        else:raise ValueError('TAB_CLOSURE_CHAIN_EXCEEDS4')
        evidence['ownership'].append({'RF_index':row['index'],'same_entry':row['same_entry'],
                                      'primary_entry':row['primary_entry'],'chain':row['chain']})
    own=[row for row in rows if row['same_entry']];merged=[]
    for row in own:
        if merged and row['begin']==merged[-1][1]:merged[-1][1]=row['end']
        else:merged.append([row['begin'],row['end']])
    foreign=next((row for row in rows if not row['same_entry']),None)
    targets=[]
    for pc in TARGETS:
        found=[row for row in rows if row['begin']<=pc<row['end']]
        targets.append({'target':pc,'RF_index':found[0]['index']if len(found)==1 else None,
                        'same_entry':len(found)==1 and found[0]['same_entry']})
    if budget.read_module(RF_RVA,RF_BYTES,'exception_record')!=window:raise ValueError('TAB_CLOSURE_RF_WINDOW_CHANGED_AFTER')
    raw=window;ranges=[{'kind':'fixed8_RF','rva':RF_RVA,'length':96,'binary_offset':0}]
    for at,value in sorted(cache.items()):
        pin=bytes.fromhex(value['raw_hex'])
        if budget.read_module(at,len(pin),'unwind_metadata')!=pin:raise ValueError('TAB_CLOSURE_UW_CHANGED_AFTER')
        ranges.append({'kind':'standard_UW','rva':at,'length':len(pin),'binary_offset':len(raw)});raw+=pin
    evidence.update(ranges=ranges,unknowns=[],metadata_readiness='FIXED_WINDOW_OWNERSHIP_COMPLETE',
        same_entry_ranges_within_fixed8=merged,first_foreign_RF=foreign,
        known_target_ownership=targets,all_known_targets_same_entry=all(row['same_entry']for row in targets),
        UW_nodes_cached_per_capture=True,fixed_window_before_after_match=True,logical_function_complete=False,
        sibling_table_outside_fixed8_scanned=False,normal_tab_input_consumer_proven=False,
        handler_code_read=False,opaque_handler_data_read=False)
    return raw

parent.REVISION='career_tab_notification_fixed8_metadata_closure_v1'
parent.capture,parent.validate_source=capture,validate_source

def run(output,dependencies=None,clock=time.perf_counter):return parent.run(output,dependencies,clock)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
