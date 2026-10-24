# 稳定版本交接

本轮在算法候选`b0eb3b5`之上增加接入和只读试读工具，没有修改调度、评分、候选、独立校验或安全写入核心。分支为`work/stable-handoff-intake`。最终源码包对应的完整源码提交写在包内`MANIFEST.json → source_commit`，不在文档内循环引用自身提交哈希。

## 两个包怎么用

| 包 | 给谁/用途 | 数据边界 |
| --- | --- | --- |
| source_kit.zip | 3号接入，1号试读；运行代码、测试、配置、依赖、合成例、模板和说明 | 只从指定Git提交的白名单受控文件导出；不含.git、原始真实数据、旧输出、真实任务/窗口、真实HTML/截图、完整环境清单、提示词或未跟踪文件 |
| local_demo_reference_kit.zip | 用户本地转交3号/4号；离线Demo、三截图、E3/E4与E5表格、讲稿、官方参考窗口 | 含真实标识，仅在本地忽略输出目录；不推Git、不上传云服务，不创建Release |

每包内有MANIFEST.json，列出文件用途、来源、字节数、SHA256、创建时间、算法候选提交及源码提交、依赖版本。manifest明确排除自身哈希。压缩包旁另有`.zip.sha256`，校验归档本身。源码逐文件读取Git对象，不把未提交工作树冒充提交版本；本地包引用的旧实验时间不会改为本轮时间。

源码白名单精确包含`.github/pull_request_template.md`和`.github/workflows/ci.yml`，未知受控文件仍使打包失败。打包回归测试创建临时Git仓库和合成历史来源，因此解压包运行测试无需自带`.git`或真实历史数据；本机需已有Git命令。修复后的新包仍须以最终本地提交实际导出，并通过包外验收回执记录结果；下文旧包路径与实测属于历史交接。

```powershell
# PowerShell校验下载或转交后的压缩包
Get-FileHash -Algorithm SHA256 .\source_kit.zip
Get-Content .\source_kit.zip.sha256
Expand-Archive -LiteralPath .\source_kit.zip -DestinationPath '.\源码 接入'
Expand-Archive -LiteralPath .\local_demo_reference_kit.zip -DestinationPath '.\local_demo_reference_kit'
```

最终两包及验收产物位于本机 `G:\bd-fmb\outputs\stable_handoff_20261023_190522`。包路径、大小、外置哈希和精确版本由`packages/packages.json`给出；`acceptance.json`、`portable_validation.json`、`pytest.xml`、`browser_from_kit/browser_checks.json`是提交之后针对最终包生成的发布验收凭据。发布时应一起查看这些包外回执；不能只因文档写好了就推定压缩包已通过。

## 先做哪一步

3号从[接入说明](TEAM3_INTEGRATION.md)运行合成一键流程，再用本地参考包的reference_windows试接真实窗口接口。1号从[试读说明](TEAM1_DATA_INTAKE.md)准备四文件及来源清单。实际本人运行后填写[3号回执](templates/TEAM3_RECEIPT.md)。给1号、3号、4号的文字在[转发草稿](FORWARD_DRAFTS.md)，本轮没有发送消息。

本轮本机已经实跑：合成基线初始10.0分、覆盖3/3、故障后3.0分、覆盖1/3，初始/故障独立评价和只读复查均0违例，完整结果树保持。只读工具已读取合成四文件与官方冻结参考四文件；后者60目标、3站、563窗口，9个短于120秒，554个能容纳120秒，502个能容纳240秒。全部只是供应窗口约束；过滤声明不转成物理认证。

源码包的移目录流程、真实参考窗口接入、最终完整测试数量、解压Demo浏览器检查、保护快照及唯一预算以本轮包外机器回执为最终结果。生成这些回执的时间晚于源码提交，所以不把未知结果预写进该提交；交付回复会列实际结果及失败记录。任何修复产生新源码提交时须重新导出对应最终包。

## 历史结果来源

主要来源是 `outputs/atomic_write_fix_20261023_182047`，本轮先验证其封存清单、任务分与报告一致、Demo哈希和浏览器记录，证据为`source_verification.json`。权威E5初始来源仍为`outputs/improvement_demo_20261023_150452/experiments/E4_seed42_late`，没有改封存JSON或伪造移机路径。

历史E5：同初始计划、14完成/1锁定/1中断/2未来受影响、6839未来候选；172.4/182.0分，收益9.6，固定历史51、新任务121.4/131，覆盖56/60及56/56，净调整5/23，宽松上界182，原始TLE逐秒0违例。历史E3/E4 Demo比较整套流程，旧E4为172.4/184.0、收益11.6，初始计划不同。二者不能混用。本轮不重新优化、不扩样本；历史TLE验证和当前窗口接入验证分开标注。

旧TLE工程的封存配置仍可能依赖本机原始轨道、站址、绝对路径及原目录。源码包不含这些数据，本轮不宣称旧TLE全量移机复现。标准窗口/合成流程按包根定位代码，允许中文/空格路径，最终验证应确认planner_import确实位于解压包且无.git目录。

## 状态和限制

- 1号实际数据：PENDING_INPUT / NOT_RUN，有限检查未发现明确来源交付；官方参考不是1号数据。
- 3号实际接入确认：PENDING_EXTERNAL；2号本机和解压目录验证不能代替3号本人。
- 干净环境安装：NOT_RUN；提供安装命令，但本轮继续用原bd-fmb解释器，不安装/升级依赖，不改requirements-lock.txt。
- 移机TLE全量复现、完整光学、正式评分：未验证。
- 旧额外复评：BLOCKED，契约未改。
- 源码包完整性、移目录接入、窗口评价/复查、试读工具及Demo包：分别以实际验收凭据给状态，不用一个PASS覆盖外部未确认项。

窗口、UTC、故障历史和评分规则见[接口契约](io_contract.md)。需要扩展规则时由团队明确确认；不静默改ID、精度、时区、优先级、站点或样本。前几轮完整记录保留在EXPERIMENTS/PROGRESS；E3/E4和Demo已完成，不再列作尚未开始。
