"""Index only direct calls/jumps to the saved native next-session-record reader."""
from pathlib import Path
import argparse
import hashlib
import heapq
import importlib.util
import json
import struct

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'tools/hit-contact-registration-index.py'
INDEX_SHA='3cf85cbf1ebac30dc3d7c7fd0518eb8ea0ba8f5637898c331e6403d7430a5598'
TARGET=0x1350EF0
PIN='4c8b0df9bf12028b0a413b8938f80100'
SOURCE=ROOT/'dist/recon-session-reader-local-live-20261013-v1/reader-local.bin'


def validate_source():
    raw=SOURCE.read_bytes()
    offset=TARGET-0x1350E98
    if len(raw)!=154 or raw[offset:offset+16].hex()!=PIN or raw[offset-7:offset]!=b'\xcc'*7 or raw[0x1350F27-0x1350E98]!=0xC3:
        raise ValueError('RECON_SESSION_READER_ENTRY_CHANGED')
    return {'source':str(SOURCE),'sha256':hashlib.sha256(raw).hexdigest(),
            'reader_entry':TARGET,'reader_bytes':56,'dispatch_or_discovery_proven':False}


def byte_matches(buffer,buffer_rva,kind,absolute):
    if kind!='code':raise ValueError('RECON_SESSION_READER_CODE_ONLY')
    def matches(opcode,label):
        at=buffer.find(opcode)
        while at>=0:
            if at+5<=len(buffer) and buffer_rva+at+5+struct.unpack_from('<i',buffer,at+1)[0]==TARGET:
                yield at,5,label
            at=buffer.find(opcode,at+1)
    return heapq.merge(matches(b'\xe8','call_next_session_record'),matches(b'\xe9','jump_next_session_record'))


def private_index():
    if hashlib.sha256(INDEX.read_bytes()).hexdigest()!=INDEX_SHA:raise ValueError('RECON_READER_INDEX_CHANGED')
    spec=importlib.util.spec_from_file_location('_session_reader_calls',INDEX)
    index=importlib.util.module_from_spec(spec);spec.loader.exec_module(index)
    index.validate_sources();source=validate_source()
    index.REVISION='recon_next_session_record_caller_index_v1'
    index.SECTIONS=index.SECTIONS[:1]
    index.TARGET_RVA=TARGET;index.PIN_RVA=TARGET;index.PIN_HEX=PIN
    index.byte_matches=byte_matches
    index.validate_sources=lambda:source
    return index


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();index=private_index();deps=dict(index.profile.load_dependencies());original=deps['game_processes']
    def pid():
        found=tuple(original())
        if found!=(args.pid,):raise ValueError('RECON_READER_PID_CHANGED')
        return found
    deps['game_processes']=pid
    print(json.dumps(index.run(args.output,dependencies=deps),indent=2))


if __name__=='__main__':main()
