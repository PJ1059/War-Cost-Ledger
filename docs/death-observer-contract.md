# 0.4.61 扩展

本接口已增加按帧 `sample_damage(now, context)`、最终完整伤害机制、具体武器／载具来源及附近同时死亡推测。新行为与预算详见 [0.4.61死因说明](death-causes-0.4.61.md)。下文旧版限制与测试数仅作历史，不代表当前实现。

# 本人死亡、来源推断与玩家快照 · 0.4.40 候选

本实现独立使用 HD2Runtime 0.30.3 的公开事件与数据布局，不复制 DeathSourceNotice 的 Lua、评分、名称表或资产。候选已通过离线测试，真实游戏的来源覆盖与姓名显示仍待验证。

## 已证明的输入

- 官方 `player_died` 提供本地标志、peer、avatar ID 和 `observed=dead_state/avatar_removed`，没有具体致死武器。事件由调用方订阅并传给观察器。
- 官方 `player_damaged` 提供一次统计 tick 的总健康损失和最后 `attacker_peer`，没有逐弹、逐敌人或原生 fatal 事件保证。
- `domains/event_natives.lua`：Health record 长 440B，lastOwner `+0x30`、lastCreditor `+0x38`、downOwner `+0x44`、downCreditor `+0x50`、life `+0x19C`。原生 ApplyDamage 存储指令 pins 和死亡状态比较经核对；这些是最近伤害／倒地来源，不自动等于致死来源。
- 姓名链沿用本项目已观察的 roster `game+0x347CED8`，每条 `0xC0`、peer 在 `+0`、名字从 `+8` 起，最多 64B。persona 链为 `game+0x347CEF0` 的内联表，count `+0x16390`、rows `+0x16398`、stride 32、index `+0x14`，有原生 HUD 按 peer 查表的指令 pin。与 Runtime 当时的四人列表按完整 peer 关联，进行双读复核，不用列表位置推断身份。

上游参考：`runtime/event_sources.lua` 的 players/health source、`runtime/event_world.lua` 的 Health 与 entity descriptor 读取、`docs/events.md`、`docs/event-scripting.md`。固定版本为 `dcd996daca2573443956c07252c55c2d86dd0320`。

## 模块接口

```lua
local native_reader = make_native_death_reader({world_api = world_api})
local deaths = make_death_observer({
    reader = native_reader,
    catalog = ENEMY_TYPES,
    source_names = SOURCE_NAMES,
})

deaths:on_damaged(event, context)
deaths:on_died(event, context)
deaths:step(now, world, game, players, context)
local new_records = deaths:take_records()
```

`native_reader:read(world, avatar)` 返回该完整 avatar 的 Health 来源快照；`native_reader:players(world, players)` 返回当时的名字和 persona 快照。两者均只读，读取上限 96 次／4096B、每次读取前检查 2ms 软预算；最多 32 个散列表探测，没有全场扫描、写入、原生调用、按键模拟或新线程。单次系统读取不可中断，不将预算视为帧率保证。

`context` 为 `{sequence, now, world, occurred_at, mission_elapsed, local_peer, avatar, players, death_index?, skip_attribution?}`。`occurred_at` 是可缺失的 Unix 秒，不能传显示日期字符串；`mission_elapsed` 是本任务已过秒数。

调用方在同一个主观察周期中提供 context。官方事件应立即传入当时的 context，不填写上一次统计的 `death_index`；原生累计死亡计数的新增值以 `observed='native_death_counter'` 补录，并填写新的正整数 `death_index`。首次读到的累计值只建立基线，不伪造以前未采集的逐次死亡。如果一次跳增多次，传 `skip_attribution=true`，不能把最后一个 Health 来源套给多条死亡。

同序号优先去重，另按本局／完整 peer／完整 avatar 关联事件与计数。事件先到或计数先到，待结算条目都可以补绑定另一路证据；每条只输出一次。只订阅／转发 `player_died` 和 `player_damaged`，不要把 `entity_died` 再当第二条本人死亡。

最多保留 16 条尚未配对的事件／计数条目，包含已经输出的条目。计数迟到时按同局、完整 peer 和事件先后顺序关联，已输出条目不再输出第二次，也不再从复活身体读取来源。只有计数、没有事件且当前 avatar 的 Health 不是死亡状态时，来源保持未知，清除未经证明的 victim.avatar_id；后来也不再取复活身体的来源。已观察到仍存活的替代身体，不会被认作这次计数所指的死者。

