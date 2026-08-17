# M36 结构化澄清恢复与轻量 Thread Checkpoint 实施素材

> 对应计划：[m36-plan.md](m36-plan.md)

## Implementation checklist

- [x] 复核工作树、LangGraph/Pydantic/FastAPI 实际版本、M35 Harness/API/Trace/Eval seam 与 P4 参考源码。
- [x] 冻结并实现 clarification/thread lifecycle reason、四轴和安全公开投影。
- [x] 实现进程内 pending checkpoint：owner、TTL、schema/version、原子 claim、resolve、clear、冲突与 fake clock。
- [x] 实现 closed-world clarification spec 和最小 Context Builder，覆盖缺主体与缺时间/维度。
- [x] 将 Harness 加深为 turn-level seam，支持 initial pending、一次 resume 和前置失败闭合结果。
- [x] 增量接入 `/api/query`、显式清理、AgentResponse 与 JSONL multi-turn Trace。
- [x] 建立 M36 sequence Eval family 和 owner/lifecycle/concurrency/context/budget/API 回归。
- [x] 按计划顺序运行聚焦测试、M35/M31–M33 回归、全仓 deterministic pytest 与静态检查。
- [x] 调用 `finish-module` 完成四遍注释审计、素材固化、Phase 4 changelog 与 `AI_CONTEXT` 更新。

## 开工快照与已确认边界

- 2026-08-16：用户确认 G-M36-1 方案 A。M36 使用应用持有的轻量进程内 checkpoint；不启用 LangGraph `InMemorySaver` / interrupt/resume，不预建持久 storage port。
- 本模块只实现 pre-Tool clarification 的一次有界恢复；不做 Evidence 跨轮复用、Tool retry、跨 Tool 补证据、Hybrid、远程 Router/query rewrite、长历史或持久 checkpoint。
- M35 的 Router、Text2SQL/RAG 深 Tool、四轴和唯一结果投影继续作为基础；无 thread 的旧请求必须保持兼容。
- 运行和验证遵守 `docs/state/runbook.md`；不自动运行真实 LLM Eval、M34 external Answer Eval、Milvus/embedding 或 LangFuse Cloud。

## 开发记录

- 2026-08-16：已完整读取 `AGENTS.md`、`m36-plan.md`、`AI_CONTEXT.md` 和 `finish-module` skill；运行命令前已读取 `runbook.md`。组合读取输出存在工具截断，但上述文件在本轮/紧邻规划轮已分别完整读取，后续按具体改动继续定点复核。
- 2026-08-16：开工检查时工作树只有未跟踪的 `m36-plan.md` 与本文件，没有其他用户改动。项目环境为 LangGraph `1.1.2`、Pydantic `2.12.5`、FastAPI `0.135.1`。
- 2026-08-16：按 P4 定点重看 ARAG `graph.py / graph_state.py / edges.py / nodes.py`。借鉴 pending query 与 clarification 分离、显式预算/停止；按方案 A 明确不采用其全局 `InMemorySaver`、`MessagesState`、LLM query rewrite、history summary、强制检索和开放 Tool loop。
- 2026-08-16：首个实现把 checkpoint 做成不可变 pending/claimed/resolved/cleared 状态机，并用单个 `RLock` 在慢 Tool 之前原子 claim。非法 clarification answers 在 claim 前拒绝、不会消费 version；Graph 开始后无论成功或失败都不退回 pending，防止重复 Tool Call。
- 2026-08-16：最小 Context Builder 只支持 plan 冻结的 `subject` 与 `analytics_scope` 两个模板；用户值不进入 thread Trace，只记录不可逆 `context_ref`。没有建立通用 storage port、自由文本 rewrite 或第二次 clarification。
- 2026-08-16：安全审查发现 M31 `audit_ref` 不含 tenant，不能直接当 checkpoint owner。已把默认 owner identity 改为 `audit_ref + tenant_id` 的内部哈希；认证适配器若显式提供 `thread_owner_ref` 则以它为作用域，并增加同 caller 跨 tenant 拒绝回归。

