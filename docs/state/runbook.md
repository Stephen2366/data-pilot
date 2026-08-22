# DataPilot Runbook

> 本文是 DataPilot 的运行入口：只说明“怎么开启哪条链路、怎么跑命令、哪些默认不能随手改”。Trigger：只要要运行命令、切模型、开 LangFuse、跑 eval、改环境变量，必须先读本文。当前状态先读 `docs/state/AI_CONTEXT.md`，评测数字和错因追溯读 `docs/state/eval-baselines.md`，Milvus / embedding 细节读 `docs/state/schema-retrieval-milvus-embedding.md`。

更新时间：2026-08-22

## 模型链路

| 目标 | 环境变量 | 说明 |
|---|---|---|
| 默认 Qwen 主链路 | `LLM_PROVIDER=qwen`；`QWEN_MODEL=qwen3.7-plus` | 当前默认。Qwen provider 读取 `QWEN_MODEL`，不是 `LLM_MODEL`。`.env` 中的 `LLM_MODEL=deepseek-v4-flash` 仅作为显式切回 DeepSeek 时的备用入口。 |
| API Text2SQL 路径 | 默认 `force_new_pipeline=true`；显式 `false` | `/api/query` 先进入 M37 turn seam；accepted initial/resume/follow-up 再恰好调用一次 M35 Graph。路由为 SQL 后，Text2SQL Tool 默认走 Schema Retrieval → QueryPlan → SQL Guard 新链路。显式 `false` 只让该 Tool 走 legacy baseline，不绕过 turn/Harness。 |
| DeepSeek 主模型对照 | `LLM_PROVIDER=deepseek`；`LLM_MODEL=deepseek-v4-flash` | 显式切换时使用；`LLM_MODEL` 在现有代码语义里主要服务 DeepSeek provider。 |
| LLM 可靠性配置 | `LLM_TIMEOUT_SECONDS=45`；`LLM_MAX_RETRIES=0`；`LLM_RETRY_BACKOFF_SECONDS=1` | M25 默认不自动重试。只对明确标记为 transient 的 timeout / 网络 / 429 / 5xx 生效；聚焦实验在当前 shell 临时覆盖，不直接改 `.env` 默认。 |
| Legacy L3 judge | `EVAL_JUDGE_MODEL=<模型名>` | 仅服务冻结旧 runner 语义；当前 M27 CLI 不提供 `--judge-model`，也不把 LLM-as-Judge 作为默认裁决器。 |

## Caller / Turn / Harness 链路

| 目标 | 配置 / 入口 | 说明 |
|---|---|---|
| M38 turn / Harness seam | `POST /api/query` | initial、pending/resume 和一次 follow-up 共用同一入口。SQL/RAG accepted turn 各至多一个深 Tool；canonical Hybrid initial 仍只 invoke 一次 Graph，但按薄计划依次执行 SQL、RAG 各一次（总计至多两个），两支 required。Hybrid 不签发 M37 follow-up；thread lifecycle 前置拒绝调用零次 Graph。 |
| 结构化 resume | 请求同时提供 `thread_id`、`expected_version`、`clarification_answers` | 三项必须成组出现；只接受 checkpoint 声明的闭集字段。一次恢复后仍不明确时以 budget stop 结束，不创建嵌套 pending。 |
| 显式一次 follow-up | initial 请求设置 `enable_bounded_follow_up=true`；后续提交 `thread_id`、`expected_version`、`follow_up_action`、`follow_up_fields` | 只有成功 SQL/RAG 才返回服务端 closed-world spec。SQL `adjust_sql_scope` 每次重查；业务 RAG `explain_same_evidence` 可按当前 active identity 重新授权并重水化，`ask_related_evidence` 重检索；external RAG 总是重检索。只能成功消费一次。 |
| 显式 clear | `DELETE /api/query/threads/{thread_id}?user_role=<role>&expected_version=<version>` | clear 不调用 Graph/Tool，但会记录 lifecycle Trace；thread id 本身不能授权操作。 |
| 进程内 checkpoint | `THREAD_CHECKPOINT_TTL_SECONDS=900` | runtime `inprocess-bounded-thread-v2`、state `m37-thread-v2`；只保存 pending clarification 或成功结果的最小 task/EvidenceRef/spec/budget，不保存旧 answer/rows/正文/citation。owner 绑定可信 caller + tenant/active role；重启或多 worker 不恢复/共享。 |
| Fixture Caller resolver | `APP_ENV=local`、`demo` 或 `test` | 只有这三个环境会由应用启动过程注入 fixture resolver，供本地演示和测试使用；请求中的 `user_role` 只选择 fixture 身份，不能自行授权。 |
| 无 Caller resolver | 其他 `APP_ENV`，或应用未注入 resolver | Graph 的 route 节点直接生成 `caller_untrusted`，不调用业务 Router adapter 或 Tool，返回 blocked / no-answer。生产接线必须显式提供真实认证 resolver。 |

