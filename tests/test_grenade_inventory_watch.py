"""Owned memory only: no game process access."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module
target=load('grenade_watch_test',ROOT/'tools/grenade-inventory-watch.py')
fixture=load('grenade_watch_memory',ROOT/'tests/test_grenade_hud_snapshot.py')


class Tests(unittest.TestCase):
    def memory(self):
        m=fixture.Memory();g=m.identity['game_base']
        for at,raw in target.pins():m.put(g+at,raw)
        inventory=struct.unpack('<Q',m.read(g+target.base.INVENTORY_GLOBAL,8))[0]
        descriptors,desc,counts=m.alloc(128),m.alloc(128),m.alloc(128)
        m.ptr(inventory+64,descriptors);m.ptr(descriptors,desc);m.ptr(inventory+88,counts)
        who=bytearray(24);struct.pack_into('<I',who,8,77);struct.pack_into('<I',who,20,1)
        m.put(desc,who);m.ptr(m.records+40,int(target.base.GAS_RESOURCE,16));m.put(counts,struct.pack('<I',4))
        m.throwable_count=counts;m.throwable_descriptor=desc
        return m

    def test_native_resource_count_zero_and_refill(self):
        m=self.memory()
        for n in (4,3,0,6):
            m.put(m.throwable_count,struct.pack('<I',n));out=target.snapshot(m,m.identity,clock=lambda:0)
            self.assertEqual(out['resource'],target.base.GAS_RESOURCE);self.assertEqual(out['count'],n)
            self.assertFalse(out['native_written']);self.assertLess(out['bytes'],1600)

    def test_wrong_descriptor_ownership_rejected(self):
        m=self.memory();m.put(m.throwable_descriptor+20,struct.pack('<I',0))
        with self.assertRaisesRegex(ValueError,'OWNERSHIP'):target.snapshot(m,m.identity,clock=lambda:0)

    def test_stock_changes_fail_closed(self):
        m=self.memory();n=[0]
        def change(memory,at,size):
            if at==m.throwable_count:
                n[0]+=1
                if n[0]==2:m.put(at,struct.pack('<I',3))
        m.changed=change
        with self.assertRaisesRegex(ValueError,'INVENTORY_CHANGED'):target.snapshot(m,m.identity,clock=lambda:0)

    def test_ship_has_no_inventory_reads(self):
        m=self.memory();m.put(m.state+target.base.layout.STATE_OFFSET,struct.pack('<I',3));m.reads=[]
        with self.assertRaisesRegex(ValueError,'EXPECTS_MISSION'):target.snapshot(m,m.identity,clock=lambda:0)
        self.assertEqual(len(m.reads),2)


if __name__=='__main__':unittest.main()
