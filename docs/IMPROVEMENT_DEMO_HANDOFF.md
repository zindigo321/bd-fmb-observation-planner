# E3 / E4 与离线 Demo 交接

实际执行日期：2026-10-23，Asia/Shanghai。分支 `work/improvement-demo`，起点 `9765eb8`。继承已有贪心及改进构造，本轮增加冻结输入复用、固定物理故障入口、验证和演示；没有改动 `planner/scheduler.py`，没有调参或新增优化算法。main 保持原状。

## 先打开交付物

本轮根目录 `G:\bd-fmb\outputs\improvement_demo_20261023_150452`，以下简称 R。真实数据、目标标识、窗口、HTML 和截图均只在本地忽略目录。

- 可直接打开：`R\demo_delivery\index.html`；无需联网、HTTP 服务或重新求解。
- 三张实际截图：`R\browser_delivery\01_seed17_improved_overview.png`、`02_late_fault_history.png`、`03_late_replanned.png`。
- 对比：`R\experiments\comparison.csv`、`comparison.md`、`summary.json`。
- 分项最终验收：`R\acceptance.json`。`experiments\summary.json` 是生成 Demo 之前的实验快照，其中 Demo 的 NOT_RUN 被最终验收文件补充，未回写历史快照。
- 命令、起止、退出码、日志、预算：`R\run_ledger.json`。
- 每案例完整证据：`R\experiments\E3_seed42`、`E3_seed17`、`E3_seed23`、`E4_seed42_late`。
- 60—90 秒讲稿：[DEMO_SCRIPT.md](DEMO_SCRIPT.md)。无演示视频；视频不是本轮阻塞项。

## 实测对比

所有任务使用 2026-08-03 全天 UTC、三个站、各档20个目标。每 seed 的样本、窗口、候选和原物理事件均先冻结，再给两种方法运行；两者消费同一完整候选表。候选字节与原参考一致；冻结源与原始输入前后哈希一致。`frozen_inputs.json`、每案例 `input_reuse.json`、`event_provenance.json` 和 `summary.json.fairness` 是机器可检查证据。

E3 同 seed 的物理故障均为站点1、00:02—02:02 UTC；来源计划中的任务ID/影响列表仅保留作来源注释，各方法影响重新计算。四份计划均通过独立原始 TLE 两端及每个内部整数秒检查，全部零违例。

| seed | 方法 | 初始任务分 | 故障后任务分 | 初始收益 | 故障后收益 | 覆盖/全部 | 覆盖/可执行 | 初始/故障后违例 | 初始上界 | 距上界（初始/故障后） |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | --- |
| 42 | 基线 | 173.2 | 172.4 | 0 | 0 | 56/60，93.33% | 56/56，100% | 0/0 | 184.0 | 10.8/11.6 |
| 42 | 改进 | 184.0 | 184.0 | +10.8 | +11.6 | 56/60，93.33% | 56/56，100% | 0/0 | 184.0 | 0/0 |
| 17 | 基线 | 180.0 | 182.0 | 0 | 0 | 57/60，95% | 57/57，100% | 0/0 | 190.0 | 10.0/8.0 |
| 17 | 改进 | 190.0 | 190.0 | +10.0 | +8.0 | 57/60，95% | 57/57，100% | 0/0 | 190.0 | 0/0 |
| 23 | 基线 | 178.2 | 176.2 | 0 | 0 | 57/60，95% | 57/57，100% | 0/0 | 189.0 | 10.8/12.8 |
| 23 | 改进 | 189.0 | 189.0 | +10.8 | +12.8 | 57/60，95% | 57/57，100% | 0/0 | 189.0 | 0/0 |

上述覆盖率、分档覆盖在各案例两方法的初始及重规划结果均相同，故只列一次。可执行分母固定取全规划期存在合法120秒候选的目标数，不随故障缩小。

