# 生涯战斗明细记录

`src/combat-records.lua` 保存本人的武器／战备来源击杀、敌人种类击杀和死亡观察。模块不读游戏内存，不更改账单、击杀统计或绶带；调用方在 `revision` 改变时持久化 `snapshot()`。

## 初始化与保存

```lua
local records = create({
    saved = store:get('combat_records_v1'),
    clock = os.time,
    weapon_catalog = CAREER_WEAPON_CATALOG,
    enemy_catalog = ENEMY_TYPES,
    legacy = store:get('last_mission'),
    history = mission_history:entries(),
})
records:observe(state)
-- revision 改变后才保存；snapshot 与内部状态隔离。
store:set('combat_records_v1', records:snapshot())
```

快照版本为 `1`：`{version=1, entries={...}, death_records={...}}`。每个 `sequence` 保存 `kills/deaths` 与 `weapon_stats`、`unit_kills` 各自已经观察到的最大计数。轮询、数值回退、重启或重复导入都不会再次累加同一计数。相同武器的多个已证明来源类型按目录的规范 `id` 汇总。

正常结束和中途返舰都保存该局；进程中断仅标记 `interrupted`，不伪造结束时间。没有自动删除或静默裁剪历史的数量上限。旧记录仅恢复实际存在的字段；缺失来源显示“未记录的旧击杀”，没有日期的旧记录不使用当前时间补填。重新加载保存的快照后，调用同一 `query` API 即可查看。

## 分类依据

`tools/career-catalogs.py` 的 `build_catalogs(integration, sdk)` 返回：

```text
{version, weapon_catalog, inputs, unknown_source_types, policy}
```

`integration` 是现有 `docs/integration-catalogs.json` 的字典，`sdk` 是包含 `PlayerWeaponAuthoringCapabilities.json` 和 `SupportWeaponCapabilities.json` 的目录路径。构建器嵌入 `result['weapon_catalog']`。

分类依据是 SDK 的来源资源哈希或唯一、完全一致的目录英文身份，再读取其 `slot`。投掷物和战备可使用现有 Runtime 来源目录的明确 `kind`。不根据名称前缀、当前手持武器或武器数字猜测槽位。无法证明的槽位保持 `unknown`。数据输入的 SHA-256 保留在返回的 `inputs` 中。

## 查询合同

`query(view, filters)` 支持 `weapons`、`enemies`、`deaths`。`filters` 包括：

- `period=all/24h/7d/30d`，`query`、`sort=kills/name`。
- 武器：`role=primary/secondary/support/throwable/stratagem/unknown/all`，中文 `weapon_type`。
- 敌人：`faction=bugs/bots/illuminate/unknown/all`，中文 `size`（包括中型精英和 BOSS）。
- 死亡：`category=enemy/player/self/environment/unknown/all`、`mode=rank/recent`。
- `focus_id` 可限制关联查询的目标，`now` 可指定 Unix 秒供离线测试；通常使用初始化的 `clock`。

返回 `{view,rows,totals,coverage,available_weapon_types}`。相同 `revision + filters + floor(now)` 返回同一只读表；下一秒或数据变化时清理查询缓存，避免生涯页每帧重新聚合。

武器和敌人行包括 `id/name/category/weapon_type?/faction?/size?/kills/unknown_kills/detail_rows`。`available_weapon_types` 根据槽位筛选，独立于文本搜索和当前子分类，供界面稳定显示筛选选项。

**武器来源统计与敌人统计是两条独立数据。当前没有逐敌人的武器关联证据。** `totals.linked_kills=0`、`coverage.per_victim_weapon=false`，明细只生成 `known=false` 的未知关联行。不能把两边的数值、时间或数量强行配对，也不再次叠加 Runtime 的来源批次，避免重复。

时间筛选以对局结束时间、已有开始时间或本模块首次观察时间为准，统计的是所选对局，非逐发或逐次击杀时间。没有时间的旧局仅纳入“全部”，在 `coverage.unknown_time_kills/deaths` 保留数量。

## 死亡与队友身份

`record_death(row)` 接收实际观察的条目，要求稳定的字符串 `id`、正整数 `sequence`；同一对局同一 `id` 幂等。发生时间 `occurred_at` 使用 Unix 秒；不以打开界面的时间回填死亡时间。

规范记录保留：

```text
id, source_id, sequence, occurred_at?, mission_elapsed?,
category, actor_name, weapon_name?, damage_kind?, confidence,
observed?, death_index?, event?, evidence?, evidence_text?, player?, victim?
```

`player` 是攻击来源玩家，`victim` 是本人，身份快照使用相同字段：`name/callsign/slot/slot_index/peer_id/persona_index/avatar_id/identity_scope/identity_source`。`slot` 是显示用的 1–4，`slot_index` 保留原生 0–3。`peer_id` 始终是精确的 16 位十六进制字符串；它是会话通信标识，不是 Steam、PSN 或永久游戏账号。模块不生成平台主页链接或永久账号字段。

结构化 `evidence` 仅保留明确的普通值字段：`death_observed`、`runtime_death_event`、`native_death_counter`、`death_index`、`native_fatal_event_proven`、`weapon_source_proven`、`damage_kind_proven`、`source_channel`、`source_reason`、`used_downing_source`、`actor_type_hash`。其中 `false` 证明标志完整保存。`evidence_text` 提供界面短说明；不保存地址、指针或任意原始内存对象。

排名的队友友伤统一归为“队友”，自身统一归为“自身”，不同参与者不拆出独立排行榜；详情保留各自的姓名、呼号和会话标识。搜索覆盖名称、武器、伤害方式、呼号、peer、记录／事件 ID、对局序号和观察通道。来源推断不用于自动判定恶意。

死亡排名行是 `{id,name,category,count,records}`；近期列表直接返回规范记录，并提供 `at/match/actor/weapon/attack` 兼容别名。`totals.deaths` 保留所选时段的原生阵亡总数，`totals.recorded_deaths` 是筛选后实际记录数；缺失旧死因数量放在 `coverage.unrecorded_deaths`，不会伪造逐条死亡。

## 离线验证

`tests/test_combat_records.lua` 使用游戏自带 LuaJIT，覆盖单调计数、来源别名合并、重启与迁移幂等、中途返舰、旧字段缺失、时段和分类筛选、缓存、结构化死亡证据、精确 peer 字符串、队友归组、呼号／序号搜索以及 501 场不裁剪。测试不读取游戏进程或真实账户；实战来源准确性仍须单独验收。
