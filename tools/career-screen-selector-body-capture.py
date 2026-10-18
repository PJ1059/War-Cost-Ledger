"""Read the screen-type switch entry's 14954DC direct fallthrough only."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_screen_selector_successor_private',
                                             ROOT / 'tools/career-screen-selector-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_screen_selector_successor_v1'
worker.session.reader.TARGET_RVA = 0x14954DC
worker.session.reader.SOURCE_REFERENCE = (
    'Actual screen-selector SHA90df3e6f1837e7912b5166877189cc2909713bbe09973a4f44e08d2934811e74; '
    '92B root screen2 -> selector1, limit34, direct fallthrough14954DC; keep fresh149544E E8->1495480; '
    'no call/Stats getter claim')

if __name__ == '__main__':
    worker.main()