| seed | 目标/站 | 窗口 | 裁剪前/实际候选 | 高/中/低覆盖 | 数据与窗口准备秒 | 候选秒 | 两阶段独立校验合计秒 | 案例进程秒 |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: |
| 42 | 60/3 | 563 | 54699/10060 | 18/18/20 | 0.104207 | 0.148827 | 1.097638 | 2.230404 |
| 17 | 60/3 | 533 | 56685/9536 | 19/19/19 | 0.091672 | 0.146627 | 1.175994 | 2.243093 |
| 23 | 60/3 | 538 | 100072/9158 | 19/18/20 | 0.100722 | 0.163738 | 1.149018 | 2.264886 |

| seed | 方法 | 初始排程秒 | 重规划秒 | 已完成/锁定/中断/受影响未来 | 净调整目标 |
| --- | --- | ---: | ---: | --- | ---: |
| 42 | 基线 | 0.004036 | 0.012719 | 0/2/1/7 | 13 |
| 42 | 改进 | 0.141064 | 0.101614 | 0/2/1/5 | 7 |
| 17 | 基线 | 0.005196 | 0.009572 | 0/1/1/9 | 11 |
| 17 | 改进 | 0.095264 | 0.095637 | 0/1/1/5 | 7 |
| 23 | 基线 | 0.003513 | 0.011759 | 0/2/1/9 | 11 |
| 23 | 改进 | 0.093631 | 0.097046 | 0/1/1/7 | 11 |

计时来自 `perf_counter()`。E3/E4 的数据准备为封存窗口复用（`sealed_source_reuse`），不包含冷启动窗口传播；独立任务校验仍实际传播原始 TLE。每行改进耗时包括内部贪心回退成本。校验合计覆盖两方法；案例进程耗时包含启动、反例和证据写入，详见各案例 `timing.json`、`execution.json`；外层台账另计完整命令耗时，不重复累加子阶段。

上界由本轮候选重新计算：逐目标最高候选整数点求和，忽略站点资源冲突。此处是初始候选上界及对它的差值，不能解释成故障后精确上界或普遍最优性。E3 比较整套“初始排程＋重规划”流程，初始计划不同，收益不能单独归因于重规划器。三个种子仅作描述性比较。seed17 基线故障后涨分来自重新选择任务时长等变化，不代表故障有益。

## 较晚故障 E4

seed42、站点2；3783—10983相对秒，即01:03:03—03:03:03 UTC。事件在 `configs/late_fault.json`，未替换 E3。

| 方法 | 已完成 | 健康站锁定 | 故障站中断 | 受影响未来 | 初始/故障后分 | 故障后相对基线收益 | 初始/重规划秒 | 净调整 |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: |
| 基线 | 14 | 1 | 1 | 2 | 173.2/172.4 | 0 | 0.004244/0.008077 | 5 |
| 改进 | 10 | 1 | 1 | 4 | 184.0/184.0 | +11.6 | 0.111321/0.150969 | 18 |

两方法均覆盖56/60及56/56，高/中/低18/18/20；初始和重规划均零违例。E4准备0.116349秒、候选0.228923秒、独立校验合计1.164077秒、案例进程2.439516秒，窗口复用。基线移动/改时长5、保留51；改进移动/改时长18、保留38；两者新增/删除均0。变化按目标、站点、UTC起止和时长比较，忽略状态/任务ID变化，没有将取消后重排数量当作净调整。

`initial_frozen_<method>.json` 在初始排程后单独保存。独立校验器从该原计划推导应保留的完成、锁定和零分中断集合，不信任规划器自报历史，也不调用调度冲突函数。中断片段原计划结束/时长仍保存，实际占用参与资源校验。

真实攻击验证在 `R\history_security_v2`：每方法1个合法对照加7个攻击，共16项均满足预期。删除完成、删除锁定、删除或伪造中断、向故障前倒填 success/completed/locked 均被拒绝，并明确要求出现历史来源违例。基线找不到同时与重规划全部任务资源兼容的倒填候选，使用原合法窗口候选并保留额外资源违例；不声称该基线反例只违反历史约束。`backfill_resource_isolated` 标志及逐案报告可复核。原有合成隔离历史反例继续通过。

## 验收、环境与预算

