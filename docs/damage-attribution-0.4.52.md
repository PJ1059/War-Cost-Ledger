# 0.4.52 同目标来源、低穿甲成就与火毒击杀

核对日期：2026-10-17。没有改写旧账户，没有把未知历史倒填到当前武器。

版本说明：下文保留 0.4.52 当时的未知段规则；当前 0.4.56 已改为 [1.5 秒连续实际伤害链](continuous-damage-chain-0.4.56.md)，不再因第二个未知编号／owner／token 单独截断。奖励和只读布局证据继续适用。

## 同目标追溯读取的实际输入

优先复用现有原生命中记录：`native-hit-feedback.classify()` 已提供同一次实际弹体接触的 `target`、`source`、`owner` 和本人归属。只用穿透／完全穿透记录作为先前造成伤害的线索；碎弹、跳弹不充当伤害。此接线不新增原生拦截。`source` 是实体编号，仍须通过当前原生实体映射、完整 generation 和前后相同的 descriptor 解析资源哈希。

`Health.lastOwner`（record+0x30）也可直接提供资源线索，但它有时是攻击者 avatar，并不保证是武器。不能把 avatar 或未知实体当当前手持枪。没有可解析武器、也没有同目标已有命中时保留未知。

活体并没有已验证的逐击元素字段。真实 `health_cause_setter` 的 `0x925E83` 比较新 life==2 后才写 extension 的 kind/element；因此只在死亡读取这两个字段。把活体 extension.life==0 当当前元素会读取未初始化或旧值，本版没有这样做。

为判断未知来源段是否发生变化，保留原始 `lastOwner` 与一个不透明 token：

| RVA | 字节 | 已验证事实 |
| --- | --- | --- |
| 0x923C24 | 45896740 | ApplyDamage 把本次额外 u32 写入当前 Health.record+0x40 |
| 0x920D5F | 8b4640 | HealthUpdate 重新读取 record+0x40，传给后续伤害 |

证据为本机已有 `dist/fire-death-apply_damage.asm`（原始输入 SHA256 `e5e4da4530273f60c8c30ecbde9b1f57fa13372f6c648a1dfad8458fddabf785`）和 `dist/fire-death-health_update.asm`。token 的完整游戏语义尚未命名；只把它当边界，不称为武器、元素或穿甲等级。每次来源采样先检查上述字节；读失败不继承旧来源。

## 连续未知段规则

- 同一完整实体、descriptor、unit 和本人生命 epoch 中，已知 AC-8 命中后紧邻一段相同 `(owner, token)` 的未知扣血，允许沿用 AC-8。
- 未知段的 owner 或 token 再变化，立即截断；后续未知不搜索更早的 AC-8。
- 已有命中记录显示另一把无法解析的未知武器，先把它作为新未知边界，之后的流血不跳过它。
- 后来出现新的已知武器，才重建可继承来源。读取间隙、实体更换、跨局／跨生命均断开旧链。

`event.damage_source` 保留 `type/raw_type`、`inferred`、`barrier`、`history_complete`、`owner/damage_token`，标明 `target_bound=true`、policy=`same_target_adjacent_unknown_run`。`barrier=true` 的目标不能再被全局来源队列补成其他枪。

这是每 100ms 的客户端观察，不是完整逐击日志。中间攻击可能发生于两次采样之间；两种未知伤害若 owner/token 相同且没有独立命中记录，无法区分。不能声称对该情况取得确定因果。Health 已销毁的尸体也不会借用别的记录。

## 奖励目录

`tools/kill-source-traits.py` 从已固定 SDK 的原始资源、攻击字段和有伤害的状态定义生成 `kill-source-traits.json`，137 个来源：37 个 AP<=2，26 个可燃烧来源，8 个毒气来源。别名只用精确资源或 kind=weapon 的唯一精确英文目录名，不用武器名前缀；同名装备投送源不继承枪械 AP/火毒属性，多个战备共用的空投舱不算毒气来源。

“等级不是问题”以本人重型／巨型死亡与该目标来源关联。AP 取该来源所有已解析攻击分支的最大值；主弹 AP2、爆炸 AP3 的 Scorcher、Punisher Plasma、Loyalist 按3，AC-8 按4，防止把低穿甲副分支当整把枪。SDK 是固定构建的默认值，其他 MOD 若改写攻击，目录不代表该次动态 AP。

“燃烧击杀”和“毒气击杀”优先使用实际目标最终元素（kind2/element1 或5）。已读取到非火毒最终元素时，不因武器可能施加状态而发逐目标火毒奖励；缺元素时保留已验证来源的合理近似。R08 单纯点燃不再授奖；R09 改用毒气击杀。最终按来源合并原生计数与目标观察，旧来源覆盖保留，防止两路重复。

`fire` 表示可能造成燃烧的来源；`native_fire` 专门控制可以直接沿用来源总杀的目录。LAS-98 等普通激光可点火，单凭它的来源总杀不能全算燃烧，因此 native_fire=false；实际读取到燃烧死亡仍计。纯火焰来源和 B/FLAM-80 Cremator 的精确别名可沿用原生来源击杀。

## 有界读取与离线验证

每轮至多8个发生变化的目标，待配原生命中至多64条，实体 hash 查找至多32槽。新增来源读取硬上限512次／32KiB，同时服从原观察器2ms软预算。失败只清掉该链，保留已有击杀观察与总数。

回归包括：相邻未知继承、第二未知截断、已知替换、读失败／PIN／generation／epoch／descriptor 替换、avatar owner 通过实际 contact.source 补武器、未知武器 contact 阻断、远端 owned 目标可读直接来源、16个死亡不因8次增强上限丢杀；AP最大值和火毒最终元素、重复死亡去重也通过。

`bench-target-damage-observer.py` 使用真实游戏 LuaJIT 和 ReadProcessMemory，仅访问本进程的合成缓冲区。每轮8个活体扣血和8个原生命中输入，128／1024／4096目标平均约0.127／0.238／0.646ms，4096目标p99约1.041ms，额外来源最高258次／6375B。完整结果与源码SHA见 `target-damage-performance.json`。这不证明真实游戏 FPS 或多人的归属准确率；2ms仍是软预算。
