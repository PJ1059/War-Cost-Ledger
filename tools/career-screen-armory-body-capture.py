"""Read only screen2 dispatch's directly observed 14381F7 fallthrough."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_screen_armory_successor_private',
                                             ROOT / 'tools/career-screen-armory-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_screen_armory_successor_v1'
worker.session.reader.TARGET_RVA = 0x14381F7
worker.session.reader.SOURCE_REFERENCE = (
    'Actual screen2 dispatch SHA868d16b58632f45583db4131fdc51fe18a5c176f67380c74009c794604a10924; '
    '71B root direct fallthrough14381F7 when screen2 absent; '
    'keep fresh14B5178 E9->14381B0, no call/Stats getter claim')

if __name__ == '__main__':
    worker.main()
