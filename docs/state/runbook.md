# DataPilot Runbook

> 本文是 DataPilot 的运行入口：只说明“怎么开启哪条链路、怎么跑命令、哪些默认不能随手改”。Trigger：只要要运行命令、切模型、开 LangFuse、跑 eval、改环境变量，必须先读本文。当前状态先读 `docs/state/AI_CONTEXT.md`，评测数字和错因追溯读 `docs/state/eval-baselines.md`，Milvus / embedding 细节读 `docs/state/schema-retrieval-milvus-embedding.md`。

更新时间：2026-08-09

## 模型链路

| 目标 | 环境变量 | 说明 |
|---|---|---|
| 默认 Qwen 主链路 | `LLM_PROVIDER=qwen`；`QWEN_MODEL=qwen3.7-plus` | 当前默认。Qwen provider 读取 `QWEN_MODEL`，不是 `LLM_MODEL`。`.env` 中的 `LLM_MODEL=deepseek-v4-flash` 仅作为显式切回 DeepSeek 时的备用入口。 |
| DeepSeek 主模型对照 | `LLM_PROVIDER=deepseek`；`LLM_MODEL=deepseek-v4-flash` | 显式切换时使用；`LLM_MODEL` 在现有代码语义里主要服务 DeepSeek provider。 |
| LLM 可靠性配置 | `LLM_TIMEOUT_SECONDS=45`；`LLM_MAX_RETRIES=0`；`LLM_RETRY_BACKOFF_SECONDS=1` | M25 默认不自动重试。只对明确标记为 transient 的 timeout / 网络 / 429 / 5xx 生效；聚焦实验在当前 shell 临时覆盖，不直接改 `.env` 默认。 |
| Legacy L3 judge | `EVAL_JUDGE_MODEL=<模型名>` | 仅服务冻结旧 runner 语义；当前 M27 CLI 不提供 `--judge-model`，也不把 LLM-as-Judge 作为默认裁决器。 |

## Schema Retrieval / Embedding 链路

> 如果用户要求使用 Milvus 相关链路，但未开启 Docker 或 Milvus，先提醒。collection 纪律、`schema_docs_hash`、M20 clean run 结论和排查菜单见 `docs/state/schema-retrieval-milvus-embedding.md`。

| 目标 | 环境变量 | 说明 |
|---|---|---|
| 默认本地检索 | `SCHEMA_VECTOR_BACKEND=inmemory`；`SCHEMA_EMBEDDING_PROVIDER=deterministic` | 当前主线默认，轻量、稳定、无需外部服务。 |
| Milvus 向量库 | `SCHEMA_VECTOR_BACKEND=milvus` | 只显式实验时开启；需要本地 Milvus 服务可用。 |
| SiliconFlow embedding | `SCHEMA_VECTOR_BACKEND=milvus`；`SCHEMA_EMBEDDING_PROVIDER=siliconflow`；`SILICONFLOW_EMBEDDING_MODEL=BAAI/bge-m3` | 可用但未切默认；真实 API 调用放 smoke / A/B。 |
| DashScope/Qwen embedding | `SCHEMA_VECTOR_BACKEND=milvus`；`SCHEMA_EMBEDDING_PROVIDER=dashscope` 或 `qwen`；`DASHSCOPE_EMBEDDING_MODEL=qwen3.7-text-embedding` | formal 曾略好，但差距小且受 LLM 波动影响，后续 RAG / Hybrid 再评估。 |

## LangFuse / Trace 链路

