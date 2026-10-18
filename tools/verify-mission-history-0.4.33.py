"""Focused offline acceptance for Career match history; no Game access."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
from test import ROOT, run_lua, main as verify_package

RUNTIME = Path('external/HD2Runtime')
HOST = ROOT / 'dist/mod-research/task-layout/hud-plus-installed-0.2.1/56E46A6DC1DF0A13.lua'
OUT = ROOT / 'dist/mission-history-0.4.33'


def main():
    OUT.mkdir(exist_ok=True)
    cases = [
        ('test_career_panel_feed.lua', 'src/career-panel-feed.lua', 'src/career-panel-model.lua', 'src/battle-hud.lua'),
        ('test_addon_mission_history.lua', 'dist/addon.lua', RUNTIME, 'tests/test_integration.lua'),
        ('test_addon_career_awards.lua', 'dist/addon.lua', RUNTIME, 'tests/test_integration.lua'),
        ('test_native_career_hud.lua', 'src/native-hud-addon.lua', 'src/native-career-hud.lua', HOST, 'dist/native-game-art.lua',
         'tests/test_native_career_panel_reader.lua', 'src/native-career-panel-reader.lua', RUNTIME,
         'tests/fixtures/career-parent-headers.lua', 'src/career-panel-model.lua', 'src/battle-hud.lua', 'tests/test_native_hud_addon.lua'),
        ('test_hud_layout.lua', 'src/hud-layout.lua'),
        ('test_game_hud.lua', 'src/game-hud.lua', 'src/battle-hud.lua', 'src/award-notifications.lua', 'dist/game-icons.lua'),
        ('test_native_hud_feed.lua', 'src/native-hud-feed.lua', 'src/game-hud.lua', 'src/battle-hud.lua', 'src/award-notifications.lua', 'dist/game-icons.lua'),
        ('test_native_hud_addon.lua', 'src/native-hud-addon.lua', HOST, 'dist/native-game-art.lua'),
    ]
    output, results = io.StringIO(), []
    name = 'package/source/price validation'
    try:
        with redirect_stdout(output):
            verify_package(package_only=True)
            results.append({'test': name, 'status': 'passed'})
            for name, *args in cases:
                run_lua(ROOT / 'tests' / name, *(p if isinstance(p, Path) else ROOT / p for p in args))
                results.append({'test': name, 'status': 'passed'})
    except Exception as exc:
        results.append({'test': name, 'status': 'failed', 'error': str(exc)})
        raise
    finally:
        (OUT / 'offline-validation.log').write_text(output.getvalue(), encoding='utf8')
        package = ROOT / 'dist/HD2-War-Cost-Ledger-0.4.33.zip'
        report = {'tests': results,
                  'status': 'passed' if len(results) == len(cases) + 1 and all(t['status'] == 'passed' for t in results) else 'failed',
                  'game_pixels_verified': False, 'deployed': False,
                  'package_sha256': hashlib.sha256(package.read_bytes()).hexdigest() if package.exists() else None}
        (OUT / 'offline-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        print(output.getvalue())
        print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
