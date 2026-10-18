"""Assemble a local, manually triggered capture package from pinned Runtime code.

This only creates research artifacts in dist/. It does not deploy or start the game.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import build as ledger_build

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path.home() / 'AppData/Local/Temp/hd2-integration-research/HD2Runtime/SkyeShade-HD2Runtime-dcd996d'
COMMIT = 'dcd996daca2573443956c07252c55c2d86dd0320'
ENTRY = 'mods/skyeshade/hd2runtime_snapshot_armed'
ENTRY_SHA = '5439fb6a4d8ea9e30a4ac53088c676245abe21ad058b6782d2be7a441ec45de3'
GUID = 'cddcc06b-1052-59c7-93c2-669aa1d20e7d'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-source', type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    upstream = args.runtime_source.resolve()
    version = (upstream / 'VERSION').read_text(encoding='utf-8').strip()
    source = (upstream / 'snapshot_capture/armed_addon.lua').read_bytes()
    if version != '0.30.3' or hashlib.sha256(source).hexdigest() != ENTRY_SHA:
        raise SystemExit('Pinned Runtime version or capture entrypoint changed; revalidate first.')
    config = json.loads((upstream / 'snapshot_capture/hd2runtime.json').read_text(encoding='utf-8'))
    config.update(name='HD2 Task Verification Capture', resource=ENTRY, guid=GUID)
    config['requires']['hd2runtime']['min_version'] = version
    description = '任务研究用手动快照入口。收到采集指令才保存本机内存；需要 HD2Runtime 0.30.3。'
    manifest = {'Version': 1, 'Guid': GUID, 'Name': 'HD2 Task Verification Capture - Local 0.1',
                'Description': description, 'Options': [{'Name': '手动快照采集',
                'Description': description, 'Include': ['capture']}]}
    ledger_build.RESOURCE = ENTRY
    archive = ledger_build.make_archive(source)
    report = {'upstream_commit': COMMIT, 'upstream_version': version,
              'entrypoint_sha256': ENTRY_SHA, 'entrypoint_unchanged': True,
              'assembly': 'local reproduction of the upstream armed entrypoint; not an official release',
              'runtime_bundled': False, 'automatic_capture': False,
              'deployed': False, 'game_launched': False, 'live_objective_verified': False}
    files = {'manifest.json': json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'),
             'hd2runtime.json': json.dumps(config, ensure_ascii=False, indent=2).encode('utf-8'),
             'capture/9ba626afa44a3aa3.patch_0': archive,
             'capture/9ba626afa44a3aa3.patch_0.stream': b'',
             'capture/9ba626afa44a3aa3.patch_0.gpu_resources': b'',
             'Source/armed_addon.lua': source,
             'README.md': (ROOT / 'docs/objective-verification.md').read_bytes(),
             'build-report.json': json.dumps(report, indent=2).encode('utf-8')}
    output = ROOT / 'dist/objective-verification'
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'HD2-Task-Verification-Capture-0.1.zip'
    with ZipFile(target, 'w', compression=ZIP_DEFLATED) as package:
        for name, data in files.items():
            package.writestr(name, data)
    with ZipFile(target) as package:
        assert package.testzip() is None
        stored = package.read('capture/9ba626afa44a3aa3.patch_0')
        assert stored[200:200 + len(source)] == source
        assert package.read('Source/armed_addon.lua') == source
    report.update(package=str(target), sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    (output / 'build-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(target)
    print('SHA256=' + report['sha256'])


if __name__ == '__main__':
    main()
