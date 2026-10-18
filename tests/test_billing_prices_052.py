"""Confirmed-workbook costs: no game reads and no invented replacement price."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build import workbook_rows,cents
spec=importlib.util.spec_from_file_location('ledger_magazine_prices_052',ROOT/'tools/magazine-prices.py')
magazine=importlib.util.module_from_spec(spec);spec.loader.exec_module(magazine)

class BillingPriceFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=workbook_rows()
        cls.catalog=json.loads((ROOT/'docs/integration-catalogs.json').read_text(encoding='utf8'))
        cls.ammo={p['name_en']:p for p in cls.catalog['ammo']}
        cls.calls={p['name_en']:p for p in cls.catalog['calls']}
    def test_price_regeneration_keeps_reviewed_enemy_and_vehicle_labels(self):
        loader=importlib.util.spec_from_file_location('ledger_catalog_regeneration_052',ROOT/'tools/integration-catalogs.py')
        generator=importlib.util.module_from_spec(loader);loader.loader.exec_module(generator)
        rebuilt=generator.catalogs()
        self.assertEqual(len(rebuilt['entities']),134)
        self.assertEqual(rebuilt['entities'],self.catalog['entities'])
        self.assertEqual(rebuilt['stat_sources'],self.catalog['stat_sources'])
        for identity in ('16474112801385B6','1FA1F596769225C2','439F9E65C18567DA'):
            self.assertEqual(rebuilt['stat_sources'][identity]['kind'],'stratagem')
    def test_programmable_backpack_rounds_are_charged_once(self):
        for name,price in [('AC-8 Autocannon',12000),('GR-8 Recoilless Rifle',350000),('RL-77 Airburst Rocket Launcher',650000)]:
            item=self.ammo[name]
            self.assertEqual(item['unit_cents'],price)
            self.assertEqual(item['projectiles_per_unit'],1)
            self.assertEqual(item['pricing_policy'],'standard_parent_round')
            self.assertTrue(item['backpack_ammo'])
            self.assertEqual(len(item['source_types']),1)
    def test_replenishable_backpack_calls_do_not_precharge_ammunition(self):
        for name,item in self.ammo.items():
            if not item.get('backpack_ammo') or name not in self.calls:continue
            call=self.calls[name]
            self.assertEqual(call['prepaid_ammo_cents'],0,name)
            self.assertEqual(call['total_cents'],call['transport_cents']+call['equipment_cents'],name)
    def test_heat_replacements_use_column_h_and_independent_ids(self):
        prices=magazine.heatsink_prices(self.rows[2],cents)
        self.assertEqual(len(prices),8)
        self.assertEqual(sum(len(p['source_types'])for p in prices),10)
        self.assertEqual(len({p['id']for p in prices}),8)
        normal_ids={p['id']for p in self.catalog['ammo']}
        for price in prices:
            row=self.rows[2][price['parent_price_id']]
            self.assertNotIn(price['id'],normal_ids)
            self.assertEqual(price['unit_cents'],cents(row['H']))
            self.assertEqual(price['unit_cents'],30000 if price['name_en']=='LAS-98 Laser Cannon'else 7500)
            self.assertEqual(price['inventory_mode'],'heatsink')
            self.assertEqual(price['billing_kind'],'heatsink')
    def test_cremator_display_fuel_price_uses_paired_deposit(self):
        price=magazine.backpack_fuel_prices(self.rows[2],cents)[0]
        self.assertEqual(price['id'],'EQ-113')
        self.assertEqual(price['unit_cents'],30)
        self.assertEqual(price['inventory_mode'],'fuel')
        self.assertEqual(price['inventory_storage'],'paired_deposit')
        self.assertEqual(price['source_types'],['0736BEE2D6328726','78A8185F63A70795'])
    def test_laser_firing_preserves_price_and_uses_maintenance_name(self):
        for name,item in self.ammo.items():
            if not name.startswith('LAS-'):continue
            row=self.rows[2][item['id']]
            self.assertEqual(item['unit_cents'],cents(row['F']))
            self.assertEqual(item['billing_kind'],'maintenance')
            self.assertEqual(item['billing_label'],'武器维护折旧费')

if __name__=='__main__':unittest.main()
