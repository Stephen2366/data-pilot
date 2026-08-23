# M42 Phase 4B B0 开发记录

> 模块 plan：`docs/notes/m42-plan.md`
>
> 范围：只完成 Phase 4B B0 前置包，不实现 M43–M48 的 Task runtime、Loop、RAG Subgraph、durable state 或 Context Compact。

## Implementation checklist

- [x] M42-A：冻结机器可读北极星 catalog、identity 规则、runtime/API 兼容矩阵、capability matrix 与 action 三层语义。
- [x] M42-B：实现独立 Phase 4B seed/oracle profile、内容身份、7/8 月真实 SQL oracle、宽表对账与 legacy 隔离。
- [x] M42-C：实现最小 `ops + customer_service` caller fixture；gold-first 记录 business RAG 首次默认检索 Observation；冻结 versioned Hybrid operator 语义且不改 legacy v1。
- [x] M42-D：实现 `phase4b-agent-scenario-v1` skeleton、closed-world validator、安全投影与篡改测试。
- [x] M42-E：创建并密封 60 题 decision reserve、污染/访问账本及项目外 artifact manifest；不运行 reserve。
- [x] M42-F：完成零 provider rehearsal、聚焦回归、受影响回归、全仓 deterministic pytest、compileall 与 diff check。
- [x] 按 `finish-module` 完成注释审查、验证快照、Handoff、Phase 4B changelog、AI_CONTEXT 与命中专项 state 更新。

## 开工基线与已确认决策

- 用户于 2026-08-23 确认 G1–G6 全部采用方案 A；命中 plan 的重开条件前不得自行降级。
- M41 的一次执行、resolved runtime、funnel、`not_observed`、closed-world、review hash 和安全投影纪律原样沿用；新建独立 Agent Scenario family，不原位修改 M41 artifact、签名或基线。
- G6 已确认使用项目外 versioned immutable store，但实际绝对路径与工作区外写入仍须在 M42-E 落盘前确认/授权。

## 开发过程记录

### 2026-08-23：启动

- 已重读 `AGENTS.md`、M42 plan、`AI_CONTEXT.md`、公共 runbook、`codebase-design` 与 `finish-module` skill。
- 初步 State impact：数据库/seed、RAG/Knowledge、Eval 合同均命中；运行入口是否需要更新待最终文件范围确认；Schema Retrieval/Milvus 默认不在范围内。
- 起始 commit：`f3cc1912a2ab1e9b87fbc3f57d4adb1cdf03df40`。启动时 Git 仅显示 M42 plan/notes 两个未跟踪文件；另有 `.codex/temp_work/pytest-m41-second/` 权限 warning，不属于 M42，不处理。

### 2026-08-23：M42-A 机器合同

- 新增独立 `engine.phase4b` seam 和 `phase4b-b0-contracts-v1` 内容 manifest；北极星 T1–T5、extended/非 happy-path、最小 caller、runtime family、Hybrid operator、action 三层语义和 capability handoff 由一个严格 loader 消费。
- 取舍：共享的只有 canonical hash implementation，seed/catalog/artifact 仍保留各自合同，避免为了代码复用制造万能 identity schema。
- 聚焦测试首次在 sandbox 内出现 pytest basetemp `WinError 5`，属于 session 清理权限而非断言失败；相同范围经批准在 sandbox 外重跑为 `2 passed in 0.42s`。

### 2026-08-23：M42-B seed 首次失败与修正

- 首次 Phase 4B 建库真实 SQL 得到 7 月净退款 `139,920`，不是冻结的 `120,000`。根因是 legacy 6 月末订单按 `paid_at + 4–8 天` 产生 `processed_at`，有 `19,920` completed refund 自然滑入 7 月。
- 取舍：不把 oracle 改成只过滤 `REF-P4B-*`（那会让产品 SQL 与测试 SQL 口径不同），也不修改默认 legacy recipe。只在显式 Phase 4B profile 的隔离副本内，把 legacy spillover 固定到 6 月末，再追加 7/8 月事实；profile summary 记录 retimed 数量。
- 首次 debug 命令在首个失败停止：`1 failed in 23.17s`；修正后待重跑。

### 2026-08-23：M42-C/D/E 阶段 checkpoint

