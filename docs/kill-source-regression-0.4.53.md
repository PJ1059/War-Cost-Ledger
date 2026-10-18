# 0.4.53 击杀来源回归修复

核对日期：2026-10-17。只修正未知链的否决条件；没有改写账户或按当前持有武器补历史。

## 原因与固定复现

0.4.52 增加同目标伤害链后，把所有完整读取但无法识别武器的目标标记为 `barrier=true`。原生 `Health.lastOwner` 常常只指向玩家本体，毒气／爆炸也可能没有可解析的逐目标武器。在这种没有任何相反武器证据的情况下，提示仍会丢弃同一次原生计杀批次中已有的 AC-8 或 G-4 来源。

用相同的目标扣血输入、玩家本体 owner 和明确的本次原生来源批次运行不可变旧包：0.4.51 显示 `AC-8 机炮`／`G-4 毒气榴弹`，0.4.52 两者均显示 `未知来源`。当前实际账户 sequence 40 的 0.4.52 记录仍有 AC-8 归并后 33 杀，证明至少这局没有丢掉全部已保存 AC-8 来源统计；该保存值不是独立原生计数。提示的否决条件可以独立导致用户观察到的回归。

AC-8 哈希 `A8CFFB316F0B5C5F` 和 G-4 哈希 `0416984F4922757B` 的来源名称与分类并未被删掉。没有证据把整局未知或所有毒气机制精确归为 G-4，本修复不这样做。

## 最小改动

未知链只在先前已知来源的继承被另一未知段截断时形成否决。目标从未观察到武器，或只观察到玩家本体／未解析 owner，不再否决本次实际原生计杀批次。

- 有明确同目标来源时，仍优先该来源。
- `AC-8 → 未知 B → 不同未知 C` 仍固定为未知，不搜索早先 AC-8，也不借全局批次或旧 recent 改回 AC-8。
- 没有同目标武器证据时，只允许本次实际原生计杀批次参与配对；没有该批次时仍不借以前的 recent 来源。
- 不改变原生计数、原始哈希、奖励合并、价格和内存读取路径。

## 验证

`test_target_damage_attribution.lua` 覆盖未知-only avatar／owner 无反证、相邻未知继承、第二未知截断、读取失败和身份边界。`test_target_damage_observer.lua` 用同一原生字节布局验证 avatar-only 情形和 G-4 直接来源；`test_kill_source_notices.lua` 验证本次来源恢复而旧 recent 不回填。

真实 built 入口 `test_addon_target_sources.lua` 在不可变 0.4.52 对“本次 AC-8 来源 + avatar-only 目标”失败；只替换 `target-damage-attribution.lua` 后通过，并验证 G-4、未知 B/C 截断、计杀没有增加、旧低穿甲成就和存档重载。最终包还需使用同一入口做回归。

本轮本地证据命令：`python -X utf8 -B dist/run-built-red053.py` 对不可变 .52 输出 `EXPECTED RED ... actual native AC8 credit survives ...`；`python -X utf8 -B dist/run-built-green053.py` 只替换唯一 trace 模块后输出 `PASS built target attribution ...`。这两个脚本仅访问离线包和测试缓冲区，不访问运行中游戏；对应正式测试由 `tools/test.py` 运行。

`target-damage-performance.json` 为本机 LuaJIT 对本进程合成缓冲区的测量；没有新增读取，额外来源读取最高 258 次／6375 字节。它不代表真实游戏帧率或多人归属准确率。
