"""Focused package and neighbouring runtime checks for the stim integration."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import importlib.util
import json
import time

from test import run_lua
from build import ROOT, RESOURCE, resource_hash

RUNTIME = Path('external/HD2Runtime')

def main():
    started = time.perf_counter()
    target = ROOT / 'dist/HD2-War-Cost-Ledger-0.4.29.zip'
    previous = ROOT / 'dist/HD2-War-Cost-Ledger-0.4.28.zip'
    report = {'version': '0.4.29', 'standard_stim_unit_cents': 250000,
              'package_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'gameplay_stim_use_verified': False}
    with ZipFile(target) as new, ZipFile(previous) as old:
        assert new.testzip() is None
        new_names, old_names = set(new.namelist()), set(old.namelist())
        report['added'] = sorted(new_names - old_names)
        report['removed'] = sorted(old_names - new_names)
        report['changed'] = sorted(n for n in new_names & old_names if new.read(n) != old.read(n))
        assert report['added'] == ['Source/stim-billing.lua'] and not report['removed']
        assert new.read('Source/addon.lua') == (ROOT / 'dist/addon.lua').read_bytes()
        assert new.read('Source/stim-billing.lua') == (ROOT / 'src/stim-billing.lua').read_bytes()
        prices = json.loads(new.read('Source/confirmed-prices.json'))
        old_prices = json.loads(old.read('Source/confirmed-prices.json'))
        assert prices['stim']['id'] == 'EQ-360' and prices['stim']['unit_cents'] == 250000
        assert all(prices[k] == v for k, v in old_prices.items() if k != 'workbook_sha256')
        for n in ('Addon/9ba626afa44a3aa3.patch_0.gpu_resources',
                  'Addon/9ba626afa44a3aa3.patch_0.stream',
                  'Source/native-hit-copy-host.lua', 'Source/career-ship-sync.lua'):
            assert new.read(n) == old.read(n), n
        spec = importlib.util.spec_from_file_location('stims_archive_icons', ROOT / 'tools/prepare-game-icons.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        sdk = module._sdk_module('hd2_archive')
        resources = sdk.read_archive(new.read('Addon/9ba626afa44a3aa3.patch_0'),
                                     new.read('Addon/9ba626afa44a3aa3.patch_0.gpu_resources'))
        lua, gpu = resources[(sdk.LUA_TYPE, resource_hash(RESOURCE))]
        assert not gpu and lua[8:] == new.read('Source/addon.lua')
        report['actual_archive_source_matches_tested_addon'] = True
        report['files'] = len(new_names)
    run_lua(ROOT / 'tests/test_addon_consumables.lua', ROOT / 'dist/addon.lua',
            ROOT / 'tests/test_consumable_reader.lua', RUNTIME)
    run_lua(ROOT / 'tests/test_addon_career_ship.lua', ROOT / 'dist/addon.lua', RUNTIME,
            ROOT / 'tests/test_native_career_reader.lua', ROOT / 'src/native-career-reader.lua',
            ROOT / 'tests/fixtures/career-visible-rows.lua', ROOT / 'src/native-career-counters.lua')
    report['neighbour_checks'] = ['built_ammo_fuel_discard_billing', 'built_career_ship_sync']
    report['elapsed_seconds'] = time.perf_counter() - started
    report['status'] = 'passed'
    (ROOT / 'dist/stims-0.4.29-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
