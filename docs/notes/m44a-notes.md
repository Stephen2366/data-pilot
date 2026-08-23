# M44A EnterpriseRAG-Bench Milvus 产品运行链路开发记录

> 模块 plan：`docs/notes/m44a-plan.md`
>
> 范围：把既有 EnterpriseRAG-Bench semantic candidate 接入普通 Uvicorn 与 external 产品 Eval；semantic 默认、lexical 仅显式 baseline、失败不回退。M44A 不占用 M44/B2，不改 M46 reserve，不重建索引。

## Implementation checklist

- [x] M44A-A：实现 API/Eval 共用的 closed-world Enterprise runtime resolver、semantic 默认和完整 snapshot identity。
- [x] M44A-B：以 FastAPI lifespan 一次持有/关闭 runtime，接入普通 `/api/query`，提供安全 readiness，并删除小语料隐式兜底。
- [x] M44A-C：external Eval 使用同一 resolver，补齐 semantic Trace/artifact/resume/compare 合同并保持旧 lexical artifact 可读。
- [x] M44A-D：补齐 Uvicorn、Milvus preflight、semantic/lexical Eval 运行说明和诊断入口。
- [x] 覆盖默认/显式选择、身份漂移、Milvus unavailable、零 fallback、生命周期/并发、API/Eval 同源和历史合同回归。
- [x] 在真实运行门前向用户请求 exact Scenario 或 `diagnostic_dev smoke` 的一次精确授权；未闭合 C6 前不得宣称 M44A 完成。
- [x] 完成注释审查、聚焦测试、受影响回归、全仓 deterministic pytest、compileall、`git diff --check`。
- [x] 调用 `finish-module`，固化验证、Handoff、Phase 4B changelog、`AI_CONTEXT` 和命中专项 state。

## 开工基线与已确认决策

- G44A-1：模块名为 M44A；M44–M48 仍对应 B2–B6，M46 sealed reserve 绑定不变。
- G44A-2：Enterprise 产品 API 与 external Eval 默认 semantic；lexical 只允许可信配置显式选择；semantic 失败关闭，禁止 lexical 或仓库小语料自动兜底。
- 复用现有 36,417-document / 139,214-unit semantic candidate；不自动启动 Docker、不建库、不改 embedding、不触碰 held-out/all。
- `finish-module` skill 已于开工时完整读取；开发完成后按其阶段 0～5 执行技术收工，不调用 `finish-docs` 或 `accept-module`。

## 开发过程记录

### 2026-08-24：启动

- 已完整读取 `AGENTS.md`、`docs/state/runbook.md`、`docs/state/AI_CONTEXT.md`、M44A plan 和 `finish-module` skill。
- 当前仍处于代码调查阶段；尚未运行真实 LLM、embedding、Milvus smoke 或 Eval，未修改任何默认配置/索引/artifact。

### 2026-08-24：首轮实现与聚焦验证