- M42-C：最小双角色 caller、默认 budget business retrieval、缺客服角色反例和 M38 legacy Hybrid 回归为 `9 passed in 1.05s`；未改 active release、ACL、默认 caller 或 Router。
- M42-D：独立 `phase4b-agent-scenario-v1` 完成 artifact、sequence/turn/execution/assertion closed-world、identity 与安全 capability report 已实现；连同 M41 合同回归为 `11 passed, 1 warning in 1.59s`，warning 是既有 Starlette/httpx deprecation，不影响模块。
- M42-E：reserve 合同、hash 对账和污染退出状态机为 `2 passed in 0.42s`。已从冻结 external corpus 按 source/长度抽取 20 份未进入既有 180 gold 的文档，编写 60 题：`20 basic / 20 core / 20 hard`，core 8 道多文档、hard 20 道多文档；结构、近重复和双审核材料的离线合同检查通过。
- 待完成：取得项目外 `phase4b-agent-eval/v1.0.0` 绝对路径写入授权，创建/密封实际资产并生成仓库安全 manifest；随后完成 rehearsal、全量验证和 finish-module。

### 2026-08-23：M42-E/F 实际资产与首次 rehearsal

- 用户确认并授权的 immutable store：`D:\.Work\Practice\AI-Project\data-pilot-datasets\phase4b-agent-eval\v1.0.0`。已密封 60 题正文、双审、source pool 与访问账本；reserve identity 为 `f70c5fcafa3d7601d2700a5d98dc2a2647532c236dd1a56e6a48008fa100e505`，首次解封模块仍是 M46。
- 仓库只保存安全 manifest，不保存题面、gold、绝对外部路径或访问凭据。密封后又以只读方式对账 source hash、逐文件 hash 和 reserve identity，身份未变化；没有运行 candidate、没有读取 M34 heldout 做调参。
- 零 provider rehearsal 已完成并固化为不可覆盖的首次 Observation：Phase 4B 7/8 月净退款分别为 `120000.00 / 180000.00`，星型表与宽表一致，保留 2 条负数冲销；默认 business retrieval 只取回 `refund_policy_quality`，遗漏 `refund_policy_basic`，因此如实记录 `all_gold_selected=false`，没有修改参数、语料、ACL 或 active release。
- Agent Scenario skeleton、capability matrix 与 deterministic report 已写入 `eval/reports/m42/`；报告明确 M42 只证明 B0 前置条件，M43–M48 能力均未宣称可用。

### 2026-08-23：finish-module 注释与合同复核

- 已完整回读 M42 新增核心代码、全部 M42 测试，以及修改后的 `engine/governance.py`、`scripts/seed_data.py`。模块/类/公开函数均有中文职责说明，复杂 seed 隔离、JSON round-trip、双审和不可覆盖路径已有关键注释。
- 复核发现：少数内部 helper 缺职责说明；B0 catalog 列表项若损坏成非 object，可能泄漏普通 `AttributeError`。已在原合同内补齐 docstring，并让 runtime family/action/scenario 的非 object 项稳定返回 `Phase4BContractError`，新增畸形 action 回归；未改变 frozen JSON、identity 或能力范围。
- 修正后的三组合同测试：首次仍受 Windows sandbox basetemp `WinError 5` 中断；相同命令经批准重跑为 `12 passed in 0.62s`。

## 关键决策与取舍

- **G1 seed profile**：方案 A 是新增独立 additive Phase 4B profile，方案 B 是升级 legacy canonical seed。B 会让 M1/M27 历史 artifact 看似仍可比较，风险更高；建议并由用户选择 A。实施时发现 legacy 退款尾巴滑入 7 月，只在显式 Phase 4B 副本内 retime，不用 `REF-P4B-*` 过滤伪造产品 SQL 口径。
- **G2 caller**：方案 A 是最小 `ops + customer_service` fixture，方案 B 是扩张全部角色/生产认证。B 会扩大授权和部署范围；建议并由用户选择 A。active SQL role 仍只有 `ops`，生产认证未建设。
- **G3 business case**：方案 A 是先冻 gold 再执行一次默认 retrieval，方案 B 是挑一次必然取全的题。B 无法形成真实失败 Observation；建议并由用户选择 A。实际结果遗漏 `refund_policy_basic`，如实保留为 M45/B3 输入，不为通过而改参数。
- **G4 Hybrid operator**：方案 A 是新建 versioned `refund_change_and_policy` contract-only 语义，方案 B 是改写 M38 `refund_reason_and_policy`。B 会破坏 legacy fixture；建议并由用户选择 A。M42 不实现新 operator runtime。
- **G5 decision reserve**：方案 A 是 60 题 basic/core/hard、含多文档、双审并在 M46 首次解封，方案 B 是复用 M34/M41 已看过题集。B 会污染 decision set；建议并由用户选择 A。任何提前访问或调参都会让 reserve 退役。
- **G6 storage**：方案 A 是项目外 versioned immutable store，仓库只留安全 manifest，方案 B 是把题面/gold 提交仓库。B 会泄漏并提高误用风险；建议并由用户选择 A。用户确认的绝对路径已获得写入授权。
- **M41 沿用方式**：不是“按旧 roadmap 忽略 M41”，也不是原位改 M41 artifact；而是复用其一次执行、closed-world、`not_observed`、review hash 和安全投影纪律，新建独立 `phase4b-agent-scenario-v1`。M41 历史资产、基线和默认 runtime 保持只读。

