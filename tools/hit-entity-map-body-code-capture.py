"""Read only the entity-map successor's declared range, pinned by SDK capacity.

Actual FD9D40..FD9D5A ends at a proven fallthrough. The SDK's FD9D68
capacity read pins the successor; no arbitrary bytes/gap scan or native call.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hit_entity_map_body_private',
                                          ROOT/'tools/hit-entity-descriptor-code-capture.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
session=profile.session
session.REVISION=session.reader.REVISION='hit_entity_map_body_declared_code_v1'
session.TARGET_RVA=session.reader.TARGET_RVA=0xFD9D68
session.TARGET_PIN=session.reader.TARGET_PIN='458b8ab8aef100'
session.reader.SOURCE_REFERENCE=(
    'HD2Runtime dcd996d exact entity map capacity PIN; '
    'actual FD9D40..FD9D5A SHA7e25fb8f557ea88ceb6bdfb85e9aad066b2985bb1368fb2c26726acf32361407 fallthrough')

if __name__=='__main__':
    session.main()
