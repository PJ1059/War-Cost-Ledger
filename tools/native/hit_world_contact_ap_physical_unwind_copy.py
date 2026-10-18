"""Fixed six-region /28RF /22CHAININFO pure relocation. No native API.

Old720B and new532B actual packets plus the existing AP48B source are hard
SHA-checked. Copy732B of complete UW blocks, preserving slots/headers/GS4;
only embedded CHAININFO triples and the28 sorted RF records are relocated.
All DWORD addresses use the supplied original Game base. No registration,
allocation, RX execution or observer; the old19RF mapper stays unchanged.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[2]
OLD_PATH=Path(__file__).with_name('hit_world_contact_unwind_copy.py')
OLD_SHA='5cb4f519e79e3a39f5a8bd207c61dbe8942a22dd90fc7ba787e4863620210d43'
if hashlib.sha256(OLD_PATH.read_bytes()).hexdigest()!=OLD_SHA:
    raise ValueError('OLD_UW_MAPPER_CHANGED')
spec=importlib.util.spec_from_file_location('_six_region_old_UW_private',OLD_PATH)
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
spec=importlib.util.spec_from_file_location('_six_region_code_private',
    Path(__file__).with_name('hit_world_contact_ap_physical_code_copy.py'))
code_copy=importlib.util.module_from_spec(spec);spec.loader.exec_module(code_copy)
REGIONS={'frame':(0x4EE6C0,67,67),'world':(0xAB5000,9852,9828),
         'contact':(0x13AC1F0,17266,17266),'ap':(0x129C9F0,843,843),
         'dispatcher':(0x129DC30,244,216),'physical':(0x13B0BD0,1552,1552)}
UW_BLOCKS={'frame':(0x2404FAC,12,0,0),'world':(0x24A6DE8,224,12,12),
           'contact':(0x25114C0,256,236,236),'ap':(0x24FC2E0,48,492,492),
           'dispatcher':(0x24FC4AC,12,540,540),'physical':(0x2511668,180,552,552)}
UW_BYTES,RF_COUNT,RF_BYTES,CHAIN_COUNT=732,28,336,22
SOURCE_DIRECTORY='hit-ap-physical-clone-metadata-live-20261013-v1'
SOURCE_BIN_SHA='c552a232fc96317db47d13e2762f5980138cc18088b9675a7c7ad53c4e6b48ce'
SOURCE_JSON_SHA='4ddefb21a6aac7d94904f66eb84bd61031e0681d34c9df54733956f9eafb20eb'
SOURCE_RANGES=(('dispatcher_fixed244',0x129DC30,244,0),('physical_RF7',0x409AE64,84,244),
               ('physical_UW180',0x2511668,180,328),('dispatcher_actual_RF',0x408E150,12,508),
               ('dispatcher_UW_node_0',0x24FC4AC,12,520))
AP_DIRECTORY='hit-inline-unwind-20261012-117bef92'
AP_BIN_SHA='47486b1672e7f9cebb26e150f4e98657659df7a3976d35f06ec7d3fe8fa35c1a'
AP_JSON_SHA='17b6da0c864f89950026e8ec1934dce0f436053462b46c392fb3a26777e7c839'
AP_RF=(0x129C9F0,0x129CD3B,0x24FC2E0)


class UnwindRejected(ValueError):pass
def sha(raw):return hashlib.sha256(raw).hexdigest()
def material(path,digest,size=None):
    raw=Path(path).read_bytes()
    if sha(raw)!=digest or size is not None and len(raw)!=size:
        raise UnwindRejected('SOURCE_SHA_MISMATCH:'+Path(path).name)
    return raw


def parse_nodes(name,block,reported,records):
    begin,size,_,_=UW_BLOCKS[name];nodes=[]
    for saved in reported:
        rva=saved['unwind_rva'];off=rva-begin;raw=bytes.fromhex(saved['raw_hex'])
        if not 0<=off<size or off+len(raw)>size or block[off:off+len(raw)]!=raw:
            raise UnwindRejected('SOURCE_NODE_BYTES_OR_BOUND:'+name)
        if len(raw)<4 or raw[0]&7!=1 or raw[0]>>3 not in (0,4)or raw[3]!=0:
            raise UnwindRejected('SOURCE_NEW_UW_LAYOUT:'+name)
        tail=4+((raw[2]+1)&~1)*2;flags=raw[0]>>3
        length=tail+(12 if flags==4 else 0)
        if len(raw)!=length or saved.get('standard_length',length)!=length:
            raise UnwindRejected('SOURCE_NEW_UW_LENGTH:'+name)
        node={'rva':rva,'offset':off,'raw':raw,'tail_offset':tail,'flags':flags,'region':name}
        if flags==4:
            node['chain']=struct.unpack_from('<III',raw,tail)
            if node['chain'] not in records or tuple(saved.get('chain_entry',()))!=node['chain']:
                raise UnwindRejected('SOURCE_CHAIN_NOT_FRESH_FAMILY_RF:'+name)
        nodes.append(node)
    by_uw={n['rva']:n for n in nodes}
    if len(by_uw)!=len(records)or set(by_uw)!={r[2]for r in records}:
        raise UnwindRejected('SOURCE_UW_RF_PAIRING:'+name)
    for row in records:
        current=row;seen=set()
        while by_uw[current[2]]['flags']==4:
            if current in seen:raise UnwindRejected('SOURCE_CHAIN_CYCLE:'+name)
            seen.add(current);current=by_uw[current[2]]['chain']
        if current!=records[0]:raise UnwindRejected('SOURCE_CHAIN_PRIMARY:'+name)
    return nodes


def load_sources(source_root=ROOT):
    old=previous.load_sources(source_root)
    folder=Path(source_root)/'dist'/SOURCE_DIRECTORY
    raw=material(folder/'callsite.bin',SOURCE_BIN_SHA,532)
    meta=json.loads(material(folder/'callsite.json',SOURCE_JSON_SHA))
    ranges=tuple((r['name'],r['rva'],r['length'],r['binary_offset'])for r in meta['ranges'])
    gates=('complete','fresh_gates_verified','standard_layouts_complete',
           'dispatcher_fixed244_before_after_match','dispatcher_known224_before_after_match',
           'dispatcher_selected_RF_and_full_UW_before_after_match',
           'physical_RF_UW_windows_before_after_match','all_known_AP_physical_contact_pins_before_after_match',
           'AP_existing_complete_UW48_only_verified')
    if (ranges!=SOURCE_RANGES or meta.get('sha256')!=SOURCE_BIN_SHA or any(meta.get(k)is not True for k in gates)
        or meta.get('metadata_copy_readiness')!='STANDARD_METADATA_CAPTURED'
        or meta.get('fingerprint')!=old['metadata']['fingerprint']):
        raise UnwindRejected('SOURCE_NEW_PACKET_CONTRACT')
    dispatcher,physical=meta['dispatcher'],meta['physical']
    if (dispatcher['unknown_layouts']or not dispatcher['complete_standard_ancestry']
            or physical['unknown_layouts']or not physical['all_seven_standard_ancestries_closed']):
        raise UnwindRejected('SOURCE_NEW_UNKNOWN_LAYOUT')
    APfolder=Path(source_root)/'dist'/AP_DIRECTORY
    apraw=material(APfolder/'drain.bin',AP_BIN_SHA,559)
    apmeta=json.loads(material(APfolder/'drain.json',AP_JSON_SHA))
    if not apmeta.get('complete')or apmeta.get('sha256')!=AP_BIN_SHA or apmeta.get('fingerprint')!=meta['fingerprint']:
        raise UnwindRejected('SOURCE_AP_PACKET_CONTRACT')
    site=next(s for s in apmeta['sites']if s['name']=='default_delta')
    aprecord=next(r for r in site['exception_records']if r['index']==63753)
    if (aprecord['rva']!=0x408E078 or aprecord['raw_hex']!=struct.pack('<III',*AP_RF).hex()
            or tuple(aprecord[k]for k in ('begin','end','unwind_rva'))!=AP_RF):
        raise UnwindRejected('SOURCE_AP_RF')
    apnode=site['unwind_chain'][0]['complete_unwind']
    apuw=apraw[159:207]
    if (apnode['rva'],apnode['binary_offset'],apnode['length'],apnode['raw_hex'])!=(0x24FC2E0,159,48,apuw.hex()):
        raise UnwindRejected('SOURCE_AP_FULL48')
    source_fields=meta['source']['AP_physical_fixed_sources']
    if source_fields['C_bin']['sha256']!=AP_BIN_SHA or source_fields['C_json']['sha256']!=AP_JSON_SHA:
        raise UnwindRejected('SOURCE_AP_FRESH_PIN_ORIGIN')
    APpins={p['name']:p for p in meta['source']['known_before_after_pins']}
    for label,rva,pin in (('known_AP_RF',0x408E078,struct.pack('<III',*AP_RF)),('known_AP_UW48',0x24FC2E0,apuw)):
        if (APpins[label]['rva'],APpins[label]['length'],APpins[label]['sha256'])!=(rva,len(pin),sha(pin)):
            raise UnwindRejected('SOURCE_AP_FRESH_PIN_CONTRACT')
    blocks={name:old['raw'][off:off+size]for name,(_,size,off,_)in previous.UW_BLOCKS.items()}
    blocks.update(ap=apuw,dispatcher=raw[520:532],physical=raw[328:508])
    records={**old['records'],'ap':[AP_RF],
        'dispatcher':[struct.unpack_from('<III',raw,508)],
        'physical':[struct.unpack_from('<III',raw,244+i*12)for i in range(7)]}
    selected=dispatcher['selected_record']
    if (selected['index']!=63771 or selected['rva']!=0x408E150
            or records['dispatcher'][0]!=tuple(selected[k]for k in ('begin','end','unwind_rva'))
            or selected['raw_hex']!=raw[508:520].hex()
            or records['physical']!=[tuple(r[k]for k in ('begin','end','unwind_rva'))for r in physical['runtime_functions']]
            or [r['index']for r in physical['runtime_functions']]!=list(range(68146,68153))):
        raise UnwindRejected('SOURCE_NEW_RF_FIELDS')
    nodes={**old['nodes'],'ap':parse_nodes('ap',apuw,[{'unwind_rva':0x24FC2E0,'raw_hex':apuw.hex()}],records['ap']),
        'dispatcher':parse_nodes('dispatcher',blocks['dispatcher'],dispatcher['unwind_nodes'],records['dispatcher']),
        'physical':parse_nodes('physical',blocks['physical'],physical['nodes'],records['physical'])}
    for name,(begin,size,_)in REGIONS.items():
        rows=records[name]
        if rows[0][0]!=begin or rows[-1][1]!=begin+size or any(a[1]!=b[0]for a,b in zip(rows,rows[1:])):
            raise UnwindRejected('SOURCE_COMPLETE_RF_COVERAGE:'+name)
    merged=b''.join(blocks[n]for n in REGIONS)
    if len(merged)!=UW_BYTES or sum(len(v)for v in records.values())!=RF_COUNT:
        raise UnwindRejected('SOURCE_FIXED_COUNTS')
    return {'raw':merged,'blocks':blocks,'records':records,'nodes':nodes,'metadata':meta,
        'evidence':{'old19RF':old['evidence'],'new_packet':{'directory':str(folder.resolve()),
            'binary_sha256':SOURCE_BIN_SHA,'metadata_sha256':SOURCE_JSON_SHA},
            'AP_existing':{'directory':str(APfolder.resolve()),'binary_sha256':AP_BIN_SHA,'metadata_sha256':AP_JSON_SHA},
            'physical_indices_fresh':list(range(68146,68153)),'source_PIDs_are_origin_only':True,
            'source_raw_is_named_UW_block_concat':True,'merged_unwind_sha256':sha(merged)}}


def build(old_game_base,code_layout,unwind_address,table_address,source_root=ROOT):
    if dict(code_copy.REGIONS)!=REGIONS or set(code_layout)!=set(REGIONS):
        raise UnwindRejected('SIX_REGION_LAYOUT_PROFILE')
    previous.code_copy._layout(old_game_base,{n:code_layout[n]for n in previous.code_copy.REGIONS})
    spans=[previous._span(code_layout[n],size,old_game_base,'code:'+n)for n,(_,size,_)in REGIONS.items()]
    spans += [previous._span(unwind_address,UW_BYTES,old_game_base,'unwind',4),
              previous._span(table_address,RF_BYTES,old_game_base,'runtime_table',4)]
    ordered=sorted(spans)
    if any(a[1]>b[0]for a,b in zip(ordered,ordered[1:])):raise UnwindRejected('LAYOUT_OVERLAP')
    source=load_sources(source_root)
    code=code_copy.build(old_game_base,code_layout,source_root)
    uw=bytearray(source['raw'])
    def map_code(name,rva):
        begin,size,_=REGIONS[name]
        if not begin<=rva<=begin+size:raise UnwindRejected('RF_CODE_BOUND:'+name)
        return code_layout[name]-old_game_base+rva-begin
    def map_uw(name,rva):
        begin,size,_,offset=UW_BLOCKS[name]
        if not begin<=rva<begin+size:raise UnwindRejected('UW_REGION_BOUND:'+name)
        return unwind_address-old_game_base+offset+rva-begin
    records,nodes,rewrites=[],[],[]
    for name in REGIONS:
        block_offset=UW_BLOCKS[name][3]
        for row in source['records'][name]:
            records.append({'region':name,'old':row,'new':(map_code(name,row[0]),map_code(name,row[1]),map_uw(name,row[2]))})
        for node in source['nodes'][name]:
            at=block_offset+node['offset']
            if node['flags']==4:
                chain=node['chain'];mapped=(map_code(name,chain[0]),map_code(name,chain[1]),map_uw(name,chain[2]))
                struct.pack_into('<III',uw,at+node['tail_offset'],*mapped)
                rewrites.append({'region':name,'old_unwind_rva':node['rva'],'new_unwind_rva':map_uw(name,node['rva']),
                    'blob_offset':at+node['tail_offset'],'old_chain':chain,'new_chain':mapped})
            changed=bytes(uw[at:at+len(node['raw'])])
            if changed[:node['tail_offset']]!=node['raw'][:node['tail_offset']]:raise UnwindRejected('HEADER_OR_SLOTS_CHANGED')
            if node['flags']!=4 and changed!=node['raw']:raise UnwindRejected('HANDLER_OR_GS_BYTES_CHANGED')
            nodes.append({'region':name,'old_unwind_rva':node['rva'],'new_unwind_rva':map_uw(name,node['rva']),
                'blob_offset':at,'length':len(changed),'flags':node['flags'],'source_hex':node['raw'].hex(),'copy_hex':changed.hex()})
    records.sort(key=lambda r:r['new'][0])
    if len(records)!=RF_COUNT or len(rewrites)!=CHAIN_COUNT or any(a['new'][1]>b['new'][0]for a,b in zip(records,records[1:])):
        raise UnwindRejected('RELOCATED_RF_TABLE_CONTRACT')
    table=b''.join(struct.pack('<III',*r['new'])for r in records)
    manifest={'profile':'fixed_six_region_28RF_22CHAIN_UW_relocation_v1','old_game_base':old_game_base,
        'code_layout':dict(code_layout),'unwind_address':unwind_address,'runtime_table_address':table_address,
        'runtime_function_count':RF_COUNT,'runtime_table_bytes':RF_BYTES,'unwind_bytes':UW_BYTES,
        'runtime_records':records,'unwind_nodes':nodes,'chain_rewrites':rewrites,'source':source['evidence'],
        'unwind_sha256':sha(uw),'runtime_table_sha256':sha(table),'instruction_offsets_preserved':True,
        'headers_slots_GS_data_preserved':True,'handler_rvas_preserved':True,'RF_sorted_nonoverlapping':True,
        'native_registered':False,'native_called':False,'Game_accessed':False,'new_RX_executed':False,
        'owned_unwind_parity_proven':False,'Game_or_exception_safety_proven':False,'classification_ready':False}
    return {'code':code,'unwind_blob':bytes(uw),'runtime_table_blob':table,'manifest':manifest}


def export_build(result,output):
    output=Path(output);code_copy.export_build(result['code'],output)
    (output/'unwind.bin').write_bytes(result['unwind_blob'])
    (output/'runtime-function-table.bin').write_bytes(result['runtime_table_blob'])
    (output/'unwind-relocation.json').write_text(json.dumps(result['manifest'],indent=2)+'\n',encoding='utf8')
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('old-game-base','frame','world','contact','ap','dispatcher','physical','unwind','table'):
        parser.add_argument('--'+name,type=lambda s:int(s,0),required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=build(args.old_game_base,{n:getattr(args,n)for n in REGIONS},args.unwind,args.table)
    export_build(result,args.output)
    print(json.dumps({'RF_count':RF_COUNT,'UW_bytes':UW_BYTES,'chain_rewrites':CHAIN_COUNT,'native_called':False,'output':str(args.output)}))
if __name__=='__main__':main()
