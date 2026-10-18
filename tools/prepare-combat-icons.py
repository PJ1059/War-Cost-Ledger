"""Render editable elbow/crush vectors; keep previous artwork unchanged.

The PNGs are checked-in build inputs, so regular MOD builds need no renderer.
Set LEDGER_SHARP_MODULE / LEDGER_NODE when using an existing bundled sharp.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artwork/combat-icons/v2'
ITEMS = [('R05', 'melee', '近战杀敌', 'R05-melee-elbow', .42),
         ('R12', 'crush', '碾压', 'R12-crush', .68)]


def build():
    render = "const sharp=require(process.argv[1]);sharp(process.argv[2],{density:384}).resize(512,512,{fit:'contain',background:{r:0,g:0,b:0,alpha:0}}).png({compressionLevel:9,palette:false}).toFile(process.argv[3]).catch(e=>{console.error(e.message);process.exit(1)})"
    items = []
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    for identity, key, name, stem, width in ITEMS:
        vector = OUT / (stem + '.svg')
        raster = vector.with_suffix('.png')
        subprocess.run([os.environ.get('LEDGER_NODE', 'node'), '-e', render,
                        os.environ.get('LEDGER_SHARP_MODULE', 'sharp'), str(vector), str(raster)], check=True)
        image = Image.open(raster).convert('RGBA')
        bbox = image.getchannel('A').point(lambda value: 255 if value >= 24 else 0).getbbox()
        items.append(dict(id=identity, key=key, name=name, kind='ribbon', accent='#c7b980',
                          file=raster.name, source_svg=vector.name,
                          source_svg_sha256=sha(vector.read_bytes()), sha256=sha(raster.read_bytes()),
                          width=512, height=512, alpha_bbox=list(bbox),
                          body_ratio=(bbox[2]-bbox[0])/(bbox[3]-bbox[1]),
                          symbol_width=width, display_scale=1, artwork_form='repo_native_vector_ribbon',
                          review_fingerprint=sha(vector.read_bytes()+raster.read_bytes()),
                          design_basis='bent armored elbow reference' if identity=='R05' else 'vehicle track over enemy silhouette'))
    catalog = dict(schema=1, version='0.4.48', revision='combat-v2',
                   method='editable native-style flat vectors', overrides=['R05'], additions=['R12'], items=items)
    (OUT/'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print('Rendered elbow replacement and crush ribbon; prior artwork untouched.')


if __name__=='__main__':
    build()