## 阶段 2 验证快照

- 2026-08-16：`compileall -q app engine eval tests` 通过。
- 2026-08-16：首轮 core + M35 兼容聚焦测试 `17 passed in 0.81s`。覆盖 subject/analytics Context、owner/TTL/clear/restart/state version、并发单 claim、一次 SQL/RAG resume、budget stop、Tool unavailable 不重试，以及 M35 Harness/Eval 回归。
- 2026-08-16：M35 API/Trace 兼容回归 `3 passed in 38.28s`；仅出现项目既有 FastAPI/Starlette `TestClient` 的 httpx deprecation warning。
- 2026-08-16：M36 API/Trace 与 turn 聚焦 `8 passed in 1.50s`；sequence Eval `3 passed in 0.76s`。Eval 覆盖 8 组 sequence，并用反例拒绝漏 turn、重复 execution 和缺 assertion。
- 2026-08-16：M36/M35/config 合并聚焦 `31 passed in 35.46s`；M31–M33 caller/ACL/outbound/Evidence/citation 安全回归 `111 passed in 2.65s`。
- 2026-08-16：后台全仓 deterministic pytest 退出码 `0`，`416 passed, 1 warning in 594.12s (0:09:54)`。warning 仍是既有 Starlette TestClient/httpx deprecation，不影响 M36；未出现 skip 或失败。日志与完成/退出证据位于 `.agent_work/temp/m36-full-pytest.{out,err,done,exit}`。
- 2026-08-16：完整回读 Phase 4 的 M36 新章节和 `AI_CONTEXT.md` 全文，标题、中文、当前状态/default/验证/路线/活跃坑一致；`git diff --check` 无 whitespace error，仅报告工作树未来由 LF 转 CRLF 的换行风格 warning。
- Streamlit 的结构化补充表单属于建议项：代码已接入并通过 compileall，但本轮未启动浏览器做人工作用性检查，不把它计入 required 自动化验收证据。

## 模块名称与改动文件清单

- 模块：M36 结构化澄清恢复与轻量 Thread Checkpoint。
- 起始 commit：用户未提供。本次按当前工作树的 `git status --short`、未暂存清单和暂存清单核对；暂存区为空。
- 计划、素材与技术档案：`docs/notes/m36-plan.md`、`docs/notes/m36-notes.md`、`docs/state/AI_CONTEXT.md`、`docs/state/change-history/phase4.md`。
- 配置与应用装配：`.env.example`、`app/core/config.py`、`app/main.py`。
- API / 前端投影：`app/schemas/agent.py`、`app/api/query.py`、`demo/streamlit_app.py`。
- Harness / Trace：`engine/harness/__init__.py`、`contracts.py`、`graph.py`、`router.py`、`thread.py`、`turn.py`、`engine/trace/recorder.py`。
- Eval / 测试：`eval/harness_turn_contracts.py`、`tests/test_config.py`、`tests/test_m36_thread.py`、`tests/test_m36_turn.py`、`tests/test_m36_api_trace.py`、`tests/test_m36_harness_turn_eval.py`。

## 关键决策与取舍

### G-M36-1：checkpoint 归属

- 方案 A：应用持有轻量进程内 checkpoint。优点是保留 M35“一次 invoke → 一份结果”，owner/TTL/version/并发集中在深 module 中；风险是服务重启后 pending 丢失，不能恢复 Graph 中间节点。
- 方案 B：直接采用 LangGraph checkpointer + interrupt/resume。优点是贴近框架原生 HITL，未来可恢复任意节点；风险是本模块就要改写 M35 invocation/result 生命周期，同时扩大 API、Trace、异常关闭和测试范围。
- 当时建议：方案 A。原因是 M36 只需证明 pre-Tool clarification 的一次有界恢复，先把安全生命周期做深比预建会话平台更合适。
- 用户最终选择：方案 A。实现中没有暗设 storage port、`InMemorySaver`、持久化替代层或“以后再换”的临时 interface。