## 模块名称与改动文件清单

- 模块：M42 / Phase 4B B0 前置包；起始 commit 明确为 `f3cc1912a2ab1e9b87fbc3f57d4adb1cdf03df40`。
- 目录与合同：`engine/phase4b/`、`domain_pack/phase4b/`、`eval/cases/agent/phase4b_reserve_manifest.json`。
- Eval 与报告：`eval/agent_scenario_contracts.py`、`eval/agent_reserve_contracts.py`、`eval/reports/m42/`。
- 构建/运行入口：`scripts/build_m42_decision_reserve.py`、`scripts/rehearse_m42_b0.py`。
- 兼容修改：`engine/governance.py`、`scripts/seed_data.py`、`AGENTS.md`。
- 测试：6 个 `tests/test_m42_*.py` 文件。
- 过程与计划：`docs/notes/m42-plan.md`、`docs/notes/m42-notes.md`。
- 项目外 immutable artifact：`D:\.Work\Practice\AI-Project\data-pilot-datasets\phase4b-agent-eval\v1.0.0`，不进入 Git 文件清单。
- 收工后还将新增/修改：Phase 4B changelog、`AI_CONTEXT.md`、数据库/RAG/Eval state 和 `docs/dev-log.md`；分别由 finish-module / finish-docs 门禁管理。

## 阶段 1 注释小结

- 完整检查 17 个 M42 相关 Python 文件（11 个实现/兼容文件 + 6 个测试），共 114 个不含构造器的类/函数/方法符号；既有文件中未触碰的简单 property/投影/helper 不计入 M42 缺失。
- 实际补写 14 处内部职责说明：合同、profile、Scenario、reserve helper、两个脚本入口/闭包，以及 4 个 M42 测试 helper；M42 新增非测试逻辑仍缺失 0 处。
- 深化的关键概念：content identity 只绑定内容不绑定路径；global/applicable/eligible action 三层不等于动作已准入；sealed reserve 的“全局存在”与“当前开发可见”分离；Phase 4B profile 只在显式选择时隔离 legacy 时间尾巴。
- 修正的复杂处：runtime family/action/scenario 非 object 项现在稳定 fail closed；Scenario tuple 经 canonical JSON round-trip 后再签名，避免内存/落盘形状漂移；首次 rehearsal 明确不可覆盖。
- 全仓测试通过后只新增测试 helper docstring，行为与验证条件未变化，因此未重复运行 9 分钟全仓测试；最终仍执行 compileall、diff 和文档检查。

## 验证快照

- `python -m pytest tests/test_m42_phase4b_contracts.py ...`：首次临时目录权限中断；同范围批准重跑 `2 passed in 0.42s`，无 warning。
- seed profile + M1：`6 passed in 60.41s`。
- M42 全部聚焦 + `compileall`：`19 passed in 47.11s`；注释复核后合同子集为 `12 passed in 0.62s`。
- M38 legacy Hybrid 回归：包含在 M42-C 的 `9 passed in 1.05s`；M41 artifact 合同回归：包含在 M42-D 的 `11 passed, 1 warning in 1.59s`。
- 计划指定受影响回归 A（M1/M27/M31–M34）：`179 passed, 1 warning in 28.41s`。
- 计划指定受影响回归 B（M35–M41）：`82 passed, 1 warning in 60.21s`。
- 注释修正后 `compileall` 和 `git diff --check` 均 exit 0；新增/产物路径 trailing-whitespace 扫描无命中。两段回归的 warning 是同一条既有 Starlette TestClient/httpx deprecation。

### 全仓后台验证启动前 checkpoint