- 实现选择：应用缺少 Enterprise snapshot/API key 或 Milvus 不可用时继续提供 `/health` 和 SQL，但 `/health/rag` 返回安全 unavailable，RAG 请求由零 Knowledge/Composer 的 fail-closed adapter 结束。这样不会让一个外部依赖拖死整个数据分析 API，也不会恢复 lexical/小语料兜底；属于 plan C2 允许的 lifespan/readiness 实现细节。
- API 与 Eval 现在共用 `EnterpriseProductRuntimeConfig/load_enterprise_product_runtime`；semantic 为默认，lexical 只显式选择。runtime identity 包含 profile/corpus、semantic manifest、embedding、collection 和 unit-set；请求体没有选择入口。
- FastAPI 使用官方推荐 lifespan 一次 acquire/release 重型 runtime；SQLite 共享只读 connection 和 semantic provider/Milvus client 增加锁，避免跨请求 cursor/cache 串线。Milvus load 后读取 load state；不 release、reset 或重建 collection。
- external Eval 新增同源 semantic 默认和精确 `--scenario` 入口；单题仍受 partition 约束，不能从默认 dev 越到 held-out。新增 preflight 脚本只检查 snapshot/Milvus 身份，不调用 embedding 或 Composer。
- 首次 sandbox 聚焦 pytest 的断言阶段已显示部分通过/错误，但 teardown 因 Windows basetemp `WinError 5` 丢失完整详情，不形成代码结论。按 runbook 获批后沙箱外重跑同一聚焦范围：`33 passed, 1 warning in 2.04s`；warning 为既有 Starlette TestClient/httpx deprecation。
- 首轮 M35–M43 API 回归真实失败 4 项：M35/M38/M40 历史测试仍把普通 API 的隐式业务小语料当 fixture；M36 虽 monkeypatch 了 adapter 类，但新 factory seam 未显式注入，导致 fake 调用数为 0。这不是恢复产品 fallback 的理由。修正为这些历史 deterministic 合同测试显式注入 `rag_tool_factory`，产品默认仍 fail-closed；同组重跑 `14 passed, 1 warning in 57.16s`。
- artifact compare 兼容复核发现：旧 M41 runtime 没有 M44A semantic fields，若直接用交集判断 allowlist，会把 `semantic_identity/collection/...` 误报成“未知字段”。修正为比较器只在内存给预注册 additive 字段补 `None`，不改签旧 artifact；新增 old lexical→semantic candidate 显式 allowlist 测试。第二轮聚焦 `39 passed, 1 warning in 2.54s`。
- 两个 CLI `--help` 与 `compileall -q app engine eval scripts tests` exit 0；CLI 已显示 semantic/lexical、semantic snapshot 和 mutually-exclusive suite/scenario 参数。help 的唯一 warning 仍是既有 TestClient/httpx deprecation；未访问 Milvus/provider。
- 生命周期复核定位到一个真实冷启动坑：最初实现先用 `query_iterator` 核对 unit set、再 `load_collection`；collection 在 Milvus 重启后可能存在但未 load，这个顺序会让预检在 readiness 前失败。已改为 `load -> get_load_state -> unit-set query`，并把非合同型 client 异常收敛为不泄露连接细节的 `semantic_runtime_unavailable`。该修正不创建、reset、release 或重建 collection。
- 为上述冷启动顺序补了无 Docker 的 fake-client 合同测试：验证严格调用顺序、NotLoad 时禁止继续查询，以及成功/失败两条路径 client 都只关闭一次。
- 冷启动修正后的聚焦测试首次仍因 Windows sandbox 清理 basetemp 触发 `WinError 5`，不能采用该轮结果；获批在沙箱外重跑后为 `19 passed, 1 warning in 1.70s`，warning 仍为既有 TestClient/httpx deprecation。
- preflight 对 resolver 的稳定合同错误原样输出 `reason_code`；对 profile verifier/Milvus SDK 的其他异常只输出统一 `enterprise_rag_runtime_unavailable` 与异常类型，避免绝对路径、URI 或 provider 正文泄漏。
- 增加真实临时 SQLite profile 的跨线程测试：同一 `check_same_thread=False` 只读 connection 由 lifespan-style runtime 共享，4 个 worker 完成 8 次 Knowledge Tool 检索，每次仍需独立形成一条 Evidence；这验证锁不是只在 fake client 上存在。
- external Eval 的 resolved-runtime 构造收口为一个纯投影函数，并在 resolver 单测中逐项对照 API/Trace 使用的 `safe_projection`：mode、semantic/manifest、embedding、collection、unit-set 都来自同一个 product identity，不允许 CLI 再猜一遍。
- 加入真实 SQLite 并发和 API/Eval 同源断言后的聚焦测试：`23 passed, 1 warning in 1.83s`；warning 仍为既有 TestClient/httpx deprecation。
- 受影响回归：M31–M34、M41、M44A 共 `177 passed, 1 warning in 5.47s`；M35–M43 Harness/API/Phase 4B 共 `96 passed, 1 warning in 110.74s`。两组 warning 均为既有 TestClient/httpx deprecation，没有新 failure。
- 只读基础设施检查：`docker ps` 显示 `milvus-standalone/minio/etcd` 均已运行约 51 分钟且 healthy。随后按 runbook 用当前 profile/semantic identity 执行 preflight，11.37 秒返回 `status=ready`：semantic adapter、manifest、`datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`、1024 维 query 模型和 unit-set identity 全部闭合；明确 `embedding_transport_called=false`、`composer_called=false`。这证明 Milvus snapshot 可加载，但尚不等于 C6 的真实 query embedding→hit→Evidence→Composer 链已闭合。
- 代码审查发现 runtime 不能只凭 collection 名和 unit-set 推断向量候选身份：同一 unit 主键集合也可能装着另一模型/recipe 的向量。已在 load 前强制核对 collection description 中的 semantic identity，并核对 semantic manifest 的 corpus/unit-recipe 与已验证 profile bundle 一致；漂移直接失败关闭，不尝试修复或重建。
- 新增 collection/profile 漂移门后的聚焦回归为 `28 passed, 1 warning in 2.11s`；按新门重跑真实只读 preflight 仍为 `status=ready`（10.48 秒），证明当前 candidate 的 description、profile、manifest、unit set 匹配，而不是测试门把合法索引挡住。