### 实现期关键取舍

- claim 与慢 Tool 分离：在 `RLock` 内完成 owner/lifecycle/answers 校验和原子 claim，Graph 在锁外运行；这样不会用慢 Tool 阻塞所有 thread，同一 version 又最多只有一个执行权。
- 非法补充值在 claim 前失败，不消耗 version；一旦 claim 后 Graph/resolve 出错则不回 pending、不自动重试，避免重复 Tool Call。
- current task 只用 `subject`、`analytics_scope` 两个 closed-world 模板构建；不保存消息历史，不做自由文本 query rewrite，不把完整 checkpoint 交给 Router/Tool。
- 安全复核发现 `TrustedCaller.audit_ref` 不含 tenant，因此默认 owner 改为 `audit_ref + tenant_id` 的内部哈希；显式 `thread_owner_ref` 则由认证适配器提供作用域。错误 owner/missing 使用同一公开结果，避免 thread 存在性侧信道。

## 阶段 1 注释小结

- 检查范围：当前模块 17 个含业务逻辑的 Python 文件，共 171 个类/函数/方法；160 个有显式 docstring，11 个为简单 `__init__` 或明显局部闭包而豁免，0 个未解释项。
- 第 1 遍覆盖：补写 15 个缺失 docstring，主要是合同 `__post_init__`、Eval fake/clock 和 TestClient DB override。
- 第 2 遍质量：深化 checkpoint“待办卡”、compare-and-set 式原子 claim、closed-world Context、owner+tenant、安全投影和不采用 LangGraph 原生 checkpoint 的原因。
- 第 3 遍可读性：复核 create→claim→resolve/clear、owner 后置 lifecycle 检查、Graph 外围预算停止、API 单向投影、sequence Eval 完整性校验；关键分支已有步骤注释，并补充 tenant 绑定为何不能只用 audit ref。
- 第 4 遍形式：更新 `app/api/query.py`、`app/schemas/agent.py` 的过时单轮/M5 描述；中文注释和 ★ 仅保留在核心边界，分隔线沿用项目约定。没有为自解释的纯字段或闭包堆砌注释。

## 参考资料

- 项目事实源：`docs/phase4-roadmap.md` 的 P4/G5、`docs/phase4-reference.md` 的 P4 定点参考、M35 plan/notes、`AI_CONTEXT.md` 与 `runbook.md`。
- 参考源码：ARAG 的 `graph.py`、`graph_state.py`、`edges.py`、`nodes.py` clarification/context 部分。
- 借鉴：pending query 与 clarification 分离、显式预算/停止、恢复前保留最小任务上下文。
- 明确不照搬：全局 `InMemorySaver`、`MessagesState`、LLM query rewrite、history summary、强制检索和开放 Tool loop；这些超出 M36 已确认的一次 pre-Tool clarification。

## Handoff

### 1. 已完成且后续可以依赖

- `/api/query` 支持普通 initial、pending clarification 和一次 resume；成功 resume 仍只进入同一个 M35 Harness，并至多调用一个 SQL/RAG 深 Tool。
- `ThreadCheckpointManager` 提供 versioned create/claim/resolve/clear、owner+tenant/active-role、TTL、state version、原子单 claim、restart loss 与安全 lifecycle fact。
- Router 输出 typed `ClarificationSpec`；`ClarificationContextBuilder` 只支持缺主体和缺时间/分组维度两个冻结模板。
- AgentResponse/JSONL Trace 能关联 turn、Graph 次数、checkpoint runtime、前后 version 和不可逆 thread/context ref；Trace 不保存 raw thread id 或补充值字典。
- `phase4-harness-turn-v1` sequence Eval 与 M36 unit/API suites 可作为后续状态能力的回归基线；M35 artifact 未改版、未混算。

