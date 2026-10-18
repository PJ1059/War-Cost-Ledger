"""Complete relocatable observer package export; no native/process execution."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

from hit_callable_profile import manifest as callable_manifest, RelocCode
from hit_entity_resolver_owned import lookup_code, allow_code, qualify_code, catalog, SDK, ROOT

MANAGER_GLOBAL_RVA = 0x346BF98


def qualifier(enemy_count,source_count):
    c=RelocCode()
    c.emit('56 57 48 83 ec 28 48 89 cf 48 89 d6')
    c.emit('81 66 58 bf fe ff ff c7 46 54 00 00 00 00')
    for name,offset,key,count,bit in [('target',44,'enemy_types',enemy_count,64),
                                      ('source',48,'source_types',source_count,256)]:
        c.emit('48 89 f9 8b 56 '+bytes([offset]).hex());c.call('resolve');c.emit('48 85 c0')
        c.branch('0f 84',name+'_ready')
        c.emit('48 89 c2');c.address('48 b9',key);c.emit('41 b8 '+struct.pack('<I',count).hex(' '))
        c.call('allow');c.emit('85 c0');c.branch('0f 84',name+'_ready')
        c.emit('81 4e 58 '+struct.pack('<I',bit).hex(' '))
        if name=='target':c.emit('c7 46 54 01 00 00 00')
        c.label(name+'_ready')
    c.emit('8b 46 58 48 83 c4 28 5f 5e c3');code=c.finish()
    return {'name':'qualifier','entry_offset':0,'code_hex':code.hex(),'executable_length':len(code),
        'relocations':c.relocations,'unwind_hex':'010603000642027001600000'}


def manager_evidence():
    domain=SDK/'domains/event_natives.lua';source=SDK/'runtime/event_world.lua'
    text=domain.read_text(encoding='utf-8')
    # Match the specific wielder block, not exe-side engine.entities.
    at=text.index('["wielder"]');sub=text[at:]
    expected={'entities':MANAGER_GLOBAL_RVA,'entityMap':0xF1AEB0,'descriptors':0xF32F18,
              'descriptorStride':24,'descriptorEntity':8}
    for key,value in expected.items():
        match=re.search(r'\["'+key+r'"\]=([0-9]+)',sub)
        if not match or int(match.group(1))!=value:raise ValueError('pinned wielder entity layout changed: '+key)
    live=source.read_text(encoding='utf-8')
    for expression in ['world.view.pointer(world.game+WI.entities)','manager+WI.entityMap',
                       'manager+WI.descriptors+index*WI.descriptorStride']:
        if expression not in live:raise ValueError('runtime world entity path changed')
    path=ROOT/'dist/hit-entity-map-analysis-20261012/function.bin';raw=path.read_bytes()
    actual_sha='27627b0418666a4ce50917587d9dd779c3736a8af2272a3a3c955f94cb3701ed'
    if len(raw)!=178 or hashlib.sha256(raw).hexdigest()!=actual_sha:raise ValueError('actual entity lookup material changed')
    pin=raw[0x10:0x17]
    if pin.hex()!='4c8b1541224902' or 0xFD9D50+7+struct.unpack('<i',pin[3:])[0]!=MANAGER_GLOBAL_RVA:
        raise ValueError('actual manager global RIP proof changed')
    return {'manager_global_rva':MANAGER_GLOBAL_RVA,'module':'game.dll','sdk_wielder':expected,
        'domain_path':'domains/event_natives.lua','domain_sha256':hashlib.sha256(domain.read_bytes()).hexdigest(),
        'runtime_path':'runtime/event_world.lua','runtime_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'runtime_lines':'545-557 entity_descriptor and entity_type',
        'actual_lookup_path':str(path.relative_to(ROOT)).replace('\\','/'),'actual_lookup_sha256':actual_sha,
        'actual_global_load_rva':0xFD9D50,'actual_global_load_pin':pin.hex(),'actual_global_rip_target':MANAGER_GLOBAL_RVA}


def package():
    base=callable_manifest();enemies,sources,catalog_evidence=catalog();m=dict(base)
    m['revision']='complete_hit_observer_package_v2'
    m['entries']=list(base['entries'])
    for name,raw in [('resolve',lookup_code()),('allow',allow_code())]:
        m['entries'].append({'name':name,'entry_offset':0,'code_hex':raw.hex(),'executable_length':len(raw),
                             'relocations':[],'unwind_hex':'01000000'})
    m['entries'].append(qualifier(len(enemies),len(sources)))
    m['data_tables']={'enemy_types':[f'{v:016X}' for v in enemies],'source_types':[f'{v:016X}' for v in sources]}
    m['data_encoding']='sorted ascending u64 little endian; hex strings must not convert through double'
    m['entity_manager_global_rva']=MANAGER_GLOBAL_RVA
    m['entity_manager_evidence']=manager_evidence();m['catalog_evidence']=catalog_evidence
    m['qualifier_signature']='uint32_t(void* manager,void* record96)'
    m['resolve_signature']='uint64_t(void* manager,uint32_t entity)'
    m['allow_signature']='uint32_t(const uint64_t* sorted,uint64_t type,uint32_t count)'
    m['qualification_limits']={'hash_probes_per_entity':8,'max_map_capacity':0x100000,
        'max_descriptor_index':0x100000,'enemy_types':111,'source_types':91,'world_scan':False}
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    target=Path(p.parse_args().output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(package(),indent=2),encoding='utf-8');print(str(target.resolve()))
