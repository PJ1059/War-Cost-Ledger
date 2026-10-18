"""One actual owned native scenario plus changed-owner CAS, no Game."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_frame_counter_tail', ROOT / 'tools/native/frame_counter_tail_owned.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class OwnedFrameCounterTests(unittest.TestCase):
    def test_native_float_counter_restore_and_third_party_owner(self):
        result = native.run_owned()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['wrapper_bytes'], 14)
        self.assertEqual(result['baseline_float_xmm0'], result['wrapped_float_xmm0'])
        self.assertEqual(result['wrapped_float_xmm0'], result['restored_float_xmm0'])
        self.assertEqual(result['restored_counts'], {'counter': 3, 'original_calls': 9})
        self.assertTrue(result['third_party_slot_preserved'])
        self.assertFalse(result['owner_checked_restore_success_after_third_party'])
        self.assertEqual(result['final_counter'], 4)
        self.assertEqual(result['final_original_calls'], 10)
        self.assertTrue(result['allocation_retained_until_process_exit'])
        self.assertFalse(result['game_slot_replacement_proven'])
        self.assertFalse(result['game_accessed'])


if __name__ == '__main__':
    unittest.main()
