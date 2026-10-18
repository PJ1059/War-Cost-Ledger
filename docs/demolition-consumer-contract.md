# 普通虫洞：消费边界与诊断行合同

2026-10-13；仅记录已证字段。当前仍不授权按候选 peer 发个人拆除绶带。

## 已闭合的正常调用链

- 原 World `AB5000` 的完整既有副本在 `AB5FFE` 调用 `13F7BA0`，指令 `e89d1b9400`；RCX=`WorldContext+1024220`，XMM1 为帧 dt。它紧随已复制的 contact 调用 `AB5FEF`。
- `13F7BA0..13F819C` 为本次真实完整 RF 的 1532B 正文，所有字节解码成功，单正常 RET `13F819B`。RF index69087，RVA `409DA80` 的实际条目为 `a07b3f019c813f01dc615102`；UW `25161DC`，头 `015d1d00`，flags0/code slots29。完整64B UW 已补采到 `dist/bughole-dispatch-unwind-live-20261013-v1/drain.bin`，SHA256 `8a596a94d3b402ef2673819085eb96b6064c6cc9ee1e48e92b5375b8e7282111`，使用原声明注册。
- 保存正文 `dist/bughole-consumer-caller-live-20261013-v1/drain.bin` SHA256 `2699cbc7b3609dff364c0aafe3f6ed31dddd2c65d463d2a4226ea0220b298e42`。本次只读27次/1790B/42.88ms，Ship与源码前后校核。
- 该 dispatch 中 `13F7D3B lea rcx,[rdi+CCFE78]`，`13F7D42 movaps xmm1,xmm8`，`13F7D46 call 13E1DC0` (`e875a0feff`)。消费入参 RCX 是 **destruction_world**，须等于 `*(Game+346D528)`；不要把减去 CCFE78 后的总 context 用作 record base。
- 该消费之前还有 `13CF940`、`12AEB10` 等调用，不能假定 World 调 dispatch 前就是队列最终状态。最小准确观察点是自有 dispatch 中的这一消费 CALL 前后。原 consumer 保留执行恰好一次，原 Game 指令页不改。
- 可把 dispatch 当独立 observer entry，按真实源的 RIP/rel32 重定位并注册原 UW，在已有 owned World 的 `AB5FFE` 改到该 entry；不用修改原 Game 或扩大六区 profile 的范围。异常/展开与正常输入输出均需独立验证。

## 只读数据

均以本次 consumer 的 destruction_world 为基址：

| 项 | 偏移/格式 | 来源 |
|---|---|---|
| 队列数据 | `+1E2F78`，每条64B | producer13E167A、consumer13E1E93/99 |
| 队列计数 | `u32(+1EAF84)` | producer13E1643/1673、consumer13E1E0F |
| 事件record index | event+18 u32 | producer13E169A、consumer13E1EAC |
| 两个未知source字段 | event+1C / +20 u32 | producer13E16B8/16BF；不冒称entity/owner |
| requested stage | event+28 u8 | producer13E169E、consumer13E2032/37 |
| 来源候选 | event+30 **完整u64** | producer13E16C2/C7、consumer13E2063/6E |
| processed | event+38 u8 | enqueue写0，consumer跳过非0，在13E2092写1 |
| mode | event+39 u8 | 原样转发，不自行解释 |
| 持久record | `+C5F78+12*index` | 上游stage getter/消费路径 |
| record字段 | +0unit u32；+4definition u16；+7stage u8；+8flags u8 | flags bit0 registered |

诊断队列读取上限512（512条结束于1EAF78，位于计数之前），超出则整批拒绝，不继续走指针。每批最多32候选并记录截断。静态洞口诊断暂只读取 `index<0x17000`，该界限来自 enqueue13E16D6 的明确分流；不是宣称整个破坏系统只有该容量。动态记录先跳过。

## 独立128B诊断行

| 行偏移 | 内容 |
|---|---|
| 00 | destruction_world u64 |
| 08 | 捕获时本地完整peer u64 |
| 10..4F | 原始64B事件，在consumer前复制 |
| 50..5B | consumer前的12B持久record |
| 5C..67 | consumer后的同index 12B持久record |
| 68 | 独立诊断sequence u32 |
| 6C..7F | 保留0 |

不能送进正常命中96B队列。Lua处理 `src/demolition-candidates.lua`：匹配同world/fullpeer，核验unit前后一致、registered仍有效、原processed0、stage0→正数；再通过当前Destructible descriptor的index+unit和Runtime明确bug_spawner资源表核验真实洞口类型。`owned`完全不用作归属。

Runtime目标索引每0.25秒刷新一次，最多32个新24B descriptor，不按整个场景额外扫描。新任务须reset，即便world指针数值复用；缺读清空当前类型索引。只能把 `target_verified` 的记录称作洞口事件，未知类型不发拆除。

