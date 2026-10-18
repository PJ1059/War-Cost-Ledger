"""Read the SDK's pinned descriptor-return fragment, never call the lookup.

The previous actual body ends FD9DD4; FD9DDB is the SDK's exact descriptor
address calculation. The common reader keeps declared ranges and total caps.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hit_entity_map_tail_private',
                                          ROOT/'tools/hit-entity-descriptor-code-capture.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
session=profile.session
session.REVISION=session.reader.REVISION='hit_entity_map_tail_declared_code_v1'
session.TARGET_RVA=session.reader.TARGET_RVA=0xFD9DDB
session.TARGET_PIN=session.reader.TARGET_PIN='488d80e3651e00'
session.reader.SOURCE_REFERENCE=(
    'HD2Runtime dcd996d descriptor-return PIN; '
    'actual body SHA32fe056de921dabffb6cdcce374752562bae8b250112c31de9d75996129d5640 ends FD9DD4')

if __name__=='__main__':
    session.main()