最小 initial 请求仍兼容旧形状：`{"question":"这个怎么处理？","user_role":"ops"}`。若响应返回 pending thread，resume 形状为 `{"question":"补充条件","user_role":"ops","thread_id":"<id>","expected_version":1,"clarification_answers":{"subject":"退款政策"}}`。要开启一次追问，在成功 initial 中增加 `"enable_bounded_follow_up":true`，再严格按响应 `follow_up.actions[].fields` 提交，例如 SQL：`{"question":"执行结构化追问","user_role":"ops","thread_id":"<id>","expected_version":1,"follow_up_action":"adjust_sql_scope","follow_up_fields":{"time_range":"2026年7月","group_by":"商品"}}`。客户端不能自行声明 Evidence 等价性，也不能添加 spec 外字段。

## Schema Retrieval / Embedding 链路

> 如果用户要求使用 Milvus 相关链路，但未开启 Docker 或 Milvus，先提醒。collection 纪律、`schema_docs_hash`、M20 clean run 结论和排查菜单见 `docs/state/schema-retrieval-milvus-embedding.md`。

| 目标 | 环境变量 | 说明 |
|---|---|---|
| 默认本地检索 | `SCHEMA_VECTOR_BACKEND=inmemory`；`SCHEMA_EMBEDDING_PROVIDER=deterministic` | 当前主线默认，轻量、稳定、无需外部服务。 |
| Milvus 向量库 | `SCHEMA_VECTOR_BACKEND=milvus` | 只显式实验时开启；需要本地 Milvus 服务可用。 |
| DashScope/Qwen embedding | `SCHEMA_VECTOR_BACKEND=milvus`；`SCHEMA_EMBEDDING_PROVIDER=dashscope`；`QWEN_EMBEDDING_MODEL=qwen3.7-text-embedding`；`QWEN_EMBEDDING_DIMENSIONS=1024` | 显式实验路径；当前不切默认，模型/检索结论需看同条件重复快照。当前 Milvus Eval 的唯一文档化 embedding 路径。 |

## LangFuse / Trace 链路

