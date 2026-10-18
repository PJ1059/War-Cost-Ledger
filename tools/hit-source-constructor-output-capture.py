"""Follow actual constructor branch1314 ->133E within declared1316..1357.

Keep the fresh original constructor caller. Do not enlarge general limits or
read game data. The predecessor packet records this exact sibling boundary.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('source_output_session',
                                             ROOT/'tools/hit-source-constructor-capture.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker = probe.worker
worker.REVISION = worker.session.REVISION = worker.session.reader.REVISION = 'hit_source_constructor_output_v3'
worker.session.reader.TARGET_RVA = 0x12A1316
worker.session.reader.SOURCE_REFERENCE = (
    'Actual262B constructor SHA8ddd54d79070adb3eaacdfe618fa69fe0ef3f54a787ea9799dcc8ae781b5a607; '
    '1314 je133E and fallthrough1316; declared[12A1316,12A1357); original13AD2E9 ->12A1210 PIN')

if __name__ == '__main__':
    worker.main()
