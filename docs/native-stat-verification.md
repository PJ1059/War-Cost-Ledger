# 原生统计缺口定位与性能证据 · 0.3.0

已实现燃烧来源击杀 → 本场“点燃”计数 → 本 MOD 历史累计 → 500 次“香喷喷”标志，并复用旧计费统计读取。新只读接口支持 int / float / bool；距离和辅助装弹尚未绑定猜测 key。包、14 项类型／边界检查、计费和燃烧回归、小型探针实文件测试均通过游戏 `lua51.dll` 离线运行；真实任务未验证。

## 已确认的线索

| 项目 | 证据 | 缺口及实际路线 |
|---|---|---|
| 我赶时间 | 上游 `scripts/research_event_state.py:833–836` 明确原生 `distance_traveled` 在舰桥也增长 | 定位实际 key、int/float 槽、单位、任务清零行为；采用任务基线增量，不能把舰桥累计全部算进任务 |
| 组合技 | 官方成就 Promote Synergy／倡导合作：辅助一名队友装填弹药；本机 Steam schema API name=29，stats/1/bits/31 | schema 只有成就位组，没有公开 INT/FLOAT 次数。用自行装弹／提供辅助／接受辅助对照原生表；若表无增量，再查 WeaponAssistedReload 组件，不能把成就解锁位当每次 +1 |
| 点燃 | 20 个来源 type 的实际武器／燃烧攻击定义与 Runtime 来源目录匹配 | 按来源击杀计数，包含直击和爆炸；缺失来源保留未覆盖，不猜。无法与死者类别关联 |

内部 key 不一定是显示名的哈希：已知 `dealt_kills` 的 key 实际对应 `kills`。`hash("distance_traveled")` 只是候选，没有启用。当前 Runtime 整数读取器只读条目 +4；距离可能使用 +8 的独立 float，不能将浮点位当整数。新接口主条目读完整 20B，来源仍一次批量读取。

官方资料：[Steam 成就](https://steamcommunity.com/stats/553850/achievements)，[固定构建原生统计研究](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_event_state.py)，[AddStat 与近战统计研究](https://github.com/SkyeShade/HD2Runtime/blob/dcd996daca2573443956c07252c55c2d86dd0320/scripts/research_event_combat.py)。本机 schema：`E:\STEAM\appcache\stats\UserGameStatsSchema_553850.bin`，已解析全部 60720 字节。

## 小型探针

仅在受控测试时启用，在项目目录运行：

```powershell
# 游戏关闭时；保留已有账目并备份设置
python tools/stat-probe.py enable
# 启动游戏，进入稳定场景后由 Codex 发出单次采集
python tools/stat-probe.py capture --label distance-before --code
python tools/stat-probe.py status
```

原始表单次采集保留 key、i32、f32、原始浮点位、bool；主表最多 4096 项，来源最多 64×16 项，总 JSON 上限 1 MiB。`--code` 只额外读取已知汇总函数及统计序列化函数共约 3.3KB。没有全进程扫描，没有向游戏内存写入或新增游戏 hook。采集输出在 `%LOCALAPPDATA%\HD2Runtime\mod_data\ledger_probe_<id>.json`，读取失败会留下明确错误结果。

距离对照：站立基线 → 一段已知位移 → 对照游戏结算距离；同时检查在舰桥和进入任务时的计数，重复确认单位和任务边界。辅助装弹对照：基线 → 本人自行装弹 → 本人提供一次辅助 → 本人接受一次辅助 → 再提供一次辅助，寻找只给提供者、可重复增长的字段。固定 key 需要行为对照或原生生产者证据，单次变化不够证明。

```powershell
python tools/stat-probe.py diff --before <第一份JSON绝对路径> --after <第二份JSON绝对路径>
# 受控测试结束、游戏关闭后停用
python tools/stat-probe.py disable
```

任务主支及参与者接口仍沿已有 `docs/objective-verification.md` 研究记录继续；本轮没有启动其大型内存快照。涉及武器和具体敌人因果归属的成就也未用累计来源数冒充。

## 性能证据

所有常规世界、玩家、信标、统计读取共用约 10Hz 观察周期；一次长帧最多观察一次。火焰分类只检查已取得的来源，不新增第二次来源内存读取。账目复制请求每 5 秒合并一次，任务结束补读尾部并立即保存。探针关闭时零文件检查；测试开启后闲置最多每秒一次小文件检查，只有 capture 才做一份统计快照。

`tests/test_events.lua` 实际回放 600 个 60fps 帧，确认世界／玩家／统计各 100 次，期间 store:set 不超过 4 次（一次检查点写两个键）。统计等待后恢复、来源变体、原生重置和退出任务尾部均有回归覆盖。没有启用全场敌人生命值、位置采样或每帧存盘。

`docs/performance-baseline.json` 使用游戏 LuaJIT、QPC 高精度计时、原版 Windows 只读适配器及真正 `ReadProcessMemory`，读取基准进程自己的合成 FFI 表。64 个来源块 ×16 项填满，各案例预热 300 次，测量 2000 次，读取失败为 0。

| 读取 | 平均耗时 | 99% 样本不超过 | 调用／字节 |
|---|---:|---:|---:|
| 正常使用的原版 2 个整数 key | 18.54 µs | 51.40 µs | 7 / 21,084B |
| 原版 3 个整数 key | 24.25 µs | 73.40 µs | 8 / 21,092B |
| 新接口同样 3 个 key | 23.86 µs | 78.40 µs | 8 / 21,128B |
| 新接口 5 个混合类型 key | 35.09 µs | 112.80 µs | 10 / 21,168B |
| 手动完整统计表采集 | 115.47 µs | 542.30 µs | 6 / 22,348B（基准主表64项） |

这些数值只包含统计读取、解码与构造结果，不包含首次结构证明、世界／信标读取、HUD 渲染、JSON 编码和文件写入。不同案例的计时差不用于宣称新接口更快。正常 2-key 读取按 10Hz 平均约 0.19ms/秒；这不能代替真实战斗的 FPS 和卡顿测量。实机应在同一场景对照账单启用／停用，同时观察游戏 FPS 和已有性能记录器的 Lua 更新间隔／CPU 尖峰；后者并非 GPU 帧时间，其他 MOD 保持一致。

Uses code / research from HD2Runtime by SkyeShade: https://github.com/SkyeShade/HD2Runtime