| 目标 | 环境变量 / 命令 | 说明 |
|---|---|---|
| 本地 JSONL trace | M27 默认写入 `eval/traces/`，可用 `--trace-dir eval/traces` 指定目录 | 默认不依赖 LangFuse；JSONL 默认不提交。 |
| `/api/query` M40 Trace | 默认 `eval/traces/traces.jsonl` | SQL、RAG、Hybrid、lifecycle Trace 均新增 `phase4-trace-runtime-v1`：只从同一 turn 的 safe ledger / diagnostics / branch 投影 Harness、Tool、release/recipe/policy、薄 plan 与 Synthesizer identity；缺 identity 记 `unavailable` 不影响 API。Hybrid JSONL 不保存 Document 正文、完整 SQL rows、private typed Evidence 或 denied branch 的真实原因/ref；不保存 raw `thread_id` 或结构化 thread 参数副本。 |
| 本地 M27 eval | `LANGFUSE_ENABLED=false`；按下方 selector 命令运行 | completed EvalRun JSON + Markdown report 是新事实源；M27 不生成旧 triage JSON。 |
| LangFuse Cloud trace/score | `LANGFUSE_ENABLED=true`，必要时 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897` | Cloud 仍是旁路增强；M27 当前只构造严格 allowlist assertion payload，实际上传需显式授权，不能影响本地 EvalRun。 |
| LangFuse smoke | `python scripts\smoke_phase3b_langfuse.py`；Cloud 硬门禁加 `--require-langfuse` | M18 的主验证入口，用于 API / JSONL / trace mapping / score / visibility。 |

## M34 EnterpriseRAG-Bench external benchmark

> 以下是 external benchmark 主流程的 9 个脚本入口骨架。`<dataset-root>`、`<profile-root>`、`<profile-identity>` 和输出文件名必须替换成当前事实；长期身份与默认 adapter 先查 `docs/state/rag-current-state.md`。真实 embedding / LLM 命令会产生外部调用和费用，不得因超时自动重跑。

| 目标 | 命令骨架 |
|---|---|
| 只读检查数据集 | `python scripts\inspect_m34_enterprise_dataset.py --dataset-root <dataset-root> --output .agent_work\temp\m34-dataset-audit.json` |
| 构建 60/120 split | `python scripts\build_m34_case_split.py --dataset-root <dataset-root> --output .agent_work\temp\m34-case-split.json` |
| dev lexical recipe 对照 | `python scripts\run_m34_lexical_dev_experiment.py --dataset-root <dataset-root> --work-dir .agent_work\temp\m34-lexical-work --output .agent_work\temp\m34-lexical-dev.json` |
| 构建 external lexical profile | `python scripts\build_m34_external_profile.py --dataset-root <dataset-root> --profile-root <profile-root> --output .agent_work\temp\m34-profile-build.json`；只有明确要切 benchmark pointer 时才加 `--activate` |
| Retrieval Eval | `python scripts\run_m34_retrieval_eval.py --dataset-root <dataset-root> --profile-root <profile-root> --profile-identity <profile-identity> --scope diagnostic_dev --output .agent_work\temp\m34-retrieval-eval.json` |
| 本地 Tool → AnswerFlow smoke | `python scripts\smoke_m34_external_runtime.py --dataset-root <dataset-root> --profile-root <profile-root> --profile-identity <profile-identity> --output .agent_work\temp\m34-external-runtime-smoke.json` |
| 构建 / 恢复 semantic candidate | `python scripts\build_m34_semantic_candidate.py --dataset-root <dataset-root> --profile-root <profile-root> --profile-identity <profile-identity> --output .agent_work\temp\m34-semantic-build.json` |
| 真实 Qwen 三题 AnswerFlow smoke | `python scripts\smoke_m34_remote_answer.py --dataset-root <dataset-root> --profile-root <profile-root> --profile-identity <profile-identity> --output .agent_work\temp\m34-remote-answer-smoke.json` |
| 真实 Qwen 180 题 Answer Eval | `python scripts\run_m34_answer_eval.py --dataset-root <dataset-root> --profile-root <profile-root> --profile-identity <profile-identity> --output .agent_work\temp\m34-answer-eval.json` |
| M39 P6 只读 readiness audit | `python scripts\audit_m39_p6_readiness.py --split eval\cases\enterprise-rag-bench-v1.0.0-split.json --lexical-dev .agent_work\temp\m34-lexical-tool-dev-retrieval.json --lexical-held-out .agent_work\temp\m34-lexical-tool-heldout-retrieval.json --semantic-dev .agent_work\temp\m34-semantic-tool-dev-retrieval.json --semantic-held-out .agent_work\temp\m34-semantic-tool-heldout-retrieval.json --answer .agent_work\temp\m34-answer-eval-full-v4.json --output eval\reports\m39-p6-readiness.json --report eval\reports\m39-p6-readiness.md`；只读取已有 JSON，六份输入 hash/identity/split/runtime 任一不符即失败关闭，零 Tool/AnswerFlow/provider 调用。 |

## Eval 命令入口

> 当前 **Text2SQL** 正式入口为 M27 v3 canonical eval：一个 Scenario 只执行一次，Result / Context / Plan / Trace / Safety 等 typed assertion 共享同一份证据。v3 增加 Schema Context 物理字段/metric 静态校验，并修正宽表业务时间合同。Phase 4 安全/RAG/Harness 使用各自独立的 contract runner，M34 external retrieval/answer 使用上节脚本；三类结果不得混算。旧 formal / challenge / diagnostic YAML、报告与分数，以及 M27 v1/v2 artifact，都是只读历史证据；它们不再由当前 `eval.run_eval` CLI 生成新结果。历史口径与数字见 `docs/archive-versions/eval-baselines-old.md` 和 `docs/state/eval-baselines.md`。

> 真实 LLM eval 默认不自动运行。用户明确说“执行 / 跑 <selector 或 suite>”时，即授权**恰好一次**运行该命令；直接按当前默认配置执行，不重复询问授权。该授权覆盖既定临时环境变量、唯一 run ID、artifact/report/checkpoint 写入和状态轮询，但不覆盖扩大范围、额外重复运行或切换默认配置。

### 真实 Eval：选哪套业务题来跑

以下命令会执行 Pipeline；真实 LLM 调用次数见“适用场景 / 数量”列。

| 目标 | 适用场景 / 数量 | 命令骨架 | 说明 |
|---|---|---|---|
| Smoke selector | 改完链路先冒烟；4 题 / 4 次调用 | `python -m eval.run_eval --selector smoke --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | 检查 API、Guard、Trace、artifact 与报告；不代表完整能力。 |
| Core suite | 正式主回归；19 题 / 19 次调用 | `python -m eval.run_eval --suite core --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | required assertion 参与主 Gate。 |
| Stress suite | 验证复杂业务边界；9 题 / 9 次调用 | `python -m eval.run_eval --suite stress --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | 覆盖递归、SCD、退款、复杂 Join；默认 advisory。 |
| Reliability selector | 看波动与可用性；2 题 / 6 次调用 | `python -m eval.run_eval --selector reliability --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | 每题 3 个 replicate；分母仍是 2 个逻辑 Scenario。 |
| Database Exception selector | 验证异常数据口径；7 题 / 7 次调用 | `python -m eval.run_eval --selector database-exception --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | 选择 canonical Stress Scenario，不复制异常题正文。 |

