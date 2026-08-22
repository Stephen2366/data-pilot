# DataPilot Text2SQL Runbook

> Text2SQL、Schema Retrieval、SQL Eval 和数据库验证的运行入口。公共授权、Gate、长任务与重跑纪律先读 [`runbook.md`](runbook.md)。评测数字和失败账本见 [`eval-baselines.md`](eval-baselines.md)。

更新时间：2026-08-23

## 当前链路与默认值

`POST /api/query → Turn → Router → Harness → Text2SQL Tool → Schema Retrieval → QueryPlan → SQL Guard → SQL execution`

| 项目 | 当前值 |
|---|---|
| Text2SQL pipeline | 默认 `force_new_pipeline=true`；显式 `false` 只切 Tool 内部 legacy baseline，不绕过 Harness |
| 主模型 | `LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus` |
| Schema Retrieval | `SCHEMA_VECTOR_BACKEND=inmemory`、`SCHEMA_EMBEDDING_PROVIDER=deterministic` |
| 当前 Eval 协议 | `m27-v3`；旧 v1/v2 artifact 只作历史解释 |
| Trace | `eval/traces/` |

DeepSeek 对照必须显式设置 `LLM_PROVIDER=deepseek`、`LLM_MODEL=deepseek-v4-flash`。Qwen 读取 `QWEN_MODEL`，不要误用 `LLM_MODEL`。

## Text2SQL 真实 Eval

| 目标 | 数量 | 命令 |
|---|---:|---|
| 查看 CLI | 0 | `python -m eval.run_eval --help` |
| Smoke | 4 题 / 4 次 | `python -m eval.run_eval --selector smoke --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<run-id>.md` |
| Core | 19 题 / 19 次 | `python -m eval.run_eval --suite core --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<run-id>.md` |
| Stress | 9 题 / 9 次 | `python -m eval.run_eval --suite stress --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<run-id>.md` |
| Reliability | 2 题 × 3 次 | `python -m eval.run_eval --selector reliability --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<run-id>.md` |
| Database Exception | 7 题 / 7 次 | `python -m eval.run_eval --selector database-exception --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<run-id>.md` |
| 精确单题 | N × replicate | `python -m eval.run_eval --scenario <scenario-id> [--scenario <id>] --replicate-count <n> --run-id <run-id> --artifact-dir eval/reports/m27-artifacts --report eval/reports/<run-id>.md` |

M27 一个 Scenario 只运行一次 Pipeline；Result、Context、Plan、Trace、Safety 等 scorer 共享同一份执行证据。

## 产物与生命周期

| 材料 | 路径 |
|---|---|
| manifest | `.agent_work/temp/m27-checkpoints/<run-id>/manifest.json` |
| 单题 checkpoint | `.agent_work/temp/m27-checkpoints/<run-id>/checkpoints/` |
| completed artifact | `eval/reports/m27-artifacts/<run-id>.json` |
| Markdown report | CLI 的 `--report` 路径 |
| JSONL Trace | `eval/traces/` 或 `--trace-dir` 指定目录 |

新 EvalRun 在开头构建一次 run-scoped Schema vector index，并供全部 Scenario 复用。若逐题重建或重复整批 embedding，应视为生命周期回归。

## 离线人工复核

以下命令不调用 LLM，也不修改自动 Gate：

- 生成或合并 review：`python -m eval.run_review --run-id <run-id> [--verdicts-json <verdicts.json>]`
- 校验来源：`python -m eval.run_review --verify-bundle eval/reports/m27-reviews/<run-id>-review.json`

复核顺序：全部自动失败 → 金额、时间、退款、SCD、递归等高风险题 → 少量自动通过题。普通业务题没有 candidate SQL 时只能标 `insufficient_evidence`；只有具有明确拦截证据的 expected rejection 才能直接判通过。

## Schema Retrieval 专项诊断

当前默认是 inmemory + deterministic。Milvus / DashScope 仅用于显式实验；collection identity、embedding 维度和排障规则见 [`schema-retrieval-milvus-embedding.md`](schema-retrieval-milvus-embedding.md)。

| 目标 | 配置 / 命令 |
|---|---|
| Milvus | `SCHEMA_VECTOR_BACKEND=milvus` |
| DashScope embedding | `SCHEMA_EMBEDDING_PROVIDER=dashscope`、`QWEN_EMBEDDING_MODEL=qwen3.7-text-embedding`、`QWEN_EMBEDDING_DIMENSIONS=1024` |
| embedding-only benchmark | `python -m eval.run_schema_retrieval_benchmark --report eval/reports/<name>-schema-retrieval-report.md --top-k 12 --fusion-strategy weighted` |

Milvus 未启动时先停止并说明，不要静默切换 backend 后声称是同一次实验。

## 数据库检查

```powershell
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic current
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m alembic check
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest tests\test_database_upgrade.py -q --basetemp=.agent_work\temp\pytest-db-current
```

只有明确需要重建本地 seed 时才运行：

`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.seed_data --reset`

SQL 字段、业务事实和 oracle 以 [`database-current-state.md`](database-current-state.md) 为准，不把旧报告中的数据当成当前数据库事实。

## 结果怎么定位

按顺序检查：Router/Harness → Schema Context → QueryPlan → SQL Guard → execution → result contract → business oracle。外部模型不可用属于 `not_observed`，不能伪造成 SQL 错误；SQL 能执行也不代表业务口径正确。
