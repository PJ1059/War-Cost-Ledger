"""Owned memory/Ship/exception fixtures; never opens a live game."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import test_recon_chat_code_capture as prior
import recon_chat_code_capture as old_reader
import fire_code_capture as old_fire
OLD = (old_reader.TARGET_RVA, old_reader.TARGET_PIN, old_reader.REVISION,
       old_fire.RANGES, old_fire.PINS, old_fire.REVISION)
spec = importlib.util.spec_from_file_location('consumer_test', ROOT / 'tools/hit-consumer-followup.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
import runpy
ship_reader = runpy.run_path(str(ROOT / 'tools/career-cache-capture.py'))


class Memory(prior.Memory):
    context = 0x1011ED90A0
    def __init__(self, state=3, after=3, bad_call=False, short_body=False):
        original = prior.sampler
        try:
            prior.sampler = c.session.reader
            super().__init__()
        finally:
            prior.sampler = original
        self.native_state, self.after, self.states = state, after, 0
        self.bad_call, self.short_body, self.closed = bad_call, short_body, False
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.closed = True
    def query(self, address):
        if self.context <= address < self.context + 0x100000:
            return {'base':self.context,'size':0x100000,'state':0x1000,'type':0x20000,'protect':4}
        return super().query(address)
    def read(self, address, length):
        rva = address - self.base
        if rva == ship_reader['STATE_GLOBAL']:
            self.reads.append((address,length)); return struct.pack('<Q', self.context)
        if address == self.context + ship_reader['STATE_OFFSET']:
            self.reads.append((address,length))
            state = self.native_state if not self.states else self.after
            self.states += 1; return struct.pack('<I',state)
        if rva == c.CALLER:
            self.reads.append((address,length))
            return bytes(5) if self.bad_call else bytes.fromhex(c.CALL_PIN)
        original = prior.sampler
        try:
            prior.sampler = c.session.reader
            raw = super().read(address,length)
        finally:
            prior.sampler = original
        if self.short_body and self.begin <= rva < self.end:
            return raw[:-1]
        return raw


class Scenario:
    def __init__(self, stages=(3,), **options):
        self.stages, self.stage, self.options = stages, 0, options
        self.memories, self.sleeps, self.fingerprints = [], [], 0
    def pids(self):
        return () if self.stages[self.stage] is None else (61204,)
    def resolve(self, pid):
        if self.stages[self.stage] == 'loading':
            raise FileNotFoundError('fixture module loading')
        return dict(prior.Memory.identity)
    def fingerprint(self):
        self.fingerprints += 1; return {}
    def open(self,pid):
        memory = Memory(state=self.stages[self.stage], **self.options)
        self.memories.append(memory); return memory
    def sleep(self,seconds):
        self.sleeps.append(seconds); self.stage += 1
        if self.stage >= len(self.stages): raise AssertionError('Unexpected retry')
    def deps(self):
        return {'fingerprints':self.fingerprint,'validate_identity':lambda *_:None,
                'game_processes':self.pids,'resolve_game':self.resolve,'Process':self.open,
                'ship_state':ship_reader['ship_state']}
    def run(self,folder,wait=False):
        return c.run(Path(folder)/'new',wait,self.deps(),self.sleep)


class Tests(unittest.TestCase):
    def test_actual_caller_precedes_declared_metadata_body(self):
        s=Scenario()
        with tempfile.TemporaryDirectory() as folder:
            result=s.run(folder); meta=json.loads(Path(result['json_path']).read_text('utf8'))
            raw=Path(result['binary_path']).read_bytes(); c.verify_saved(meta,raw)
            memory=s.memories[0]
            self.assertEqual(memory.reads[2],(memory.base+c.CALLER,5))
            self.assertEqual(raw[:5],bytes.fromhex(c.CALL_PIN))
            self.assertEqual(meta['callee_rva'],0x93C580)
            self.assertFalse(meta['classification_ready'])
            self.assertFalse(meta['logical_function_complete'])
            self.assertEqual(meta['budget']['bytes_requested']+5+24,sum(n for _,n in memory.reads))
            self.assertEqual(meta['budget']['read_calls']+1+4,len(memory.reads))
            self.assertEqual(s.fingerprints,1)
            self.assertTrue(memory.closed)
    def test_wait_140_seconds_and_initial_module_without_code(self):
        s=Scenario([None]*67+['loading',2,4,5,3])
        with tempfile.TemporaryDirectory() as folder:
            result=s.run(folder,True)
            self.assertGreater(sum(s.sleeps),120)
            self.assertEqual(result['ship_wait_polls'],4)
            self.assertEqual(result['ship_wait_bytes_read'],48)
            self.assertEqual(result['ship_wait_read_calls'],8)
            self.assertEqual(result['waiting_code_reads'],0)
            for memory in s.memories[:-1]:
                self.assertEqual(sum(n for _,n in memory.reads),12)
                self.assertNotIn((memory.base+c.CALLER,5),memory.reads)
            self.assertTrue(all(m.closed for m in s.memories))
    def test_nonship_once_never_reads_code(self):
        for state in (2,4,5):
            s=Scenario([state])
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError,'EXPECTS_SHIP'): s.run(folder)
                self.assertEqual(len(s.memories[0].reads),2)
                self.assertEqual(s.sleeps,[])
    def test_bad_actual_call_never_reads_metadata_or_body(self):
        s=Scenario(bad_call=True)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'PIN_MISMATCH'):s.run(folder,True)
            self.assertEqual(len(s.memories[-1].reads),3)
            self.assertEqual(s.sleeps,[])
            self.assertFalse(list(Path(folder).rglob('*.bin')))
    def test_short_body_and_ship_change_do_not_save_success(self):
        for options, message in (({'short_body':True},'SHORT_READ'),({'after':4},'SHIP_CHANGED')):
            s=Scenario(**options)
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError,message):s.run(folder)
                self.assertFalse(list(Path(folder).rglob('*.bin')))
    def test_source_pin_and_body_boundary_reverified(self):
        s=Scenario()
        with tempfile.TemporaryDirectory() as folder:
            result=s.run(folder);meta=json.loads(Path(result['json_path']).read_text('utf8'))
            raw=Path(result['binary_path']).read_bytes()
            with self.assertRaises(ValueError):c.verify_saved(meta,b'\0'+raw[1:])
            changed=copy.deepcopy(meta);changed['candidate_body']['function_begin']+=1
            with self.assertRaises(ValueError):c.verify_saved(changed,raw)
    def test_private_profiles_dont_change_existing_tools(self):
        self.assertEqual(OLD,(old_reader.TARGET_RVA,old_reader.TARGET_PIN,old_reader.REVISION,
                              old_fire.RANGES,old_fire.PINS,old_fire.REVISION))


if __name__=='__main__':
    unittest.main()
