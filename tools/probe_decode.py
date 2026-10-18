"""Decode the bounded HD2STAT1 capture outside the game's update thread.

No filenames from the capture are used for output. The caller decides where to
save the returned object. Integer, float and bool slots remain independent.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import struct


MAGIC = b'HD2STAT1'
HEADER = struct.Struct('<8s5I')
ENTRY_STRIDE = 20
SOURCE_STRIDE = 328
SOURCE_BLOCKS = 64
SOURCE_ENTRIES = 16
MAX_SIZE = 1048576
MAX_CAPACITY = 4096


def _uint(value, limit=0xFFFFFFFF):
    return type(value) is int and 0 <= value <= limit


def _entry(data: bytes, offset: int, slot: int) -> dict:
    key, integer, bits = struct.unpack_from('<IiI', data, offset)
    number = struct.unpack_from('<f', data, offset + 8)[0]
    byte = data[offset + 12]
    result = {'slot': slot, 'key': key, 'i32': integer,
        'f32_valid': math.isfinite(number), 'float_bits': bits,
        'bool': byte != 0, 'bool_byte': byte}
    if result['f32_valid']:
        result['f32'] = number
    return result


def decode_binary(data: bytes) -> dict:
    """Return the legacy JSON snapshot shape after exact binary validation."""
    if not isinstance(data, bytes) or len(data) < HEADER.size or len(data) > MAX_SIZE:
        raise ValueError('二进制采集长度无效（上限 1 MiB）。')
    magic, *lengths = HEADER.unpack_from(data)
    if magic != MAGIC:
        raise ValueError('二进制采集 magic 无效。')
    if HEADER.size + sum(lengths) != len(data):
        raise ValueError('二进制采集分段长度与文件不一致。')
    buffers = []
    offset = HEADER.size
    for length in lengths:
        buffers.append(data[offset:offset + length])
        offset += length
    metadata_bytes, main_bytes, source_bytes, *code_bytes = buffers
    try:
        metadata = json.loads(metadata_bytes.decode('utf8'))
    except (ValueError, UnicodeError) as error:
        raise ValueError('二进制采集 metadata 不是有效 UTF-8 JSON。') from error
    if not isinstance(metadata, dict):
        raise ValueError('二进制采集 metadata 不是对象。')
    capacity, empty = metadata.get('capacity'), metadata.get('empty')
    if not _uint(capacity, MAX_CAPACITY) or not _uint(empty):
        raise ValueError('二进制采集容量或空槽键无效。')
    if capacity and capacity & (capacity - 1):
        raise ValueError('二进制采集容量不是 2 的幂。')
    if not _uint(metadata.get('player_entity')) or not _uint(metadata.get('score_index'), 3):
        raise ValueError('二进制采集玩家索引无效。')
    if len(main_bytes) != capacity * ENTRY_STRIDE:
        raise ValueError('二进制采集主表长度无效。')
    if len(source_bytes) not in (0, SOURCE_BLOCKS * SOURCE_STRIDE):
        raise ValueError('二进制采集来源表长度无效。')

    stats = {'player_entity': metadata['player_entity'], 'score_index': metadata['score_index'],
        'capacity': capacity, 'main': [], 'sources': []}
    for slot in range(capacity):
        offset = slot * ENTRY_STRIDE
        if struct.unpack_from('<I', main_bytes, offset)[0] != empty:
            stats['main'].append(_entry(main_bytes, offset, slot))
    if source_bytes:
        for block in range(SOURCE_BLOCKS):
            base = block * SOURCE_STRIDE
            lo, hi = struct.unpack_from('<II', source_bytes, base)
            if lo == 0 and hi == 0:
                continue
            source = {'block': block, 'type': '%08X%08X' % (hi, lo), 'entries': []}
            for slot in range(SOURCE_ENTRIES):
                offset = base + 8 + slot * ENTRY_STRIDE
                if struct.unpack_from('<I', source_bytes, offset)[0] == 0:
                    break
                source['entries'].append(_entry(source_bytes, offset, slot))
            stats['sources'].append(source)

    result = dict(metadata)
    result['stats'] = stats
    ranges = metadata.get('code_ranges')
    if ranges is None:
        if any(code_bytes):
            raise ValueError('二进制采集有代码段但缺少范围描述。')
    else:
        if not isinstance(ranges, list) or len(ranges) != 2:
            raise ValueError('二进制采集代码范围数量无效。')
        result['code'] = []
        for description, buffer in zip(ranges, code_bytes):
            if not isinstance(description, dict) or not _uint(description.get('rva')) or not _uint(description.get('size'), MAX_SIZE):
                raise ValueError('二进制采集代码范围描述无效。')
            item = {'rva': description['rva'], 'size': description['size']}
            if buffer:
                if len(buffer) != description['size']:
                    raise ValueError('二进制采集代码段长度无效。')
                item['hex'] = buffer.hex().upper()
            elif description.get('error') == 'unreadable':
                item['error'] = 'unreadable'
            else:
                raise ValueError('二进制采集代码段为空且未报告不可读。')
            result['code'].append(item)
    return result


def read_binary(path: Path) -> dict:
    path = Path(path)
    if path.stat().st_size > MAX_SIZE:
        raise ValueError('二进制采集超过 1 MiB。')
    with path.open('rb') as source:
        data = source.read(MAX_SIZE + 1)
    return decode_binary(data)
