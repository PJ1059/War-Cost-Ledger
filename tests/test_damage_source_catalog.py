import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AC8 = 'A8CFFB316F0B5C5F'
G6 = '4CE9EAB785A79B7B'
R36 = 'B6AFF2195568767F'
G7 = '075B19B068FB1045'


class DamageSourceCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads((ROOT / 'docs/damage-source-catalog.json').read_text(encoding='utf-8'))
        spec = importlib.util.spec_from_file_location('ledger_damage_catalog', ROOT / 'tools/damage-source-catalog.py')
        cls.generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.generator)

    def edges(self, kind, native_id):
        return self.document['nodes'][f'{kind}:{native_id}']

    def test_ac8_default_projectile_direct_and_explosion_damage_are_distinct(self):
        self.assertIn({'kind': 'damage_info', 'id': 213, 'field_offset': 60, 'role': 'direct_hit'}, self.edges('projectile', 115))
        self.assertIn({'kind': 'explosion', 'id': 404, 'field_offset': 144, 'role': 'impact'}, self.edges('projectile', 115))
        self.assertIn({'kind': 'damage_info', 'id': 370, 'field_offset': 4, 'role': 'explosion_damage'}, self.edges('explosion', 404))

    def test_ac8_flak_native_secondary_root_does_not_depend_on_partial_wiki_mapping(self):
        source = self.document['sources'][AC8]
        self.assertIn({'kind': 'projectile', 'id': 284, 'component': 'ProjectileWeaponComponentData', 'member': '576'}, source['roots'])
        self.assertEqual(source['sdk_branch_coverage'], 'partial')
        self.assertIn('AC-8 P1 IE', source['sdk_unresolved_branch_labels'])
        self.assertEqual(source['evidence'], 'parsed_native_typed_references')
        self.assertIn({'kind': 'damage_info', 'id': 202, 'field_offset': 60, 'role': 'direct_hit'}, self.edges('projectile', 284))
        self.assertIn({'kind': 'explosion', 'id': 380, 'field_offset': 144, 'role': 'impact'}, self.edges('projectile', 284))

    def test_flak_explosion_emits_thirty_shared_shrapnel(self):
        self.assertIn({'kind': 'damage_info', 'id': 346, 'field_offset': 4, 'role': 'explosion_damage'}, self.edges('explosion', 380))
        self.assertIn({'kind': 'projectile', 'id': 201, 'field_offset': 84, 'role': 'shrapnel', 'count': 30}, self.edges('explosion', 380))
        self.assertIn({'kind': 'damage_info', 'id': 189, 'field_offset': 60, 'role': 'direct_hit'}, self.edges('projectile', 201))

    def test_zero_count_reference_is_not_an_emission_edge(self):
        self.assertFalse(any(row['kind'] == 'projectile' for row in self.edges('explosion', 404)))
        self.assertIn({'explosion': 404, 'projectile': 201, 'count': 0}, self.document['dormant_zero_count_shrapnel'])

    def test_shared_shrapnel_keeps_ac8_frag_eruptor_and_lure_candidates(self):
        for kind, native_id in [('projectile', 201), ('damage_info', 189)]:
            row = self.document['reverse'][kind][str(native_id)]
            self.assertEqual(row['candidates'], [G6, 'A20683199DFC19E8', AC8, R36])
            self.assertTrue(row['shared'])
            self.assertTrue(row['unresolved'])

    def test_eagle_and_unnamed_consumers_prevent_default_ac8_exclusivity(self):
        for kind, native_id in [('projectile', 115), ('explosion', 404), ('damage_info', 213), ('damage_info', 370)]:
            row = self.document['reverse'][kind][str(native_id)]
            self.assertEqual(row['candidates'], [AC8])
            self.assertTrue(row['shared'])
            self.assertTrue(row['unresolved'])
        evidence = self.document['unresolved_origin_evidence']['projectile:115']
        self.assertIn('resource:0BD0F9D59048E9D1', evidence)
        self.assertIn('resource:B6CAF17BA65A7147', evidence)

    def test_flak_direct_damage_has_one_resolved_native_parent(self):
        for kind, native_id in [('projectile', 284), ('damage_info', 202)]:
            self.assertEqual(self.document['reverse'][kind][str(native_id)],
                             {'candidates': [AC8], 'unresolved': False, 'shared': False})

    def test_unowned_alternate_projectile_is_not_silently_discarded(self):
        row = self.document['reverse']['damage_info']['346']
        self.assertEqual(row['candidates'], [AC8])
        self.assertTrue(row['unresolved'])
        self.assertIn('unowned:projectile:206', self.document['unresolved_origin_evidence']['damage_info:346'])

    def test_frag_eruptor_and_pineapple_have_separate_native_families(self):
        self.assertIn(257, self.document['sources'][G6]['types']['explosion'])
        self.assertIn(158, self.document['sources'][R36]['types']['explosion'])
        self.assertEqual(self.document['sources'][G7]['types'],
                         {'projectile': [210], 'explosion': [8, 44], 'damage_info': [336, 337], 'beam': [], 'arc': []})
        self.assertNotIn(G7, self.document['reverse']['damage_info']['189']['candidates'])

    def test_resource_hashes_and_native_enum_namespaces_stay_separate(self):
        for kind, rows in self.document['reverse'].items():
            self.assertIn(kind, ('projectile', 'explosion', 'damage_info', 'beam', 'arc'))
            for native_id, row in rows.items():
                self.assertTrue(native_id.isdecimal())
                self.assertEqual(row['candidates'], sorted(set(row['candidates'])))
                for resource in row['candidates']:
                    self.assertRegex(resource, r'^[0-9A-F]{16}$')
                    self.assertIn(resource, self.document['sources'])

    def test_all_native_edges_have_concrete_typed_targets(self):
        for node, edges in self.document['nodes'].items():
            for edge in edges:
                self.assertIn(f"{edge['kind']}:{edge['id']}", self.document['nodes'], node)
                if edge.get('role') == 'shrapnel':
                    self.assertGreater(edge['count'], 0)

    def test_public_blast_context_uses_source_specific_native_radius(self):
        self.assertEqual(self.document['source_radius'][AC8], 8)
        self.assertEqual(self.document['source_radius'][R36], 8)
        self.assertGreater(self.document['source_radius'][G6], 0)
        self.assertNotIn('A6A735ACCB4A327F', self.document['source_radius'], 'Stalwart has no parsed explosion radius')
        self.assertNotIn('46.5', self.document['source_radius_policy'])

    def test_all_five_native_namespaces_are_complete_without_cross_namespace_ids(self):
        expected = {'projectile': 350, 'explosion': 422, 'damage_info': 649, 'beam': 30, 'arc': 16}
        self.assertEqual(set(self.document['reverse']), set(expected))
        for kind, count in expected.items():
            self.assertEqual(len(self.document['reverse'][kind]), count, kind)
            self.assertTrue(all(f'{kind}:{native_id}' in self.document['nodes']
                                for native_id in self.document['reverse'][kind]), kind)
        self.assertEqual(len(self.document['nodes']), sum(expected.values()))

    def test_laser_and_arc_native_damage_chains_are_not_omitted(self):
        cases = [('27EE1ED8F6FB6356', 'BeamWeaponComponentData', 'beam', 8, 501, 12),
                 ('3C86E871923F3970', 'BeamWeaponComponentData', 'beam', 6, 508, 12),
                 ('7B06196E90154C88', 'BeamWeaponComponentData', 'beam', 11, 500, 12),
                 ('076DD5D4F4360204', 'ArcWeaponComponentData', 'arc', 3, 199, 36),
                 ('74599E56F72F9D7E', 'ArcWeaponComponentData', 'arc', 13, 211, 36)]
        for source, component, kind, native_id, damage_id, offset in cases:
            with self.subTest(source=source):
                root = {'kind': kind, 'id': native_id, 'component': component, 'member': '0'}
                self.assertIn(root, self.document['resource_nodes'][source])
                self.assertIn(root, self.document['sources'][source]['roots'])
                self.assertIn({'kind': 'damage_info', 'id': damage_id, 'field_offset': offset,
                               'role': 'beam_damage' if kind == 'beam' else 'arc_damage'},
                              self.edges(kind, native_id))
                self.assertIn(source, self.document['reverse']['damage_info'][str(damage_id)]['candidates'])

    def test_laser_cannon_resource_variants_remain_shared_instead_of_selecting_a_hash(self):
        sources = ['1980D92B619FF5FE', '56070F36CFFFA8A8', 'D54B9505C0F72873']
        self.assertEqual(self.document['reverse']['damage_info']['507']['candidates'], sources)
        self.assertTrue(self.document['reverse']['damage_info']['507']['shared'])
        for source, beam in zip(sources, [24, 10, 1]):
            self.assertEqual(self.document['sources'][source]['types']['beam'], [beam])
            self.assertIn(507, self.document['sources'][source]['types']['damage_info'])

    def test_full_resource_roots_keep_unlabelled_scythe_and_eagle_consumers(self):
        roots = self.document['resource_nodes']
        self.assertIn({'kind': 'projectile', 'id': 115, 'component': 'ProjectileWeaponComponentData',
                       'member': '0'}, roots['B6CAF17BA65A7147'])
        self.assertIn({'kind': 'beam', 'id': 8, 'component': 'BeamWeaponComponentData',
                       'member': '0'}, roots['7E3145A5BAA4B948'])
        self.assertNotIn('7E3145A5BAA4B948', self.document['sources'])
        row = self.document['reverse']['damage_info']['501']
        self.assertIn('27EE1ED8F6FB6356', row['candidates'])
        self.assertTrue(row['shared'])
        self.assertTrue(row['unresolved'], 'one named Scythe plus an unlabelled consumer is not an exact identity')
        self.assertIn('resource:7E3145A5BAA4B948', self.document['unresolved_origin_evidence']['damage_info:501'])
        for resource, refs in roots.items():
            self.assertRegex(resource, r'^[0-9A-F]{16}$')
            for ref in refs:
                self.assertIn(f"{ref['kind']}:{ref['id']}", self.document['nodes'])
                self.assertIn('component', ref)
                self.assertIn('member', ref)

    def test_unowned_native_rows_stay_explicitly_unresolved(self):
        for kind, rows in self.document['reverse'].items():
            for native_id, row in rows.items():
                if not row['candidates']:
                    self.assertTrue(row['unresolved'], (kind, native_id))

    def test_arc_and_beam_raw_files_are_part_of_the_pinned_input_contract(self):
        expected = {'generated_beam_settings.dl_bin': 'FDE93701608D12CB1AA4985F11EB9F2BAB8BB6DC4E8F556B7F7B18B171C7017B',
                    'generated_arc_settings.dl_bin': '08E1461A8D8EE1C46FBCE72FFAA629B489AE512B8B8253AE187D9DBF78A0F159'}
        for name, fingerprint in expected.items():
            self.assertEqual(self.document['inputs']['datalibrary'][name], fingerprint)
            self.assertEqual(self.generator.PINNED_SETTINGS_SHA256[name], fingerprint)

    def test_explosion_event_names_roundtrip_to_explosion_ids_not_damage_ids(self):
        names = self.document['explosion_names']
        self.assertEqual(len(names), 257)
        for name, native_id in names.items():
            self.assertIsInstance(name, str)
            self.assertIs(type(native_id), int)
            self.assertIn(str(native_id), self.document['reverse']['explosion'])
        for name, native_id in {'support_weapon/ac8_autocannon/impact': 404,
                                'support_weapon/ac8_autocannon/function_impact': 380,
                                'support_weapon/rl77_airburst_rocket_launcher/impact': 325,
                                'support_weapon/rl77_airburst_rocket_launcher/function_expiry': 300,
                                'support_weapon/rl77_airburst_rocket_launcher/function_expiry/shrapnel_expiry': 7,
                                'throwable/g4_gas/detonation': 177,
                                'GP-20 Ultimatum': 341}.items():
            self.assertEqual(names[name], native_id)
        self.assertNotEqual(names['support_weapon/ac8_autocannon/impact'], 370,
                            'ExplosionType 404 must not become its DamageInfoType 370')
        self.assertEqual(self.document['inputs']['runtime']['domains/explosion_catalogue.lua'],
                         self.generator.PINNED_EXPLOSION_DOMAIN_SHA256)

    def test_legacy_explosion_name_collisions_are_omitted_instead_of_picked(self):
        rows = [('canonical/a', 1, 'shared legacy'), ('canonical/b', 2, 'shared legacy'),
                ('canonical/c', 3, 'safe legacy'), ('canonical/d', 3, 'safe legacy')]
        index = self.generator.unique_explosion_names(rows)
        self.assertNotIn('shared legacy', index)
        self.assertEqual(index['safe legacy'], 3)
        self.assertEqual(index['canonical/a'], 1)
        fields = self.generator.lua_fields('{["damage"]={["type"]=346},["type"]=380,["nested"]={{["type"]=99}}}')
        self.assertEqual(fields['type'], '380')
        self.assertEqual(self.generator.lua_fields(fields['damage'])['type'], '346')

    def test_regeneration_is_reproducible_when_offline_inputs_are_available(self):
        try:
            self.generator.discover_datalibrary(self.generator.RUNTIME_DEFAULT)
        except (FileNotFoundError, KeyError):
            self.skipTest('Optional pinned authoring data is unavailable; checked-in native contracts still run')
        self.assertEqual(self.generator.build(), self.document)

    def test_mismatched_settings_cannot_regenerate_reviewed_catalog(self):
        try:
            self.generator.discover_datalibrary(self.generator.RUNTIME_DEFAULT)
        except (FileNotFoundError, KeyError):
            self.skipTest('Optional pinned authoring data is unavailable')
        real_sha = self.generator.sha

        for name in ('generated_projectile_settings.dl_bin', 'generated_beam_settings.dl_bin',
                     'generated_arc_settings.dl_bin'):
            with self.subTest(name=name):
                def changed(path):
                    return '0' * 64 if Path(path).name == name else real_sha(path)

                with patch.object(self.generator, 'sha', side_effect=changed):
                    with self.assertRaisesRegex(ValueError, 'settings fingerprints'):
                        self.generator.build()


if __name__ == '__main__':
    unittest.main()