### 2026-08-24：全仓测试前 checkpoint

- 关键决策仍只有已确认的 semantic 默认、lexical 显式、零 fallback；没有引入临时 backend、索引重建、held-out/all、reserve 或 Phase 4B owner 变化。
- 改动范围已闭合为：统一 resolver/identity，FastAPI lifespan/readiness，Milvus 冷启动与强身份门，共享只读 SQLite/Milvus 并发边界，external Eval 同源与 artifact additive fields，preflight/runbook，以及对应测试；未扩到 semantic 召回优化。
- 已完成证据：最新聚焦 28 passed；RAG/Eval 受影响 177 passed；Harness/API/Phase 4B 受影响 96 passed；真实只读 preflight ready；先前 compileall/CLI help 通过。
- 已知风险：C6 尚未运行真实 query embedding→Milvus hit→SQLite Evidence→Qwen Composer；单题 smoke 也不能证明 semantic 质量优于历史 lexical。当前 Milvus 容器在线，但应用不会代管其启动。
- 待完成：最终 compile/diff check、后台全仓 deterministic pytest；检查结果后请求/执行用户精确授权的 C6；再调用 finish-module 更新 changelog、AI_CONTEXT 和命中专项 state。
- checkpoint 后 `compileall -q app engine eval scripts tests` 与 `git diff --check` 均 exit 0；diff 输出只有 Git 的 LF→CRLF 工作区提示。
- 全仓 deterministic pytest 已后台启动，PID `63880`。命令脚本：`.agent_work/temp/run_m44a_full_pytest.ps1`；日志：`.agent_work/temp/m44a-full-pytest.log`；退出码：`.agent_work/temp/m44a-full-pytest.exitcode`；完成标记：`.agent_work/temp/m44a-full-pytest.done`。当前状态：**运行中，待检查**，不得提前记录为通过。
- 用户续接后已核对完成标记、退出码和日志：exit code `0`，`517 passed, 1 warning in 609.32s (0:10:09)`。warning 为既有 Starlette TestClient/httpx deprecation，与 M44A 无关；后台全仓验证现可判定通过。
- C6 运行门：用户于 2026-08-24 明确选择方案 A，只授权 `diagnostic_dev` 的 `qst_0386` **恰好一次**；不扩大到 9 题 smoke，不触碰 held-out/all，不自动重跑，不允许 lexical fallback。

### 2026-08-24：C6 真实 semantic 产品链

