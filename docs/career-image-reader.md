# 真实生涯截图的本地读取

已经可以在本机从简体中文生涯截图读取总击杀、三族击杀、死亡次数，生成可复核的 JSON。它使用 Windows 内置中文 OCR（图像中文字识别），不上传图片、不需要账户密钥、不读取游戏内存，也不改生涯基准。

这一步是截图读取，**尚不是上舰后自动同步**。飞船场景本身没有显示这些数字；真实生涯页、截图归属及同期 MOD 历史锚点仍需要在后续自动流程中连接。

## 使用

将生涯截图文件拖到项目根目录的 `读取生涯截图.cmd` 上。该图片须同时显示“敌方击杀数”、三族击杀数和“死亡次数”；当前版本不合并不同时间／上下两张截图。

命令行等效操作，在 `.` 运行：

```powershell
& 'external/python.exe' -X utf8 'tools/read-career-image.py' 'C:/完整路径/生涯截图.png'
```

结果位于 `dist/career-image-reader`：原始 OCR 词与位置、图像 SHA256、五项数字及标签配对证据。原图不修改。`ready_to_sync=false` 表示这只是待核对记录，不能直接传给旧 `sync-career-kd.py` 替换当前账号。

缺少标签、数值跨行、标签重复、多列混淆、千位分组不合规、三族之和与总击杀不一致时拒绝输出统计结果；不会猜测缺失数字。OCR 可能识错，几何和总和检查不能证明账号归属、截图日期或所有数字一定正确。

## 本轮验证

已对用户原始生涯图片实际运行 Windows OCR：351849 总击杀、308255 终结族、23438 机器人、20156 光能者、4633 死亡，与用户此前确认一致。11 个解析场景通过，包含真实 OCR 的保留词框、缺死亡、跨列、结算页、重复标签、同排额外数字、千分组错误、跨行数字及逗号附着的跨行变体。

本轮没有将新工具装进游戏，正式 0.4.13 的 KD、账目与其他 MOD 不由本工具修改。截图识别耗时不是游戏 FPS 测试。

参考：[HD2Stats 作者说明](https://hd2stats.heliohost.us/hd2stats.php?mode=help)、[Melchior 作者说明](https://hd2clans.com/news/33)、[微软官方 OCR 示例](https://github.com/microsoft/Windows-universal-samples/blob/4eb2fcb499c5bc549e918920cfd2b64396a650d9/Samples/OCR/cs/OcrFileImage.xaml.cs)。本项目实现只调用系统 API，没有复制示例代码；原始参考副本与 MIT 许可留在研究目录。