| 环节 | 实际结果 | 证据（相对 R） |
| --- | --- | --- |
| 算法执行、候选和事件公平性 | PASS，4案例×4计划 | `experiments/summary.json`、各目录 manifest |
| 独立真实轨道合法性 | PASS，全部逐秒、零违例 | 各案例 `checks/` |
| 历史保护 | PASS，16个真实合法/攻击案例 | `history_security_v2/history_security.json` |
| 默认入口兼容 | PASS，四份旧格式任务CSV及候选CSV逐字节一致 | `delivery_verification/verification.json` |
| 只读复查 | PASS，56文件 SHA256 前后一致 | `recheck_late/recheck.json`、前后哈希文件 |
| 新目录复现 | PASS，四任务表及候选一致，重新逐秒校验 | `delivery_verification/workspace`、`result` |
| 自动测试 | 65通过（原43＋新增22），19.03秒 | `pytest_pass.xml`、`command_18.log` |
| Demo数据 | PASS，任务分/整数点/覆盖分母及分档/校验报告核对 | `demo_delivery/demo_data_check.json` |
| Demo实际浏览器交互 | PASS，33检查、3截图、无运行异常 | `browser_delivery/browser_checks.json` |
| 原始数据和三个旧源目录 | PASS，前后哈希一致 | `acceptance.json`、各 `input_reuse.json` |
| 1号数据交付、3号确认 | PENDING_EXTERNAL | 未收到、未发送消息 |
| 旧额外复评 | BLOCKED | 原SHA256及事件契约问题仍隔离 |
| 干净环境安装、视频 | NOT_RUN | 未声称完成 |

浏览器用本机 Chrome，通过 DevTools 真正操作全部4案例×2方法×3视图，另检查晚故障seed限制、缩放、任务点击、分步、播放、暂停、窄屏无页面级溢出。页面在离线网络条件下打开本地文件；正常使用无需 Node。截图已人工查看，初始任务、锁定/中断和重规划视图可辨。

本轮27条串行计算/测试命令累计147.226秒，600秒预算剩余452.774秒；21条PASS、6条FAIL，均保留日志，未有预算超时。本轮预算是新授权，不是旧额外复评延时。每条均由 Windows Job Object 限制进程树，单次上限不超过300秒及当时剩余预算。

保留的失败：第8条历史脚本未找到资源隔离候选；第10/12/13条浏览器连接、Chrome沙箱兼容及SVG点击调用问题；第16条pytest系统临时目录权限；第17条合成窗口运行缺缓存说明。分别修复夹具断言、浏览器连接/输入方式、改用项目临时目录、补全窗口模式缓存说明后验证通过。未将普通错误写成BLOCKED，未覆盖失败目录。

默认入口回归发生真实缓存未命中，窗口传播25.623秒，外层命令29.084秒；没有强行改缓存身份。新目录复现使用相同已安装环境和只读准备产物，不等同于干净环境安装。`requirements-dev.txt` 固定实测pytest9.1.1；本轮没有安装或升级包。原未跟踪 `requirements-lock.txt` 字节及未跟踪状态保持。

## 可复制命令

现有环境直接运行；全新环境的最小依赖安装说明如下，本轮没有执行安装：

```powershell
Set-Location G:\bd-fmb
$py = 'D:\conda_envs\bd-fmb\python.exe'
# 仅新环境需要；运行只需 requirements.txt，测试使用 requirements-dev.txt
& $py -X utf8 -m pip install -r requirements-dev.txt
```

复现实验需要本地原始输入，以及 `configs/improvement_demo.json` 指向的三个封存旧结果。缺少这些文件不会用同一窗口改seed冒充复现；新克隆可先运行 [合成示例](../demo/README.md)。以下命令在新目录建立新一轮600秒台账，不重用已完成的本轮台账：