| 目标 | 环境变量 / 命令 | 说明 |
|---|---|---|
| 本地 JSONL trace | M27 默认写入 `eval/traces/`，可用 `--trace-dir eval/traces` 指定目录 | 默认不依赖 LangFuse；JSONL 默认不提交。 |
| 本地 M27 eval | `LANGFUSE_ENABLED=false`；按下方 selector 命令运行 | completed EvalRun JSON + Markdown report 是新事实源；M27 不生成旧 triage JSON。 |
| LangFuse Cloud trace/score | `LANGFUSE_ENABLED=true`，必要时 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897` | Cloud 仍是旁路增强；M27 当前只构造严格 allowlist assertion payload，实际上传需显式授权，不能影响本地 EvalRun。 |
| LangFuse smoke | `python scripts\smoke_phase3b_langfuse.py`；Cloud 硬门禁加 `--require-langfuse` | M18 的主验证入口，用于 API / JSONL / trace mapping / score / visibility。 |

## Eval 命令入口

> 当前正式入口为 **M27 canonical eval**：一个 Scenario 只执行一次，Result / Context / Plan / Trace / Safety 等 typed assertion 共享同一份证据。旧 formal / challenge / diagnostic YAML、报告与分数是只读历史证据；它们不再由当前 `eval.run_eval` CLI 生成新结果。历史口径与数字见 `docs/archive-versions/eval-baselines-old.md`。

> 真实 LLM eval 默认不自动运行。用户明确要求执行某个 eval（如“跑 Smoke”“执行 Core eval”）即视为该命令的授权，直接按当前默认配置运行。

| 目标 | 适用场景 / 数量 | 命令骨架 | 说明 |
|---|---|---|---|
| 查看 M27 CLI（无模型调用） | 想确认参数；0 次调用 | `python -m eval.run_eval --help` | 确认 `--selector`、`--suite`、`--scenario`、`--replicate-count` 等新参数。 |
| Smoke selector | 改完链路先冒烟；4 题 / 4 次调用 | `python -m eval.run_eval --selector smoke --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | 检查 API、Guard、Trace、artifact 与报告；不代表完整能力。 |
| Core suite | 正式主回归；19 题 / 19 次调用 | `python -m eval.run_eval --suite core --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | required assertion 参与主 Gate。 |
| Stress suite | 验证复杂业务边界；9 题 / 9 次调用 | `python -m eval.run_eval --suite stress --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | 覆盖递归、SCD、退款、复杂 Join；默认 advisory。 |
| Reliability selector | 看波动与可用性；2 题 / 6 次调用 | `python -m eval.run_eval --selector reliability --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | 每题 3 个 replicate；分母仍是 2 个逻辑 Scenario。 |
| Database Exception selector | 验证异常数据口径；7 题 / 7 次调用 | `python -m eval.run_eval --selector database-exception --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<name>.md` | 选择 canonical Stress Scenario，不复制异常题正文。 |
| M26 audit（冻结审计，无模型调用） | 复核历史 run；数量随冻结输入 | `python -m eval.run_audit --trace <frozen-trace.jsonl> --report <frozen-report.md> --triage <frozen-triage.json> --output-prefix eval/reports/m26-audit` | 只读取旧 case/trace/report/triage；不调用 LLM、不重跑旧 scorer。 |
| schema retrieval embedding-only | 只测检索召回；10 条 query | `python -m eval.run_schema_retrieval_benchmark --report eval/reports/<name>-schema-retrieval-report.md --top-k 12 --fusion-strategy weighted` | 不调用 PipelinePort / LLM SQL；Milvus 与 embedding 开关见 state 文档。 |

M27 artifact 默认写入 `eval/reports/m27-artifacts/`，短期 checkpoint 写入 `.codex/temp_work/m27-checkpoints/`，JSONL trace 写入 `eval/traces/`。报告中的 `eligible / observed / passed / failed / not_observed`、Gate 和可比性规则见 `docs/state/eval-baselines.md`。

## 运行纪律

- `.env` 的默认模型、默认 embedding、默认向量库属于长期基线选择；实验时优先在当前 shell 临时设置环境变量，不直接改默认。
- `LLM_MODEL` 当前保留，不取消；它是 DeepSeek provider 的显式模型入口。若后续要统一成所有 provider 共用 `LLM_MODEL`，需要做兼容迁移：Qwen 先读 `QWEN_MODEL`，缺省再 fallback 到 `LLM_MODEL`，并同步 `.env.example` / 文档 / 测试。
- 报告中的 `review_required` / `manual_review` 可能不等同命令行 failed 数；它表示“待处理 / 待人工判断”，用于闭环排队。M22 的 `manual_or_diagnostic` 视图会单列这类 case：请求仍会运行并记录 trace，但不把无法稳定自动判分的复杂语义题伪装成自动能力硬门。
