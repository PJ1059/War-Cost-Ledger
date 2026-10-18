"""Reuse owned PE/Ship fixtures with the exact private entity-map profile."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
spec=importlib.util.spec_from_file_location('entity_map_owned_support',
                                         ROOT/'tests/test_hit_queue_consumer_code_capture.py')
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
spec=importlib.util.spec_from_file_location('entity_map_private_profile',
                                         ROOT/'tools/hit-entity-descriptor-code-capture.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
support.drain=profile.session

class EntityMapTests(support.QueueDrainTests):
    def test_private_profile_and_real_capture_are_isolated(self):
        reader=profile.session.reader
        self.assertEqual(reader.TARGET_RVA,0xFD9D50)
        self.assertEqual(reader.TARGET_PIN,'4c8b1541224902')
        memory=support.Memory()
        raw,meta=reader.capture(memory,memory.identity)
        self.assertEqual(raw[0x50:0x57],bytes.fromhex(reader.TARGET_PIN))
        self.assertEqual(meta['source_revision'],'hit_entity_map_declared_code_v1')
        self.assertEqual(memory.body_reads(),[(memory.begin,256)])
        self.assertLessEqual(meta['budget']['read_calls'],32)
        self.assertLessEqual(meta['budget']['bytes_requested'],8192)
        reader.verify_saved(meta,raw)
        self.assert_profiles_unchanged()

if __name__=='__main__':
    unittest.main()
