# 调度与评价接口 v1

本版本是 60 目标冒烟测试的交接契约，不代表已确认的正式赛事规则。1 号交付数据、3 号接入方式仍待双方确认。所有 CSV/JSON 使用 UTF-8；CSV 可有 BOM。示例 `examples/synthetic` 为人工合成数据，不能作为真实观测证据。

## 1 号提供的目录

| 文件 | 必填字段 | 类型与约束 |
| --- | --- | --- |
| targets.csv | target_id, priority, full_score | ID 为正十进制整数；priority 为 high/medium/low，满分分别 5/3/2；ID 唯一 |
| stations.csv | station_id | 正整数且唯一；窗口调度只需此字段，设备限制应已反映在窗口中 |
| windows.csv | window_id, target_id, station_id, start_utc, end_utc | window_id 为非空唯一字符串；引用已有目标和站；开始早于结束 |
| metadata.json | schema_version, data_version, time_precision_s, horizon_start_utc, horizon_end_utc, filters_applied | schema_version=1，time_precision_s=1；版本非空字符串；filters_applied 为实际已应用过滤条件的字符串列表 |

UTC 严格写为 `YYYY-MM-DDTHH:MM:SSZ`，精度为整秒，不接受本地时间、未注明时区、偏移形式或小数秒。时长单位为秒，满分为任务分。Alpha-5 TLE 编号在兼容适配器中转为十进制 ID。`window_id` 不应因排序变化而改变。

窗口几何端点包含起止时刻，任务必须完整落在一个窗口中；占用使用半开区间 `[start,end)`。短于 120 秒的合法窗口保留并记录，不产生候选，不算数据错误。窗口允许重叠；这不意味着站点可并行执行任务。

未知编号、重复编号、缺字段、非法时间、错误优先级/满分或窗口超出元数据时域均立即拒绝。站点子集与规划子时域可配置；合法窗口按子时域裁剪。标准窗口模式使用表内全部目标，seed 和抽样数仅用于 TLE 抽样路径。

`filters_applied` 应写明仰角、夜间、地影/目标受光、日月规避、天气、视场等哪些已应用；空列表表示没有宣称任何过滤。接口不把供应方声明当作已独立物理验证。TLE 适配器仅计算几何仰角 10°—85°，未验证完整光学可观测性。

## 配置及排程函数

完整可复制配置见 `configs/smoke.yaml`、`configs/seed17.yaml`、`configs/seed23.yaml`、`configs/synthetic.yaml`。

- 实验参数：`seed`、`sample_counts: {high, medium, low}`、`station_ids`、`start_utc`、`horizon_seconds`（或 `start_utc` + `end_utc`）、`input_dir`、`input_mode`、`method`、候选网格和裁剪上限。
- 固定本轮假设：时长 `[120,240]`，分别得满分 60%/100%；切换 30 秒；仰角 `[10,85]`。配置偏离这些值会拒绝，不推定中间时长评分。
- `frozen_sample` 可指定已经冻结的 TLE 样本；种子、每档数量、原始输入哈希必须一致。省略时，在当前新输出目录中先冻结再计算，不按结果换样。
- `method` 为 `baseline`、`improved` 或回归用 `both`。`baseline` 保留原先按开始时刻排序的贪心；`improved` 保留优先级/稀缺性/冲突损失构造，并以整数分、覆盖数词典序和基线比较回退。
- 可调用函数：`planner.scheduler.schedule(candidates, method='baseline', *, fixed=(), interrupted=(), clock)`。输入为内部整秒候选字典，返回新任务列表，不修改输入；`clock.check()` 用于预算控制。CSV 接入优先使用统一命令，避免业务调用者构造内部字段。

## 任务与独立评价

`tasks_<方法>.csv` 为交接文件，至少包含 `task_id,target_id,station_id,start_utc,end_utc,duration_s,status`。`schedule_*.csv` 保留旧内部格式以便 E0 逐字节对照，目标字段名为 `satnum`。额外字段 `candidate_id,window_id,priority,start_s,end_s,points_int,score` 用于追踪和检查。独立评价从 targets 的原始优先级和实际 UTC 时长重算得分，不采用自报 `score`。统一输出中自报分和来源字段也会被交叉核对。

每目标全站至多一次成功；同站不重叠；不同目标至少间隔 30 秒。中断占用仍检查资源冲突，但计零分；其目标可重新完整执行。满分与整数点换算为 `points_int = task_score * 5`。

故障重规划须额外提供独立保存的初始任务表、事件 JSON 和中断表：

- 事件必需 `station_id,start_s,end_s`；秒数相对配置起点，故障占用 `[start_s,end_s)`；产出事件同时含 UTC 和选择说明。
- 初始任务 `end_s <= 故障开始`：保留为 `completed`。
- `start_s < 故障开始 < end_s`：健康站为 `locked`；故障站截断为 `interrupted`，保存 `planned_end_s,planned_duration_s,planned_end_utc`。
- 故障恰好在任务开始：尚未执行，不形成 locked 或零时长 interrupted；健康站可从该时刻重新安排。恰好在任务结束：算 completed。
- 除上述保留成功任务外，其余成功任务必须 `status=new_success` 且开始不早于故障。历史集合和中断集合均要求与独立推导结果完全相同，不能靠改 status 增删历史。
- 初始计划、窗口和原始目标应由评价方持有。本地 manifest 检测意外或单文件篡改，不是抵抗“同时篡改所有输入和清单”的数字签名。

`--evaluate` 读取标准任务表独立评价；初始表也会先独立校验。仅最小必填列的初始任务可评价；动态评价建议保留完整来源列，确保历史身份逐字段匹配。缺少 window_id 时按匹配窗口确定。

## 输出和退出码

每次 `--out` 必须是全新目录，源输入、源结果、缓存目录与输出不得嵌套。`--check-only --source ... --out ...` 只读源证据，所有报告、日志、计时写入新目录，并保存源目录全部文件的前后 SHA256 清单。

| 状态/退出码 | 含义 |
| --- | --- |
| PASS / 0 | 所请求核心流程执行完成且独立约束检查通过；不表示最优、不表示正式赛事得分或队友确认 |
| FAIL / 2 | 数据错误、证据变化或约束违例，原因在 failure.json 或各检查报告 |
| BLOCKED / 3 | 缺少必需输入、预算到期、运行隔离失败或额外复评契约未统一；不是 PASS |

空任务表在资源约束上可行，覆盖和分数为零；无有效故障演示时 `fault_demo_status=BLOCKED`。核心运行与可选额外复评分别标状态，后者不混入主评价 PASS。

主要产物：`metrics.json`（实际任务分、覆盖、分档、可执行分母、窗口/候选数、违例、阶段耗时）、`checks/*.json`（独立详细证据）、`effective_config.json`、`frozen_sample.json`、`input_hashes.json`、`standard_input/`、`cache.json`、`timing.json`、`execution.json`、`evidence_manifest.json`。

覆盖率分别是覆盖目标数/全部输入目标数、覆盖目标数/至少存在一个合法 120 秒候选的目标数；分母为零时 rate 为 null。故障后仍沿用全规划期候选分母，便于与初始计划对照。TLE 模式另逐秒检查排程区间仰角；窗口模式仅验证所提供窗口，不声称重新验证其物理过滤条件。

缓存绑定原始输入哈希、实际抽样 ID、站点参数、UTC 起点和时长、过滤条件、粗细采样参数、运行依赖版本和适配器源文件 SHA256，并校验缓存内容哈希。单次运行总预算不超过 300 秒；父进程通过 Windows Job Object（POSIX 为进程组）约束整棵子进程树，超时保留已有证据，不自动重试。
