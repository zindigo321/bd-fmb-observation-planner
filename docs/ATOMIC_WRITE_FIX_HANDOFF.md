# 临时文件硬链接修复交接（2026-10-23）

本轮从 `work/path-safety-replan-e5` 的 `b504f93` 创建 `work/atomic-write-hardening`，修复原子写入对预植入硬链接的截断问题。未修改调度器、候选生成、独立校验器、算法参数或 Demo 界面。原分支及 main 保留；最终提交与远端推送回执见本轮本地 `delivery_git.json` 和交付回复。

本轮唯一产物根目录：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047`（下文 R）。真实控制台账为 `R\control\run_ledger.json`，与所有攻击夹具分离。提示词的后续指定保存位置为项目外 `G:\bd-fmb_local\handoff`；本轮没有向旧 `_local/handoff` 写入新提示词，工程代码和交付文档留在项目中。

## 修复前后证据

原 `guard_writes([ledger.tmp], [raw_directory])` 只比较目录路径关系及两个端点的 samefile，无法识别目录外的硬链接指向目录内部文件。预算保存随后以固定 ledger.tmp 截断写入，即使后续 CLI 返回 2，输入也已损坏。直接文件保护测试不能覆盖这个目录级缺口。

本轮只对合成的 `raw/input.txt` 创建硬链接，未给任何真实输入、配置或历史产物创建攻击链接。两条路径为 `R\before_fix\budget_execute\{raw\input.txt,ledger.tmp}` 和 `R\before_fix\full_experiment_cli\{raw\input.txt,ledger.tmp}`；修复后在独立 `after_fix` 下重新创建同构夹具。

| 实际调用 | 修复前 | 修复后 |
| --- | --- | --- |
| 预算 execute，保护 raw 目录 | samefile=true；guard ALLOWED；故意失败命令返回2；原始文本变成台账JSON，旧alias被移走 | samefile=true；guard ALLOWED；原子保存成功；故意失败命令仍返回2；raw完整树及旧alias保持 |
| run_improvement.py 完整入口，保护 raw 目录 | prepare成功，故意不完整配置随后返回2；原始文本已变成台账JSON | prepare成功，后续同样返回2；raw完整树/哈希及旧alias保持，三个合成封存源不变 |

原合成文本SHA256为 `dc7299a5dd1289ef57bac22a5c720a2089af8cbcf437bb7a5b8f9751af02a19d`。修复前预算例变成 `8eb610ad03bf692726835778adccafee04aac97f6867fe837f08235d9599c6b4`，完整入口例变成 `2e5dcd4c7254201b1efc82205e25b11bd84d047117412cdc92c5528119789f74`。修复后两例前后均保持原哈希，旧alias仍samefile=true。完整命令、两条实际路径、退出码、内容片段及含空目录的前后树在 `before_fix/reproduction.json`、`after_fix/reproduction.json`；修复前源文件副本另存 `budget_run_before.py`、`common_before.py`。

修复后是安全完成原子保存，不把故意失败的合成实验解释为算法PASS。已有具体文件别名或封存目录的预检仍可以提前拒绝，原14项P1路径测试未删改。

## 实现与写入点

新增 `planner/atomic_io.py`：目标同目录 `tempfile.mkstemp` 独占创建，以返回的fd经 `os.fdopen` 写入，关闭句柄后 `os.replace`。不打开固定旧临时路径，不提前删除未知文件。fdopen失败会关闭原fd；序列化、部分写入、关闭或替换异常均不发布不完整目标，并只清理本次拥有的临时路径。清理失败附到原异常note并继续抛出；保留原错误，绝不当作成功。

`planner/common.py` 的JSON/CSV、`scripts/budget_run.py` 的所有save分支改用该实现；`scripts/run_improvement.py` 可重复汇总的comparison.md也改为安全替换。保留旧临时名保守预检，但它们不再是实际写入目标。已有直接文件硬链接、目录联接、封存、日志、预算与进程树保护保留。

JSON保留UTF-8、两空格缩进、插入键序、原换行和公共API的allow_nan=False；台账沿用原序列化参数。CSV保留fields次序、extrasaction=ignore、newline=''及原字节。新增目标和更新合法目标均通过测试；现有目标本身为合成输入硬链接时，替换只断开该目标名，原输入仍不变。

完整生产调用清单在 `R\write_inventory.md`。未改的直接写入主要属于受控全新结果目录中的launch/exception/log/HTML/截图等；没有将所有新文件写入扩成安全框架。本轮验证串行场景，不宣称抗并发恶意目录替换、断电持久性或跨平台认证；未增加依赖。

## 本轮实跑结果

| 验收项 | 实际结果及证据 |
| --- | --- |
| 自动测试 | 117 passed，0 failed / errors / skipped；原94+新增23，pytest报告28.86秒，外层29.326782秒；`pytest.xml`、`control/command_03.log` |
| 实际Windows链接 | 硬链接使用G盘os.link；Windows目录junction测试实际执行，没有跳过 |
| 异常与预算 | JSON非有限/不可序列化、CSV流式失败、fdopen/部分写入/replace失败、清理失败有用异常、原目标和输入保持；预算开始/完成、命令FAIL、超时BLOCKED、进程启动异常、保存失败留下RUNNING并拒绝续跑均覆盖 |
| E5共同条件 | 14完成/1锁定/1中断/2受影响未来，共同未来候选6839；方法前后共享条件与输入保持 |
| E5字节兼容 | 两份schedule CSV与PREV/E5_common_baseline逐字节一致；`csv_regression.json` |
| E5独立复核 | 专用check-only重新实际检查，33文件/3目录完整树及SHA256不变；`E5_recheck/recheck.json` |
| E3/E4真实回归 | 4案例16计划均原始TLE逐整数秒及两端检查PASS、0违例；16任务CSV+4候选CSV与OLD逐字节一致 |
| Demo | 从本轮新E3/E4生成，数据检查PASS；Chrome离线交互33项PASS、0运行异常，三张实际截图已逐张查看；没有E5新界面 |
| 旧资料保护 | 原始raw、三个旧封存源、OLD整树、PREV整树、requirements-lock.txt、.gitignore全部前后不变，包含空目录；`protected_before.json`和`protected_after.json` |
| 封存/编译 | 六个新封存结果目录清单有效，无本次临时文件；改动Python文件编译通过，哈希在acceptance.json |

E5本次数据：

| 方法 | 最终分 | 固定历史/新任务 | 覆盖（全部/可执行） | 违例 | 净调整 | 重规划秒 | 独立验证秒 | 条件上界 |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 172.4 | 51.0/121.4 | 56/60 · 56/56 | 0 | 5 | 0.003321 | 0.330995 | 182.0 |
| improved | 182.0 | 51.0/131.0 | 56/60 · 56/56 | 0 | 23 | 0.070897 | 0.326955 | 182.0 |

收益9.6，来自既有算法；本轮I/O修复没有提升分数。共同初始文件SHA256仍为 `1b37fab094cb6b2a9f0d99aa92d0c018d8ad02a4de14e42f1aba831b1963ec8c`，共同条件SHA256为 `585404b8222cdcacc53127826603515a5a11be1ca2efc446cc975ff994db8d67`。单次内部总计2.326887秒，外层3.156530秒。条件上界忽略资源冲突；Demo展示的是E3/E4整体流程，不应将旧E4不同初始计划的11.6分收益混为E5收益。

E3三种子故障后基线/改进仍为42：172.4/184.0，17：182.0/190.0，23：176.2/189.0；E4较晚故障仍172.4/184.0。真实输入、ID、TLE、站址、窗口、HTML、截图、台账和攻击夹具只在本地忽略目录，不进入Git。

## 预算、失败与边界

本轮唯一600秒台账15条串行受控命令共 **81.018276秒**，余 **518.981724秒**；15条外层命令均按预期PASS，没有外层意外失败或超时。修复前两个实际调用的退出2和输入损坏如实保留；修复后的合成配置/命令退出2、测试中故意FAIL/BLOCKED/保存故障是验证对象，未伪装成算法成功。所有夹具内部台账只作被测数据，耗时包含在外层命令，不扩充预算。单条上限不超过300秒及剩余额度；阅读、编辑、文档、权限等待不计入计算预算。

旧额外复评继续BLOCKED，本轮未改契约或运行该复评；1号实际交付和3号确认仍PENDING_EXTERNAL，未发送消息。未做干净安装、完整光学验证或正式评分；不增加新算法、参数扫描或第二E5起点。此前独立历史攻击16例属于旧轮证据，本轮不重复宣称新执行16例；本轮新执行的117项测试含原E5历史与公平性回归。

环境清单仍未跟踪且被忽略，SHA256为 `03471313d71afce5590dc529b8adf38f2f6c8a94704a95e01ad8823feba0856c`；`.gitignore`原规则未变。分项状态与源码哈希详见 `R\acceptance.json`。

## 可复制PowerShell命令

下面为后续人工复核使用的新目录和独立600秒台账，本轮没有再执行一遍这些命令。每段失败应停止排查；现有真实原始数据及OLD封存产物是必要输入，新克隆不会自带。

```powershell
Set-Location 'G:\bd-fmb'
$py = 'D:\conda_envs\bd-fmb\python.exe'
$r = 'G:\bd-fmb\outputs\atomic_write_fix_20261023_182047'
$v = Join-Path 'G:\bd-fmb\outputs' ('atomic_manual_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$ledger = Join-Path $v 'control\run_ledger.json'

# 测试：新的basetemp，复用本次人工复核唯一台账
& $py -X utf8 scripts/budget_run.py --ledger $ledger --timeout 120 -- $py -X utf8 -m pytest tests -q --basetemp "$v\pytest_tmp" --junitxml "$v\pytest.xml"
if ($LASTEXITCODE -ne 0) { throw 'pytest failed' }

# 重新验证目录级硬链接反例的修复结果：只攻击新建合成夹具
& $py -X utf8 scripts/budget_run.py --ledger $ledger --timeout 60 -- $py -X utf8 "$r\reproduce_atomic.py" --out "$v\hardlink_probe" --expect safe
if ($LASTEXITCODE -ne 0) { throw 'hardlink probe failed' }

# E5真实复现；入口自身计入同一台账，不再套一层budget_run
& $py -X utf8 scripts/run_replan_e5.py --source outputs/improvement_demo_20261023_150452/experiments/E4_seed42_late --initial-plan outputs/improvement_demo_20261023_150452/experiments/E4_seed42_late/initial_frozen_baseline.json --event configs/late_fault.json --out "$v\E5" --ledger $ledger --budget-seconds 120
if ($LASTEXITCODE -ne 0) { throw 'E5 failed' }
& $py -X utf8 scripts/run_replan_e5.py --check-only --source "$v\E5" --out "$v\E5_recheck" --ledger $ledger --budget-seconds 120
if ($LASTEXITCODE -ne 0) { throw 'E5 recheck failed' }

# E3/E4与Demo；每个产物目录必须新建
& $py -X utf8 scripts/run_improvement.py --spec configs/improvement_demo.json --out "$v\experiments" --ledger $ledger
if ($LASTEXITCODE -ne 0) { throw 'E3/E4 failed' }
& $py -X utf8 scripts/budget_run.py --ledger $ledger --timeout 60 -- $py -X utf8 scripts/build_demo.py --summary "$v\experiments\summary.json" --out "$v\demo"
if ($LASTEXITCODE -ne 0) { throw 'Demo build failed' }
& $py -X utf8 scripts/budget_run.py --ledger $ledger --timeout 60 -- node scripts/browser_demo_test.mjs "$v\demo\index.html" "$v\browser"
if ($LASTEXITCODE -ne 0) { throw 'browser checks failed' }

# 查看已经交付的本轮Demo；也可把$r替换为$v查看人工复核的新Demo
Start-Process "$r\demo\index.html"
```

## 关键产物完整路径

- 分项验收：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\acceptance.json`
- 写入点清单：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\write_inventory.md`
- 修复前/后：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\before_fix\reproduction.json`、`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\after_fix\reproduction.json`
- 测试：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\pytest.xml`
- E5表格：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\E5_common_baseline\comparison.csv`
- 只读复核：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\E5_recheck\recheck.json`
- 字节回归：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\csv_regression.json`
- E3/E4表格：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\experiments\comparison.csv`
- Demo：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\demo\index.html`
- 浏览器报告/截图：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\browser\browser_checks.json`及同目录`01_seed17_improved_overview.png`、`02_late_fault_history.png`、`03_late_replanned.png`
- 前后完整树：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\protected_before.json`、`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\protected_after.json`
- 唯一台账：`G:\bd-fmb\outputs\atomic_write_fix_20261023_182047\control\run_ledger.json`
