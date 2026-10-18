"""Use the pinned official SDK to check or trigger the installed capture package."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'arm'])
    parser.add_argument('--label', default='objective-host-baseline')
    parser.add_argument('--runtime-source', type=Path, default=Path.home() /
                        'AppData/Local/Temp/hd2-integration-research/HD2Runtime/SkyeShade-HD2Runtime-dcd996d')
    args = parser.parse_args()
    sdk = args.runtime_source.resolve() / 'sdk/hd2.py'
    if not sdk.is_file():
        parser.error('Pinned SDK is missing. Restore the Runtime research source before capture.')
    command = [sys.executable, '-X', 'utf8', '-B', str(sdk), 'snapshot', args.action]
    if args.action == 'arm':
        command += ['--label', args.label]
    return subprocess.run(command, cwd=sdk.parent).returncode


if __name__ == '__main__':
    raise SystemExit(main())
