# DataPilot Runbook

> DataPilot 的公共运行入口。运行任何项目命令前先读本文，再按任务进入 Text2SQL 或 RAG 专用 runbook。当前状态见 `AI_CONTEXT.md`，评测数字见 `eval-baselines.md`；本文不保存历史实验和基线数字。

更新时间：2026-08-24

## 先选链路

| 要做什么 | 必读入口 |
|---|---|
| Text2SQL、Schema Retrieval、SQL Eval、数据库验证 | [`runbook-text2sql.md`](runbook-text2sql.md) |
| 业务 RAG、M34 external、180 题 Eval、RAG review | [`runbook-rag.md`](runbook-rag.md) |
| 启动 API、调用 `/api/query`、查看 Trace、判断 Eval 生命周期 | 继续读本文 |

用户只说“eval / 评测 / core / smoke / reliability”而未指明 Text2SQL 还是 RAG 时，先问一句再路由；`stress` 仅 Text2SQL，`basic / hard / full / business / held-out` 仅 RAG。

口令映射：用户说“执行当前模块的 Probe / 开发期真实探针”，且当前 plan 已预注册 Probe ID 与场景时，按本文 standing authorization 直接执行；用户说 `smoke/core/reliability/held-out/eval` 等 selector 时，走 Formal Eval 精确授权。只说“跑个真实测试看看”但没有已注册 Probe 或范围不明时，先确定最小场景，不能解释成任意 Eval 授权。

模块收工后的单次真实运行不追溯算作 Live Dev Probe；没有 Formal Eval selector 时也不是 Formal Eval。它必须由用户明确授权场景和预算，标记 `exploratory / baseline-ineligible / not-development-probe`，只执行一次、不自动重跑、不登记基线，并默认遵守 Live Dev Probe 的安全禁区；需要扩大禁区边界时另行确认。

## 公共环境

- 默认模型：`LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`
- 默认可靠性：`LLM_TIMEOUT_SECONDS=45`、`LLM_MAX_RETRIES=0`、`LLM_RETRY_BACKOFF_SECONDS=1`；本机 `.env` 已覆盖 `LLM_TIMEOUT_SECONDS=120`（2026-08-23，Qwen 比较类 QueryPlan 实测 43~105s），config 默认仍 45。
- 实验配置只在当前 shell 临时覆盖；不得顺手修改 `.env`、默认模型、embedding、向量库或 active identity。

## API / Harness

- 统一入口：`POST /api/query`。
- EnterpriseRAG-Bench 产品 RAG 的环境变量、Milvus preflight 和 Uvicorn 启动方式见 `runbook-rag.md`；应用不会自动启动 Docker/Milvus。
- `GET /health` 是进程 liveness；`GET /health/rag` 是 Enterprise RAG readiness。后者 503 时 RAG 失败关闭且零 Evidence/Composer，但 SQL 与 liveness 仍可工作；不得把它解释成 lexical fallback。
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
- M44 B2 task 使用独立 bounded Decision Loop：客户端仍只提交自然语言与严格 task envelope，不能提交 Action、budget、knowledge scope/runtime 或 repair 指令。Response/Trace 会增量返回安全的 `action_attempts`、`agent_budget`、`agent_termination`、`knowledge_runtimes` 与 `agent_loop_runtime`；普通非 task API 仍保持 M44A Enterprise RAG 默认。
- B2 零 provider rehearsal：`python -m scripts.rehearse_m44_b2`。它复核 T3 Observation 驱动的原因→商品动作、T4 business Hybrid、T5 correction/reauthorization、单次 dialect repair、negative no-extra-action 与 Agent Scenario v3，输出到 `eval/reports/m44/`；external calls 固定为 0。
- SQL repair 仅由服务端将 `sql_dialect_incompatible` + `mysql_unsupported_date_trunc` 准入一次，并使用独立 `sql_repair` outbound purpose；timeout、provider unavailable、generic DB error 和 Guard deny 均不自动 retry。真实 provider repair showcase 仍须按本 runbook 的真实运行纪律单独授权。

## Trace / LangFuse

- 本地 JSONL Trace 默认写入 `eval/traces/`；`/api/query` 主 Trace 为 `eval/traces/traces.jsonl`。
- SQL 单路（含 agent task SQL）JSONL Trace 沿用历史兼容合同：可保存已经 SQL Guard 且已授权执行的 `columns/rows`，供本地排障与 Response/Trace 对账。Hybrid Trace 仍必须清空完整 SQL rows；所有 Trace 均不得保存 Document 正文、private Evidence、raw DB error、Prompt、raw thread id/raw task id 或结构化 thread/task 参数副本。Agent task 的 action Observation/node Context/Scenario artifact 也不得借此例外携带 rows。
- LangFuse 默认关闭。只有显式任务才设置 `LANGFUSE_ENABLED=true`；Cloud 只是旁路增强，不能影响本地 EvalRun。
- LangFuse 专项排障不放在本 runbook；需要时按 `AI_CONTEXT.md` 和历史索引进入对应资料。

## Live Dev Probe（开发期真实探针）

Live Dev Probe 用少量真实 API、LLM、MySQL、Milvus/RAG 调用检查产品效果，防止只靠 pytest/fake 形成“合同通过但真实体验不可用”。本节是其 standing authorization、计数口径、默认额度、禁区、重验与 Formal Eval 分账的唯一事实源；满足下述边界时开发中无需逐次询问。

