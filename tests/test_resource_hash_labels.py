"""Exact resource-label conversion and evidence boundaries; no game access."""
from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from resource_hash_labels import REVIEWED_ENEMIES, apply_labels, build_labels, hex_id, runtime_entity_rows


class HashLabels(unittest.TestCase):
    def test_u64_keeps_low_bits(self):
        self.assertEqual(hex_id('10845250369047350884'), '968211C0033DCE64')
        self.assertEqual(hex_id('18446744073709551615'), 'FFFFFFFFFFFFFFFF')
        self.assertNotEqual(hex_id('10845250369047350884'), hex_id('10845250369047350885'))

    def test_rounded_numeric_and_invalid_input_rejected(self):
        for value in (10845250369047350884, float(10845250369047350884),
                      '1.084525036904735e19', '18446744073709551616', '0', '-1', '968211C0033DCE64'):
            self.assertIsNone(hex_id(value), value)

    def test_conflicting_labels_not_chosen(self):
        cells = [dict(row=4, col=0, text='哈希值')]
        for row, name in [(5, '名称甲'), (6, '名称乙')]:
            cells.extend([dict(row=row, col=0, text='10845250369047350884'), dict(row=row, col=1, text=name)])
        value = build_labels(cells)
        self.assertFalse(value['aliases'])
        self.assertIn('968211C0033DCE64', value['conflicts'])

    def test_labels_do_not_invent_fatal_weapon_size_or_ownership(self):
        integration = dict(entities={}, stat_sources={})
        labels = dict(aliases={
            '1111111111111111': dict(name_zh='敌人甲', name_en='Enemy A', row=6, column=1),
            '2222222222222222': dict(name_zh='爆炸筒', name_en='Explosive Barrel', row=7, column=1),
            '3333333333333333': dict(name_zh='未知构筑', name_en='Unknown Building', row=8, column=1),
            '4444444444444444': dict(name_zh='仅有云表名称', name_en='Cloud Label Only', row=9, column=1)})
        native = {'1111111111111111': dict(kill=True, kind='enemy', faction='terminids'),
                  '2222222222222222': dict(kill=False), '3333333333333333': dict(kill=True)}
        out, _ = apply_labels(integration, labels, native)
        self.assertEqual(set(out['entities']), {'1111111111111111'})
        self.assertEqual(out['entities']['1111111111111111']['class'], '未知体型')
        self.assertTrue(all(v['kind'] == 'unknown' for v in out['stat_sources'].values()))
        self.assertIn('4444444444444444',out['stat_sources'])
        self.assertNotIn('4444444444444444',out['entities'])
        self.assertEqual(integration, dict(entities={}, stat_sources={}))

    def test_existing_reviewed_labels_preserved(self):
        old = dict(key='Warrior', name_zh='武斗虫', name_en='Warrior', **{'class': '中型'})
        integration = dict(entities={'1111111111111111': old}, stat_sources={'1111111111111111': dict(name_zh='原名')})
        labels = dict(aliases={'1111111111111111': dict(name_zh='云表异名', name_en='Other', row=6, column=1)})
        out, _ = apply_labels(integration, labels, {'1111111111111111': dict(kind='enemy', kill=True)})
        self.assertEqual(out, integration)

    def test_reviewed_predator_stalker_exact_hash_closes_runtime_kind_gap(self):
        hash_id='D1E990BAF22D5A52'
        labels=dict(aliases={hash_id:dict(name_zh='掠食追踪虫',name_en='Predator Stalker',row=7,column=19)})
        runtime={hash_id:dict(kill=True,id='entity/v1/unresolved/'+hash_id)}
        out,_=apply_labels(dict(entities={},stat_sources={}),labels,runtime)
        row=out['entities'][hash_id]
        self.assertEqual(row['key'],'Predator Stalker')
        self.assertEqual(row['class'],'中型精英')
        self.assertEqual(row['faction'],'terminids')
        self.assertEqual(row['class_basis'],'user_confirmed_2026-10-15')
        self.assertTrue(row['kill'])
        again,_=apply_labels(out,labels,runtime)
        self.assertEqual(out,again,'reviewed regeneration must be idempotent')
        out,_=apply_labels(dict(entities={},stat_sources={}),labels,{hash_id:dict(kill=False)})
        self.assertNotIn(hash_id,out['entities'],'full label alone cannot create an enemy without the Runtime kill identity')

    def test_all_reviewed_missing_kind_identities_keep_names_separate_from_classes(self):
        labels=dict(aliases={hash_id:dict(name_zh=row['name_zh'],name_en=row['name_en'],row=7,column=1)
                            for hash_id,row in REVIEWED_ENEMIES.items()})
        runtime={hash_id:dict(kill=True,id='entity/v1/unresolved/'+hash_id) for hash_id in REVIEWED_ENEMIES}
        out,_=apply_labels(dict(entities={},stat_sources={}),labels,runtime)
        self.assertEqual(len(out['entities']),14)
        self.assertEqual(out['entities']['98152772A72F7838']['asset'],True,'the Dropship variant remains a demolition asset')
        self.assertEqual(out['entities']['34DFD23365472E9E']['air'],True)
        self.assertEqual(out['entities']['D1E990BAF22D5A52']['name_zh'],'掠食追踪虫')
        self.assertEqual(out['entities']['D1E990BAF22D5A52']['class'],'中型精英')
        self.assertEqual(out['entities']['91EBD77931110AFC']['class'],'未知体型',
                         'BFV medium feedback is not the roster classification of an unreviewed variant')
        for hash_id in ('52018DEB9AB6827E','B056F8FC74ABA02D'):
            self.assertEqual(out['entities'][hash_id]['class'],'未知体型')
            self.assertEqual(out['entities'][hash_id]['identity_basis'],
                             'exact_cloud_hash_runtime_kill_and_cloud_enemy_group')
        self.assertTrue(all('／' not in row['name_zh'] and '/中型' not in row['name_zh'] for row in out['entities'].values()))
        again,_=apply_labels(out,labels,runtime)
        self.assertEqual(out,again)

    def test_checked_in_catalog_missing_kind_audit_contract(self):
        value=json.loads((ROOT/'docs/integration-catalogs.json').read_text(encoding='utf8'))
        rows=value['entities']
        self.assertEqual(len(rows),135)
        self.assertEqual(len(value['stat_sources']),1185)
        self.assertEqual(sum(row.get('basis')=='exact_cloud_hash_and_runtime_enemy_type' for row in rows.values()),36)
        reviewed={hash_id:row for hash_id,row in rows.items()
                  if row.get('basis')=='reviewed_exact_hash_runtime_unresolved_enemy'}
        self.assertEqual(set(reviewed),set(REVIEWED_ENEMIES))
        self.assertEqual(len(reviewed),14)
        self.assertEqual(sum(row.get('identity_basis')=='exact_cloud_hash_and_runtime_kill_and_bfv17_type_identity'
                             for row in reviewed.values()),12)
        self.assertEqual(sum(row.get('identity_basis')=='exact_cloud_hash_runtime_kill_and_cloud_enemy_group'
                             for row in reviewed.values()),2)
        legacy=[row for row in rows.values() if row.get('basis') not in
                ('exact_cloud_hash_and_runtime_enemy_type','reviewed_exact_hash_runtime_unresolved_enemy',
                 'reviewed_full_enemy_body_resource')]
        self.assertEqual(len(legacy),84)
        roster=json.loads((ROOT/'docs/enemy-catalog/units.json').read_text(encoding='utf8'))['units']
        roles={row['name_en']:row for row in roster}
        self.assertEqual(len({row['key']for row in rows.values()}&roles.keys()),76)
        self.assertEqual(len({row['key']for row in legacy}&roles.keys()),62)
        for row in legacy+list(reviewed.values()):
            if row['key'] in roles:
                role=roles[row['key']]
                self.assertEqual(row['name_zh'],role['name_zh'])
                self.assertEqual(row['class'],role['display_class'])
                self.assertEqual(row['air'],'飞行' in role['tags'])
        self.assertNotIn('FD5247653C897803',rows,'an unnamed native kill identity is retained as unknown')

    def test_runtime_kind_does_not_leak_from_source_table(self):
        text = 'return {["types"]={["1111111111111111"]={["kill"]=true,["kind"]="enemy"}},["sources"]={["2222222222222222"]={["kind"]="weapon"}}}'
        rows = runtime_entity_rows(text)
        self.assertEqual(set(rows), {'1111111111111111'})
        self.assertTrue(rows['1111111111111111']['kill'])

    def test_cloud_label_same_name_does_not_classify_another_resource(self):
        spec = importlib.util.spec_from_file_location('career_catalog_hash_test', ROOT / 'tools/career-catalogs.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            sdk = Path(directory)
            weapon = dict(name='Weapon Name', slot='primary', resources=['0x1111111111111111'],
                          weaponType='Assault Rifle')
            (sdk/'PlayerWeaponAuthoringCapabilities.json').write_text(json.dumps(dict(weapons=[weapon])))
            (sdk/'SupportWeaponCapabilities.json').write_text(json.dumps(dict(weapons=[])))
            sources = {value: dict(name='Weapon Name', name_zh='同名资源', kind='unknown',
                                  basis='exact_cloud_hash_label_only')
                       for value in ('1111111111111111','2222222222222222')}
            catalog = module.build_catalogs(dict(stat_sources=sources),sdk)['weapon_catalog']
            self.assertEqual(catalog['1111111111111111']['category'],'primary')
            self.assertEqual(catalog['2222222222222222']['category'],'unknown')


if __name__ == '__main__':
    unittest.main()
