"""Read the actual Career stats-fill entry's direct 18E6446 common continuation."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_stat_common_private',
                                             ROOT / 'tools/career-stat-fill-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_stat_common_v1'
worker.session.reader.TARGET_RVA = 0x18E6446
worker.session.reader.SOURCE_REFERENCE = (
    'Actual StatsFill successor SHA238f2d4a4307188e16625b1c255b93fc9052c5b2aea0eb6089e51352ffa4f5b1; '
    'root JNE18E63D4->18E6446 and successor directfallthrough18E6446; only common stat fields, no geometry helpers; '
    'keep fresh18E5ACA E8->18E62B0; fieldnames/ready unproven, no getter call')

if __name__ == '__main__':
    worker.main()
