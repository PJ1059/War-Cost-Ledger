"""Fixed MOD child-tree fixtures; never imports a live process dependency."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
target=load('own_controls',ROOT/'tools/career-own-controls-snapshot.py')
prior=load('own_controls_memory',ROOT/'tests/test_career_ui_snapshot.py')

class Memory(prior.Memory):
    def __init__(self,labels=('累计战果','历史对局','下一局')):
        super().__init__();self.frame=0x303000000;self.first=0x303001000
        self.widget(self.controller+0x4DAF8,self.controller+0xA0,child=self.frame)
        self.widget(self.frame,self.controller+0x4DAF8,child=self.first)
        self.put(self.frame+0x24,struct.pack('<ff',420,747))
        self.put(self.frame+0x64,struct.pack('<f',1));self.put(self.frame+0x8C,struct.pack('<f',1))
        for index,label in enumerate(labels):
            row=self.first+index*4096;text=row+1024
            self.widget(row,self.frame,child=text,sibling=row+4096 if index<len(labels)-1 else 0)
            self.widget(text,row,kind=9)
            self.put(text+0x11C,(label.encode()+b'\0').ljust(24,b'\0'))
            font=bytearray(60);struct.pack_into('<ff',font,0,14,14)
            self.put(text+0x444,font)
        raw=bytes(self.bytes[self.frame+i] for i in range(256))
        owner={'controller':self.controller,'gui_context':self.gui,'list':self.list,
               'panel':self.controller+target.layout.CAREER_PANEL}
        self.source={'status':'complete','headers_stable':True,'identity':self.identity,'game_pid':123,
            'owner_before':owner,'nodes':[{'address':self.frame,**target.parent.unpack(raw),
                                         'header_hex':raw.hex(),'geometry':target.parent.geometry(raw)}]}

class Tests(unittest.TestCase):
    def capture(self,m):return target.capture(m,m.identity,m.source,clock=lambda:0)
    def test_three_known_controls_font_and_both_geometry_headers(self):
        m=Memory();r=self.capture(m)
        self.assertEqual(set(r['found']),{'tab_collection','tab_history','history_next'})
        self.assertEqual(len(r['children']),3)
        self.assertEqual(r['found']['tab_history']['text']['requested_height'],14)
        self.assertEqual(r['found']['tab_history']['text']['geometry']['pivot_y'],0)
        self.assertLess(r['active_read_calls'],target.MAX_READS)
        self.assertFalse(r['native_written']);self.assertFalse(r['native_called']);self.assertFalse(r['account_modified'])
    def test_24_cap_does_not_follow_25th_child(self):
        m=Memory(tuple('other' for _ in range(25)));r=self.capture(m)
        self.assertEqual(len(r['children']),24);self.assertTrue(r['child_limit_reached'])
        self.assertNotIn((m.first+24*4096,256),m.reads)
        self.assertLessEqual(r['active_read_bytes'],target.MAX_BYTES)
        self.assertLessEqual(r['active_read_calls'],target.MAX_READS)
    def test_unknown_child_owner_and_non_single_text_are_rejected(self):
        for offset,value in [(240,0x303200000),(232,0x303200000)]:
            m=Memory();text=m.first+1024;m.put(text+offset,struct.pack('<Q',value))
            with self.subTest(offset=offset),self.assertRaises(ValueError):self.capture(m)
            self.assertNotIn((0x303200000,256),m.reads)
    def test_frame_move_rejected_before_descending(self):
        m=Memory();m.put(m.frame+4,struct.pack('<f',1))
        with self.assertRaisesRegex(ValueError,'FRAME_CHANGED'):self.capture(m)
        self.assertNotIn((m.first,256),m.reads)
    def test_stale_frame_parent_field_does_not_prove_live_attachment(self):
        m=Memory();m.put(m.controller+0x4DAF8+224,struct.pack('<Q',0))
        with self.assertRaisesRegex(ValueError,'FRAME_NOT_ATTACHED'):self.capture(m)
        self.assertNotIn((m.frame,256),m.reads)
    def test_closed_page_and_bad_source_identity_never_read_own_frame(self):
        for which in ('page','identity'):
            m=Memory()
            if which=='page':m.alphas=[0]
            else:m.source['identity']={'game_base':1}
            with self.subTest(which=which),self.assertRaises((ValueError,target.parent.NotVisible)):self.capture(m)
            self.assertNotIn((m.frame,256),m.reads)
    def test_resume_fixed_second_segment_without_rewalking_first(self):
        m=Memory(tuple('other' for _ in range(24))+('累计战果','历史对局','下一局'))
        first=self.capture(m);m.reads=[]
        second=target.capture(m,m.identity,m.source,clock=lambda:0,continuation=first)
        self.assertEqual(second['segment'],2);self.assertEqual(len(second['children']),3)
        self.assertEqual(set(second['found']),set(target.TARGETS.values()))
        for index in range(23):self.assertNotIn((m.first+index*4096,256),m.reads)
        self.assertEqual(m.reads.count((m.first+23*4096,256)),1)
        with self.assertRaisesRegex(ValueError,'CONTINUATION_SOURCE'):
            target.capture(m,m.identity,m.source,clock=lambda:0,continuation=second)
    def test_changed_saved_link_refused_before_second_segment(self):
        m=Memory(tuple('other' for _ in range(25)));first=self.capture(m)
        m.reads=[];m.put(m.first+23*4096+232,struct.pack('<Q',0))
        with self.assertRaisesRegex(ValueError,'CONTINUATION_LINK_CHANGED'):
            target.capture(m,m.identity,m.source,clock=lambda:0,continuation=first)
        self.assertNotIn((m.first+24*4096,256),m.reads)

if __name__=='__main__':unittest.main()
