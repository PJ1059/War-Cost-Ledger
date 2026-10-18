"""Read the proven 1495360 entry's 14953B4 direct fallthrough only."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_screen_enter_successor_private',
                                             ROOT / 'tools/career-screen-enter-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_screen_enter_successor_v1'
worker.session.reader.TARGET_RVA = 0x14953B4
worker.session.reader.SOURCE_REFERENCE = (
    'Actual screen-enter SHA9df4899c1388b298ea711835d7b6bb152d278edcc3744b54d3b34134fe9b21f2; '
    '84B root direct fallthrough14953B4; keep fresh1438264 E8->1495360; '
    'no call/Stats getter claim')

if __name__ == '__main__':
    worker.main()
