# 可选旧复评器：BLOCKED，已隔离

旧入口保存在本地忽略目录 `prototype_v1/evaluate/` 和 `prototype_v1/evaluator_adapter.py`，不纳入当前主调用链。

2026-10-21 独立审计证据指出：旧复评器绑定的 `PLAN.md` / `EXECUTION_REQUIREMENTS.md` SHA256 与下载副本不符；适配器的 `earliest_midpoint_prioritize_future` 事件选择规则也不在其允许集合中。证据本地路径 `outputs/prior_audit/optional_evaluator_gate.json`。本轮读取了证据和相关实现，没有把这次历史 BLOCKED 写成本轮 PASS。

当前 `python smoke_test.py --optional-evaluator --out outputs/optional_check_新编号` 明确输出 BLOCKED 并返回 3；不调用旧入口，也不移除哈希检查。主校验器独立完成本轮评价，不依赖这一入口。

后续如需恢复，应先确认真实规则版本、重审文件哈希并实现真实事件选择语义，再运行可追踪的兼容测试。不能改名冒充相同规则。此工作尚未执行，未阻塞本轮基线交接。