### 2. 下一模块建议入口

- 先结合 Phase 4 roadmap 和新的 sequence 失败结构，判断下一片是 Evidence 失效/重新取证，还是扩展更一般但仍受控的 Context Builder；从 `engine/harness/turn.py` 的 turn seam 和 `eval/harness_turn_contracts.py` 的 sequence evidence 开始调查。

### 3. 未完成、未证明与当前风险

- 未运行真实 LLM Router/Text2SQL Eval、M34 external Answer Eval、Milvus/embedding、remote Composer/Judge 或 LangFuse Cloud；本模块只证明 deterministic clarification/controller 合同。
- checkpoint 仅在单进程内存中，服务重启/多 worker 不共享；这是方案 A 的明确语义，不是可用性承诺。
- 只支持一次恢复、两个 Context 模板；Evidence 复用/失效、Tool retry、Hybrid、长历史、持久化均未实现。
- Streamlit 最小表单未做浏览器人工检查；API/Trace 的同一恢复路径已有 TestClient 自动化覆盖。
- resolved/cleared tombstone 当前保留到进程结束；TTL 已限制 pending 恢复窗口，但本模块没有冻结或实现后台清扫频率。

### 4. 必须延续的决策与边界

- 保留方案 A，除非触发既定决策门；不得把临时持久层或 LangGraph interrupt 偷塞进现有 interface。
- accepted turn 恰好一次 Graph，lifecycle 前置拒绝零次；claim 后失败不重试、不恢复 pending。
- thread id 不是授权凭证；owner/tenant/active role/version 必须在 Tool 前校验，错误 owner 不泄露 thread 是否存在。
- 不让 Router/Tool 读取完整 thread/checkpoint/history；API、Trace、Eval 都从 turn result 与 lifecycle fact 单向投影。

### 5. 待触发的决策门

- 触发条件：真实需求要求恢复 Tool/Evidence/任意 Graph 节点，进程重启恢复成为 required Scenario，或方案 A 无法满足已冻结 clarification sequence。
- 触发前允许：继续做只读调查、失败归因、Scenario/接口设计。
- 触发前禁止：自行切换 LangGraph checkpointer、引入持久 storage adapter，或把一次恢复扩大成长对话/开放 Tool loop。

### 6. 下一轮规划必读指针

- `docs/notes/m36-plan.md`：第 3–8 节，理解本模块冻结的合同、排除项与决策门。
- `engine/harness/thread.py::ThreadCheckpointManager / ClarificationContextBuilder`：owner/version/TTL/Context 的唯一实现边界。
- `engine/harness/turn.py::run_turn / _run_resume`：accepted/rejected turn、claim 后不重试和预算停止的主 seam。
- `eval/harness_turn_contracts.py::run_harness_turn_contracts / validate_completed_turn_artifact`：下一模块扩展 sequence evidence 时必须延续的 closed-world 完整性合同。
- `tests/test_m36_thread.py`、`tests/test_m36_turn.py`、`tests/test_m36_api_trace.py`：安全、并发、API/Trace 的直接回归证据。
- `docs/state/AI_CONTEXT.md` 与 `docs/state/runbook.md`：下一轮当前状态和实际运行入口；涉及历史取舍时先读 `docs/state/CHANGELOG_INDEX.md`。

## finish-module 技术档案交付清单

