"""Follow the actual string-storage helper's immediate declared successor."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('format_storage_body_session',
                                           ROOT/'tools/career-format-helper-capture.py')
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker=probe.worker
worker.REVISION=worker.session.REVISION=worker.session.reader.REVISION='career_format_storage_successor_v2'
worker.session.reader.TARGET_RVA=0x143A241
worker.session.reader.SOURCE_REFERENCE=(
    'Actual storage helper SHA0401d315c35f10597a8b707c9fcc3ceab89b455b83f810eab01863151c95b348; '
    '143A241 immediate fallthrough; keep143C960 ->143A1B0 actual caller PIN')

if __name__=='__main__':
    worker.main()
