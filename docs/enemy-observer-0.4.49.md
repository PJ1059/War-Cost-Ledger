# 0.4.49 敌人名称与遗漏死亡的修正依据

本次离线检查仅修复可定位的问题，没有改写账户存档。游戏内新增观察结果仍待验证。

## 掠食追踪虫的实际遗漏

2026-10-15 只读检查最新第 32 场：原生击杀 860，已分类目标 693，另有完整目标 hash `D1E990BAF22D5A52` 的 73 杀，剩余 94 杀没有保存目标身份。73 杀的原始 hash 已在旧记录中，重新载入目录后可以补名；94 杀没有原始目标 hash，不能从总数还原。

`D1E990BAF22D5A52` 的精确十进制为 `15125779956101896786`。用户提供的公开 QQ 表“哈希表-整合”第 7 行、第 19 列，与 BFV 1.7 的十六进制表、十进制身份表一致：`Predator Stalker / 掠食追踪虫`。普通追踪虫 `F540CA9D9D4A422E` 和掠食猎虫 `883401AF2A98A5F6` 是不同资源，不合并。

Runtime 0.30.3 的 `domains/event_entities.lua` 为这个资源提供 `kill=true`，但只给 `entity/v1/unresolved/...`，缺少 `kind='enemy'`。原名称合并工具需要 `kind='enemy'`，所以跳过了它。这是已经证明的命名缺口，不是这 73 杀完全没被观察到。

`tools/resource_hash_labels.py` 现为这一精确 hash 加入已审阅敌人身份，按用户确认归类“中型精英”。显示姓名仍只有“掠食追踪虫”，分类保存在独立字段，不拼入姓名。

随后全面检查 Runtime 的 501 个实体资源，其中 129 个 `kill=true`、18 个缺少 `kind='enemy'`。18 项中原有 3 项已映射；本轮补齐 14 项，包括掠食追踪虫、10 个其他敌人、1 个运输舰变体和 2 个仅 QQ 表有精确姓名的敌人资源。12 项由 BFV 精确身份表与 QQ 表共同对齐；2 项为 QQ“机器人-基础单位/特殊变种”分组与 Runtime 计杀身份共同确认，体型保持未知。运输舰变体沿用 asset 身份，不混入普通敌人计杀。

唯一仍无名的原生计杀资源是 `FD5247653C897803`，BFV 精确身份表与 QQ 都未提供姓名。BFV 手工表共 139 个精确十进制身份，其中 122 项已映射；其余 17 项中，16 项在当前 Runtime 与 QQ 精确资源表均不存在，1 项是 Runtime 明确 `kill=false` 的穿刺虫资源。不能把这些相近 hash 强制当作实际计杀资源；当前穿刺虫计杀资源 `AE57FCDB49F74E98` 已有名称与内部分类。

当前目录 134 个敌人/构筑 hash、76 个已命名名册种类，1185 个统计来源标签。保留原有 84 项分类、36 项 Runtime+QQ 映射；新增审阅缺 kind 身份共 14 项。旧 `unmapped_roster` 字段仍是原目录的 21 项元数据。全部姓名不附加体型/等级后缀。

## 参考实现与本地技术路径

参考 ZIP：`【正式版丨必装HD2Runtime】战地5击杀反馈v1.7.zip`，SHA256 `584886c8e23c1fddc1162a972efd87fad67e288cfd7ddd2fac529af42d109630`。只读取其源码，不执行第三方代码。

参考源码 `93E5D0431533CBC9.lua`：

- 1541、1760、2342 行包含 Predator Stalker 的身份、翻译和完整 hash 对齐。
- 2925—3056 行的 R40 追踪死亡/受伤/消失候选，用本人原生 `dealt_kills` 增长形成归属额度，并先消耗直接确认死亡。
- 3098—3128 行的 R41 在近期消失、本人伤害或爆炸等证据上选择候选；不会把单纯消失直接当作本人击杀。
- 5810—5860 行消费额度，无法识别目标时仍保留未知。其观察与推测比旧 Ledger 只接受可见活体转死亡的路径更宽。

本地 `src/kill-observer.lua` 沿用 Runtime 已校验的 health/corpse 内存字段。health 的 descriptor 包含 `type/entity/unit`；health record 包含 `life/health/lastCreditor/downCreditor`。`runtime/event_world.lua:167` 的 `corpses` 提供死亡原实体 ID 到尸体索引的对应；184 行的 `corpse_entity` 核对尸体接管的 unit。网络对象属主不用于冒充实际击杀归属。

## 新观察口径

观察频率改为 10 Hz，保留最多 4096 health records、16384 hash slots、每轮最多 64 个新 health descriptors、2 ms 软检查点与无慢帧补跑。尸体表由 Runtime 限制最多 512 条；每轮尸体 descriptor 最多再查 64 条。

直接观察到的活体→死亡，若当前 creditor 明确，继续报告真实本人或其他玩家归属。这些本人死亡优先消耗原生 KILLS 额度。没有 creditor 的死亡，以及有 origin/unit 证据的活体→尸体，只在 0.75 秒内存在剩余本人 KILLS 增量时推测归属；候选至少等待 0.15 秒，给同批直接死亡先到达的机会。推测事件标注 `inferred=true`、`native_creditor_verified=false`，不填造假的 `killer_peer`。

为覆盖两个轮询之间已经死亡的快目标，完整首次基线之后新增的已死 health descriptor 也可成为候选。新出现的尸体若 descriptor 仍保留精确敌人 type、有效 entity/unit，也可成为候选；若只剩 generic corpse type，则不能猜回原敌名。尸体首次全表读数、初始已死 health rows、描述符暖机时溢出的旧行都只作为基线。已知其他 peer 的死亡不会转给本人。断读、换 world、换本人 peer、重置任务会清理候选；跨生命的推测额度也会清理。

这些补偿仍属于短窗口推测，可能受多人同时击杀、客户端同步和读数顺序影响。它改善目标覆盖，不证明每个目标的具体致死武器。原生总击杀不会因为提示或补偿再增加。

## 离线验证

`tests/test_kill_observer.lua` 覆盖直接归属、额度与延迟顺序、未知 creditor、origin/unit 尸体、新增精确敌人尸体、首见已死、generic corpse、过期、初始基线、描述符暖机、断读、world/生命变化与 10 Hz 节律。`tests/test_resource_hash_labels.py` 共 10 组验证，包含 14 项缺 kind 身份、134/76 总数契约、原有分类保留与重建幂等。

`tools/bench-kill-observer.py` 已用新源码重新测量游戏 LuaJIT 与本进程的真实 ReadProcessMemory；结果在 `kill-observer-performance.json`。128/1024/4096 活体稳态平均每轮约 0.0127/0.1027/0.3866 ms，P99 约 0.0191/0.1565/0.4759 ms。该基准包含开启归属额度回调、空尸体 global 的额外读取，不包含尸体集中生成、待归属队列或真实游戏渲染，不能当作实战帧率验证。
