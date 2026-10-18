"""Owned memory/Win32 doubles only; no process, OS cursor, input or Game access."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
t=load('native_cursor',ROOT/'tools/career-native-cursor-snapshot.py')
f=load('cursor_memory',ROOT/'tests/test_career_ui_snapshot.py')

class Memory(f.Memory):
    def __init__(self):
        super().__init__(nodes=0);self.manager=0x306000000;self.cursor=self.manager+t.CURSOR_OFFSET
        self.put(self.identity['game_base']+t.MANAGER_RVA,struct.pack('<Q',self.manager))
        self.widget(self.cursor,0,kind=3);self.put(self.cursor+4,struct.pack('<ff',700,600))
        self.put(self.cursor+0x200,struct.pack('<Q',self.manager+0x160))
        self.put(self.cursor+0x26C,struct.pack('<ff',704,580))
        for at,pin in t.CALLER_PINS:self.put(self.identity['game_base']+at,bytes.fromhex(pin))
        self.adapter=t.evidence();self.put(self.identity['game_base']+t.ADAPTER_RVA,self.adapter)
        owner,_=t.layout.locate(t.Budget(self,self.identity,clock=lambda:0))
        self.source={'status':'complete','headers_stable':True,'identity':dict(self.identity),'owner_before':owner,'game_pid':123}
        self.reads=[];self.queries=[]

def os_sample(pid=123,hwnd=50,x=704,y=212):
    return {'foreground':True,'pid':pid,'hwnd':hwnd,'screen_point':[x+10,y+20],
            'client_point':[x,y],'client_size':[1436,792],'client_rect':[0,0,1436,792]}

class Tests(unittest.TestCase):
    def capture(self,m,os_read=None):return t.capture(m,m.identity,m.source,os_read or os_sample,m.adapter,clock=lambda:0)
    def test_fixed_cursor_branch_and_budget(self):
        m=Memory();r=self.capture(m)
        self.assertEqual(r['selected_branch'],'field_26c');self.assertEqual(r['selected_native_point'],[704,580])
        self.assertTrue(r['os_point_stable']);self.assertFalse(r['native_called']);self.assertFalse(r['input_sent'])
        self.assertEqual([n for at,n in m.reads if at==m.cursor],[256,256])
        self.assertLessEqual(r['active_read_bytes'],t.MAX_BYTES);self.assertLessEqual(r['active_read_calls'],t.MAX_READS)
        print('fixture capture budget',r['active_read_bytes'],r['active_read_calls'])
    def test_both_special_selectors_and_local_fallback(self):
        for offset,expected in ((0x160,'field_26c'),(0x288,'field_26c'),(0x400,'local_position_4')):
            m=Memory();m.put(m.cursor+0x200,struct.pack('<Q',m.manager+offset));r=self.capture(m)
            self.assertEqual(r['selected_branch'],expected)
            self.assertEqual(r['selected_native_point'],[700,600]if expected=='local_position_4'else[704,580])
    def test_wrong_foreground_pin_or_parent_reads_no_cursor(self):
        for mode in ('foreground','pin','parent'):
            m=Memory()
            if mode=='pin':m.put(m.identity['game_base']+t.CALLER_PINS[0][0],b'\x90')
            if mode=='parent':m.source['owner_before']['controller']+=8
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                self.capture(m,(lambda:os_sample(pid=456))if mode=='foreground'else None)
            self.assertNotIn((m.cursor,256),m.reads)
    def test_changed_cursor_rejected_and_os_movement_reported(self):
        m=Memory();seen=0
        def changed(mem,at,size):
            nonlocal seen
            if at==mem.cursor+0x26C:
                seen+=1
                if seen==2:mem.put(at,struct.pack('<ff',1,2))
        m.changed=changed
        with self.assertRaisesRegex(ValueError,'CURSOR_CHANGED'):self.capture(m)
        m=Memory();samples=iter([os_sample(),os_sample(y=213)])
        self.assertFalse(self.capture(m,lambda:next(samples))['os_point_stable'])
    def test_foreground_wait_requires_continuity_and_has_no_game_reads(self):
        m=Memory();now=[0.0];samples=[]
        def read():
            samples.append(now[0]);return os_sample(pid=456 if .4<=now[0]<.6 else 123)
        def sleep(dt):now[0]+=dt
        r=t.wait_foreground(123,3,read,lambda:now[0],sleep)
        self.assertGreaterEqual(r['seconds'],1.6);self.assertGreaterEqual(r['foreground_seconds'],1)
        self.assertEqual(m.reads,[])
        self.assertEqual(t.wait_foreground(123,0,lambda:self.fail('default must not poll')),{'waited':False})
        for value in (-1,61,float('nan')):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'WAIT_RANGE'):t.wait_foreground(123,value,read)
    def test_timeout_before_process_open_and_no_game_memory(self):
        m=Memory();now=[0.0]
        with tempfile.TemporaryDirectory()as folder:
            import json
            p=Path(folder)/'source.json';p.write_text(json.dumps(m.source),'utf8')
            with self.assertRaisesRegex(ValueError,'FOREGROUND_TIMEOUT'):
                t.run(p,Path(folder)/'output',.3,deps=f.deps(m),os_read=lambda:os_sample(pid=456),
                    clock=lambda:now[0],sleep=lambda dt:now.__setitem__(0,now[0]+dt))
        self.assertEqual(m.entered,0);self.assertEqual(m.reads,[])

if __name__=='__main__':unittest.main()
