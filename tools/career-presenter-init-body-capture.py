"""Read the actual init entry's directly observed 14C0597 fallthrough."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_presenter_successor_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_presenter_init_successor_v1'
worker.session.reader.TARGET_RVA = 0x14C0597
worker.session.reader.SOURCE_REFERENCE = (
    'Actual init entry SHA138050dee2ef22f91e800ae743b1e1eda5f9d62100610fa16ae8630e0c6550a0; '
    '71B root direct fallthrough14C0597; actualrecord71744 [14C0597,14C05DA)/2521D20; '
    'keep fresh14C03B0 E9->14C0550, no call/Stats getter claim')

if __name__ == '__main__':
    worker.main()
