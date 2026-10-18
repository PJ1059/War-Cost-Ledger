"""One bounded read of our already captured Career frame and its text children.

This does not discover a new tree: the source snapshot fixes the current PID,
module identity and exact attached 420px-wide MOD frame. No game calls/writes.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import struct
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_controls_parent', ROOT/'tools/career-parent-snapshot.py')
parent = importlib.util.module_from_spec(spec); spec.loader.exec_module(parent)
layout = parent.layout
REVISION = 'career_own_controls_24_headers_v1'
MAX_CHILDREN, MAX_BYTES, MAX_READS, MAX_QUERIES, SOFT_SECONDS = 24, 24576, 128, 128, 1.0
TARGETS = {'累计战果': 'tab_collection', '历史对局': 'tab_history', '下一局': 'history_next'}


class Budget(layout.Budget):
    def gate(self, size):
        if self.total['bytes']+size>MAX_BYTES or self.total['reads']>=MAX_READS or self.queries>MAX_QUERIES:
            raise ValueError('CAREER_CONTROLS_BUDGET')
        if self.clock()-self.started>=SOFT_SECONDS:
            raise ValueError('CAREER_CONTROLS_TIME_BUDGET')
    def read(self, address, size, **options):
        if self.queries>=MAX_QUERIES: raise ValueError('CAREER_CONTROLS_QUERY_BUDGET')
        return super().read(address, size, **options)


def selected_frame(source):
    if source.get('status')!='complete' or not source.get('headers_stable'):
        raise ValueError('CAREER_CONTROLS_SOURCE_INCOMPLETE')
    root=source['owner_before']['controller']+0x4DAF8
    candidates=[n for n in source['nodes'] if n['kind']==1 and n['parent']==root
                and n['geometry']['width_at24']==420 and n['geometry']['height_at28']>=160]
    if len(candidates)!=1: raise ValueError('CAREER_CONTROLS_SOURCE_AMBIGUOUS')
    return candidates[0]


def fields(raw):
    result=parent.geometry(raw)
    for name, offset in {'local_x':4,'local_y':8,'local_width':12,'local_height':16,
                         'scale_x':20,'scale_y':24,'size_factor_x':28,'size_factor_y':32,
                         'anchor_x':44,'anchor_y':48,'rotation_pivot_x':52,'rotation_pivot_y':56,
                         'pivot_x':60,'pivot_y':64}.items():
        result[name]=struct.unpack_from('<f',raw,offset)[0]
    return result


def capture(process, identity, source, clock=time.perf_counter, continuation=None):
    chosen=selected_frame(source)
    if source['identity']!=identity: raise ValueError('CAREER_CONTROLS_SOURCE_MODULE_CHANGED')
    budget=Budget(process,identity,clock)
    owner,why=layout.locate(budget)
    if not owner: raise parent.NotVisible(why,budget)
    for key in ('controller','gui_context','list','panel'):
        if owner[key]!=source['owner_before'][key]: raise ValueError('CAREER_CONTROLS_SOURCE_OWNER_CHANGED')
    layout.verify_code(budget)
    at=chosen['address']; root_at=owner['controller']+0x4DAF8
    # Saved evidence places the MOD frame first in this root's address-sorted
    # child chain. Require that exact live attachment rather than following an
    # old allocation whose parent field survived page teardown.
    root_header=budget.read(root_at,256)
    root_info=parent.validate(root_header,owner['gui_context'],owner['controller']+0xA0)
    if root_info['kind']!=1 or root_info['child']!=at:
        raise ValueError('CAREER_CONTROLS_FRAME_NOT_ATTACHED')
    raw=budget.read(at,256)
    info=parent.validate(raw,owner['gui_context'],owner['controller']+0x4DAF8)
    if info['kind']!=1 or fields(raw)!=fields(bytes.fromhex(chosen['header_hex'])):
        raise ValueError('CAREER_CONTROLS_FRAME_CHANGED')
    original=raw
    cursor=info['child']; seen=set(); children=[]; found={}; segment=1
    if continuation is not None:
        if (continuation.get('status')!='complete' or continuation.get('source_revision')!=REVISION
                or continuation.get('identity')!=identity or continuation.get('segment',1)!=1
                or continuation.get('frame',{}).get('address')!=at
                or not continuation.get('child_limit_reached') or not continuation.get('next_unread')
                or len(continuation.get('children',[]))!=MAX_CHILDREN):
            raise ValueError('CAREER_CONTROLS_CONTINUATION_SOURCE')
        previous_frame=bytes.fromhex(continuation['frame']['header_hex'])
        if fields(previous_frame)!=fields(raw) or previous_frame[0xE0:0x100]!=raw[0xE0:0x100]:
            raise ValueError('CAREER_CONTROLS_CONTINUATION_FRAME_CHANGED')
        # One fixed predecessor proves the saved next pointer remains linked.
        # The previous 24 children are not traversed or reread.
        predecessor=continuation['children'][-1]
        header=budget.read(predecessor['address'],256)
        linked=parent.validate(header,owner['gui_context'],at)
        if (linked['kind']!=predecessor['kind'] or linked['next']!=continuation['next_unread']
                or linked['child']!=predecessor['child']):
            raise ValueError('CAREER_CONTROLS_CONTINUATION_LINK_CHANGED')
        seen={n['address'] for n in continuation['children']}
        cursor=continuation['next_unread'];segment=2
    while cursor and len(children)<MAX_CHILDREN:
        if cursor in seen: raise ValueError('CAREER_CONTROLS_CYCLE')
        seen.add(cursor)
        header=budget.read(cursor,256); child=parent.validate(header,owner['gui_context'],at)
        row={'address':cursor,**child,'header_hex':header.hex(),'geometry':fields(header)}
        children.append(row)
        # Images are terminal. Only a direct MOD frame's single text child is
        # followed, and only the fixed inline UTF-8 prefix is inspected.
        if child['kind']==1 and child['child']:
            text_at=child['child']; text_header=budget.read(text_at,256)
            text_info=parent.validate(text_header,owner['gui_context'],cursor)
            if text_info['kind']!=9 or text_info['next'] or text_info['child']:
                raise ValueError('CAREER_CONTROLS_TEXT_SHAPE')
            label=budget.read(text_at+0x11C,24)
            caption=label.split(b'\0',1)[0].decode('utf8',errors='replace')
            text={'address':text_at,**text_info,'header_hex':text_header.hex(),
                  'label_prefix_hex':label.hex(),'label':caption,'geometry':fields(text_header)}
            row['text']=text
            if caption in TARGETS:
                font=budget.read(text_at+0x444,60)
                text['font_hex']=font.hex()
                text['requested_height'],text['effective_height'],text['spacing'],text['scroll_offset']=struct.unpack_from('<ffff',font)
                text['layout_flags']=struct.unpack_from('<I',font,0x468-0x444)[0]
                text['font_resource']=struct.unpack_from('<Q',font,0x470-0x444)[0]
                found[TARGETS[caption]]=row
        cursor=child['next']
        if len(found)==len(TARGETS): break
    final=budget.read(at,256)
    if final!=original: raise ValueError('CAREER_CONTROLS_FRAME_CHANGED')
    final_root=parent.validate(budget.read(root_at,256),owner['gui_context'],owner['controller']+0xA0)
    if final_root['kind']!=1 or final_root['child']!=at:
        raise ValueError('CAREER_CONTROLS_FRAME_NOT_ATTACHED')
    after,why=layout.locate(budget)
    if not after or any(after[k]!=owner[k] for k in ('controller','list','gui_context','state_context')):
        raise ValueError('CAREER_CONTROLS_OWNER_CHANGED')
    return {'status':'complete','source_revision':REVISION,'captured_at':datetime.now(timezone.utc).isoformat(),
            'identity':identity,'owner_before':owner,'owner_after':after,'frame':{'address':at,'header_hex':original.hex()},
            'segment':segment,'children':children,'found':found,'next_unread':cursor,'child_limit_reached':bool(cursor and len(children)==MAX_CHILDREN),
            'active_read_bytes':budget.total['bytes'],'active_read_calls':budget.total['reads'],
            'active_query_calls':budget.queries,'read_records':budget.total['records'],
            'native_called':False,'native_written':False,'account_modified':False,'atomic':False,
            'limits':{'children':MAX_CHILDREN,'bytes':MAX_BYTES,'reads':MAX_READS,'queries':MAX_QUERIES,'seconds':SOFT_SECONDS}}


def run(source_path, folder, *, deps=None, clock=time.perf_counter, continuation_path=None):
    source_path,folder=Path(source_path).resolve(),Path(folder).resolve()
    source=json.loads(source_path.read_text('utf8'));selected_frame(source)
    continuation=None
    if continuation_path:
        continuation_path=Path(continuation_path).resolve()
        continuation=json.loads(continuation_path.read_text('utf8'))
        if (continuation.get('source_sha256')!=hashlib.sha256(source_path.read_bytes()).hexdigest()
                or continuation.get('game_pid')!=source['game_pid']):
            raise ValueError('CAREER_CONTROLS_CONTINUATION_IDENTITY')
    if folder.exists(): raise ValueError('CAREER_CONTROLS_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    try:
        deps=layout.dependencies() if deps is None else deps
        stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(source['game_pid'],): raise ValueError('CAREER_CONTROLS_SOURCE_PID_CHANGED')
        pid=pids[0];identity=deps['resolve_game'](pid);deps['validate_identity'](identity,stamps)
        with deps['Process'](pid) as process: result=capture(process,identity,source,clock,continuation)
        final=deps['resolve_game'](pid);deps['validate_identity'](final,stamps)
        if final!=identity or tuple(deps['game_processes']())!=(pid,): raise ValueError('CAREER_CONTROLS_MODULE_CHANGED')
        result.update(game_pid=pid,source_path=str(source_path),source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest())
        if continuation_path:
            result.update(continuation_path=str(continuation_path),continuation_sha256=hashlib.sha256(continuation_path.read_bytes()).hexdigest())
        path=folder/'controls.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
        status={'status':'complete','json_path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'found':list(result['found']),'child_limit_reached':result['child_limit_reached'],
                'active_read_bytes':result['active_read_bytes'],'active_read_calls':result['active_read_calls']}
        (folder/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n','utf8')
        return status
    except Exception as error:
        (folder/'status.json').write_text(json.dumps({'status':'failed','error':str(error),
            'native_called':False,'native_written':False,'account_modified':False},ensure_ascii=False,indent=2)+'\n','utf8')
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--continuation',type=Path,help='Completed first 24-child segment; resume its fixed next link once.')
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    print(json.dumps(run(args.source,args.output,continuation_path=args.continuation),ensure_ascii=False))
