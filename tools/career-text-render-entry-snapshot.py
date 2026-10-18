"""Read the visible Career GUI's one proven text-create API entry, exactly 512B.

No tree traversal, projection guessing, native invocation, wait or writes.
The source parent snapshot fixes ownership; five frozen caller PINs fix the
context+8 / API-root+D0 / GUI-table+1B0 chain. All reads share one budget.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('text_entry_parent',ROOT/'tools/career-parent-snapshot.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
layout=parent.layout
REVISION='career_text_create_one_entry_512_v1'
API_GLOBAL=0x3326308
CODE_BYTES=512
MAX_BYTES,MAX_READS,MAX_QUERIES,SECONDS=4096,64,65,1.0
PINS=((0x143DA60,'4c8b9bf8000000'),(0x143DAF4,'488b050d88ee01'),
      (0x143DB04,'488b88d0000000'),(0x143DB2C,'4c8b91b0010000'),
      (0x143DB54,'498b4b08'))

class Budget(layout.Budget):
    def gate(self,size):
        if self.total['bytes']+size>MAX_BYTES or self.total['reads']>=MAX_READS or self.queries>MAX_QUERIES:
            raise ValueError('CAREER_TEXT_ENTRY_BUDGET')
        if self.clock()-self.started>=SECONDS:raise ValueError('CAREER_TEXT_ENTRY_TIME_BUDGET')

def module_sources(pid):
    from fire_code_windows import _modules
    rows=_modules(pid)
    result={}
    for role,name in [('game','game.dll'),('exe','helldivers2.exe')]:
        matches=[row for row in rows if row['name'].casefold()==name]
        if len(matches)!=1:raise ValueError('CAREER_TEXT_ENTRY_MODULE_AMBIGUOUS')
        row=matches[0]
        for key in ('base','size','path'):result[role+'_'+key]=row[key]
    return result

def capture(process,identity,source,clock=time.perf_counter,submit_source=None,prepare_source=None,move_source=None):
    if source.get('status')!='complete' or not source.get('headers_stable'):
        raise ValueError('CAREER_TEXT_ENTRY_SOURCE_INCOMPLETE')
    if any(identity.get(k)!=v for k,v in source['identity'].items()):
        raise ValueError('CAREER_TEXT_ENTRY_MODULE_CHANGED')
    for role,expected in [('game',layout.IMAGE_SIZE),('exe',0x39E8000)]:
        if not layout.pointer(identity.get(role+'_base',0)) or identity[role+'_base']%4096 or identity.get(role+'_size')!=expected:
            raise ValueError('CAREER_TEXT_ENTRY_MODULE_INVALID')
    b=Budget(process,identity,clock)
    before,why=layout.locate(b)
    if not before:raise parent.NotVisible(why,b)
    owner_keys=('controller','list','panel','gui_context','state_context','dispatch')
    if any(before[k]!=source['owner_before'][k] for k in owner_keys):
        raise ValueError('CAREER_TEXT_ENTRY_OWNER_CHANGED')
    layout.verify_code(b)
    for at,hex_ in PINS:
        if b.read(identity['game_base']+at,len(bytes.fromhex(hex_)),image=True,code=True)!=bytes.fromhex(hex_):
            raise ValueError('CAREER_TEXT_ENTRY_CALLER_PIN')
    def chain():
        gui=b.ptr(before['gui_context']+8)
        api=b.ptr(identity['game_base']+API_GLOBAL,image=True)
        if not layout.pointer(gui) or not layout.pointer(api):raise ValueError('CAREER_TEXT_ENTRY_POINTER')
        table=b.ptr(api+0xD0)
        if not layout.pointer(table):raise ValueError('CAREER_TEXT_ENTRY_POINTER')
        entry=b.ptr(table+0x1B0)
        if not layout.pointer(entry,False):raise ValueError('CAREER_TEXT_ENTRY_POINTER')
        return {'engine_gui':gui,'api_root':api,'gui_api':table,'text_create':entry}
    pointers=chain();entry=pointers['text_create']
    if submit_source is not None or prepare_source is not None or move_source is not None:
        prior=move_source or prepare_source or submit_source
        previous_stage,previous_rva=(('gui_text_prepare',0x26D310) if move_source else
            ('gui_text_submit',0x267230) if prepare_source else ('text_create',0x340C30))
        if (prior.get('status')!='complete' or prior.get('source_revision')!=REVISION
                or prior.get('stage','text_create')!=previous_stage or prior['identity']!=identity
                or prior['pointers']!=pointers or prior['entry']['module']!='exe'
                or prior['entry']['rva']!=previous_rva):
            raise ValueError('CAREER_TEXT_ENTRY_SUBMIT_SOURCE')
        # Sole Gui-consuming direct CALL in each captured submission wrapper.
        # Move uses the public HUD+ WorldPose contract, not a text helper.
        call_at,pin,target=((0x341ED0,'f30f105918f30f105114e911d7f1ff',0x25F5F0) if move_source else
            (0x26726B,'e8a0600000',0x26D310) if prepare_source else (0x340DB4,'e87764f2ff',0x267230))
        if b.read(identity['exe_base']+call_at,len(bytes.fromhex(pin)),code=True)!=bytes.fromhex(pin):
            raise ValueError('CAREER_TEXT_ENTRY_SUBMIT_CALL_PIN')
        entry=identity['exe_base']+target
    roles=[role for role in ('game','exe') if identity[role+'_base']<=entry<entry+CODE_BYTES<=identity[role+'_base']+identity[role+'_size']]
    if len(roles)!=1:raise ValueError('CAREER_TEXT_ENTRY_OUTSIDE_IMAGES')
    b.queries+=1;region=process.query(entry)
    if region['type']!=0x1000000:raise ValueError('CAREER_TEXT_ENTRY_NOT_IMAGE')
    raw=b.read(entry,CODE_BYTES,code=True)
    if chain()!=pointers:raise ValueError('CAREER_TEXT_ENTRY_CHAIN_CHANGED')
    after,why=layout.locate(b)
    if not after or any(after[k]!=before[k] for k in owner_keys):raise ValueError('CAREER_TEXT_ENTRY_PAGE_CHANGED')
    return {'status':'complete','source_revision':REVISION,'captured_at':datetime.now(timezone.utc).isoformat(),
        'identity':identity,'owner_before':before,'owner_after':after,'pointers':pointers,
        'stage':'gui_move_matrix' if move_source is not None else 'gui_text_prepare' if prepare_source is not None else 'gui_text_submit' if submit_source is not None else 'text_create',
        'entry':{'address':entry,'module':roles[0],'rva':entry-identity[roles[0]+'_base'],
                 'length':CODE_BYTES,'region':region,'sha256':hashlib.sha256(raw).hexdigest(),'hex':raw.hex()},
        'active_read_bytes':b.total['bytes'],'active_read_calls':b.total['reads'],'active_query_calls':b.queries,
        'read_records':b.total['records'],'pointer_chain_stable':True,'page_visible':True,
        'native_called':False,'native_written':False,'account_modified':False,
        'limits':{'bytes':MAX_BYTES,'reads':MAX_READS,'queries':MAX_QUERIES,'seconds':SECONDS,
                  'code_bytes':CODE_BYTES,'chain_bytes_per_pass':32}}

def run(source_path,output,*,deps=None,clock=time.perf_counter,submit_path=None,prepare_path=None,move_path=None):
    source_path,output=Path(source_path).resolve(),Path(output).resolve()
    source=json.loads(source_path.read_text('utf8'))
    prior=None
    if sum(bool(v)for v in (submit_path,prepare_path,move_path))>1:raise ValueError('CAREER_TEXT_ENTRY_SELECT_ONE_STAGE')
    if submit_path or prepare_path or move_path:
        prior=json.loads(Path(submit_path or prepare_path or move_path).read_text('utf8'))
        if prior.get('source_sha256')!=hashlib.sha256(source_path.read_bytes()).hexdigest() or prior.get('game_pid')!=source['game_pid']:
            raise ValueError('CAREER_TEXT_ENTRY_SUBMIT_SOURCE')
    if output.exists():raise ValueError('CAREER_TEXT_ENTRY_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    try:
        if deps is None:
            deps=layout.dependencies();deps['resolve_sources']=module_sources
        stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(source['game_pid'],):raise ValueError('CAREER_TEXT_ENTRY_PID_CHANGED')
        pid=pids[0];identity=deps['resolve_sources'](pid);deps['validate_identity'](identity,stamps)
        with deps['Process'](pid) as process:
            r=capture(process,identity,source,clock,submit_source=prior if submit_path else None,
                prepare_source=prior if prepare_path else None,move_source=prior if move_path else None)
        final=deps['resolve_sources'](pid);deps['validate_identity'](final,stamps)
        if final!=identity or tuple(deps['game_processes']())!=(pid,):raise ValueError('CAREER_TEXT_ENTRY_MODULE_CHANGED')
        r.update(game_pid=pid,source_path=str(source_path),source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest())
        (output/'text-create.bin').write_bytes(bytes.fromhex(r['entry']['hex']))
        path=output/'text-create.json';path.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n','utf8')
        status={k:r[k] for k in ('status','active_read_bytes','active_read_calls','active_query_calls')}
        status.update(json_path=str(path),module=r['entry']['module'],rva=hex(r['entry']['rva']),
                      sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (output/'status.json').write_text(json.dumps(status,indent=2)+'\n','utf8')
        return status
    except Exception as e:
        (output/'status.json').write_text(json.dumps({'status':'failed','error':str(e),'native_written':False,'native_called':False},indent=2)+'\n','utf8')
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--submit-from',help='Fixed second stage: exe 0x267230 reached by observed CALL at 0x340DB4')
    p.add_argument('--prepare-from',help='Fixed third stage: exe 0x26D310 reached by observed CALL at 0x26726B')
    p.add_argument('--gui-move-from',help='Public HUD+ matrix setter: pinned exe 0x341ED0 tail-jumps to 0x25F5F0')
    a=p.parse_args()
    try:print(json.dumps(run(a.source,a.output,submit_path=a.submit_from,prepare_path=a.prepare_from,move_path=a.gui_move_from)))
    except (ValueError,OSError,parent.NotVisible) as e:p.exit(1,str(e)+'\n')
