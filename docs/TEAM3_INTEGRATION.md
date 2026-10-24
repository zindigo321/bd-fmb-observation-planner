# 给3号：从解压到接入

先交基线。源码包不带真实数据，也不需要.git目录；自带的小数据是合成示例。收到的压缩包旁有`.sha256`，包内`MANIFEST.json`记录精确源码提交、算法候选b0eb3b5、文件哈希与打包环境版本。

## 1. 环境和最短流程

工作目录是**解压后的source_kit目录**，可以有空格或中文。下面的python可替换为你自己的Python 3.11完整路径；本机试验使用原有解释器，没有重新安装环境。

```powershell
Set-Location '你解压的源码包目录'
$py = 'python'  # 已激活环境；也可填写你自己的python.exe路径
# 新环境才安装；本轮没有实际执行干净环境安装
& $py -m pip install -r requirements.txt
# 正式运行时每次换一个新输出目录
& $py -X utf8 scripts/team3_run.py --python $py synthetic --out 'outputs/接入 01'
if ($LASTEXITCODE -ne 0) { throw '先看workflow.json或控制台，不继续后续步骤' }
```

无需安装时最短就是最后两行。脚本按自身位置找代码；输入/输出参数中的相对路径相对于你当前工作目录，内部子命令统一在包根运行。`--python`指定子命令解释器，省略则使用启动该脚本的解释器。默认baseline；要已有改进对照加`--method both`。默认运行阶段共120秒，`--budget-seconds`在子命令前指定，最多300；每个子进程由原Windows Job Object/进程组限时，不自动重试。任一步非0即停止依赖步骤。

一键流程会依次完成规划、初始任务独立评价、有效故障的独立评价、只读复查。新目录内：`config.yaml`是实际配置，`run/`是规划结果，`evaluate_baseline/`、`evaluate_fault_baseline/`、`recheck/`分别保存评价与复查。`cache/`与它们分离。`workflow.json`记录代码导入路径、解释器、版本、真实命令、返回码、耗时及输入/结果完整树是否不变。

本轮本机合成基线实测初始10.0分、覆盖3/3，故障后3.0分、覆盖1/3，均0违例。该小例仅验证接口；模拟故障较长，不能用它代表真实算法收益。最终解压包验证结果见发布包旁验收报告，不把本机结果冒充你本人已接入。

## 2. 标准窗口接入

先把收到的数据作为只读输入。四文件须满足[契约](io_contract.md)，未知数据先走试读，再人工查看报告和生成的配置。

```powershell
& $py -X utf8 scripts/inspect_team1_input.py --input-dir '../local_demo_reference_kit/reference_windows' --source-label '官方冻结参考，非1号交付' --out 'outputs/参考试读 01'
if ($LASTEXITCODE -ne 0) { throw '试读未通过' }
& $py -X utf8 scripts/team3_run.py --python $py windows --input-dir '../local_demo_reference_kit/reference_windows' --config 'outputs/参考试读 01/prepared_windows.yaml' --out 'outputs/参考接入 01'
if ($LASTEXITCODE -ne 0) { throw '接入未通过' }
```

两包解压后可放相邻目录；路径按你的实际位置填写。正式1号交付替换输入目录和来源说明。准备配置从元数据取得UTC范围，默认使用站点表全部站点；显式子站点/子时域方法见[1号试读说明](TEAM1_DATA_INTAKE.md)。移动数据后重新试读，或显式传入新的`--input-dir`；wrapper按本次实际输入和新输出重设输入/缓存位置。旧封存JSON不需要修改。

标准窗口模式使用全部供应目标，seed不重新抽样。只检查供应窗口内的调度约束，不重新传播轨道，不认证供应方声明的夜间、受光、天气等过滤条件。参考包的历史TLE逐秒证据只属于原来源。

## 3. 读取哪些结果

