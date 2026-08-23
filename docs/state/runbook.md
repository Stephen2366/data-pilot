# DataPilot Runbook

> DataPilot 的公共运行入口。运行任何项目命令前先读本文，再按任务进入 Text2SQL 或 RAG 专用 runbook。当前状态见 `AI_CONTEXT.md`，评测数字见 `eval-baselines.md`；本文不保存历史实验和基线数字。

更新时间：2026-08-23

## 先选链路

| 要做什么 | 必读入口 |
|---|---|
| Text2SQL、Schema Retrieval、SQL Eval、数据库验证 | [`runbook-text2sql.md`](runbook-text2sql.md) |
| 业务 RAG、M34 external、180 题 Eval、RAG review | [`runbook-rag.md`](runbook-rag.md) |
| 启动 API、调用 `/api/query`、查看 Trace、判断 Eval 生命周期 | 继续读本文 |

用户只说“eval / 评测 / core / smoke / reliability”而未指明 Text2SQL 还是 RAG 时，先问一句再路由；`stress` 仅 Text2SQL，`basic / hard / full / business / held-out` 仅 RAG。

## 公共环境

- 默认模型：`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`
- 默认可靠性：`LLM_TIMEOUT_SECONDS=45`、`LLM_MAX_RETRIES=0`、`LLM_RETRY_BACKOFF_SECONDS=1`
- 实验配置只在当前 shell 临时覆盖；不得顺手修改 `.env`、默认模型、embedding、向量库或 active identity。

## API / Harness

- 统一入口：`POST /api/query`。
- `APP_ENV=local|demo|test` 才注入 fixture caller resolver；请求里的 `user_role` 只能选择 fixture 身份，不能自行授权。
- 其他环境没有 authenticated resolver 时，在 Tool 前以 `caller_untrusted` 失败关闭。
- 最小请求：`{"question":"这个怎么处理？","user_role":"ops"}`。
- resume 必须同时提交 `thread_id`、`expected_version`、`clarification_answers`。
- follow-up 必须先在 initial 中显式设置 `enable_bounded_follow_up=true`，再严格提交响应声明的 action/fields。
- clear：`DELETE /api/query/threads/{thread_id}?user_role=<role>&expected_version=<version>`。
- 进程内 thread checkpoint 默认 TTL：`THREAD_CHECKPOINT_TTL_SECONDS=900`；重启或多 worker 不恢复、不共享。
- M43 Agent task family 仍走同一 `POST /api/query`，只有请求携带严格 nested envelope 才启用：start 为 `"task":{"action":"start"}`；continue/switch/cancel 必须同时提交服务端上一响应的 `task_id` 与 `expected_version`。task envelope 与 legacy thread/follow-up payload 互斥，客户端不得提交 delta/state/route/Evidence/runtime 字段。
- task clear：`DELETE /api/query/tasks/{task_id}?user_role=<role>&expected_version=<version>`。M43 task boundary 与 thread checkpoint 分离，但同样是进程内、默认 TTL 900s、重启/多 worker 不恢复；真正 durable task state 属于 B5，不得把当前 adapter 作为持久化能力。
- B1 零 provider rehearsal：`python -m scripts.rehearse_m43_b1`。它只复核 B1 contract、TaskState/Evidence invalidation、node Context、Scenario v2 和冻结 SQL oracle，输出到 `eval/reports/m43/`；不运行真实 LLM、embedding、数据库或 sealed reserve。

## Trace / LangFuse

- 本地 JSONL Trace 默认写入 `eval/traces/`；`/api/query` 主 Trace 为 `eval/traces/traces.jsonl`。
- Trace 不保存 Document 正文、完整 SQL rows、private Evidence、raw thread id/raw task id 或结构化 thread/task 参数副本；Agent task Trace 只增加安全 task lifecycle/state/delta/transition/node-context 投影。
- LangFuse 默认关闭。只有显式任务才设置 `LANGFUSE_ENABLED=true`；Cloud 只是旁路增强，不能影响本地 EvalRun。
- LangFuse 专项排障不放在本 runbook；需要时按 `AI_CONTEXT.md` 和历史索引进入对应资料。

## 真实 Eval 公共纪律

1. 真实 LLM Eval 默认不自动运行。
2. 用户明确说“执行 / 跑某个 selector、suite 或 partition”时，只授权该范围恰好一次；不重复询问，也不扩大范围、换默认或额外重跑。未指明 Text2SQL/RAG 不算“明确说”，先问一句，不属重复询问。
3. 一个授权只创建一个 `run_id`。前台等待超时不代表运行结束，必须检查同一 run 的 manifest、checkpoint、artifact。
4. manifest 仍为 `running` 或 checkpoint 继续增加时只等待；禁止换 ID 重跑。
5. completed artifact 才是自动评测事实源；部分 checkpoint、Markdown report 或历史投影不能冒充 completed run。
6. 真实运行后必须记录 usage、失败层、artifact identity 和 review 证据；基线是否登记由用户决定。

| Gate | 含义 | 处理 |
|---|---|---|
| `passed` | required assertions 全部有证据且通过 | 继续人工复核；不自动登记长期基线 |
| `failed` | 已观察到确定的合同失败 | 按分层证据定位，禁止靠重跑掩盖 |
| `inconclusive` | required assertions 存在 `not_observed` | 保留证据，不自动重跑或登记基线 |

## 长任务与验证

- 长任务纪律（后台、日志路径、checkpoint、汇报方式）按 `AGENTS.md`「长时间命令与余额控制」执行。
- 完整仓库验证：`python -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\pytest-<name>`
- 改动后运行：`git diff --check`

## 数据库安全提醒

数据库重置见 Text2SQL runbook
