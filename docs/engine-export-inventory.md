# 引擎导出清单：一次只读诊断

0.4.20 在飞船状态稳定6秒后，列出当前Lua中的 stingray 根表，以及 PhysicsWorld、Actor、World、Unit、ScriptWorld、Application 六个指定模块的字符串名字和值类型。每个模块及名字按名称排序；不调用任何成员、不读取对象值或元表、不解析userdata、不记录游戏地址，也不创建物理回调。

完整名单一次性保存在独立诊断存档 `mods_hd2_costs_war_cost_ledger_engine_exports.json` 的 `inventory`。主 MOD 存档的 `engine_api_inventory_v1` 及状态只保留代码SHA、游戏构建指纹、时间、计数、完整性原因与保存结果的简短摘要，避免每次账单存档重复编码名单。同一构建及采集代码只采一份，跨启动停采；任务、读不到世界、非live适配器均不运行。根绑定不是table时只保存不支持摘要，不打开诊断存档。未完整或不支持的模块不能当作成功命中来源。

限额为总1024次键扫描、每模块256次、名字最多96B、2ms软时间检查；非字符串或不可打印名字被过滤并标注partial。缺失/非table绑定标unsupported，不能据此宣称引擎没有该功能。只返回{name,type}等普通值，可以直接保存JSON。存档写入在完成后只做一次，其耗时单独以实际日志观察。

这个诊断用于确认实际可用的正常回调入口。官方Stingray的Unit Flow物理接触可触发脚本回调，需要对应资源、图连接和被加载；HD2是否提供完整命中载荷仍未知。四类命中仍未接通，单独函数名也不能证明AP、本人归属或真实跳弹覆盖。

旧七采点实验因实际VirtualProtect错误5已暂停自动装载；正常游戏不再每次启动重试。内部 `native_hit_auto_install` 默认false，仅owned开发fixture显式true继续验证旧实验。已认证且匹配当前模块的既有句柄继续按原10Hz生命周期消费，不更改H01总命中、账单、生涯同步或HUD。

纯读取模块来自本地Runtime `ledger-interfaces` 分支 `runtime/engine_exports.lua`。13项owned模块测试已通过；实际导出内容、菜单画面及FPS仍需此次实机诊断，不能以隔离测试代替。
