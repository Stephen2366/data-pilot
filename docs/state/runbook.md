# DataPilot Runbook

> 本文是 DataPilot 的运行入口：只说明“怎么开启哪条链路、怎么跑命令、哪些默认不能随手改”。Trigger：只要要运行命令、切模型、开 LangFuse、跑 eval、改环境变量，必须先读本文。当前状态先读 `docs/state/AI_CONTEXT.md`，评测数字和错因追溯读 `docs/state/eval-baselines.md`，Milvus / embedding 细节读 `docs/state/schema-retrieval-milvus-embedding.md`。

更新时间：2026-08-02

## 模型链路

| 目标 | 环境变量 | 说明 |
|---|---|---|
| 默认 DeepSeek 主链路 | `LLM_PROVIDER=deepseek`；`LLM_MODEL=deepseek-v4-flash` | 当前默认。`LLM_MODEL` 在现有代码语义里主要服务 DeepSeek provider；不要把它误读成所有 provider 的统一模型名。 |
| Qwen 主模型对照 | `LLM_PROVIDER=qwen`；`QWEN_MODEL=qwen3.7-max` 或 `qwen3.7-plus` | Qwen provider 当前读取 `QWEN_MODEL`，不是 `LLM_MODEL`。`.env` 里保留 `LLM_MODEL=deepseek-v4-flash` 不会影响 Qwen run。 |
| L3 judge | `EVAL_JUDGE_MODEL=<模型名>` 或 CLI `--judge-model <模型名>` | 默认关闭；只影响 eval 追加的 L3 judge，不改变业务 NL2SQL 主模型。 |

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
| 本地 JSONL trace | 默认即可，或在测试中指定 `--trace .agent_work\temp\<name>.jsonl` | 默认不依赖 LangFuse；JSONL 默认不提交。 |
| 本地 eval + triage | `LANGFUSE_ENABLED=false`；`python -m eval.run_eval ... --triage-json .agent_work\temp\<name>-triage.json` | 生成 Markdown report 和本地 triage JSON；`langfuse_triage_scores` 显示 skipped 属正常。 |
| LangFuse Cloud trace/score | `LANGFUSE_ENABLED=true`，必要时 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7897` | Cloud 是旁路增强；写入失败不应影响本地 eval 结果。 |
| LangFuse smoke | `python scripts\smoke_phase3b_langfuse.py`；Cloud 硬门禁加 `--require-langfuse` | M18 的主验证入口，用于 API / JSONL / trace mapping / score / visibility。 |

## Eval 命令入口

> Eval 集合关系：
>
> - `formal`：主线回归集，文件为 `eval/cases/phase3a-regression.yaml`，当前 10 条。
> - `challenge`：数据库升级压力集，文件为 `eval/cases/database-upgrade-challenge.yaml`，当前 16 条；其中 10 条与 `formal` 重复 / 等价，因此它不是与 formal 互斥的新样本集。
> - `diagnostic`：排障扩展 run，当前命令为 `database-upgrade-challenge.yaml + phase3a-diagnostic-benchmark.yaml`；也就是完整包含 `challenge`，并通过 challenge 间接覆盖那 10 条 formal 重复 / 等价 case。
> - 真实 LLM eval 有非确定性；同一个 case 分开跑两次，结果可能不同。
>
> - 做日常验收或冒烟时，可按需要分别跑 `formal` / `challenge` / `diagnostic`：`formal` 看主线回归，`challenge` 看数据库升级压力，`diagnostic` 看失败结构和排障线索。
>
> - 做严谨对比或排查重复 case 稳定性时，优先跑一次 `diagnostic` 作为统一采样入口，再按 `case_id` / 来源切出 `formal`、`challenge` 子集统计；不要用三次独立 run 直接互相比。

| 目标 | 命令骨架 | 说明 |
|---|---|---|
| smoke | `python -m eval.run_eval --cases eval\cases\smoke.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\<name>-traces.jsonl --report .agent_work\temp\<name>-report.md --triage-json .agent_work\temp\<name>-triage.json` | 快速确认链路活着，不替代 benchmark。 |
| formal | `python -m eval.run_eval --cases eval\cases\phase3a-regression.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\<name>-formal-traces.jsonl --report .agent_work\temp\<name>-formal-report.md --triage-json .agent_work\temp\<name>-formal-triage.json` | 主线回归对照。 |
| challenge | `python -m eval.run_eval --cases eval\cases\database-upgrade-challenge.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\<name>-challenge-traces.jsonl --report .agent_work\temp\<name>-challenge-report.md --triage-json .agent_work\temp\<name>-challenge-triage.json` | 更难的数据库升级题。 |
| diagnostic | `python -m eval.run_eval --cases eval\cases\database-upgrade-challenge.yaml --extra-cases eval\cases\phase3a-diagnostic-benchmark.yaml --pipeline-mode new_text2sql --trace .agent_work\temp\<name>-diagnostic-traces.jsonl --report .agent_work\temp\<name>-diagnostic-report.md --triage-json .agent_work\temp\<name>-diagnostic-triage.json` | 定位边界和失败结构，不追满分。 |
| failure distribution 对比 | `python -m eval.run_eval --compare-triage-left <left>.json --compare-triage-right <right>.json --compare-triage-report .agent_work\temp\<name>-compare.md` | M19 A/B 入口，看失败结构变化，不只看总分。 |

## 运行纪律

- `.env` 的默认模型、默认 embedding、默认向量库属于长期基线选择；实验时优先在当前 shell 临时设置环境变量，不直接改默认。
- `LLM_MODEL` 当前保留，不取消；它是 DeepSeek 默认模型入口。若后续要统一成所有 provider 共用 `LLM_MODEL`，需要做兼容迁移：Qwen 先读 `QWEN_MODEL`，缺省再 fallback 到 `LLM_MODEL`，并同步 `.env.example` / 文档 / 测试。
- M19 triage 的 `review_required` / `manual_review` 可能不等同命令行 failed 数；它表示“待处理/待人工判断”，用于闭环排队。
