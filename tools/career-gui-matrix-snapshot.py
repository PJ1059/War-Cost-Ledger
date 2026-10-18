"""One bounded snapshot of proven engine-Gui +10..8F, including pose +28..67.

Source is the frozen gui_move_matrix entry. Does not call or modify a GUI.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('career_gui_matrix_entry',ROOT/'tools/career-text-render-entry-snapshot.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
layout=entry.layout
REVISION='career_owned_gui_pose_128_v1'
SETTER=0x25F5F0
PREFIX='4c8bdc534881ecd00000000f10028b410441b9080000008944242441b898000000488b41080f114128c74424200a0000000f104a10410f2973e80f1149380f1042200f1141480f104a30498d53d80f114958'

def capture(process,identity,source,clock=time.perf_counter):
    if (source.get('status')!='complete' or source.get('stage')!='gui_move_matrix'
            or source['entry']['module']!='exe' or source['entry']['rva']!=SETTER
            or not source['entry']['hex'].startswith(PREFIX) or source['identity']!=identity):
        raise ValueError('CAREER_GUI_POSE_SOURCE')
    b=entry.Budget(process,identity,clock)
    before,why=layout.locate(b)
    if not before:raise entry.parent.NotVisible(why,b)
    keys=('controller','list','panel','gui_context','state_context','dispatch')
    if any(before[k]!=source['owner_before'][k]for k in keys):raise ValueError('CAREER_GUI_POSE_OWNER_CHANGED')
    layout.verify_code(b)
    pin=bytes.fromhex(PREFIX)
    if b.read(identity['exe_base']+SETTER,len(pin),code=True)!=pin:raise ValueError('CAREER_GUI_POSE_SETTER_PIN')
    gui=b.ptr(before['gui_context']+8)
    if gui!=source['pointers']['engine_gui'] or not layout.pointer(gui):raise ValueError('CAREER_GUI_POSE_GUI_CHANGED')
    raw=b.read(gui+0x10,128)
    matrix=list(struct.unpack_from('<16f',raw,0x28-0x10))
    if not all(math.isfinite(v)for v in matrix):raise ValueError('CAREER_GUI_POSE_NONFINITE')
    if b.read(gui+0x10,128)!=raw or b.ptr(before['gui_context']+8)!=gui:raise ValueError('CAREER_GUI_POSE_CHANGED')
    after,why=layout.locate(b)
    if not after or any(after[k]!=before[k]for k in keys):raise ValueError('CAREER_GUI_POSE_PAGE_CHANGED')
    return {'status':'complete','source_revision':REVISION,'captured_at':datetime.now(timezone.utc).isoformat(),
        'identity':identity,'owner_before':before,'owner_after':after,'engine_gui':gui,'field_start':0x10,'field_length':128,
        'raw_hex':raw.hex(),'pose_offset':0x28,'pose_matrix':matrix,'dimensions_offsets':[0x14,0x18],
        'dimensions':list(struct.unpack_from('<ff',raw,4)),'active_read_bytes':b.total['bytes'],
        'active_read_calls':b.total['reads'],'active_query_calls':b.queries,'read_records':b.total['records'],
        'bytes_stable':True,'native_called':False,'native_written':False,'account_modified':False,
        'limits':{'bytes':entry.MAX_BYTES,'reads':entry.MAX_READS,'queries':entry.MAX_QUERIES,'seconds':entry.SECONDS}}

def run(source_path,output):
    source_path,output=Path(source_path).resolve(),Path(output).resolve();source=json.loads(source_path.read_text('utf8'))
    if output.exists():raise ValueError('CAREER_GUI_POSE_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    try:
        deps=layout.dependencies();stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(source['game_pid'],):raise ValueError('CAREER_GUI_POSE_PID_CHANGED')
        pid=pids[0];identity=entry.module_sources(pid);deps['validate_identity'](identity,stamps)
        with deps['Process'](pid) as process:r=capture(process,identity,source)
        final=entry.module_sources(pid);deps['validate_identity'](final,stamps)
        if final!=identity or tuple(deps['game_processes']())!=(pid,):raise ValueError('CAREER_GUI_POSE_MODULE_CHANGED')
        r.update(game_pid=pid,source_path=str(source_path),source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest())
        path=output/'gui-pose.json';path.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n','utf8')
        status={k:r[k]for k in ('status','active_read_bytes','active_read_calls','pose_matrix','dimensions')}
        status.update(json_path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (output/'status.json').write_text(json.dumps(status,indent=2)+'\n','utf8');return status
    except Exception as e:
        (output/'status.json').write_text(json.dumps({'status':'failed','error':str(e),'native_written':False})+'\n','utf8');raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:print(json.dumps(run(a.source,a.output)))
    except (ValueError,OSError,entry.parent.NotVisible)as e:p.exit(1,str(e)+'\n')
