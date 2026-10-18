"""Fixed 17A9820 declaration/UW metadata only; never read its instructions.

Known CALL1455E1A is checked before/after. Only Ship PID67988, exact module
identities and PE, bounded 12B pdata search and <=4 standard UW nodes.
Opaque language data stays unknown; no handler code, consumer or callback claim.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'tools/hit-contact-forwarder-code-capture.py'
BASE_SHA='3cb34d65eabbbdd27a188f40e295117aad8c04aca7c9ab4282390f1cb998fc39'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:raise ValueError('TAB_METADATA_BASE_CHANGED')
spec=importlib.util.spec_from_file_location('_career_tab_metadata_private',BASE)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
REVISION='career_tab_initializer_standard_metadata_v1'
TARGET_RVA,CALLER,CALL_PIN=0x17A9820,0x1455E1A,bytes.fromhex('e8013a3500')
EXPECTED_PID=67988
MAX_BYTES,MAX_READS,MAX_SECONDS=16384,64,2.0
MAX_NODES,MAX_NODE_BYTES=4,128
RO_BEGIN,RO_END=0x2111000,0x263BA0C
POST_BYTES,POST_CALLS=4096+5+12+12+MAX_NODES*MAX_NODE_BYTES,5+MAX_NODES
SOURCE=ROOT/'dist/career-armory-view-init-20261012-8a8b50c3/capture'
SOURCE_BIN_SHA='4ab9fe08c4d409637872f9f6926b73a0906ad8d53292023bd32c1100a7990257'
SOURCE_JSON_SHA='c13ec7a27a44d91b3e79b8444a64a9888f7fee2e7c52c1e1ea8c96b9664b7ca7'


def validate_source():
    raw=(SOURCE/'drain.bin').read_bytes();meta_raw=(SOURCE/'drain.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_BIN_SHA or hashlib.sha256(meta_raw).hexdigest()!=SOURCE_JSON_SHA:
        raise ValueError('TAB_METADATA_SOURCE_CHANGED')
    m=json.loads(meta_raw)
    if (not m.get('complete') or m.get('sha256')!=SOURCE_BIN_SHA
            or m.get('fingerprint')!=base.profile.FINGERPRINT
            or m.get('callee_rva')!=0x1455C30 or m.get('body_binary_offset')!=5
            or m.get('ranges')!=[{'name':'impact_consumer_callsite','rva':0x1455A34,'length':5,'binary_offset':0},
                {'name':'impact_consumer_declared_0','rva':0x1455C30,'length':2855,'binary_offset':5}]):
        raise ValueError('TAB_METADATA_SOURCE_PROFILE')
    off=5+CALLER-0x1455C30
    if raw[off:off+5]!=CALL_PIN or CALLER+5+struct.unpack_from('<i',CALL_PIN,1)[0]!=TARGET_RVA:
        raise ValueError('TAB_METADATA_SOURCE_CALL')
    return {'bin':str(SOURCE/'drain.bin'),'bin_sha256':SOURCE_BIN_SHA,
            'json':str(SOURCE/'drain.json'),'json_sha256':SOURCE_JSON_SHA,
            'caller_rva':CALLER,'pin_hex':CALL_PIN.hex(),'target_rva':TARGET_RVA,
            'known_registers':{'RCX':'Armory object + 0x570','EDX':900},
            'R8_R9_and_900_semantics_proven':False,'source_PID_is_current_identity':False}


class Budget(base.Budget):
    def __init__(self,process,identity,clock=time.perf_counter):
        # Only this newly loaded private module is configured; old defaults unchanged.
        base.MAX_BYTES,base.MAX_READS,base.MAX_SECONDS=MAX_BYTES,MAX_READS,MAX_SECONDS
        super().__init__(process,identity,clock)


def inspect_header(budget):
    raw=base.inspect_header(budget);second=base.PE_OFFSET+24+240+40
    if (struct.unpack_from('<II',raw,second+8)!=(RO_END-RO_BEGIN,RO_BEGIN)
            or struct.unpack_from('<I',raw,second+36)[0]!=0x40000040):
        raise ValueError('TAB_METADATA_RO_SECTION_CHANGED')
    return raw


def capture(budget,evidence):
    reader=base.profile.private_reader()
    reader.TARGET_RVA,reader.TARGET_PIN=TARGET_RVA,''
    reader.IMAGE_SIZE=base.IMAGE_SIZE
    reader.EXCEPTION_RVA,reader.EXCEPTION_SIZE=base.EXCEPTION_RVA,base.EXCEPTION_SIZE
    # Metadata ownership may span more than a body-read cap; no code is read.
    reader.MAX_FUNCTION_BYTES=base.CODE_END-base.CODE_BEGIN
    def reserve(size,calls=1):
        budget.require_capacity(size+POST_BYTES,calls+POST_CALLS)
        if budget.query_calls+calls+POST_CALLS>MAX_READS:raise ValueError('TAB_METADATA_QUERY_POST_RESERVE')
    def read(rva,n):
        pdata=base.EXCEPTION_RVA<=rva<rva+n<=base.EXCEPTION_RVA+base.EXCEPTION_SIZE
        if not pdata and not RO_BEGIN<=rva<rva+n<=RO_END:raise ValueError('TAB_METADATA_OUTSIDE_FIXED_METADATA_SECTIONS')
        reserve(n);return budget.read_module(rva,n,'exception_record' if pdata else 'unwind_metadata')
    reader.checked_metadata_read=lambda _,rva,n:read(rva,n)
    records=[];evidence['exception_records']=records
    begin,end=reader.find_function(budget,records)
    if not base.CODE_BEGIN<=begin<TARGET_RVA+1<=end<=base.CODE_END:raise ValueError('TAB_METADATA_DECLARATION_NOT_CODE')
    selected=records[-1];current=(begin,end,selected['unwind_rva'])
    nodes=[];unknowns=[];evidence['unwind_nodes']=nodes;seen=set();frame=None
    for level in range(MAX_NODES):
        begin,end,at=current
        reader.validate_runtime_entry(begin,end,at)
        if not base.CODE_BEGIN<=begin<end<=base.CODE_END:raise ValueError('TAB_METADATA_CHAIN_DECLARATION_NOT_CODE')
        if at in seen:raise ValueError('TAB_METADATA_CHAIN_CYCLE')
        seen.add(at);header=read(at,4)
        node={'begin':begin,'end':end,'unwind_rva':at,'header_hex':header.hex(),'raw_hex':header.hex(),'length':4}
        nodes.append(node)
        try:
            flags=reader.check_unwind_header(header)
            if header[0]&7!=1:raise ValueError('UNWIND_VERSION_NOT_V1')
            if frame is not None and header[3]!=frame:raise ValueError('CHAIN_FRAME_MISMATCH')
            frame=header[3];slots_end=4+2*((header[2]+1)&~1)
            length=slots_end+(12 if flags&4 else 4 if flags&3 else 0)
            if length>MAX_NODE_BYTES:raise ValueError('STANDARD_NODE_EXCEEDS_128')
        except ValueError as error:
            unknowns.append({'rva':at,'reason':str(error)});break
        raw=read(at,length)
        if raw[:4]!=header:raise ValueError('TAB_METADATA_UW_HEADER_CHANGED')
        node.update(version=1,flags=flags,prolog_size=header[1],slot_count=header[2],
            frame_register=header[3]&15,frame_offset_bytes=header[3]&0xF0,
            raw_hex=raw.hex(),length=length,standard_layout_complete=True)
        if flags&4:
            current=struct.unpack_from('<III',raw,slots_end);node['chain_entry']=list(current)
            if level+1==MAX_NODES:unknowns.append({'rva':at,'reason':'CHAIN_EXCEEDS_FOUR_NODES'})
        else:
            if flags&3:
                node.update(handler_rva=struct.unpack_from('<I',raw,slots_end)[0],handler_data_rva=at+length,
                            handler_data_format_known=False)
                unknowns.append({'rva':at+length,'reason':'OPAQUE_HANDLER_DATA_NOT_READ'})
            break
    evidence.update(function_begin=selected['begin'],function_end=selected['end'],selected_runtime_function=selected,
        unknowns=unknowns,metadata_readiness='WITHHELD_UNKNOWN_LAYOUT' if unknowns else 'STANDARD_METADATA_COMPLETE',
        initializer_instructions_read=False,handler_code_read=False,opaque_handler_data_read=False,
        callback_registration_proven=False,normal_tab_input_consumer_proven=False,logical_function_complete=False)
    raw_rf=bytes.fromhex(selected['raw_hex'])
    if budget.read_module(selected['rva'],12,'exception_record')!=raw_rf:raise ValueError('TAB_METADATA_RF_CHANGED_AFTER')
    raw=raw_rf;ranges=[{'kind':'selected_runtime_function','rva':selected['rva'],'length':12,'binary_offset':0}]
    for node in nodes:
        pin=bytes.fromhex(node['raw_hex'])
        if budget.read_module(node['unwind_rva'],len(pin),'unwind_metadata')!=pin:
            raise ValueError('TAB_METADATA_UW_CHANGED_AFTER')
        ranges.append({'kind':'standard_unwind_metadata','rva':node['unwind_rva'],'length':len(pin),'binary_offset':len(raw)})
        raw+=pin
    evidence['ranges']=ranges
    return raw


def run(output,dependencies=None,clock=time.perf_counter):
    folder=Path(output).resolve()
    if folder.exists():raise ValueError('TAB_METADATA_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    evidence={'source_revision':REVISION,'target_rva':TARGET_RVA,'caller_rva':CALLER,
        'capture_purpose':'DECLARATION_AND_STANDARD_UNWIND_METADATA_ONLY','complete':False,
        'metadata_only':True,'native_called':False,'native_written':False,'attempts':1,
        'extra_callee_reads':0,'heap_reads_excluding_fixed_FSM':0,'classification_ready':False}
    budget=None
    try:
        evidence['source']=validate_source()
        deps=dependencies if dependencies is not None else base.profile.load_dependencies()
        stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(EXPECTED_PID,):raise ValueError('TAB_METADATA_EXPECTS_AUTHORIZED_PID67988_ONLY')
        pid=pids[0];identity=deps['resolve_game'](pid)
        deps['validate_identity'](identity,stamps);base.profile.validate_module(identity)
        evidence.update(game_pid=pid,identity=identity,fingerprint=base.profile.FINGERPRINT)
        with deps['Process'](pid) as process:
            budget=Budget(process,identity,clock)
            before=deps['ship_state'](budget,identity);evidence['ship_before']=before
            if before['state']!=3:raise ValueError('TAB_METADATA_EXPECTS_SHIP_ONLY')
            header=inspect_header(budget);pin=budget.read_module(CALLER,5,'known_caller_pin',True)
            if pin!=CALL_PIN:raise ValueError('TAB_METADATA_CALLER_PIN_CHANGED')
            raw=capture(budget,evidence)
            header_after=inspect_header(budget);pin_after=budget.read_module(CALLER,5,'known_caller_pin_after',True)
            after=deps['ship_state'](budget,identity);evidence['ship_after']=after
            if header_after!=header or pin_after!=pin:raise ValueError('TAB_METADATA_SOURCE_CHANGED_AFTER')
            if before!=after:raise ValueError('TAB_METADATA_SHIP_CONTEXT_CHANGED')
            budget.time_gate()
        final=deps['resolve_game'](pid);deps['validate_identity'](final,stamps)
        if final!=identity or tuple(deps['game_processes']())!=(pid,):raise ValueError('TAB_METADATA_MODULE_OR_PID_CHANGED')
        budget.time_gate()
        binary,report=folder/'metadata.bin',folder/'metadata.json'
        evidence.update(complete=True,sha256=hashlib.sha256(raw).hexdigest(),binary_bytes=len(raw),
            budget=budget.summary(),read_records=budget.records,fresh_gates_verified=True,
            caller_pin_before_after=pin.hex(),PE_header_before_after_match=True,
            captured_at=datetime.now(timezone.utc).isoformat(),tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        binary.write_bytes(raw);report.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n','utf8')
        return {'status':'complete','binary_path':str(binary),'json_path':str(report),
                'sha256':evidence['sha256'],'metadata_readiness':evidence['metadata_readiness']}
    except Exception as error:
        if budget is not None:evidence.update(budget=budget.summary(),read_records=budget.records)
        evidence.update(error=str(error),complete=False,partial_binary_saved=False)
        (folder/'metadata.incomplete.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n','utf8')
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(run(args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
