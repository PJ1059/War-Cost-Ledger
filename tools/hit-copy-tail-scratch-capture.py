"""One fixed read-only path into existing 0.4.25 owned diagnostic scratch.

No Game pointer from HI/target/source rows is followed. No FIFO body, calls,
writes, retries, installation, or process control. All RPM/query plus two
creation-time queries share this private 48KiB/96IO/2s profile. Mutable row
payloads remain two raw samples; identity/source changes withhold the BIN.
"""
from __future__ import annotations
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import time

ROOT=Path(__file__).resolve().parents[1]
REVISION='copy_tail_owned_scratch_readonly_v1'
EXPECTED_PID=27268
MAX_BYTES,MAX_IO,MAX_SECONDS=48*1024,96,2.0
LOCATOR=ROOT/'tools/hit-game-plugin-export-locator.py'
LOCATOR_SHA='82346fce9dec9a84d7af88e556fd448bf3f1893cf6c48888baa7f00b2b8a3ded'
PROFILE=ROOT/'docs/native-hit-copy-observer-v1.json'
PROFILE_SHA='c3bf4a1961da5a6848a19a34d99e79b1800aa96bb93b9969412cc8f62e3be3f4'
SLOT_RVA=0x37CEB78
PEER=0x06464E240E0D372A
EPOCH=15
BLOCK_BYTES=2080
ARENA_DELTA=0x18040


def source():
    if hashlib.sha256(LOCATOR.read_bytes()).hexdigest()!=LOCATOR_SHA:
        raise ValueError('TAIL_SCRATCH_LOCATOR_SOURCE_CHANGED')
    raw=PROFILE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROFILE_SHA:
        raise ValueError('TAIL_SCRATCH_PROFILE_SOURCE_CHANGED')
    profile=json.loads(raw)
    if (profile['revision']!='copy_pending_tail_diagnostic_v1'
            or profile['arena_capacity']!=32 or profile['arena_row_bytes']!=640
            or profile['tail_diagnostic']!={'revision':1,'head_offset':128,'head_bytes':32,
                'scratch_offset':160,'record_offset':256,'record_bytes':96,
                'capacity':16,'alt_tag':3,'true_tag':4}):
        raise ValueError('TAIL_SCRATCH_PROFILE_CONTRACT')
    layouts={};offset=0
    for entry in profile['entries']:
        offset=(offset+15)//16*16
        layouts[entry['name']]=(offset,entry)
        offset+=len(bytes.fromhex(entry['code_hex']))
    if (layouts['physical_success'][0]!=0x960
            or len(bytes.fromhex(layouts['physical_success'][1]['code_hex']))!=788
            or layouts['tail_diagnostic'][0]!=0x1AD0
            or len(bytes.fromhex(layouts['tail_diagnostic'][1]['code_hex']))!=784):
        raise ValueError('TAIL_SCRATCH_FIXED_GATEWAY_LAYOUT')
    spec=importlib.util.spec_from_file_location('_tail_scratch_private_locator',LOCATOR)
    locator=importlib.util.module_from_spec(spec);spec.loader.exec_module(locator)
    locator.validate_source()
    reader=locator.private_reader()
    return locator,reader,layouts


def q(raw,at=0):return struct.unpack_from('<Q',raw,at)[0]
def u(raw,at=0):return struct.unpack_from('<I',raw,at)[0]
def canonical(at,n=1):
    return type(at)is int and type(n)is int and 0<n and 65536<=at<at+n<0x800000000000


def process_creation_time(process):
    # Public process-information query on the existing read-only handle.
    api=process._kernel.GetProcessTimes
    api.argtypes=[ctypes.c_void_p]+[ctypes.POINTER(ctypes.c_uint64)]*4
    api.restype=ctypes.c_int
    values=[ctypes.c_uint64()for _ in range(4)]
    if not api(process._require_open(),*[ctypes.byref(v)for v in values]):
        raise ctypes.WinError(ctypes.get_last_error())
    return values[0].value