- 关键决策：G1–G6 方案 A 均已按确认实现；legacy 默认、active business release、ACL、Router、Composer、模型与 external lexical 默认均未改变；M41 资产继续只读沿用，M42 Agent Scenario 使用独立 family。
- 改动范围：新增 `engine/phase4b/`、Phase 4B domain profile/manifest、Agent Scenario/reserve 合同、60 题外部密封脚本与安全 manifest、零 provider rehearsal/报告、6 组 M42 测试；仅为 tenant fixture 扩展 `engine/governance.py`，仅以显式 profile 扩展 `scripts/seed_data.py`，并同步 `AGENTS.md` 目录树。
- 已完成验证：M42 聚焦、seed/M1、M38/M41 定点回归、M1/M27/M31–M41 全受影响回归、compileall、diff check 均通过；项目外 reserve 已只读 hash 对账；首次 Observation 已固化且不可覆盖。
- 已知风险：business 首次检索真实遗漏基础退款政策，是 M45/B3 的输入而非 M42 修复目标；60 题 reserve 在 M46 前保持 sealed；全仓 pytest 尚待后台完成并检查。
- 待完成：检查全仓后台退出码/完成标记/日志；随后更新 Phase 4B changelog、`AI_CONTEXT`、数据库/RAG/Eval state，完整回读 notes/state，完成 finish-module 硬门。

### 全仓后台验证（运行中，待检查）

- 命令：`python -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\m42-full-pytest-base`
- PID：`54368`
- stdout：`.agent_work/temp/m42-full-pytest.out`
- stderr：`.agent_work/temp/m42-full-pytest.err`
- 退出码：`.agent_work/temp/m42-full-pytest.exit`
- 完成标记：`.agent_work/temp/m42-full-pytest.done`
- 当前状态：**运行中，待检查**；未提前记录为验证通过，也未宣称 M42 完成。

### 全仓后台验证首次结果与原命令重跑 checkpoint

- 首次后台任务完成标记存在，但 exit code 为 `1`。pytest 收集 `490 items` 后，大量依赖 `tmp_path` 的测试在 sandbox `basetemp=.agent_work/temp/m42-full-pytest-base` 遭遇 `PermissionError: [WinError 5]`；session finish 也因无法遍历同一路径退出。该结果是运行环境失败，不是可信的全仓通过；其中混入的 error/failure 不能在临时目录失效时冒充代码回归结论。
- 处理方式：不改代码、不改测试、不缩小范围，使用同一全仓命令、全新的 basetemp 和日志路径，在已授权的 sandbox 外后台重跑。此前两段同环境受影响回归已分别 `179 passed`、`82 passed`，因此本次只解决全仓运行条件。
- 重跑前改动范围、关键决策、已完成验证、风险与待办沿用上一 checkpoint；新增风险仅为“全仓结果尚未取得”，`finish-module` 与 `finish-docs` 均继续停门。

### 全仓后台验证重跑（运行中，待检查）

- 命令：`python -m pytest -p no:cacheprovider --basetemp=.agent_work\temp\m42-full-pytest-approved-base`
- PID：`55220`
- stdout：`.agent_work/temp/m42-full-pytest-approved.out`
- stderr：`.agent_work/temp/m42-full-pytest-approved.err`
- 退出码：`.agent_work/temp/m42-full-pytest-approved.exit`
- 完成标记：`.agent_work/temp/m42-full-pytest-approved.done`
- 当前状态：**沙箱外运行中，待检查**；finish-module/finish-docs 未完成。

### 全仓后台验证重跑结果

- 完成标记为 `completed`，exit code `0`，stderr 为空。
- 全仓结果：`487 passed, 3 skipped, 1 warning in 566.30s`。3 个 skip 是既有 Milvus 专项环境跳过；warning 是既有 Starlette TestClient/httpx deprecation，均不阻塞 M42。
- 首次 sandbox 失败保留为环境故障记录，不覆盖、不伪装成代码回归；沙箱外同范围重跑是本模块最终全仓事实。

## 参考资料