```powershell
Set-Location G:\bd-fmb
$py = 'D:\conda_envs\bd-fmb\python.exe'
$r = 'outputs/reproduce_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
& $py -X utf8 scripts/run_improvement.py --spec configs/improvement_demo.json --out "$r/experiments" --ledger "$r/run_ledger.json"
if ($LASTEXITCODE -ne 0) { throw '实验未通过，先查看台账与日志' }
& $py -X utf8 scripts/budget_run.py --ledger "$r/run_ledger.json" --timeout 60 --output "$r/recheck" -- $py -X utf8 smoke_test.py --check-only --source "$r/experiments/E4_seed42_late" --out "$r/recheck"
if ($LASTEXITCODE -ne 0) { throw '只读复查未通过' }
& $py -X utf8 scripts/budget_run.py --ledger "$r/run_ledger.json" --timeout 60 --output "$r/demo" -- $py -X utf8 scripts/build_demo.py --summary "$r/experiments/summary.json" --out "$r/demo"
if ($LASTEXITCODE -ne 0) { throw 'Demo证据未通过' }
Start-Process (Resolve-Path "$r/demo/index.html").Path
```

只从已经交付的结果生成新Demo，不重新计算轨道：

```powershell
$py = 'D:\conda_envs\bd-fmb\python.exe'
$source = 'G:\bd-fmb\outputs\improvement_demo_20261023_150452\experiments\summary.json'
$htmlOut = 'G:\bd-fmb\outputs\demo_copy_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
& $py -X utf8 G:\bd-fmb\scripts\build_demo.py --summary $source --out $htmlOut
if ($LASTEXITCODE -eq 0) { Start-Process "$htmlOut/index.html" }
# 已交付HTML可直接打开：
Start-Process 'G:\bd-fmb\outputs\improvement_demo_20261023_150452\demo_delivery\index.html'
```

以下可选复核命令接续上面的新 `$r`，逐条执行并检查退出码。所有输出目录须全新，pytest也使用新basetemp，避免权限问题或清理既有临时目录：

```powershell
& $py -X utf8 scripts/budget_run.py --ledger "$r/run_ledger.json" --timeout 120 -- $py -X utf8 -m pytest tests -q --basetemp="$r/pytest_tmp" --junitxml="$r/pytest.xml"
& $py -X utf8 scripts/budget_run.py --ledger "$r/run_ledger.json" --timeout 60 --output "$r/history" -- $py -X utf8 scripts/verify_late_history.py --source "$r/experiments/E4_seed42_late" --out "$r/history"
& $py -X utf8 scripts/budget_run.py --ledger "$r/run_ledger.json" --timeout 60 --output "$r/browser" -- node scripts/browser_demo_test.mjs "$r/demo/index.html" "$r/browser"
```

自动浏览器测试需要 Node24 和本机Chrome（默认 `C:/Program Files/Google/Chrome/Application/chrome.exe`）；使用Edge时，在HTML及输出目录参数之后追加浏览器exe路径。测试专用的 `--no-sandbox --disable-gpu` 仅用于本机生成页面的受控自动化，外层预算入口终止整个进程树；正常打开HTML不需要这些参数。

`--reuse-source` 与 `--fault-event` 仅用于普通运行。后者严格检查整数站点/相对秒、站点存在、区间合法及UTC一致；`--event` 仍仅用于外部任务评价，误用于普通运行会返回FAIL。默认入口不传新选项，行为保持原样。

## 给3号、4号和队长

3号可用 `smoke_test.py` 统一入口或现有 `schedule()` 接口，读取任务CSV、`fault_impacts.json`、`changes_<method>.json` 和逐计划 `checks/*.json`；按0成功、2失败、3阻塞处理，不能只看文件存在。输入输出契约继续见 [io_contract.md](io_contract.md)。需外部确认1号交付数据版本、窗口过滤、成功次数与中断口径、实际接入命令；当前仅提供可审阅产物，没有代对方确认。

4号和队长可直接使用离线HTML、三张截图、讲稿和本页对比表，讲明冻结样本、任务分口径及全流程比较。真实产物不在Git，转交时由用户按团队渠道处理；本轮未发送消息或上传真实数据。

真实轨道几何冒烟演示，完整光学条件未验证。夜间、受光、日月规避、天气、跟踪、视场、地形及状态估计仍不在验证范围。窗口网格与逐秒检查不是连续时间/窗口完备性证明；任务分不是正式百分制。未扩大目标规模、未做压力扫描、云端演化或旧额外复评修复。
