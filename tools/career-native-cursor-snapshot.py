"""One fixed Career cursor/OS point comparison; no input, activation or writes.

Career's frozen 18E5BAE/18E5BB8/18E5BD2 passes [game+347CE38]+5F0 to the
verified hover adapter. Read only that widget's header, +200 selector and
+26C float pair. Optional foreground wait samples Win32 only, then performs
one bounded game-memory capture after about one continuous foreground second.
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
spec=importlib.util.spec_from_file_location('native_cursor_parent',ROOT/'tools/career-parent-snapshot.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
layout=parent.layout
REVISION='career_fixed_native_cursor_os_point_v1'
OWNER_KEYS=('controller','list','panel','gui_context','state_context','dispatch')
MANAGER_RVA,CURSOR_OFFSET=0x347CE38,0x5F0
ADAPTER_RVA,ADAPTER_LENGTH=0x178F970,144
ADAPTER_SOURCE=ROOT/'dist/career-click-0.4.34/native-hover-adapter-v1/hover-caller.json'
ADAPTER_SOURCE_SHA='4ef6d7f138ba6089310ad66ea3974abbe514dad954ed65b4067d659c16c5b120'
CALLER_SOURCE=ROOT/'dist/career-mode2-fill-fallthrough-live-20261013-v1/capture/drain.bin'
CALLER_SOURCE_SHA='992e768b511d445d38b06fb140852410ee926c97ba78c22835e75369296c12cc'
CALLER_PINS=((0x18E5BAE,'488b0d8372b901'),(0x18E5BB8,'4881c1f0050000'),(0x18E5BD2,'e8999deaff'))
MAX_BYTES,MAX_READS,MAX_QUERIES,SECONDS=4096,48,48,1.0

class Budget(layout.Budget):
    def gate(self,size):
        if self.total['bytes']+size>MAX_BYTES or self.total['reads']>=MAX_READS or self.queries>MAX_QUERIES:
            raise ValueError('CAREER_NATIVE_CURSOR_BUDGET')
        if self.clock()-self.started>=SECONDS:raise ValueError('CAREER_NATIVE_CURSOR_TIME_BUDGET')
    def read(self,address,size,**options):
        if self.queries>=MAX_QUERIES:raise ValueError('CAREER_NATIVE_CURSOR_QUERY_BUDGET')
        return super().read(address,size,**options)

def evidence():
    caller=CALLER_SOURCE.read_bytes()
    if hashlib.sha256(caller).hexdigest()!=CALLER_SOURCE_SHA:raise ValueError('CAREER_NATIVE_CURSOR_CALLER_SOURCE')
    # Frozen binary starts with a 5B parent CALL, then function 18E5BA0.
    for at,pin in CALLER_PINS:
        start=5+at-0x18E5BA0
        if caller[start:start+len(bytes.fromhex(pin))]!=bytes.fromhex(pin):
            raise ValueError('CAREER_NATIVE_CURSOR_CALLER_SOURCE_PIN')
    frozen=ADAPTER_SOURCE.read_bytes()
    if hashlib.sha256(frozen).hexdigest()!=ADAPTER_SOURCE_SHA:raise ValueError('CAREER_NATIVE_CURSOR_ADAPTER_SOURCE')
    saved=json.loads(frozen);entry=saved['entry'];raw=bytes.fromhex(entry['hex'])
    if (saved.get('status')!='complete' or entry['rva']!=ADAPTER_RVA or len(raw)!=ADAPTER_LENGTH
            or hashlib.sha256(raw).hexdigest()!=entry['sha256']):
        raise ValueError('CAREER_NATIVE_CURSOR_ADAPTER_SOURCE_PIN')
    return raw

def win32_reader():
    """Read-only calls only; deliberately no foreground/focus/cursor setters."""
    import ctypes as C
    from ctypes import wintypes as W
    u=C.WinDLL('user32',use_last_error=True)
    u.GetForegroundWindow.argtypes=[];u.GetForegroundWindow.restype=W.HWND
    u.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)];u.GetWindowThreadProcessId.restype=W.DWORD
    u.GetCursorPos.argtypes=[C.POINTER(W.POINT)];u.GetCursorPos.restype=W.BOOL
    u.ScreenToClient.argtypes=[W.HWND,C.POINTER(W.POINT)];u.ScreenToClient.restype=W.BOOL
    u.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)];u.GetClientRect.restype=W.BOOL
    def read():
        hwnd=u.GetForegroundWindow();pid=W.DWORD()
        if not hwnd or not u.GetWindowThreadProcessId(hwnd,C.byref(pid)):
            return {'foreground':False,'pid':0,'captured_monotonic':time.perf_counter()}
        point=W.POINT();rect=W.RECT()
        if not u.GetCursorPos(C.byref(point)):raise OSError('CAREER_NATIVE_CURSOR_OS_POINT')
        screen=[point.x,point.y]
        if not u.ScreenToClient(hwnd,C.byref(point)) or not u.GetClientRect(hwnd,C.byref(rect)):
            raise OSError('CAREER_NATIVE_CURSOR_OS_CLIENT')
        return {'foreground':True,'pid':pid.value,'hwnd':int(hwnd),'screen_point':screen,
            'client_point':[point.x,point.y],'client_rect':[rect.left,rect.top,rect.right,rect.bottom],
            'client_size':[rect.right-rect.left,rect.bottom-rect.top],'captured_monotonic':time.perf_counter()}
    return read

def wait_foreground(pid,seconds,read,clock=time.perf_counter,sleep=time.sleep):
    if not isinstance(seconds,(float,int)) or not math.isfinite(seconds) or not 0<=seconds<=60:
        raise ValueError('CAREER_NATIVE_CURSOR_WAIT_RANGE')
    if seconds==0:return {'waited':False}
    started=clock();since=None;handle=None
    while True:
        now=clock()
        if now-started>=seconds:raise ValueError('CAREER_NATIVE_CURSOR_FOREGROUND_TIMEOUT')
        observed=read()
        if observed.get('foreground') and observed.get('pid')==pid:
            if since is None or handle!=observed.get('hwnd'):since=now;handle=observed.get('hwnd')
            if now-since>=1.0:return {'waited':True,'seconds':now-started,'foreground_seconds':now-since}
        else:since=None;handle=None
        sleep(min(.1,max(.001,seconds-(clock()-started))))

def check_os(value,pid):
    if not value.get('foreground') or value.get('pid')!=pid:raise ValueError('CAREER_NATIVE_CURSOR_GAME_NOT_FOREGROUND')
    if any(type(v)is not int for v in value.get('client_point',[])) or len(value.get('client_point',[]))!=2:
        raise ValueError('CAREER_NATIVE_CURSOR_OS_INVALID')
    size=value.get('client_size',[])
    if len(size)!=2 or any(type(v)is not int or v<=0 for v in size):raise ValueError('CAREER_NATIVE_CURSOR_OS_INVALID')

def capture(process,identity,source,os_read,adapter_pin,clock=time.perf_counter):
    if source.get('status')!='complete' or not source.get('headers_stable') or source['identity']!=identity:
        raise ValueError('CAREER_NATIVE_CURSOR_SOURCE')
    if len(adapter_pin)!=ADAPTER_LENGTH:raise ValueError('CAREER_NATIVE_CURSOR_ADAPTER_PIN_LENGTH')
    b=Budget(process,identity,clock);before,why=layout.locate(b)
    if not before:raise parent.NotVisible(why,b)
    if any(before[k]!=source['owner_before'][k]for k in OWNER_KEYS):raise ValueError('CAREER_NATIVE_CURSOR_OWNER_CHANGED')
    layout.verify_code(b)
    for rva,hex_ in CALLER_PINS:
        pin=bytes.fromhex(hex_)
        if b.read(identity['game_base']+rva,len(pin),image=True,code=True)!=pin:raise ValueError('CAREER_NATIVE_CURSOR_CALLER_PIN')
    if b.read(identity['game_base']+ADAPTER_RVA,ADAPTER_LENGTH,image=True,code=True)!=adapter_pin:
        raise ValueError('CAREER_NATIVE_CURSOR_ADAPTER_PIN')
    os_before=os_read();check_os(os_before,source['game_pid'])
    manager=b.ptr(identity['game_base']+MANAGER_RVA,image=True)
    if not layout.pointer(manager):raise ValueError('CAREER_NATIVE_CURSOR_MANAGER')
    at=manager+CURSOR_OFFSET
    raw=b.read(at,256);selector=b.ptr(at+0x200);point=b.read(at+0x26C,8)
    flags=struct.unpack_from('<I',raw)[0];kind=(flags>>18)&15
    if not flags or not kind:raise ValueError('CAREER_NATIVE_CURSOR_WIDGET')
    local=list(struct.unpack_from('<ff',raw,4));projected=list(struct.unpack('<ff',point))
    if not all(math.isfinite(v)for v in local+projected):raise ValueError('CAREER_NATIVE_CURSOR_NONFINITE')
    branch='field_26c' if selector in (manager+0x160,manager+0x288) else 'local_position_4'
    selected=projected if branch=='field_26c'else local
    # Fixed identity/point rereads, no follow-up pointers or UI traversal.
    if b.ptr(identity['game_base']+MANAGER_RVA,image=True)!=manager or b.read(at,256)!=raw or b.ptr(at+0x200)!=selector or b.read(at+0x26C,8)!=point:
        raise ValueError('CAREER_NATIVE_CURSOR_CHANGED')
    os_after=os_read();check_os(os_after,source['game_pid'])
    if os_before['hwnd']!=os_after['hwnd'] or os_before['client_size']!=os_after['client_size']:
        raise ValueError('CAREER_NATIVE_CURSOR_OS_WINDOW_CHANGED')
    after,why=layout.locate(b)
    if not after or any(after[k]!=before[k]for k in OWNER_KEYS) or after['header']!=before['header']:
        raise ValueError('CAREER_NATIVE_CURSOR_PAGE_CHANGED')
    return {'status':'complete','source_revision':REVISION,'captured_at':datetime.now(timezone.utc).isoformat(),
        'identity':identity,'owner_before':before,'owner_after':after,'manager':manager,'cursor':at,
        'cursor_header_hex':raw.hex(),'cursor_kind':kind,'selector':selector,'selector_offset':selector-manager,
        'local_position':local,'field_26c':projected,'selected_branch':branch,'selected_native_point':selected,
        'os_before':os_before,'os_after':os_after,'os_point_stable':os_before['client_point']==os_after['client_point'],
        'active_read_bytes':b.total['bytes'],'active_read_calls':b.total['reads'],'active_query_calls':b.queries,
        'read_records':b.total['records'],'native_called':False,'native_written':False,'account_modified':False,
        'input_sent':False,'atomic':False,'coordinate_equivalence_proven':False,
        'limits':{'bytes':MAX_BYTES,'reads':MAX_READS,'queries':MAX_QUERIES,'seconds':SECONDS}}

def run(source_path,output,wait_seconds=0,*,deps=None,os_read=None,clock=time.perf_counter,sleep=time.sleep):
    source_path,output=Path(source_path).resolve(),Path(output).resolve()
    source_raw=source_path.read_bytes();source=json.loads(source_raw);pin=evidence()
    if not math.isfinite(wait_seconds) or not 0<=wait_seconds<=60:raise ValueError('CAREER_NATIVE_CURSOR_WAIT_RANGE')
    if output.exists():raise ValueError('CAREER_NATIVE_CURSOR_OUTPUT_EXISTS')
    output.mkdir(parents=True)
    try:
        deps=layout.dependencies()if deps is None else deps
        stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(source['game_pid'],):raise ValueError('CAREER_NATIVE_CURSOR_PID_CHANGED')
        pid=pids[0];identity=deps['resolve_game'](pid);deps['validate_identity'](identity,stamps)
        os_read=win32_reader()if os_read is None else os_read
        if wait_seconds:print('Waiting for target Game foreground for one continuous second; no input sent.',flush=True)
        waited=wait_foreground(pid,wait_seconds,os_read,clock,sleep)
        with deps['Process'](pid)as process:r=capture(process,identity,source,os_read,pin,clock)
        final=deps['resolve_game'](pid);deps['validate_identity'](final,stamps)
        if final!=identity or tuple(deps['game_processes']())!=(pid,):raise ValueError('CAREER_NATIVE_CURSOR_MODULE_CHANGED')
        r.update(game_pid=pid,source_path=str(source_path),source_sha256=hashlib.sha256(source_raw).hexdigest(),
            caller_source_sha256=CALLER_SOURCE_SHA,adapter_source_sha256=ADAPTER_SOURCE_SHA,foreground_wait=waited)
        path=output/'cursor.json';path.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n','utf8')
        status={k:r[k]for k in ('status','selected_branch','selected_native_point','os_point_stable','active_read_bytes','active_read_calls')}
        status.update(json_path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        (output/'status.json').write_text(json.dumps(status,indent=2)+'\n','utf8');return status
    except Exception as e:
        (output/'status.json').write_text(json.dumps({'status':'failed','error':str(e),'native_called':False,'native_written':False,'input_sent':False},indent=2)+'\n','utf8')
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--wait-for-game-seconds',type=float,default=0);a=p.parse_args()
    try:print(json.dumps(run(a.source,a.output,a.wait_for_game_seconds)))
    except (ValueError,OSError,parent.NotVisible)as e:p.exit(1,str(e)+'\n')
