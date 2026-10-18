"""Read one fixed 1KiB native card-hover caller; do not follow its operands.

The SDK names game+0x18D0690 as the caller of contains-point at 0x144D320.
This snapshot only establishes the caller's argument provenance. It does not
assume that any discovered coordinate field also belongs to the Career GUI.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hover_caller_parent',ROOT/'tools/career-parent-snapshot.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
layout=parent.layout
REVISION='career_known_card_hover_caller_1k_v1'
TARGET_RVA,CODE_BYTES=0x18D0690,1024
CONTAINS_RVA,CONTAINS_PIN=0x144D320,bytes.fromhex('4883ec78f30f10a984000000f30f1091')
MAX_BYTES,MAX_READS,MAX_QUERIES,SECONDS=4096,48,48,1.0
OWNER_KEYS=('controller','list','panel','gui_context','state_context','dispatch')
REFERENCE='HD2Runtime dcd996d docs/custom-stratagems.md:2875-2876'
REFERENCE_SHA='525e0a2e48fd9f39680c3eb76365ddc8dbb9906b32f8fca2676a9f8e033caa55'
ADAPTER_RVA,ADAPTER_BYTES,ADAPTER_CALL=0x178F970,144,0x18D074C

class Budget(layout.Budget):
    def gate(self,size):
        if self.total['bytes']+size>MAX_BYTES or self.total['reads']>=MAX_READS or self.queries>MAX_QUERIES:
            raise ValueError('CAREER_HOVER_CALLER_BUDGET')
        if self.clock()-self.started>=SECONDS:raise ValueError('CAREER_HOVER_CALLER_TIME_BUDGET')
    def read(self,address,size,**options):
        if self.queries>=MAX_QUERIES:raise ValueError('CAREER_HOVER_CALLER_QUERY_BUDGET')
        return super().read(address,size,**options)

def capture(process,identity,source,clock=time.perf_counter,adapter_source=None):
    if source.get('status')!='complete' or not source.get('headers_stable'):
        raise ValueError('CAREER_HOVER_CALLER_SOURCE_INCOMPLETE')
    if identity!=source['identity']:raise ValueError('CAREER_HOVER_CALLER_MODULE_CHANGED')
    b=Budget(process,identity,clock)
    before,why=layout.locate(b)
    if not before:raise parent.NotVisible(why,b)
    if any(before[k]!=source['owner_before'][k] for k in OWNER_KEYS):
        raise ValueError('CAREER_HOVER_CALLER_OWNER_CHANGED')
    layout.verify_code(b)
    if b.read(identity['game_base']+CONTAINS_RVA,len(CONTAINS_PIN),image=True,code=True)!=CONTAINS_PIN:
        raise ValueError('CAREER_HOVER_CALLER_CONTAINS_PIN')
    target,length=TARGET_RVA,CODE_BYTES
    if adapter_source is not None:
        prior=adapter_source
        if (prior.get('status')!='complete' or prior.get('source_revision')!=REVISION
                or prior['identity']!=identity or prior['entry']['rva']!=TARGET_RVA
                or prior['entry']['length']!=CODE_BYTES):
            raise ValueError('CAREER_HOVER_CALLER_ADAPTER_SOURCE')
        code=bytes.fromhex(prior['entry']['hex'])
        if hashlib.sha256(code).hexdigest()!=prior['entry']['sha256']:
            raise ValueError('CAREER_HOVER_CALLER_ADAPTER_SOURCE_SHA')
        call=code[ADAPTER_CALL-TARGET_RVA:ADAPTER_CALL-TARGET_RVA+5]
        if len(call)!=5 or call[0]!=0xE8 or ADAPTER_CALL+5+struct.unpack('<i',call[1:])[0]!=ADAPTER_RVA:
            raise ValueError('CAREER_HOVER_CALLER_ADAPTER_CALL')
        if b.read(identity['game_base']+ADAPTER_CALL,5,image=True,code=True)!=call:
            raise ValueError('CAREER_HOVER_CALLER_ADAPTER_CALL_CHANGED')
        target,length=ADAPTER_RVA,ADAPTER_BYTES
    at=identity['game_base']+target
    raw=b.read(at,length,image=True,code=True)
    if b.read(at,16,image=True,code=True)!=raw[:16]:
        raise ValueError('CAREER_HOVER_CALLER_HEAD_CHANGED')
    after,why=layout.locate(b)
    if not after or any(after[k]!=before[k] for k in OWNER_KEYS) or after['header']!=before['header']:
        raise ValueError('CAREER_HOVER_CALLER_PAGE_CHANGED')
    return {'status':'complete','source_revision':REVISION,'captured_at':datetime.now(timezone.utc).isoformat(),
        'identity':identity,'owner_before':before,'owner_after':after,
        'reference':REFERENCE,'reference_sha256':REFERENCE_SHA,
        'entry':{'rva':target,'address':at,'length':length,'hex':raw.hex(),
                 'sha256':hashlib.sha256(raw).hexdigest()},
        'active_read_bytes':b.total['bytes'],'active_read_calls':b.total['reads'],'active_query_calls':b.queries,
        'read_records':b.total['records'],'native_called':False,'native_written':False,'account_modified':False,
        'argument_source_proven':False,'career_coordinate_applicability_proven':False,'atomic':False,
        'limits':{'bytes':MAX_BYTES,'reads':MAX_READS,'queries':MAX_QUERIES,'seconds':SECONDS,'code_bytes':length}}

def run(source_path,output,*,deps=None,clock=time.perf_counter,adapter_path=None):
    source_path,output=Path(source_path).resolve(),Path(output).resolve()
    source_raw=source_path.read_bytes();source=json.loads(source_raw)
    prior=None
    if adapter_path:
        prior=json.loads(Path(adapter_path).read_text('utf8'))
        if prior.get('game_pid')!=source['game_pid'] or prior.get('source_sha256')!=hashlib.sha256(source_raw).hexdigest():
            raise ValueError('CAREER_HOVER_CALLER_ADAPTER_SOURCE')
    if output.exists():raise ValueError('CAREER_HOVER_CALLER_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    try:
        deps=layout.dependencies() if deps is None else deps
        stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(source['game_pid'],):raise ValueError('CAREER_HOVER_CALLER_PID_CHANGED')
        pid=pids[0];identity=deps['resolve_game'](pid);deps['validate_identity'](identity,stamps)
        with deps['Process'](pid) as process:r=capture(process,identity,source,clock,adapter_source=prior)
        final=deps['resolve_game'](pid);deps['validate_identity'](final,stamps)
        if final!=identity or tuple(deps['game_processes']())!=(pid,):raise ValueError('CAREER_HOVER_CALLER_MODULE_CHANGED')
        r.update(game_pid=pid,source_path=str(source_path),source_sha256=hashlib.sha256(source_raw).hexdigest())
        (output/'hover-caller.bin').write_bytes(bytes.fromhex(r['entry']['hex']))
        path=output/'hover-caller.json';path.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n','utf8')
        status={k:r[k]for k in ('status','active_read_bytes','active_read_calls','active_query_calls')}
        status.update(json_path=str(path),rva=hex(r['entry']['rva']),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (output/'status.json').write_text(json.dumps(status,indent=2)+'\n','utf8');return status
    except Exception as e:
        (output/'status.json').write_text(json.dumps({'status':'failed','error':str(e),'native_called':False,'native_written':False},indent=2)+'\n','utf8')
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--adapter-from',help='Only the source-proven CALL 18D074C target 178F970; exactly 144B')
    a=p.parse_args()
    try:print(json.dumps(run(a.source,a.output,adapter_path=a.adapter_from)))
    except (ValueError,OSError,parent.NotVisible) as e:p.exit(1,str(e)+'\n')
