"""Run the actual built addon end-to-end in this process, never the game.

The seven sites are private fixture pages. Native publishers are invoked
directly; no patched callsite or original game procedure is ever executed.
"""
import argparse
import contextlib
import ctypes
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from build import lua_table, VERSION
from test import run_lua
from hit_bridge_owned import OwnedBridge

SDK = Path('external/HD2Runtime')
IMAGE_BYTES = 0x4744000


def run(addon, archive, runtime, output):
    output.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as z:
        assert z.testzip() is None
        assert z.read('Source/addon.lua') == addon.read_bytes(), 'built addon and ZIP source differ; rebuild first'
        profile_name = next(name for name in ['docs/native-hit-observer-package-v6.json','docs/native-hit-observer-package-v5.json','docs/native-hit-observer-package-v4.json', 'docs/native-hit-observer-package-v3.json',
            'docs/native-hit-observer-package-v2.json'] if name in z.namelist())
        profile = json.loads(z.read(profile_name))
        addon_version=json.loads(z.read('manifest.json'))['Name'].rsplit(' - ',1)[1]
        assert len(profile['entries']) == 19 and len(profile['sites']) == 7
    captured = io.StringIO()
    with OwnedBridge(capacity=8) as owner:
        image = owner._allocate(IMAGE_BYTES, executable=False)
        dos = bytearray(64); dos[:2] = b'MZ'; struct.pack_into('<I', dos, 60, 0x80)
        pe = bytearray(88); pe[:4] = b'PE\0\0'; struct.pack_into('<I', pe, 80, IMAGE_BYTES)
        ctypes.memmove(image, bytes(dos), len(dos)); ctypes.memmove(image + 0x80, bytes(pe), len(pe))
        pages = set()
        for site in profile['sites']:
            at, pin = image + site['rva'], bytes.fromhex(site['pin_hex'])
            ctypes.memmove(at, pin, len(pin)); pages.add(at & ~4095)
        assert len(pages) == 3
        old = ctypes.c_uint32()
        for page in pages:
            assert owner.kernel.VirtualProtect(page, 4096, 0x20, ctypes.byref(old))
        fixture = output / 'owned-built-addon-fixture.lua'
        fixture.write_text('return ' + lua_table({'image': {'base': image, 'size': IMAGE_BYTES},
            'sites': profile['sites'], 'readable_pages': [image] + sorted(pages),
            'addon_version':addon_version}), encoding='utf8')
        with contextlib.redirect_stdout(captured):
            dll = run_lua(ROOT / 'tests/test_native_hit_addon_owned.lua', addon, runtime, fixture)
        log = captured.getvalue()
        print('\n'.join(line for line in log.splitlines() if not line.startswith('OWNED_EVIDENCE_JSON ')))
        (output / 'lua-output.txt').write_text(log, encoding='utf8')
        line = next((line for line in log.splitlines() if line.startswith('OWNED_EVIDENCE_JSON ')), None)
        assert line, 'owned Lua evidence missing'
        evidence = json.loads(line[len('OWNED_EVIDENCE_JSON '):])
        assert evidence['passed'] and evidence['installed_sites'] == 7
        for site in profile['sites']:
            expected = bytes.fromhex(site['pin_hex'])
            actual = ctypes.string_at(image + site['rva'], len(expected))
            assert actual != expected and actual[0] == 0xE8
            assert len(expected) != 6 or actual[-1] == 0x90
    sources = ['tools/native/test_hit_addon_owned.py', 'tests/test_native_hit_addon_owned.lua']
    report = {'status': 'PASS', 'origin': 'actual_built_addon_own_process_private_image',
        'lua51_dll': dll, 'addon': str(addon), 'archive': str(archive),
        'addon_sha256': hashlib.sha256(addon.read_bytes()).hexdigest(),
        'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'fixture_boundary': {'image_bytes': IMAGE_BYTES, 'patch_pages_rx': 3,
            'event_world': 'current host process, simulated Ship/Mission/player/stat boundary',
            'read': 'declared owned PE header and three site pages only',
            'kernel': 'real SDK windows_ffi; only GetModuleHandleA(game.dll) substitutes owned image',
            'publisher_and_drain': 'actual native package entry pointers',
            'original_procedures_or_patched_sites_invoked': False,
            'game_hud_pixels_or_fps_verified': False},
        'game_reads': 0, 'game_writes': 0, 'game_installation': False,
        'evidence': evidence,
        'files': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources}}
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': 'PASS', 'checks': evidence['checks'], 'report': str(output / 'verification.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon', type=Path, default=ROOT / 'dist/addon.lua')
    parser.add_argument('--archive', type=Path, default=ROOT / ('dist/HD2-War-Cost-Ledger-'+VERSION+'.zip'))
    parser.add_argument('--runtime', type=Path, default=SDK)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/hit-built-addon-owned-20261012')
    args = parser.parse_args()
    run(args.addon.resolve(), args.archive.resolve(), args.runtime.resolve(), args.output.resolve())
