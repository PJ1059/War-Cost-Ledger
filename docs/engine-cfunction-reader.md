# 六个脚本入口：只读身份诊断

0.4.21 在飞船稳定8秒后，只采一份 World.set_flow_callback_object、Unit.flow_event 及 Application.flow_callback_context_world/unit/entity/level 的入口信息。它用于取得后续定向代码核对的位置；不调用这些成员、目标地址或 setter，不能据此宣称四类命中已接通。

先校验已证明的Runtime world、Lua DLL SHA256、LuaJIT2.1.0-alpha/x64/非GC64 ABI。普通C函数身份来自相同DLL的owned公开C API对照：ffid字节+6须为1，GC对象+24的8B才是普通C入口。Lua函数与fast builtin拒绝。`%p`只提供GC对象地址，不是函数正文。随后通过Runtime只读方法读取32B对象前缀；入口须位于当前已证明EXE/Game映像、可读可执行MEM_IMAGE区域，候选代码前缀只读16B。未验证函数签名、默认回调对象、转发/恢复或完整命中producer。

采样最多6个函数、12次/288B读取，2ms软检查。别名入口复用16B前缀；单项缺失、失败或预算耗尽保留其它已独立核对的候选，整体身份变化才全部拒绝。Lua DLL完整文件哈希一次，单独于采样额度；实际匹配文件469080B，SDK模块哈希API没有未知文件大小的预限。关闭、非飞船、任务中不采。

完整普通值结果独立保存到`mods_hd2_costs_war_cost_ledger_engine_bindings.json`的`inventory`。主账户`engine_cfunction_inventory_v1`和状态只保存计数、完整性、代码/构建指纹、时间、保存结果与耗时摘要。相同采样源码/构建跨启动停采，旧记录标historical且identity_ready=false。缺少全部指定函数时只保存摘要，不打开独立存档。持久化耗时不在2ms采样限额内；日志总耗时包含模块加载、哈希和独立存档，但主账户保存另计。

同DLL公开C API布局探针及13项reader owned测试已通过；测试使用自己的LuaState/闭包与当前宿主的实际windows_readonly方法，执行目标callbacks为0、Game进程读写为0。真实入口、游戏采样耗时和FPS尚需实机证据。完整四类命中仍需本人、目标、穿甲/装甲、未击穿原因、真实跳弹及逐接触生命周期。
