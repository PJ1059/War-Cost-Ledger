"""Ship-only six exact instruction PINs and their declared unwind ancestry.

No function bodies, scope tables, heap, native calls, writes or thread actions.
One shared cache/budget: 8192 B, 192 reads/queries, 2 s soft; Ship adds 24 B/4.
"""
from pathlib import Path
import importlib.util
import hashlib
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('inline_unwind_private_session',
    ROOT/'tools/hit-queue-consumer-code-capture.py')
session=importlib.util.module_from_spec(spec);spec.loader.exec_module(session)
reader=session.reader
REVISION='hit_inline_declared_unwind_v1'
SITES=(('contact_begin',0x13AD4E8,'e8c350efff'),
       ('default_delta',0x129CABC,'f3410f5cc1'),
       ('custom_curve',0x129CADF,'e85cfeffff'),
       ('ap_result',0x129CB61,'f30f117704'),
       ('normal_final',0x13AD88B,'e8a004efff'),
       ('iteration_end',0x13AD1D4,'8b442474ffc0'))
session.REVISION=reader.REVISION=REVISION
reader.MAX_READS=192
# This profile reads only metadata. Parent ranges can exceed the unrelated
# 4 KiB body-copy limit; all RVA/image/depth/slot bounds remain enforced.
reader.MAX_FUNCTION_BYTES=reader.IMAGE_SIZE
reader.SOURCE_REFERENCE='actual c062eb498383dd15c9e4c22bdc2668eda732db8e737cf8bee11b7f97076408e4 and declared iteration barrier'

def capture(process,identity,clock=time.perf_counter,evidence=None):
    reader.validate_module(identity)
    budget=reader.Budget(process,identity,clock)
    cache={};records=[];parts=[]
    evidence={} if evidence is None else evidence
    evidence.update(source_revision=REVISION,sites=records,metadata_only=True,
                    native_written=False,native_called=False,scope_table_read=False)
    def metadata(rva,size):
        budget.time_gate()
        key=(rva,size)
        if key not in cache:cache[key]=reader.checked_metadata_read(budget,rva,size)
        return cache[key]
    original_table_read=reader.table_read
    reader.table_read=lambda b,i:metadata(reader.EXCEPTION_RVA+i*reader.ENTRY_SIZE,reader.ENTRY_SIZE)
    try:
        # Validate every actual instruction first. A mismatch prevents ancestry
        # exploration and leaves a failed packet; there is no retry or patch.
        for name,rva,pin in SITES:
            reader.TARGET_RVA,reader.TARGET_PIN=rva,pin
            window=reader.window_capture(((name,rva,len(bytes.fromhex(pin))),))
            raw,_=window.capture(budget,identity,sleep=lambda _:None)
            records.append({'name':name,'rva':rva,'pin':pin,'binary_offset':sum(map(len,parts)),
                            'pin_length':len(raw),'exception_records':[],'unwind_chain':[]})
            parts.append(raw)
        for item in records:
            reader.TARGET_RVA,reader.TARGET_PIN=item['rva'],item['pin']
            begin,end=reader.find_function(budget,item['exception_records'])
            reader.unwind_ancestry((begin,end,item['exception_records'][-1]['unwind_rva']),metadata,item['unwind_chain'])
            item.update(function_begin=begin,function_end=end)
            for node in item['unwind_chain']:
                header=bytes.fromhex(node['header']['raw_hex']);flags=reader.check_unwind_header(header)
                length=4+2*((header[2]+1)&~1)+(12 if flags&4 else 4 if flags&3 else 0)
                block=metadata(node['unwind_rva'],length)
                if block[:4]!=header:raise ValueError('INLINE_UNWIND_HEADER_CHANGED')
                if flags&4 and block[-12:].hex()!=node['chain_entry']['raw_hex']:
                    raise ValueError('INLINE_UNWIND_CHAIN_CHANGED')
                if flags&3:
                    handler=int.from_bytes(block[-4:],'little')
                    if not 0<handler<reader.IMAGE_SIZE:raise ValueError('INLINE_UNWIND_HANDLER_OUTSIDE_IMAGE')
                    node['handler_rva']=handler
                node['complete_unwind']={'rva':node['unwind_rva'],'binary_offset':sum(map(len,parts)),
                    'length':length,'raw_hex':block.hex(),'slot_count':header[2],'scope_table_read':False}
                parts.append(block)
        binary=b''.join(parts)
        meta={'source_revision':REVISION,'sites':records,'metadata_only':True,
              'boundary_kind':'six_exact_instruction_pins_and_declared_unwind_metadata',
              'scope_table_read':False,'code_bytes':31,'bytes_written':len(binary),
              'binary_sha256':hashlib.sha256(binary).hexdigest(),'source_reference':reader.SOURCE_REFERENCE,
              'diagnostic_only':True,'classification_ready':False,'native_written':False,'native_called':False}
        verify_saved(meta,binary)
        return binary,meta
    finally:
        reader.table_read=original_table_read
        evidence['budget']=budget.summary()
        if 'meta' in locals():meta['budget']=evidence['budget']

def verify_saved(meta,raw):
    if meta.get('source_revision')!=REVISION or meta.get('scope_table_read') is not False:
        raise ValueError('INLINE_UNWIND_SAVED_PROFILE')
    if len(meta['sites'])!=6:raise ValueError('INLINE_UNWIND_SAVED_SITES')
    at=0
    for site,(name,rva,pin) in zip(meta['sites'],SITES):
        code=bytes.fromhex(pin)
        if (site['name'],site['rva'],site['pin'],site['binary_offset'],site['pin_length'])!=(name,rva,pin,at,len(code)):
            raise ValueError('INLINE_UNWIND_SAVED_PIN_METADATA')
        if raw[at:at+len(code)]!=code:raise ValueError('INLINE_UNWIND_SAVED_PIN')
        at+=len(code)
        if not site['function_begin']<=rva<rva+len(code)<=site['function_end']:
            raise ValueError('INLINE_UNWIND_SAVED_FUNCTION')
        if not 1<=len(site['unwind_chain'])<=reader.MAX_CHAIN_NODES:
            raise ValueError('INLINE_UNWIND_SAVED_DEPTH')
    for site in meta['sites']:
        for node in site['unwind_chain']:
            reader.validate_runtime_entry(node['begin'],node['end'],node['unwind_rva'])
            part=node['complete_unwind'];block=bytes.fromhex(part['raw_hex'])
            header=bytes.fromhex(node['header']['raw_hex']);flags=reader.check_unwind_header(header)
            expected=4+2*((header[2]+1)&~1)+(12 if flags&4 else 4 if flags&3 else 0)
            if part['binary_offset']!=at or len(block)!=expected or raw[at:at+expected]!=block or block[:4]!=header:
                raise ValueError('INLINE_UNWIND_SAVED_BLOCK')
            if flags&4 and block[-12:].hex()!=node['chain_entry']['raw_hex']:
                raise ValueError('INLINE_UNWIND_SAVED_CHAIN')
            if flags&3 and not 0<int.from_bytes(block[-4:],'little')<reader.IMAGE_SIZE:
                raise ValueError('INLINE_UNWIND_SAVED_HANDLER')
            at+=expected
    if len(raw)!=at or meta['bytes_written']!=at or hashlib.sha256(raw).hexdigest()!=meta['binary_sha256']:
        raise ValueError('INLINE_UNWIND_SAVED_SIZE_OR_HASH')

reader.capture=capture
reader.verify_saved=verify_saved
if __name__=='__main__':session.main()