def make_budget(reader):
    class Budget(reader.Budget):
        def time_gate(self):
            if self.clock()-self.started>=MAX_SECONDS:raise ValueError('TAIL_SCRATCH_TIME_BUDGET')
        def reserve(self,size,io):
            self.time_gate()
            if self.bytes_requested+size>MAX_BYTES or self.read_calls+self.query_calls+io>MAX_IO:
                raise ValueError('TAIL_SCRATCH_SHARED_BUDGET')
        def require_capacity(self,size,calls=1):
            if not 0<size:raise ValueError('TAIL_SCRATCH_READ_SIZE')
            self.reserve(size,calls)
        def query(self,address):
            self.reserve(0,1);self.query_calls+=1
            return self.process.query(address)
        def creation(self,function):
            self.reserve(0,1);self.query_calls+=1
            value=function(self.process)
            if type(value)is not int or value<=0:raise ValueError('TAIL_SCRATCH_CREATION_TIME_INVALID')
            return value
        def read(self,address,size,purpose='ship'):
            self.require_capacity(size)
            return super().read(address,size,purpose)
        def owned(self,address,size,purpose,code=False,base=None,total=None):
            if not canonical(address,size)or size>4096:
                raise ValueError('TAIL_SCRATCH_OWNED_ADDRESS')
            if base is not None and not(base<=address<address+size<=base+total):
                raise ValueError('TAIL_SCRATCH_OWNED_FIXED_RANGE')
            self.reserve(size,2)
            region=self.query(address)
            if (region['state']!=0x1000 or region['type']!=0x20000
                    or region['protect']&0x100
                    or region['protect']&0xff!=(0x20 if code else 4)
                    or not region['base']<=address<address+size<=region['base']+region['size']):
                raise ValueError('TAIL_SCRATCH_OWNED_REGION')
            raw=self.read(address,size,'owned_'+purpose)
            self.records[-1].pop('module',None);self.records[-1].pop('rva',None)
            self.records[-1].update(address=address,address_basis='fixed_owned_follow_chain')
            return raw
        def summary(self):
            return {'read_calls':self.read_calls,'query_calls':self.query_calls,
                'io_calls':self.read_calls+self.query_calls,'bytes_requested':self.bytes_requested,
                'bytes_returned':self.bytes_returned,'elapsed_ms':(self.clock()-self.started)*1000,
                'max_bytes':MAX_BYTES,'max_io':MAX_IO,'soft_seconds':MAX_SECONDS,
                'includes_creation_queries':True}
    return Budget


def check_entry(raw,entry,keys):
    expected=bytearray.fromhex(entry['code_hex']);actual=bytearray(raw)
    if len(actual)!=len(expected):raise ValueError('TAIL_SCRATCH_ENTRY_LENGTH')
    for reloc in entry['relocations']:
        at=reloc['offset'];key=reloc['address_key']
        value=q(actual,at)
        if key not in keys or value!=keys[key]+reloc.get('addend',0):
            raise ValueError('TAIL_SCRATCH_ENTRY_LITERAL: '+key)
        actual[at:at+8]=bytes(8)
    if actual!=expected:raise ValueError('TAIL_SCRATCH_ENTRY_BYTES')


def follow(budget,layouts):
    game=budget.identity['game_base']
    slot=budget.read_module(SLOT_RVA,8,'owned_dispatch_slot')
    w=q(slot)
    if not canonical(w,0xD000)or w%65536 or not game+0x4744000<=w<w+0xD000<=game+0x7FFFFFFF:
        raise ValueError('TAIL_SCRATCH_WRAPPER_LAYOUT')
    wrapper=budget.owned(w,14,'wrapper',True,w,0xB000)
    if (wrapper[:4]!=bytes.fromhex('f048ff05')or wrapper[8:10]!=bytes.fromhex('ff25')
            or w+8+struct.unpack_from('<i',wrapper,4)[0]!=w+0xC000
            or w+14+struct.unpack_from('<i',wrapper,10)[0]!=w+0xC008):
        raise ValueError('TAIL_SCRATCH_WRAPPER_PIN')
    counter=budget.owned(w+0xC000,16,'counter_target',False,w+0xC000,0x1000)
    if q(counter,8)!=w+0x100:raise ValueError('TAIL_SCRATCH_FRAME_TARGET')
    pc=w+0xA604
    site=budget.owned(pc,5,'physical_true_site',True,w,0xB000)
    if site[0]!=0xE8:raise ValueError('TAIL_SCRATCH_PHYSICAL_CALL')
    gw=pc+5+struct.unpack_from('<i',site,1)[0]
    base=gw-layouts['physical_success'][0]
    if (not canonical(base,65536)or base%65536
            or not game+0x4744000<=base<base+65536<=game+0x7FFFFFFF):
        raise ValueError('TAIL_SCRATCH_PACKAGE_LAYOUT')
    gateway=budget.owned(gw,788,'physical_gateway',True,base,65536)
    arena=q(gateway,155)
    if not canonical(arena,64+32*640)or arena%8:raise ValueError('TAIL_SCRATCH_ARENA_LITERAL')
    bridge=arena-ARENA_DELTA
    keys={name:base+at for name,(at,_)in layouts.items()}
    keys.update(arena=arena,bridge=bridge,current_user_global=game+0x347CEF0,
                entity_manager_global=game+0x346BF98)
    check_entry(gateway,layouts['physical_success'][1],keys)
    helper=budget.owned(keys['tail_diagnostic'],784,'tail_helper',True,base,65536)
    check_entry(helper,layouts['tail_diagnostic'][1],keys)
    return {'wrapper':w,'gateway':gw,'package_base':base,'arena':arena,'bridge':bridge,
        'site_hex':site.hex(),'gateway_sha256':hashlib.sha256(gateway).hexdigest(),
        'helper_sha256':hashlib.sha256(helper).hexdigest(),'slot_hex':slot.hex(),
        'wrapper_hex':wrapper.hex(),'counter':q(counter),'frame_target':q(counter,8)}


