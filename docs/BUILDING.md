# Build and verify / 构建与验证

This source snapshot builds **HD2 War Cost Ledger 0.4.66**. Run commands from the repository root on 64-bit Windows. Building is offline and does not install the mod or access a running game.

本公开源码用于构建 **0.4.66**。在 Windows 64 位系统的仓库根目录运行以下命令；构建不会安装 MOD，也不会访问正在运行的游戏。

## Build inputs / 构建输入

- Python 3.12 and Pillow (`python -m pip install Pillow`). The tested environment used Python 3.12.
- [HD2Runtime source](https://github.com/SkyeShade/HD2Runtime) at commit `dcd996daca2573443956c07252c55c2d86dd0320` (0.30.3), including its `sdk/` directory. It is an external dependency, not bundled here.
- The checked-in `pricing/HD2-军需价格表-v0.2.xlsx`, JSON catalogs, and artwork listed by the build. Do not replace these with personal ledger exports or newer unreviewed game tables.

```powershell
$env:HD2_RUNTIME_SOURCE = 'D:/Dependencies/HD2Runtime'
$env:HD2_RUNTIME_SDK = "$env:HD2_RUNTIME_SOURCE/sdk"
python -X utf8 -B tools/build.py
```

Output: `dist/HD2-War-Cost-Ledger-0.4.66.zip`. The package contains three `Addon/` archive files and the mod-manager manifest. The main archive contains 125 resources, including 53 award images, four metric images, two trend indicators, the ribbon frame and UI support. Existing PNGs are read without redrawing them. The original runtime dependencies remain separate downloads.

输出为上述 ZIP；使用 MOD 管理器导入。生产构建沿用已审阅 PNG 和价格表，不重新生成图像，也不重新抓取网页、哈希表或用户存档。运行时依赖仍须单独安装。

## Package and LuaJIT checks / 包与 LuaJIT 检查

Use the `lua51.dll` from your own Helldivers 2 installation. This is not a generic Lua executable.

```powershell
$env:HD2_LUA51_DLL = 'D:/SteamLibrary/steamapps/common/Helldivers 2/bin/lua51.dll'
python -X utf8 -B tools/test.py --package-only
```

This checks package integrity, resource identities, artwork inputs, pricing and the initial independent Lua tests. It is a bounded package check, not the full regression suite.

这条命令验证包结构、资源、图案输入、价格与基础 Lua 用例；它不等于完整回归测试。

## Full regression suite / 完整回归

The full suite also needs Capstone (`python -m pip install capstone`) and external reference code/data. Supply these paths; do not copy complete third-party mods or personal research captures into the public repository:

| Environment variable | Required external input |
| --- | --- |
| `HD2_RUNTIME_SOURCE` | Pinned Runtime 0.30.3 source above |
| `HD2_RUNTIME_SDK` | Its `sdk/` directory |
| `HD2_LUA51_DLL` | Installed game `bin/lua51.dll` |
| `HD2_MENU_API_SOURCE` | Mod Options Menu version 3 `components/ModOptionsMenu/src/api.lua`; keep its sibling source modules |
| `HD2_EVENT_NATIVES_SOURCE` | Runtime commit `75988a992141023e50fc0193f4b1de017d9e4b57`, `domains/event_natives.lua` |
| `HD2_HUD_PLUS_021_SOURCE` | HD2 HUD+ 0.2.1 extracted Lua resource `56E46A6DC1DF0A13.lua` |
| `HD2_HUD_PLUS_024_SOURCE` | HD2 HUD+ 0.2.4 extracted Lua resource of the same name |
| `HD2_DAMAGE_DATALIBRARY` | Filediver-extracted datalibrary for build `F5FEE03DCFDB`; tables and checksums are checked by `docs/damage-source-catalog.json` and Runtime's build profile |
| `HD2_RESEARCH_FIXTURES_ROOT` | Private historical research-fixture directory for legacy bughole/recon diagnostics, captured task-layout caller bytes and native contact-code packet checks; see below |

```powershell
python -X utf8 -B tools/test.py
```

Tests use owned memory and simulated native IO. They do not prove live-game coverage, frame rate or the accuracy of every attribution. Optional comparisons with older release ZIPs are skipped when those ZIPs are absent and are reported as skipped.

完整检查使用测试自有内存与模拟读数，不证明实战准确率或帧率。旧版本 ZIP 对照缺失时会明确记为跳过。

The legacy diagnostic checks require the original bughole diagnostic input, captured recon row descriptors, extracted locale strings, `task-module-update-58132.bin`, native contact-code packet directories and an externally obtained Overwatch locator profile under `HD2_RESEARCH_FIXTURES_ROOT`. Those captures and third-party packages are intentionally absent from this public snapshot. Without that external evidence, the full suite reports a missing input; it must not be described as passed. The core gameplay regressions and all `tests/fixtures/` source fixtures remain in the repository. Game code pins, resource IDs and non-identifying byte fixtures are retained because they are technical test inputs.

旧研究诊断用例依赖开发时的虫洞诊断、聊天行结构、游戏语言字符串及外部 HUD 定位资料。这些原始采样和完整第三方 MOD 不随源码公开；缺少时完整命令会报告输入缺失，不能声称全部通过。仓库保留核心回归和 `tests/fixtures/` 技术样本。

## Source and output boundaries / 源码与输出边界

`src/` contains production Lua. `tools/build.py` is the build entry, `tools/test.py` is the regression entry, and remaining diagnostic tools are specialist research utilities rather than end-user installers. Public source excludes local deployment/update scripts, accounts, save files, logs, browser caches and review HTML. Build outputs stay in ignored `build/` and `dist/` directories.

Metadata paths use repository-relative names or pinned upstream identities. Changing only those provenance paths requires corresponding whole-file checksum references to be refreshed; it does not justify changing game resource IDs, code pins, prices or artwork bytes. Licensing and source credits are in [THIRD-PARTY](../THIRD-PARTY.md), [NOTICE](../NOTICE) and [DATA-SOURCES](DATA-SOURCES.md).

## Ground-fire catalogue

`python -X utf8 -B tools/ground-fire-contexts.py --check` re-derives the 0.4.66 catalogue from the pinned Runtime and Filediver datalibrary above. It covers every positive explosion/projectile/component FireTemplate row, while enabling only eleven reviewed explosion events. It never reads a running game. The full regression includes the eleven-event built-addon replay.