1. **适用与设计**：module plan 必须先判断是否适用，并冻结 Probe ID、真实场景、产品入口、观察字段、三态标准、预算、停止条件和切片时点。修改真实 LLM、数据库、RAG/Milvus、API 多轮或外部 runtime 行为时默认适用；纯静态合同/数据结构可说明理由后跳过。预注册 Probe 是计划基线而非上限。开发中出现计划外的真实失败、新假设或需要判别的最小场景时，可以动态追加 Probe：AI 必须主动向用户提出（场景、理由、真实链路、预计 calls/tokens、与 standing 额度及预注册清单的关系、停止条件），获得明确授权后才能执行，并按与预注册相同的口径记录三态、usage 与 `continue/revise/stop` 决定。不得因 token 成本自行放弃提案，也不得把未授权追加解释成 standing authorization。追加指新的最小判别场景，不是对同一场景重复抽样；重跑纪律仍按第 7 条。

2. **开发时点与阻塞门**：第一条真实纵向链路可运行后执行首个 Probe；后续 Probe 在对应关键切片完成后、依赖其结果的下一切片开始前执行。notes 开工 checklist 要预登记 `after Mx-A / before Mx-B` 一类时点。Probe 必须先形成 `passed / failed / inconclusive` 观察结果和对应的 `continue / revise / stop` 开发决策；只有 `continue` 才能放行被它阻塞的下一切片，`revise` 必须先修复并按第 7 条最小重验，`stop` 暂停对应分支。禁止把所有 Probe 统一拖到代码冻结或 `finish-module`。
3. **开发决策证据**：Probe 后立刻记录执行时间、当时代码阶段、HEAD/模块 dirty、命令/依赖、Response/Trace identity/usage、总体 Gate 和关键子能力三态，以及 `continue / revise / stop` 决定；具体观察项见第 5 条。失败或未触发时还要写首个失败层、当前根因假设和下一个最小判别动作；`not_exercised` 是子能力记为 `inconclusive` 的原因，不是第四种三态值。总体通过不得覆盖未触发分支；预登记的安全拒绝若精确命中负断言，该断言记 `passed`，不误记为场景失败。notes 中 Probe→决策→修改/重验必须保持时间顺序；HEAD 只是提交基线，高风险模块可再记限定范围的 diff hash。
4. **计数口径与默认额度**：一次 `provider call` 是一次真实出站尝试，不等于一个 turn/API 请求；chat、embedding、repair 和 retry 都逐次计数。出站只要发生，即使后续 Gate 失败也必须记实际 stage/strategy 和 usage；“已配置”不等于“已触发”。tokens 只用 `total_tokens` 或完整 input+output；否则标 `token_usage_observed=false`、不估算或记 0。默认每模块 2～4 个场景、每场景首次 1 次，累计 calls ≤ 8、tokens ≤ 30000；notes 持续记“本次/模块累计/授权来源与剩余”。精确扩额只对已确认的场景/能力生效，不自动延伸到新切片；预计扩额时先请用户确认，单次响应意外越界后如实记账并停止。
5. **真实链路与 oracle**：优先经过 API → caller/task → Tool → MySQL/Milvus/LLM → Response/Trace。除 HTTP 和 rows，还要检查业务语义 oracle、安全负断言、runtime identity、实际 action/strategy、usage、Evidence/状态、termination 和失败层。需要测试数据时，plan 预先写明来源、事务/rollback 与前后恢复断言；恢复失败是独立的 `stop`。
6. **数据与动作禁区**：自动探针只用 canonical、公开或 diagnostic/dev 场景。优先只读；plan 声明的事务内临时 seed 必须 rollback 并核对恢复。禁止 held-out、sealed reserve、`all/full`、Reliability 重复、大规模 generation、新数据出站类别、持久数据写入/reset、索引重建、active release/default 切换或其他有状态扩权。
7. **首次执行、重验与证据时效**：不得为了通过而自动重跑、换 run ID/模型/backend、切 fallback 或放宽安全门；也不得为展示 repair/retry 人为制造坏 SQL/provider 故障，自然未触发就记 `inconclusive` + `not_exercised`。确需故障注入时另立 deterministic/controlled fault test，不冒充真实产品 Probe。系统性失败立即停止定位；具体修复落盘后只允许最小受影响场景重验 1 次，并保留前后 attempt。Probe 后若再修改它覆盖的核心行为、默认策略、调用次数、数据/安全合同或 runtime，旧结果只是历史 attempt，必须重新判断最小重验；纯注释/无行为文档修改不使证据失效。依赖不可用记 `inconclusive`，不能用 fake 通过覆盖。
8. **证据身份**：可以复用现有 Eval runner 的单 Scenario/dev 入口，但 run/notes/report 必须明确标记 `exploratory`、`baseline-ineligible`。除非现有 artifact schema 已支持，否则不得虚构 protocol 字段；开发探针不写入正式基线、不与正式 Eval 分母混算。
9. **收工职责**：`finish-module` 只审计 Probe 是否在计划切片时点发生。适用模块缺少开发期证据时，必须写 `development_probe_missing` 并返回开发流程；不能在收工阶段首次跑一次就抹掉流程缺口。按时尝试但真实依赖不可用的 `inconclusive` 可以作为真实边界保留。模块完成时说明探针结论；若下一结论需要稳定性/泛化、多场景分母或 default/release 切换证据，再提醒用户精确授权对应 Formal Smoke/Core/Reliability/held-out/基线候选。

## 真实 Eval 公共纪律

1. Formal Eval 默认不自动运行；上节额度内的 Live Dev Probe 是已授权例外，但它不是 Formal Eval，不能产生正式质量或基线结论。
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
