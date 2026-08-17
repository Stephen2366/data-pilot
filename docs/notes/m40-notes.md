# M40 P7 跨路径 Trace 运行身份与阶段保证包 — 实施素材

> 范围以 [m40-plan.md](m40-plan.md) 为准：统一安全 Trace runtime identity、五路径 API/Trace rehearsal、P7 closed-world assurance manifest 与 capability matrix；不新增业务 Tool、检索策略、远程调用或默认切换。

## Implementation checklist

- [x] 复核 M35–M39 Harness / Trace / Eval seam 与 P7 参考源码，冻结 C1–C3 的输入和安全边界。
- [x] 实现 C1 Trace Runtime Identity Envelope，并为 SQL、RAG、Hybrid、lifecycle 的 unavailable 降级补合同测试。
- [x] 实现 C2 五路径 API/Trace rehearsal，验证 response/Trace 同源、Evidence/citation、预算/lifecycle 与非泄露。
- [x] 实现 C3 P7 assurance manifest，闭合 P1–P6 required family 与 M39 frozen `no_go`，拒绝历史/质量 artifact 注入。
- [x] 生成安全 JSON/Markdown assurance report 与 capability matrix；不宣称 Phase 4 已人工验收。
- [x] 运行聚焦、M31–M39 回归与完整 deterministic pytest；记录真实输出、warning 和失败处理。
- [x] 执行 `finish-module`：注释审查、notes 素材、state/changelog、回读与交付门。

## 开工快照与边界

- 用户已确认按 `AI_CONTEXT.md` 的 M39 验收状态继续，M40 进入 P7；M39 的严格 `no_go`、external lexical 默认和 P6 重开门不改变。
- 当前工作树已有 `docs/module-plan-template.md`、`docs/notes/m39-{plan,notes}.md`、`docs/state/AI_CONTEXT.md` 修改；这些在本模块开工前已存在，除非后续与 M40 同一事实必须协调，否则不归并或覆盖。
- 本模块仅运行本地 deterministic 测试/contract runner；不调用真实 LLM、remote embedding/Milvus、LangFuse Cloud 或 M34 external 运行。
- 过程记录：已读取 AGENTS、M40 plan、AI_CONTEXT；按必读规则继续核对 runbook、RAG/Eval state、CHANGELOG_INDEX 与 Phase 4 历史。`finish-module` skill 已读取，收工时将按其阶段门执行。

## 实施进展与待决冲突

- 已实现 C1 初版：`engine.trace.runtime` 从同一 `AgentTurnResult` 的安全投影构造版本化 runtime envelope；SQL 只读取 ledger `runtime_ref`，RAG 只读取已有 diagnostics，Hybrid 记录薄计划 / Synthesizer 与安全 branch 摘要。缺字段标为 `unavailable`，不会中断 API。
- 已实现 C3 初版：`eval.phase4_assurance` 以 exact family catalog 运行 P1–P5 deterministic contracts、只读验证 M39 `no_go`，并拒绝 family 漏项/顺序漂移/runtime identity 篡改；`scripts/run_m40_phase4_assurance.py` 可从已验证 C2 JSON 写 JSON/Markdown report。
- C2 真实 API rehearsal 已跑到澄清恢复。SQL、RAG、Hybrid、恢复和未受信 caller 拒绝均得到完整 runtime envelope；RAG citation 与 Trace Evidence 采用公开的 authority/revision/anchor 坐标对账，避免要求 API 暴露 private Evidence ID。
- **待用户决策：Trace 与 raw clarification value 的边界冲突。** 现有 `TraceRecord` 长期保存用户可见 `answer`；resume 后正常 RAG answer 会自然复述补充的 subject（本轮为“退款政策”）。因此“Trace 不出现任何 raw thread/follow-up 值”若按字面执行，必须改 Trace 的既有 answer 保存合同；若保持当前合同，只能保证不保存 `thread_id`、`clarification_answers` / `follow_up_fields` 结构及其独立参数副本。已验证 `thread_id` 本身只以 `thread_safe_ref` hash 出现。暂停 C2 该断言，等待确认，未宣称验证通过。
- **已确认（用户选择 A）**：保留既有 Trace 的用户可见 `answer` 合同；C2 禁止 raw `thread_id`、`clarification_answers` / `follow_up_fields` 结构及独立参数副本，不把 answer 自然复述业务主题误判为泄露。已同步收紧后的合同文字到 M40 plan，继续执行。