def headers(budget,path):
    arena,bridge=path['arena'],path['bridge']
    a=budget.owned(arena,64,'arena_header',False,bridge,ARENA_DELTA+64+32*640)
    b=budget.owned(bridge,64,'bridge_header',False,bridge,ARENA_DELTA+64+32*640)
    h=budget.owned(arena+64+128,32,'diagnostic_head',False,arena,64+32*640)
    if (u(a)!=32 or u(a,4)!=640 or q(a,8)!=EPOCH or q(a,16)!=PEER
            or q(a,48)!=arena+64 or u(a,60)%2 or u(a,40)not in(0,1)
            or u(b)!=1 or u(b,4)!=1024 or q(b,8)!=EPOCH or q(b,16)!=PEER
            or u(h,16)>16 or u(h,20)>=1<<u(h,16)or q(h,24)!=EPOCH):
        raise ValueError('TAIL_SCRATCH_ARENA_IDENTITY')
    return a,b,h


def parse_samples(chunks,head_before,head_after):
    result=[]
    for sample in range(2):
        rows=[]
        for group in range(8):
            block=chunks[sample*8+group]
            for within in range(4):
                at=within*640;meta=block[at:at+32];raw=block[at+64:at+160]
                flags=u(raw,88);tag=u(raw,60)
                stage='empty_or_not_reached'
                if raw!=bytes(96):
                    stage=('stale_or_unrecognized_raw'if(q(raw,8)!=EPOCH or q(raw,16)!=PEER or tag not in(3,4))
                           else {0x0B:'enemy_and_source_not_admitted',0x4B:'enemy_only',
                                 0x10B:'source_only',0x14B:'enemy_and_source_admitted'}.get(flags,'other_flags'))
                rows.append({'index':group*4+within,'thread_owner':u(meta),
                    'phase':u(meta,4),'HI_value_only':q(meta,8),'curve':u(meta,16),
                    'scratch_raw_hex':raw.hex(),'scratch_epoch':f'{q(raw,8):016X}',
                    'scratch_peer':f'{q(raw,16):016X}','tag':tag,'target_value_only':u(raw,44),
                    'source_value_only':u(raw,48),'owner_value_only':u(raw,52),
                    'capture_flags':flags,'target_kind':u(raw,84),'stage':stage,
                    'passed_fullpeer_and_owned_row':stage not in('empty_or_not_reached','stale_or_unrecognized_raw')})
        result.append({'sample':sample+1,'rows':rows})
    return {'samples':result,'heads_identical':head_before==head_after,
            'raw_payload_identical':chunks[:8]==chunks[8:],
            'scratch_proves_last_reached_qualifier_only':True,'Game_pointers_followed':False,
            'zero_scratch_does_not_distinguish_peer_from_lookup':True}


