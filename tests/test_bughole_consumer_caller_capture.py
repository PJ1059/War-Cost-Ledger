"""Offline profile checks; importing this tool never opens a process."""
from pathlib import Path
import importlib.util
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bughole_consumer_profile',
    ROOT / 'tools/bughole-consumer-caller-capture.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ConsumerCaller(unittest.TestCase):
    def test_exact_saved_consumer_and_budgets(self):
        self.assertEqual(profile.CALL_RVA + 5 + struct.unpack('<i', bytes.fromhex(profile.CALL_HEX)[1:])[0], 0x13E1DC0)
        self.assertEqual(profile.reader.TARGET_RVA, 0x13F7D46)
        self.assertEqual(profile.parent.TARGET_RVA, 0x13E1DC0)
        self.assertEqual(profile.worker.EXPECTED_PID, 7416)
        self.assertEqual((profile.worker.MAX_BYTES, profile.worker.MAX_IO, profile.worker.MAX_SECONDS), (8192, 48, 2))
        self.assertEqual(profile.reader.MAX_FUNCTION_BYTES, 4096)

    def test_real_metadata_resolver_finds_only_containing_declaration(self):
        reader = profile.reader
        original, original_size = reader.table_read, reader.EXCEPTION_SIZE
        entries = [(0x13F7000, 0x13F7800, 0x2500000), (0x13F7900, 0x13F7E00, 0x2500010),
                   (0x13F8000, 0x13F8100, 0x2500020)]
        reads = []
        try:
            reader.EXCEPTION_SIZE = len(entries) * 12
            def read(_, index):
                reads.append(index)
                return struct.pack('<III', *entries[index])
            reader.table_read = read
            journal = []
            self.assertEqual(reader.find_function(None, journal), entries[1][:2])
            self.assertEqual(reads, [1])
            self.assertEqual(journal[-1]['unwind_rva'], 0x2500010)
            # Oversized actual ranges are retained as metadata, never read as code.
            entries[1] = (0x13F6900, 0x13F8E00, 0x2500010)
            with self.assertRaisesRegex(ValueError, 'FUNCTION_TOO_LARGE'):
                reader.find_function(None, [])
        finally:
            reader.table_read, reader.EXCEPTION_SIZE = original, original_size

if __name__ == '__main__':
    unittest.main()
