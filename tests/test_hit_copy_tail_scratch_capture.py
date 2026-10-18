"""One fixed-reader fixture group; all process/memory/time operations are fake."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import test_flow_exe_entry_code_capture as fixture

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "owned_tail_scratch_capture", ROOT / "tools/hit-copy-tail-scratch-capture.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class Memory(fixture.Memory):
    def __init__(self, locator, layouts, change=None):
        super().__init__(state=3, after=3)
        self.change, self.arena_reads = change, 0
        self.wrapper = self.game + 0x10000000
        self.package = self.wrapper + 0x100000
        self.bridge = self.package + 0x20000
        self.arena = self.bridge + capture.ARENA_DELTA
        self.header = (ROOT / "dist/hit-contact-registration-source-20261013/game-pe-header.bin").read_bytes()
        self.directory = (locator.SOURCE / "original-export.bin").read_bytes()
        self.locator = locator
        self.regions = [(self.wrapper, 0xB000, 0x20),
                        (self.wrapper + 0xC000, 0x1000, 4),
                        (self.package, 0x10000, 0x20),
                        (self.bridge, 0x20000, 4)]
        keys = {name: self.package + at for name, (at, _) in layouts.items()}
        keys.update(arena=self.arena, bridge=self.bridge,
                    current_user_global=self.game + 0x347CEF0,
                    entity_manager_global=self.game + 0x346BF98)
        self.segments = {
            self.game + capture.SLOT_RVA: struct.pack("<Q", self.wrapper),
            self.wrapper: bytes.fromhex("f048ff05") + struct.pack("<i", 0xC000 - 8)
                + bytes.fromhex("ff25") + struct.pack("<i", 0xC008 - 14),
            self.wrapper + 0xC000: struct.pack("<QQ", 123, self.wrapper + 0x100),
            self.wrapper + 0xA604: b"\xE8" + struct.pack(
                "<i", keys["physical_success"] - (self.wrapper + 0xA604 + 5)),
        }
        for name in ("physical_success", "tail_diagnostic"):
            entry = layouts[name][1]
            raw = bytearray.fromhex(entry["code_hex"])
            for r in entry["relocations"]:
                struct.pack_into("<Q", raw, r["offset"], keys[r["address_key"]] + r.get("addend", 0))
            if name == "physical_success" and change == "gateway_bytes":
                raw[0] ^= 1
            if name == "physical_success" and change == "gateway_literal":
                rel = next(r for r in entry["relocations"] if r["address_key"] == "tail_diagnostic")
                struct.pack_into("<Q", raw, rel["offset"], keys["tail_diagnostic"] + 16)
            self.segments[keys[name]] = bytes(raw)
        arena = bytearray(64 + 32 * 640)
        struct.pack_into("<IIQQQQIIQII", arena, 0,
                         32, 640, capture.EPOCH, capture.PEER, 300, 0,
                         0, 0, self.arena + 64, 0, 4)
        struct.pack_into("<QQIIQ", arena, 64 + 128, 16, 485, 0, 0, capture.EPOCH)
        for i, flags in enumerate((0x0B, 0x4B, 0x10B, 0x14B)):
            row = 64 + i * 640
            struct.pack_into("<IIQII", arena, row + 96,
                             700 + i, 3, self.context + i * 0x100, 1, 0)
            scratch = row + 160
            struct.pack_into("<QQ", arena, scratch + 8, capture.EPOCH, capture.PEER)
            struct.pack_into("<I", arena, scratch + 36, 3)
            struct.pack_into("<III", arena, scratch + 44, 1001, 1002, 71)
            struct.pack_into("<I", arena, scratch + 60, 3)
            struct.pack_into("<II", arena, scratch + 84, int(bool(flags & 0x40)), flags)
        self.segments[self.arena] = bytes(arena)
        bridge = bytearray(64)
        struct.pack_into("<IIQQIIIIQQQ", bridge, 0,
                         1, 1024, capture.EPOCH, capture.PEER, 0, 0, 0, 0, 232, 0, 10)
        self.segments[self.bridge] = bytes(bridge)

    def query(self, address):
        for base, size, protect in self.regions:
            if base <= address < base + size:
                self.queries.append(address)
                return dict(base=base, size=size, state=0x1000,
                            type=0x20000, protect=protect)
        if address == self.game + self.locator.TARGET_RVA:
            self.queries.append(address)
            return dict(base=self.game, size=self.locator.IMAGE_SIZE,
                        state=0x1000, type=0x1000000, protect=0x20)
        return super().query(address)

    def read(self, address, size):
        rva = address - self.game
        special = {0: self.header, self.locator.EXPORT_RVA: self.directory,
                   self.locator.TARGET_RVA: bytes.fromhex("85c90f85a2000000488d0581f6ffff48")}
        if rva in special:
            self.reads.append((address, size)); raw = special[rva]
            assert len(raw) == size
            return raw
        for start, raw in self.segments.items():
            if start <= address < address + size <= start + len(raw):
                self.reads.append((address, size))
                at = address - start; result = bytearray(raw[at:at + size])
                if address == self.arena and size == 64:
                    self.arena_reads += 1
                    if self.change == "post_epoch" and self.arena_reads > 1:
                        struct.pack_into("<Q", result, 8, capture.EPOCH + 1)
                return bytes(result)
        return super().read(address, size)


class Scenario(fixture.Scenario):
    def __init__(self, locator, layouts, change=None):
        super().__init__()
        self.memory = Memory(locator, layouts, change)
        self.change, self.creation_queries = change, 0

    def dependencies(self):
        deps = super().dependencies()
        def start_time(process):
            assert process is self.memory
            self.creation_queries += 1
            return 0x123456789 + int(self.change == "start_time" and self.creation_queries > 1)
        deps["start_time"] = start_time
        return deps


class TailScratchCaptureTests(unittest.TestCase):
    def test_one_fixed_fake_reader_group(self):
        locator, _, layouts = capture.source()
        cases = [(None, None), ("gateway_bytes", "TAIL_SCRATCH_ENTRY_BYTES"),
                 ("gateway_literal", "TAIL_SCRATCH_ENTRY_LITERAL"),
                 ("post_epoch", "TAIL_SCRATCH_ARENA_IDENTITY"),
                 ("start_time", "TAIL_SCRATCH_SOURCE_PHASE_STARTTIME_CHANGED")]
        with patch.object(capture, "EXPECTED_PID", 54321):
            for change, reason in cases:
                with self.subTest(change=change), tempfile.TemporaryDirectory() as parent:
                    s = Scenario(locator, layouts, change); folder = Path(parent) / "capture"
                    if reason:
                        with self.assertRaisesRegex(ValueError, reason):
                            capture.run(folder, s.dependencies(), clock=fixture.Clock())
                        self.assertEqual(list(folder.glob("*.bin")), [])
                        evidence = json.loads((folder / "scratch.incomplete.json").read_text("utf8"))
                        self.assertFalse(evidence["partial_binary_saved"])
                    else:
                        status = capture.run(folder, s.dependencies(), clock=fixture.Clock())
                        evidence = json.loads(Path(status["json_path"]).read_text("utf8"))
                        raw = Path(status["binary_path"]).read_bytes()
                        self.assertEqual(len(raw), 33280)
                        self.assertEqual(evidence["binary_sha256"], hashlib.sha256(raw).hexdigest())
                        self.assertEqual(len(evidence["ranges"]), 16)
                        self.assertEqual(evidence["diagnostic_claimed_before"], 0)
                        self.assertEqual(evidence["diagnostic_claimed_after"], 0)
                        for sample in evidence["interpretation"]["samples"]:
                            self.assertEqual(len(sample["rows"]), 32)
                            self.assertEqual([r["stage"] for r in sample["rows"][:4]],
                                ["enemy_and_source_not_admitted", "enemy_only",
                                 "source_only", "enemy_and_source_admitted"])
                        self.assertEqual(evidence["budget"]["io_calls"], 90)
                        self.assertEqual(evidence["budget"]["bytes_requested"], 45226)
                        self.assertEqual(s.creation_queries, 2)
                    budget = evidence["budget"]
                    self.assertEqual(budget["read_calls"], len(s.memory.reads))
                    self.assertEqual(budget["query_calls"], len(s.memory.queries) + s.creation_queries)
                    self.assertEqual(budget["bytes_requested"], sum(n for _, n in s.memory.reads))
                    self.assertLessEqual(budget["io_calls"], 96)
                    self.assertLessEqual(budget["bytes_requested"], 48 * 1024)
                    self.assertFalse(evidence["native_called"])
                    self.assertFalse(evidence["native_written"])
                    self.assertTrue(s.memory.closed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