## 全仓验证前 checkpoint（2026-08-17）

- **完成的改动范围**：新增 `engine/trace/runtime.py`；Trace schema/API projector 增加 `runtime_identity`；Hybrid result 保存受控 `synthesizer_identity`；新增 P7 rehearsal / assurance model、validator、Markdown renderer 与本地 `scripts/run_m40_phase4_assurance.py`；新增 M40 专项测试，并给既有 SQL/RAG/Hybrid API Trace 回归补 runtime identity 断言。
- **关键设计**：C2 每路径写入 `execution_identity`，它是同次 response/Trace 的安全投影哈希，绑定 trace id、四轴、runtime、EvidenceRef / branch / lifecycle 与 Graph 次数，但 artifact 不保存正文、rows、raw thread 参数或答案内容。C3 exact catalog 只允许 P1、P2 retrieval/answer、P3、P4 turn/follow-up、P5、M39 P6 `no_go`、P7 rehearsal 九个 family；M27 历史与 M34 质量数没有可填槽位。
- **已完成验证**：M40 聚焦 `6 passed, 1 warning in 12.72s`；M31–M39 受影响确定性回归 `208 passed, 1 warning in 51.21s`；`compileall` 与 `git diff --check` 通过。唯一 warning 为既有 FastAPI TestClient / httpx 弃用提示。
- **已知风险**：未发现功能失败。P7 technical assurance 不代表用户人工验收、生产认证、真实外部 provider 质量或 P6 Subgraph 完成；M39 `no_go` 保持不变。
- **待完成**：启动/检查后台全仓 pytest；通过后执行 `finish-module` 的注释审计、state/changelog/AI_CONTEXT 收工和回读门。

## 后台全仓 pytest（已完成并检查）

