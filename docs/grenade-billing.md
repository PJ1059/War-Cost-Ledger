# 一次性投掷物计费 · 0.4.52

0.4.52 修正拿出手雷提前收费：原生 counts 为储备数，现在额外读取同一 owned Inventory 的 `slots.held` 实体，用引擎完整实体/类型核对是否为同款投掷物。计费总库存为 `储备 + 同款在手1枚`，拿出、保持和取消不收费，真正脱手后总库存下降才收费。沿用身份、任务、生命周期、同类型及 500ms 连续采样规则。详见 `billing-fixes-0.4.52.md`；下文保留最初接入字段和价格来源。


0.4.39 没有消费入口，因此包括毒气手雷在内的投掷物不会加账单。0.4.40 候选从 HD2Runtime 0.30.3 的 `domains/player_equipment.lua` 读取原生库存：本人 avatar 的 Inventory record `+0x28` 为投掷物资源类型；manager `+0x58` 指向 counts，索引步长 8、`+0` 是当前数量。上游 `runtime/player_equipment.lua:inventory` 使用同一对字段；原生补给代码 pins 95–104 证明资源和数量关系。不是从投掷按键、爆炸、持枪、图标纹理或战果反推。

`grenade-reader.lua` 仅导入数据域和只读字节模块；未导入带主动动作依赖的 `runtime/player_equipment`。每次按当前完整 avatar 查原生散列表，核对 descriptor 的实体和 owned 标记；读取前后资源、库存、descriptor、manager 和记录数组必须一致。没有全场扫描、钩子、原生调用或游戏写入。

源表 23 种投掷物精确匹配上游资源，其中 22 种“消耗时计费”的一次性投掷物接入。毒气手雷 EQ-127 为 **180 MC/枚**，价格直接取已确认工作簿，不另定价。源和价格证据见 `grenade-pricing-evidence.json`。飞刀 EQ-126 按“遗失/报废收费、回收再投不重复采购”的特殊规则，不能把投出当采购，目前保留未接入。

同世界、任务、完整 peer、玩家、avatar、生命周期、同资源的连续有效库存下降才计费。补给增加、切换投掷物、换身体、死亡、任务切换、读取失败或超过 500ms 的采样缺口都重建基线，首次基线不追收。一个采样间隔内同时补给与投出的抵消无法完全还原，故可能漏计，不能补猜。原生库存因其他 MOD 直接减少也无法区分具体原因。

沿用 10Hz 任务观察。读取硬上限 64 次／4096B，每次读取前检查 1ms 软预算，单次系统读取不能中断，不承诺帧率。离线真实 Runtime 数据域夹具首次核对代码加读取为 40 次／311B，后续为 21 次／228B。计费合并每种 `event=throwable_consumed` 明细，进入 `total_cents`、`equipment_ammo_cents` 和既有扣费提示，记录 `grenade_units/grenade_cents`，沿用批量保存／结束保存，不与来源击杀或 SHOTS 再次收费。

离线测试：`test_grenade_reader.lua` 的身份／原生字段／竞态／预算、`test_grenade_billing.lua` 的连续下降及复活／补给／类型／缺口，和实际构建入口 `test_addon_grenades.lua`。`grenade-inventory-watch.py` 是有指纹核对和时长上限的外部只读验证工具，输出为私有诊断，不改变账目。候选尚需本机正常投掷后验证资源、库存和安装后的实际账单变化。
