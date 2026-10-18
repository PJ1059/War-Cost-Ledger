# 逐次命中原生读取 · 2026-10-12

## 当前证据：找到另一个保留装甲倍率的队列

2026-10-12续查补正：真实ProduceDamage声明片段证明旧0x70 DamageEvent的`+38`也保存最终DamageValues+04装甲倍率bits（129E4DE/129E4E1），不是只有queue6保留factor。`+30`来自DP+0C，`+34`为DP+10转换f32；source kind来自HitInfo+00，R9第四参写+20。最终倍率仍缺默认/custom/force证据，不能据它授予四类；队列消费时序仍不完整。新证据dist/hit-native-bridge-feasibility-20261012/produce-damage-verification.json。下文旧诊断reader还未增加factor字段、也未生产计数。

本机实际代码已证明：直接弹体出口 `13AE4D3 → 13B2BE0` 接收同次 HitInfo 和 DamageValues，将最终装甲倍率写入 DamageSystem 第 6 号队列的 `+28`。该队列条目为 **80 B**，entries=`+1B1120`，count=`+201138`，容量4096；它与下文旧的112 B DamageEvent队列不同。目标、节点、伤害、入射／反射方向也保留。实际代码与原字节见 `dist/hit-impact-analysis-20261011/REPORT.md`。

已取得 Drain 的实际 prologue及已声明主体，`12A78DA..12A7ABE` 对这个新队列每次处理最多16条，以80 B步长处理并扣除已处理数量。`12A79DC → 93BB90` 和 `12A7A69 → 93C580` 是两个实际消费者调用。现已取得93C580的4705B正文，主要为效果/声音；末端93D6CC→796F10只在damage>0且factor>0时调用，HUD语义未证并排除未击穿。未见已证local gate或持久事件身份，计数可能在Lua更新前已经减少，不能把对当前数组的重复轮询当完整计数。尾部另有未采的已声明片段，因此尚不宣称完整Drain时机／压缩出口。新证明见dist/hit-consumer-code-analysis-20261012/REPORT.md。

新条目 `+04` 是HitInfo+100的正规化owner；来源构造函数12A1210的327B已沿真实分支补齐，sourceBlock+0=原source、+4=正规化owner、+8=最终creditor peer，非零输入peer保持，零peer才fallback。后续HitInfo+110保留peer，但queue6没有复制它。`+18` 被producer写为0，consumer将其当作可选效果状态指针，不能当creditor；不能直接以owner==localAvatar证明本人归属。来源闭环见dist/hit-owner-prefix-analysis-20261012/REPORT.md。

真正跳弹成功尾分支13B11D4及参数已证；低速退出也返回true，所以AL=1或反射向量均不足。最终倍率1可能来自force/custom路径。**四类绶带仍未接通**；不将代码样本当命中事件，不给它们加数。总命中H01保持现有游戏统计。下一步需在保留peer与同次判定的位置保存有界原生事件，读取时序/覆盖仍需验证。

2026-10-11的四份样本／门控／等待合计6339 B、79次内存读取，包含tail等待108 B／17读，不含早先14976 B首包。2026-10-12上舰又取得上述consumer/source证据；逐包预算另见dist/interface-followup-live-verification-20261012.json。全部工具已退出，没有新增战斗轮询或原生hook。工具夹具、实际SHA/PIN/异常表边界及独立复核通过，游戏FPS未测。

后续只研究已证明的消费入口与原始owner来源，评估在生产或消费时保留本人事件的有界接口。不再按旧研究要求用户重复动作前采样，或把完整模块快照当当前唯一方案。

## 历史：旧DamageEvent诊断读取

最新证据见 `dist/hit-integration-gap-20261011/REPORT.md`。早期脚本暂名 `hitVerifyBuffer` 的 global `0x346D558` 实际是爆炸请求队列，不是命中事件队列。直接弹体路径的 `DamageEvent+0x20` 恒为 0，`+0x60` 是生成时参数副本，不能用于逐次穿甲分类。

仍有队列字段尚未闭合其生产赋值和消费含义。因此准确结论是“没有已验证可用的分类字段”，不能断言整个 `0x70` 记录绝对没有装甲倍率。当前诊断 reader 不提供正式分类；旧研究记录保留在下文。

本轮新增 `src/native-hit-reader.lua`：能通过已验证 Runtime 世界读取**原始伤害队列样本**，帮助核对目标、命中 actor 和玩家归属。它没有安装，也未读取实际战斗；不能输出已证实的跳弹／穿甲分类。9 项游戏 LuaJIT 离线测试通过，测试输入都是合成缓冲区。

## 本轮补齐的证据链

固定参考为 HD2Runtime `dcd996daca2573443956c07252c55c2d86dd0320`、Steam 构建 `25480438`。这里区分三个不同结构，不能将相同偏移混用。

