# 协作与提交

## 开始修改

从最新主分支创建工作分支；保持本地未提交修改已妥善处理。

```powershell
git switch main
git pull --ff-only origin main
git switch -c work/你的任务名称
```

主分支用于稳定交付，通过 Pull Request 合并。提交说明写清实际变化，例如“修复故障前完成任务保留”，无需统一改写已有历史。

## 本地验证

使用 Python 3.11，安装依赖后在项目根目录执行。已有项目环境可直接使用。

```powershell
$py = 'python'
$run = 'outputs/local_check_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
New-Item -ItemType Directory -Path $run -ErrorAction Stop | Out-Null

& $py -X utf8 -m pytest tests -q --basetemp "$run/pytest" --junitxml "$run/pytest.xml"
if ($LASTEXITCODE -ne 0) { throw '测试未通过' }

& $py -X utf8 scripts/team3_run.py synthetic --out "$run/synthetic"
if ($LASTEXITCODE -ne 0) { throw '合成接入未通过' }
```

每次使用新输出目录。Windows 特有的联接、大小写别名等测试应在 Windows 上执行；报告跳过时注明原因，不把跳过写成验证通过。

## 检查提交内容

只暂存本次要交付的文件，在提交前查看列表与差异：

```powershell
git add -- 你修改的文件
git diff --cached --name-only
git diff --cached --check
git diff --cached
git commit -m '说明本次实际改动'
git push -u origin HEAD
```

真实原始数据、真实目标/窗口/任务表、运行输出、缓存、截图、压缩包、密码和 Token、机器专属环境快照及本地提示词不上传。合成示例必须明确标注为合成数据。忽略规则不能替代暂存内容检查。

## Pull Request 与自动测试

创建 PR 时使用仓库模板，填写问题、改动、实测结果、接口/评分影响和未验证项。PR 合入 main 前等待 `Windows Python 3.11` 检查通过。模板合入主分支后才会自动用于后续 PR；引入模板的第一份 PR 需手动填写。

自动测试工作流会在指向 main 的 PR、main 的推送、初次配置分支的推送及手动触发时运行，使用 Windows 2025 和 Python 3.11 安装依赖、检查依赖一致性、运行完整测试与合成接入。它不使用真实比赛数据，不替代真实 TLE 实验、1号数据验收、3号本人接入或正式评分。

首次云端运行成功后，仓库管理员在主分支保护中要求 PR 和此状态检查；尚无第二位可审阅成员时，先不要求批准数量，避免阻塞交付。禁止强制推送与删除 main。设置是否生效以 GitHub 在线规则为准，新增文档不会自动启用保护。

## 格式与现有证据

源代码和文档按 `.gitattributes`、`.editorconfig` 使用 UTF-8 和规定换行。不要批量格式化旧代码、执行全仓库换行重写，或改写封存实验。CSV 保持原有 Git 自动文本处理方式，不新增强制换行规则；忽略目录中的任务表与封存证据不参与本次变更。

项目尚未确定开源许可证，需团队明确后再添加 LICENSE。
