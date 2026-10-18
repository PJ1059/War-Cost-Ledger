"""Execute the exact typed-ID gateways against owned native pool/frame memory.

No game process, installed MOD, account, native hooks, or game code execution.
"""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys
import types

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/native'))
sys.path.insert(0,str(ROOT/'tests'))
import hit_copy_typed_ids_060_observer as producer
import hit_copy_damage_id_054_observer as damage_producer
import test_hit_copy_damage_id_054_owned as D
from hit_bridge_owned import OwnedBridge
from test_hit_copy_reflection_observer_owned import replay_preserved
from test_hit_copy_pending_observer_owned import RETURN,STACK_VALUES,COMMON_RCX

PROFILE=ROOT/'docs/native-hit-damage-id-profile-0.4.60.json'
OLD=ROOT/'docs/native-hit-damage-id-profile-v1.json'
OLD_SHA='2c5abff2c8b8606d0c413cafe546fbd53c7ebcadd17aeafc35e22a6f342e7754'


def fixture(bridge,manifest):
    p,h=D.make_fixture(bridge,manifest,reflection=True)
    p.context=bridge._allocate(0xE7080,executable=False)
    p.config[8]=p.context
    p.slot=3;p.config[10]=p.slot
    p.flight=p.context+0x3040+p.slot*0x70
    p.pool=p.context+0x4D040+p.slot*0xC8
    p.bad_frame=0;p.type_after_begin=None
    parent=p.runner
    def runner(self,actions,**options):
        original=self.b._procedure
        needle=b'\x49\xbb'+struct.pack('<Q',self.addresses['contact_begin'])+b'\x41\xff\xd3'
        def bind(raw,*args,**kwargs):
            if 'contact_begin' in actions and needle in raw:
                # Decoy begin-time RDI must never act as the slot. The real
                # parent frame, R15 system and R14 hit pool remain independent.
                before=b'\x48\xbf'+struct.pack('<Q',0x123456789ABCDEF0)
                after=b''
                if self.bad_frame:
                    before+=bytes.fromhex('48 83 c5 10')
                    after+=bytes.fromhex('48 83 ed 10')
                if self.type_after_begin is not None:
                    after+=b'\x49\xba'+struct.pack('<Q',self.context+0xE5040+self.slot*4)
                    after+=bytes.fromhex('41 c7 02')+struct.pack('<I',self.type_after_begin)
                raw=raw.replace(needle,before+needle+after)
            return original(raw,*args,**kwargs)
        self.b._procedure=bind
        try:return parent(actions,**options)
        finally:self.b._procedure=original
    p.runner=types.MethodType(runner,p)
    return p,h


def prepare(p,h,*,slot=3,type_id=284,damage_id=202,unknown=False,bad_frame=False,bad_hit=False,
            raw_slot=None,system_missing=False,dead=False,other_peer=False):
    p.slot=slot;p.config[10]=slot if raw_slot is None else raw_slot
    p.config[8]=0 if system_missing else p.context
    p.flight=p.context+0x3040+slot*0x70
    p.pool=p.context+0x4D040+slot*0xC8
    if bad_hit:p.pool=p.context+0x4D040+((slot+1)%2048)*0xC8
    p.bad_frame=int(bad_frame);p.type_after_begin=None;p.mutate_after_begin=None
    p.reflection_defaults();h.reset()
    ctypes.c_uint32.from_address(p.context+0xE5040+slot*4).value=type_id
    ctypes.c_uint32.from_address(p.pool+12).value=damage_id
    h.put32(h.life,2 if dead else 0)
    p.resolver.insert(1002,0x4D1C334D294DFA97 if unknown else p.source,1)
    ctypes.c_uint64.from_buffer(p.hit,0x110).value=p.b.local_peer ^ ((1<<32)if other_peer else 0)