- 使用从未存在的新 run ID `m44a-rag-external-qst0386-20260824-c6` 执行 `diagnostic_dev/qst_0386` 恰好一次；进程 exit 0，artifact `status=completed`、identity `0a5bc40a8514177d30fef6d49375d4edead1635fe178115a98d7b388d14c9647`，required Gate `12 passed / 0 failed / 0 not_observed`。
- 运行身份明确为 `semantic`、`knowledge-enterprise-milvus-semantic-v1`、`qwen3.7-text-embedding/1024`、semantic `9aec12...e20`、manifest `22c573...97b`、collection `datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`、unit set `17d5af...905f`；artifact、RAG diagnostics 与 Trace route runtime 三方一致且 Trace `missing=[]`。
- 唯一产品执行为 HTTP 200、`rag/completed/complete/passed`，Graph `route -> rag_tool -> controller`，RAG Tool/Knowledge/Gate/Composer/Validator 均一次。semantic adapter 产出 5 个 candidate，授权/去重/预算后 3 个 Evidence 进入 generation，gold 文档在 candidate/selected/generation_visible/cited 四阶段均命中；最终 1 个物理文档形成 2 条 claim citation，authority/ref/revision/anchor 可回查 SQLite profile。
- Qwen Composer 一次成功：prompt 1717、completion 337、total 2054 tokens，provider attempts=1、retry=0；AnswerFlow 约 7.70 秒，HTTP 约 7.71 秒。没有第二次运行、lexical fallback、held-out/all、索引写入或重建。
- required Gate 已通过，但 advisory `answer_facts_exact_lower_bound` 失败，triage 标记 `review_required=true`。这不推翻 C6 的链路合同，却意味着不能据此声称语义答案质量或 semantic 全集质量已证明；需在收工前对 qst_0386 的 question/gold/answer 做一次只读人工语义核对并如实记录。
- 人工语义核对：原题问 2026-02 us-west Dedicated autoscaler 卡在 minimum 的根因与 hotfix；gold 要求“PromQL label 从 `cluster_id` 改为 `cluster` 导致空 metrics/no scale-out；恢复 legacy label 并在无 series 时 fallback”。本次 answer 完整表达了这两项正向事实，没有落入 cooldown、quota、API Gateway/warm-pool 或 control-plane OOM 等禁答混淆项，因此人工 verdict 为 **pass**。advisory 失败属于 exact lower-bound 自动措辞/事实拆分未全部匹配，不改写自动 artifact，也不登记为全量 semantic 基线。

## 关键决策与取舍

- **G44A-1 模块编号**：选项是把修复并入原 M44/B2，或插入独立 M44A。建议并由用户确认插入 M44A，因为向量产品链是 B2 开工前置而不是 Decision Loop 能力；风险是文档形成双路线，因此 M44–M48 与 B2–B6 owner、M46 sealed reserve 首次解封绑定全部保持不变。
- **G44A-2 产品默认**：选项是 lexical 默认/semantic 显式，或 semantic 默认/失败自动 lexical，或 semantic 默认/失败关闭。建议并由用户确认第三项：API 与 external Eval 默认 semantic，lexical 仅可信配置显式 baseline；否则普通体验仍不是向量 RAG，或故障会被 fallback 掩盖。主要代价是 Docker/Milvus/provider 变成显式运行前置，且当前 dense-only 质量证据低于 lexical。
- **运行不可用边界**：实现采用“RAG fail-closed、整个 API 仍存活”。`/health` 与 SQL 不因 Milvus 故障退出，`/health/rag` 返回 503，RAG 请求零 Evidence/Composer；这属于 plan 已允许的 readiness 实现，不是新降级 backend。
- **C6 范围**：用户在 exact `qst_0386` 一次与 9 题 diagnostic smoke 之间选择前者；影响是以最低成本证明完整向量产品链，但不能形成 60/180 题质量结论。真实运行没有自动重试、扩题或切 lexical。

## 模块名称与改动文件清单

- 模块：M44A EnterpriseRAG-Bench Milvus 产品运行链路。起始 commit 明确为 `098bd6014fb6cad648eed17197e5a71b31f25c15`，收工时 HEAD 仍为该 commit，本模块尚无中途提交；清单由 `git status --short`、三种 `git diff --name-only` 和真实运行产物归并。
- 应用/配置：`app/api/query.py`、`app/core/config.py`、`app/main.py`。
- RAG/Harness/Trace：`engine/harness/adapters.py`、`engine/rag/answer_flow.py`、`engine/rag/enterprise_runtime.py`、`engine/rag/enterprise_semantic.py`、`engine/rag/enterprise_product_runtime.py`、`engine/trace/runtime.py`。
- Eval：`eval/rag_e2e_contracts.py`、`eval/rag_e2e_review.py`、`eval/rag_external_catalog.py`、`eval/run_rag_external_eval.py`。
- 运行入口与文档：`scripts/check_enterprise_rag_runtime.py`、`docs/state/runbook-rag.md`、`docs/notes/m44a-notes.md`；plan `docs/notes/m44a-plan.md` 已在起始 commit 内，不重复算实现 diff。
- 测试：`tests/test_config.py`、`tests/test_m34_enterprise_runtime.py`、`tests/test_m35_api_trace.py`、`tests/test_m36_api_trace.py`、`tests/test_m37_api_trace.py`、`tests/test_m38_hybrid_api_trace.py`、`tests/test_m40_trace_rehearsal.py`、`tests/test_m41_rag_external_suites.py`、`tests/test_m41_rag_review_history.py`、`tests/test_m44a_api_runtime.py`、`tests/test_m44a_enterprise_product_runtime.py`。
- C6 产物：`eval/reports/m41-rag-external-artifacts/m44a-rag-external-qst0386-20260824-c6.json`、`eval/reports/m44a-rag-external-qst0386-20260824-c6.md`、`eval/reports/m44a-rag-external-qst0386-20260824-c6-triage.json`；checkpoint/Trace 位于 `.agent_work/temp/m41-rag-external-checkpoints/`，按现有纪律不提交。
- finish-module/finish-docs 将新增或更新的技术档案与学习复盘在最终 Git 清单再次归并；未发现与本模块重叠的用户改动。

