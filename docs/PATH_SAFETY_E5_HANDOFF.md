# P1目录保护修复与E5同初始计划重规划交接

执行日期：2026-10-23，Asia/Shanghai。起点 `97d41e6`，分支 `work/path-safety-replan-e5`。P1独立提交 `341ac9e`；E5、测试和本说明在后续提交。没有修改main、原算法、独立校验器或真实旧数据。

本轮根目录 R：`G:\bd-fmb\outputs\path_safety_e5_20261023_164001`。旧交付 OLD：`G:\bd-fmb\outputs\improvement_demo_20261023_150452`。真实产物全部留在忽略目录，仓库只提交源码、合成测试与说明。

## P1：先复现，再验证修复

修复前实际将 `outputs/E0_seed42` 复制到 `R\before_fix\sealed_source_copy`，对副本调用旧总入口并指定其内部 `nested_output`。原CLI返回2，但新增了输出目录、snapshots空目录/事件文件、`frozen_inputs.json`。证据为 `R\before_fix\reproduction.json`，含完整前后树、命令、退出码及旧代码哈希；旧脚本、stderr/stdout与夹具内部台账保留。没有对真实封存源做破坏性反例。

修复在 `planner/path_safety.py`、`scripts/run_improvement.py`、`scripts/budget_run.py`：

- 使用实际解析后的Path、路径祖先关系和存在文件的samefile身份检查，覆盖相对路径、`..`、Windows大小写、目录联接及文件别名，不用字符串前缀判定。
- 总入口在创建任何目录/台账/日志前，读取所有seed的源、当前及来源配置，收集原始输入、冻结样本、配置、规格和事件文件。检查输出、缓存、台账、原子临时文件及本轮所有自动日志位置。
- `--prepare` 自己也预检，并独占创建全新实验根目录；总入口不再提前创建根目录。台账放在实验根目录之外，通常是其父目录，原交付命令结构保持可用。
- 汇总逐一检查实际CSV/Markdown/JSON及临时写入位置，允许父目录汇总，拒绝封存案例内部或解析到受保护输入的目标。预算入口在自己的首次mkdir之前也检查实际台账、临时文件和日志。
- 非法路径返回FAIL/2并写stderr，不创建目录或空目录。目录联接解析和链接身份检查不构成对恶意并发替换链接的原子防护；本轮没有并发修改输入。

修复后对新的完整源副本重做同一攻击，CLI仍返回2，但整个夹具树及文件哈希完全不变，连台账/输出根也未创建。证据：`R\path_fix_verification.json`。14项新增路径测试包含第一/第二/第三源、相等/内部/`..`/大小写、原始输入、非法台账、自动日志和原子临时文件硬链接、直接prepare、封存位置汇总、相邻前缀合法输出、真实Windows目录联接。全部实际通过，没有跳过联接测试。最后还单独验证了E5验收汇总器拒绝封存位置，证据 `R\final_code_checks.json`。

## E5固定共同起点

权威来源是 `OLD\experiments\E4_seed42_late\initial_frozen_baseline.json`，与同目录 `schedule_baseline.csv` 完整任务语义交叉检查，并独立重算为173.2分、56个目标。没有重新生成两种方法各自的初始计划。

使用seed42的60目标、站点1/2/3、2026-08-03全天UTC、10060个冻结候选。物理事件为站点2、`[3783,10983)`，即01:03:03—03:03:03 UTC。实际推导并冻结一次共享完成/锁定/中断历史及未来候选，再为两方法提供独立内存副本。每方法调用前后均验证内容及顺序哈希，来源不一致也拒绝。

共同输入哈希如下。语义哈希采用UTF-8、键排序、紧凑JSON，列表保留原顺序；整体条件哈希还包含来源路径，因此迁移目录可能改变来源/整体哈希，不影响单项任务语义哈希。

| 内容 | SHA256 |
| --- | --- |
| 共同初始JSON原文件字节 | `1b37fab094cb6b2a9f0d99aa92d0c018d8ad02a4de14e42f1aba831b1963ec8c` |
| 共同初始计划语义 | `c68cda7770c5baea117199b77059d1237302cf40322a13583f42a4c5ffef7037` |
| 事件语义 | `fe2fc5e3dc76aedbc721d4f1289cd0579685ad96477260962b0ff9ba9affca2c` |
| 完整候选语义 | `e242dddb7dc0b69892328aecf5090455e10fe73b02f2f44735a3f725fb3ee407` |
| 未来候选语义 | `1fa13c6cff72706e706130aeb8b7cfe59eb28ca22c903b652a06471b164b5c18` |
| 固定成功历史语义 | `5f12d96af1c7a42bccec0926d5b443cb1cdc7fcbe36c6f70efab026c4907330a` |
| 中断历史语义 | `b8020956192d1acbaa1020146ef62d8aa29ad2822c6850dfde22e38b2d02db65` |
| 共同条件整体 | `585404b8222cdcacc53127826603515a5a11be1ca2efc446cc975ff994db8d67` |

