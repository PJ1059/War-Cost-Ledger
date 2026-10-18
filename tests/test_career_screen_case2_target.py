"""Fixed 17B fixture, no table scan, no live process or native invocation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import test_hit_consumer_followup as prior
spec = importlib.util.spec_from_file_location('case2_slot_profile_test', ROOT / 'tools/career-screen-case2-target.py')
profile = importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)

class Memory(prior.Memory):
    def __init__(self, bad=None, target=0x149550A, short=False, **kwargs):
        super().__init__(**kwargs)
        self.bad, self.target, self.short = bad, target, short
    def read(self, at, length):
        rva = at - self.base
        if rva in (profile.CALLER, profile.SWITCH, profile.SLOT):
            self.reads.append((at, length))
            if rva == profile.SLOT:
                raw = struct.pack('<I', self.target)
                return raw[:-1] if self.short else raw
            raw = bytes.fromhex(profile.CALL_PIN if rva == profile.CALLER else profile.SWITCH_PIN)
            return b'\0' + raw[1:] if self.bad == rva else raw
        return super().read(at, length)

class Scenario(prior.Scenario):
    def open(self, pid):
        memory = Memory(state=self.stages[self.stage], **self.options)
        self.memories.append(memory);return memory
    def run(self, folder, wait=False):
        return profile.run(Path(folder) / 'new', self.deps())

class Tests(unittest.TestCase):
    def test_one_slot_exact_budget_and_target_not_executed(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as folder:
            result = scenario.run(folder)
            meta = json.loads(Path(result['json_path']).read_text('utf8'))
            raw = Path(result['binary_path']).read_bytes()
            profile.verify_saved(meta, raw)
            self.assertEqual(len(raw), 17)
            self.assertEqual(meta['target_rva'], 0x149550A)  # Owned fixture, not an actual table claim.
            self.assertEqual(len(scenario.memories[0].reads), 7)
            self.assertEqual(sum(n for _, n in scenario.memories[0].reads), 41)
            self.assertFalse(meta['native_called']);self.assertFalse(meta['statistics_read'])
            self.assertEqual(scenario.sleeps, [])
    def test_nonship_reads_no_pin_or_slot(self):
        for state in (2, 4, 5):
            scenario = Scenario([state])
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError, 'EXPECTS_SHIP'):
                    scenario.run(folder)
                self.assertEqual(len(scenario.memories[0].reads), 2)
    def test_bad_pins_never_read_target_slot(self):
        for rva, code_reads in ((profile.CALLER, 1), (profile.SWITCH, 2)):
            scenario = Scenario(bad=rva)
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError, 'PIN_MISMATCH'):
                    scenario.run(folder)
                memory = scenario.memories[0]
                self.assertEqual(len(memory.reads), 2 + code_reads)
                self.assertNotIn((memory.base + profile.SLOT, 4), memory.reads)
    def test_short_slot_and_outside_image_never_save_success(self):
        for options in ({'short':True}, {'target':0}, {'target':profile.session.reader.IMAGE_SIZE}):
            scenario = Scenario(**options)
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):scenario.run(folder)
                self.assertFalse(list(Path(folder).rglob('*.bin')))
    def test_ship_changed_rejects(self):
        scenario = Scenario(after=4)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'SHIP_CHANGED'):scenario.run(folder)
    def test_soft_budget_before_any_code_read(self):
        memory = Memory();ticks = iter((0, 3))
        with self.assertRaisesRegex(ValueError, 'BUDGET'):
            profile.capture(memory, memory.identity, clock=lambda: next(ticks))
        self.assertEqual(memory.reads, [])
    def test_existing_folder_no_dependencies_or_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
                profile.run(folder, {'fingerprints':lambda: self.fail('dependency called')})
    def test_saved_pin_range_target_corruption(self):
        scenario = Scenario()
        with tempfile.TemporaryDirectory() as folder:
            result = scenario.run(folder)
            meta = json.loads(Path(result['json_path']).read_text('utf8'));raw=Path(result['binary_path']).read_bytes()
            with self.assertRaises(ValueError):profile.verify_saved(meta, b'\0'+raw[1:])
            bad=copy.deepcopy(meta);bad['target_rva']+=1
            with self.assertRaises(ValueError):profile.verify_saved(bad,raw)
    def test_private_profile_no_shared_mutation(self):
        self.assertEqual(prior.OLD, (prior.old_reader.TARGET_RVA, prior.old_reader.TARGET_PIN, prior.old_reader.REVISION,
                                   prior.old_fire.RANGES, prior.old_fire.PINS, prior.old_fire.REVISION))

if __name__ == '__main__':
    unittest.main()
