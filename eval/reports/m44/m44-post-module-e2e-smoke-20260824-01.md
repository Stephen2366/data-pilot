# M44 post-module exploratory E2E smoke

## 身份与边界

- 执行时间：2026-08-24 18:05（Asia/Shanghai）
- 分类：`exploratory / baseline-ineligible / not-development-probe`
- 范围：一条 canonical T1→T5 产品链，经过真实 FastAPI `/api/query`、Qwen `qwen3.7-plus`、MySQL 与 task runtime。
- 限额：最多 8 次真实 provider 出站、30000 observed tokens；达到边界后停止，不重跑、不换模型/backend。
- 数据：在同一未提交事务中追加官方 Phase 4B seed，结束后 rollback；运行前后数据库快照一致，`database_restored=true`。
- 原始证据：`.agent_work/temp/m44-post-module-smoke-20260824-01/artifact.json`；Trace SHA-256 `05fa65b919033040a4d03ab60066e031f369c97196a857d54b3789f4928e6e59`。

## 结果

Gate：**failed**。共执行 T1～T3，累计 8 calls / 32674 observed tokens；最后一个已开始的 T3 response 使累计 token 超过软上限，runner 保留该次 usage 并按纪律停止，因此 T4/T5 未执行。

| Turn | 结果 | 关键观察 |
|---|---|---|
| T1：查询 2026 年 7 月实际净退款金额 | pass | HTTP 200，`answer_ready`，得到 oracle `120000`；2 calls / 5724 tokens |
| T2：改成 8 月并和 7 月比较 | fail | 约束修改和旧 Evidence invalidation 正常；生成了 MySQL 不支持的 `DATE_TRUNC`，最终 `sql_execution_error`，没有进入预期 repair；2 calls / 8368 tokens |
| T3：解释上涨原因 | fail | Controller 确实选择了两次有界 SQL Evidence action，但两次都被同类方言错误阻断；4 calls / 18582 tokens |
| T4/T5 | not observed | 达到总调用额度后停止，不能据此判断 business Knowledge runtime、partial answer 或 correction 链路的真实效果 |

## 失败定位

1. `run_sql_tool` 在真实数据库异常时返回 `error_type=sql_execution_error` 且 `safety_status=blocked`。
2. Harness 的 `DATE_TRUNC` 方言分类条件却要求该结果 `safety_status=passed`。
3. 因此真实错误不会被归一化为 allowlisted `sql_dialect_incompatible/mysql_unsupported_date_trunc`，B2 Controller 看见的只是通用不可恢复错误，`repair_sql_evidence` 没有机会运行。

这说明 deterministic fake 覆盖了 repair 控制合同，却没有覆盖真实 `run_sql_tool` 的错误形状。

## 安全发现

真实 Trace 的 tool call 中出现了底层数据库异常文本。代码路径也把同一未脱敏 `tool_calls` 投影给 API Response。这与“API/Trace 不保存 raw DB error”的既有合同冲突，优先级高于单纯的答案质量问题。本文不复制原始异常内容。

## 结论与下一步

- T1 证明单月 SQL 纵向链路可用；本次不能证明 M44 canonical T1→T5 真实链路闭合。
- 建议在 M45 前安排一个聚焦的 M44 post-finish defect patch：统一真实 SQL 错误的安全 typed projection，使 allowlisted 方言错误能进入一次 repair，同时彻底切断 API/Trace raw DB error。
- 补充真实错误形状的 deterministic regression 后，只重验最小受影响的 T2/T3 链路；是否执行该代码修复与真实重验需另行确认。本报告本身不改变产品默认、数据库或正式 Eval 基线。