### 复核与历史审计：跑完后怎么看

以下命令只读取已有材料，**不调用 LLM**，也不改变自动 EvalRun、分母或 Gate。

| 目标 | 适用场景 / 数量 | 命令骨架 | 说明 |
|---|---|---|---|
| M27 Codex / 人工复核 | 自动结果需逐题业务核验；0 次模型调用 | `python -m eval.run_review --run-id <run-id> [--verdicts-json <verdicts.json>]` | 读取 completed artifact、短期 checkpoint 与 catalog，生成带 SHA-256 来源指纹的独立 review bundle。 |
| 校验既有 review 来源 | 复核前确认材料未被替换；0 次模型调用 | `python -m eval.run_review --verify-bundle eval/reports/m27-reviews/<run-id>-review.json` | 对 artifact 与每题 checkpoint 重算 SHA-256；缺失、清理或改写都会失败。 |
| M26 audit（冻结审计） | 复核历史 run；数量随冻结输入 | `python -m eval.run_audit --trace <frozen-trace.jsonl> --report <frozen-report.md> --triage <frozen-triage.json> --output-prefix eval/reports/m26-audit` | 只读取旧 case/trace/report/triage；不调用 LLM、不重跑旧 scorer。 |

### 专项检查与辅助命令

这些命令用于查看配置或隔离诊断，**不生成端到端 Text2SQL 分数**。

