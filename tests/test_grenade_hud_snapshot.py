"""Owned native-memory fixture: never connects to a running game."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('grenade_snapshot_test',ROOT/'tools/grenade-hud-snapshot.py')
target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)


class Memory:
    def __init__(self):
        self.identity={'game_base':0x180000000}
        self.data={};self.reads=[];self.changed=None
        self.next=0x290000000
        game=self.identity['game_base'];p=target.sources()
        self.p,self.t=p['inventory'],p['throwable_ui']
        for pin in self.p['pins']+self.t['pins']:self.put(game+pin['rva'],bytes.fromhex(pin['hex']))
        self.state=self.alloc(0x100000);self.user=self.alloc(0x10000);self.players=self.alloc(4096)
        self.entities=self.alloc(0x1000000);self.hud=self.alloc(0x300000);self.inventory=self.alloc(4096)
        for offset,value in ((target.layout.STATE_GLOBAL,self.state),(target.USER_GLOBAL,self.user),
            (target.PLAYER_GLOBAL,self.players),(target.ENTITY_GLOBAL,self.entities),(target.HUD_GLOBAL,self.hud),
            (target.INVENTORY_GLOBAL,self.inventory)):self.ptr(game+offset,value)
        self.put(self.state+target.layout.STATE_OFFSET,struct.pack('<I',4))
        self.ptr(self.user+target.USER_PEER,0x1122)
        self.put(self.players+132,struct.pack('<I',1));peer=bytearray(56)
        struct.pack_into('<Q',peer,0,0x1122);struct.pack_into('<I',peer,24,3);self.put(self.players+712,peer)
        self.put(self.players+936,struct.pack('<I',7))
        self.map(self.entities+target.NET_MAP,{7:0})
        self.put(self.entities+target.ENTITY_BASE,struct.pack('<I',77))
        self.map(self.inventory+target.INVENTORY_MAP,{77:0})
        self.records=self.alloc(128);self.ptr(self.inventory+target.INVENTORY_RECORDS,self.records)
        self.record=bytearray(48);struct.pack_into('<IIIII',self.record,0,101,0,0,104,0);self.put(self.records,self.record)
        self.map(self.entities+target.ENTITY_MAP,{101:1,104:2})
        for index,entity,resource in ((1,101,0x12345678),(2,104,int(target.GAS_RESOURCE,16))):
            raw=bytearray(24);struct.pack_into('<QI',raw,0,resource,entity)
            self.put(self.entities+target.DESCRIPTOR_BASE+index*24,raw)
        self.put(self.hud+target.HUD_BUILT,b'\1');self.panel=self.hud+target.SELF_PANEL
        for offset,parent,kind in ((0,0,1),(self.t['outer'],self.panel,1),
            (self.t['parent'],self.panel+self.t['outer'],1),(self.t['picture'],self.panel+self.t['parent'],3),
            (self.p['grenade_widget'],self.panel+self.t['parent'],3)):
            raw=bytearray(256);struct.pack_into('<I',raw,0,kind<<18)
            struct.pack_into('<QQ',raw,240,parent,0x300000000);self.put(self.panel+offset,raw)
        self.dictionary_at=self.panel+self.p['grenade_widget']+self.p['dictionary']
        self.stock(4,4)
        self.ptr(self.panel+self.t['texture_cache'],0x11113333)
        self.ptr(self.panel+self.t['picture']+0x150,0x11113333)

    def alloc(self,size):
        value=self.next;self.next+=(size+0xFFFF)&~0xFFFF;return value
    def put(self,at,raw):
        for i,b in enumerate(raw):self.data[at+i]=b
    def ptr(self,at,value):self.put(at,struct.pack('<Q',value))
    def map(self,at,values):
        buckets=self.alloc(128);self.put(at,struct.pack('<QIII',buckets,16,0xFFFFFFFF,1))
        self.put(buckets,b'\xff'*128)
        for key,value in values.items():self.put(buckets+(key%16)*8,struct.pack('<II',key,value))
    def stock(self,current,maximum,kind=4):
        d=bytearray(self.p['count']+1);d[self.p['count']]=2
        struct.pack_into('<III',d,8,self.p['current_key'],kind,current)
        struct.pack_into('<III',d,32,self.p['maximum_key'],4,maximum);self.put(self.dictionary_at,d)
    def query(self,at):
        game=self.identity['game_base'];image=game<=at<game+target.layout.IMAGE_SIZE
        return {'base':at&~0xFFFF,'size':65536,'protect':0x20 if image else 4,'type':0x1000000 if image else 0x20000,'state':0x1000}
    def read(self,at,size):
        self.reads.append((at,size))
        if self.changed:self.changed(self,at,size)
        return bytes(self.data[at+i] for i in range(size))


class Tests(unittest.TestCase):
    def run_capture(self,m):return target.snapshot(m,m.identity,clock=lambda:0)

    def test_stock_and_exact_resource_candidates_without_billing(self):
        m=Memory();out=self.run_capture(m)
        self.assertEqual(out['stock'],{'current':4,'maximum':4})
        self.assertTrue(out['gas_resource_present']);self.assertEqual(out['texture'],'0000000011113333')
        gas=[x for x in out['inventory_candidates'] if x.get('resource')==target.GAS_RESOURCE]
        self.assertEqual(gas[0]['offset'],12)
        self.assertFalse(out['throwable_type_binding_proven']);self.assertFalse(out['native_written'])
        self.assertLess(out['active_read_bytes'],6000);self.assertLess(out['active_read_calls'],110)

    def test_empty_stock_and_refill_are_valid_diagnostic_values(self):
        for value,maximum in ((0,4),(6,6)):
            m=Memory();m.stock(value,maximum);out=self.run_capture(m)
            self.assertEqual(out['stock']['current'],value)

    def test_missing_gas_identity_does_not_guess_from_texture(self):
        m=Memory();m.ptr(m.entities+target.DESCRIPTOR_BASE+48,0xABCDEF)
        self.assertFalse(self.run_capture(m)['gas_resource_present'])

    def test_counter_types_and_bounds(self):
        for current,maximum,kind in ((5,4,4),(4,4,1),(0,0,4)):
            m=Memory();m.stock(current,maximum,kind)
            with self.subTest(current=current,maximum=maximum,kind=kind),self.assertRaisesRegex(ValueError,'SHADER'):
                self.run_capture(m)

    def test_stock_changes_during_capture_fail(self):
        m=Memory();n=[0]
        def change(memory,at,size):
            if at==m.dictionary_at:
                n[0]+=1
                if n[0]==2:m.stock(3,4)
        m.changed=change
        with self.assertRaisesRegex(ValueError,'SNAPSHOT_CHANGED'):self.run_capture(m)

    def test_foreign_bitmap_owner_or_changed_pin_rejected(self):
        for mode in ('owner','pin'):
            m=Memory()
            if mode=='owner':m.ptr(m.panel+m.t['picture']+0xF0,m.panel)
            else:m.put(m.identity['game_base']+m.p['pins'][0]['rva'],b'\0')
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'OWNERSHIP|PIN_CHANGED'):
                self.run_capture(m)

    def test_ship_stops_before_hud_player_reads(self):
        m=Memory();m.put(m.state+target.layout.STATE_OFFSET,struct.pack('<I',3))
        with self.assertRaisesRegex(ValueError,'EXPECTS_MISSION'):self.run_capture(m)
        self.assertEqual(len(m.reads),2)


if __name__=='__main__':unittest.main()