当前实际安装的 Runtime 0.30.3 缺少这三个 descriptor API。`src/demolition-world.lua` 仅移植冻结上游的只读子集，匹配原 build SHA 和7个源指令 PIN 后沿现有 `world.view` 读取。15种洞口资源 hash 与官方 `domains/event_natives.lua` 逐项核对，返回值刻意不带网络 owned 字段。

## 原生实现与离线证据

生成器 `tools/native/demolition_diagnostic_observer.py` 产生 `docs/native-demolition-diagnostic-profile-v1.json`；保留旧 normal-hit revision、entries、8个 sites，追加独立 wrapper/drain/dispatch，不扩大六区源副本。

诊断头64B：`+00 capacity=32 u32`、`+04 stride=128 u32`、`+08 epoch u64`、`+10 peer u64`、`+18 published_count u32`、`+1C lock u32`、`+20 sequence u32`、`+24 dropped u32`、`+28 rejected u32`、`+2C batches u32`、`+30 pending_count u32`、`+34 scanned u32`、`+38 reserved u64`；行从 `+40` 开始。

wrapper 在 enabled/稳定 generation/完整 peer/world 全部匹配时尝试一次私锁。旧 epoch 或 peer 的未读批次会在锁内丢弃，避免下一局一直 full；同上下文允许跨帧向未读批次追加至32行，不覆盖旧行。本次追加起点保存在原栈帧的 +F0，仅新增行读取消费后的状态。捕获前后原 consumer 恰好调用一次，跨调用只持有私锁；正常 hit 的 active 引用在原调用前释放，返回后重新核对同一代次。若原 consumer 异常展开，私诊断锁可能保持占用至本次会话结束，但不会卡住正常 hit 的 active 计数。

`uint32 demolition_drain(diag,dst,max)` 只访问自有页；一次 CAS，busy立即0，最多32行，容量不足整批保留，不部分乱序。Lua每秒drain后最多保留32条已核验洞口和8条未知物，去重键最多40个；不把场景装饰写满洞口样本额度。

`tools/native/test_demolition_diagnostic_owned.py` 在自有内存实际执行 wrapper/drain；验证原调用一次，GPR/XMM0..5/算术flags/MXCSR输出相同，32行限额，10种拒绝分支，跨局旧批次回收，Windows注册展开元数据恢复栈，39处rel32完全还原原dispatch。没有打开游戏或执行采来的游戏正文。报告 `dist/demolition-owned-0.4.31/verification.json` 为PASS。Lua回归 `tests/test_demolition_candidates.lua`、`tests/test_demolition_world.lua` 也通过；尚需游戏内实际装载和一次封洞样本。

0.4.31实机已装载并记录真实stage0→1，但仅保存8条未知装饰，未得到已核验洞口。已发现并修复确定采样缺口：旧版只要published_count非0就拒绝整帧，1秒drain期间即使只有一条装饰也会挡住随后洞口。0.4.32自有内存报告 `dist/demolition-owned-0.4.32/verification.json` 验证1+2+29条跨帧追加、剩余2格时仅追加2/5、旧post字节不变、空后续帧不丢旧行、原消费仍完整处理全部事件；正常命中旧entries/sites完全一致。

当前任务结束后固定Destructible API快照 `dist/bughole-descriptors-after-own-hole-20261013-v1/descriptors.json` 为count0，虽world指针仍相同，实体列表已清空，不能事后还原本局洞口类型。Lua诊断新增descriptor_count/cached_descriptors/known_holes/pending_descriptors/invalid_descriptors/descriptor_failures/incomplete与receipts_seen/target_missing/unit_mismatch/unknown_limit，供下一自然对局区分类型缓存未完成与原生漏样。未知行仍不会事后自动晋升为洞口。

## 剩余归属证据

event+30经 `13D8B10` 第八参数原样送 `606E80`，返回u32写**新分配的临时记录**+40；该+40不是持久12B record字段。既有命中source constructor也向同helper传明确creditor，支持归属候选，尚不证明虫洞所有生产路径使用同语义。

本轮针对转发层13E1460/13E2790的直接CALL/JMP精确索引0候选，不能排除间接注册。最后已索引13E311E来源为R15，它也填多个u32字段；本次真实RF ancestry未包含R15初始化所在sibling，不补猜。停止跟进静态helper。

下一步：独立诊断只记录一次本人单人手雷封洞的128B receipt，与当前完整peer/真实洞口unit/type/stage核对。非本人/连锁仍应保持未证；不得用最后一次爆炸距离、host权威或整个巢穴完成替代个人封洞事件。既有Health构筑拆除继续保留，普通洞口将来独立增加拆除/资产计数，不增加kill。