| 目标 | 适用场景 / 数量 | 命令骨架 | 说明 |
|---|---|---|---|
| 查看 M27 CLI | 想确认参数；0 次调用 | `python -m eval.run_eval --help` | 查看 `--selector`、`--suite`、`--scenario`、`--replicate-count` 等参数。 |
| schema retrieval embedding-only | 只测检索召回；10 条 query | `python -m eval.run_schema_retrieval_benchmark --report eval/reports/<name>-schema-retrieval-report.md --top-k 12 --fusion-strategy weighted` | 不调用 PipelinePort / LLM SQL；Milvus 与 embedding 开关见 state 文档。 |

M27 artifact 默认写入 `eval/reports/m27-artifacts/`，短期 checkpoint 写入 `.agent_work/temp/m27-checkpoints/`，JSONL trace 写入 `eval/traces/`。报告中的 `eligible / observed / passed / failed / not_observed`、Gate 和可比性规则见 `docs/state/eval-baselines.md`。

新 Text2SQL Eval 会在一个 EvalRun 开始时构建一次 Schema vector index，注入该 run 的全部 Scenario，并在环境关闭时释放；artifact 的 resolved runtime identity 记录 `schema_vector_index_reuse=run_scoped` 及可用的 Milvus row count。若观察到逐题重建/重复整批 embedding，应视为生命周期回归，而不是正常耗时。

### Phase 4 business RAG 真实产品链路 Eval（M41）

> 这是 `/api/query → caller → turn → Router → Harness → RAG Tool → business AnswerFlow → Qwen Composer → API/Trace` 的产品 E2E。每个 Scenario/replicate 恰好执行一次产品请求，scorer、report、triage、review、compare 都只读该请求形成的共享 Evidence。它不同于 M31–M40 deterministic contract，也不同于 M34 绕过产品 Harness 的 external benchmark，三者不得混算。

真实命令使用独立 `phase4-rag-eval-business-generation-outbound-v1`：只在显式 M41 CLI 中允许已通过 caller/ACL/Gate 且属于 `role_restricted_policy_text` 或 `metric_definition` 的 generation context 发往 Qwen。`security_policy` 和未知类别在网络前失败关闭；普通 API 仍使用 deterministic Composer 和默认 `phase4-outbound-v1`。

| 目标 | Scenario / 最大 Qwen 调用 | 命令骨架 | 边界 |
|---|---:|---|---|
| 查看参数 | 0 | `python -m eval.run_rag_eval --help` | 不调用 provider。 |
| Smoke | 2 / 最多 1 | `python -m eval.run_rag_eval --selector smoke --run-id <run-id> --report eval/reports/<name>.md` | 一条需要 Qwen generation 的题 + 一条 no-candidate/no-generation 题；真实首次运行只授权这一档。 |
| Core | 3 / 最多 3 | `python -m eval.run_rag_eval --suite core --run-id <run-id> --report eval/reports/<name>.md` | 退款、发票、指标口径；必须在 smoke 检查后另行授权。 |
| Diagnostic | 2 / 最多 1 | `python -m eval.run_rag_eval --suite diagnostic --run-id <run-id> --report eval/reports/<name>.md` | 多文档为 advisory 诊断，另含 no-candidate。 |
| Reliability | 1×3 / 最多 3 | `python -m eval.run_rag_eval --suite reliability --run-id <run-id> --report eval/reports/<name>.md` | 同题三次 replicate，只用于波动/可用性。 |
| 精确单题 | N×replicate | `python -m eval.run_rag_eval --scenario <scenario-id> [--scenario <id>] --replicate-count <n> --run-id <run-id> --report eval/reports/<name>.md` | `--scenario` 与 selector/suite 互斥；题面仍只来自 canonical catalog。 |