| 文件/字段 | 意义 |
| --- | --- |
| `run/tasks_baseline.csv` | 初始计划；改进为tasks_improved.csv |
| `task_id,target_id,station_id` | 任务、目标、站点标识；目标/站点为正十进制ID |
| `start_utc,end_utc,duration_s` | UTC整秒起止、秒数；格式YYYY-MM-DDTHH:MM:SSZ |
| `status` | success初始成功；completed故障前已完成；locked健康站正在执行且保留；new_success故障后新安排；interrupted零分片段单列 |
| `tasks_baseline_replanned.csv` | 基线重规划；改进对应tasks_replanned.csv |
| `fault_event.json,interrupted_baseline.csv` | 故障站和相对秒区间、中断实际占用及原计划结束信息 |
| `metrics.json → plans` | task_score任务分，coverage数量，by_priority_coverage分档数量，violation_count违例数 |
| `coverage_all` | 覆盖数/全部输入目标数 |
| `coverage_executable` | 覆盖数/全规划期至少存在合法120秒候选的目标数；故障后不缩小分母，零分母rate=null |
| `checks/*.json` | 独立校验详细报告；评价重算原始优先级和实际时长，不信任务自报score |
| `timing.json,metrics.runtime` | 阶段计时、子进程内部总耗时；不要把各层总耗时再次相加 |
| `execution.json,workflow.json` | 进程退出、超时、外层墙钟；改进方法耗时含内部基线回退 |

## 4. 评价方单独调用

评价方保管权威targets/windows和初始计划。不要让被评价方连同任务表一起替换这些证据。

```powershell
& $py -X utf8 scripts/team3_run.py evaluate --input-dir 'examples/synthetic' --config 'configs/synthetic.yaml' --tasks 'outputs/接入 01/run/tasks_baseline.csv' --out 'outputs/单独评价 01'
if ($LASTEXITCODE -ne 0) { throw '评价未通过' }
& $py -X utf8 scripts/team3_run.py evaluate --input-dir 'examples/synthetic' --config 'configs/synthetic.yaml' --tasks 'outputs/接入 01/run/tasks_baseline_replanned.csv' --initial-plan 'outputs/接入 01/run/tasks_baseline.csv' --event 'outputs/接入 01/run/fault_event.json' --interrupted 'outputs/接入 01/run/interrupted_baseline.csv' --out 'outputs/故障评价 01'
if ($LASTEXITCODE -ne 0) { throw '故障评价未通过' }
& $py -X utf8 scripts/team3_run.py recheck --source 'outputs/接入 01/run' --out 'outputs/复查 01'
```

故障评价的初始计划、事件、中断表必须同时给出。独立校验从初始计划推导完成/锁定/中断集合，再检查待评价表。故障开始时刻恰好结束的任务算完成；恰好开始的任务不算锁定。中断零分但参与资源占用，之后可为该目标重做。

正常规划要注入固定故障，用`synthetic/windows --fault-event 文件`；外部故障评价用`evaluate --event 文件`。事件秒数相对配置UTC起点，字段见契约；不要混用两种参数。wrapper复用`smoke_test.py`，没有改评分或校验算法。

`evaluate --config`也可读取成功运行的`run/effective_config.json`；`recheck`自动读取该文件。两种只读模式仅从内存中的执行配置移除历史规划用的`fault_event_path`，不修改源文件，也不重新注入故障。故障评价仍须显式提供初始计划、事件和中断表，复查仍校验源结果的封存证据。`reuse_source`和`frozen_sample`在所有标准窗口模式中继续拒绝；规划模式仍须用`--fault-event`显式注入。

## 5. 失败如何处理

| 返回码 | 含义和动作 |
| --- | --- |
| 0 | 本次所请求流程通过；检查报告与范围，不等于正式评分或物理认证 |
| 2 | 非法输入、约束违例、已有/嵌套输出、契约不匹配；看inspection.json、workflow.json、console日志和checks报告，修正输入副本后换新输出目录 |
| 3 | 必需文件缺失、预算不足/超时或执行条件阻塞；补输入或合理提高预算至最多300秒，再用新目录，不把部分结果当通过 |

路径拒绝在创建输出前发生，因此可能只有控制台原因而没有报告。试读数据错误通常会在新报告目录留下第一条错误，不保证列出所有后续错误。不得通过删除旧输出、改原始输入或关闭保护来“重跑成功”。

## 6. Demo与回执

另一个本地包中双击`demo/index.html`即可，完全离线、预计算回放，无需Python/Node。E3/E4页面中的旧E4收益11.6分属于不同初始计划的整套流程；E5的9.6分在独立表格，不能混说。

请填写[接入回执模板](templates/TEAM3_RECEIPT.md)。3号确认当前是PENDING_EXTERNAL；本轮仅做本机及新解压目录验证，没有发送消息或代填通过。干净安装、另一台机器上的TLE全量复现、完整光学和正式评分未验证。旧额外复评继续BLOCKED。
