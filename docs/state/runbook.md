# DataPilot Runbook

> 本文是 DataPilot 的运行入口：只说明“怎么开启哪条链路、怎么跑命令、哪些默认不能随手改”。Trigger：只要要运行命令、切模型、开 LangFuse、跑 eval、改环境变量，必须先读本文。当前状态先读 `docs/state/AI_CONTEXT.md`，评测数字和错因追溯读 `docs/state/eval-baselines.md`，Milvus / embedding 细节读 `docs/state/schema-retrieval-milvus-embedding.md`。

更新时间：2026-08-09

## 模型链路

| 目标 | 环境变量 | 说明 |
|---|---|---|
| 默认 Qwen 主链路 | `LLM_PROVIDER=qwen`；`QWEN_MODEL=qwen3.7-plus` | 当前默认。Qwen provider 读取 `QWEN_MODEL`，不是 `LLM_MODEL`。`.env` 中的 `LLM_MODEL=deepseek-v4-flash` 仅作为显式切回 DeepSeek 时的备用入口。 |
| API Text2SQL 路径 | 默认 `force_new_pipeline=true`；显式 `false` | 普通 `/api/query` 默认走 Schema Retrieval → QueryPlan → SQL Guard 的新链路；`false` 只保留给 legacy baseline 兼容排障。 |
| DeepSeek 主模型对照 | `LLM_PROVIDER=deepseek`；`LLM_MODEL=deepseek-v4-flash` | 显式切换时使用；`LLM_MODEL` 在现有代码语义里主要服务 DeepSeek provider。 |
| LLM 可靠性配置 | `LLM_TIMEOUT_SECONDS=45`；`LLM_MAX_RETRIES=0`；`LLM_RETRY_BACKOFF_SECONDS=1` | M25 默认不自动重试。只对明确标记为 transient 的 timeout / 网络 / 429 / 5xx 生效；聚焦实验在当前 shell 临时覆盖，不直接改 `.env` 默认。 |
| Legacy L3 judge | `EVAL_JUDGE_MODEL=<模型名>` | 仅服务冻结旧 runner 语义；当前 M27 CLI 不提供 `--judge-model`，也不把 LLM-as-Judge 作为默认裁决器。 |

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
| 本地 M27 eval | `LANGFUSE_ENABLED=false`；按下方 selector 命令运行 | completed EvalRun JSON + Markdown report 是新事实源；M27 不生成旧 triage JSON。 |
| LangFuse Cloud trace/score | `LANGFUSE_ENABLED=true`，必要时 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897` | Cloud 仍是旁路增强；M27 当前只构造严格 allowlist assertion payload，实际上传需显式授权，不能影响本地 EvalRun。 |
| LangFuse smoke | `python scripts\smoke_phase3b_langfuse.py`；Cloud 硬门禁加 `--require-langfuse` | M18 的主验证入口，用于 API / JSONL / trace mapping / score / visibility。 |

## Eval 命令入口

> 当前正式入口为 **M27 v2 canonical eval**：一个 Scenario 只执行一次，Result / Context / Plan / Trace / Safety 等 typed assertion 共享同一份证据。旧 formal / challenge / diagnostic YAML、报告与分数，以及 M27 v1 artifact，都是只读历史证据；它们不再由当前 `eval.run_eval` CLI 生成新结果。历史口径与数字见 `docs/archive-versions/eval-baselines-old.md` 和 `docs/state/eval-baselines.md`。

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

### 前台等待超时：到哪里检查

前台工具等待超时不等于 Eval 已停止。使用同一个 `run_id` 检查下列位置；在 manifest 仍为 `running` 或 checkpoint 还在增加时，只继续等待，不得换 ID 重跑。

| 材料 | 精确路径 | 说明 |
|---|---|---|
| 生命周期 manifest | `.agent_work/temp/m27-checkpoints/<run-id>/manifest.json` | `running`、`completed`、`interrupted` 或 `failed` 的唯一状态记录。 |
| 单题 checkpoint | `.agent_work/temp/m27-checkpoints/<run-id>/checkpoints/` | 每完成一题写入一份证据；文件继续增加说明 run 仍在推进。 |
| 长期 artifact | `eval/reports/m27-artifacts/<run-id>.json` | 只有 completed run 才生成；它是自动评测长期事实源。 |
| Markdown report | 命令的 `--report` 路径 | 由 completed artifact 投影而来，供阅读 Gate 和统计。 |

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

### 长时间真实 Eval 的执行纪律

- 默认直接在当前终端执行一次 `python -m eval.run_eval`；一次用户授权只创建一个 `run_id`。`run_id` 就是本次评测的唯一准考证号，用来绑定 checkpoint、artifact 和报告，不能拿它反复重跑。
- 前台工具等待超时**不等于** Eval 已停止。按上方“前台等待超时”表检查同一 `run_id` 的 manifest、checkpoint 和 artifact；checkpoint 仍增长或 manifest 为 `running` 时，只继续等待和轮询，禁止换 `run_id` 重跑。
- 普通 Smoke / Core 不要临时使用 `.ps1`、隐藏 PowerShell、计划任务或额外终端。它们不是项目的正式入口，容易让一次授权意外变成多次真实调用。
- 只有确认原 run 进程已经退出、manifest 明确为 `interrupted` / `failed`、且没有 completed artifact 时，才可新建 `run_id` 重跑；必须先在模块 notes 记录原因。
- 若未来确实需要后台执行能力，应单独设计、测试并取得用户确认一个固定入口；不能在真实 LLM 基线期间临时拼装执行器。

## 运行纪律

- `.env` 的默认模型、默认 embedding、默认向量库属于长期基线选择；实验时优先在当前 shell 临时设置环境变量，不直接改默认。
- `LLM_MODEL` 当前保留，不取消；它是 DeepSeek provider 的显式模型入口。若后续要统一成所有 provider 共用 `LLM_MODEL`，需要做兼容迁移：Qwen 先读 `QWEN_MODEL`，缺省再 fallback 到 `LLM_MODEL`，并同步 `.env.example` / 文档 / 测试。
- 报告中的 `review_required` / `manual_review` 可能不等同命令行 failed 数；它表示“待处理 / 待人工判断”，用于闭环排队。M22 的 `manual_or_diagnostic` 视图会单列这类 case：请求仍会运行并记录 trace，但不把无法稳定自动判分的复杂语义题伪装成自动能力硬门。
