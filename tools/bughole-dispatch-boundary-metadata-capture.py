"""One fixed adjacent-RF ownership packet for the known dispatch entry.

Read96B (eightRFs from actual saved index68550) twice, at most four UW
nodes per declaration, including codes/CHAIN/handler RVA but no handler/scope.
Known CALL5+entry155 are full source PINs before/after, never new body reads.
Shared Ship27268/context/PID/module gates and16KiB/64IO-query/2s cap.
No dynamic range expansion, function body follow, callee/heap/event values,
Game calls/writes/retry. Metadata ownership is not complete logical CFG.
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
FROZEN = ROOT / 'tools/bughole-network-handler-code-capture.py'
FROZEN_SHA = 'a586d762f3939dfc55b1f06215131928bb95463e5f6b286a34b40eb57eb075f1'
SOURCE = ROOT / 'dist/bughole-destruction-dispatch-live-20261013-v1'
META_SHA = 'd8fee42f118dc8145cd081105ee5b16814f31314cf2de9b413a3d15cd7a05273'
BIN_SHA = '698e4743de51c82e818d3db8e8621c07619c2740a68d34e2df09050104e63f4f'
ENTRY, TARGETS = 0x13D8B10, (0x13D8BAB, 0x13D8D07)
CALL, CALL_HEX = 0x13E2097, 'e8746affff'
REVISION = 'bughole_dispatch_fixed_adjacent_RF_ownership_metadata_v1'
if hashlib.sha256(FROZEN.read_bytes()).hexdigest() != FROZEN_SHA:
    raise ValueError('BUGHOLE_BOUNDARY_FROZEN_SESSION_CHANGED')
encoded, entry_body = (SOURCE/'drain.json').read_bytes(), (SOURCE/'drain.bin').read_bytes()
if hashlib.sha256(encoded).hexdigest() != META_SHA or hashlib.sha256(entry_body).hexdigest() != BIN_SHA:
    raise ValueError('BUGHOLE_BOUNDARY_ENTRY_SOURCE_CHANGED')
saved = json.loads(encoded)
if (not saved.get('complete') or saved.get('body_bytes') != 155
        or not saved.get('parent_CALL_before_after_match') or not saved.get('target_entry_declared')
        or not saved.get('selected_RF_before_after_match') or not saved.get('UW_before_after_match')
        or saved.get('function_begin') != ENTRY or saved.get('function_end') != TARGETS[0]
        or len(saved['unwind_chain']) != 1 or entry_body[-6:].hex() != '0f825c010000'
        or ENTRY + 149 + 6 + struct.unpack_from('<i', entry_body, 151)[0] != TARGETS[1]):
    raise ValueError('BUGHOLE_BOUNDARY_ENTRY_FLOW_CONTRACT')
ANCHOR = saved['exception_records'][-1]
WINDOW_RVA, WINDOW_BYTES = ANCHOR['rva'], 96
spec = importlib.util.spec_from_file_location('_bughole_boundary_private_session', FROZEN)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
if (WINDOW_RVA != worker.session.reader.EXCEPTION_RVA + 12*ANCHOR['index']
        or ANCHOR['index'] != 68550 or ANCHOR['raw_hex'] != '108b3d01ab8b3d01003c5102'
        or saved['fingerprint'] != worker.session.tail['FINGERPRINT']):
    raise ValueError('BUGHOLE_BOUNDARY_SAVED_RF_INDEX_CONTRACT')
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = REVISION
# Metadata does not allocate/read a declared body. Keep the existing tuple/
# alignment validity gates while leaving body-size acceptance to the later
# explicit code-read plan; a foreign adjacent function may legitimately be large.
def metadata_entry_valid(begin,end,unwind):
    if (not 0x1000 <= begin < end <= 0x2110A93 or not 0 < unwind < worker.session.reader.IMAGE_SIZE
            or unwind % 4 or unwind + 4 > worker.session.reader.IMAGE_SIZE):
        raise ValueError('BUGHOLE_BOUNDARY_METADATA_ENTRY_INVALID')
worker.session.reader.validate_runtime_entry = metadata_entry_valid


def capture(process, identity, clock=time.perf_counter, evidence=None):
    reader = worker.session.reader
    reader.validate_module(identity)
    budget = reader.Budget(process, identity, clock)
    evidence = {} if evidence is None else evidence
    records, ownership, cache = [], [], {}
    evidence.update(source_revision=REVISION, metadata_only=True, code_only=False,
        new_code_body_reads=0, heap_event_reads=0, native_called=False, native_written=False,
        handler_scope_reads=0, extra_callee_reads=0, exception_records=records, ownership=ownership,
        max_unknown_UW_nodes_per_target=4, source_entry_body_sha256=BIN_SHA)
    def source_pins():
        pins = reader.window_capture((('known_dispatch_parent_CALL_PIN',CALL,5),
                                      ('known_dispatch_full155_PIN',ENTRY,155)))
        pins.PINS = ((CALL,CALL_HEX),(ENTRY,entry_body.hex()))
        raw,_ = pins.capture(budget,identity,sleep=lambda _:None)
        return raw
    before = source_pins()
    table = reader.checked_metadata_read(budget,WINDOW_RVA,WINDOW_BYTES)
    if table[:12].hex() != ANCHOR['raw_hex']:
        raise ValueError('BUGHOLE_BOUNDARY_ANCHOR_RF_CHANGED')
    for i in range(8):
        raw=table[i*12:(i+1)*12];begin,end,uw=struct.unpack('<III',raw)
        reader.validate_runtime_entry(begin,end,uw)
        if not 0x1000 <= begin < end <= 0x2110A93 or records and records[-1]['end']>begin:
            raise ValueError('BUGHOLE_BOUNDARY_RF_ORDER_OR_CODE_RANGE')
        records.append({'index':ANCHOR['index']+i,'rva':WINDOW_RVA+i*12,
            'raw_hex':raw.hex(),'begin':begin,'end':end,'unwind_rva':uw})
    def metadata(at,size):
        key=(at,size)
        if key not in cache:
            cache[key]=reader.checked_metadata_read(budget,at,size)
        return cache[key]
    known_header=saved['unwind_chain'][0]['header']
    chains={}
    def chain(row):
        if row['index'] in chains:
            return chains[row['index']]
        nodes=[]
        reader.unwind_ancestry((row['begin'],row['end'],row['unwind_rva']),metadata,nodes)
        if len(nodes)>4:
            raise ValueError('BUGHOLE_BOUNDARY_UW_NODE_LIMIT')
        for node in nodes:
            hdr=bytes.fromhex(node['header']['raw_hex']);flags=reader.check_unwind_header(hdr)
            if node['header']['rva']==known_header['rva'] and node['header']['raw_hex']!=known_header['raw_hex']:
                raise ValueError('BUGHOLE_BOUNDARY_KNOWN_ENTRY_UW_CHANGED')
            aligned=4+2*((hdr[2]+1)&~1)
            blob=metadata(node['unwind_rva'],aligned)
            if blob[:4]!=hdr:
                raise ValueError('BUGHOLE_BOUNDARY_UW_HEADER_INSIDE_CODES_CHANGED')
            node.update(full_codes_hex=blob.hex(),flags=flags,code_slots=hdr[2])
            if flags&3:
                at=node['unwind_rva']+aligned;raw=metadata(at,4);handler=struct.unpack('<I',raw)[0]
                if not 0x1000<=handler<0x2110A93:
                    raise ValueError('BUGHOLE_BOUNDARY_HANDLER_RVA_INVALID')
                node['handler_rva_metadata']={'rva':at,'raw_hex':raw.hex(),'handler':handler,'scope_followed':False}
        terminal=tuple(nodes[-1][k] for k in ('begin','end','unwind_rva'))
        result={'record_index':row['index'],'begin':row['begin'],'end':row['end'],
            'chain':nodes,'terminal_primary':list(terminal),
            'same_entry_primary':terminal==(ENTRY,TARGETS[0],ANCHOR['unwind_rva'])}
        chains[row['index']]=result
        ownership.append(result)
        return result
    chain(records[0])
    candidates=[];boundary=None;last=ENTRY
    for row in records:
        if row['begin']!=last:
            boundary={'reason':'actual_gap_before_next_RF','next_record':row};break
        result=chain(row)
        if not result['same_entry_primary']:
            boundary={'reason':'first_adjacent_RF_has_foreign_primary','next_record':row,
                'foreign_primary':result['terminal_primary']};break
        candidates.append(row);last=row['end']
    focus=[]
    for target in TARGETS:
        matches=[row for row in records if row['begin']<=target<row['end']]
        if len(matches)!=1:
            raise ValueError('BUGHOLE_BOUNDARY_TARGET_OUTSIDE_FIXED8_RF:'+hex(target))
        result=chain(matches[0]);focus.append({'target':target,**result})
    # Revalidate precisely the fixed table, the known source pins and all UW
    # metadata already used; no new addresses or fields are discovered here.
    if reader.checked_metadata_read(budget,WINDOW_RVA,WINDOW_BYTES)!=table or source_pins()!=before:
        raise ValueError('BUGHOLE_BOUNDARY_TABLE_OR_SOURCE_CHANGED')
    for (at,size),raw in cache.items():
        if reader.checked_metadata_read(budget,at,size)!=raw:
            raise ValueError('BUGHOLE_BOUNDARY_UW_METADATA_CHANGED')
    budget.time_gate()
    evidence.update(complete=True,metadata_only=True,code_only=False,
        source_pins_before_after_match=True,fixed_RF_table_before_after_match=True,
        full_UW_codes_and_trailers_before_after_match=True,focus_targets=focus,
        same_entry_contiguous_declarations=candidates,next_declaration_boundary=boundary,
        metadata_owner_interval_closed=boundary is not None and all(x['same_entry_primary'] for x in focus),
        code_read_plan={'begin':ENTRY,'end':last,'bytes':last-ENTRY,'body_not_read':True,
            'normal_CFG_proven':False},logical_function_complete=False,normal_CFG_proven=False,
        fixed_RF_window={'rva':WINDOW_RVA,'bytes':WINDOW_BYTES,'records':8},
        ranges=[{'name':'fixed8_adjacent_RF_metadata','rva':WINDOW_RVA,'length':WINDOW_BYTES,'binary_offset':0}],
        body_bytes=0,code_body_bytes=0,source_PIN_bytes=320,budget=budget.summary())
    return table,dict(evidence)


worker.capture=capture

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        status=worker.run(args.output)
        path=Path(status['json_path']);report=json.loads(path.read_text('utf8'))
        report.update(code_only=False,metadata_only=True,new_code_body_reads=0)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
        print(json.dumps(status,ensure_ascii=False,indent=2))
    except(OSError,ValueError)as error:
        parser.exit(1,str(error)+'\n')
