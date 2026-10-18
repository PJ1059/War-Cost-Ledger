"""Focused owned-memory tests; no live Game reads."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_hit_contact_registration_index as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recon_locale_index', ROOT / 'tools/recon-discovery-locale-reference-index.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReconLocaleIndexTests(unittest.TestCase):
    def small_run(self, index, scenario, output):
        with patch.object(fixture, 'indexer', index):
            return fixture.ContactReferenceTests().run_small(scenario, output)

    def test_sources_exact_ids_scope_and_preserved_budgets(self):
        index = module.private_index()
        self.assertEqual(len(index.SECTIONS), 1)
        self.assertEqual((index.MAX_BYTES, index.MAX_READS, index.MAX_SECONDS), (48*1024*1024, 256, 2))
        self.assertEqual(index.MAX_CANDIDATES, 64)
        self.assertTrue(index.validate_sources()['templates_verified_in_two_languages'])
        raw = b'\x90' + struct.pack('<I', module.LOCALE_IDS[0]) + struct.pack('<I', module.LOCALE_IDS[1]+1)
        self.assertEqual([(r[0], r[1]) for r in module.byte_matches(raw, 0, 'code', b'')], [(1,4)])
        with self.assertRaisesRegex(ValueError, 'CODE_ONLY'):
            module.byte_matches(raw, 0, 'declared_ro_data', b'')

    def test_chunk_boundary_once_no_full_image_and_byte_only_semantics(self):
        index = module.private_index()
        code = bytearray(b'\x90'*256)
        for at, target in ((62, module.LOCALE_IDS[0]), (128, module.LOCALE_IDS[1])):
            code[at:at+4] = struct.pack('<I', target)
        scenario = fixture.Scenario(bytes(code), b'')
        with tempfile.TemporaryDirectory() as folder:
            result = self.small_run(index, scenario, Path(folder)/'capture')
            meta = json.loads(Path(result['json_path']).read_text('utf8'))
            self.assertEqual([r['locale_id'] for r in meta['candidates']], list(module.LOCALE_IDS))
            self.assertEqual([r['rva'] for r in meta['candidates']], [0x1000+62, 0x1000+128])
            self.assertTrue(all(r['window_bytes']<=64 and not r['instruction_boundary_verified'] for r in meta['candidates']))
            self.assertFalse(meta['whole_binary_saved'])
            self.assertFalse(meta['runtime_producer_proven'])
            self.assertEqual(meta['ship_before'], meta['ship_after'])
            self.assertTrue(scenario.memory.closed)

    def test_candidate_cap_and_nonship_refusal(self):
        index = module.private_index()
        for options, expected in (({}, 'truncated'), ({'state':4}, 'EXPECTS_SHIP')):
            with tempfile.TemporaryDirectory() as folder:
                scenario = fixture.Scenario(struct.pack('<I', module.LOCALE_IDS[0])*70, b'', **options)
                if options:
                    with self.assertRaisesRegex(ValueError, expected):
                        self.small_run(index, scenario, Path(folder)/'capture')
                    self.assertEqual(scenario.memory.payload_reads, 0)
                else:
                    result = self.small_run(index, scenario, Path(folder)/'capture')
                    meta = json.loads(Path(result['json_path']).read_text('utf8'))
                    self.assertEqual(result['status'], expected)
                    self.assertEqual(len(meta['candidates']), 64)

    def test_source_hash_and_wrong_pid_refuse_without_process_open(self):
        with tempfile.TemporaryDirectory() as folder:
            changed = tuple((p, '0'*64, texts) for p, sha, texts in module.SOURCES)
            with patch.object(module, 'SOURCES', changed):
                with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                    module.run(Path(folder)/'source', 1, {})
            scenario = fixture.Scenario(bytes(256), b'')
            with self.assertRaisesRegex(ValueError, 'PID_CHANGED'):
                module.run(Path(folder)/'pid', 999999, scenario.dependencies())
            self.assertEqual(scenario.opens, 0)

    def test_source_pin_or_budget_failure_withholds_candidates(self):
        index = module.private_index()
        for options, cap, expected in (({'changed_pin':True}, 256, 'LOADED_SOURCE_CHANGED'),
                                       ({}, 6, 'BUDGET')):
            with tempfile.TemporaryDirectory() as folder, patch.object(index, 'MAX_READS', cap):
                scenario = fixture.Scenario(struct.pack('<I',module.LOCALE_IDS[0])+bytes(252), b'', **options)
                with self.assertRaisesRegex(ValueError, expected):
                    self.small_run(index, scenario, Path(folder)/'capture')
                meta = json.loads((Path(folder)/'capture/references.incomplete.json').read_text('utf8'))
                self.assertNotIn('candidates', meta)
                self.assertTrue(meta['results_withheld'])


if __name__ == '__main__':
    unittest.main()