def run(output,dependencies=None,clock=time.perf_counter):
    folder=Path(output).resolve()
    if folder.exists():raise ValueError('TAIL_SCRATCH_OUTPUT_EXISTS')
    folder.mkdir(parents=True)
    evidence={'source_revision':REVISION,'complete':False,'native_called':False,
        'native_written':False,'Game_HI_or_entity_pointers_followed':False,'FIFO_body_read':False,
        'attempts':1,'profile_sha256':PROFILE_SHA,'snapshot_atomic':False,'classification_modified':False}
    budget=None
    try:
        locator,reader,layouts=source()
        deps=dependencies if dependencies is not None else reader.profile.load_dependencies()
        stamps=deps['fingerprints']();pids=tuple(deps['game_processes']())
        if pids!=(EXPECTED_PID,):raise ValueError('TAIL_SCRATCH_EXACT_PID_REQUIRED')
        identity=deps['resolve_game'](EXPECTED_PID);deps['validate_identity'](identity,stamps)
        reader.profile.validate_module(identity)
        evidence.update(identity=identity,game_pid=EXPECTED_PID,fingerprint=reader.profile.FINGERPRINT)
        with deps['Process'](EXPECTED_PID)as process:
            budget=make_budget(reader)(process,identity,clock)
            creation=budget.creation(deps.get('start_time',process_creation_time))
            state_before=deps['ship_state'](budget,identity)
            if state_before['state']!=3:raise ValueError('TAIL_SCRATCH_SHIP_REQUIRED')
            original=locator.snapshot(budget)
            if original[2].hex()!='85c90f85a2000000488d0581f6ffff48':
                raise ValueError('TAIL_SCRATCH_GETTER_PIN')
            path=follow(budget,layouts);a,b,h=headers(budget,path)
            # Exact16 payload reads + max29 post IO /5973 bytes includes both
            # source snapshots, private code/path, headers and starttime check.
            budget.reserve(16*BLOCK_BYTES+5973,32+29)
            chunks=[];ranges=[]
            for sample in range(2):
                for group in range(8):
                    offset=64+group*4*640+96
                    chunks.append(budget.owned(path['arena']+offset,BLOCK_BYTES,
                        f'rows_sample{sample+1}_group{group}',False,path['arena'],64+32*640))
                    ranges.append({'sample':sample+1,'first_row':group*4,'arena_offset':offset,
                        'length':BLOCK_BYTES,'binary_offset':(sample*8+group)*BLOCK_BYTES})
            aa,bb,hh=headers(budget,path);again=follow(budget,layouts)
            if (u(a,60)!=u(aa,60)or u(a,40)!=u(aa,40)
                    or q(hh,0)<q(h,0)or q(hh,8)<q(h,8)
                    or u(hh,16)<u(h,16)or u(hh,20)&u(h,20)!=u(h,20)
                    or any(again[k]!=path[k]for k in path if k!='counter')
                    or again['counter']<path['counter']):
                raise ValueError('TAIL_SCRATCH_PATH_OR_IDENTITY_CHANGED')
            final_snapshot=locator.snapshot(budget);state_after=deps['ship_state'](budget,identity)
            creation_after=budget.creation(deps.get('start_time',process_creation_time))
            if original!=final_snapshot or state_before!=state_after or creation_after!=creation:
                raise ValueError('TAIL_SCRATCH_SOURCE_PHASE_STARTTIME_CHANGED')
            final=deps['resolve_game'](EXPECTED_PID);deps['validate_identity'](final,stamps)
            if final!=identity or tuple(deps['game_processes']())!=(EXPECTED_PID,):
                raise ValueError('TAIL_SCRATCH_MODULE_PID_CHANGED')
            budget.time_gate()
        raw=b''.join(chunks)
        evidence.update(complete=True,source_gates_verified=True,creation_filetime=creation,
            ship_before=state_before,ship_after=state_after,owned_path=path,ranges=ranges,
            header_before={'arena':a.hex(),'bridge':b.hex(),'head':h.hex()},
            header_after={'arena':aa.hex(),'bridge':bb.hex(),'head':hh.hex()},
            native_filtered_before=q(b,56),native_filtered_after=q(bb,56),
            arena_rejected_before=q(a,32),arena_rejected_after=q(aa,32),
            arena_generation=u(a,60),arena_enabled=u(a,40),arena_active_before=u(a,44),
            arena_active_after=u(aa,44),diagnostic_claimed_before=u(h,16),
            diagnostic_claimed_after=u(hh,16),diagnostic_alt=q(hh),diagnostic_true=q(hh,8),
            budget=budget.summary(),read_records=budget.records,
            interpretation=parse_samples(chunks,h,hh),captured_at=datetime.now(timezone.utc).isoformat(),
            binary_sha256=hashlib.sha256(raw).hexdigest())
        binary,report=folder/'scratch.bin',folder/'scratch.json'
        binary.write_bytes(raw);report.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
        return {'status':'complete','json_path':str(report),'binary_path':str(binary),'sha256':evidence['binary_sha256']}
    except Exception as error:
        evidence.update(status='failed',error=str(error),partial_binary_saved=False)
        if budget is not None:evidence.update(budget=budget.summary(),read_records=budget.records)
        (folder/'scratch.incomplete.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    try:print(json.dumps(run(parser.parse_args().output),indent=2))
    except(OSError,ValueError)as error:parser.exit(1,str(error)+'\n')
