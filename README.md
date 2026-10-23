# bd-fmb-observation-planner

百度伐谋杯第四题自主观测任务规划。当前交付是基于算法候选`b0eb3b5`的稳定源码接入包、离线演示参考包与只读标准窗口试读工具，见[稳定交接](docs/STABLE_HANDOFF.md)、[3号接入](docs/TEAM3_INTEGRATION.md)、[1号试读](docs/TEAM1_DATA_INTAKE.md)。最终包版本以MANIFEST.source_commit为准，验收以包旁机器回执为准。

新解压目录无真实数据也可运行，不需要.git；从包根执行：

```powershell
$py = 'python' # 或自己的Python 3.11解释器完整路径
& $py -X utf8 scripts/team3_run.py --python $py synthetic --out 'outputs/接入 01'
```

该命令依次完成基线规划、初始/故障独立评价及只读复查。输入/输出支持中文和空格路径，输出必须全新。没有依赖时先`python -m pip install -r requirements.txt`；本轮未执行干净安装。源码包不含真实数据；本地Demo/参考包仅由用户通过团队渠道转交。1号实际交付和3号本人确认仍待外部完成，转发草稿只写在[文档](docs/FORWARD_DRAFTS.md)，未发送。

历史E5同初始计划对照172.4→182.0、收益9.6；历史E3/E4整体流程及Demo见对应交接。以下保留本机TLE入口示例，旧TLE数据/封存绝对路径不属于本轮移机验证范围。

## 直接运行

```powershell
Set-Location G:\bd-fmb
$py = 'D:\conda_envs\bd-fmb\python.exe'
& $py -X utf8 smoke_test.py --config configs/smoke.yaml --method baseline --out outputs/baseline_01
& $py -X utf8 smoke_test.py --check-only --source outputs/baseline_01 --out outputs/recheck_01
```

每次输出路径必须全新。复查必须显式给源结果和独立输出，源证据全部文件内容哈希保持不变。

Git 仓库不含真实比赛数据。已有本地 `prototype_v1/data_raw` 和冻结样本时可运行控制案例；新克隆先用合成示例：

```powershell
$py = 'D:\conda_envs\bd-fmb\python.exe'
& $py -X utf8 -m pip install -r requirements-dev.txt
& $py -X utf8 smoke_test.py --config configs/synthetic.yaml --out outputs/synthetic_01
& $py -X utf8 -m pytest tests -q --basetemp=outputs/pytest_new_01
```

已有 bd-fmb 环境不需要安装。稳定算法候选已有117项测试通过；本轮新增入口的最终测试数量见交付验收回执，开发依赖固定pytest9.1.1；运行仅需requirements.txt。本轮未安装或升级依赖，未做干净环境安装验证。`requirements-lock.txt` 是用户原有完整环境快照，保持原字节和未跟踪状态。每次测试使用新的basetemp。

## 交付与结果

- [docs/PATH_SAFETY_E5_HANDOFF.md](docs/PATH_SAFETY_E5_HANDOFF.md)：P1修复前后完整目录树证据、E5共同输入哈希与受控结果、专用只读复核及复现命令。

- [docs/IMPROVEMENT_DEMO_HANDOFF.md](docs/IMPROVEMENT_DEMO_HANDOFF.md)：本轮E3/E4实测、600秒预算台账、复现/复查/Demo命令和分项验收。
- [demo/README.md](demo/README.md)：离线生成器和清晰标注的合成演示；[中文讲稿](docs/DEMO_SCRIPT.md)。

- [BASELINE_HANDOFF.md](BASELINE_HANDOFF.md)：安装、队友接入、独立评价及只读复查命令。
- [docs/io_contract.md](docs/io_contract.md)：字段、端点、故障边界、评分和返回码。
- [EXPERIMENTS.md](EXPERIMENTS.md)：实际 E0/E1/E2 结果、证据、耗时和局限。
- [PROGRESS.md](PROGRESS.md)：实际完成、待确认、未执行工作。
- [docs/team_questions.md](docs/team_questions.md)：给 1 号、3 号的待确认清单。
- [docs/optional_evaluator.md](docs/optional_evaluator.md)：旧额外复评保持 BLOCKED。

入口 `smoke_test.py`；`planner/scheduler.py` 提供 `schedule()`；`planner/validator.py` 独立重算评分、约束和历史来源，不调用调度器可行性或评分函数。`planner/tle_adapter.py` 保留官方 TLE 适配，`planner/io_contract.py` 直接读取标准窗口。`configs/` 提供三个固定种子和合成配置。

真实数据、冻结样本和结果全部在本地忽略目录 `prototype_v1/`、`outputs/`，不提交。缓存绑定原始数据、样本、站点、时域、过滤/采样和版本；算法比较无需重复传播。默认单进程；每案例最多 300 秒，超时终止工作进程树，不自动重试。

每目标一次成功、中断零分、120/240 秒离散得分和海拔近似椭球高属于本轮测试假设；几何仰角不等于完整光学可观测。正式规则与两套评分口径待确认。未收到明确标记的 1 号数据，未声称已与 3 号确认接口。

E5入口为 `scripts/run_replan_e5.py`，两方法共享一份冻结初始计划、历史和候选；其 `--check-only` 是专用只读复核，不套用旧四计划命名。实验根必须全新，台账放在实验根之外（推荐父目录）。E3/E4总入口在任何写入前预检全部输入及台账/日志位置，支持正常相邻输出，拒绝封存源内部写入。
