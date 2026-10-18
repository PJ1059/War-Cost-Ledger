"""Owned code/exception fixtures only; no live game reads or native calls."""
from pathlib import Path
import importlib.util
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'tests')]
import recon_chat_code_capture as original
import test_recon_chat_code_capture as prior
spec = importlib.util.spec_from_file_location('recon_session_event_capture', ROOT/'tools/recon-session-event-code-capture.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class SessionWriterTests(unittest.TestCase):
    def test_exact_known_source_and_isolation(self):
        self.assertEqual(len(tool.verify_source()), 64)
        self.assertEqual(tool.TARGET_RVA, 0x10834ED)
        self.assertEqual(len(bytes.fromhex(tool.TARGET_PIN)), 58)
        self.assertIsNot(tool.reader, original)
        self.assertEqual(original.TARGET_RVA, 0x1097A7C)
        self.assertEqual(tool.reader.MAX_FUNCTION_BYTES, 4096)
        self.assertEqual(tool.reader.MAX_BYTES, 8192)
        self.assertEqual(tool.reader.MAX_READS, 32)

    def fixture(self):
        # Put the known PIN in one synthetic RF without crossing its boundary.
        memory = prior.Memory()
        memory.begin = tool.TARGET_RVA & ~0xff
        memory.end = memory.begin + 0x200
        return memory

    def test_code_is_saved_without_claiming_discovery_semantics(self):
        with patch.object(prior, 'sampler', tool.reader):
            memory = self.fixture()
            binary, meta = tool.reader.capture(memory, memory.identity, clock=prior.Clock())
            tool.reader.verify_saved(meta, binary)
        self.assertEqual(meta['target_rva'], tool.TARGET_RVA)
        self.assertEqual(meta['recon_events_emitted'], 0)
        self.assertEqual(meta['chat_messages_read'], 0)
        self.assertFalse(meta['native_called'])
        self.assertFalse(meta['native_written'])
        self.assertLessEqual(meta['budget']['bytes_requested'], 8192)

    def test_wrong_pin_and_short_read_stop(self):
        for flag, reason in [('corrupt', 'PIN_MISMATCH'), ('short', 'SHORT_READ')]:
            with patch.object(prior, 'sampler', tool.reader):
                memory = self.fixture()
                setattr(memory, flag, True)
                with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, reason):
                    tool.reader.capture(memory, memory.identity, clock=prior.Clock())

    def test_large_or_long_chain_does_not_sample_unbounded_code(self):
        with patch.object(prior, 'sampler', tool.reader):
            memory = self.fixture()
            memory.end = memory.begin + 4097
            with self.assertRaisesRegex(ValueError, 'FUNCTION_TOO_LARGE'):
                tool.reader.capture(memory, memory.identity, clock=prior.Clock())
            self.assertTrue(all(length == 12 for _, length in memory.reads))
            memory = self.fixture()
            memory.configure_chain(4)
            with self.assertRaisesRegex(ValueError, 'UNWIND_DEPTH_LIMIT'):
                tool.reader.capture(memory, memory.identity, clock=prior.Clock())
            self.assertTrue(all(length <= 12 for _, length in memory.reads))


if __name__ == '__main__':
    unittest.main()
