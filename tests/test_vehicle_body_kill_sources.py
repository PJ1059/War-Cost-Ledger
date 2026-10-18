"""Reviewed parent source identities and exclusions; no game access."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from vehicle_body_kill_sources import REVIEWED, build_sources


class VehicleBodySources(unittest.TestCase):
    def fixture(self, directory):
        runtime = Path(directory)
        sdk = runtime/'sdk';sdk.mkdir()
        domain = runtime/'domains';domain.mkdir()
        vehicles=[];weapons=[];chains=[];entities=[]
        for index,(name,parent) in enumerate(REVIEWED.items()):
            mount=f'{index+1:016X}'
            vehicles.append(dict(name=name, vehicleClass='FRV',callInStratagem=dict(known=True)))
            weapons.append(dict(vehicle=name))
            chains.append(f'["mountChain"]={{["mountPath"]="0x{mount}",["slot"]=0,["vehicle"]="{name}",["vehicleResource"]="0x{parent}"}}')
            entities.append(f'["{parent}"]={{["kill"]=false,["name"]="vehicle_{index}",["faction"]="helldivers",["id"]="entity/v1/helldivers/test_{index}"}}')
        (sdk/'VehicleAuthoringCapabilities.json').write_text(json.dumps(dict(vehicles=vehicles)))
        (sdk/'VehicleWeaponCapabilities.json').write_text(json.dumps(dict(vehicles=weapons)))
        (domain/'vehicle_weapon_authoring.lua').write_text('return {'+','.join(chains)+'}')
        (domain/'event_entities.lua').write_text('return {["types"]={'+','.join(entities)+'}}')
        return sdk

    def test_exact_nine_known_call_in_parents_only(self):
        with tempfile.TemporaryDirectory() as directory:
            data=build_sources(self.fixture(directory))
            self.assertEqual(data['source_count'],9)
            self.assertEqual(set(data['sources']),set(REVIEWED.values()))
            self.assertTrue(all(row['known_player_call_in'] for row in data['sources'].values()))
            self.assertTrue(data['rule_does_not_claim_native_collision_mechanism'])
            self.assertFalse(data['backfill_missing_source_identity'])

    def test_missing_player_call_in_is_not_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk=self.fixture(directory);p=sdk/'VehicleAuthoringCapabilities.json'
            data=json.loads(p.read_text());data['vehicles'][0]['callInStratagem']['known']=False
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(AssertionError,'call-in provenance'):
                build_sources(sdk)

    def test_enemy_or_unknown_faction_is_not_admitted(self):
        for faction in ('automatons','unknown'):
            with tempfile.TemporaryDirectory() as directory:
                sdk=self.fixture(directory);p=sdk.parent/'domains/event_entities.lua'
                p.write_text(p.read_text().replace('["faction"]="helldivers"',f'["faction"]="{faction}"',1))
                with self.assertRaisesRegex(AssertionError,'friendly vehicle'):
                    build_sources(sdk)

    def test_different_mount_parent_is_not_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk=self.fixture(directory);p=sdk.parent/'domains/vehicle_weapon_authoring.lua'
            p.write_text(p.read_text().replace('0x9B2140378640432E','0x1111111111111111',1))
            with self.assertRaisesRegex(AssertionError,'vehicle parent differs'):
                build_sources(sdk)

    def test_name_or_semantic_suffix_does_not_establish_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk=self.fixture(directory);p=sdk.parent/'domains/vehicle_weapon_authoring.lua'
            p.write_text(p.read_text().replace('["vehicleResource"]','["semanticId"]',1))
            with self.assertRaisesRegex(AssertionError,'vehicle parent differs'):
                build_sources(sdk)

    def test_frozen_real_evidence_table_rebuilds_and_excludes_mounts(self):
        sdk=Path(os.environ.get('HD2_RUNTIME_SDK',str(Path(os.environ['LOCALAPPDATA'])/'Temp/hd2-integration-research/HD2Runtime/SkyeShade-HD2Runtime-dcd996d/sdk')))
        labels=json.loads((ROOT/'docs/resource-hash-aliases.json').read_text(encoding='utf8'))['aliases']
        data=build_sources(sdk,labels=labels)
        self.assertEqual(data,json.loads((ROOT/'docs/vehicle-body-kill-sources.json').read_text(encoding='utf8')))
        sources=set(data['sources'])
        for row in data['sources'].values():
            self.assertFalse(sources.intersection(row['mounted_weapon_hashes']))
        self.assertNotIn('1FA1F596769225C2',sources)
        self.assertNotIn('439F9E65C18567DA',sources)
        self.assertNotIn('E9CD1D0D118886AF',sources)
        self.assertNotIn('423FF97D57AB04F5',sources)


if __name__=='__main__':
    unittest.main()
