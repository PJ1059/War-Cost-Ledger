"""Independent bounded-input review; owned fixtures only, no live process API."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import test_hit_consumer_followup as existing

c = existing.c


class NullContextMemory(existing.Memory):
    def read(self, address, length):
        if address - self.base == existing.ship_reader['STATE_GLOBAL']:
            self.reads.append((address, length))
            return bytes(8)
        return super().read(address, length)


class InitialNullScenario(existing.Scenario):
    def open(self, pid):
        memory = (NullContextMemory() if self.stage == 0
                  else existing.Memory(state=3))
        self.memories.append(memory)
        return memory


class Review(unittest.TestCase):
    def test_null_ship_context_waits_without_reading_code(self):
        scenario = InitialNullScenario(stages=(0, 3))
        with tempfile.TemporaryDirectory() as folder:
            result = scenario.run(folder, True)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(scenario.sleeps, [2])
            self.assertEqual(scenario.memories[0].reads,
                             [(scenario.memories[0].base
                               + existing.ship_reader['STATE_GLOBAL'], 8)])
            self.assertEqual(result['ship_wait_read_calls'], 3)
            self.assertEqual(result['ship_wait_bytes_read'], 20)
            self.assertTrue(all(m.closed for m in scenario.memories))

    def test_disjoint_declared_ancestry_survives_outer_prefix_offsets(self):
        memory = existing.Memory()
        nodes = memory.configure_chain(1)
        raw, meta = c.capture(memory, memory.identity)
        meta['sha256'] = hashlib.sha256(raw).hexdigest()
        c.verify_saved(meta, raw)
        self.assertEqual(raw[:5], bytes.fromhex(c.CALL_PIN))
        self.assertEqual(meta['body_binary_offset'], 5)
        self.assertEqual([(r['rva'], r['length']) for r in meta['ranges'][1:]],
                         [(nodes[1][0], 0x80), (nodes[0][0], 0x100)])
        self.assertEqual([r['binary_offset'] for r in meta['ranges']], [0, 5, 133])
        self.assertFalse(meta['logical_function_complete'])
        self.assertFalse(meta['candidate_body']['logical_function_complete'])
        for address, length in memory.reads:
            if address - memory.base == c.CALLER or length in (4, 12):
                continue
            self.assertTrue(any(memory.base + b <= address
                                and address + length <= memory.base + e
                                for b, e, _ in nodes))

    def test_empty_callee_pin_does_not_bypass_declared_body_limit(self):
        memory = existing.Memory()
        memory.end = memory.begin + 4097
        evidence = {}
        with self.assertRaisesRegex(ValueError, 'FUNCTION_TOO_LARGE'):
            c.capture(memory, memory.identity, evidence=evidence)
        self.assertEqual(memory.reads[0], (memory.base + c.CALLER, 5))
        self.assertTrue(all(length == 12 for _, length in memory.reads[1:]))
        self.assertLessEqual(evidence['budget']['bytes_requested'], 8192)
        self.assertLessEqual(evidence['budget']['read_calls'], 32)

    def test_identity_mismatch_stops_before_any_process_open_or_retry(self):
        scenario = existing.Scenario()
        deps = scenario.deps()
        def mismatch(*_):
            raise ValueError('owned build mismatch')
        deps['validate_identity'] = mismatch
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'new'
            with self.assertRaisesRegex(ValueError, 'owned build mismatch'):
                c.run(output, True, deps, scenario.sleep)
            status = json.loads((output / 'status.json').read_text('utf8'))
            self.assertEqual(status['status'], 'failed')
            self.assertFalse(status['capture_attempted'])
            self.assertEqual(scenario.memories, [])
            self.assertEqual(scenario.sleeps, [])
            self.assertFalse(list(output.rglob('*.bin')))


if __name__ == '__main__':
    unittest.main()
