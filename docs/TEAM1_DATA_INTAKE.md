# 给1号：标准窗口数据接收与只读试读

目前没有发现带明确交付说明或来源记录的1号数据。实际1号数据试读为 **PENDING_INPUT / NOT_RUN**。合成示例和官方冻结参考窗口只用于验证工具，不能代替你的交付。不会据目录名、官方ZIP或来源文字自动确认你已经交付。

## 交付什么

一个目录包含四个UTF-8文件，CSV允许UTF-8 BOM，JSON按UTF-8读取。请一并填写[接收清单](templates/TEAM1_DELIVERY.md)，记录交付人、时间、版本、来源、过滤与规则差异。可参考[元数据填写模板](templates/team1_metadata.template.json)，模板占位值不能直接当真实数据使用。

| 文件 | 必需字段和约束 |
| --- | --- |
| targets.csv | target_id正十进制且唯一；priority为high/medium/low，对应full_score=5/3/2 |
| stations.csv | station_id正十进制且唯一；配置所选站点必须存在 |
| windows.csv | window_id唯一；target_id/station_id有效引用；start_utc/end_utc为UTC整秒，开始早于结束，位于元数据范围内 |
| metadata.json | schema_version=1、time_precision_s=1、非空data_version、horizon_start_utc/horizon_end_utc、filters_applied字符串列表 |

UTC格式为`YYYY-MM-DDTHH:MM:SSZ`；不静默转换本地时间、偏移或小数秒。Alpha-5、其他ID映射、不同表结构/精度/优先级必须报告适配需求，不能悄悄改值后称符合旧契约。完整约定见[io_contract.md](io_contract.md)。

## 收到后怎样试读

从源码包根目录执行；解释器使用你自己的已激活Python 3.11。数据只读，报告写独立新目录，默认30秒、最多300秒，整棵子进程树受控；不排程、不画图、不做轨道传播。

```powershell
$py='python'
& $py -X utf8 scripts/inspect_team1_input.py --input-dir '../收到的窗口' --source-label '填写实际交付人、时间和版本' --out 'outputs/试读 01'
if ($LASTEXITCODE -ne 0) { throw '先处理试读报告中的错误，不启动规划' }
```

通过后查看`inspection.json`及`prepared_windows.yaml`。前者给出文件SHA256/字节数、解码结果、目标/站点/窗口数量、分档数量、UTC范围、时长最小/中位/最大值、短于120秒及能容纳120/240秒的窗口数、过滤声明、前后完整目录树与输入不变检查。验证复用原load_tables和整数/UTC解析，不另写一套规则。合法数据全四文件全行检查；错误报告记录第一条失败及尚未完成范围，超时为BLOCKED/NOT_COMPLETED，不能说全量通过。

配置默认用元数据完整时域及表内全部站点，input_dir指向本次实际输入；不会默认套旧日期或站点1—3。缓存位置另置。若只想规划明确子集：

```powershell
# 以下7/9与06:10—06:30仅适用于仓库合成例；实际填写自己数据范围
& $py -X utf8 scripts/inspect_team1_input.py --input-dir 'examples/synthetic' --source-label '合成子集验证' --station-ids 9 --start-utc '2026-08-03T06:10:00Z' --end-utc '2026-08-03T06:30:00Z' --out 'outputs/子集试读 01'
```

即使显式选子集，也先验证全量原始四文件。报告分别列出全量统计和planning_selection；只有显式选择的规划切片会裁剪窗口，原文件不改。无此参数就不截断。准备配置给人审阅后，通过[3号窗口工作流](TEAM3_INTEGRATION.md)运行；数据移动后重做试读或传入新input-dir。窗口模式seed不重新抽样。

## 结果与边界

0=数据契约和所选配置通过，2=错误数据/非法路径，3=缺文件或预算/执行条件阻塞。输出嵌套输入、已有输出或封存目录写入会提前拒绝，不能留下新空目录。每次新建报告目录，不覆盖旧报告。

短于120秒但合法的窗口保留，不算错误；可容纳时长只表示几何区间长度够，不等于在资源冲突下能执行。重叠窗口不意味着同一站可同时观测。读入成功不等于调度成功。filters_applied只是供方声明，报告始终注明物理条件未独立验证。

当前冒烟假设待确认：每目标全站最多一次成功；120/240秒得60%/100%；高/中/低满分5/3/2；不同目标切换30秒；中断零分但可重做；窗口几何含端点、资源占用半开区间。两套正式评分口径尚未统一。

请逐项确认哪些已合入窗口：仰角、夜间、目标受光、日月规避、天气、视场、跟踪速度、地形、站点可用性。未合入的条件及其字段、单位、责任方请明确记录；不能由2号推定已经处理。

本轮有限检查范围是项目data/raw、data/processed、已指定交接目录和已知工程资料；没有扫描整台电脑。源文件与旧产物保持只读。1号实际数据缺失只阻塞真实试读，工具、模板和参考验证仍正常交付。