机器证据：`R\E5_common_baseline\shared\contract.json`、`common_inputs.json`、`conditions_baseline.json`、`conditions_improved.json`。共享快照与权威源前后不变；方法不能替换共同初始计划、自报历史或悄悄换候选。

## E5本轮实际结果

两方法共有14项完成、1项健康站锁定、1项故障站中断、2项原未来任务受影响。固定成功历史15项、51.0分；中断零分，仍参与实际占用校验，可在以后重新完整观测。

| 方法 | 最终总分 | 固定历史分 | 新任务分 | 覆盖/全部 | 覆盖/可执行 | 高/中/低覆盖 | 违例 | 重规划秒 | 独立验证秒 | 净调整 |
| --- | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: |
| baseline | 172.4 | 51.0 | 121.4 | 56/60，93.33% | 56/56，100% | 18/18/20 | 0 | 0.003326 | 0.330910 | 5 |
| improved | 182.0 | 51.0 | 131.0 | 56/60，93.33% | 56/56，100% | 18/18/20 | 0 | 0.083727 | 0.391897 | 23 |

同起点收益为 `(910−862)/5 = +9.6` 分。基线新增0、删除0、移动/改时长5、保留51；改进新增0、删除0、移动/改时长23、保留33。比较忽略纯状态或任务ID变化。两方法完成/锁定/中断历史均由独立校验从共同原计划推导并完整匹配。

条件宽松上界为182.0分＝固定历史51.0＋未固定目标的未来候选逐目标最高分131.0；固定成功目标不重复计分，中断目标可进入未来候选，忽略资源冲突。基线距上界9.6，改进距上界0。本场景结果不能宣称所有重规划场景更优或普遍最优；旧184分不是这个共同历史约束下的必达成绩。

输入读取及校验器准备0.097736秒；共同初始计划独立验证0.273137秒；共享历史/未来候选准备0.002353秒；内部总耗时2.430907秒；包含进程启动的外层命令3.196393秒。源封存哈希、快照序列化等成本包含在总耗时中。方法耗时仅包含各自schedule调用；输入复制、读写、哈希和独立验证在方法计时之外。改进包含内部基线回退。以上均为单次perf_counter观测，不宣称统计显著的速度优势。

完整结果：`R\E5_common_baseline\comparison.csv`、`comparison.md`、`summary.json`。逐方法任务、中断表、变化明细、独立报告、配置、版本及共享初始计划均在同目录，封存清单为 `evidence_manifest.json`。

给4号可直接引用的结论：**在seed42、共同基线初始计划及同一较晚故障下，已有改进重规划得到182.0分，相比基线172.4分提升9.6分；覆盖相同、历史完整、逐秒独立校验零违例，但净调整由5增至23，单次重规划耗时也更高。**

## 本轮验收与未做事项

| 验收 | 实际结果与证据（相对R） |
| --- | --- |
| 全部测试 | 94通过、无跳过，原65＋路径14＋E5条件/历史15；`pytest_e5.xml`，25.92秒 |
| 共同条件防伪 | 初始、来源、事件、固定/中断、完整/未来候选任一不一致均拒绝；方法输入被修改也拒绝 |
| E5独立合法性 | 两份新计划均原始TLE两端及内部每个整数秒检查；窗口、故障占用、资源、30秒切换、唯一成功、原始优先级计分及精确历史全通过 |
| E5真实历史攻击 | `E5_history_security_final/history_security.json`；16个合法/攻击案例满足预期，另有共同来源不一致拒绝。所有攻击在完整副本及独立内存副本中进行 |
| 真实倒填反例范围 | 倒填候选单独通过真实TLE/窗口合法性；不声称与全部计划资源隔离，且每个攻击必须实际触发历史来源违例 |
| E5只读复核 | `E5_recheck/recheck.json`；33文件、3目录完整树前后一致，重新独立校验初始及两新计划 |
| E3/E4回归 | 4案例16计划重新实际运行，真实TLE通过；16份旧格式任务表及4候选表字节一致；`e3_e4_regression.json` |
| Demo新生成路径 | 从本轮新E3/E4产物重新生成`demo/index.html`，数据检查PASS，33项实际Chrome交互通过；`browser/browser_checks.json`和3张截图 |
| 旧资料整体保护 | OLD整轮产物含旧HTML、三个原封存源、原始输入、requirements-lock.txt及.gitignore完整树/哈希不变；`protected_before.json`、`protected_after.json` |
| 编译及最后补充验证 | PASS；`final_code_checks.json`，台账第17、19、20条 |
| 外部确认 | 1号交付、3号接口确认仍PENDING_EXTERNAL；未发送消息或代替团队确认 |
| 旧额外复评 | BLOCKED；没有修改契约、没有延期旧预算 |
| 可选第二共同起点 | NOT_RUN；本轮只报告要求的共同基线起点，不混合两组结果 |
| 干净安装、完整光学、正式评分 | 未验证；不声称完成 |

Demo仍展示E3/E4整体流程，E5以独立表格交付，不能把页面旧E4的+11.6分转述为E5收益。新截图已查看，旧HTML字节未变。全部验收门槛分开见 `acceptance.json`，最后脚本补充验证见 `final_code_checks.json`。