- 命令：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m40-full`
- PID：`40124`
- stdout：`.agent_work/temp/m40-full-pytest.out`
- stderr：`.agent_work/temp/m40-full-pytest.err`
- 退出码：`.agent_work/temp/m40-full-pytest.exit`，值为 `0`。
- 完成标记：`.agent_work/temp/m40-full-pytest.done` 已存在；stdout 结论为 `447 passed, 3 skipped, 1 warning in 503.36s`，详见“阶段 2：验证快照”。

## finish-module 技术档案交付清单

- [x] 模块最终文件范围已与 Git 状态、起始 commit 和 notes 核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] 已读取 `CHANGELOG_INDEX.md`，并按索引写入完整模块记录。
- [x] `AI_CONTEXT.md` 已更新并清理失效、重复或仅具历史价值的内容。
- [x] 所有命中的专项 state 均已完整检查，并已更新或记录“无需修改”的理由。
- [x] 新结论与历史条目、代码、测试、Eval、默认配置和各 state 之间不存在冲突或重复权威定义。
- [x] changelog 新章节、`AI_CONTEXT.md` 和所有修改过的专项 state 已完整回读。
- [x] `git diff --check` 及本轮涉及的文档链接检查已通过，结果已写回 notes。

## State impact（已回读确认）

- **已更新**：`AI_CONTEXT.md`（当前模块、P7 technical Gate、Trace identity 与路线边界）；`runbook.md`（API JSONL Trace runtime envelope）；`eval-baselines.md`（P7 deterministic Gate 不与质量基线混算）；`change-history/phase4.md`（完整模块档案与方案 A）。
- **已检查、无需修改**：`rag-current-state.md`（M40 不改 release、external lexical 默认、M39 no-go 或 RAG 质量结论）。
- **未命中**：`database-current-state.md`、`schema-retrieval-milvus-embedding.md`。

## 模块名称与最终改动文件清单

- **模块**：M40 P7 跨路径 Trace 运行身份与阶段保证包。
- **起始依据**：最近提交为 `64e7c74 M39 Subgraph审计`；M40 开工时工作树已含用户的 `docs/module-plan-template.md`、`docs/notes/m39-plan.md`、`docs/notes/m39-notes.md` 与 `docs/state/AI_CONTEXT.md` 改动。M40 不归并前述前三项，仅在 AI_CONTEXT 的同一当前状态区追加自己的事实。
- **M40 代码与测试**：`app/api/query.py`、`engine/harness/contracts.py`、`engine/harness/graph.py`、`engine/trace/recorder.py`、`engine/trace/runtime.py`、`eval/phase4_assurance.py`、`scripts/run_m40_phase4_assurance.py`、`tests/test_m35_api_trace.py`、`tests/test_m38_hybrid_api_trace.py`、`tests/test_m40_phase4_assurance.py`、`tests/test_m40_trace_rehearsal.py`。
- **M40 文档与技术档案**：`docs/notes/m40-plan.md`、本文、`docs/state/AI_CONTEXT.md`、`docs/state/runbook.md`、`docs/state/eval-baselines.md`、`docs/state/change-history/phase4.md`；`docs/dev-log.md` 留给后续 `finish-docs`。

## 关键决策与取舍（已确认）

- **C1 安全 runtime envelope**：不新建第二套运行事实，也不读取 private Evidence；SQL 从 safe ledger 读取 `runtime_ref`，RAG 从既有 safe diagnostics 读取 AnswerFlow/release/corpus/adapter/recipe/Composer/policy identity，Hybrid 增加 thin plan、Synthesizer 和安全 branch 摘要。缺 identity 标为 `unavailable` 而非阻断 API；P7 canonical rehearsal 才把它判为失败，保持 Trace 的旁路性质。
- **C2 真实一次执行**：五条 HTTP 路径各执行一次后，使用同次 response/Trace 的四轴、runtime、EvidenceRef/branch/lifecycle 与 Graph count 计算不可逆 `execution_identity`；artifact 不保存正文、rows、raw thread 参数或 answer 内容。没有把单独重新运行的 Trace 伪装为演练证据。
- **Trace 与澄清参数冲突（用户选择 A）**：resume 的用户可见 answer 会自然复述 subject。方案 A 保留长期 Trace 的既有 answer 合同，禁止 raw `thread_id` 与 `clarification_answers` / `follow_up_fields` 结构或独立参数副本；方案 B 需改写已有 answer Trace 合同。B 会扩大兼容/可观测性影响，建议 A；用户确认 A，已冻结到 plan/C2 测试。
- **C3 closed-world，不凑总分**：P7 manifest 只允许 P1 security/release、P2 retrieval/answer、P3 Harness、P4 turn/follow-up、P5 Hybrid、P6 verified no-go、P7 rehearsal 九个 family。M27 历史 artifact、M34 retrieval/Answer 数字与 advisory 指标没有可填槽位；P6 仍是路线决策证据，不改写为 RAG 质量通过。

## 阶段 1：注释审查

- **检查范围**：完整检查 7 个本模块生产代码文件和 4 个本模块测试文件；既有文件只审查 M40 新增/修改的 Trace、Hybrid 与断言区域，未改动无关用户代码。
- **补写与深化**：补写 1 处缺失注释（`eval.phase4_assurance._hash()` 的稳定 identity 序列化规则）；`runtime.py`、assurance dataclass/validator、CLI、Hybrid Synthesizer identity、Trace schema 字段和 C2 execution fingerprint 均已有中文职责、边界或安全原因说明。
- **结果**：没有剩余的非豁免新增类/函数或关键安全分支缺注释；未为自解释的局部测试断言堆砌注释。

## 阶段 2：验证快照

- **M40 聚焦**：`python -m pytest tests/test_m40_phase4_assurance.py tests/test_m40_trace_rehearsal.py -q -rA --basetemp=.agent_work/temp/pytest-m40-finish` → `7 passed, 1 warning in 13.04s`。覆盖 SQL safe ledger identity、identity 缺失降级、C2 漏路径/runtime 反例、five-path API rehearsal、M39 no-go、exact family 和 CLI JSON/Markdown 输出。
- **受影响回归**：`python -m pytest <tests/test_m31* 至 test_m39*> -q -rA --basetemp=.agent_work/temp/pytest-m40-m31-m39` → `208 passed, 1 warning in 51.21s`。覆盖 Evidence、RAG、Harness、thread、Hybrid 与 M39 no-go 未回归。
- **全仓 deterministic pytest**：后台命令 `python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m40-full`，PID `40124`；已检查 `.agent_work/temp/m40-full-pytest.{done,exit,out,err}`，退出码 `0`，`447 passed, 3 skipped, 1 warning in 503.36s`。3 skip 是既有 Milvus/远端 embedding 条件项；唯一 warning 是 FastAPI TestClient/httpx 弃用提示，均不阻塞。之后新增的 CLI 测试已由上述 M40 聚焦命令覆盖，未改变运行代码行为。
- **静态/交付检查**：`python -m compileall -q engine/trace eval scripts/run_m40_phase4_assurance.py`、`git diff --check` 均 exit 0；当前 diff 只有 Git 的 CRLF 提示，无 whitespace error。

## 参考资料

- **定点复核**：`agentic-rag-for-dummies` 的 `AgentState / append_unique / set_union` 与 evaluation notebook；DB-GPT 的 `RetrieverSimilarityMetric / RetrieverMRRMetric / RetrieverHitRateMetric / RetrieverEvaluator`。
- **借鉴**：保存真实执行事实、让后续评估读取保存产物；retrieval 与 answer/contract 分层。
- **不照搬**：完整 context/history、MessagesState、开放循环/强制搜索/checkpointer、RAGAS/LLM Judge/平均分、DB-GPT DAG/embedding scorer；DataPilot 继续以已有 Evidence、四轴、ACL/outbound、closed-world 和 P6 no-go 为边界。

## Handoff

- **已完成且可依赖**：`TraceRecord.runtime_identity` 的 `phase4-trace-runtime-v1`，SQL/RAG/Hybrid/lifecycle 的安全 projection 和 unavailable 降级；five-path C2 rehearsal、P7 exact-nine-family validator、JSON/Markdown CLI；M39 P6 frozen `no_go` 被只读验证而没有被翻转。
- **未完成与风险**：technical Gate 不证明生产认证、真实 provider/外部语料质量、开放 Router、长期会话或 Phase 4 人工验收；既有 Trace answer 仍可能自然复述业务主题，这是用户确认 A 后保留的兼容边界，不是结构化 thread 参数泄露。
- **必须延续的边界与决策门**：external lexical 默认、M39 strict no-go、LangFuse Cloud 关闭、任何新的 Knowledge/RAG 出站默认拒绝均不变。只有未污染 dev 证明 Observation 驱动允许动作新增 Evidence，且 held-out 协议和可比额外预算固定后，才可另立 P6 实验；不得借 M40 的 P7 Gate 宣称 Subgraph 完成。
- **下一模块入口与必读指针**：若后续另开能力模块，先读 `docs/phase4-roadmap.md`、AI_CONTEXT、M40 plan/notes、`eval/phase4_assurance.py`、`engine/trace/runtime.py`、`tests/test_m40_trace_rehearsal.py` 与 M39 no-go report，再依据真实需求立计划。

## finish-docs 执行清单

- [x] “简述”和“先用大白话”准确说明了五路径可追溯、闭合保证包与不等同人工验收的结果。
- [x] “这次做了什么”恰好保留 3 个一级编号步骤：runtime identity、五路径 rehearsal、closed-world assurance。
- [x] 每个一级步骤都写明了实施方式、方案 A 的边界或 closed-world 取舍，以及对应验证结果。
- [x] 新概念用安全收据、包装箱等通俗比喻解释，并落到 `TraceRecord`、C2 artifact 和 manifest 的真实职责。
- [x] 已逐项对照 `runtime.py`、`phase4_assurance.py`、API / Graph 改动与测试，代码链路无虚构。
- [x] 关键设计点明确说明了不保存 raw 参数、unavailable 不阻断 API、P7 不替代 P6/人工验收等边界。
- [x] 已包含一段可直接用于面试复述的完整模块叙事。
- [x] 3 个面试追问均基于方案 A、跨路径闭环和 no-go 三项真实取舍，回答含具体合同与验证证据。
- [x] 验证章节仅使用本 notes 已记录的聚焦、回归、全仓、compileall 与 diff 检查结果。
- [x] 复制命令均使用项目既有 Python 与临时 basetemp 路径，可本地安全重复运行。
- [x] 已完整回读 M40 dev-log；每个主要章节均保留至少一个加粗重点标记。

## finish-docs 交付结论

- 已完整回读 M40 的 dev-log 和本清单；内容、命令与验证事实均可回溯到本 notes。
- `finish-docs` 阶段只修改 `docs/dev-log.md` 与本文，未改动 AI_CONTEXT、CHANGELOG_INDEX 或技术历史。
- 收尾 `git diff --check` 通过后，可进入用户人工检查和 `accept-module` 验收门；P7 technical Gate 不等同 Phase 4 或 P6 的完成。
