"""Two owned smoke groups for fixed new source/target; no Game or full scan."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_hit_contact_registration_index as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owned_forwarder_reference_index',
    ROOT / 'tools/hit-contact-forwarder-reference-index.py')
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)


class ForwarderIndexSmokeTests(unittest.TestCase):
    def test_private_new_target_pin_source_and_small_exact_target_stream(self):
        old = (fixture.indexer.TARGET_RVA, fixture.indexer.PIN_RVA, fixture.indexer.PIN_HEX)
        index = wrapper.private_index()
        self.assertEqual((index.TARGET_RVA, index.PIN_RVA, index.PIN_HEX),
                         (0x13F7690, 0x13F7690, wrapper.PIN_HEX))
        self.assertEqual((index.MAX_BYTES, index.MAX_READS, index.MAX_SECONDS), (48 * 1024 * 1024, 256, 2.0))
        source = index.validate_sources()
        self.assertEqual(source['target_rva'], 0x13F7690)
        self.assertEqual(source['old_parent_provenance']['target_rva'], 0x13AC1F0)
        self.assertTrue(source['old_parent_source_validated_before_target_override'])
        self.assertFalse(source['logical_function_complete'])
        with patch.object(fixture, 'indexer', index):
            code, data = fixture.reference_payloads()
            scenario = fixture.Scenario(code, data, state=2, after=2)
            with tempfile.TemporaryDirectory() as parent:
                result = fixture.ContactReferenceTests().run_small(scenario, Path(parent) / 'capture',
                                                                  allow_title_screen=True)
                meta = json.loads(Path(result['json_path']).read_text('utf8'))
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(meta['target_rva'], 0x13F7690)
                self.assertEqual(meta['fresh_pin']['rva'], 0x13F7690)
                self.assertEqual(meta['fresh_pin']['hex'], wrapper.PIN_HEX)
                self.assertEqual(meta['source']['metadata_sha256'], wrapper.SOURCE_SHA)
                self.assertEqual(len(meta['candidates']), 6)
                self.assertTrue(all(row['target_rva'] == 0x13F7690 for row in meta['candidates']))
                self.assertEqual(meta['ship_before']['state'], 2)
                self.assertEqual(meta['ship_before'], meta['ship_after'])
                self.assertFalse(meta['registered_callback_proven'])
                self.assertFalse(meta['whole_binary_saved'])
        self.assertEqual((fixture.indexer.TARGET_RVA, fixture.indexer.PIN_RVA, fixture.indexer.PIN_HEX), old)
        self.assertEqual(hashlib.sha256(wrapper.INDEX.read_bytes()).hexdigest(), wrapper.INDEX_SHA)

    def test_changed_source_and_claimed_logical_complete_refuse_before_game_open(self):
        calls = []
        deps = {'Process': lambda *_: calls.append('open')}
        with tempfile.TemporaryDirectory() as parent:
            with patch.object(wrapper, 'SOURCE_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'SOURCE_CHANGED'):
                    wrapper.run(Path(parent) / 'capture', deps)
            self.assertEqual(calls, [])
            source = Path(parent) / 'changed-source'
            source.mkdir()
            raw = (wrapper.SOURCE / 'forwarder.json').read_bytes()
            changed = json.loads(raw)
            changed['logical_function_complete'] = True
            (source / 'forwarder.json').write_text(json.dumps(changed), 'utf8')
            (source / 'forwarder.bin').write_bytes((wrapper.SOURCE / 'forwarder.bin').read_bytes())
            with patch.object(wrapper, 'SOURCE_SHA', hashlib.sha256((source / 'forwarder.json').read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'SOURCE_PROFILE'):
                    wrapper.validate_source(fixture.indexer.profile.FINGERPRINT, source)
            changed['logical_function_complete'] = False
            changed['exception_records'][-1]['begin'] += 1
            (source / 'forwarder.json').write_text(json.dumps(changed), 'utf8')
            with patch.object(wrapper, 'SOURCE_SHA', hashlib.sha256((source / 'forwarder.json').read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'DECLARATION_CHANGED'):
                    wrapper.validate_source(fixture.indexer.profile.FINGERPRINT, source)


if __name__ == '__main__':
    unittest.main()