def original_calls_preserved(p,raw,actions):
    hi=struct.unpack_from('<Q',raw,8)[0]
    for name,area in [('contact_begin',0),('normal_final',128)]:
        times=actions.count(name)
        assert struct.unpack_from('<Q',raw,area+96)[0]==times
        if not times:continue
        rcx,rdx,r8,r9=struct.unpack_from('<4Q',raw,area)
        assert rcx==p.output+area
        assert rdx==(hi-0x1A0 if name=='normal_final'else hi)
        assert r8==(hi if name=='normal_final'else 0xFFEEDDCCBBAA9988)
        assert r9==0x8877665544332211
        assert struct.unpack_from('<8Q',raw,area+32)==STACK_VALUES
    for index,name in enumerate(actions):
        if name in('contact_begin','normal_final'):
            assert struct.unpack_from('<Q',raw,0x180+index*8)[0]==RETURN
    assert p.config[7]==COMMON_RCX,'contact_end must retain the original parent frame'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output;output.mkdir(parents=True,exist_ok=True)
    catalog=json.loads((ROOT/'docs/damage-source-catalog.json').read_text(encoding='utf8'))
    manifest=json.loads(PROFILE.read_text())
    assert manifest==producer.package(damage_producer.audited_ids(catalog),catalog)
    old_bytes=OLD.read_bytes();assert hashlib.sha256(old_bytes).hexdigest()==OLD_SHA
    old=json.loads(old_bytes)
    base=damage_producer.package(damage_producer.audited_ids(catalog))
    assert manifest['sites']==old['sites']==base['sites']
    assert manifest['abi']==1 and manifest['record_bytes']==96 and manifest['arena_capacity']==32
    assert len(manifest['data_tables']['source_types'])==94
    assert manifest['data_tables']==base['data_tables']
    entries={e['name']:e for e in base['entries']}
    for entry in manifest['entries']:
        if entry['name']not in('contact_begin','reflection_writeback'):
            assert entry==entries[entry['name']],entry['name']
    report=dict(status='RUNNING',game_access=False,game_code_executed=False,
                installed_files_accessed=False,account_access=False,ABI=1,record_bytes=96,cases=[])
    actions=('contact_begin','default_delta','normal_final','contact_end')
    cases=[('native_type_and_damage_distinct',{},True),
           ('first_pool_slot',dict(slot=0),True),('last_pool_slot',dict(slot=2047,type_id=350),True),
           ('bad_parent_frame',dict(bad_frame=True),False),('mismatched_hit_record',dict(bad_hit=True),False),
           ('slot_at_bound',dict(raw_slot=2048),False),('slot_negative',dict(raw_slot=0xFFFFFFFFFFFFFFFF),False),
           ('slot_nonzero_high32',dict(raw_slot=(1<<32)|3),False),
           ('missing_system',dict(system_missing=True),False),('zero_type',dict(type_id=0),False),
           ('type_at_bound',dict(type_id=351),False),('type_u32_marker',dict(type_id=0xFFFFFFFF),False),
           ('shared_fragments',dict(type_id=201,damage_id=189),True)]
    new_ids=sorted(set(damage_producer.audited_ids(catalog))-
                   {int(x,16)for x in old['data_tables']['damage_info_types']})
    cases.extend((f'new_damage_id_{i}',dict(damage_id=i),True)for i in new_ids)
    for unknown in(False,True):
        with OwnedBridge()as bridge:
            p,h=fixture(bridge,manifest)
            for name,options,typed in cases:
                prepare(p,h,unknown=unknown,**options)
                records,_,_,raw=p.run(actions)
                original_calls_preserved(p,raw,actions)
                assert len(records)==1,(unknown,name,len(records))
                r=records[0]
                assert bool(r.capture_flags&2048)==typed,(unknown,name,r.capture_flags)
                if typed:assert r.projectile_slot==options.get('type_id',284),(name,r.projectile_slot)
                assert r.projectile_generation==options.get('damage_id',202)
                assert r.capture_flags&512 and bool(r.capture_flags&1024)==unknown
                assert r.native_branch==1 and r.target==1001 and r.source==1002 and r.creditor==bridge.local_peer
                assert ctypes.c_uint32.from_address(p.pool+12).value==options.get('damage_id',202)
                report['cases'].append(dict(name=name,unknown=unknown,projectile_flag=typed,records=1))
            for name,options in [('corpse',dict(dead=True)),('other_peer',dict(other_peer=True))]:
                prepare(p,h,unknown=unknown,**options);records,_,_,_=p.run(actions)
                assert not records,name
                report['cases'].append(dict(name=name,unknown=unknown,records=0))
            for normal_first in(False,True):
                prepare(p,h,unknown=unknown)
                sequence=('contact_begin',)+(('default_delta','normal_final')if normal_first else())+('reflection_writeback','contact_end')
                runner=p.runner(sequence);runner(ctypes.addressof(p.config))
                raw=ctypes.string_at(p.output,4096);records=bridge.drain()
                assert len(records)==1
                r=records[0]
                assert r.projectile_slot==284 and r.projectile_generation==202
                assert r.capture_flags&2048 and r.capture_flags&512 and bool(r.capture_flags&1024)==unknown
                assert r.native_branch==2
                replay_preserved(p,raw)
                report['cases'].append(dict(name='reflection_keeps_frozen_type_not_legacy_slot',unknown=unknown,normal_first=normal_first,records=1))
            for bad in ('bad_frame','bad_hit'):
                prepare(p,h,unknown=unknown,**{bad:True})
                sequence=('contact_begin','reflection_writeback','contact_end')
                runner=p.runner(sequence);runner(ctypes.addressof(p.config))
                raw=ctypes.string_at(p.output,4096);records=bridge.drain()
                assert len(records)==1
                r=records[0]
                assert not r.capture_flags&2048 and r.capture_flags&512
                assert r.projectile_generation==202 and r.projectile_slot==3
                assert bool(r.capture_flags&1024)==unknown
                replay_preserved(p,raw)
                report['cases'].append(dict(name='reflection_metadata_rejection_preserves_damage_'+bad,unknown=unknown))
            prepare(p,h,unknown=unknown);p.type_after_begin=0
            pair=('contact_begin','default_delta','normal_final','contact_begin','default_delta','normal_final','contact_end')
            records,_,_,_=p.run(pair)
            assert len(records)==2 and [bool(r.capture_flags&2048)for r in records]==[True,False]
            assert [r.projectile_generation for r in records]==[202,202]
            report['cases'].append(dict(name='new_begin_clears_stale_projectile_validity',unknown=unknown))
            prepare(p,h,unknown=unknown);p.type_after_begin=201
            records,_,_,_=p.run(actions)
            assert len(records)==1 and records[0].projectile_slot==284
            assert ctypes.c_uint32.from_address(p.context+0xE5040+p.slot*4).value==201
            report['cases'].append(dict(name='type_pool_mutation_after_begin_is_not_borrowed',unknown=unknown))
            prepare(p,h,unknown=unknown);p.type_after_begin=201;p.mutate_after_begin=189
            pair=('contact_begin','default_delta','normal_final','contact_begin','default_delta','normal_final','contact_end')
            records,_,_,_=p.run(pair)
            assert [(r.projectile_slot,r.projectile_generation)for r in records]==[(284,202),(201,189)]
            assert all(r.capture_flags&2048 for r in records)
            report['cases'].append(dict(name='next_begin_recaptures_type_and_damage',unknown=unknown,records=2))
    # Old immutable profile can publish its historical reflection slot, but
    # never sets2048. Consumers cannot treat that old integer as a type ID.
    for reflection in(False,True):
        with OwnedBridge()as bridge:
            p,h=fixture(bridge,old);prepare(p,h)
            sequence=('contact_begin',)+(('reflection_writeback',)if reflection else('default_delta','normal_final'))+('contact_end',)
            runner=p.runner(sequence);runner(ctypes.addressof(p.config));records=bridge.drain()
            assert len(records)==1 and not records[0].capture_flags&2048
            assert records[0].projectile_generation==202
            if reflection:assert records[0].projectile_slot==3
            report['cases'].append(dict(name='legacy_profile_has_no_projectile_validity',reflection=reflection,records=1))
    report.update(status='PASS',profile_sha256=hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
                  historical_profile_sha256=OLD_SHA,new_damage_ids_executed=new_ids,
                  captures_real_projectile_type=True,new_hook_sites=0,qualification_unchanged=True)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print('PASS concrete native ProjectileType+DamageInfo capture: '+str(len(report['cases']))+' owned cases; ABI96/8 sites/qualification unchanged')


if __name__=='__main__':main()
