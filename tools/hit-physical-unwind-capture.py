"""Ship-only pinned success instruction plus its complete unwind metadata.

No function-body scan, scope-table read, native call, patch or thread operation.
Uses one shared 8192B/32-read/2s-soft budget; Ship gates add 24B/4 reads.
"""
from pathlib import Path
import importlib.util
import time
import hashlib

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('physical_unwind_private_session',
                                          ROOT/'tools/hit-queue-consumer-code-capture.py')
session=importlib.util.module_from_spec(spec);spec.loader.exec_module(session)
reader=session.reader
session.REVISION=reader.REVISION='physical_success_unwind_metadata_v1'
session.TARGET_RVA=reader.TARGET_RVA=0x13B11D4
session.TARGET_PIN=reader.TARGET_PIN='32c088451c'
reader.SOURCE_REFERENCE='actual physical success SHA c062eb498383dd15c9e4c22bdc2668eda732db8e737cf8bee11b7f97076408e4'


def capture(process,identity,clock=time.perf_counter,evidence=None):
    reader.validate_module(identity)
    budget=reader.Budget(process,identity,clock)
    journal=[];nodes=[]
    evidence={} if evidence is None else evidence
    evidence.update(exception_records=journal,unwind_chain=nodes,
                    source_revision=reader.REVISION,target_rva=reader.TARGET_RVA,
                    native_written=False,native_called=False)
    try:
        begin,end=reader.find_function(budget,journal)
        reader.unwind_ancestry((begin,end,journal[-1]['unwind_rva']),
            lambda rva,size:reader.checked_metadata_read(budget,rva,size),nodes)
        window=reader.window_capture((('physical_success_instruction',reader.TARGET_RVA,5),))
        raw,meta=window.capture(budget,identity,sleep=lambda _:None)
        pieces=[raw]
        for node in nodes:
            header=bytes.fromhex(node['header']['raw_hex'])
            flags=reader.check_unwind_header(header)
            padded_slots=2*((header[2]+1)&~1)
            tail=12 if flags&4 else (4 if flags&3 else 0)
            size=4+padded_slots+tail
            block=reader.checked_metadata_read(budget,node['unwind_rva'],size)
            if block[:4]!=header:raise ValueError('PHYSICAL_UNWIND_HEADER_CHANGED')
            if flags&4:
                if block[-12:].hex()!=node['chain_entry']['raw_hex']:
                    raise ValueError('PHYSICAL_UNWIND_CHAIN_CHANGED')
            elif tail:
                handler=int.from_bytes(block[-4:],'little')
                if not 0<handler<reader.IMAGE_SIZE:raise ValueError('PHYSICAL_UNWIND_HANDLER_OUTSIDE_IMAGE')
                node['handler_rva']=handler
            node['complete_unwind']={'rva':node['unwind_rva'],'binary_offset':sum(map(len,pieces)),
                'length':size,'raw_hex':block.hex(),'slot_count':header[2],
                'frame_register':header[3]&15,'frame_offset':header[3]>>4,
                'scope_table_read':False}
            pieces.append(block)
        meta.update(exception_records=journal,unwind_chain=nodes,function_begin=begin,function_end=end,
                    target_rva=reader.TARGET_RVA,source_reference=reader.SOURCE_REFERENCE,
                    boundary_kind='pinned_success_instruction_plus_declared_unwind_metadata',
                    logical_function_complete=False,all_sibling_fragments_captured=False,
                    bytes_written=sum(map(len,pieces)),code_bytes=5,scope_table_read=False,
                    diagnostic_only=True,classification_ready=False,native_called=False,native_written=False)
        binary=b''.join(pieces)
        meta['code_pin_sha256']=hashlib.sha256(raw).hexdigest()
        meta['binary_sha256']=hashlib.sha256(binary).hexdigest()
        verify_saved(meta,binary)
        return binary,meta
    finally:
        evidence['budget']=budget.summary()
        if 'meta' in locals():meta['budget']=evidence['budget']


def verify_saved(meta,raw):
    if meta['source_revision']!=reader.REVISION or meta['target_rva']!=reader.TARGET_RVA:
        raise ValueError('PHYSICAL_UNWIND_SAVED_PROFILE')
    if raw[:5]!=bytes.fromhex(reader.TARGET_PIN) or meta['scope_table_read'] is not False:
        raise ValueError('PHYSICAL_UNWIND_SAVED_PIN')
    if not meta['function_begin']<=reader.TARGET_RVA<reader.TARGET_RVA+5<=meta['function_end']:
        raise ValueError('PHYSICAL_UNWIND_SAVED_RANGE')
    at=5
    if not 1<=len(meta['unwind_chain'])<=reader.MAX_CHAIN_NODES:
        raise ValueError('PHYSICAL_UNWIND_SAVED_DEPTH')
    for node in meta['unwind_chain']:
        part=node['complete_unwind'];block=bytes.fromhex(part['raw_hex'])
        header=bytes.fromhex(node['header']['raw_hex']);flags=reader.check_unwind_header(header)
        expected=4+2*((header[2]+1)&~1)+(12 if flags&4 else 4 if flags&3 else 0)
        if part['binary_offset']!=at or len(block)!=expected or raw[at:at+expected]!=block or block[:4]!=header:
            raise ValueError('PHYSICAL_UNWIND_SAVED_BLOCK')
        if flags&4 and block[-12:].hex()!=node['chain_entry']['raw_hex']:
            raise ValueError('PHYSICAL_UNWIND_SAVED_CHAIN')
        if flags&3 and not 0<int.from_bytes(block[-4:],'little')<reader.IMAGE_SIZE:
            raise ValueError('PHYSICAL_UNWIND_SAVED_HANDLER')
        at+=expected
    if len(raw)!=at or meta['bytes_written']!=at:raise ValueError('PHYSICAL_UNWIND_SAVED_SIZE')


reader.capture=capture
reader.verify_saved=verify_saved
if __name__=='__main__':session.main()