## 阶段 1 注释小结

- 完整审查 14 个生产代码/脚本文件和 11 个测试文件；生产文件共扫描 189 个 class/function/method 定义（多数为既有 M31–M43 代码），并逐项回读 M44A 新增/修改 seam。开发时已经补齐新文件、类、函数与关键分支注释，收工审查新增缺失注释 `0`，仍缺失 `0`。
- 新概念解释已覆盖：closed-world resolver、FastAPI lifespan、liveness/readiness 分离、fail-closed adapter、source/derived-index 分权、semantic snapshot identity、Milvus 冷启动 `load -> state -> query` 顺序、跨线程只读共享锁，以及 additive artifact compatibility。
- 关键“为什么”已写进代码：不能把 `None` runtime 恢复成小语料；为什么 Trace identity 不能反向选 backend；为什么 collection 名/unit-set 之外还要核对 description/profile；为什么不 release/reset/rebuild；为什么旧 artifact 只补预注册 optional fields。
- 复杂处/过时注释已随实现修正：普通 API 的 M41 deterministic fallback 描述退役；Milvus 启动顺序和 shared SQLite/Milvus 锁增加踩坑说明；历史 API 测试明确标为显式 fixture seam。没有为凑数量给自解释字段模型补冗余注释。

## 阶段 2 验证快照

- 聚焦 resolver/API/Eval/identity/cold-start：最终相关轮 `28 passed, 1 warning in 2.11s`；此前各轮 33/39/19/23 passed 用于定位兼容、生命周期和并发问题。Windows sandbox 的两次 `WinError 5` 只发生在 pytest basetemp 清理，均在获批沙箱外用新 basetemp 重跑取得明确 exit 0；失败轮不计作通过。
- RAG/Eval 受影响回归：PowerShell 按文件名选择 M31–M34、M41、M44A，`177 passed, 1 warning in 5.47s`。
- Harness/API/Phase 4B 回归：按文件名选择 M35–M43，`96 passed, 1 warning in 110.74s`；历史测试已显式注入 deterministic RAG fixture，产品默认无 fallback。
- 全仓 deterministic pytest：后台 PID 63880，完成标记和 exit code 已核对，`517 passed, 1 warning in 609.32s (0:10:09)`。
- 静态/格式：`python -m compileall -q app engine eval scripts tests` exit 0；两个 CLI `--help` exit 0；`git diff --check` exit 0，只有 LF→CRLF 工作区提示。
- 真实只读 preflight：当前 Milvus 三容器 healthy；两次 preflight 均 `status=ready`（最终 10.48 秒），完整核对 profile/manifest/collection/load/unit-set，明确 embedding/Composer transport 未调用。
- 用户授权的真实 C6：`qst_0386` 恰好一次，命令 exit 0，completed artifact `0a5bc40...c9647`，required `12/0/0`，semantic 5→3→3→1 漏斗，Qwen attempts=1/retry=0/2054 tokens，人工语义 pass；未运行第二题、第二次 replicate 或 lexical。
- completed artifact 独立只读校验：`validate_completed_artifact` exit 0，重算 identity/Gate 仍为 `0a5bc40...c9647` 与 `passed 12/0/0`。
- 所有 pytest warning 都是既有 `StarletteDeprecationWarning: TestClient/httpx`，不影响 M44A 合同；真实运行同样只出现该 warning。没有 ORM/Alembic/seed/database schema 修改，因此不运行 `alembic check/current` 或 reset。