等待 0.5 秒后，仅重新读取原死亡 avatar 一次；不改为读取复活后当前 avatar。若死亡后的 owner、creditor 或 victim 类型与死亡当时已经存在的身份冲突，保留未知，不能把后来攻击尸体的人替换成死亡来源。进入舰船或序号改变时，`step` 立即输出旧序号尚待结算的条目，不需要在舰船继续等。新任务调用 `reset()` 前须先执行该结清步骤。`reset()` 明确清空本观察器状态；`take_records()` 消费已完成输出，不生成额外死亡。

## 输出与身份语义

每条为 `{id, sequence, occurred_at?, mission_elapsed?, category, actor_name?, confidence, player?, victim, evidence}`。category 为 enemy/player/self/environment/unknown，confidence 只有 inferred/low/unknown；没有已确认致死来源级别。武器、伤害类别、Steam／PSN 永久账号 ID 未获证明，保留未知，不拿当前持枪替代。

`player` 是攻击来源玩家，`victim` 是本人；两者只保存当时的 `{name?,callsign?,slot?,slot_index?,peer_id?,persona_index?,avatar_id?,identity_scope,identity_source?}`。`slot` 为显示用 1–4，`slot_index` 保留 Runtime 列表原始 0–3，persona_index 为原生 0–3。列表槽位和 persona 都可能改变。没有证明原生 callsign 文本，默认缺失；不把 persona 数字自动叫作 P1–P4。`peer_id` 是会话 peer，不是可跨局复用的 Steam／PSN 身份。

身份在伤害事件或死亡事件发生时冻结。延时期间即使有人改名、换位、离队、加入，也不从后来同一 P 槽填充旧条目。伤害事件已有的攻击者快照优先于之后的名字；不知道名字时就保留未知。

`evidence` 是有界纯数据表，不能转换成字符串后丢掉：

```text
death_observed, runtime_death_event, native_death_counter, death_index?,
native_fatal_event_proven=false, weapon_source_proven=false,
damage_kind_proven=false, source_channel?, source_reason?,
used_downing_source?, actor_type_hash?
```

不保存内存指针、存活对象或当前账号接口；交给历史模块的是独立副本。

## 来源推断及局限

Health owner 与 creditor 同当时 roster 的完整 peer/avatar 一致时可给出玩家／自身来源；可信敌人类型可给出敌人名称。若最近 1.5 秒还有一致的玩家伤害事件，来源 confidence 可为 inferred；仅有 Health 或最近伤害归属为 low。相互冲突的玩家与敌人证据保留 unknown。没有 creditor 不等于摔死或其他环境死因；只有明确的环境类型目录事实才允许 environment。

Health 只保存最近伤害来源，可能陈旧；事件伤害也是同 tick 汇总。无精确致死武器、伤害种类／元素、命中部件或明确的致死伤害队列。本切片不做爆炸空间猜测。尸体已移除、预算中断、读取失败、未映射敌人、旧历史未采集，都可能留下未知来源，但仍保留死亡本身。

pending 上限 16、一次待消费输出上限 128、每任务关联身份上限 1024；超限计入 diagnostics.dropped，原生总死亡统计不受影响。累计死亡与逐条已记录数量的差额由 UI 如实显示为未记录，不能倒填。

## 离线验证

`tests/test_death_observer.lua`：29 个行为用例，覆盖事件／计数去重、延时同 avatar、姓名／slot／persona 冻结、改名离队、不误认武器、未知／冲突、计数缺口、返舰及换序号结清、死亡后来源／身份变化、已输出事件的迟到计数、复活后计数、无身体计数与迟到事件、容量和消费。

`tests/test_native_death_reader.lua`：10 个真实 Runtime 数据域的 owned-memory 用例，覆盖 Health 字段、完整代际、descriptor、名字／persona、槽位调整、编码、竞态、pin 与预算。正常 Health 34 次读取／1379B，roster 23 次／831B。测试仅在游戏自带 LuaJIT 中运行已构造的本地字节夹具，没有访问真实游戏或账号。
