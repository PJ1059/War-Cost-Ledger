# 原生个人生涯两行读取

`src/native-career-reader.lua` 已加入0.4.19可见生涯页同步。生产调用使用 `visible_only=true`，页面隐藏立即停止行读取。同步层负责低频调度和账户基准；读取模块只返回数据，不保存账户、加载GUI、发送消息或调用原生getter/setter。

## 调用

```lua
local reader = nativeCareer.new({visible_only = true, clock = world.runtime.precise_time or os.clock})
local snapshot, reason = reader:read(world, localPeerHex)
```

`world` 沿Runtime event_world.open已证明的game/view/runtime；`view.read(address,n)`须返回exact字符串，runtime.mode须live。`localPeerHex`为玩家current peer的16位十六进制。模块将 `[game+347CEF0]+B398` 的两个u32在读取前后与此peer核对，含owner地址稳定。

成功snapshot含 `kills/deaths/local_peer/status/identity`。`status=page_visible` 表示本次前后完整生涯页均可见；`ui_cache_observed` 表示同一owner曾完整可见读取后、当前页面关闭但两行缓存仍可读。`ui_cache_loaded`仅由一次可见成功建立。原生alpha使用真实值，不将隐藏伪造为可见。`server_ready/backend_ready/ui_cache_refresh_verified`均保持false；根同步层不能由缓存存在推定已返舰更新。

当前支持的是实机明确绑定标签和值的子集：敌方击杀标签F68F08B2、死亡标签32C9CF0D，COUNT模板2BAA24A7，参数keyAB2A7B35/type4/high32=0/low<2^31。用户自己打开的完整生涯页显示351849/4633，成功两行包SHA6dc84d63eddee2136e1572fbaa7b6c5ccf8900bd213e21acbf71b25551e2b9fc与这两行吻合；不是使用已否定的346D570 debug缓存。此支持范围无需定义所有类型的enum或调用未知formatter。

## 成本和失效

只在Ship=3读取Career；其他状态只复核状态12B/2read。调用者应低频放在Ship分支，任务中无需调用。整个调用所有read均通过同一64次/8KiB/2ms软检查点，指针/u32无预算旁路。同步I/O已经在途时不能抢占，因此软上限不是游戏FPS保证。当前registry5首读58次/6761B，含四actual label PIN和本地peer前后4次；同game+view后续54次/6720B。模块不遍历完整列表，只取firstrow、走8个NEXT、读取rows0/8的标签和值。

前后核对Ship、注册表owner、list child/next/parent/context、8步路径、两行/四个text的parent/context/kind7和关键数值。布局、账户peer、代码PIN、count/type/数值变化、短读或预算失败返回nil，绝不填0。真实稳定的0是有效数值。代码PIN按current双build/schema和game+view世界身份缓存；新世界重新验证。缺失或初始隐藏缓存不建立ready。

## 验证

`tests/test_native_career_reader.lua` 在游戏自带LuaJIT的隔离Lua状态中15项通过。使用当前Runtime bytes/schema和真实partial字节的28条紧凑fixture；本地peer字段由已公开Runtime布局添加到owned测试内存，不冒称真实包已采peer。

已验证：两行/预算计数、PIN缓存和换world复验、非Ship范围、peer拒绝与前后变化、初始隐藏拒绝/已加载隐藏缓存、Mission期间不读/返舰不宣称fresh、同context重建、type4范围、真实0/读取失败差别、PIN错、值变化/cycle、首读前预算、schema与非live零IO。

尚需实机：游戏内同一Runtime.view的耗时；关闭页缓存是否存活；任务后返舰缓存是否自行更新。模块不自动同步任何生涯基准。后续只能用观察到的更新证据决定是否接受闭页值，不能由两次相同缓存值直接宣称serverready。

## 闭页实机事实（2026-10-12）

用户返回普通飞船后，`dist/career-hidden-cache-20261012-0a84f777` 返回 `CAREER_CACHE_WAITING_ARMORY`：active registry 的kind224移除。原生完整页面两行读取已证实，但这个UI owner的生命周期使本模块不能宣称普通上舰自动读取。缓存初始化条件保持，未改成隐藏owner猜读。下一阶段追PresenterManager::open的Armory初始化/data provider入口，仅读取代码，不打开页面或调用该函数。实际Runtime f32 decoder先拒绝exp255，因此新增loaded→NaN/±Inf字节fixture均拒读，无需另加NaN补丁。
