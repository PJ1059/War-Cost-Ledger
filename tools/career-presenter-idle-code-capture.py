"""Read the proven current-presenter==0 branch; never initialise a presenter."""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('career_presenter_idle_private',
                                             ROOT / 'tools/career-presenter-init-code-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'career_presenter_idle_declared_v1'
worker.session.reader.TARGET_RVA = 0x14C0604
worker.session.reader.SOURCE_REFERENCE = (
    'Actual init body SHA604996278d7b8ff0da43df69d4d9887848352f11a34ab080e684ed61baeacc5d; '
    '14C05BB 7447 JE14C0604 when manager.currentID==0; '
    'keep fresh14C03B0 E9->14C0550; no native call, no Stats/provider claim')

if __name__ == '__main__':
    worker.main()
