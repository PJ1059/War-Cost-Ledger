"""Exercise native Windows APIs against this Python process only."""
import ctypes
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fire_code_windows as adapter


@unittest.skipUnless(os.name == 'nt', 'Windows adapter')
class WindowsTests(unittest.TestCase):
    def test_x64_abi(self):
        self.assertEqual(ctypes.sizeof(adapter._ModuleEntry), 1080)
        self.assertEqual(ctypes.sizeof(adapter._MemoryBasicInformation), 48)
        self.assertEqual(adapter._MemoryBasicInformation.RegionSize.offset, 24)
        self.assertEqual(adapter.PROCESS_VM_READ | adapter.PROCESS_QUERY_INFORMATION, 0x410)

    def test_own_buffer_exact_read_and_query(self):
        raw = b'owned\x00buffer\x80\xff'
        buffer = ctypes.create_string_buffer(raw)
        with adapter.Process(os.getpid()) as process:
            self.assertEqual(process.read(ctypes.addressof(buffer), len(raw)), raw)
            region = process.query(ctypes.addressof(buffer))
            self.assertEqual(region['state'], 0x1000)
            self.assertLessEqual(region['base'], ctypes.addressof(buffer))
            self.assertGreater(region['base'] + region['size'], ctypes.addressof(buffer))
            with self.assertRaises(OSError):
                process.read(1, 4)
        self.assertIsNone(process._handle)
        process.close()
        with self.assertRaises(ValueError):
            process.read(ctypes.addressof(buffer), 1)

    def test_own_modules_and_absent_game(self):
        modules = adapter._modules(os.getpid())
        self.assertTrue(modules)
        self.assertTrue(any(Path(item['path']).name.casefold() == Path(sys.executable).name.casefold()
                            for item in modules))
        with self.assertRaises(FileNotFoundError):
            adapter.resolve_game(os.getpid())


if __name__ == '__main__':
    unittest.main()
