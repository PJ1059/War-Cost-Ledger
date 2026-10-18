# 普通虫洞拆除归属推测

## 0.4.51 实战证据确认的目标发现修复

2026-10-16 读取本机实际 Runtime 日志，确认 0.4.50 已加载、explosions 事件源已启动；第 33、34 局的拆巢摘要均为 `known_holes=0 / closures=0 / awarded=0`。账户中的 `bughole_diagnostic_v1` 同样没有观察到已知虫洞。当前首先缺失的是目标发现，不能再用放宽爆炸半径或移除竞争条件当作修复证据。

现有摘要不足以区分“列表有数据但 pointer/index 尚无效”“描述已读但资源未匹配目录”“洞不在该枚举路径”。旧固定 descriptor 快照来自舰上（mode=3、count=0），不能用来确认任务中的原因。另一个诊断缺陷是 `status()` 持有可变 reader 表，结束任务 reset 可把 `last_mission.demolition_status` 归零；这只影响证据保存，不解释任务中的漏计。

首次诊断冻结在 `dist/combat-fixes-0.4.51/demolition-observed-baseline.json`。本轮观察器补充零额外原生读取的分类计数：`descriptor_count / valid_pointers / invalid_pointers / invalid_indices / cached_descriptors / descriptor_failures / nonhole_descriptors`，并保留最多 8 个已读资源 hash；不改拆除奖励口径。

用户保持在实际未封洞旁时，首轮只读快照 `dist/bughole-open-descriptor-0.4.51-20261016/descriptors.json` 返回 64 个有效地址，但所有 index 均从 `0x17000` 起，被旧版上限整体跳过，因而没有读取任何 descriptor。第二轮沿相同已验证地址读取 64 个 24 字节 descriptor，确认其中有 11 个目录已知普通虫洞，index 为 `0x17026..0x17030`。它们全部拥有可读且 unit 一致、registered 的 12 字节记录，stage 均为 0。

第三轮核对真实本地 enqueue caller `13E1512` 与网络 handler `BBA67E`：两处均为 `4181f8007c0100`（`cmp r8d,0x17C00`）。既有 getter、consumer 的 stride、stage、unit 指令 PIN 同样匹配。旧 `0x17000` 只限制 enqueue 中的静态 packed-stage 另一路处理，并非 records 总容量。普通洞使用其后的动态记录，旧上限错误地把它们全部排除。

随后用户只封一个洞，再只读原 11 个固定记录：`0x17026 / unit4194819` 恰好 `stage0→1`，其余 10 洞维持 0；descriptor、unit、注册标志与重复读取均稳定。真实 before 为 `dist/bughole-open-dynamic-records-0.4.51-20261016/records.json`（3770 字节、136 次读取），after 为 `dist/bughole-closed-dynamic-records-0.4.51-20261016/records.json`（682 字节、58 次读取）。所有采样只读，不调用游戏函数、不改内存、不改账目。

最小修复将 `bughole-observer.max_record_index` 与 `demolition-world.max_records` 同时改为 `0x17C00`；读取 records 前增加上述两处真实容量 PIN。单轮窗口、描述读取和位置预算保持不变。`tests/fixtures/bughole-dynamic-records-20261016.lua` 保留去掉进程地址的原始 descriptor/record 字节及两份证据 SHA，`tests/test_bughole_dynamic_records.lua` 用真实 adapter 回放：0.4.50 发现 0 洞而失败，新版发现 11 洞且只发出该 1 次关闭。其他既有稀疏轮转、归属和边界检查仍通过。更新后的实际游戏绶带显示仍需运行新版确认；本轮已确认真实封洞事件与原先丢弃它的原因。

0.4.49 按用户明确选择采用偏向奖励的近似口径：观察到实际虫洞关闭，并且近期有覆盖其位置的本人爆炸，即可授予拆除绶带。多人重叠攻击时可能把队友实际关闭的洞也算给本人。输出始终带 `confidence=inferred`、`creditor_verified=false`，保存匹配证据；不据此增加敌人击杀数或账单。

## 输入与输出

`src/demolition-attribution.lua` 导出工厂函数。实例有 `observe_explosion(event, now)`、`observe_closure(event, now)`、`advance(now)`、`reset(mission)`。`advance` 返回本轮新授予数组；每项含洞 `id`、`mission`、`closed_at`、判定 `time` 与 `evidence`。

