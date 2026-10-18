"""Prepare/inspect a diagnostic package in the test process; never open Game."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from build import lua_table
from test import run_lua
from hit_bridge_owned import OwnedBridge


def run(profile_path, output):
    profile = json.loads(profile_path.read_text(encoding='utf8'))
    assert profile['demolition_diagnostic']['capacity'] == 32
    output.mkdir(parents=True, exist_ok=True)
    with OwnedBridge(capacity=8) as owner:
        image = owner._allocate(0x4744000, executable=False)
        fixture = output / 'package-fixture.lua'
        fixture.write_text('return ' + lua_table({'image': {'base': image, 'size': 0x4744000},
                                                   'profile': profile}), encoding='utf8')
        run_lua(ROOT / 'tests/test_native_demolition_package.lua', ROOT,
                Path('external/HD2Runtime'), fixture)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.profile.resolve(), args.output.resolve())