| 步骤 | 已定位的原生数据 | 对分类的意义 |
| --- | --- | --- |
| 当前弹体参数 | projectile system `+0x4D040`，每项 `0xC8`；`+0x18..1E` 为四个 AP 通道，`+0x38` 为穿甲倍率 | 这是当前弹体参数，尚未连接某一次接触。倍率取整、穿甲加成和前次贯穿都会影响本次值。 |
| 直接接触构造 | `0x13AD4E8` 调用 `BuildHitEvent 0x12A25B0`，临时 **`0x118` HitInfo** 位于该调用者的 `[rbp+0x580]` | 目标 `+0x20`，节点 `+0x24`，部位 hash `+0x7C`，部位装甲 `+0x50`，表面法线 `+0x88`，有效 AP 四通道 `+0x9C..A8`，creditor `+0x110` 同属于本次接触。 |
| 本次穿甲判定 | `DamageValues 0x129DC30` → builder `0x129C9F0` → `0x129C7C0` 按实际接触角选择 AP 通道；`0x129CABC` 执行 AP−装甲 | 差值 `<0` 为阻挡，`0..不足1` 使用 `0.65` 装甲倍率，`≥1` 使用 `1.0`；这比武器标称 AP 更接近实际判定。 |
| 判定结果临时值 | **`0x24` DamageValues** 的 `+0x04` 保存装甲倍率；`HitInfo +0x73` 和 `ProjectileInfo +0xFC bit0` 可强制倍率 `1.0` | 不能将倍率 `1.0` 一概说成高一级穿甲。新接口还须保留实际比较值、强制标志及来自直接弹体处理路径的证据。 |
| 排队与消费 | `ProduceDamage 0x129DD30` 将部分信息压入 **`0x70` DamageEvent**；`ConsumeDamageEvent 0x12A7D40` 应用伤害、记录统计 | 队列保留目标／actor／dealer／owner／creditor／伤害量。公开研究没有证明它保留 AP 四通道、有效通道选择或物理反弹判定。不能从零伤害、未知字段或生命变化还原分类。 |

新增依据是 [research_direct_hit_damage.py](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_direct_hit_damage.py)：`PROOFS`、`EVENT_LAYOUT`、`VALUES_LAYOUT` 与 `report.functions` 明确连接实际部位装甲、有效 AP、按角选通道和装甲倍率。以前仅记录“AP 四通道，通道选择未知”的项目说明应按上述证据更新；**能够定位判定函数**仍不等于能够在 Lua 更新时拿到那次判定。

跳弹分支另在 `0x13B0BF8..0x13B117D`，贯穿后 AP 扣减在 `0x13AD211..24C`、速度衰减在 `0x13ADBB4..BE5`。伤害来源 kind=1 可以表示反弹之后的伤害，不能替代最初反弹接触的计数。部位摧毁与弱点仍需要本次接触的完整敌军身份及节点映射；本轮未给未知 actor 赋中文部位名。

## 原始队列采样器

```lua
local reader = require('mods/.../native-hit-reader').create()
-- 调用方决定诊断采样时机；模块不注册每帧扫描或计时器。
local sample, reason = reader.sample(16)
if sample then
    for i = 1, sample.sampled_count do
        local event = sample.records[i]
        -- 保存为诊断样本；不要调用 hit_feedback.accept(event, now)。
    end
end
```

`create()` 接受可选的 `event_world` 与 `event_natives`，默认使用 Runtime 对应模块。读取前先由 `event_world.open()` 校验构建，再核对本模块 15 条生产／消费／本机归属指令；不匹配则返回原因。源码内的 RVA 只有通过这些校验才用于读取。

- 默认只读队列前 16 条，最多 64 条；每条 `0x70` 字节，记录数量最多 4096。暴露 `observed_queue_count` 与 `truncated`，不隐藏截断或宣称完整事件流。
- 复用读取缓冲与 64 个记录槽。样本对象会在下一次调用时被覆盖；仅迭代 `1..sampled_count`，保存时复制有效条目。空队列不读取条目。
- 重新读取管理器地址、队列计数和本机 peer；明显变化或失读拒绝整个样本。相同计数下的队列压缩／替换仍可能发生，不能据此保证原子快照。
- creditor 拆成两个 `u32`，避免把 64 位身份转成 Lua 浮点数丢失精度。`local_player` 只表示 creditor 等于本机 peer，未证明目标是敌军或伤害是直接接触。
- `+0x20` 留为 `unknown_key`，`+0x60` 留为 `unknown_60`；没有当作弹体身份、武器 ID 或穿甲结果。每条记录始终 `verified=false`、`direct=nil`、`result=nil`；整份样本始终 `classification_verified=false`、`complete_stream=false`。