- 爆炸输入：`time`、`position={x,y,z}`、最终匹配半径 `radius`、`local_player=true/false/nil`。只有明确 `true` 才能授予；队友或未确认来源仅记竞争证据。逐字段复制坐标，不依赖 `pairs` 遍历 Runtime 的只读代理。
- 关闭输入：稳定洞 `id`、`kind=bug_hole`、正整数 `stage`、`time`、位置。接线层验证真实已知虫洞的同一注册记录 `0→正 stage`；首次读到已关闭洞只建基线。网络 `owned` 不作为拆除者证据。若有明确他人责任证据，`responsible_local=false` 仍直接拒绝。
- 两类 `time` 与 `now` 都使用本机接收时的 HUD 秒数。任务变化调用 `reset`；带 `mission` 的异任务事件会拒绝。

## 时间、范围与竞争

检查 `[观察到关闭前 2.5 秒, 关闭后 0.35 秒]` 的爆炸。有本人覆盖立即授予；没有证据则最多等 2.25 秒，不强制等待完整窗口。后沿容纳轮询和事件交付顺序，不接受关闭很久之后的本人爆炸。这与参考 BFV 的“最多等证据、已有证据即反馈”一致。

已知半径来自独立 SDK 表，匹配限制在 9–46.5 米；未知本人型号或半径缺失时采用参考算法的 9 米。SDK 的 `demolition=0` 不再提前排除本人爆炸。其他／未知来源缺半径时按 46.5 米收集竞争证据；这些爆炸不会独自授予，也不会否决已有本人覆盖。单条爆炸位置缺失或有界缓存溢出不再污染其他有效本人事件。成功证据保存 `conflict_count` 与所选爆炸的 `radius_basis`。

同一爆炸可覆盖多个独立洞。洞身份保存至任务重置，最多 2048，满后停止新增推测，不清空去重重发。待判定最多 64 条；爆炸最多 96 条、保留 5.1 秒。时间倒退清空爆炸和待判定，保留洞去重并等待干净窗口；任务、原生世界切换或实际读取中断清空关联，不回补缺口内已关闭的洞。

## 关闭采样与本轮漏计修复

`src/bughole-observer.lua` 沿用固定布局的 4 Hz 只读采样，每轮最多读取 32 个新描述、24 个阶段窗口和 4 个位置，不扩大原生读取预算。

0.4.48 在本轮预算未覆盖某个洞时清除了它的阶段基线。80 个分散索引的固定测试因此无法识别任何关闭；旧测试还把这种漏计作为预期结果。0.4.49 保留预算轮转中尚未访问的同洞基线，真实读取失败、时间缺口或身份变化仍重新建基线。对应测试现要求 80 个洞全部各识别一次。

原实现只在洞关闭后读位置，此时原生 unit 可能已经销毁。现在在仍存活时缓存同一个洞的位置；关闭先用缓存，未缓存才在剩余预算内读取。缓存也逐字段复制，不会被后续可变输入修改。位置从未成功读取的洞仍不伪造坐标；首次见到已关闭洞仍不重放。

实际 0.4.48 日志只证明爆炸事件源已启动、MOD 已加载；第 32 局账目中拆除为零，未保存能区分关闭读取与匹配拒绝的细节。因此上述离线复现证明了功能缺陷，不能据此认定它就是该场实战唯一原因。

## 验证与剩余限制

针对性检查：`tests/test_bughole_observer.lua` 覆盖稀疏轮转、活洞缓存、预算、真实中断与同洞去重；`tests/test_demolition_attribution.lua` 覆盖即时反馈、9 米回退、竞争证据、时限与任务重置；`tests/test_addon_demolition.lua` 用实际打包入口连接原生阶段布局、Runtime 爆炸回调、绶带、账目和历史。

多人归属仍是推测。初次进入时尚未观察到存活基线、位置从未可读、爆炸事件未上报、过多分散阶段记录导致轮询延后，均可能漏计。现有路径只覆盖目录已知普通虫洞，不能据此宣称所有敌方设施已经接入。真实任务反馈仍需实战观察。
