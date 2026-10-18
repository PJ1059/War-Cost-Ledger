"""One pending-producer replay group, using this Python process's owned pages.

This tool never enumerates or opens another process. All callable addresses,
manager/user globals, HitInfo, damage values, stack frames and sentinels belong
to this tool. It does not execute captured game code or install a game hook.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/native"))
from hit_bridge_owned import OwnedBridge, Record, _Code
from hit_contact_arena_owned import OwnedContactArena
from hit_entity_resolver_owned import OwnedEntityResolver
from hit_physical_profile_owned import snapshot_code

RETURN = 0x1122334455667788
COMMON_RCX = 0x8877665544332211
STACK_VALUES = tuple(0xFEDCBA9876543200 + i for i in range(8))
ALLOC = 0x2208
CALLER_UNWIND = bytes.fromhex(
    "01441400 44a80a00 3b980900 32680800 27014100 1d010002 13010002 "
    "0cf0 0ae0 08d0 06c0 0470 0360 0250 0130"
)


def address(fn):
    return int(ctypes.cast(fn, ctypes.c_void_p).value)


def relocated(entry, addresses):
    raw = bytearray.fromhex(entry["code_hex"])
    for item in entry["relocations"]:
        at = item["offset"]
        if item["width"] != 8 or raw[at:at + 8] != bytes(8):
            raise AssertionError("Only manifest-declared zero 8-byte literals may bind")
        struct.pack_into("<Q", raw, at,
                         addresses[item["address_key"]] + item["addend"])
    return bytes(raw)


def sentinel_code():
    c = _Code()
    for reg, opcode in [(1, "48 89 09"), (2, "48 89 51 08"),
                        (8, "4c 89 41 10"), (9, "4c 89 49 18")]:
        c.emit(opcode)
    for i in range(8):
        c.emit("48 8b 84 24 " + struct.pack("<I", 0x28 + 8 * i).hex(" "))
        c.emit("48 89 81 " + struct.pack("<I", 0x20 + 8 * i).hex(" "))
    c.emit("48 ff 41 60 48 b8 " + struct.pack("<Q", RETURN).hex(" ") + " c3")
    return c.finish()


class Fixture:
    def __init__(self, bridge, manifest):
        self.b, self.m = bridge, manifest
        self.arena = OwnedContactArena(bridge)
        self.resolver = OwnedEntityResolver(bridge)
        self.entries = {e["name"]: e for e in manifest["entries"]}
        tables = manifest.get("data_tables", {})
        enemies = [int(v, 16) for v in tables.get("enemy_types", [])]
        sources = [int(v, 16) for v in tables.get("source_types", [])]
        self.enemy = (enemies or self.resolver.enemies)[0]
        self.source = (sources or self.resolver.sources)[0]
        self.resolver.insert(1001, self.enemy, 0)
        self.resolver.insert(1002, self.source, 1)
        manager_global = bridge._allocate(8, executable=False)
        ctypes.c_uint64.from_address(manager_global).value = self.resolver.manager
        user = bridge._allocate(0xB3A0, executable=False)
        ctypes.c_uint64.from_address(user + 0xB398).value = bridge.local_peer
        user_global = bridge._allocate(8, executable=False)
        ctypes.c_uint64.from_address(user_global).value = user
        original = bridge._procedure(sentinel_code(), ctypes.c_uint64,
                                     unwind=bytes.fromhex("01000000"))
        self.addresses = {
            "arena": self.arena.address, "bridge": bridge.base,
            "entity_manager_global": manager_global,
            "current_user_global": user_global,
            "qualifier": address(self.resolver._qualify),
            "publish": address(bridge.publisher), "drain": address(bridge.consumer),
            "original_contact_begin": address(original),
            "original_normal_final": address(original),
            "original_custom_curve": address(original),
        }
        for name, values in tables.items():
            raw = b"".join(struct.pack("<Q", int(v, 16)) for v in values)
            at = bridge._allocate(len(raw), executable=False)
            ctypes.memmove(at, raw, len(raw)); self.addresses[name] = at
        # Resolve a frozen entry only after every declared dependency is bound.
        # Existing bridge/resolver leaves may supply keys the producer reuses.
        self.functions = {}
        pending = dict(self.entries)
        for key in pending:
            self.addresses.pop(key, None)
        while pending:
            progress = False
            for name, entry in list(pending.items()):
                if any(r["address_key"] not in self.addresses
                       for r in entry["relocations"]):
                    continue
                code = relocated(entry, self.addresses)
                fn = bridge._procedure(code, ctypes.c_uint64,
                                       unwind=bytes.fromhex(entry["unwind_hex"]),
                                       executable_length=entry["executable_length"])
                self.functions[name] = fn; self.addresses[name] = address(fn)
                del pending[name]; progress = True
            if not progress:
                missing = sorted({r["address_key"] for e in pending.values()
                                  for r in e["relocations"]
                                  if r["address_key"] not in self.addresses})
                raise AssertionError(f"Unresolved frozen dependencies: {missing}")
        self.snapshots = []
        for displacement in (0, 512):
            c = _Code(); snapshot_code(c, displacement); c.emit("c3")
            self.snapshots.append(bridge._procedure(
                c.finish(), None, unwind=bytes.fromhex("01000000")))
        self.hit = (ctypes.c_uint8 * 0x118)()
        self.damage = (ctypes.c_uint8 * 0x24)()
        self.projectile = (ctypes.c_uint8 * 0x100)()
        self.floats = (ctypes.c_float * 4)(5, 4, 17, 19)
        self.mxcsr = ctypes.c_uint32(0x3F80)
        self.output = bridge._allocate(4096, executable=False)
        bridge.kernel.GetCurrentThreadId.argtypes = []
        bridge.kernel.GetCurrentThreadId.restype = ctypes.c_uint32
        owned_thread = int(bridge.kernel.GetCurrentThreadId())
        # Every scenario starts with empty rows and only this same tool thread
        # runs; its first bounded arena probe therefore owns this precise row.
        self.row = self.arena.rows + (owned_thread & 31) * 640
        self.config = (ctypes.c_uint64 * 8)(
            self.output, ctypes.addressof(self.hit), ctypes.addressof(self.damage),
            ctypes.addressof(self.floats), ctypes.addressof(self.projectile),
            self.row, ctypes.addressof(self.mxcsr), 0)
        self.defaults()

    def defaults(self):
        ctypes.memset(self.hit, 0, len(self.hit))
        ctypes.memset(self.damage, 0, len(self.damage))
        ctypes.memset(self.projectile, 0, len(self.projectile))
        ctypes.c_uint64.from_buffer(self.hit, 0x110).value = self.b.local_peer
        ctypes.c_uint32.from_buffer(self.hit, 0x20).value = 1001
        ctypes.c_uint32.from_buffer(self.hit, 0x80).value = 1002
        ctypes.c_uint32.from_buffer(self.hit, 0x100).value = 71
        ctypes.c_float.from_buffer(self.hit, 0x50).value = 4
        ctypes.c_float.from_buffer(self.damage, 0).value = 22
        ctypes.c_float.from_buffer(self.damage, 4).value = 0.65
        self.damage[0x1C] = 1
        self.floats[0], self.floats[1] = 5, 4
        self.mxcsr.value = 0x3F80
        self.config[7] = 0
        ctypes.memset(self.output, 0, 4096)
        self.arena.reset_after_owned_calls_return()

    def runner(self, actions):
        if len(actions) > 8:
            raise AssertionError("One scenario is bounded to eight producer-site calls")
        c = _Code()
        c.emit("53 55 56 57 41 54 41 55 41 56 41 57 "
               "48 81 ec 00 10 00 00 84 04 24 "
               "48 81 ec 00 10 00 00 84 04 24 "
               "48 81 ec 08 02 00 00 84 04 24")
        c.emit("0f 29 b4 24 80 00 00 00 44 0f 29 8c 24 90 00 00 00 "
               "44 0f 29 94 24 a0 00 00 00 0f ae 9c 24 b0 00 00 00")
        c.emit("49 89 cc 48 8d 9c 24 00 01 00 00 4c 8d b4 24 80 fb ff ff "
               "4c 89 f5 49 89 dd")  # R12 config; HI=RSP+100; RBP=RSP-480.
        c.emit("49 8b 74 24 08 48 89 df b9 23 00 00 00 fc f3 48 a5")
        c.emit("48 b8 " + struct.pack("<Q", COMMON_RCX).hex(" ")
               + " 49 89 86 c0 24 00 00")
        for i, value in enumerate(STACK_VALUES):
            c.emit("48 b8 " + struct.pack("<Q", value).hex(" ")
                   + " 48 89 84 24 " + struct.pack("<I", 0x20 + 8 * i).hex(" "))
        for i, action in enumerate(actions):
            if action in ("contact_begin", "normal_final", "custom_curve"):
                out = {"contact_begin": 0, "normal_final": 128, "custom_curve": 256}[action]
                c.emit("49 8b 0c 24 48 8d 89 " + struct.pack("<I", out).hex(" "))
                if action == "normal_final":
                    c.emit("49 8b 54 24 10 49 89 d8 49 8b 44 24 20")
                else:
                    c.emit("48 89 da 49 b8 88 99 aa bb cc dd ee ff")
                c.emit("49 b9 11 22 33 44 55 66 77 88")
            elif action == "default_delta":
                c.emit("4d 8b 54 24 18 f3 41 0f 10 02 f3 45 0f 10 12 "
                       "f3 45 0f 10 4a 04 4d 8b 54 24 30 41 0f ae 12")
                c.emit("49 8b 0c 24 48 8d 89 00 02 00 00")
            elif action == "physical_success":
                c.emit("49 8b 6c 24 10 49 89 dd 41 bf 11 00 00 00 "
                       "49 8b 0c 24 48 8d 89 00 06 00 00")
            elif action == "contact_end":
                c.emit("4c 89 f5 49 8b 0c 24 48 8d 89 00 0a 00 00")
            else:
                raise AssertionError(f"Unknown action {action}")
            c.emit("49 bb " + struct.pack("<Q", self.addresses[action]).hex(" "))
            if action in ("default_delta", "physical_success", "contact_end"):
                c.emit("ff 15 02 00 00 00 eb 08 "
                       + struct.pack("<Q", address(self.snapshots[0])).hex(" "))
            c.emit("41 ff d3")
            if action == "physical_success":
                c.emit("34 01 ff 15 02 00 00 00 eb 08 "
                       + struct.pack("<Q", address(self.snapshots[1])).hex(" "))
                c.emit("4c 89 f5")
            elif action == "default_delta":
                c.emit("ff 15 02 00 00 00 eb 08 "
                       + struct.pack("<Q", address(self.snapshots[1])).hex(" "))
            elif action == "contact_end":
                c.emit("49 89 4c 24 38 49 8b 0c 24 48 8d 89 00 0a 00 00")
                c.emit("ff 15 02 00 00 00 eb 08 "
                       + struct.pack("<Q", address(self.snapshots[1])).hex(" "))
            else:
                c.emit("49 8b 14 24 48 89 82 " + struct.pack("<I", 0x180 + i * 8).hex(" "))
            c.emit("48 b8 " + struct.pack("<Q", self.b.base).hex(" ") + " 8b 40 1c "
                   "49 8b 14 24 89 82 " + struct.pack("<I", 0x1C0 + i * 4).hex(" "))
            c.emit("49 8b 44 24 28 8b 40 58 89 82 "
                   + struct.pack("<I", 0x1E0 + i * 4).hex(" "))
        # Preserve the caller's own pre-test floating-point environment.
        c.emit("0f 28 b4 24 80 00 00 00 44 0f 28 8c 24 90 00 00 00 "
               "44 0f 28 94 24 a0 00 00 00 0f ae 94 24 b0 00 00 00 48 81 c4 "
               + struct.pack("<I", ALLOC).hex(" ")
               + " 41 5f 41 5e 41 5d 41 5c 5f 5e 5d 5b c3")
        code = c.finish()
        return self.b._procedure(code, None, ctypes.c_void_p, unwind=CALLER_UNWIND)

    def run(self, actions):
        runner = self.runner(actions)
        runner(ctypes.addressof(self.config))
        raw = ctypes.string_at(self.output, 4096)
        trace = list(struct.unpack_from("<" + "I" * len(actions), raw, 0x1C0))
        flags = list(struct.unpack_from("<" + "I" * len(actions), raw, 0x1E0))
        return self.b.drain(), trace, flags, raw


def record_dict(record):
    out = {}
    for name, _ in Record._fields_:
        value = getattr(record, name)
        out[name] = "NaN" if isinstance(value, float) and math.isnan(value) else value
    out["raw_hex"] = ctypes.string_at(ctypes.addressof(record), 96).hex()
    return out


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


def unchanged_snapshot(raw, start, *, physical=False, default_delta=None,
                       snan=False):
    before, after = raw[start:start + 512], raw[start + 512:start + 1024]
    gp_before, gp_after = struct.unpack_from("<16Q", before), struct.unpack_from("<16Q", after)
    if physical:
        expect(gp_after[0] == (gp_before[0] & ~0xFF) | 1,
               "Physical original clear/XOR changed more than AL")
        expect(gp_before[1:] == gp_after[1:], "Physical gateway changed a GP register")
        expect(after[128] & 0xC5 == 0 and after[129] == 0,
               "Physical caller XOR AL,1 did not leave its actual arithmetic flags")
    else:
        expect(gp_before == gp_after, "Gateway changed an original GP register")
        expect(before[128:130] == after[128:130], "Gateway changed arithmetic flags")
    if default_delta is not None or snan:
        expect(before[164:416] == after[164:416],
               "Default SUBSS changed another XMM lane/register")
        bits = struct.unpack_from("<I", after, 160)[0]
        if snan:
            expect(bits & 0x7FC00000 == 0x7FC00000, "Actual SUBSS did not quiet the supplied sNaN")
            expect(struct.unpack_from("<I", after, 136)[0]
                   == struct.unpack_from("<I", before, 136)[0] | 1,
                   "Default gateway lost original SUBSS invalid sticky bit")
        else:
            expect(struct.unpack_from("<f", after, 160)[0] == default_delta,
                   "Default gateway did not preserve post-original XMM0")
            expect(before[136:140] == after[136:140], "Default gateway changed full post-MXCSR")
    else:
        expect(before[160:416] == after[160:416], "Gateway changed an XMM register")
        expect(before[136:140] == after[136:140], "Gateway changed full MXCSR")


def sentinel_parameters(fixture, raw, actions):
    hi = struct.unpack_from("<Q", raw, 8)[0]
    for action, area in [("contact_begin", 0), ("normal_final", 128), ("custom_curve", 256)]:
        times = actions.count(action)
        expect(struct.unpack_from("<Q", raw, area + 96)[0] == times,
               f"{action} original callee was not called exactly once per site")
        if not times:
            continue
        rcx, rdx, r8, r9 = struct.unpack_from("<4Q", raw, area)
        expect(rcx == fixture.output + area, f"{action} lost original RCX")
        expect(rdx == (ctypes.addressof(fixture.damage) if action == "normal_final" else hi),
               f"{action} lost original RDX")
        expect(r8 == (hi if action == "normal_final" else 0xFFEEDDCCBBAA9988),
               f"{action} lost original R8")
        expect(r9 == 0x8877665544332211, f"{action} lost original R9")
        expect(struct.unpack_from("<8Q", raw, area + 32) == STACK_VALUES,
               f"{action} lost an original stack argument")
    for i, action in enumerate(actions):
        if action in ("contact_begin", "normal_final", "custom_curve"):
            expect(struct.unpack_from("<Q", raw, 0x180 + 8 * i)[0] == RETURN,
                   f"{action} changed the original callee return value")
    if "contact_end" in actions:
        expect(fixture.config[7] == COMMON_RCX, "Common exit did not replay original MOV RCX,[RBP+24C0]")
        unchanged_snapshot(raw, 2560)


def main():
    destination = ROOT / "dist/hit-copy-pending-observer-owned-20261013-v1"
    destination.mkdir(parents=True, exist_ok=True)
    generator = ROOT / "tools/native/hit_copy_pending_observer.py"
    sha = hashlib.sha256(generator.read_bytes()).hexdigest()
    frozen = "c13d771d037a83c514d6ca650321ff078542855be5035d85ead9b47b17546c54"
    expect(sha == frozen, "Frozen generator changed; owned replay withheld")
    import hit_copy_pending_observer as producer
    m = producer.manifest()
    expect(len(m["entries"]) == 18 and len(m["sites"]) == 6,
           "Frozen six-site/eighteen-entry interface changed")
    default = next(e for e in m["entries"] if e["name"] == "default_delta")
    expect(default["code_hex"].startswith("f3410f5cc1")
           and default["unwind_hex"] == "01130605130310012400087007600650",
           "Default original SUBSS/UW +5 contract changed")
    report = {
        "status": "RUNNING", "group": "one_owned_pending_replay_group",
        "pid": os.getpid(), "generator_sha256": sha,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "external_process_enumeration": False, "Game_access": False,
        "Game_code_executed": False, "Game_hook_installed": False,
        "gameplay_or_exception_safety_proven": False,
        "all_native_targets_owned": False, "cases": [],
    }
    started = time.perf_counter()
    current = "owned_initialization"
    try:
        with OwnedBridge() as b:
            p = Fixture(b, m)
            for entry in m["entries"]:
                for rel in entry["relocations"]:
                    target = p.addresses[rel["address_key"]] + rel["addend"]
                    expect(any(base <= target < base + size
                               for base, size in b._allocation_sizes.items()),
                           f"Relocation escaped owned allocation: {entry['name']}:{rel['address_key']}")
            report["all_native_targets_owned"] = True
            cases = [
                ("normal_negative_delta", 3, ("contact_begin", "default_delta", "normal_final", "contact_end"), [0, 0, 0, 1], 1),
                ("normal_equal_delta", 4, ("contact_begin", "default_delta", "normal_final", "contact_end"), [0, 0, 0, 1], 1),
                ("normal_high_delta", 5, ("contact_begin", "default_delta", "normal_final", "contact_end"), [0, 0, 0, 1], 1),
                ("normal_then_true_physical", 3, ("contact_begin", "default_delta", "normal_final", "physical_success", "contact_end"), [0, 0, 0, 0, 1], 1),
                ("AP_force_survives_physical", 5, ("contact_begin", "default_delta", "normal_final", "physical_success", "contact_end"), [0, 0, 0, 0, 1], 1),
                ("next_begin_and_final_end_once", 5, ("contact_begin", "default_delta", "normal_final", "contact_begin", "default_delta", "normal_final", "contact_end", "contact_end"), [0, 0, 0, 1, 1, 1, 2, 2], 2),
                ("missing_AP_rejected", 5, ("contact_begin", "normal_final", "contact_end"), [0, 0, 0], 0),
                ("wrong_high_peer_rejected", 5, ("contact_begin", "default_delta", "normal_final", "physical_success", "contact_end"), [0, 0, 0, 0, 0], 0),
                ("unknown_enemy_rejected", 5, ("contact_begin", "default_delta", "normal_final", "physical_success", "contact_end"), [0, 0, 0, 0, 0], 0),
                ("custom_force_survives_physical", 5, ("contact_begin", "custom_curve", "normal_final", "physical_success", "contact_end"), [0, 0, 0, 0, 1], 1),
                ("original_SUBSS_snan_post_MXCSR", 5, ("contact_begin", "default_delta", "normal_final", "contact_end"), [0, 0, 0, 1], 1),
            ]
            for current, ap, actions, expected_trace, count in cases:
                p.defaults(); p.floats[0] = ap
                ordinal_before = p.arena.stats()["contact_counter"]
                if current == "wrong_high_peer_rejected":
                    ctypes.c_uint64.from_buffer(p.hit, 0x110).value = b.local_peer ^ (1 << 32)
                elif current == "unknown_enemy_rejected":
                    ctypes.c_uint32.from_buffer(p.hit, 0x20).value = 9999
                elif current in ("custom_force_survives_physical", "AP_force_survives_physical"):
                    p.hit[0x73] = 1; p.projectile[0xFC] = 1
                elif current == "original_SUBSS_snan_post_MXCSR":
                    ctypes.c_uint32.from_buffer(p.floats).value = 0x7F800001
                records, trace, flags, raw = p.run(actions)
                case = {"name": current, "status": "CHECKING", "actions": list(actions),
                        "count_trace": trace, "capture_flags_trace": flags,
                        "records": [record_dict(r) for r in records]}
                report["cases"].append(case)
                expect(trace == expected_trace, f"{current}: first count trace difference {trace} != {expected_trace}")
                expect(len(records) == count, f"{current}: expected {count} records, got {len(records)}")
                sentinel_parameters(p, raw, actions)
                if "default_delta" in actions:
                    expect(all(flags[i] == 0x9C for i, action in enumerate(actions)
                               if action == "default_delta"),
                           "Default AP-stage flags differ from exact 0x9C")
                    unchanged_snapshot(raw, 512,
                                       default_delta=ap - 4 if current != "original_SUBSS_snan_post_MXCSR" else None,
                                       snan=current == "original_SUBSS_snan_post_MXCSR")
                if "physical_success" in actions:
                    unchanged_snapshot(raw, 1536, physical=True)
                    expect(p.damage[0x1C] == 0, "Original physical DP+1C clear was lost")
                if current == "normal_then_true_physical":
                    r = records[0]
                    expect(r.native_branch == 2 and r.projectile_slot == 17
                           and r.ap_delta == -1 and r.selected_ap == 3
                           and r.armour == 4 and r.capture_flags == 0x1FF,
                           "True physical result did not replace exactly one full normal/AP tuple")
                elif current == "AP_force_survives_physical":
                    expect(records[0].native_branch == 2 and records[0].effect_flags == 3
                           and records[0].ap_delta == 1 and records[0].selected_ap == 5
                           and records[0].capture_flags == 0x1FF,
                           "True physical result discarded valid AP/force or polluted capture flags")
                elif current == "custom_force_survives_physical":
                    expect(records[0].native_branch == 2 and records[0].effect_flags == 7,
                           "True physical result discarded custom/HI-force/projectile-force evidence")
                elif current == "original_SUBSS_snan_post_MXCSR":
                    expect(math.isnan(records[0].ap_delta), "Producer fabricated a finite AP delta from sNaN")
                    case["raw_nonfinite_result_requires_consumer_unknown"] = True
                elif count:
                    expect(all(r.native_branch == 1 and r.capture_flags == 0x1FF
                               and r.ap_delta == ap - 4 and r.creditor == b.local_peer
                               and r.target == 1001 and r.source == 1002 for r in records),
                           "Normal frozen tuple/ownership/class evidence changed")
                if current not in ("missing_AP_rejected", "unknown_enemy_rejected",
                                   "custom_force_survives_physical"):
                    expect(all(flags[i] == 0x1FF for i, action in enumerate(actions)
                               if action in ("normal_final", "physical_success")),
                           "Full normal/physical tuple flags differ from exact 0x1FF")
                if count:
                    expect([r.contact_ordinal for r in records]
                           == list(range(ordinal_before + 1, ordinal_before + count + 1)),
                           "One physical/normal contact generated more than one ordinal")
                expect(ctypes.c_uint32.from_address(p.arena.address + 44).value == 0,
                       "Gateway active counter did not return to zero")
                case.update(status="PASS", original_parameters_and_returns_preserved=True,
                            GP_XMM_full_MXCSR_replay_preserved=True)
            report["accepted_records"] = b.stats()["accepted"]
            report["status"] = "PASS"
        # OwnedBridge keeps its allocation list as evidence after close; a
        # successful context exit means every registered table was removed
        # and each listed owned allocation was VirtualFree'd exactly once.
        report["owned_allocations_released"] = b.closed
        report["released_allocation_count"] = len(b._allocations)
    except Exception as error:
        report.update(status="FAIL", first_failure_case=current,
                      first_failure=f"{type(error).__name__}: {error}")
    report["elapsed_ms"] = (time.perf_counter() - started) * 1000
    out = destination / "report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]),
                      "report": str(out), "first_failure": report.get("first_failure")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