本轮唯一预算台账 `R\run_ledger.json`：20条串行受控命令共152.042秒，600秒余447.958秒；均按各自预期完成。修复前被审计的旧CLI实际退出2且污染副本，作为反例如实保存；第1条外层验证命令因成功复现该缺陷而返回0。夹具内部旧台账仅是被测旧入口产物，其全部耗时已包含在第1条，不用于另行扩充预算。阅读、编辑、权限审核等待和写作时间不计入计算预算。没有环境安装/升级，没有扩大样本或参数扫描。

## 给3号：运行、输入输出与退出码

所有命令从 `G:\bd-fmb` 执行，使用现有解释器，不要求安装新依赖。0为通过、2为失败、3为输入缺失或预算阻塞。每个结果目录必须新建，台账位于结果根目录之外；已有结果不覆盖。

E5来源必须是已封存、可回溯原始输入的真实TLE案例。`--initial-plan`接共同JSON，默认来源的`initial_frozen_baseline.json`；`--event`接固定事件，本入口的参数独立于旧smoke_test.py的运行/评价模式。初始计划必须匹配来源的基线CSV，事件必须匹配来源的较晚物理事件；两方法无单独初始计划或事件参数。可选`--reference-method improved`是另一个共同起点，本轮未执行，不应将两起点混作一组。

以下在新目录/新600秒台账复现测试、E5和只读复核。已有本地原始数据与OLD产物是必要输入；新克隆不含它们。

```powershell
Set-Location G:\bd-fmb
$py = 'D:\conda_envs\bd-fmb\python.exe'
$r = 'outputs/e5_reproduce_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
$old = 'outputs/improvement_demo_20261023_150452/experiments/E4_seed42_late'

& $py -X utf8 scripts/budget_run.py --ledger "$r/run_ledger.json" --timeout 120 -- $py -X utf8 -m pytest tests -q --basetemp="$r/pytest_tmp" --junitxml="$r/pytest.xml"
if ($LASTEXITCODE) { throw '测试未通过' }

& $py -X utf8 scripts/run_replan_e5.py --source $old --initial-plan "$old/initial_frozen_baseline.json" --event configs/late_fault.json --out "$r/E5" --ledger "$r/run_ledger.json"
if ($LASTEXITCODE) { throw 'E5未通过，查看台账与失败证据' }

& $py -X utf8 scripts/run_replan_e5.py --check-only --source "$r/E5" --out "$r/recheck" --ledger "$r/run_ledger.json"
if ($LASTEXITCODE) { throw '独立复核未通过' }

Import-Csv "$r/E5/comparison.csv" | Format-Table method,final_score,fixed_history_score,new_tasks_score,coverage,violations,replan_seconds,net_adjusted_targets
Get-Content "$r/E5/comparison.md" -Encoding UTF8
```

E5采用`shared_initial_replanning_v1`格式，两份schedule都是重规划结果，初始只保存在shared快照；不能交给旧smoke_test.py的`--check-only`按旧初始/重规划命名解释。上面的专用只读入口重新读取共同快照、各方法条件、实际中断表和新任务，调用同一独立原始TLE校验器，并输出完整树前后证据；拒绝在复核时替换初始计划或事件。

按需继续在同一新台账验证真实历史攻击及重建E3/E4 Demo：

```powershell
& $py -X utf8 scripts/budget_run.py --ledger "$r/run_ledger.json" --timeout 60 -- $py -X utf8 scripts/verify_e5_history.py --source "$r/E5" --out "$r/history_attacks"
if ($LASTEXITCODE) { throw '历史保护验证未通过' }
& $py -X utf8 scripts/run_improvement.py --spec configs/improvement_demo.json --out "$r/experiments" --ledger "$r/run_ledger.json"
if ($LASTEXITCODE) { throw 'E3/E4未通过' }
& $py -X utf8 scripts/budget_run.py --ledger "$r/run_ledger.json" --timeout 60 -- $py -X utf8 scripts/build_demo.py --summary "$r/experiments/summary.json" --out "$r/demo"
if ($LASTEXITCODE) { throw 'Demo证据未通过' }
Start-Process (Resolve-Path "$r/demo/index.html").Path
```

直接打开本轮已生成Demo，不重新计算：

```powershell
Start-Process 'G:\bd-fmb\outputs\path_safety_e5_20261023_164001\demo\index.html'
```

自动浏览器回归仍用`node scripts/browser_demo_test.mjs HTML NEW_OUTPUT_DIRECTORY`，外层套预算入口，Node24和本机Chrome/Edge为可选测试工具。正常打开HTML不需要Node或Python，页面自包含。

给3号优先读取`summary.json`的status、shared_conditions、gain、rows，结合`checks/*.json`而非只看任务文件存在。给4号使用本页E5表与上述准确结论；E3/E4的画面和讲稿沿用原范围。实际移交及队友确认由用户/团队完成。本轮到此停止，不追加其他场景。
