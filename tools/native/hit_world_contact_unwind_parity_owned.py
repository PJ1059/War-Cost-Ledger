"""One Windows unwind parity run in this Python process's PAGE_READWRITE memory.

No Game process access, executable pages, dynamic function-table registration,
or execution of captured instructions/handlers. RtlVirtualUnwind(0) receives
the selected RF directly. The synthetic input is identical apart from ControlPc
and CONTEXT.Rip; it is not a reconstruction of a running Game frame.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    'fixed_hit_unwind_copy', Path(__file__).with_name('hit_world_contact_unwind_copy.py'))
mapper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mapper)

CFG_SOURCES = {
    'world': ('hit-world-update-r14-remainder-live-20261013-v1/r14-analysis.json',
              '8c9c7091cd2fc4a05cbd7700f92b257f56ab07dbd36d7ab84e5b303b186cfa25', 2137),
    'contact': ('hit-contact-whole-envelope-analysis-20261013-v1/analysis.json',
                '703c1a9cd5eb50f57c1c777614459cdffee4287183a00cad81dfbccdb95ece30', 3673),
}
COPY_RVAS = {'frame': 0x10000000, 'world': 0x10001000, 'contact': 0x10004000}
NEW_UW_RVA, NEW_TABLE_RVA = 0x10010000, 0x10011000
IMAGE_SIZE, STACK_SIZE, CONTEXT_SIZE = 0x10020000, 0x40000, 0x4D0
NONVOLATILE_GPRS = {'Rbx': 0x90, 'Rbp': 0xA0, 'Rsi': 0xA8, 'Rdi': 0xB0,
                    'R12': 0xD8, 'R13': 0xE0, 'R14': 0xE8, 'R15': 0xF0}
XMM_OFFSETS = {f'Xmm{i}': 0x1A0 + i * 16 for i in range(6, 16)}
DOCS = ['https://learn.microsoft.com/en-us/windows/win32/api/winnt/nf-winnt-rtlvirtualunwind',
        'https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-context']


class RuntimeFunction(ctypes.Structure):
    _fields_ = [('BeginAddress', ctypes.c_uint32), ('EndAddress', ctypes.c_uint32),
                ('UnwindData', ctypes.c_uint32)]


def load_pcs(code_source):
    """Use the two frozen closed CFGs, byte-checked against the captured code."""
    pcs, evidence = {}, []
    for name, (relative, expected_sha, count) in CFG_SOURCES.items():
        path = ROOT / 'dist' / relative
        raw = path.read_bytes()
        if mapper.sha(raw) != expected_sha:
            raise ValueError('CFG_SOURCE_SHA:' + name)
        analysis = json.loads(raw)
        items = analysis['instructions']
        begin, _, code_length = mapper.code_copy.REGIONS[name]
        if (analysis.get('normal_CFG_closed') is not True or analysis.get('issues') != []
                or len(items) != count or analysis.get('reachable_instruction_count') != count):
            raise ValueError('CFG_SOURCE_CONTRACT:' + name)
        found = []
        for item in items:
            offset = item['rva'] - begin
            encoded = bytes.fromhex(item['hex'])
            if (not 0 <= offset < code_length or offset + len(encoded) > code_length
                    or len(encoded) != item['size']
                    or code_source[name][offset:offset + len(encoded)] != encoded):
                raise ValueError('CFG_CODE_BYTES:' + name)
            found.append(item['rva'])
        if len(set(found)) != count or min(found) != begin:
            raise ValueError('CFG_PC_SET:' + name)
        pcs[name] = sorted(found)
        evidence.append({'region': name, 'path': str(path), 'sha256': expected_sha,
                         'reachable_instruction_count': count})
    md = mapper.code_copy.capstone.Cs(mapper.code_copy.capstone.CS_ARCH_X86,
                                    mapper.code_copy.capstone.CS_MODE_64)
    frame_begin = mapper.code_copy.REGIONS['frame'][0]
    frame = list(md.disasm(code_source['frame'], frame_begin))
    if len(frame) != 14 or sum(i.size for i in frame) != 67 or frame[-1].mnemonic != 'jmp':
        raise ValueError('FRAME_LINEAR_PATH')
    pcs['frame'] = [i.address for i in frame]
    return pcs, evidence


def normalize_ip(ip, base, layout):
    """Normalize only addresses inside original/copy code regions; all else literal."""
    for name, (rva, size, _) in mapper.code_copy.REGIONS.items():
        for start in (base + rva, layout[name]):
            if start <= ip < start + size:
                return ['code_region', name, ip - start]
    return ['absolute', ip]


def aligned_context():
    owner = ctypes.create_string_buffer(CONTEXT_SIZE + 15)
    return owner, (ctypes.addressof(owner) + 15) & ~15


class OwnedMemory:
    """Only VirtualAlloc/VirtualFree on allocations owned by this process."""
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.c_uint32, ctypes.c_uint32]
        self.kernel.VirtualAlloc.restype = ctypes.c_void_p
        self.kernel.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
        self.kernel.VirtualFree.restype = ctypes.c_int
        self.allocations, self.committed_pages = [], set()

    def allocate(self, size, commit=False):
        address = self.kernel.VirtualAlloc(None, size, 0x2000 | (0x1000 if commit else 0), 4)
        if not address:
            raise ctypes.WinError(ctypes.get_last_error())
        self.allocations.append((int(address), size))
        return int(address)

    def write_image(self, image, rva, raw):
        if not 0 <= rva < IMAGE_SIZE or rva + len(raw) > IMAGE_SIZE:
            raise ValueError('OWNED_IMAGE_BOUND')
        first, end = rva & ~0xFFF, (rva + len(raw) + 0xFFF) & ~0xFFF
        for offset in range(first, end, 0x1000):
            address = image + offset
            if address not in self.committed_pages:
                at = self.kernel.VirtualAlloc(address, 0x1000, 0x1000, 4)
                if at != address:
                    raise ctypes.WinError(ctypes.get_last_error())
                self.committed_pages.add(address)
        ctypes.memmove(image + rva, raw, len(raw))

    def close(self):
        failed = []
        for address, _ in reversed(self.allocations):
            if not self.kernel.VirtualFree(address, 0, 0x8000):
                failed.append(address)
        self.allocations.clear()
        return failed


def native_api():
    nt = ctypes.WinDLL('ntdll')
    nt.RtlCaptureContext.argtypes = [ctypes.c_void_p]
    nt.RtlCaptureContext.restype = None
    nt.RtlVirtualUnwind.argtypes = [ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint64,
                                  ctypes.POINTER(RuntimeFunction), ctypes.c_void_p,
                                  ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint64),
                                  ctypes.c_void_p]
    nt.RtlVirtualUnwind.restype = ctypes.c_void_p
    return nt


def snapshot(context, establisher, base, layout):
    raw = ctypes.string_at(context, CONTEXT_SIZE)
    out = {n: struct.unpack_from('<Q', raw, at)[0] for n, at in NONVOLATILE_GPRS.items()}
    out.update({n: raw[at:at + 16].hex() for n, at in XMM_OFFSETS.items()})
    out['Rsp'] = struct.unpack_from('<Q', raw, 0x98)[0]
    out['Rip'] = normalize_ip(struct.unpack_from('<Q', raw, 0xF8)[0], base, layout)
    out['EstablisherFrame'] = establisher
    return out


def run():
    if os.name != 'nt' or ctypes.sizeof(ctypes.c_void_p) != 8 or ctypes.sizeof(RuntimeFunction) != 12:
        raise ValueError('WINDOWS_X64_REQUIRED')
    source = mapper.load_sources()
    code_source, code_evidence = mapper.code_copy.load_sources()
    pcs, cfg_evidence = load_pcs(code_source)
    report = {'profile': 'owned_RW_same_input_RtlVirtualUnwind_parity_v1',
              'captured_at': datetime.now(timezone.utc).isoformat(), 'owned_process_pid': os.getpid(),
              'native_handler_type': 0, 'native_API_names': ['VirtualAlloc', 'VirtualFree',
                                                           'RtlCaptureContext', 'RtlVirtualUnwind'],
              'metadata_source': source['evidence'], 'code_sources': code_evidence,
              'CFG_sources': cfg_evidence, 'official_contracts': DOCS,
              'input_scope': 'One identical synthetic stack/CONTEXT at every saved normal-CFG PC; not actual Game frames.',
              'Rip_normalization': 'Only inside original/copy code region -> region+offset. Outside stays absolute.',
              'allocation_protection': 'PAGE_READWRITE only; reserved image pages committed only as needed.',
              'dynamic_function_table_registered': False, 'Game_accessed': False,
              'Game_or_copied_code_executed': False, 'handler_executed': False,
              'actual_Game_unwind_or_execution_proven': False, 'classification_ready': False,
              'expected_PC_counts': {n: len(pcs[n]) for n in mapper.code_copy.REGIONS},
              'tested_PC_counts': {n: 0 for n in mapper.code_copy.REGIONS},
              'RtlCaptureContext_calls': 0, 'RtlVirtualUnwind_calls': 0, 'differences': [],
              'status': 'INCOMPLETE'}
    memory, started = OwnedMemory(), time.perf_counter()
    try:
        base = memory.allocate(IMAGE_SIZE)
        stack = memory.allocate(STACK_SIZE, commit=True)
        layout = {n: base + r for n, r in COPY_RVAS.items()}
        built = mapper.build(base, layout, base + NEW_UW_RVA, base + NEW_TABLE_RVA)
        for name, raw in code_source.items():
            memory.write_image(base, mapper.code_copy.REGIONS[name][0], raw)
            memory.write_image(base, COPY_RVAS[name], built['code']['blobs'][name])
        for _, (rva, length, offset, _) in mapper.UW_BLOCKS.items():
            memory.write_image(base, rva, source['raw'][offset:offset + length])
        memory.write_image(base, NEW_UW_RVA, built['unwind_blob'])
        memory.write_image(base, NEW_TABLE_RVA, built['runtime_table_blob'])
        # All candidate restored pointers and caller returns are readable owned
        # stack addresses, outside both code layouts. No guessed live stack.
        stack_raw = b''.join(struct.pack('<Q', stack + 0x20000 + (i % 256) * 8)
                             for i in range(STACK_SIZE // 8))
        ctypes.memmove(stack, stack_raw, STACK_SIZE)
        stack_sha = hashlib.sha256(stack_raw).hexdigest()
        nt = native_api()
        owner0, captured = aligned_context()
        nt.RtlCaptureContext(captured)
        report['RtlCaptureContext_calls'] += 1
        initial = bytearray(ctypes.string_at(captured, CONTEXT_SIZE))
        struct.pack_into('<I', initial, 0x30, 0x10000B)  # AMD64 control/integer/float.
        for offset in range(0x78, 0xF8, 8):
            struct.pack_into('<Q', initial, offset, stack + 0x10000)
        # A body-shaped RSP keeps every saved XMM area 16B-aligned. This is
        # still one synthetic input, not a guessed per-PC execution state.
        struct.pack_into('<Q', initial, 0x98, stack + 0x8000)
        for i in range(16):
            at = 0x1A0 + i * 16
            initial[at:at + 16] = struct.pack('<QQ', 0x1111000000000000 + i, 0x2222000000000000 + i)
        old_owner, old_context = aligned_context()
        new_owner, new_context = aligned_context()
        old_records = [(n, r) for n in mapper.code_copy.REGIONS for r in source['records'][n]]
        old_RF = (RuntimeFunction * 19)(*(RuntimeFunction(*r) for _, r in old_records))
        new_by_old = {tuple(r['old']): i for i, r in enumerate(built['manifest']['runtime_records'])}
        new_table = (RuntimeFunction * 19).from_address(base + NEW_TABLE_RVA)
        report['owned_image_base'] = base
        report['owned_image_reservation_bytes'] = IMAGE_SIZE
        report['owned_stack_bytes'] = STACK_SIZE
        report['committed_image_pages'] = len(memory.committed_pages)
        report['runtime_function_count'] = 19
        report['mapper_UW_sha256'] = built['manifest']['unwind_sha256']
        report['mapper_RF_sha256'] = built['manifest']['runtime_table_sha256']
        failed = False
        for name in mapper.code_copy.REGIONS:
            region_begin = mapper.code_copy.REGIONS[name][0]
            for pc in pcs[name]:
                record_i, record = next((i, r) for i, (n, r) in enumerate(old_records)
                                        if n == name and r[0] <= pc < r[1])
                new_pc = layout[name] + pc - region_begin
                contexts = []
                for at, control_pc, RF in (
                    (old_context, base + pc, ctypes.pointer(old_RF[record_i])),
                    (new_context, new_pc, ctypes.pointer(new_table[new_by_old[record]]))):
                    ctypes.memmove(at, bytes(initial), CONTEXT_SIZE)
                    ctypes.c_uint64.from_address(at + 0xF8).value = control_pc
                    handler_data, establisher = ctypes.c_void_p(), ctypes.c_uint64()
                    selected_handler = nt.RtlVirtualUnwind(0, base, control_pc, RF, at,
                                                          ctypes.byref(handler_data),
                                                          ctypes.byref(establisher), None)
                    report['RtlVirtualUnwind_calls'] += 1
                    observed = snapshot(at, establisher.value, base, layout)
                    observed['SelectedHandler'] = int(selected_handler or 0)
                    contexts.append(observed)
                report['tested_PC_counts'][name] += 1
                differences = [{'field': k, 'original': contexts[0][k], 'copy': contexts[1][k]}
                               for k in contexts[0] if contexts[0][k] != contexts[1][k]]
                if contexts[0]['SelectedHandler'] or contexts[1]['SelectedHandler']:
                    differences.append({'field': 'unexpected_handler_selection',
                                        'original': contexts[0]['SelectedHandler'],
                                        'copy': contexts[1]['SelectedHandler']})
                if differences:
                    report['differences'] = [{'region': name, 'original_pc_rva': pc,
                                              'copy_pc_rva': new_pc - base,
                                              'fields': differences[:10],
                                              'omitted_field_differences': max(0, len(differences) - 10)}]
                    failed = True
                    break
            if failed:
                break
        report['fake_stack_before_sha256'] = stack_sha
        report['fake_stack_after_sha256'] = hashlib.sha256(ctypes.string_at(stack, STACK_SIZE)).hexdigest()
        report['fake_stack_unchanged'] = report['fake_stack_after_sha256'] == stack_sha
        report['all_saved_reachable_PCs_tested'] = report['expected_PC_counts'] == report['tested_PC_counts']
        report['status'] = ('PASS' if not failed and report['fake_stack_unchanged']
                            and report['all_saved_reachable_PCs_tested'] else 'FAIL')
        report['owned_same_input_unwind_parity_proven'] = report['status'] == 'PASS'
    except Exception as error:
        report['status'] = 'ERROR'
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        report['owned_same_input_unwind_parity_proven'] = False
    finally:
        failures = memory.close()
        report['owned_allocations_released'] = not failures
        report['release_failures'] = failures
        report['elapsed_ms'] = (time.perf_counter() - started) * 1000
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'tested_PC_counts': report['tested_PC_counts'],
                      'RtlVirtualUnwind_calls': report['RtlVirtualUnwind_calls'],
                      'owned_allocations_released': report['owned_allocations_released'],
                      'report': str(args.report)}))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