默认位置：manifest/checkpoint/每题安全 Trace 在 `.agent_work/temp/m41-rag-checkpoints/<run-id>/`；completed artifact 在 `eval/reports/m41-rag-artifacts/<run-id>.json`；report/triage 使用 CLI 给定路径。没有 completed artifact 时，不得把 report、部分 checkpoint 或 M34 历史结果登记成 M41 基线。

RAG failure funnel 依次查看：产品 API/Harness/Trace → retrieved → selected → generation-visible → Composer/provider/support → cited → answer 自动下限与人工 correctness/completeness。上游不可用使下游 `not_observed`，不能批量伪造 semantic failed；`answer_status=complete`、命中 gold 或 citation 合法均不单独等于自然语言答案正确。

以下 M41 命令全部离线，零 Tool/LLM 调用：

| 目标 | 命令骨架 | 说明 |
|---|---|---|
| 生成 review bundle | `python -m eval.run_rag_review --artifact eval/reports/m41-rag-artifacts/<run-id>.json --checkpoint-dir .agent_work/temp/m41-rag-checkpoints --reviewer <name> --output eval/reports/<run-id>-review.json` | 每题保存 answer/citation/funnel/自动 assertions，并绑定 artifact 与 checkpoint SHA-256。 |
| 校验 review 来源 | `python -m eval.run_rag_review --bundle eval/reports/<run-id>-review.json --verify-only --output eval/reports/<run-id>-review-verified.json` | 任一来源缺失或 hash 改变即拒绝。 |
| 合并人工 verdict | `python -m eval.run_rag_review --bundle <bundle.json> --verdicts <verdicts.json> --output <reviewed.json>` | verdict key 为 `<scenario-id>:r<replicate>`，必须闭集覆盖；只与自动结果并列，不改 Gate。 |
| 严格 compare | `python -m eval.run_rag_compare --left <left.json> --right <right.json> --output <compare.json>` | catalog/selector/runtime/policy/scorer 任一不同即拒绝直接升降比较。 |
| M34 历史投影 | `python -m eval.run_rag_m34_history --source .agent_work/temp/m34-answer-eval-full-v4.json --output eval/reports/m34-answer-historical-view.json` | 校验 M34 artifact identity 后只读汇总；明确标记 external direct AnswerFlow，不冒充产品 E2E。 |

人工 review 首版采用 deterministic oracle 下限 + 人工裁决，不调用 LLM Judge。应复核全部自动失败/`not_observed`、所有高风险与多文档题，并抽样自动通过题；没有答案或引用/context 不足时只能标 `insufficient_evidence`，不能猜成 pass/fail。

### 真实 Eval 生命周期：等待、终态与重跑

一次用户授权只创建一个 `run_id`。前台工具等待超时不等于 Eval 已停止；使用同一个 `run_id` 检查下列位置，在 manifest 仍为 `running` 或 checkpoint 还在增加时只继续等待，不得换 ID 重跑。

| 材料 | 精确路径 | 说明 |
|---|---|---|
| 生命周期 manifest | `.agent_work/temp/m27-checkpoints/<run-id>/manifest.json` | `running`、`completed`、`interrupted` 或 `failed` 的唯一状态记录。 |
| 单题 checkpoint | `.agent_work/temp/m27-checkpoints/<run-id>/checkpoints/` | 每完成一题写入一份证据；文件继续增加说明 run 仍在推进。 |
| 长期 artifact | `eval/reports/m27-artifacts/<run-id>.json` | 只有 completed run 才生成；它是自动评测长期事实源。 |
| Markdown report | 命令的 `--report` 路径 | 由 completed artifact 投影而来，供阅读 Gate 和统计。 |

