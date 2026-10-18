"""Follow the proven33B entry's immediate declared successor, not a larger cap."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('source_constructor_body_session',
                                           ROOT/'tools/hit-source-constructor-capture.py')
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
worker=probe.worker
worker.REVISION=worker.session.REVISION=worker.session.reader.REVISION='hit_source_constructor_successor_v2'
worker.session.reader.TARGET_RVA=0x12A1231
worker.session.reader.SOURCE_REFERENCE=(
    'Actual source constructor entry SHAdce55e023592196b55aa6f76dbbf943c559fb1fa4c5e591c53859bf5b182705a; '
    '12A1231 immediate fallthrough; keep13AD2E9 ->12A1210 actual caller PIN')

if __name__=='__main__':
    worker.main()