- `agentic-rag-for-dummies/notebooks/evaluation.ipynb`：借鉴“一次执行后保存实际 answer/context 再评分”和数据集一致性检查；不照搬逐题 reset、CSV 唯一事实源、简单平均或跳过失败。
- DB-GPT `rag/evaluation/retriever.py`、`answer.py`：借鉴 retrieval/answer evaluator 分层；不让 evaluator 重跑 operator，也不用单一 LLM 分数替代安全 Gate/人工复核。
- WrenAI `MemoryIndex.reset / LanceDBIndex.rebuild` 与 `watch.py`：借鉴 source/derived identity 分离和成功构建后推进 observed state；不照搬 path/size/mtime fingerprint、watcher 原子性假设或未校验 fallback。
- DataAgent `AgentVectorStoreServiceImpl.replaceDocumentsByMetadata`：借鉴按 metadata 身份隔离替换；DataPilot 继续使用 immutable staged release，不把 best-effort cleanup 描述成事务。
- GustoBot `multi_tool.py::local_search / finalize / _collect_sources`：只借鉴多数据面分开保存再汇合的形态；不照搬 Router 未指定时自动扩 Tool、文件名冒充 citation 或任一分支命中即 complete。
- 这些参考都不具备 DataPilot 的 22 条 business / 36,417 文档 external 双规模、typed Evidence、ACL、四轴和 sealed decision reserve；最终保证由 M42 自身 closed-world 合同与测试提供。精确适配表见 `docs/notes/m42-plan.md` 第 3 节。

## Handoff

### 已完成且可依赖

- M43/B1 可直接加载 `phase4b-b0-contracts-v1`，消费 T1–T5、extended/非 happy-path、runtime family、最小 caller、四轴和 capability handoff；不得重新定义这些冻结输入。
- 显式 `profile_alias="phase4b"` 可构建可复现的 7/8 月 SQL oracle；legacy 默认仍是 `sqlite_deterministic_seed`。profile/oracle/content identity 和宽表对账均有真实 SQL 验证。
- `phase4b-agent-scenario-v1` 能生成并拒绝篡改的 completed skeleton；它是 Eval artifact 接口，不是 Agent runtime 已完成证明。
- M45/B3 可消费首次 business Observation；M46/B4 在规定门后可消费 sealed reserve protocol。仓库 manifest 与外部逐文件 hash 已闭合。

### 未完成与风险

- M42 没有实现 TaskState、顶层 Loop、新 Hybrid operator 执行、RAG Subgraph、durable checkpoint、Context Builder/Compact；对应能力仍由 M43–M48 owner 标为 unavailable。
- 首次 business retrieval 没取全两份 gold 政策，证明默认 lexical 小语料也会漏选；这是后续诊断输入，不是 M42 应当偷偷修复的质量问题。
- 60 题 reserve 只完成离线构造、双审与密封，没有运行 candidate，也没有形成性能/质量基线；合成 external 文档不能外推真实企业生产质量。
- Phase 4B profile 为北极星提供确定性事实，仍需后续 Scenario 防止过度适配；默认产品数据库没有被切换到新 profile。

### 必须延续的边界与决策门

- legacy 与 agent runtime family 必须并存并分别过 Gate；禁止把 legacy field/budget 静默改成 Agent 语义。
- M46 前 reserve 保持 sealed；任何提前 gold/candidate 访问或用于调参都必须按状态机退役，不能继续作为 decision set。
- 不得仅因实现方便缩减 Phase 4B 最终能力；M43–M48 owner 和最终验收仍以 roadmap/独立 module plan 为准。
- active business release、ACL、默认 lexical/Composer/model、M34/M41 baseline 均未改变；未来切换仍需新 identity、可比证据和用户确认。

### 下一模块入口与必读指针

- 建议下一模块按 roadmap 进入 M43/B1，从 `docs/phase4b-roadmap.md` 的 B1、`docs/notes/m42-plan.md` Handoff、`domain_pack/phase4b/b0_contracts.json`、`engine/phase4b/contracts.py` 和 `tests/test_m42_phase4b_contracts.py` 开始。
- TaskState/turn-boundary 设计前定点复核 `docs/phase4-reference.md` 对应 LangGraph/DataAgent 状态与 checkpoint reference；只借鉴 state seam/保证边界，不把参考项目字段原样复制到 DataPilot。
- M45/B3 需要从 `eval/reports/m42/m42-business-first-observation.json` 开始，且只能使用预注册动作与预算；M46/B4 才能按 manifest 的 `first_unseal_module` 进入 reserve decision。

## finish-module 技术档案交付清单

- [x] 模块最终文件范围已与 Git 状态、起始 commit 和 notes 核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] 已读取 `CHANGELOG_INDEX.md`，并按索引写入完整模块记录。
- [x] `AI_CONTEXT.md` 已更新并清理失效、重复或仅具历史价值的内容。
- [x] 所有命中的专项 state 均已完整检查，并已更新或记录“无需修改”的理由。
- [x] 新结论与历史条目、代码、测试、Eval、默认配置和各 state 之间不存在冲突或重复权威定义。
- [x] changelog 新章节、`AI_CONTEXT.md` 和所有修改过的专项 state 已完整回读。
- [x] `git diff --check` 及本轮涉及的文档链接检查已通过，结果已写回 notes。

