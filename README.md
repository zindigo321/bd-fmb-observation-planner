# bd-fmb-observation-planner

百度伐谋杯第四题（开运联合）自主观测任务规划：可交接贪心基线、独立校验、站点故障重规划。本轮沿用原真实数据实现，修复历史伪造与复查覆盖问题，增加标准窗口表输入和可配置实验参数。

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
python -m pip install -r requirements.txt
python smoke_test.py --config configs/synthetic.yaml --out outputs/synthetic_01
python -m pytest tests -q
```

已有 bd-fmb 环境不需要安装。测试需要 pytest；本轮未新增或升级依赖。`requirements-lock.txt` 是用户原有完整环境快照，保持原样且未纳入本轮提交。

## 交付与结果

- [BASELINE_HANDOFF.md](BASELINE_HANDOFF.md)：安装、队友接入、独立评价及只读复查命令。
- [docs/io_contract.md](docs/io_contract.md)：字段、端点、故障边界、评分和返回码。
- [EXPERIMENTS.md](EXPERIMENTS.md)：实际 E0/E1/E2 结果、证据、耗时和局限。
- [PROGRESS.md](PROGRESS.md)：实际完成、待确认、未执行工作。
- [docs/team_questions.md](docs/team_questions.md)：给 1 号、3 号的待确认清单。
- [docs/optional_evaluator.md](docs/optional_evaluator.md)：旧额外复评保持 BLOCKED。

入口 `smoke_test.py`；`planner/scheduler.py` 提供 `schedule()`；`planner/validator.py` 独立重算评分、约束和历史来源，不调用调度器可行性或评分函数。`planner/tle_adapter.py` 保留官方 TLE 适配，`planner/io_contract.py` 直接读取标准窗口。`configs/` 提供三个固定种子和合成配置。

真实数据、冻结样本和结果全部在本地忽略目录 `prototype_v1/`、`outputs/`，不提交。缓存绑定原始数据、样本、站点、时域、过滤/采样和版本；算法比较无需重复传播。默认单进程；每案例最多 300 秒，超时终止工作进程树，不自动重试。

每目标一次成功、中断零分、120/240 秒离散得分和海拔近似椭球高属于本轮测试假设；几何仰角不等于完整光学可观测。正式规则与两套评分口径待确认。未收到明确标记的 1 号数据，未声称已与 3 号确认接口。
