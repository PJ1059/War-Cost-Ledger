"""Render the 0.4.47 native-vector achievement additions, without touching v18.

The five SVGs are editable source; PNGs are deterministic build inputs. Rendering
requires an existing Node sharp package. Set LEDGER_SHARP_MODULE to its absolute
module entry if sharp is outside node's normal resolution paths. No dependency
is downloaded or installed by this helper.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artwork/achievement-icons/v1'
SKULL=ROOT/'artwork/icon-drafts/v17/references/native-round-eye-skull/HD2-native-round-eye-skull.svg'
WHITE='#fff9ed'
GOLD='#c7b980'
ITEMS=[('R11','killstreak','连杀','ribbon'),('M07','double_giant','一炮双响','medal'),
       ('M08','democracy_star','民主之星','medal'),
       ('M09','super_democracy_star','超级民主之星','medal'),
       ('M10','supreme_democracy_star','超级无上民主之星','medal'),
       ('M11','level_not_problem','等级不是问题','medal')]

def sha(raw):return hashlib.sha256(raw).hexdigest()
def star(cx,cy,r=10):
    points=[]
    for n in range(10):
        radius=r if n%2==0 else r*.43
        angle=-math.pi/2+n*math.pi/5
        points.append(f'{cx+math.cos(angle)*radius:.4f},{cy+math.sin(angle)*radius:.4f}')
    return '<polygon points="'+' '.join(points)+'" fill="'+WHITE+'"/>'

def svg(identity,path):
    def skull(x,y,size):
        return f'<g transform="translate({x} {y}) scale({size/29.7083:.8f})"><path fill="{WHITE}" fill-rule="nonzero" d="{path}"/></g>'
    if identity=='R11':
        body=skull(8,23,29)+skull(49,23,29)+skull(89.75,23,29)
        body+='<path d="M38 37H46M79 37H87" fill="none" stroke="'+GOLD+'" stroke-width="3"/>'
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 80">'+body+'</svg>\n'
    body='<path d="M29 8H50L59 38H40ZM78 8H99L88 38H69Z" fill="none" stroke="'+GOLD+'" stroke-width="3"/>'
    body+='<path d="M64 27L99 41V82L64 118 29 82V41Z" fill="none" stroke="'+GOLD+'" stroke-width="3"/>'
    body+='<path d="M64 34L92 45V79L64 108 36 79V45Z" fill="none" stroke="'+GOLD+'" stroke-width="1.4"/>'
    if identity=='M07':
        body+=skull(36,53,28)+skull(65,53,28)
        body+='<path d="M52 94H76" stroke="'+GOLD+'" stroke-width="3"/>'
    elif identity=='M11':
        body+='<path d="M75 48L87 55V76L71 94 55 76V55Z" fill="none" stroke="'+WHITE+'" stroke-width="3"/>'
        body+='<path d="M39 58H59L67 64 59 70H39Z" fill="'+WHITE+'"/>'
        body+='<path d="M72 55V65M80 55V65M43 81L53 74M40 75L50 71" stroke="'+GOLD+'" stroke-width="3"/>'
    else:
        n={'M08':1,'M09':2,'M10':3}[identity]
        xs={1:[64],2:[51,77],3:[43,64,85]}[n]
        body+=''.join(star(x,48,8 if n==3 else 9) for x in xs)
        body+=skull(45,64,40)
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'+body+'</svg>\n'

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    raw=SKULL.read_bytes()
    native=ET.fromstring(raw)
    path=native.find('{http://www.w3.org/2000/svg}path').attrib['d']
    node=os.environ.get('LEDGER_NODE','node')
    sharp=os.environ.get('LEDGER_SHARP_MODULE','sharp')
    renderer="const sharp=require(process.argv[1]);sharp(process.argv[2],{density:384}).resize(512,512,{fit:'contain',background:{r:0,g:0,b:0,alpha:0}}).png({compressionLevel:9,palette:false}).toFile(process.argv[3]).catch(e=>{console.error(e.message);process.exit(1)})"
    items=[]
    for identity,key,name,kind in ITEMS:
        vector=OUT/(identity+'-'+key+'.svg')
        vector.write_text(svg(identity,path),encoding='utf8',newline='\n')
        raster=vector.with_suffix('.png')
        subprocess.run([node,'-e',renderer,sharp,str(vector),str(raster)],check=True)
        image=Image.open(raster).convert('RGBA')
        bbox=image.getchannel('A').point(lambda v:255 if v>=24 else 0).getbbox()
        fingerprint=sha(json.dumps({'png':sha(raster.read_bytes()),'svg':sha(vector.read_bytes()),'bbox':bbox},sort_keys=True).encode())
        items.append({'id':identity,'key':key,'name':name,'kind':kind,'accent':GOLD,
            'file':raster.name,'source_svg':vector.name,'source_svg_sha256':sha(vector.read_bytes()),
            'sha256':sha(raster.read_bytes()),'width':512,'height':512,'alpha_bbox':list(bbox),
            'body_ratio':(bbox[2]-bbox[0])/(bbox[3]-bbox[1]),'symbol_width':.70 if kind=='ribbon' else .34,
            'display_scale':1,'artwork_form':'repo_native_vector_'+kind,'review_fingerprint':fingerprint,
            'native_skull_source':SKULL.relative_to(ROOT).as_posix(),'native_skull_sha256':sha(raw)})
    catalog={'schema':1,'revision':'achievement-v1','version':'0.4.47',
        'method':'editable repo-native vector composition; native skull path retained exactly',
        'source_artwork_unchanged':True,'items':items}
    (OUT/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Rendered achievement SVG/PNG assets; original v18 files untouched.')

if __name__=='__main__':build()