## 参考资料

- WrenAI `index_backend.py`：借鉴 source/derived index 分离；适配为 SQLite profile 权威、Milvus 只做候选；不照搬自动 reset/rebuild/watch。
- GustoBot `multi_tool.py` / `vector_store.py`：借鉴稳定 workflow seam 和向量主键候选；适配到既有 Knowledge Tool/Evidence/citation；不照搬 fallback、自动级联或从 Milvus payload 直接拼引用。
- DB-GPT `knowledge.py`：借鉴 retrieval chunks 与 structured references 分层；不照搬字符串 source/异常结果。
- DataAgent `AgentVectorStoreServiceImpl.java`：用其 best-effort replace 反例提醒发布风险；M44A 明确只读，不把“先加后删”当原子发布。
- FastAPI 官方 lifespan 文档：确认请求前 acquire、shutdown release 和 TestClient context 生命周期；不照搬其资源业务语义。
- Milvus 官方 load/get-load-state/search 文档：确认 collection 必须 load 才能 query/search，并用 load state 做 readiness；DataPilot 额外保留 manifest hash、description、unit-set 和 profile/corpus 强身份门。

## Handoff

### 已完成且可依赖

- 普通 Uvicorn 与 external Eval 共用一个 Enterprise resolver；默认 semantic，显式 lexical 才能复现 baseline，任何 semantic 故障都不 fallback。
- FastAPI lifespan 每进程一次加载/关闭 139k metadata、只读 SQLite 和 Milvus client；`/health/rag` 可直接证明安全 runtime identity，未就绪时 RAG 零 Evidence/Composer、SQL/liveness 仍可用。
- Milvus runtime 已验证 collection existence/description、load state、visible unit-set，以及 profile/corpus/unit-recipe、embedding model/dimensions；Trace/artifact/Eval resolved identity 三方同源。
- C6 的 qst_0386 单题真实链已通过：semantic candidate 5、selected/visible 3、gold cited，required Gate 12/12，人工语义 pass，Qwen 一次 2054 tokens；这足以证明当前向量产品链可工作。

### 未完成与风险

- 只证明一条 diagnostic_dev 产品链，不能外推 semantic 60/180 题质量、可靠性或相对 lexical 的净收益；历史 M34 @20 仍提示 dense-only candidate 质量较弱。
- semantic query/search 首版用单锁串行，共享安全优先于吞吐；139k metadata 和 unit-set 启动校验有约 10 秒级成本。应用不启动/维护 Docker，Milvus 离线会明确 unavailable。
- 自动 advisory 对 qst_0386 的 exact answer facts 未全匹配，虽人工 verdict pass，仍应保留自动与人工双视图，不改签 artifact。

### 必须延续的边界与决策门

- M44A 不占 B milestone；下一能力模块仍是 M44/B2。M46 reserve 继续 sealed，M44A 未读取或改签。
- semantic 默认、lexical 仅显式、无 fallback 是用户确认的长期选择。只有用户明确改变产品默认，或新的版本化 candidate/A-B 证据要求重开，才能重新决策；不能因开发便利或单题波动切回。
- 新索引、embedding、fusion、rerank 或重建必须形成独立 candidate identity、明确成本和显式授权，不能原位覆盖现有 semantic snapshot。

### 下一模块入口与必读指针

- M44/B2 plan 应从 `docs/phase4b-roadmap.md` 的 Decision Loop owner、`docs/notes/m44a-notes.md` 本 Handoff、`engine/rag/enterprise_product_runtime.py` 的稳定 Tool seam、`tests/test_m44a_*` 的 fail-closed/identity 合同开始。
- 若 M45/B3 后续开展 failure campaign，先读本次 C6 artifact 和 `eval-baselines.md` 的历史 lexical 失败层；把真实 failure cluster 作为 action 输入，不把 qst_0386 单题 pass 当全局质量结论。

## finish-module 技术档案交付清单

