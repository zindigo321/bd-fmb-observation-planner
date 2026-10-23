# 离线实验回放

`template.html` 是生成器模板，数据来自本轮任务 CSV、独立校验报告及指标；直接打开模板没有实验数据。真实生成物保存在忽略的 `outputs/`，不要提交 HTML、截图、目标或窗口 JSON。

已有真实实验结果的生成、打开及截图命令见 [交接说明](../docs/IMPROVEMENT_DEMO_HANDOFF.md)。HTML 自包含，无 CDN、HTTP 服务或浏览器现场求解；打开时不运行 Python。

新克隆没有真实数据时，可使用仓库已有合成输入。这是 06:00 UTC 开始、1 小时、站点 7/9 的小契约示例，不是真实几何结果：

```powershell
Set-Location G:\bd-fmb
$py = 'D:\conda_envs\bd-fmb\python.exe'
& $py -X utf8 smoke_test.py --config configs/synthetic.yaml --out outputs/demo_synthetic_run
& $py -X utf8 scripts/build_demo.py --summary configs/demo_synthetic.json --out outputs/demo_synthetic_html
Start-Process (Resolve-Path outputs/demo_synthetic_html/index.html).Path
```

目录须全新；重新演示请为运行目录和 HTML 目录换名，并同步 `configs/demo_synthetic.json` 的 `directory`。该 JSON 只含合成运行路径，不含真实数据。

错误证据会生成可解释的 FAIL/BLOCKED 页面，并隐藏正常指标区域。生成器返回码：成功 0、无完整证据 3、证据内容不一致 2；已存在目录和源目录嵌套直接拒绝，不覆盖源证据。

可选自动浏览器测试使用本机 Node 24 与 Chrome/Edge，无 npm 依赖。它针对完整 E3/E4 页面；合成示例由 pytest 验证数据和状态。测试器通过本机 DevTools 接口加载 `file://` 页面，并启用离线网络条件；只为受控本地页面使用 `--no-sandbox --disable-gpu`，外层预算入口负责终止浏览器进程树。用户正常打开 HTML 无需这些启动参数。
