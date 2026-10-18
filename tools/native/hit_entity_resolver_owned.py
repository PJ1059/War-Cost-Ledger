"""Bounded entity/type lookup on tool-owned memory only; no game connector.

Map fields and descriptor calculation match actual FD9D40..FD9DF2 plus the
matching Runtime SDK. At most eight hash probes per entity. Static type lists
admit named hostile enemies and supported personal projectile weapon sources.
No world scan, Lua callback, allocation or system call occurs in these leaves.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import re
import struct
from pathlib import Path

from hit_bridge_owned import _Code,Record

ROOT=Path(__file__).resolve().parents[2]
SDK=Path('external/HD2Runtime')
MAP=0xF1AEB0
DESCRIPTORS=0xF32F18
STRIDE=24
PROBE_LIMIT=8
INDEX_LIMIT=0x100000


def lookup_code():
    """u64 type(manager RCX, entity EDX), zero when absent/unproven. Leaf ABI."""
    c=_Code()
    c.emit('49 89 ca 48 85 c9')
    c.branch('0f 84','unknown')
    c.emit('85 d2')
    c.branch('0f 84','unknown')
    c.emit('45 8b 8a b8 ae f1 00 45 85 c9')
    c.branch('0f 84','unknown')
    c.emit('41 81 f9 00 00 10 00')
    c.branch('0f 87','unknown')
    c.emit('44 89 c8 41 ff c9 44 85 c8') # original capacity & (capacity-1)
    c.branch('0f 85','unknown')
    c.emit('89 d0 41 0f af 82 c0 ae f1 00 44 21 c8')
    c.emit('4d 8b 82 b0 ae f1 00 4d 85 c0')
    c.branch('0f 84','unknown')
    c.emit('b9 08 00 00 00')
    c.label('probe')
    c.emit('45 8b 1c c0 41 39 d3')
    c.branch('0f 84','found')
    c.emit('45 3b 9a bc ae f1 00')
    c.branch('0f 84','unknown')
    c.emit('ff c0 44 21 c8 ff c9')
    c.branch('0f 85','probe')
    c.branch('e9','unknown')
    c.label('found')
    c.emit('45 8b 5c c0 04 41 81 fb 00 00 10 00')
    c.branch('0f 83','unknown')
    c.emit('4d 6b db 18 4f 8d 9c 1a 18 2f f3 00')
    c.emit('41 39 53 08')
    c.branch('0f 85','unknown')
    c.emit('49 8b 03 41 39 53 08') # entity/type/entity; never reuses stale type alone
    c.branch('0f 85','unknown')
    c.emit('4d 3b 82 b0 ae f1 00')
    c.branch('0f 85','unknown')
    c.emit('41 ff c1 45 3b 8a b8 ae f1 00')
    c.branch('0f 85','unknown')
    c.emit('c3')
    c.label('unknown')
    c.emit('31 c0 c3')
    return c.finish()


def allow_code():
    """u32 admitted(sorted u64 table RCX, type RDX, count R8D); <=11 probes."""
    c=_Code()
    c.emit('45 85 c0')
    c.branch('0f 84','no')
    c.emit('41 81 f8 00 04 00 00')
    c.branch('0f 87','no')
    c.emit('45 31 c9')
    c.label('search')
    c.emit('45 39 c1')
    c.branch('0f 83','no')
    c.emit('44 89 c0 44 29 c8 d1 e8 44 01 c8 48 3b 14 c1')
    c.branch('0f 84','yes')
    c.branch('0f 82','lower')
    c.emit('44 8d 48 01')
    c.branch('e9','search')
    c.label('lower')
    c.emit('41 89 c0')
    c.branch('e9','search')
    c.label('yes')
    c.emit('b8 01 00 00 00 c3')
    c.label('no')
    c.emit('31 c0 c3')
    return c.finish()


def catalog():
    # This generated SDK table contains simple entity dictionaries. Reject
    # non-enemy/unresolved kill-score entries rather than expanding their meaning.
    path=SDK/'domains/event_entities.lua'
    text=path.read_text(encoding='utf8').split('["sources"]=',1)[0]
    matches=re.findall(r'\["([0-9A-F]{16})"\]=\{([^{}]*)\}',text)
    enemies=sorted(int(key,16) for key,row in matches
                   if '["kill"]=true' in row and '["kind"]="enemy"' in row)
    import sys
    sys.path.insert(0,str(ROOT/'tools'))
    from hit_sources import generate
    hit=generate(ROOT)
    sources=sorted(int(key,16) for key in hit['sources'])
    assert len(enemies)==111 and len(sources)==91
    return enemies,sources,dict(sdk_commit=hit['runtime_commit'],
        enemy_catalog_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_evidence=hit['evidence'],enemy_count=len(enemies),source_count=len(sources))


def qualify_code(lookup,allow,enemy_table,enemy_count,source_table,source_count):
    """u32 qualify(manager RCX, owned record RDX); does not publish/count."""
    c=_Code()
    c.emit('56 57 48 83 ec 28 48 89 cf 48 89 d6')
    c.emit('81 66 58 bf fe ff ff c7 46 54 00 00 00 00')
    for name,entity_offset,table,count,bit in [
        ('target',44,enemy_table,enemy_count,64),
        ('source',48,source_table,source_count,256)]:
        c.emit('48 89 f9 8b 56 '+bytes([entity_offset]).hex())
        c.emit('48 b8 '+lookup.to_bytes(8,'little').hex(' ')+' ff d0 48 85 c0')
        c.branch('0f 84',name+'_ready')
        c.emit('48 89 c2 48 b9 '+table.to_bytes(8,'little').hex(' '))
        c.emit('41 b8 '+count.to_bytes(4,'little').hex(' '))
        c.emit('48 b8 '+allow.to_bytes(8,'little').hex(' ')+' ff d0 85 c0')
        c.branch('0f 84',name+'_ready')
        c.emit('81 4e 58 '+bit.to_bytes(4,'little').hex(' '))
        if name=='target':c.emit('c7 46 54 01 00 00 00')
        c.label(name+'_ready')
    c.emit('8b 46 58 48 83 c4 28 5f 5e c3')
    return c.finish()


class OwnedEntityResolver:
    """A fixture manager/descriptor map owned by the same OwnedBridge process."""
    def __init__(self,bridge,*,capacity=16):
        if capacity<1 or capacity>1024 or capacity&(capacity-1):
            raise ValueError('fixture capacity must be a small power of two')
        self.bridge=bridge
        self.capacity=capacity
        self.manager=bridge._allocate(DESCRIPTORS+STRIDE*32,executable=False)
        self.buckets=bridge._allocate(capacity*8,executable=False)
        self.empty=0xffffffff
        self.multiplier=3
        for i in range(capacity):
            ctypes.memmove(self.buckets+i*8,struct.pack('<II',self.empty,0xffffffff),8)
        ctypes.memmove(self.manager+MAP,struct.pack('<QIII',self.buckets,capacity,self.empty,self.multiplier),20)
        self._lookup=bridge._procedure(lookup_code(),ctypes.c_uint64,ctypes.c_void_p,ctypes.c_uint32)
        self._allow=bridge._procedure(allow_code(),ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint64,ctypes.c_uint32)
        self.enemies,self.sources,self.evidence=catalog()
        self.tables={}
        for name,values in [('enemy',self.enemies),('source',self.sources)]:
            at=bridge._allocate(len(values)*8,executable=False)
            ctypes.memmove(at,b''.join(struct.pack('<Q',v) for v in values),len(values)*8)
            self.tables[name]=(at,len(values))
        code=qualify_code(int(ctypes.cast(self._lookup,ctypes.c_void_p).value),
                          int(ctypes.cast(self._allow,ctypes.c_void_p).value),
                          *self.tables['enemy'],*self.tables['source'])
        self._qualify=bridge._procedure(code,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_void_p,
            unwind=bytes.fromhex('01060300 0642 0270 0160 0000'))

    def insert(self,entity,kind,index):
        if self.bridge.closed or not 0<entity<2**32-1 or not 0<=index<32:
            raise ValueError('fixture identity/index')
        start=(entity*self.multiplier)&(self.capacity-1)
        for probe in range(self.capacity):
            slot=(start+probe)&(self.capacity-1)
            found=ctypes.c_uint32.from_address(self.buckets+slot*8).value
            if found in (self.empty,entity):
                ctypes.memmove(self.buckets+slot*8,struct.pack('<II',entity,index),8)
                ctypes.memmove(self.manager+DESCRIPTORS+index*STRIDE,struct.pack('<QIIQ',kind,entity,0,0),24)
                return slot
        raise ValueError('fixture map full')

    def lookup(self,entity):
        if self.bridge.closed or not isinstance(entity,int) or not 0<=entity<2**32:
            raise ValueError('closed fixture or invalid identity')
        return int(self._lookup(self.manager,entity))

    def admitted(self,group,kind):
        if self.bridge.closed or group not in self.tables or not 0<=kind<2**64:
            raise ValueError('closed fixture or invalid catalog identity')
        table,count=self.tables[group]
        return bool(self._allow(table,kind,count))

    def qualify(self,record):
        if self.bridge.closed or not isinstance(record,Record):
            raise ValueError('closed fixture or invalid owned record')
        return int(self._qualify(self.manager,ctypes.addressof(record)))