- [x] 最终文件范围已由 Git 三视图复核，并排除无关用户改动。
- [x] notes 已包含实现清单、关键决策、踩坑、验证证据、参考资料和 Handoff。
- [x] Phase 4B changelog 已写入 M44A 结构化模块档案，并对被修正的旧默认判断加注。
- [x] `AI_CONTEXT.md` 已切到 M44A 当前事实、下一模块和活跃风险。
- [x] 命中的 RAG、Eval、Milvus/embedding、runbook 专项状态已同步；数据库状态确认无需更新。
- [x] 所有新增路径/链接、身份、数字和默认行为已交叉核对。
- [x] 修改后的技术档案已完整回读到 EOF，`git diff --check` 通过。
- [x] finish-module 最终状态与 Implementation checklist 已全部闭合。

## State impact

- [x] `docs/state/change-history/phase4b.md`：新增 M44A 模块档案并修正“external 默认 lexical / semantic 未激活”的持续性解释。
- [x] `docs/state/AI_CONTEXT.md`：更新当前模块、产品默认、最新验证、路线和活跃坑。
- [x] `docs/state/rag-current-state.md`：区分 22 条业务 lexical 与 Enterprise 产品 semantic 默认，记录 runtime、C6 和边界。
- [x] `docs/state/eval-baselines.md`：登记 C6 为当前技术 smoke 证据而非正式长期基线，保留历史 lexical 基线解释。
- [x] `docs/state/schema-retrieval-milvus-embedding.md`：明确 Schema Retrieval 与 Enterprise RAG 是两条独立向量链。
- [x] `docs/state/runbook.md` / `runbook-rag.md`：补齐 liveness/readiness、启动前置与默认选择的一致入口。
- [x] `docs/state/database-current-state.md`：无 ORM、Alembic、seed、数据库 schema 或指标口径变化，无需更新。

finish-module 结论：技术实现、真实 C6、验证、注释、状态档案与 Handoff 全部闭合。最终 `git diff --check` exit 0；仅有 Git 的 LF→CRLF 工作区提示。M44A 可以进入 finish-docs，但尚未执行人工 `accept-module`。

## finish-docs 执行清单

- [x] 已确认 finish-module 技术档案交付清单全部为 `[x]`。
- [x] dev-log 只基于最终 notes、技术档案和真实证据写作，没有补造实现或结论。
- [x] 章节包含大白话故事、实现拆解、新概念、代码阅读路线、设计要点、面试亮点与追问。
- [x] 章节明确 semantic 默认的效果、Docker/Milvus 前置、fail-closed 与单题 C6 的证据边界。
- [x] 可复制命令与本地体验步骤安全且指向 `runbook-rag.md` 的当前配置。
- [x] 新章节已完整回读，数字、路径、identity 和下一模块与技术档案一致。
- [x] finish-docs 开始后只修改 `docs/dev-log.md` 与本 notes；`git diff --check` 通过。

finish-docs 结论：M44A 学习复盘已追加到 `docs/dev-log.md`，从 finish-docs 开始到闭合只修改该文件与本 notes。章节已完整回读到 EOF，明确区分“产品默认 semantic”和“尚未证明质量优于 lexical”。

## 2026-08-24：收工后 semantic smoke 真实运行

