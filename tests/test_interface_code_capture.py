import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('interface_capture', ROOT / 'tools/interface-code-capture.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CapturePlan(unittest.TestCase):
    def test_sequential_independent_failures_and_exact_tools(self):
        calls = []
        def fake(args, **kw):
            name = Path(args[1]).name
            self.assertTrue(Path(args[1]).is_file())
            calls.append(name)
            return SimpleNamespace(returncode=1 if len(calls) == 1 else 0)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(module.run(fake, Path(folder)), 1)
            state = json.loads((Path(folder) / 'status.json').read_text())
            self.assertEqual(state['status'], 'finished_with_gaps')
            self.assertIsNone(state['timeout_seconds'])
            self.assertFalse(state['native_written'])
            self.assertEqual(state['concurrent_samplers'], 1)
            self.assertEqual(calls, [p[1] for p in module.PLAN])
            self.assertEqual(len(state['samplers']), 3)

    def test_all_success_finishes_without_retry_or_relaunch(self):
        calls = []
        def fake(args, **kw):
            calls.append(args)
            return SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(module.run(fake, Path(folder)), 0)
            self.assertEqual(len(calls), 3)
            state = json.loads((Path(folder) / 'status.json').read_text())
            self.assertEqual(state['status'], 'finished')


if __name__ == '__main__':
    unittest.main()
