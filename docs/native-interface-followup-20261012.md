# 原生接口续查 · 2026-10-12

上舰后的代码采集已结束。此轮验证原生函数和字段，尚未生成逐次命中事件，也没有读取实际生涯总数。正式0.4.13、部署和账号未由本轮修改。

## 命中消费：真实4705B已取得

自动工具46592在Ship校验实际caller `12A7A69 e8124b69ff → 93C580` 后，因真实声明范围 `[93C580,93D7E1)` 的4705B超过通用4096B上限，按设计退出；失败包保留。根据已取得的异常表记录，用 `hit-consumer-known-range-capture.py` 固定核对caller、12B记录及4B unwind header，分4096+609B取正文，通用上限未改。

成功材料 `dist/hit-consumer-exact-20261012/drain.bin/json` SHA `90c946961aa86f000ca00f292cc3421f0820dce63fe8512bb279cf10bb99afd8`。21B前缀及4705B正文，含前后Ship共4750B/9读。独立复核通过；1085条可达指令的函数内分支闭合，外callee仍未知。

consumer主要处理三维效果和声音，没有证实本地玩家过滤。queue6 `+18` 被作为可选效果状态指针使用，不能当creditor。末端 `93D6CC → 796F10` 只在伤害和装甲倍率都为正时调用，排除了未击穿；其HUD语义也未证明，不能作为完整四类命中接口。

## 命中归属：构造输出已闭合

复用旧实际direct/ricochet包，新增4352B来源前段和32B跳弹入口。来源前段13AC300起于上一条指令的位移，不能当函数入口；只从已证入口局部分析。

实际 `13AD2E9 → 12A1210` 将C8 creditor peer、owner entity、source entity传入来源构造函数。逻辑函数被编译器拆成多个声明片段；33B入口和229B后继之后，沿实际 `12A1314 je12A133E`/fallthrough及已记录 `[12A1316,12A1357)`65B补齐，没有扩大通用扫描。

三包合并为 `[12A1210,12A1357)`327B，构造函数内分支和ret闭合；外helper语义仍未知。

| 字段 | 实际写入 | 已证含义 |
| --- | --- | --- |
| sourceBlock+0 | 12A133E，EDI | 原source entity |
| sourceBlock+4 | 12A1344，EBX | 条件替代/正规化后的owner |
| sourceBlock+8 | 12A1348，R14 | 最终64位creditor peer |

非零输入peer保持；零输入才9EF150 fallback。owner有实体映射和peer恢复路径，不能等同当前avatar。InitHitInfo将+4传入+100、+8传入+110；queue6只复制前者，丢弃peer。来源字段闭环已经证明，游戏内本地命中记录仍未实现。

真实跳弹helper参数及成功尾分支13B11D4已证；低速退出也可返回AL=1，因此不能用返回值、反射向量或速度变化直接加跳弹数。force/custom可令factor=1，不能统一判完全击穿。没有持久事件序号和可靠Lua采集时序。

下一接口应在同次原生接触仍保留peer、AP/装甲、强制标志及真正跳弹分支时保存有界事件，再批量交给Lua；queue6反复轮询无法证明完整性。来源原字节见 `dist/hit-owner-prefix-analysis-20261012/REPORT.md`，效果consumer见 `dist/hit-consumer-code-analysis-20261012/REPORT.md`。

## 生涯：UILabel字符串记录已实机证明

自动工具20068取得122B writer143C950；随后沿实际 `143C960 → 143A1B0` 和其分支取格式存储片段。实际布局：label key+272，records+280，每项24B，record key+0 u32、type+4 u32，type1的value+8为64位字符串指针，count+616 u8。

新key追加及已有key指针改变时的写回/AL=1已证；record+16保存AAFF30返回高32，其算法未命名。相同指针22B `[143A2C2,143A2D8)` 和1737970/AAFF30外callee未取，数字类型仍未知，不能将value槽统一读成u64生涯数。

Career标签key和页面定位有静态依据，但具体行和值控件绑定、数字格式、账号/加载状态未闭合。普通Ship状态不证明Career页或后端数据已就绪。上舰自动生涯同步仍未接通，不覆盖现有351849杀/4633死亡基准。报告 `dist/career-format-storage-analysis-20261012/REPORT.md`。

## 验证与性能边界

本轮较早39项夹具通过，新小profile隔离校验通过；实际包SHA/PIN、异常表/父链、重叠字节、前后Ship相同context及独立复核通过。记录 `dist/interface-followup-live-verification-20261012.json`；较早待机记录作为历史保留。

所有工具只取代码，没有调用这些setter/helper、安装hook或新增战斗轮询。单次诊断读取量和IO时间已记录，FPS未测试。原待机46592/20068均已退出，当前无采集待机；不需要再开地图、按F8或动作前手动采样。