- 用户明确授权再执行一次 RAG smoke。按 runbook 唯一映射冻结为 external `diagnostic_dev/smoke`：9 个冻结 dev Scenario、各 1 次 execution；当前 semantic 产品默认，不切 lexical、不触碰 held-out/all、不自动重跑。
- 运行前置已核对：项目 Python、dataset/profile/semantic 路径存在，DashScope key 已配置；沙箱外只读 `docker ps` 显示 Milvus standalone/minio/etcd 均 healthy。
- 只读 preflight `status=ready`：profile `e8783fe...fa2`、semantic `9aec12...e20`、manifest `22c573...97b`、collection `datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`、unit-set `17d5af...905f` 一致，且 embedding/Composer transport 均未调用。
- 唯一 run ID：`m44a-rag-external-semantic-smoke-20260824-023039`；启动前确认 artifact、report 和 checkpoint 均不存在。运行脚本 `.agent_work/temp/run_m44a_semantic_smoke_20260824_023039.ps1`；日志 `.agent_work/temp/m44a-rag-external-semantic-smoke-20260824-023039.log`；退出码 `.agent_work/temp/m44a-rag-external-semantic-smoke-20260824-023039.exitcode`；完成标记 `.agent_work/temp/m44a-rag-external-semantic-smoke-20260824-023039.done`。
- 后台任务已启动，PID `58364`。命令、范围和运行身份与上方 checkpoint 一致；日志、退出码、完成标记路径均已固化。
- 完成标记 `2026-08-24T02:33:20.8411384+08:00`、exit code `0`；manifest/artifact 均为 completed，没有 resume 或第二次运行。artifact identity `4bfff9dffdf57ca667bbfa1f585eb287b37ff5de3d6dd9d32c49628c00d5346d`。
- 自动结果：9/9 均 HTTP 200、`rag/completed/complete/passed`，每题 RAG Tool/Composer 各一次，provider `9/9` 成功、retry0、总 usage `19033` tokens。required Gate `failed`：`92 passed / 16 failed / 0 not_observed`；advisory `18/9/0`。primary triage 为 `5 passed / 4 retrieval`，4 个 retrieval 失败是 qst_0016/0047/0181/0420；全体都是 `5 candidate → 3 selected → 3 generation-visible`，gold 四层命中题数均为 `5/9`。
- 来源哈希 review bundle 已验证 artifact 1 + checkpoints 9。逐题人工语义 verdict 为 `2 pass / 7 fail`：qst_0019、qst_0386 pass；qst_0016/0047/0181/0420 因错材料或漏 gold 答错，qst_0461 遗漏 14 天/周五 16:00 规则并加入无关安排，qst_0431 虽命中两份 gold 但遗漏 Hosted/Dedicated 完整步骤，qst_0318 把 `02:18:22Z` 答成 `02:21Z`。
- 与历史 post-fix lexical smoke `m41-rag-external-smoke-20260823-154101` 的 candidate compare 合同通过；仅放行 10 个预注册 retrieval/semantic runtime 字段。自动配对 `1 win / 5 tie / 3 loss`，required 从 `96/12/0` 变为 `92/16/0`；semantic 在 qst_0431 从 selection→passed，qst_0047 从 selection→retrieval，qst_0181/0420 从 citation→retrieval。usage 从 `20288` 降至 `19033`（-1255），p50 AnswerFlow `7851.565→7877.805ms`。
- 人工 verdict 相对 lexical `3 pass / 6 fail` 为 semantic `2 pass / 7 fail`；共同通过 qst_0019/0386，共同失败 6 题，qst_0461 从 lexical pass 变为 semantic fail，没有人工净新增 pass。由于每个 backend 仅单次 generation、compare 是整体 runtime candidate 且没有 Reliability，不能把该差异归因给 Milvus/embedding 或宣布 semantic 稳定更差；但它明确推翻“单题 C6 足以代表当前 smoke 质量”的任何乐观外推。
- completed artifact 已用 `validate_completed_artifact` 独立只读复核，重算 identity `4bfff9d...5346d` 与 Gate `failed 92/16/0` 一致；`git diff --check` exit 0。
- 证据：artifact/report/triage 位于 `eval/reports/m41-rag-external-artifacts/m44a-rag-external-semantic-smoke-20260824-023039.json` 与同名 report/triage；review、verified、verdicts、reviewed 和 `m44a-rag-external-semantic-smoke-vs-lexical-20260824-compare.json` 均已提交到 `eval/reports/`。checkpoint/Trace 仍在 `.agent_work/temp/`。
- 当前结论：本次授权已经恰好一次闭合，不自动重跑、不登记正式长期基线、不触碰 held-out/all。semantic 继续作为已确认产品默认，但当前 smoke 没有提供质量胜出证据；后续若要判断 backend 稳定差异，必须另立 Reliability/候选决策计划和用户授权。

## 2026-08-24：accept-module 门禁 checkpoint

- accept-module 已执行检查 1-6、8、9（结论见最终验收报告）。
- 检查 7 裁剪验证：用户明确豁免本次运行（"其他没问题就不测试了，直接改为已验收"），未执行新 pytest。可信依据为 notes/phase4b.md 已记录、且完成标记与 exit code 已核对过的 2026-08-24 全仓 `517 passed, 1 warning`（后台 PID 63880）与各组裁剪回归快照；本次验收报告将检查 7 标为"用户豁免"，不冒充本次执行。
- 验收结论：无 ❌，用户指示直接记"已验收通过"，AI_CONTEXT 当前活动模块已同步。
