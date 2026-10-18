"""Build/check the reviewed native fire-source whitelist; never reads a running game.

From war-cost-ledger: python -B tools/research-fire-sources.py --check
Inputs are the pinned HD2Runtime SDK/catalog and matching Filediver datalibrary.
Only docs/fire-sources.json is written without --check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
COMMIT = "dcd996daca2573443956c07252c55c2d86dd0320"
RUNTIME_DEFAULT = (Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
                   / "Temp/hd2-integration-research/HD2Runtime/SkyeShade-HD2Runtime-dcd996d")
DL_DEFAULT = PROJECT.parent / "spore-map/vendor/filediver/datalibrary"
OUTPUT = PROJECT / "docs/fire-sources.json"
INPUTS = ["domains/event_entities.lua", "sdk/StatusEffectCatalog.json",
          "sdk/PlayerWeaponAuthoringCapabilities.json", "sdk/SupportWeaponCapabilities.json",
          "sdk/ThrowableAuthoringCapabilities.json", "schemas/stratagem_authoring_catalog.json",
          "schemas/build_profile.json"]
FIRE_IDS = {"fire", "burning_heavy"}
FIRE_TYPES = {5: "fire", 32: "burning_heavy"}  # Pinned current-build status identities, not old enums.
LASER_POLICY_NAMES = {"LAS-5 Scythe", "LAS-7 Dagger", "LAS-98 Laser Cannon", "Orbital Laser",
                      "A/LAS-98 Laser Sentry"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def normal(value: str) -> str:
    return f"{int(value, 16):016X}"


def status_nodes(value, pointer="", view=None):
    """Keep actual typed status records; names containing 'flam' never select a source."""
    out = []
    if isinstance(value, dict):
        if value.get("kind") == "StatusEffectSettings" and value.get("recordType") in FIRE_TYPES:
            out.append({"pointer": pointer, "status_type": value["recordType"],
                        "status": FIRE_TYPES[value["recordType"]],
                        "parent_damage_type": value.get("parentDamageType")})
        if value.get("kind") == "DamageInfo" and value.get("recordType") is not None and view is not None:
            group = view.settings_table("damage").groups[value["group"]]
            rows = group.row_for_type(value["recordType"])
            if len(rows) != 1:
                raise ValueError("Ambiguous native DamageInfo record")
            row, body = rows[0]
            for slot in range(4):
                kind, strength = struct.unpack_from("<If", body, 44 + 8 * slot)
                if kind in FIRE_TYPES and strength > 0:
                    out.append({"pointer": pointer, "status_type": kind, "status": FIRE_TYPES[kind],
                                "native_damage_type": value["recordType"], "native_damage_row": row,
                                "slot": slot + 1, "strength": strength})
        for key, child in value.items():
            out.extend(status_nodes(child, pointer + "/" + str(key), view))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            out.extend(status_nodes(child, pointer + "/" + str(index), view))
    return out


def build(runtime: Path, datalibrary: Path) -> dict:
    sys.path.insert(0, str(runtime / "scripts"))
    from migration.build_view import from_datalibrary
    view = from_datalibrary(datalibrary, {})
    profile = json.loads((runtime / "schemas/build_profile.json").read_text(encoding="utf-8"))
    pinned = profile["builds"][profile["active"]]
    for key in ["entitiesSha256", "typelibSha256"]:
        if view.build[key] != pinned["datalibrary"][key].upper():
            raise ValueError("Datalibrary fingerprint differs: " + key)
    data = {name: json.loads((runtime / name).read_text(encoding="utf-8"))
            for name in INPUTS if name.endswith(".json")}
    raw = (runtime / INPUTS[0]).read_text(encoding="utf-8")
    tail = raw.split('["sources"]=', 1)[1].split(',["summary"]=', 1)[0]
    pattern = r'\["([0-9A-F]{16})"\]=\{\["name"\]="((?:\\.|[^"\\])*)",\["kind"\]="([^"]+)"\}'
    catalog = {h: {"name": json.loads('"' + n + '"'), "kind": k}
               for h, n, k in re.findall(pattern, tail)}
    declared_count = re.search(r'\["sources"\]=(\d+)', raw.split('["summary"]=', 1)[1])
    if not declared_count or len(catalog) != int(declared_count[1]):
        raise ValueError("Unexpected generated source catalog syntax/count")
    components = view.resource_components()
    sources, excluded, uncovered = {}, {}, []

    def exclude(h, name, reason):
        excluded[h] = {"type": h, "name": name, "reason": reason}

    def add(h, name, domain, evidence):
        h = normal(h)
        if int(h, 16) not in view.entity_rows:
            raise ValueError("Source resource absent from pinned entities: " + h)
        entry = sources.setdefault(h, {"type": h, "name": name, "aliases": [], "domains": [],
                                      "runtime_source_name": catalog.get(h, {}).get("name"),
                                      "evidence": [], "live_source_attribution": "not_tested"})
        if name != entry["name"] and name not in entry["aliases"]:
            entry["aliases"].append(name)
        if domain not in entry["domains"]:
            entry["domains"].append(domain)
        if evidence not in entry["evidence"]:
            entry["evidence"].append(evidence)

    status_catalog = data["sdk/StatusEffectCatalog.json"]
    appliers = {}
    for status in status_catalog["statuses"]:
        if status["semanticId"] not in FIRE_IDS:
            continue
        for owner in status["appliedBy"]:
            appliers.setdefault((owner["domain"], owner["object"]), []).append(status["semanticId"])
    player_catalog = data["sdk/PlayerWeaponAuthoringCapabilities.json"]
    players = {x["name"]: x for x in player_catalog["weapons"]}
    support = {x["catalogIdentity"]: x for x in data["sdk/SupportWeaponCapabilities.json"]["weapons"].values()}
    throwables = {x["name"]: x for x in data["sdk/ThrowableAuthoringCapabilities.json"]["throwables"]}
    stratagems = data["schemas/stratagem_authoring_catalog.json"]["stratagems"]
    payload_owners = {}
    for name, value in stratagems.items():
        for resource in (value.get("root") or {}).get("payloads", []):
            payload_owners.setdefault(normal(resource), set()).add(name)

    for (domain, name), statuses in sorted(appliers.items()):
        common = {"artifact": "sdk/StatusEffectCatalog.json", "object": name, "statuses": sorted(statuses)}
        if domain == "player_weapon_authoring":
            weapon = players[name]
            proof = [{"field": f["semanticFieldId"], "status": f["currentDefault"], "backing": f["backing"]}
                     for f in weapon["fields"] if f["semanticFieldId"].startswith("damage.status_")
                     and f["currentDefault"] in FIRE_IDS]
            if not proof:
                raise ValueError("No native fire slot for player weapon: " + name)
            for resource in weapon["resources"]:
                add(resource, name, domain, dict(common, attack_artifact="sdk/PlayerWeaponAuthoringCapabilities.json",
                                                native_slots=proof))
        elif domain == "support_weapon_authoring":
            weapon = support[name]
            for resource in weapon["resourceHashes"]:
                proof = [{"role": a["role"], "kind": a["kind"], "damage_info": a.get("damageInfo"),
                          "status_effects": a["statusEffects"]} for a in weapon["runtimeAttacks"]
                         if normal(a["resourceHash"]) == normal(resource)
                         and any(s["type"] in FIRE_TYPES for s in a.get("statusEffects", []))]
                if not proof:
                    raise ValueError("No native fire attack for support variant: " + resource)
                add(resource, name, domain, dict(common, attack_artifact="sdk/SupportWeaponCapabilities.json",
                                                native_attacks=proof))
        elif domain == "throwable_authoring":
            matches = [h for h, value in catalog.items() if value["name"] == name and value["kind"] == "throwable"]
            if not matches or name not in throwables:
                raise ValueError("Throwable source/definition missing: " + name)
            for h in matches:
                add(h, name, domain, dict(common, identity=throwables[name]["identity"]))
        elif domain == "stratagem_authoring":
            value = stratagems[name]
            proof = status_nodes(value, view=view)
            if not proof:
                raise ValueError("No typed fire status in stratagem graph: " + name)
            for resource in value["root"]["payloads"]:
                h = normal(resource)
                if len(payload_owners[h]) > 1:
                    exclude(h, " / ".join(sorted(payload_owners[h])), "共享 payload，不能由来源 type 唯一确认燃烧战备。")
                    continue
                if "HellpodRackComponentData" in components.get(int(h, 16), []):
                    exclude(h, name, "仅投送舱/装备架；不把投送舱砸死计入燃烧来源。")
                    continue
                add(h, name, domain, dict(common, attack_artifact="schemas/stratagem_authoring_catalog.json",
                                         root=value["root"], native_status_nodes=proof))
        else:
            uncovered.append({"name": name, "domain": domain, "statuses": statuses,
                              "reason": "载具挂载武器存在燃烧定义，但逐来源 type 与该挂载的对应未实测；不把整车或其他挂载击杀算入。"})

    # Thermite's burn is a native timed template, not a DamageInfo status slot.
    thermite = throwables["G-123 Thermite"]
    timed = [x for x in thermite["blocked"] if "Fire" in x.get("nativeStatusTypes", [])
             and "Thermite" in x.get("nativeStatusTypes", [])]
    if len(timed) != 1:
        raise ValueError("Thermite native timed-burn evidence missing")
    for h, value in catalog.items():
        if value["name"] == thermite["name"] and value["kind"] == "throwable":
            add(h, thermite["name"], "throwable_authoring", {
                "artifact": "sdk/ThrowableAuthoringCapabilities.json", "object": thermite["name"],
                "native_timed_status_template": timed[0], "identity": thermite["identity"]})

    # Underbarrels are separate weapon entities. Validate the actual typed spray->damage->status chain.
    for weapon in player_catalog["subweapons"]:
        if "SprayWeapon" not in weapon["implementationFamilies"]:
            continue
        for resource in weapon["resources"]:
            record = view.record("SprayWeaponComponentData", int(resource, 16))
            damage_type = struct.unpack_from("<I", record["bytes"], 200)[0]
            rows = view.settings_table("damage").row_for_type(damage_type)
            if len(rows) != 1:
                raise ValueError("Ambiguous underbarrel DamageInfo")
            row, body = rows[0]
            slots = [{"type": struct.unpack_from("<I", body, 44 + 8 * i)[0],
                      "strength": struct.unpack_from("<f", body, 48 + 8 * i)[0]} for i in range(4)]
            if not any(x["type"] in FIRE_TYPES for x in slots):
                continue
            add(resource, weapon["name"], "player_subweapon", {
                "artifact": "sdk/PlayerWeaponAuthoringCapabilities.json", "link": weapon["link"],
                "spray_component_row": record["recordIndex"], "damage_type_member_offset": 200,
                "damage_info_type": damage_type, "damage_row": row, "status_slots": slots,
                "note": "独立下挂资源；未验证游戏是否始终以此 type 记账，不纳入母枪普通子弹。"})

    # Names inherited from a dedicated call-in must not promote the delivery pod itself.
    fire_names = {entry["name"] for entry in sources.values()}
    for h, value in catalog.items():
        if value["name"] in fire_names and "HellpodRackComponentData" in components.get(int(h, 16), []):
            exclude(h, value["name"], "Runtime 将独占投送 payload 命名为装备；此实体只有投送架，不是燃烧武器。")
    eagle = stratagems["Eagle Airstrike"]
    if status_nodes(eagle, view=view):
        raise ValueError("Ordinary Eagle Airstrike unexpectedly has a fire slot")
    for resource in eagle["root"]["payloads"]:
        exclude(normal(resource), "Eagle Airstrike", "普通高爆飞鹰空袭；实际攻击图没有 fire/burning_heavy 状态，不视为凝固汽油弹空袭。")
    parent = players["SMG/FLAM-34 Stoker"]
    for resource in parent["resources"]:
        exclude(normal(resource), parent["name"], "母枪普通子弹不属于火焰；只候选独立下挂喷射武器 type。")
    if set(sources) & set(excluded):
        raise ValueError("Included/excluded source overlap")
    optional = []
    for h, entry in list(sources.items()):
        if entry["name"] in LASER_POLICY_NAMES or set(entry["aliases"]) & LASER_POLICY_NAMES:
            entry["exclusion_reason"] = "原生定义会点燃，但本项目默认仅计火焰武器/燃烧弹/燃烧战备；一般激光来源全部击杀不纳入。"
            entry["source_category"] = "burning_laser_optional"
            optional.append(entry)
            del sources[h]
        elif "player_subweapon" in entry["domains"]:
            entry["source_category"] = "flame_underbarrel"
        elif "throwable_authoring" in entry["domains"]:
            entry["source_category"] = "incendiary_throwable"
        elif entry["name"] == "A/FLAM-40 Flame Sentry":
            entry["source_category"] = "flame_sentry"
        elif "stratagem_authoring" in entry["domains"]:
            entry["source_category"] = "incendiary_stratagem"
        elif "SprayWeaponComponentData" in components.get(int(h, 16), []):
            entry["source_category"] = "flame_weapon"
        else:
            entry["source_category"] = "incendiary_ammunition"
    for entry in sources.values():
        entry["aliases"].sort()
        entry["domains"].sort()
    return {
        "schema_version": 1, "runtime_version": "0.30.3", "runtime_commit": COMMIT,
        "rule": "按游戏原生 dealt_kills 来源 type 计为燃烧来源击杀；包含该来源的直击、爆炸和持续燃烧归属击杀。",
        "policy": {"include_laser_sources": False,
                   "basis": "火焰武器/燃烧弹/燃烧战备来源；仅有点燃状态的普通激光来源另列可选，不默认计入。"},
        "build": {"exe_sha256": pinned["exeSha256"], "game_dll_sha256": pinned["gameDllSha256"],
                  "entities_sha256": view.build["entitiesSha256"], "typelib_sha256": view.build["typelibSha256"]},
        "source_types": sorted(sources), "sources": [sources[h] for h in sorted(sources)],
        "optional_excluded_by_policy": sorted(optional, key=lambda x: x["type"]),
        "excluded": [excluded[h] for h in sorted(excluded)], "uncovered": uncovered + [
            {"name": "unattributed / unknown / shared payload", "reason": "原生无来源部分及未证明的来源不归给火焰；不根据显示名字或当前手持武器补猜。"},
            {"name": "独立地雷、地面火焰/状态实体及自定义弹药", "reason": "仅当原生 kills 记到已验证 type 才计入；其独立来源 hash 和 MOD 改写后的武器状态未做完整实机枚举。"}],
        "limitations": [
            "这是来源击杀口径，不能称为严格烧死；激光类虽有原生 fire 定义，但按项目政策默认排除。",
            "sources 是按来源累计的击杀，没有死者 type；仅此表不能可靠判断燃烧来源杀了巨型或强袭虫。",
            "SDK/原生数据验证通过不代表每个变体已在实机产生该 source type；特别是未命名下挂武器仍需实测。",
            "不读取游戏进程、不启动游戏、不修改 Runtime/部署；只生成此目录。"],
        "evidence_artifacts": [{"path": name, "sha256": sha(runtime / name)} for name in INPUTS],
        "summary": {"included_source_types": len(sources), "excluded_source_types": len(excluded),
                    "optional_laser_source_types": len(optional),
                    "unnamed_in_runtime": [h for h in sorted(sources) if sources[h]["runtime_source_name"] is None],
                    "live_verified": False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=RUNTIME_DEFAULT)
    parser.add_argument("--datalibrary", type=Path, default=DL_DEFAULT)
    parser.add_argument("--check", action="store_true", help="Verify the saved JSON without writing it")
    args = parser.parse_args()
    value = build(args.runtime_root.resolve(), args.datalibrary.resolve())
    body = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != body:
            raise SystemExit("FAIL: docs/fire-sources.json differs from pinned evidence")
    else:
        OUTPUT.write_text(body, encoding="utf-8", newline="\n")
    print(json.dumps(dict(status="PASS", mode="check" if args.check else "generate", **value["summary"])))


if __name__ == "__main__":
    main()