核对结果：最终 Git 清单与起始 commit/notes 一致；完整回读时发现 M42 路线判断最初落在 `AI_CONTEXT` 活跃坑表之后，已移回“当前路线判断”顶部并重新核对。最终 compileall 与 `git diff --check` exit 0，10 个 plan/state/artifact/外部 manifest 关键路径全部存在。`AGENTS.md` 等文件的 LF→CRLF 提示只是 Git 行尾提醒，不是 diff error；无新的失效链接或默认配置冲突。finish-module 硬门全部通过。

## State impact

- **已更新**：`database-current-state.md`（显式 Phase 4B profile、identity、7/8 月 oracle 和 legacy 隔离）；`rag-current-state.md`（首次真实漏选 Observation、Agent skeleton 与 sealed reserve 污染门）；`eval-baselines.md`（登记 B0 deterministic artifact/protocol，明确不形成质量基线）；Phase 4B changelog（完整 M42 模块档案）；`AI_CONTEXT.md`（当前模块、默认 profile 边界、最新验证和路线入口）。
- **已检查、无需修改**：`runbook.md`。M42 rehearsal/build 脚本不是产品 API 或真实 Eval 日常入口，且固定首次输出不可覆盖；可复制复核命令放 notes/dev-log，避免把一次性密封流程提升为公共默认运行入口。
- **未命中**：`schema-retrieval-milvus-embedding.md`；M42 未改 Schema Retrieval、embedding、Milvus 或 collection。

## finish-docs 执行清单（Track A）

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] “这次做了什么”的每个编号点都交代：原问题/影响、关键概念的通俗解释、如何解决、重要取舍、验证证据、未证明的边界；不适用项可以省略。
- [x] 每个编号点没有挤成一个无断点大段：编号下先写一句可独立成立的结论，再用 `- **小标题**：` 或分段落拆分不同主题；任何自然段超过约 4 行、或包含 3 个以上独立主题时必须拆分。
- [x] 正文每个英文/代码术语首次出现时紧跟括号或一句通俗解释（如 `checkpoint（任务检查点）`）。
- [x] 需要对照的数字（A/B 结果、覆盖率、pass 数）优先用列表或表格呈现，不埋在长句中间。
- [x] 新概念存在时已用通俗语言解释；没有新增概念时不强行编造。
- [x] “代码阅读路线”是按真实调用或数据流组织，不止说明“看什么”，还需要说明“为什么/解决了什么”
- [x] 有“设计要点”
- [x] “有面试价值的亮点”有可背、可独立展开的亮点。
- [x] “有面试价值的亮点”只讲能在面试中拿得出手的、能让面试官认可能力的，禁止强行凑数。
- [x] 追问优先围绕亮点展开，没有强行凑数的低价值问题和回答。
- [x] “验证与下一步”只引用 notes 中的真实验证快照。
- [x] 复制命令安全、可重复，并标明必要前置条件。
- [x] 模块记录的各个小节的文本都要用 `**...**` 加粗标出“服务于扫读抓重点”的关键词或关键短句。

当前素材核对：最近一次 finish-module 技术档案交付清单 8/8 为 `[x]`；范围、用户 G1–G6 最终选择、真实验证、风险/兼容/安全边界、遗留和 Handoff 均齐全。Track A 开始前 Git 范围与 notes 一致；技术 state 已记录起始 SHA-256，finish-docs 阶段不再修改这些文件。

Track A 最终核对：M42 模块记录已完整回读，8 个必需小节齐全；“这次做了什么”有 5 个主体编号，另有 6 步真实代码阅读路线、4 个面试亮点、4 个对应追问、验证对照表和带前置说明的安全复核命令。回读中把“全部聚焦 19”修正为“首轮聚焦 19”，并为 SQL、identity、gold-first、provider、ACL、active release、warning/skip 等首次出现的术语补了通俗解释。引用的 9 个关键路径全部存在；Track A 前后 6 份技术 state 的 SHA-256 完全一致，期间只编辑 `docs/dev-log.md` 和本 notes；`git diff --check` 通过，只有既有 LF→CRLF 行尾提示。
