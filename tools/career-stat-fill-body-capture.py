"""Read the actual Career stats-fill entry's direct 18E63E9 continuation."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_stat_fill_successor_private',
                                             ROOT / 'tools/career-stat-fill-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_stat_fill_successor_v1'
worker.session.reader.TARGET_RVA = 0x18E63E9
worker.session.reader.SOURCE_REFERENCE = (
    'Actual StatsFill SHAe9ec6b03305d1a69e50d7a9b5c735eff511404d61ccb1a3c9e0d16437da97880; '
    '313B root direct fallthrough18E63E9 after setting RCX=panel+9B8,EDX=1,R8D=panel+2FE08; '
    'keep fresh18E5ACA E8->18E62B0; fieldnames/ready unproven, no getter call')

if __name__ == '__main__':
    worker.main()