M41 RAG Eval 使用同一生命周期语义，但路径为 `.agent_work/temp/m41-rag-checkpoints/<run-id>/manifest.json`、同目录 `checkpoints/` 与 `traces/`、`eval/reports/m41-rag-artifacts/<run-id>.json`。如果进程在 Trace 已落盘、checkpoint 尚未提交时中断，runner 会以 `rag_execution_uncommitted_trace` 失败关闭，不能自动再次调用 provider；必须保留证据并由用户决定新 run。

只有原进程已经退出、manifest 明确为 `interrupted` / `failed` 且不存在 completed artifact 时，才能在用户授权范围内决定是否新建 run；原因必须先记入模块 notes。真实 LLM Eval 不临时拼装 `.ps1`、隐藏 PowerShell、计划任务或其他后台执行器。

### 真实 Eval 跑完后：怎样处理 Gate

| Gate | 大白话含义 | 下一步 |
|---|---|---|
| `passed` | 所有 required assertion 都有证据且通过。 | 可按 Review 覆盖规则复核；是否登记长期 baseline 仍由用户决定。 |
| `failed` | 已拿到候选答卷，但至少一条 required assertion 确实不符合合同。 | 先读 artifact / report / checkpoint 定位业务或合同问题；不要靠重跑掩盖失败。 |
| `inconclusive` | 有 required assertion 为 `not_observed`，常见原因是 timeout 或外部不可用。 | 不自动重跑、不登记正式 baseline；保留本轮证据，等待用户明确决定是否重跑。 |

### M27 Review 覆盖规则

- Core / Stress 运行后，优先复核**全部自动失败**、退款/SCD/金额/时间/递归等**高风险业务合同**，再抽取少量自动通过题作为误通过抽样；不是每次都机械复核全部通过题。
- 普通业务题没有 candidate SQL（例如外部服务不可用）时只能标 `insufficient_evidence`，意思是“没有足够材料判断”，不是模型答对或答错。只有 `safety_block` / `expected_rejection` 合同可以凭明确拦截证据判通过。
- verdict 还必须填写结构化分类：`confirmed_correct`、两类正确拒绝，或业务 SQL / 输出合同 / Schema Context / 其他合同错误，以及 `execution_evidence_unavailable`。分类只为汇总定位，**不参与自动 Gate 或 CI**。
- 新生成的 bundle 为 `m27-review-bundle-v2`。早期 v1 review 仅作历史证据，缺少来源哈希和上述限制，不能用新校验命令验证；需要时按原 run 重新生成 v2，而不是改写旧自动 EvalRun。

## 数据库维护与验证

涉及数据库结构、seed 或固定业务事实时，按需运行，不要把历史验收数字当成当前结果：

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic current
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic check
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.seed_data --reset
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_database_upgrade.py tests\test_m30_knowledge_catalog.py -q --basetemp=.agent_work\temp\pytest-db-current
git diff --check
```

`seed_data --reset` 会重建本地目标库，只在任务明确需要重置 seed 时运行。完整仓库 pytest 属于模块收工验证，按 AGENTS 的长时间命令规则执行，不作为每次数据库检查的默认动作。

## 运行纪律

- `.env` 的默认模型、默认 embedding、默认向量库属于长期基线选择；实验时优先在当前 shell 临时设置环境变量，不直接改默认。
- `LLM_MODEL` 当前保留，不取消；它是 DeepSeek provider 的显式模型入口。若后续要统一成所有 provider 共用 `LLM_MODEL`，需要做兼容迁移：Qwen 先读 `QWEN_MODEL`，缺省再 fallback 到 `LLM_MODEL`，并同步 `.env.example` / 文档 / 测试。
- 报告中的 `review_required` / `manual_review` 可能不等同命令行 failed 数；它表示“待处理 / 待人工判断”，用于闭环排队。M22 的 `manual_or_diagnostic` 视图会单列这类 case：请求仍会运行并记录 trace，但不把无法稳定自动判分的复杂语义题伪装成自动能力硬门。
