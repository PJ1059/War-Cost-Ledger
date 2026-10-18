"""Owned byte fixtures only; never imports the process backend or opens Game."""
from pathlib import Path
import importlib.util
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hole_snapshot',ROOT/'tools/bughole-descriptor-snapshot.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Memory:
    def __init__(self,count=3,mode=4,old_world=True,dynamic=False):
        self.base=0x140000000;self.manager=0x20000000;self.state=0x21000000
        self.holes,self.prior,_=m.sources();self.world=self.prior[0]['world'] if old_world else 0x30000000
        self.ranges=[];self.reads=[]
        def put(address,data):self.ranges.append((address,bytes(data)))
        self.put=put
        for rva,pin in m.PINS:put(self.base+rva,bytes.fromhex(pin))
        put(self.base+m.MANAGER,struct.pack('<Q',self.manager))
        put(self.base+m.WORLD,struct.pack('<Q',self.world))
        put(self.base+m.layout.STATE_GLOBAL,struct.pack('<Q',self.state))
        put(self.state+m.layout.STATE_OFFSET,struct.pack('<I',mode))
        put(self.manager+12,struct.pack('<I',count))
        if count>1024:return
        indices=[self.prior[0]['record_index'],4000,9000]+list(range(10000,11021))
        if dynamic:indices=list(range(0x17000,0x17000+count))
        indices=indices[:count]
        put(self.manager+0x4030,b''.join(struct.pack('<Q',0x40000000+i*32)for i in range(count)))
        put(self.manager+0x6030,b''.join(struct.pack('<I',i)for i in indices))
        for i,index in enumerate(indices):
            kind=next(iter(self.holes)) if i==1 else '0000000000000001'
            put(0x40000000+i*32,struct.pack('<QIIII',int(kind,16),i+100,i+200,0,1))
            put(self.world+m.RECORDS+12*index,struct.pack('<I H B B I',i+200,4,0,1,3))
        for item in self.prior:
            if item['record_index'] not in indices:
                put(self.world+m.RECORDS+12*item['record_index'],struct.pack('<I H B B I',item['unit'],4,0,1,3))
    def query(self,address):
        for start,raw in self.ranges:
            if start<=address<start+len(raw):
                return {'base':start,'size':len(raw),'state':0x1000,'type':0x1000000,'protect':0x40}
        raise AssertionError(f'unplanned query {address:x}')
    def read(self,address,size):
        self.reads.append((address,size))
        for start,raw in self.ranges:
            if start<=address<address+size<=start+len(raw):return raw[address-start:address-start+size]
        raise AssertionError('unplanned read')
    def snapshot(self):return m.snapshot(self,{'game_base':self.base,'game_size':m.layout.IMAGE_SIZE},clock=lambda:0)


class Tests(unittest.TestCase):
    def test_closed_hole_and_scenery(self):
        result=Memory().snapshot()
        self.assertEqual(result['status'],'complete');self.assertEqual(result['holes'],1)
        hole=result['rows'][1]
        self.assertTrue(hole['record_matches_unit'] and hole['record_stable'] and hole['descriptor_stable'])
        self.assertEqual(hole['record']['stage'],1)
        self.assertTrue(result['previous_samples'][0]['in_descriptor_manager'])
        self.assertFalse(result['previous_samples'][1]['in_descriptor_manager'])
    def test_capacity_budget(self):
        result=Memory(count=1024).snapshot()
        self.assertLessEqual(result['read_bytes'],65536);self.assertLessEqual(result['read_calls'],1280)
    def test_dynamic_ordinary_hole_included(self):
        result=Memory(dynamic=True).snapshot()
        self.assertEqual(result['holes'],1)
        row=result['rows'][1]
        self.assertEqual(row['record_index'],0x17001)
        self.assertTrue(row['record_matches_unit'] and row['record_stable'] and row['descriptor_stable'])
    def test_count_rejected(self):
        with self.assertRaisesRegex(ValueError,'HOLE_DESCRIPTOR_COUNT'):Memory(count=1025).snapshot()
    def test_ship_preserved_world(self):
        self.assertEqual(Memory(mode=3).snapshot()['status'],'complete')
    def test_ship_changed_world_stops_before_descriptor(self):
        memory=Memory(mode=3,old_world=False);result=memory.snapshot()
        self.assertEqual(result['status'],'previous_mission_world_unavailable')
        self.assertFalse(any(address==memory.manager+12 for address,size in memory.reads))


if __name__=='__main__':unittest.main()