这是**诊断取样器**，重复读到同一队列没有新增战果；暂不做不可靠的队列去重，不给绶带加数。它只读内存，不改健康、武器、原生函数或游戏保护，不自动启用；本轮未加入构建或安装。

## 本机数据限制已实际核查

本机 `data/game/game.dll` SHA256 为 `2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E`，与参考构建一致。PE 声明 `.text` 对应虚拟区域从 `0x1000` 起、大小 `0x210FA93`，但其磁盘 raw 仅 `0x850800`；`0x129CABC`、`0x129DD77`、`0x12A6F17`、`0x13AD4E8` 都没有对应磁盘明文字节。因此不能将磁盘文件映射成已展开 `.text` 来继续反汇编。

`%LOCALAPPDATA%/HD2Runtime/local_research/snapshots` 中没有 `.hd2snap`。只发现 `control/status.txt`：此前采集会话 `captures=0`、`end=1`；本轮检查时游戏未运行。现有源码研究可以帮助定位，但未在这台机器的展开内存上重新证明未知字段。

HUD+ 0.2.1 的 crosshair 表控制准星定义，命中相关 raycast/ricochet 字段服务预测轨迹；没有发现它提供真实射击命中结果事件。BF5 Kill Feedback 包依赖观察生命损失，也没有额外的实际穿甲接口。公开 Runtime 事件来自更新回调的轮询，没有原生穿甲／跳弹分支订阅。

## 实际接通需要的最小数据与新接口

下一次只采**普通子弹未击穿、同级击穿、高一级击穿、物理跳弹**四组明确接触；再加空枪对照。保留同局完整展开 `game.dll` 的 `.hd2snap`，才可追查原生射击反馈 HUD 的生产／读取字段和临时值的去向。不要要求每枪之前手工采样；采集应在外部工具中预先准备，以自动缓冲保留前后记录。

| 必须关联的数据 | 原生捕获位置／验证用途 |
| --- | --- |
| 直接接触身份、本人归属 | 弹体处理调用链 `0x13AD4E8 → 0x12A25B0`；同次 HitInfo 的目标、节点／部位 hash、creditor 与源弹体。证明弹体完整身份和接触序号，处理同颗弹体多次接触、霰弹丸与槽位复用。 |
| 实际选中的 AP 与部位装甲 | builder 的 `0x129CA3E` 调用 `0x129C7C0`；`0x129CABC` 比较之前的选中 AP 与装甲，连同 `HitInfo +0x73`、ProjectileInfo 强制标志，以及 builder 返回的 `DamageValues +0x04`。不从累计增长或最终伤害推定。 |
| 物理去向 | 跳弹分支的实际判定结果、贯穿后继续飞行分支与上述接触身份对应；不能用一次速度改变或反弹伤害 kind 推定。 |
| 本机 Lua 能否观察保留记录 | 保存 Lua 更新前后与原生队列消费的顺序，确认真实射击反馈是否有可持续读取的结果缓冲。队列样本用于交叉核对，不能证明未入队的零伤害碰撞。 |
| 敌人部位及多人覆盖 | 至少普通敌人／有装甲部位对照；主机与加入队友的本机样本。确认 actor→节点→部位映射及归属，之后再验证近战空挥／命中未杀／零伤害接触。 |

若原生 HUD 没有保留完整结果，需开发**在真实接触路径执行时保存记录的原生观察桥**，由原生端将已验证结果写入有上限的事件环，Lua 只批量读取。现有 Runtime 不提供这样的观察桥；本轮没有实现或安装 hook，也没有假装普通 Lua 轮询能读取已经失效的栈内容。桥的地址、保存寄存器、原生调用来源与接触身份须由展开代码重新验证，才可实现；完整快照与实际战斗记录是下一步的必要证据。

性能路线优先查询已保留的原生反馈；必要观察桥仅处理本人接触、固定事件环和有界批量读取。暂未启用 2048 弹体全池高频扫描。队列采样测试证明每次读取有上限，不证明任何游戏 FPS 结论。

## 离线验证

`tests/test_native_hit_reader.lua` 在游戏安装目录的 LuaJIT DLL 中通过 9 项合成检查：字段偏移／精确 creditor、默认与最大读量、固定槽复用、空队列、采样过程中计数改变、断读／短读、非法队列大小与 peer、版本／指令变更、NaN 遥测以及 kind=1 不冒充初次跳弹。读取测试没有启动游戏，也没有取得真实分类样本。

上游证据：[直接命中伤害链](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_direct_hit_damage.py)、[弹体记录与反弹／贯穿路径](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_projectile_ballistics.py)、[DamageEvent／归属／队列消费](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_event_combat.py)、[公开累计命中说明](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/docs/events.md#damage-and-hit-attribution)。