- [x] 已先读 `CHANGELOG_INDEX.md`，并把记录写入索引指定的当前 Phase 文件。
- [x] 当前 Phase changelog：完整模块已有新的 `###` 条目，包含改动范围、关键记录、参考资料、验证快照、遗留/后续；小修复已有对应简短条目。
- [x] 当前 Phase changelog：改动范围已通过 Git 状态、未暂存、暂存及适用时的起始 commit 清单共同核对，归并后没有遗漏模块文件。
- [x] 当前 Phase changelog：关键用户决策已记录选项、影响、风险、建议与最终选择，没有只写方案代号。
- [x] `AI_CONTEXT.md`：只同步影响续接的当前事实，当前模块、默认配置、最新基线和活跃边界准确。
- [x] `AI_CONTEXT.md` 已完整审查，不是只检查本次新增位置。
- [x] 已替换、退役或删除过时、已完成、已解决、重复或仅具历史价值的当前内容，并确认有价值历史仍可追溯。
- [x] `AI_CONTEXT.md` 的当前状态、默认值、验证事实、路线判断和活跃坑不存在互相冲突的结论。
- [x] 已检查新结论是否修正旧结论；需要时已在 CHANGELOG 旧条目原位添加 `⚠️ 注`。
- [x] CHANGELOG 本模块章节与 AI_CONTEXT 关键区域已完整回读，无截断、乱码、标题层级错误、事实夸大或 notes 不支持的结论。
- [x] `git diff --check` 已通过；如只有换行风格 warning，已如实记录且确认不是 whitespace error。

## finish-docs 执行清单

- [x] 有“简述”和“先用大白话讲”
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] 每个编号点都交代：原问题/影响、关键概念的通俗解释、如何解决、为何不选更宽松方案（如适用）、真实验证证据、尚未证明的边界。
- [x] 本模块首次出现的术语保留英文或代码名，并紧跟一句普通语言解释。

- [x] “新概念”解释至少一个本模块新术语
- [x] “代码阅读路线”是按调用顺序的编号列表，不止说明“看什么”，还需要说明“为什么/解决了什么”
- [x] 有“设计要点”
- [x] “面试怎么讲”有一段可直接复述的模块叙述，说明目标、方案、验证和边界。
- [x] 至少有 1 个 `[基础追问]` 和 1 个 `[工程/深挖追问]`；架构、评测、安全等复杂模块优先增加 `[压力追问]`。
- [x] 追问基于真实实现与证据，覆盖设计取舍、失败场景或后续边界。
- [x] 不写纯定义、送分、显而易见、凑数的低价值问题。
- [x] “验证与下一步”只引用 notes.md 中真实验证快照
- [x] 有可复制命令和本地启动体验/无独立入口说明
- [x] 未把确定性测试写成真实 LLM 能力结论
- [x] 模块记录的各个小节都要用 `**...**` 加粗标出“服务于扫读抓重点”的关键词或关键短句。

## finish-docs 执行结果

- 2026-08-17：按用户明确指示把本文件顶部状态从“开发中”修正为“施工完成，待人工检查与验收”；随后完整读取本 notes、`AI_CONTEXT.md`、`CHANGELOG_INDEX.md` 及索引指向的 Phase 4 M36 技术档案，关键素材和技术结论一致。
- 素材来源：以本 notes 为单一事实源，使用同一会话的新鲜上下文核对，并以 `AI_CONTEXT.md`、Phase 4 M36 changelog 和 Git 范围只读交叉验证；未新跑 pytest、API、smoke、Eval、数据库或真实 LLM。
- 已在 `docs/dev-log.md` 末尾追加 `## ★ M36 结构化澄清恢复与轻量 Thread Checkpoint`，完整回读 179 行新章节。
- dev-log 发生 **1 次二次补齐**：初次回读发现第 4 个“这次做了什么”要点还需明确说明不把完整 checkpoint/补充值写入 Trace、也不改写 M35 历史 artifact 的原因，补齐后再次完整回读通过。
- 15 项 dev-log 交付门均已逐项核对并单独勾选；没有把 deterministic pytest/sequence Eval 写成真实 LLM 或开放多轮能力。
- 本轮只修改 `docs/notes/m36-notes.md` 与 `docs/dev-log.md`；文件时间与操作记录确认未修改 `AI_CONTEXT.md`、`CHANGELOG_INDEX.md` 或 `change-history/`。
- `git diff --check` 无 whitespace error；只有工作树既有的 LF 将转 CRLF 换行风格 warning，不阻塞 finish-docs。
