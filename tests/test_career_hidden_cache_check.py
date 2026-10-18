"""Saved user-confirmed reference replay only; no game or native invocation."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'dist/career-target-rows-20261012-a7a9566c/career-rows.json'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load('hidden_checker_fixture', ROOT / 'tools/career-hidden-cache-check.py')


class Memory:
    def __init__(self, alpha=0.0):
        reference = checker.reference(REFERENCE)
        self.identity = dict(reference['identity'])
        self.bytes, self.reads, self.entered, self.changed = {}, [], 0, None
        self.alpha_address = reference['owner_before']['panel'] + 195256 + 84
        for record in reference['read_records']:
            raw = bytes.fromhex(record['raw_hex'])
            assert len(raw) == record['length']
            self.put(record['address'], raw)
        self.put(self.alpha_address, struct.pack('<f', alpha))
        addresses = sorted(self.bytes)
        self.regions = []
        for address in addresses:
            if self.regions and address == self.regions[-1][0] + self.regions[-1][1]:
                self.regions[-1][1] += 1
            else:
                self.regions.append([address, 1])

    def put(self, address, raw):
        self.bytes.update((address + index, value) for index, value in enumerate(raw))

    def query(self, address):
        base = self.identity['game_base']
        if base <= address < base + self.identity['game_size']:
            return {'base': base, 'size': self.identity['game_size'], 'state': 0x1000,
                    'type': 0x1000000, 'protect': 0x20}
        for start, length in self.regions:
            if start <= address < start + length:
                return {'base': start, 'size': length, 'state': 0x1000, 'type': 0x20000, 'protect': 4}
        raise AssertionError('unowned query')

    def read(self, address, length):
        self.reads.append((address, length))
        if self.changed:
            self.changed(self, address, length)
        return bytes(self.bytes[address + index] for index in range(length))

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *args):
        return False


def dependencies(memory, *, pid=48892):
    return {'fingerprints': lambda: {}, 'game_processes': lambda: (pid,),
            'resolve_game': lambda _: dict(memory.identity), 'validate_identity': lambda *_: None,
            'Process': lambda _: memory}


class Tests(unittest.TestCase):
    def run_case(self, memory, **options):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'new'
            return checker.run(folder, reference_path=REFERENCE,
                               deps=dependencies(memory), clock=lambda: 0, **options)

    def test_visible_hidden_actual_alpha_kept_and_exact54_reads6729_bytes(self):
        for alpha in (0.0, 1.0):
            with self.subTest(alpha=alpha):
                memory = Memory(alpha)
                result = self.run_case(memory)
                self.assertEqual((result['active_read_calls'], result['active_read_bytes']), (54, 6729))
                self.assertEqual((result['alpha_before'], result['alpha_after']), (alpha, alpha))
                self.assertEqual(result['owner_before']['alpha_raw_hex'], struct.pack('<f', alpha).hex())
                self.assertEqual(result['status'], 'ui_cache_observed')
                for key in ('server_ready', 'backend_ready', 'career_stats_ready', 'account_modified', 'native_called', 'native_written'):
                    self.assertFalse(result[key])

    def test_wrong_reference_sha_before_dependencies_or_reads(self):
        memory = Memory()
        with tempfile.TemporaryDirectory() as temporary:
            bad = Path(temporary) / 'bad.json'; bad.write_text('{}')
            with patch.object(checker, 'private_target', side_effect=AssertionError('target')):
                with self.assertRaisesRegex(ValueError, 'REFERENCE_SHA'):
                    checker.run(Path(temporary) / 'new', reference_path=bad, deps=dependencies(memory))
        self.assertEqual(memory.reads, [])

    def test_pid_or_module_changed_before_process(self):
        for failure in ('pid', 'module'):
            memory = Memory(); deps = dependencies(memory, pid=48893 if failure == 'pid' else 48892)
            if failure == 'module': memory.identity['game_base'] += 4096
            with tempfile.TemporaryDirectory() as temporary, self.subTest(failure=failure):
                with self.assertRaisesRegex(ValueError, 'REFERENCE_PID|REFERENCE_MODULE'):
                    checker.run(Path(temporary) / 'new', reference_path=REFERENCE, deps=deps, clock=lambda: 0)
            self.assertEqual(memory.reads, []); self.assertEqual(memory.entered, 0)

    def test_nonship_has_two_reads_zero_registry_pin_or_row(self):
        memory = Memory(); source = checker.reference(REFERENCE)
        memory.put(source['owner_before']['state_context'] + 705052, struct.pack('<I', 2))
        with self.assertRaisesRegex(ValueError, 'WAITING_SHIP'): self.run_case(memory)
        self.assertEqual(len(memory.reads), 2); self.assertEqual(sum(length for _, length in memory.reads), 12)

    def test_reference_value_change_rejected_before_success_file(self):
        memory = Memory(); source = checker.reference(REFERENCE)
        value = source['rows_before']['deaths']['value']['address']
        memory.put(value + 288, struct.pack('<Q', 4634))
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'new'
            with self.assertRaisesRegex(ValueError, 'VALUE_CHANGED'):
                checker.run(folder, reference_path=REFERENCE, deps=dependencies(memory), clock=lambda: 0)
            self.assertFalse((folder / 'career-hidden-cache.json').exists())
            self.assertEqual(json.loads((folder / 'status.json').read_text())['status'], 'failed')
        self.assertEqual(memory.entered, 1)

    def test_list_rebuild_or_context_change_stops_once(self):
        source = checker.reference(REFERENCE)
        for failure in ('rebuild', 'context'):
            memory = Memory(); count = [0]; at = source['owner_before']['list']
            def mutate(memory, address, length):
                if address == at:
                    count[0] += 1
                    if count[0] == 2:
                        offset = 224 if failure == 'rebuild' else 248
                        memory.put(at + offset, struct.pack('<Q', source['row_path_before'][1] if failure == 'rebuild' else source['owner_before']['gui_context'] + 8))
            memory.changed = mutate
            with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, 'LIST_REBUILT|OWNER_CHANGED'):
                self.run_case(memory)
            self.assertEqual(memory.entered, 1)

    def test_bad_pin_or_build_rejected_before_rows(self):
        for failure in ('pin', 'build'):
            memory = Memory(); deps = dependencies(memory)
            if failure == 'pin': memory.put(memory.identity['game_base'] + 0x143C950, b'\0')
            else: deps['fingerprints'] = lambda: (_ for _ in ()).throw(ValueError('BUILD_CHANGED'))
            with tempfile.TemporaryDirectory() as temporary, self.subTest(failure=failure):
                with self.assertRaisesRegex(ValueError, 'CODE_PIN|BUILD_CHANGED'):
                    checker.run(Path(temporary) / 'new', reference_path=REFERENCE, deps=deps, clock=lambda: 0)
            self.assertTrue(len(memory.reads) < 12)

    def test_final_process_change_has_no_success_output(self):
        memory = Memory(); deps = dependencies(memory); calls = [0]
        def pids():
            calls[0] += 1
            return (48892 if calls[0] == 1 else 48893,)
        deps['game_processes'] = pids
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'new'
            with self.assertRaisesRegex(ValueError, 'MODULE_CHANGED'):
                checker.run(folder, reference_path=REFERENCE, deps=deps, clock=lambda: 0)
            self.assertFalse((folder / 'career-hidden-cache.json').exists())

    def test_existing_output_and_frozen_source_change_stop_before_reads(self):
        memory = Memory()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
                checker.run(temporary, reference_path=REFERENCE, deps=dependencies(memory))
            with patch.object(checker, 'TARGET_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'TARGET_SOURCE_CHANGED'):
                    checker.run(Path(temporary) / 'new', reference_path=REFERENCE, deps=dependencies(memory))
        self.assertEqual(memory.reads, [])

    def test_private_locator_does_not_pollute_frozen_module(self):
        ordinary = load('ordinary_target_fixture', ROOT / 'tools/career-target-rows.py')
        locate = ordinary.layout.locate
        private = checker.private_target()
        self.assertIsNot(private, ordinary); self.assertIsNot(private.layout, ordinary.layout)
        self.assertIs(ordinary.layout.locate, locate)
        memory = Memory(0.0)
        owner, reason = ordinary.layout.locate(ordinary.Budget(memory, memory.identity, clock=lambda: 0))
        self.assertIsNone(owner); self.assertEqual(reason, 'waiting_career')

    def test_out_of_range_alpha_or_soft_budget_stops(self):
        for alpha in (-1.0, 1.5, float('nan')):
            memory = Memory(alpha)
            with self.subTest(alpha=alpha), self.assertRaisesRegex(ValueError, 'CACHE_ALPHA'):
                self.run_case(memory)
        memory = Memory(); ticks = iter((0.0, 1.0))
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(ValueError, 'SOFT_BUDGET'):
            checker.run(Path(temporary) / 'new', reference_path=REFERENCE,
                        deps=dependencies(memory), clock=lambda: next(ticks))
        self.assertEqual(memory.reads, [])


if __name__ == '__main__':
    unittest.main()
