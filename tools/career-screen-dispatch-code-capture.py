"""Read the proven screen-enter continuation after generic input cleanup."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_screen_dispatch_private',
                                             ROOT / 'tools/career-screen-enter-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_screen_dispatch_declared_v1'
worker.session.reader.TARGET_RVA = 0x1495423
worker.session.reader.SOURCE_REFERENCE = (
    'Actual screen-enter SHA9df4899c1388b298ea711835d7b6bb152d278edcc3744b54d3b34134fe9b21f2 '
    'JBE14953AA->1495423; successor SHAaa0c6cbcd0e5cc2ef624f4a0012a578d8754296d0da692ee86438e544685a3c9 '
    'direct fallthrough1495423; no input-helper/heap/native-call traversal; '
    'keep fresh1438264 E8->1495360')

if __name__ == '__main__':
    worker.main()
