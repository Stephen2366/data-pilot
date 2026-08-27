# DataPilot AI Context Changelog — Phase 4B

> Phase 4B 的新记录写入本文件头部；阶段结束后再将本文件转为历史档案。
>
> 本文件保存 Phase 4B（M41 起，对应 `docs/phase4b-roadmap.md`）的模块档案、实验记录和技术取舍，按时间倒序排列。Phase 4（M29–M40）历史仍见 `change-history/phase4.md`。当前项目状态以 `docs/state/AI_CONTEXT.md` 为准；跨阶段索引见 `docs/state/CHANGELOG_INDEX.md`。
>
> 默认先按模块号、日期或关键词定位，再读取相关章节，不要无差别全文读取。新结论修正本阶段旧判断时，应在旧条目原位添加 `⚠️ 注`。

标题标签：

- `[模块任务]`：功能、架构、默认行为、安全口径、评测口径等实质性任务。
- `[实验]`：A/B、真实 LLM Eval、smoke 或会影响路线判断的实验结论。
- `[小修]`：文档措辞、口径同步、注释补充、轻量整理；只需简写，不要求完整模板。

「变更记录」：小修可以只写一段话；较大的任务建议包含：改动范围、关键记录（比如关键决策、决策原因、实验结果、新发现、用户做出的选择等）、参考资料、验证快照、遗留/后续。

同一模块 / 同一阶段内连续的小修（中间没有被 [模块任务] / [实验] 等其他类型条目隔开时），合并到一个 [小修] 小节。

## 变更记录（新的在上）

### [实验] Phase 4B 整体审计双 Probe（2026-08-27 后，审计轮）

- **范围与授权**：M49 收工后对 B0～B6 做整体审计，用户授权两个 `exploratory / baseline-ineligible / development-probe`：P1 纵向链 ≤14 calls/≤60,000 tokens（运行仓库已提交 `scripts/probe_m49_phase4b_continuity.py`，r9），P2 真实 lineage 安全负例 ≤6 calls/≤15,000 tokens；后经用户裁决追加 P2 attempt 2 最小重验 ≤2 calls/≤6,000 tokens。只写隔离库 `datapilot_m48_test` 并清理 0/0；不碰 held-out/reserve/生产数据/默认切换。
- **P1 r9 结果**：当前工作区（含未提交 external Subgraph 水化修复）真实 Qwen/MySQL/business Subgraph 同一 task T1→T6 一次贯通，版本链 `1→3→5→7→9→11`；T3 Observation 驱动两次 SQL action；T4/T5 Hybrid+business Subgraph 各 2 citations；新进程 T6 Compact `triggered_and_committed`（`68cae70a...`）零 Graph/Tool/provider 复述；no-resolver 负例 `task_unavailable`/0 provider/不创建 task；12 calls/52,709 tokens、retry0、cleanup 0/0。**证明未提交改动没有破坏整条链，当前工作区可一键复现招牌演示。**
- **P2 attempt 1**：T2 前置 turn 的 `sql_generation` 阶段 Qwen 网络调用 120s 超时（query_plan 68s 已成功），产品正确失败关闭（`llm_generation_error`→不执行 SQL→`no_answer`，usage 完整记账），负例未触达；根因=provider 抖动，非产品缺陷。证据保留，不自动重跑。
- **P2 attempt 2（用户裁决最小重验）**：T1 真实 v1 后，不存在的 `expected_version=2` → `task_version_conflict`（0 provider/0 invocation/不投影 task），`customer_service` 角色漂移 → `task_unavailable`（blocked/0 provider/0 invocation）；两负例与预注册预期一致。state 直查因审计 runner 用错列名（真实主键 `task_key=sha256(task_id)`）未观察到，间接证据：0 invocations + 无 task 投影 + M48-P2 边界 artifact。2 calls/5,783 tokens。
- **总账**：18 calls / 71,001 tokens（≤20/≤75,000），retry0。审计发现（README 过期/默认演示库缺 8 月种子/未提交工作区/purge 无 scheduler/演示链对 Qwen 延迟敏感等）与三态结论见 `docs/notes/phase4b-audit-notes.md`；本轮只审计不修代码。

### [实验] M49 收工后 RAG 真实链路探索重验（2026-08-27）

- **范围与边界**：用户授权 5 个固定场景、最多 10 provider attempts / 35000 observed tokens 的收工后探索重验；只读业务 active release、external `diagnostic_dev/qst_0386` 与 `qst_0431`、冻结 semantic profile/collection，禁止 held-out、sealed reserve、生产数据、重建索引、切默认或自动重跑。该运行标记为 `exploratory / baseline-ineligible / not-development-probe`，不是 Formal Eval 或开发期 Probe。
- **已通过链路**：Business happy path `quality_refund_materials` required `14/0/0`、1 Qwen / 1013 tokens；无候选 `unsupported_warranty_rule` required `9/0/0`、Composer 0；Enterprise semantic Pipeline qst_0386 required `12/0/0`，漏斗 `5→3→3→1`，1 embedding + 1 Qwen / 2082 observed chat tokens，advisory 仍 `2/1`。
- **首个失败与根因**：experimental Subgraph qst_0431 已完成 semantic initial retrieval、deterministic procedure admission、2-unit sibling expansion 和 3 条最终 Evidence，但最终 `context_characters=0`；Qwen transport 成功后以 `composer_response_invalid_cardinality` 失败（398+9=407 tokens），required `9/1/2`、漏斗 `3→3→3→0`，安全关闭无答案。根因是 external active bundle 按设计只载 metadata/空 content，正常 Pipeline 通过 SQLite materializer 水化；`BoundedRAGSubgraphAcquirer._reauthorize_and_merge()` 却直接用 metadata entry 重建 Evidence，没有调用正文 loader。现有 external chain fixture 自带正文，聚焦 qst_0431 类测试仍通过，未覆盖产品 metadata-only seam。
- **初始停门**：累计 `5 provider attempts（3 chat + 2 embedding）/ 3502 observed chat tokens` 后按预注册首个产品失败停止，未立即执行 R5 或重跑 R4。该时点只证明 Business、External Pipeline 与 Subgraph 检索/扩展/失败关闭，不能宣称 external recovery→Composer 或本轮 Hybrid 贯通。
- **修复与 R4R**：用户授权修复和下一次 Probe。Subgraph recovery 现在显式注入既有 Enterprise SQLite context loader；每条 metadata entry 水化后必须保持 key/revision/content hash/anchor、正文非空且有坐标，再重建 Evidence。FastAPI/Eval 产品组装都注入同一 loader；缺依赖或漂移失败关闭，不放宽 Composer/support/citation validator。R4R 同题一次将 `context_characters 0→5425`，结果 `completed/complete/passed`、漏斗 `3→3→3→2`、1 embedding + 1 Qwen / 2304 tokens；required Gate 仍因 `cited_gold` 为 `11/1/0`，所以技术链恢复但质量未通过。
- **R5 与验证**：R4R 无系统性失败后，原预注册 R5 单 turn 真实 Hybrid 通过：Qwen + SQL Guard + `datapilot_m48_test` + business Subgraph 同一父 Loop 完成 SQL/Document 双 Evidence，8 rows、2 citations、2 calls / 9696 tokens，task/event `0/0→1/1→0/0`。campaign 最终 `9 attempts（6 chat + 3 embedding）/ 15502 observed chat tokens`；受影响回归 `84 passed, 1 existing warning`，compileall通过。没有 held-out、reserve、fallback、索引或默认切换；证据见 `docs/notes/m49-rag-postprobe.md` 和 `.agent_work/temp/m49/rag-postprobe/`。

### [模块任务] M49 Phase 4B 最终联调与证据可信度优化（2026-08-27）

- **改动范围**：基线 HEAD=`6e3cf3459088010e308a28d8361cd10b4348faba`，模块期间无提交。修复完整显式重述仍叠加旧 requirement、comparison repair-success/跨 turn coverage、conditional quality dependency、QueryPlan/SQL derived-scope fidelity 与重启后 existing-result 断点；新增 Context/Compact v2 bounded latest result digest、Scenario v7、assurance v2、真实 P1/P2 Probe、连续 rehearsal、报告和回归。M42～M48 artifact 保持可读；没有修改业务 seed、Knowledge active release、Milvus/index、Pipeline/Subgraph rollout 或 sealed reserve。
- **关键决策与实现**：用户确认 G49-1～G49-5 均采用 A：typed completeness 替换完整重述、additive v7/assurance v2、B4 experimental-only 正式收口、`datapilot_dev` 正常迁移 0005、内部 `caller_untrusted`/公开 `task_unavailable` 分层。QueryPlan 与 derived SQL 均只强化 prompt 正反例，不弱化 validator。G49-6/G49-7 采用 guarded typed rows 的确定性两期增量与 active Evidence 跨 turn 复用。G49-8 针对个人 Demo 采用 C，但收敛为 Context/Compact additive v2：最近结果摘要最多 8 KiB/16 Evidence ID，不改 TaskState/数据库 schema，v1 继续可读，terminal scrub 不变；`ask_about_existing_result` 可零 Graph/Tool/provider 复用，缺 digest 则明确要求重查。LLM Turn Understanding C 只进入防遗忘账本，未实施。
- **真实 Probe 与实验结论**：P1 最终在真实 Qwen + Text2SQL + Guard + MySQL 完成 T1/T2，完整重述只保留 comparison requirement，并自然覆盖 `DATE_TRUNC` failure→deterministic repair success，4 calls/13075 tokens、cleanup 0/0。P2 r1～r7 依次暴露 QueryPlan alias、代理/网络、derived scope、Controller dependency/cross-turn coverage 与 T6 结果解释合同，均按首错分层保留；r8 同一 task 贯通 T1～T5，worker B 新进程恢复并在 T6 从 Compact v2 digest 零调用复用最近结果，安全负例在 deep runtime/provider 前关闭，12 calls/51013 tokens、retry0、cleanup 0/0。两项均为 exploratory/baseline-ineligible，只证明固定 Demo 技术链，不外推泛化、质量或生产能力。
- **证据可信度修复**：旧 Scenario v6/assurance 继续只读，但不再允许 contract identity 或常量 observation 冒充执行。v7 required assertion 必须绑定独立 execution locator/identity，缺失自动 `not_observed`；assurance v2 再聚合 v7、各 B 合同与 execution evidence。正式 Scenario v7 identity=`9b133cdf0bd1c071a0f10f79d03e86a0cdc00a4a75258a5d0e878a78e8ced080`，assurance v2=`bc4958405eb777b9be3a0ee1e392a9592181792d3563e0b1be33db53312e36bf`，均 completed。
- **参考与适配**：依据 `docs/phase4-reference.md` 与 M42～M48 合同，复用 additive version、closed-world identity、父子预算、Evidence/Context 分权、服务端受控策略和失败关闭 seam。未照搬 LLM 自由摘要/TaskDelta、自动 SQL 语义改写、弱化 plan fidelity、Graph program counter 持久化或用 deterministic artifact 代替质量 Eval；本模块无新增外部研究。
- **验证快照**：最终聚焦=`35 passed, 1 existing warning`；deterministic evidence=`6 passed`，JUnit SHA-256=`9f2f9e55...65e0`。全仓前台收集 677 项后后台同次=`677 passed, 1 warning in 595.25s`；首次 launcher 失败发生在 collection 前、零测试执行，已分账保留。compileall、rehearsal 重签、`git diff --check`、Alembic `current=20260827_0005 (head)` 与 `check=No new upgrade operations detected` 均通过。`datapilot_dev` 从 0003 正常升级且 users/orders/refunds/knowledge_docs 仍为 `200/10000/1000/11`，无 reset/reseed。
- **遗留/后续**：Phase 4B 固定展示链可技术收口；Pipeline 仍默认、Subgraph 仍 server-controlled experimental、no-auto-fallback、reserve sealed/not-run。未证明开放问法泛化、RAG/LLM 质量胜出、生产认证、性能/HA、跨 task 长期记忆或外部 Tool exactly-once。只有形成稳定失败簇和新候选时再立编号计划，不为扩功能而扩功能。

### [模块任务] M48 Phase 4B B6 Context Compact 与全阶段技术集成（2026-08-27）

- **改动范围**：起始 HEAD=`472b1ca55fad9c373839d0e82f7dc4d815a63b92`，期间无模块提交。新增 content-bound B6 contract/manifest、strict Task Context Window/Task Compact codec、统一 Context Builder、memory/MySQL boundary context seam、event v2、Alembic `20260827_0005`、API/Trace 安全投影、真实 MySQL 双 Probe、continuous rehearsal、Agent Scenario v6、B0～B6 assurance、报告和 M48 测试；旧 v1～v5 artifact、业务表/seed authority、Knowledge release、Milvus/index、M46 rollout/reserve 均未改签或切换。
- **关键决策与实现**：用户对 G48-1/G48-2 均选择 A：5 committed turns 或 candidate node Context 75% token budget 双触发，recent raw window 只保留最近 2 个 user turns且每条 2048 bytes；checkpoint additive context payload + event v2，不新增第三张表，真实写入只允许 `datapilot_m48_test`。Compact 由 TaskState + 连续 typed turns 确定性派生，保留 source/version/high-risk references，但从不成为 Evidence/ACL/业务 authority；state/context/event 同 claim 原子提交，terminal/clear/expiry 同步 scrub。收工回归还发现 switch 误带旧 Context lineage，现已保持旧 task claim/退役语义，同时让新 task 从 T1/version=1 独立起步。
- **真实 Probe 与实验结论**：P1 的实际时点为 after B + C/D draft / before E，晚于理想 before-C，已如实保留；attempt 1 暴露 TaskState JSON list/tuple restart parity，修复后 attempt 2 在真实 MySQL 验证 migration、唯一 CAS winner、event failure 原子 rollback、clear/expiry/purge、0005 downgrade/upgrade并 `continue`。P2 依次暴露探针问法、source-gap 注入方法和 durable 索引列 content-binding 三类问题；产品缺口修复后 attempt 4 `continue`，strict-lineage 加固后再次完整跨进程重验仍 `continue`。最终版本链=`1→3→5→7→9→11`，Compact=`d7a5fcf3...d098`、source=`1..5`，restart、extended correction、business Subgraph、role/version/competition、source gap/corruption、redaction均通过；provider calls/tokens=`0/0`，Agent synthetic 行最终=`0/0`。两项均为 exploratory/baseline-ineligible，不是 Formal Eval。
- **参考与适配**：定点复核 agentic-rag-for-dummies 的 token-trigger/summary+recent/orchestrator 重入通路，以及 LangGraph Memory/Context/Graph API 对 thread state、runtime context 与 model context 的分权。借鉴“先判规模、压缩后让真实节点消费、保留去重/执行 identity、用真实下游验证”的 seam；适配为 DataPilot typed Compact、MySQL task boundary、per-node allowlist/budget/fingerprint 和 paired behavior Gate。未照搬 LLM 自由摘要、MessagesState 全历史、RemoveMessage 保真假设、framework checkpointer/program counter、文本相似度代替安全与行为等价。
- **验证快照**：M48 final focused=`21 passed`，switch 修复跨 M43/M48=`6 passed`；M42～M48=`185 passed`、M31～M41=`237 passed`。真实隔离库 Alembic `current=20260827_0005 (head)`、`check=No new upgrade operations`，P1 完成 downgrade→0004→upgrade 对称验证；compileall、rehearsal、`git diff --check` 通过。Scenario v6 identity=`53dde9550b9e10c8565bdb4f6b6224cc6bfbb594140fa99ddd6fe5df8767beaf`，assurance=`4084e4289b0cee7e8cb9cabaf139f41eba761a4d111a90ce6d5705ba271ca22b`。首轮全仓 `1 failed, 660 passed` 暴露 switch lineage 并修复，最终独立后台全仓=`662 passed, 1 warning in 589.75s`；warning 仅既有 Starlette/httpx deprecation。
- **遗留/后续**：B6 与 Phase 4B technical integration 已完成，但尚不等于最终验收、RAG/LLM 质量提升、生产认证、外部 Tool exactly-once、性能/HA 或长期/跨 task memory。`datapilot_dev` 按禁区仍未迁移 0005。Pipeline 继续默认、Subgraph 继续 server-controlled experimental、无自动跨策略 fallback、reserve sealed/read0/not-run；后续只有形成明确失败簇或新质量 candidate 才另立有编号 plan。当前流程进入 finish-docs、人工演示与 `accept-module`。

> ⚠️ 注（2026-08-27，M49 修正）：上述“`datapilot_dev` 未迁移”和“进入最终验收流程”是 M48 收工时事实。M49 经用户授权已将默认开发库正常迁移至 0005、业务关键计数不变，并修复连续自然语言链与执行证据独立性；当前以 M49 Scenario v7/assurance v2 和 677 项全仓结果为最新技术收口证据。M48 v6/assurance 原件不改签，但不能再作为执行证据可信度的最高版本。

### [模块任务] M47 Phase 4B B5 Durable Task State（2026-08-26）

- **改动范围**：起始 commit 明确为 `db0c14548d1f3a6fd270560fd0440108e4a35493`，期间无模块提交。模块新增 B5 machine contract/manifest、closed-world TaskState v2 codec、adapter-neutral boundary、checkpoint/event ORM 与 Alembic `20260826_0004`、MySQL durable adapter、产品/API/Trace 接线、真实 MySQL Probe、restart/multi-worker rehearsal、Agent Scenario v5、报告与专项测试；同步修正 M1 表集合及 M43/M46 additive compatibility 断言。没有修改业务表、seed、Knowledge/RAG release、embedding/index、M46 rollout/reserve 或 M48 Context Compact。
- **关键记录**：用户对 G47-1/G47-2 均选择方案 A：产品默认 MySQL/InnoDB snapshot + typed event ledger，memory 仅 test 明示；active TTL 900 秒，terminal/clear/expiry 立即 scrub，24h 后 bounded purge，不新增应用层加密；真实 Probe 只写隔离库 `datapilot_m47_test`，禁止触碰 `datapilot_dev` 与业务数据。owner、tenant、active role、expected version、single-use claim token 与 TTL 共同进入数据库 CAS；switch 在短事务内原子退休旧 task/创建新 task；claimed crash 保守停止且不自动重放 Tool。当前合法 TaskState v2 可严格 round-trip，G47-3 migration registry 未触发。
- **真实 Probe 与实验结论**：P1 在切片 C 后、D 前按时执行并经一次 import-order 修复后 `continue`；最终真实 MySQL 双 session 唯一 claim、commit/switch rollback、active/claimed expiry scrub、过期 commit fencing 与 bounded purge 全部通过，清理 `5/13→0/0`。P2 在 E 后、F 前经三轮 fixture/断言修正后 `continue`；process A/B `version 1→3` restart-resume、双 worker 单胜者、旧版本拒绝、role/tenant 隐匿拒绝、claimed crash 保守停止和 clear scrub 通过，清理 `4/11→0/0`。两项 calls/tokens 均 `0/0`，均为 exploratory/baseline-ineligible 开发证据，不是 Formal Eval。
- **参考资料**：定点复核 DataAgent saver/GraphService 接线、ARAG `InMemorySaver + interrupt_before` 反例，以及 MySQL InnoDB locking、JSON 和 SQLAlchemy transaction/rowcount 官方文档。借鉴 adapter seam、短事务、数据库条件更新和显式 release；未照搬 Graph program counter、应用层伪 CAS、长事务、`SKIP LOCKED`、自由 JSON 或“有 saver 即 durable”的结论。
- **验证快照**：注释审计 12 个主要 Python 文件/112 个 symbol，非豁免缺失 0；最终 lifecycle 聚焦 `27 passed`，TTL/fencing 聚焦 `12 passed`，Phase 4B 受影响集合无 failure；Scenario v5 6/6、零 provider，identity `c1ad166376db7ecc4e49b6aa870b4967c37d0f0779eeeb521fe7daf9d66000af`。临时 SQLite metadata 的 Alembic current 为 `20260826_0004 (head)` 且 check 无新操作，compileall/diff check 通过。后台全仓真实执行 640 项为 `639 passed, 1 failed, 1 warning`，唯一失败是 M1 旧断言未计两张 M47 基础设施表；修复后该项独立 `1 passed`，故当前代码下 640 项均有通过证据，但不表述为同一次全仓零失败。warning 为既有 Starlette/httpx deprecation。
- **遗留/后续**：`datapilot_dev` 按用户禁区仍未执行 0004，产品 task runtime 启动前必须正常迁移；未证明外部 Tool exactly-once、生产认证、吞吐/容灾或 Agent 答案质量。M48/B6 应消费 durable typed event/checkpoint identity 构建有界 Compact，不得恢复 Graph/RAG program counter，也不得把 rows、正文、答案、Prompt 或无界历史写回 checkpoint。

### [模块任务] M46 Phase 4B B4 Bounded Agentic RAG与experimental rollout（2026-08-26）

- **改动范围**：起始commit明确为`08b0333`，期间有部分提交`417a788 M46-part1-20260826-160237`。模块新增内容绑定B4合同、Document Evidence Acquisition seam、Pipeline/Subgraph两个adapter、有界RAG子图、external requirement formation与专属proposal outbound、父子预算/Evidence重授权、Agent Scenario v4、API/Trace/Eval同源投影、paired runner/review和M46测试/报告；没有修改数据库schema/seed、active release、embedding/collection、Composer安全validator或客户端策略接口。
- **关键设计与用户决策**：RAG恢复循环放在一次父级Knowledge action内部，避免顶层Agent与RAG形成双循环；模型最多提出两个question-grounded atomic obligations，source-span/value/coverage/action/ACL/预算仍由确定性代码裁决。三代historical完成后，用户确认experimental rollout终局：Pipeline保持默认，Subgraph保留server-controlled experimental，不启用自动cross-strategy fallback；当前candidate不晋级，decision reserve保持sealed/read0/not-run。未来重开必须新假设、新candidate、新授权，仓库外todo固定Evidence run identity→Composer structured output→formation grounding的优先级。
- **真实证据**：P1 business纵向链`passed/continue`；D0的P0后经P0R=`passed/continue`。最终historical v3 `m46-historical-paired-20260826-164511`两臂各60 completed，Subgraph child projection 60/60完整，value-shape问题清零，answer-ready提高到26并新增43条Evidence。rollout评审将下一轮优化收敛到Evidence run identity、formation grounding和Composer structured output；当前candidate保持experimental，原始Gate、paired verdict及Probe时间线由Eval账本和模块notes保留。
- **参考资料**：依据`docs/phase4-reference.md`定点复核ARAG parent/child retrieval与conditional edge、DB-GPT structured references/evaluator，以及LangGraph Subgraphs/Graph API；借鉴私有子图state、显式映射、结构化引用和评测分层。未照搬自由LLM tool call、MessagesState大状态、framework recursion/checkpoint冒充业务预算或durable state、gold/title动作选择和失败后自动fallback。
- **验证快照**：注释审计23个代码文件/257个符号，缺失0；收口聚焦`57 passed, 1 warning`，兼容修复聚焦`26 passed, 1 warning`，compileall/diff check通过。首次全仓`621 passed / 5 failed`真实发现B4 typed failure扩散到M33/M34旧Pipeline，修复为仅B4 subgraph账启用；第二次全仓`625 passed / 1 failed`，唯一失败是未修改的M31 fault-injection在pytest临时目录`os.replace`触发Windows `WinError 5`，同项沙箱外独立`1 passed`。warning为既有Starlette/httpx deprecation；626项均有当前代码下通过证据。
- **遗留/后续**：未证明Subgraph总体正确率、Reliability、吞吐、多worker或默认收益；P3与真实decision reserve均未运行。M47/B5消费稳定TaskState/turn boundary、B4 termination/child ledger和最终rollout，只在任务边界持久化/恢复，不能恢复RAG Subgraph program counter。M46后续质量修复不属于B5，必须按仓库外重开包另立计划。

### [实验] M46/B4 historical Pipeline/Subgraph paired v2 仍为 no-go（2026-08-26）

- **范围与身份**：按用户精确授权运行 external `diagnostic_dev/full` 60 题 × Pipeline/Subgraph 两臂，logical run `m46-historical-paired-20260826-160237`，candidate `26636b5c...68c8`、B4 contract `8915f0f0...ddf7`；两臂各 60 次均 completed，paired manifest 为 `completed_pending_review`，reserve `f70c5fca...e505` 全程 sealed、未读取逐题内容。Pipeline artifact `b01fa4e3...bfc4`，Subgraph `7eb33e64...dc8a`，paired `88e263f4...a622`，comparison `4bfcea7d...e5bf`。
- **结果与失败结构**：Pipeline Gate `571/112/37`，Subgraph `375/126/219`，60 个 paired verdict 全部 `insufficient`；basic/core/hard passed 分别 `269→131 / 272→154 / 134→90`。formation v2 已把旧候选的 28 个 unsupported current qualifier 降到 0，但 Subgraph 仍为 45 contract failure、12 answer-ready、3 child projection missing；主要新失败簇为 value-shape 19、observe Evidence contract 15，12 个 answer-ready 又全部被严格 Composer 合同拒绝。最终 60 题均 no-answer，因此只能判定 historical `no-go/revise`，不能冻结 candidate、解封 reserve或切换默认。
- **Usage 边界**：Pipeline 已知 requests `113`、chat tokens `132841`；Subgraph 已知下限 requests `123`、chat tokens `102522`，但 3 条 child projection 缺失，且两臂 embedding tokens 均不可得，所以禁止将这些数字解释为完整总成本。
- **后续有界修复**：本地已把 `composer_output_invalid` 收敛为保留 child ledger 的 typed result；formation v3 对合法但错误的 value-shape 枚举使用服务端 deterministic expected shape 规范化；Evidence 异常只投影 allowlisted reason。B4 contract 更新为 `df8a96c4...1afe`，新 candidate `ab66f20d...2f78` 仅完成零 provider preflight，受影响回归 `61 passed, 1 warning`。它是新候选，不继承 v2 授权；是否再次运行 historical 或调整 M46 完成路线须另行决定，当前 Pipeline 继续默认、Subgraph 仅 experimental、reserve 继续 sealed。

> ⚠️ 注（同日最后一次 historical v3）：用户授权把 `ab66f20d...2f78` 作为最后一个 historical candidate；run `m46-historical-paired-20260826-164511` 两臂各60 completed、reserve sealed。v3 消除了 value-shape `19→0`，把 child projection补齐至60/60，并将answer-ready `12→26`；closed-set review据此把下一轮优化边界收敛到Evidence run identity、formation grounding和Composer structured output。当前candidate不晋级、不解封reserve、不再追加同类historical调参；用户随后已显式修订完成门并确认Pipeline默认/Subgraph experimental的rollout终局，原始Gate和paired数字仍由Eval artifact保留，详见上方M46模块档案。

### [模块任务] M45 Phase 4B B3 RAG failure funnel 与 action-level Evidence admission（2026-08-25）

- **改动范围**：起始 commit `7d254ff4...9ec9` 明确，期间无中间提交。新增四代 content-bound diagnostic campaign、RAG failure funnel/typed Observation、deterministic rewrite、same-document sibling expansion、受控 structured requirement proposal、procedure forward continuation、closed-world qualification/tamper validator、Probe/rehearsal、v1～v4 review 与 M45 tests；只在 `EnterpriseContextLoader` 增加只读 forward sibling identity seam。未接产品 B2 Loop/API、未改 active release、semantic/embedding/default、Composer、corpus/index 或 M46 reserve。
- **关键记录与用户决策**：首轮 deterministic trigger no-go 后，用户为 demo 效果确认 question + authorized Evidence 的受控 proposal；P4/P4R 仍分别暴露 schema/literal matching 与“模型认为 coverage 完整”的失败。用户随后确认 M45-H 方案 A：不再追加模型调用，而以默认关闭的 `procedure_boundary_v1` 在 signed procedure intent + authority forward unit 同时成立时准入 expansion。它只证明需要补上下文，不把 sibling 当答案事实；仍受 2 seeds、scan8/add4、同物理文档、双 ACL、duplicate/no-progress 与 stop 约束。
- **Probe 与证据**：P1 business rewrite passed；P2/P2C 失败推动 rewrite→expansion/sibling v2，P2D passed；P3/P4/P4R 的 no-go 全部保留。P4 使用 2 chat / 3877 observed tokens；P4R 另有 1 chat attempt，但 runner crash 导致 tokens/raw response=`unobserved`，未补发。P5 复用 P3 qst_0431 immutable Evidence，零 retrieval/embedding/chat/Composer，补入 2 条 forward same-document Evidence并 passed。模块累计 `8 embedding + 3 chat = 11` provider attempts。
- **最终产物**：v4 campaign `15cda06e...e708`，P5 safe `a3a4f7e8...4a72`，external v1.3 manifest `2d369472...d0f6`，final review `949a3b03...fbb4`=`go_for_M46`；query rewrite/context expansion 两卡 completed，reserve sealed。项目外 v1.0～v1.3 保存 private evidence，仓库只保存安全 review/hash。
- **参考资料**：定点复核 ARAG child/parent retrieval、conditional edge/去重与 DB-GPT structured references/evaluator。借鉴首次检索与恢复分权、identity 驱动 continuation、确定性 dispatcher；适配为 SQLite authority、typed EvidenceDelta、ACL 与预算。不照搬自由 LLM tool call、字符串 Observation、顺序 parent ID、默认全文展开、gold/title seed selector 或平台大状态。
- **验证快照**：注释审计 13 个 Python 文件/126 个符号，补写 25 个 docstring；compileall 通过；聚焦 `29 passed`；受影响 `54 passed, 1 warning`；后台全仓 `582 passed, 1 warning in 665.44s`。warning 为既有 Starlette/httpx deprecation。manifest SHA、artifact identity、safe/private lineage 与 reserve sealed 对账通过。
- **遗留/后续**：M45 只是 diagnostic action admission，不是产品 Agentic RAG，也未证明答案正确、总体质量或 Reliability。M46/B4 须另立 plan 接 Pipeline/Subgraph、父子预算与首次 sealed reserve A/B，并保留 proposal validator、procedure trigger、ACL/duplicate/no-progress/stop；当前不运行 Formal Eval。

### [实验] M45/B3 diagnostic campaign 到达 C5 no-go（2026-08-25）

- **范围与边界**：在隔离 diagnostic runtime 实现 B3 六层三态 funnel、deterministic focused rewrite、同物理文档 sibling expansion v2、action/budget/EvidenceDelta/qualification artifact 和离线复核脚本；没有接入产品 B2 Loop/API，没有修改 active release、Enterprise semantic 默认、embedding、Composer、corpus/index recipe，也没有读取 M46 sealed reserve。
- **用户决策与演进**：G45-1/G45-2 采用方案 A；P2 暴露单 rewrite coverage 不足后，用户确认 G45-3 的 `rewrite → expansion` 两步链；P2C 证明 immediate neighbor 不足后，又确认 G45-4 的同文档 bounded sibling scan（每 seed 最多 8 个 identity、最多 2 seeds、最多新增 4 条 Evidence）。旧失败 artifact 全部保留，后续 Probe 不冒充重验或覆盖。
- **真实 Probe 结果**：P1 business rewrite passed；P2 Round 2 找到 qst_0420 目标文档 fragment 但 rate/measurement coverage 未闭合；P2C immediate neighbor failed；P2D sibling v2 passed。P3 首次执行 qst_0431/qst_0461 时，两题 initial Evidence 都让 question-derived generic slots 显示完整，因而 expansion 不 eligible、rewrite 被拒且只允许 stop，均为 failed。campaign 累计 8 次 embedding provider attempt，零 chat/model/Composer、零 observed chat tokens；预算守卫阻止了 fallback 和额外调用。
- **结论与路线影响**：离线 review artifact `33efaf8f...9ea9` 为 `review_required/no_go`；continuation expansion card 通过，但 direct expansion card 未完成，所以 M45/B3 未完成、不得调用 `finish-module` 做完成收工，M46 不得开工。结果满足 G45-1 结构化 requirement/rewrite proposal 的硬重开证据信号，但不自动授权模型；若继续，须先由用户确认修订 M45 的 receiver、purpose、出站字段、模型、预算和新 Probe，且禁止 gold/reserve/答案事实进入 proposal。
- **证据与安全**：完整 probe 证据保存在项目外 `phase4b-rag-action-diagnostics/v1.0.0`，private manifest SHA-256 `467de737...c3ed3`；仓库只保存安全 review/failure slices/report。safe/private identity 与文件 hash、ACL 重授权、同文档边界、scan/add/chain budget、duplicate/no-progress 和 no-go tamper 均由 deterministic tests/rehearsal 核验；M46 reserve 仍 sealed。

> ⚠️ 注（同日 structured proposal 重开与 P4）：用户为 demo 效果选择 question + authorized Evidence 的受控 A2，新增 diagnostic-only Qwen proposal、strict validator 和 additive v2 campaign。P4 两题各一次，共 2 calls / 3877 tokens、零新 retrieval/embedding/Composer，但仍 failed：qst_0431 暴露 prompt 未声明 marker group 上限且失败 raw 未保留；qst_0461 proposal 正确识别 schedule 缺口，却因整句 literal marker 未匹配 sibling 的语义等价表述而没有 expansion preview。v2 review `ce0d7615...40af` 仍为 no-go，累计 provider attempts=10；当前不得自动重跑或启动 M46。后续若继续，最小候选是 proposal-only token-overlap、qst_0461 immutable 离线重放和 qst_0431 唯一一次新 proposal，须用户另行确认新 campaign/Probe。

> ⚠️ 注（同日 P4R 最小 repair 与 v3 最终 no-go）：用户确认 proposal-only token-overlap、完整 prompt schema、失败私有证据保留，以及 qst_0461 零 provider 离线重放后 qst_0431 唯一一次 revalidation。qst_0461 最终 expansion passed；qst_0431 transport 成功但本地 coverage validator 得到 `proposal_no_unsupported_requirement`，未执行 action。runner 未 catch 异常导致 raw response 与 token usage 未落盘，故只记已知 1 chat attempt、tokens=`unobserved`，禁止补发或估算为 0。recovered safe `6426219b...a949`，v3 review `8fb3cfad...14e4`=`review_required/no_go`，累计 `8 embedding + 3 chat = 11` provider attempts；M45/B3 未完成、M46/`finish-module` blocked。受影响回归 `50 passed, 1 warning`。后续若继续须由用户确认新的结构完整性 action trigger 与 plan 范围，不能把当前 campaign 再重验。

> ⚠️ 注（同日 M45-H 最终修正）：用户确认的默认关闭 `procedure_boundary_v1` 用 P3 immutable qst_0431 Evidence 完成零 provider P5，新增 2 条 forward same-document Evidence；v4 review `949a3b03...fbb4`=`go_for_M46`。因此上述 v3 no-go 仍是不可变历史 lineage，但不再代表当前模块状态；M45/B3 已完成技术收工，产品 Subgraph/答案净收益仍留给 M46。

### [小修] Live Dev Probe 诊断与证据时效口径（2026-08-24）

- 根据 M44 多轮真实修复经验，在 `runbook.md` 和 module plan 模板精简补齐：总体/子能力三态、失败层→根因假设→最小判别动作、实际 strategy/usage 记账、模块累计额度、事务数据恢复、禁止人为触发故障，以及核心行为改变后旧 Probe 失效。后续复核又将 plan/`finish-module` 的公共字段清单收敛到各自事实源，并明确收工后单次真实运行须另获授权、标记 `not-development-probe` 且不登记基线；未扩大 Live Dev Probe standing authorization、Formal Eval 或产品 runtime。
- 同日再补充“预注册为基线、允许授权追加”：runbook 第 1 条明确预注册 Probe 是计划基线而非上限，开发中计划外的真实失败/新假设可动态追加最小 Probe，但必须由 AI 主动向用户提出（场景/理由/链路/预算/额度关系/停止条件）并获授权后执行，同口径记录三态与开发决定；追加指新的最小判别场景，不是对同一场景重复抽样。`AGENTS.md` 增加对应短条款，plan 模板补追加口径。不改变 standing 额度、重跑禁令与 Formal Eval 分账。

### [实验] M44 defect repair Live Dev Probe 与 SQL repair A/B（2026-08-24）

- **范围**：M44 重开后先修复真实 MySQL 1305/DATE_TRUNC typed classification 与 API/Trace 脱敏，并登记精确 month bucket fidelity 等价；聚焦 deterministic `38 passed, 1 warning`。随后按用户授权比较服务端候选 A `deterministic_ast` 与候选 B `llm_enriched`，各运行一次真实 `/api/query` T1→T2、Qwen、MySQL 和事务内 Phase 4B seed；不触碰 T3～T5、RAG、held-out、reserve 或生产默认。
- **A 结果**：真实 repair 被触发，本地 AST 将 DATE_TRUNC 编译为 MySQL SQL，fidelity/Guard/执行通过并返回 7 月 `120000`、8 月 `180000`；但本次上游 QueryPlan/candidate 只含 `month/net_refund_amount`，没有 `diff/change_rate/60000`，所以产品 Gate 仍 failed。报告用量 5 calls / 20721 tokens，含旧 attempts 的 runner 累计 13 / 50152；Trace `71265284...5dead`。
- **B 结果**：初始 candidate 与增强 repair 都保留四列，但 repair action 重新生成的 QueryPlan 只要求两列，fidelity 将 `diff/change_rate` 判为 extra 并安全阻断。报告用量 5 calls / 21839 tokens，runner 累计 18 / 71991；最后已开始 response 越过 token cap 后未继续。Trace `2918edb5...b8f2`。这不是统计学 A/B，也不能把 B 归因为 prompt 不遵循；主要证据是 repair 前后计划合同漂移。
- **安全与观测**：两项 Response/Trace 均无 raw DB error，数据库均完整 rollback。另发现 repair LLM 成功返回后若在 fidelity/output Gate 失败，error span 漏写 `LLMCallEvidence`，使 action/artifact 少计真实 repair request/tokens，runner 的 `strategy_exercised` 也出现假阴性；因此 18 / 71991 只是报告下界，不是可信预算闭合证据。
- **路线影响**：production 仍保持 `llm_minimal`，A/B 均未切默认，M44 renewed finish 继续阻塞。下一步必须由用户决定是否扩展核心合同：repair 私有复用首次可信 QueryPlan/output snapshot、task comparison 注入服务端 required outputs，并补齐所有后置 Gate failure 的 usage/strategy Trace；确认前停止真实 provider 调用。artifact 位于 `.agent_work/temp/m44-pfix-candidate-{a,b}-20260824-01/`。

> ⚠️ 注（同日用户决策与 G3 实现）：用户选择收敛后的方案 A，只让 repair 私有复用首次可信 QueryPlanStep/candidate/issue、把 `deterministic_ast` 切为服务端默认并补后置 Gate usage/strategy；明确不为 T2 硬编码四列、不建设通用 required-output 平台。deterministic 聚焦 `40 passed`、新增合同单文件 `13 passed`、受影响兼容 `86 passed, 1 warning`。由于 G3 发生在 A/B 真实运行之后，最终代码仍缺对应 Live Probe，renewed finish-module 阶段 0 已退回开发并等待新的精确运行授权。

> ⚠️ 注（同日 G3 最终 Live Dev Probe）：用户另批 canonical T1→T2 一次、≤5 calls / ≤22000 tokens；实际 4 calls / 14298 tokens。T1 得到 `120000`；T2 正确 invalidation，并以合法 MySQL SQL 取得 `120000/180000`，但 QueryPlan 仍只要求 `month/net_refund_amount`，系统未计算 `60000` 就 `answer_ready`，故 Gate failed。初始 SQL 没有 dialect failure，repair 路径未触发而记 inconclusive；raw DB error 未泄漏、数据库 rollback。该重复结果把剩余问题收敛为独立 comparison completion 合同缺口；继续实现会改变 G3“不建设通用输出平台”的确认边界，用户决策前停止，不重复抽样。

> ⚠️ 注（同日 G4 用户决策与实现）：用户选择方案 A，在 M44 内新增窄 typed comparison completion：只消费服务端 `metric_comparison` requirement、TaskState 两期/metric 与已验证 SQL rows，确定性派生 delta/rate；异常形状或零基期不准 `answer_ready`。它不改 QueryPlan、dialect repair 或 Evidence identity，也不扩成任意公式平台。另修复 Trace `tool_observation` 白名单投影缺 return。focused `19 passed`、受影响 `108 passed`、全仓 `553 passed, 1 warning`。M44 既有 standing/精确真实额度已经耗尽，新的 G4 canonical T1→T2 Probe 已预登记但待用户确认独立 ≤5 calls / ≤22000 tokens，确认前不运行。

> ⚠️ 注（同日 G4 Live Dev Probe passed）：用户批准的新 `M44-PFIX-G4-1` 只运行 canonical T1→T2 一次，实际 4 calls / 15762 tokens。T2 API/Trace same-source 给出 120000/180000、delta=60000、rate=0.5 与 50% Answer，旧 Evidence invalidation、answer_ready、usage、raw-error 非泄漏和数据库 rollback 全部通过；Trace `6e2fc4a2...a54fa`，completion identity `41b577e...ecac9`。初始 SQL 已合法而没有自然触发 repair，故 G3 repair real path 仍记 inconclusive，不为展示 repair 追加调用。artifact 为 exploratory/baseline-ineligible，不登记长期基线。

> ⚠️ 注（同日 renewed finish 安全合同确认）：审计发现 runbook/plan 的“Trace 不保存 rows”与长期实现不一致：SQL 单路一直投影 `response.rows`，只有 Hybrid 显式清空。用户确认方案 B，冻结现行兼容合同：本地 SQL/task SQL JSONL 可保存已经 Guard/授权的 `columns/rows`；Hybrid Trace、action Observation、node Context 和 Scenario artifact 仍禁止完整 rows，Document/private Evidence/raw DB error/prompt/stack 禁区不变。该决策不改代码运行行为，只消除错误的文档承诺。

### [实验] M44 收工后 canonical task 真实 E2E smoke（2026-08-24）

- **范围与身份**：用户明确授权 M44 收工后执行一条 T1→T5 canonical 产品链，经过真实 FastAPI `/api/query`、Qwen `qwen3.7-plus`、MySQL 与 task runtime；分类为 `exploratory / baseline-ineligible / not-development-probe`，不是 Formal RAG Eval，也不追溯冒充 M44 开发期 Probe。只运行一个 sequence，不换模型/backend、不自动重跑、不触碰 held-out 或 M46 sealed reserve。
- **数据与用量**：因默认 `datapilot_dev` 没有 Phase 4B 8 月数据，runner 在同一未提交事务追加官方 profile seed，所有 turn 复用该 Session，结束后 rollback；新连接确认数据库前后均为 2026-07 30 rows / `19920` 且临时 Phase 4B rows=0。T1～T3 累计 8 provider calls / 32674 observed tokens；最后一个已开始的 T3 response 使累计 token 越过 30000，按纪律保留 usage 后停止，T4/T5 未运行。
- **结果**：Gate failed。T1 单月 SQL 成功并得到 oracle `120000`；T2 的 constraint delta 和旧 Evidence invalidation 正常，但真实 Qwen 生成 MySQL 不支持的 `DATE_TRUNC` 后直接 `unrecoverable/sql_execution_error`；T3 的两次有界 SQL Evidence action 选择正确，却被同类错误阻断。不能据此判断 T4 business Knowledge、partial answer 或 T5 correction 的真实效果。
- **根因与安全发现**：真实 `run_sql_tool` 对数据库异常返回 `safety_status=blocked/error_type=sql_execution_error`，Harness 的方言分类却要求 `safety_status=passed`，所以错误无法归一化为 allowlisted dialect issue，B2 repair seam 实际不可达。另发现 tool call 保留底层数据库异常文本，且 API Response 与 JSONL Trace 投影同一未脱敏对象，违反既有 raw DB error 禁止外露合同；此前 deterministic fake 只证明控制合同，没有覆盖真实 SQL Tool 错误形状。
- **路线影响**：M44 deterministic 技术收工事实不改写，但 canonical T1→T5 真实产品链尚未闭合。M45 前应先另行授权一个聚焦 defect patch：统一真实 SQL 错误的安全 typed projection、接通 allowlisted repair、切断 API/Trace raw error，并增加 real-shape regression；代码修复后只重验最小受影响 T2/T3。报告见 `eval/reports/m44/m44-post-module-e2e-smoke-20260824-01.md`，原始 artifact 位于 `.agent_work/temp/m44-post-module-smoke-20260824-01/`，Trace SHA-256 `05fa65b9...e6e59`。

> ⚠️ 注（同日 M44 repair Probe）：typed classification/repair bridge 与公开 API/Trace 脱敏已修复并通过真实链；后续 A/B 又暴露 repair 重新规划导致前后 output contract 漂移、comparison QueryPlan 输出不稳定和后置 Gate 漏计 repair usage。旧条目的修复建议已执行，但 canonical T2 仍未闭合。

### [小修] 开发期 Live Dev Probe 真实效果验证纪律（2026-08-24）

- **影响面**：所有后续模块的 module plan、开发切片、真实调用授权、过程 notes 与 `finish-module` 门禁；不改变产品 runtime、默认模型或既有 Eval 基线。
- 用户确认建立 pytest/deterministic → Live Dev Probe → Formal Eval 三层验证。今后 module plan 必须提前判断真实探针是否适用，并写清 Probe ID、场景、产品链路、观察事实、三态结果、预算、停止条件、切片时点和正式 Eval 建议。
- Live Dev Probe 获长期 standing authorization：默认每模块 2～4 个 canonical/public/diagnostic-dev 场景、每场景首次 1 次、总 provider calls≤8、observed tokens≤30000；具体修复落盘后可在总额度内对最小受影响场景额外重验 1 次并保留前后 attempt。它优先经过真实 API/caller/task/Tool/MySQL/Milvus/LLM/Response/Trace，只作 exploratory、baseline-ineligible 开发证据，不登记长期基线、不与正式 Eval 分母混算，也不得为通过重跑或换模型/backend。
- 自动授权明确排除 held-out、M46 sealed reserve、all/full、Reliability 重复、大规模 generation、新数据出站类别、数据库 reset、索引重建和 active/default 切换。Formal Smoke/Core/Reliability/held-out/基线候选继续需要用户精确授权；本次只修改工作流文档和 `finish-module` skill，没有运行真实 provider、Eval 或改动产品代码/默认 runtime。

> ⚠️ 注（同日用户复核后修正）：初版虽要求开发期 Probe，但主要硬门仍落在 `finish-module`，存在全部拖到收工才首次执行的漏洞。现已改为切片级阻塞门：首条纵向链路可运行后即执行，结果必须在下一依赖切片前形成 `continue/revise/stop` 决定；`finish-module` 只审计开发时点证据，缺失时记录 `development_probe_missing` 并退回开发，不能靠收工补跑冒充开发期验证。

> 生效边界：自 2026-08-24 后新建的 module plan 起强制执行，当前路线即 M45 起；M44 及更早模块不追溯补造开发期证据。若旧模块重开并发生实质性代码修改，新修改部分适用本纪律。后续 Formal Eval 或新模块 Probe 可以提供新的最终效果证据，但不能改写旧模块当时的开发过程事实。

### [模块任务] M44 Phase 4B B2 Evidence-driven Bounded Decision Loop（2026-08-24）

- **改动范围**：新增 additive B2 contract/manifest、TaskState v2、typed Requirement/Action/Budget/Consumption/EvidenceDelta/Progress/Termination、服务端 Knowledge Runtime Resolver、独立 task-only LangGraph Loop、Agent Scenario v3、rehearsal/report 和四组 M44 测试；task envelope 改接一次深 Loop invoke，legacy 非 task Harness、M42 v1 与 M43 v2 validator 保持兼容。B2 contract identity `a808b321...d485b`。
- **用户决策与预算**：G44-1～G44-4 均选 A。普通 API 保持 M44A Enterprise semantic，task requirement 由服务端 closed-world scope 选择 business/external；next Action 完全确定性，decision model calls/tokens=0；父预算最多 3 Evidence actions/deep Tools、SQL 3、Knowledge 1、每 requirement repair 1、retrieval batch 1、candidate 5、selected/generation-visible 3、model calls 6、observed tokens 24000；SQL repair 使用独立最小 outbound purpose。未选的结构化模型 proposal 方案 B 只进入 `AI_CONTEXT` 防遗忘账本，不是 M44 未完成项。
- **关键实现与修正**：Controller 在每次 action 前按 typed requirement/依赖、duplicate/no-progress 和实际消费重新裁决，超额消费保留账本后稳定停止。跨 turn active Evidence 覆盖旧 requirement；T3 由 reason Observation 的正向 Evidence 增量驱动 product SQL，T4 形成 SQL→business Document Hybrid，T5 correction 显式 invalidation 后重取 SQL/document。业务检索缺 required basic 时停止 `budget_exhausted/required_coverage_incomplete` 且不重复 query。精确 `DATE_TRUNC` 执行错误仅允许一次最小 repair，prompt 不含 Schema、raw DB error、rows 或 stack，修复结果重走 QueryPlan validation、SQL fidelity、Guard 与执行。
- **安全投影与 Eval**：API、JSONL Trace 和 Scenario v3 从同一 Loop/turn facts 投影 action attempts、budget、termination、knowledge runtime 与 actual-node Context v2；action/Context/v3 不保存 rows，SQL 单路 JSONL 则沿用 Guarded rows 兼容投影，Hybrid 清空完整 rows。raw task/thread ID、Document 正文、private Evidence、prompt、raw DB error、stack 或 Thought 均不保存。v3 rehearsal artifact `63c9483...ac700`，T3/T4/T5、repair once、negative skip 共 6/6，external calls=0；它是 deterministic 控制/安全证据，不是质量基线。
- **参考与适配**：定点复核 ARAG conditional edge/state/nodes、DataAgent dispatcher/repair 回边和 LangGraph Runtime/conditional edge/recursion limit。借鉴 typed state 回边、固定 dispatcher、execution key 去重和实际 Context；适配为 DataPilot closed-world action、三层业务预算与 fail-closed Evidence；不照搬 LLM 自由 tool call、字符串 Observation、平台大状态、人审/Python executor 或用框架 recursion limit 冒充业务预算。精确坐标见 `docs/notes/m44-plan.md` 与 notes。
- **验证快照**：最终聚焦 `57 passed, 1 warning`；deterministic rehearsal 6/6、external calls=0；后台全仓 `539 passed, 1 warning in 599.47s`，exit 0。compileall 与 `git diff --check` 在代码冻结点通过，技术档案写入后再次复核。warning 为既有 Starlette TestClient/httpx deprecation。
- **边界与后续**：未运行真实 provider、真实 repair showcase、RAG Eval、held-out/all 或 sealed reserve；未实现 B3 recovery action、B4 RAG Subgraph、B5 durable state、B6 Compact。下一模块 M45/B3 只能基于已保存 Observation 诊断并准入预注册 action；M46 前 reserve 保持 sealed。数据库 schema/seed/指标、embedding/Milvus snapshot、业务 active release、默认模型与历史基线均未改变。

> ⚠️ 注（2026-08-24 收工后真实 smoke 修正）：deterministic fake 证明了 repair 与安全投影的控制合同，但没有覆盖真实 `run_sql_tool` 的数据库错误形状。真实路径因 `blocked`/`passed` 条件错位无法进入 dialect repair，且 raw DB error 可进入 API/Trace；在聚焦修复和最小真实重验前，不能把本条外推为 canonical T1→T5 产品链闭合。详见本文件顶部同日 `[实验]`。

### [实验] M44A Enterprise semantic external dev Smoke（2026-08-24）

- **范围与身份**：用户明确授权 RAG smoke，按 runbook 唯一执行 external `diagnostic_dev/smoke` 9 题各一次；run `m44a-rag-external-semantic-smoke-20260824-023039`、artifact `4bfff9d...5346d` completed，exit 0，无 resume/重跑、lexical fallback、held-out/all 或 reserve 访问。runtime 为 semantic `9aec12...e20`、manifest `22c573...97b`、Qwen embedding 1024、既有 Milvus collection/unit-set；运行前 preflight ready。
- **自动结果**：9/9 HTTP 200、Composer 9/9 成功、retry0、usage `19033` tokens。Gate failed，required `92/16/0`、advisory `18/9/0`；primary triage `5 passed / 4 retrieval`，gold candidate/selected/generation-visible/cited 均为 `5/9`。qst_0016/0047/0181/0420 在 candidate 阶段漏 gold，但仍基于错误材料形成 complete answer。
- **人工复核**：artifact + 9 checkpoint 哈希验证通过，闭集 verdict `2 pass / 7 fail`。qst_0019/0386 pass；四个 retrieval 漏失题均 fail；qst_0461 漏关键清理规则并混入无关安排，qst_0431 命中双 gold 但完整步骤不足，qst_0318 精确开始时间错误。
- **候选对比**：与 2026-08-23 post-fix lexical smoke 只按 10 个预注册 runtime 字段做 candidate compare，自动 `1 win / 5 tie / 3 loss`、required `96/12/0→92/16/0`、tokens `20288→19033`；人工 `3/6→2/7`，唯一 verdict 退化为 qst_0461。两侧均为单次 generation、非 Reliability，且 runtime 字段共同变化，因此不能做单组件因果归因或声称 semantic 稳定更差。
- **结论与证据**：本次结果没有 semantic 质量胜出证据，也表明单题 C6 不能外推 smoke；但不改变用户确认的 semantic 产品默认和 fail-closed 合同。本 run 不自动登记正式长期基线。artifact/report/triage/review/verdict/reviewed/compare 见 `eval/reports/m44a-rag-external-semantic-smoke-20260824-023039*` 与 `m44a-rag-external-semantic-smoke-vs-lexical-20260824-compare.json`；后续稳定判断需独立 Reliability/候选计划和授权。

### [模块任务] M44A EnterpriseRAG-Bench Milvus 产品运行链路（2026-08-24）

- **改动范围**：起始 commit `098bd6014fb6cad648eed17197e5a71b31f25c15`。新增 API/Eval 共用的 closed-world Enterprise runtime resolver、FastAPI lifespan 与 `/health/rag`、Milvus semantic adapter 冷启动/强身份门、external 精确 Scenario 入口、preflight 脚本、Trace/artifact additive identity 和 M44A 测试；历史 API 合同测试改为显式注入 deterministic 业务 RAG fixture。没有 ORM/Alembic/seed、业务 22 条 release、semantic snapshot 或 Phase 4B owner 变化。
- **用户决策与默认合同**：M44A 插在 B1/B2 之间但不占里程碑，M44–M48 仍对应 B2–B6，M46 reserve 继续 sealed。用户确认 Enterprise 产品 API/external Eval 默认 semantic；lexical 只作显式历史 baseline。semantic 配置、provider 或 Milvus 不可用时 RAG 失败关闭、零 Evidence/Composer，不回退 lexical 或业务小语料；SQL 与 `/health` 仍可用，`/health/rag` 返回 503。应用不自动启动 Docker、建库、reset 或重建索引。
- **实现与身份**：SQLite profile `e8783fe...fa2` 继续作为正文/Evidence authority，Milvus 只选 unit identity。resolver 强制核对 profile/corpus/unit recipe、semantic manifest `22c573...97b`、semantic `9aec12...e20`、embedding `dashscope/qwen3.7-text-embedding/1024`、collection `datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89` 及 unit-set `17d5af...905f`；冷启动严格 load→load state→unit-set query。共享只读 SQLite/Milvus client 受锁保护并幂等关闭；API、Trace 与 Eval 从同一 safe projection 取运行身份。旧 lexical artifact 对新增字段按预注册 optional `None` 兼容，不回写、不改签。
- **真实 C6**：用户只授权 `diagnostic_dev/qst_0386` 恰好一次。run `m44a-rag-external-qst0386-20260824-c6` completed，artifact `0a5bc40...c9647`，required `12/0/0`、Gate passed；semantic candidate→selected→generation-visible→cited 为 `5→3→3→1`，Qwen attempts=1/retry0/2054 tokens，人工语义 verdict pass。自动 advisory exact-fact 下限仍失败并保留；没有第二次运行、lexical fallback、held-out/all 或索引写入，因此只证明真实向量产品链闭合，不是 semantic 质量基线。
- **参考与适配**：定点复核 WrenAI source/derived-index seam、GustoBot vector-store/tool workflow、DB-GPT structured references、DataAgent best-effort replace 反例，以及 FastAPI lifespan、Milvus load/load-state 官方合同。借鉴 source/index 分权、稳定 workflow seam 和 readiness；适配为 SQLite authority + Milvus 候选 + Evidence/citation 强身份门；不照搬自动 reset/rebuild/watch、字符串 source、best-effort replace 或降级 fallback。精确坐标见 `docs/notes/m44a-plan.md` 与 notes。
- **验证快照**：聚焦 `28 passed, 1 warning`；RAG/Eval 回归 `177 passed, 1 warning`；Harness/API/Phase 4B 回归 `96 passed, 1 warning`；最终全仓 `517 passed, 1 warning in 609.32s`。compileall、两个 CLI help、`git diff --check` 通过；真实 preflight 两次 ready，最终 10.48 秒且零 embedding/Composer transport。warning 均为既有 Starlette TestClient/httpx deprecation；两次 sandbox basetemp `WinError 5` 均在获批沙箱外重跑闭合。
- **边界与后续**：历史 M34 @20 仍显示当前 dense snapshot 不胜 lexical；产品默认切换来自用户对“真实向量 RAG”的合同选择，不是质量优越结论。单题 C6 不外推 60/180、Reliability、吞吐或多 worker。下一模块仍是 M44/B2 独立 plan；新 embedding/recipe/Hybrid/rerank 或默认切换必须形成新 identity、证据和用户确认。

### [实验] M43 后真实 Qwen 交互验证：比较类 QueryPlan 不稳定与超时调整（2026-08-23）

- **场景与边界**：M43 技术收工后，用真实 Qwen `qwen3.7-plus` 在默认 MySQL legacy 世界通过 `/api/query` 交互复现 canonical T1→T2。这不是正式 eval run（无 run_id/manifest/artifact），不登记基线，也不进入 `eval-baselines.md`（按该账本规则，运行事故/外部服务异常不作独立记录）。
- **比较类 QueryPlan 不稳定**：同一 T2“查询 2026-07 和 2026-08 的实际净退款金额，并计算差额和变化率”4 次尝试 3 种失败——2 次 45s 读超时（`read operation timed out`）；1 次生成 PostgreSQL 方言 `DATE_TRUNC('month', …)`，MySQL 报 `1305 FUNCTION datapilot_dev.DATE_TRUNC does not exist`（prompt 已要求 MySQL 兼容语法，模型未遵守）；1 次 QueryPlan 结构非法（`ORDER BY` 别名 `month` 未在 `output_expressions` 绑定）被 M10 自检以 `plan_validation_failed` 在碰库前拦截。成功两次总 latency `105.3s` / `43.3s`；单月 T1 在 45s 内稳定成功。
- **超时调整**：本机 `.env` 增加 `LLM_TIMEOUT_SECONDS=120`，避免比较类 QueryPlan 被 45s 误杀；config 默认仍 45、retry0 不变。
- **两个世界再次印证**：默认 MySQL legacy 世界 7 月净退款为 `19920`（即 M42 登记的 103 条 6 月 `processed_at` 尾巴），canonical `120000/180000` 只在显式 `profile_alias="phase4b"` 隔离副本成立；M43 task 机制（delta/invalidation/Context/版本）在两种数据世界与四种失败路径下均按合同工作。
- **路线价值**：四种失败分别死于客户端超时、数据库方言、计划自检三层，实证纵深防御；“执行失败 → 观察错误 → 修正重试”正是 M44/B2 Observation-driven Loop 的输入场景；`DATE_TRUNC` 方言错误是 Text2SQL 方言自检/修复课题（P5 质量项）的候选证据。

### [模块任务] M43 Phase 4B B1 Task runtime 与自然多轮 v1（2026-08-23）

- **改动范围**：起始 commit `8ae217c8904dfe808c32b346028bff251bbf2f7d`。新增 additive B1 contract/manifest、通用 `TaskDelta → TaskState` 状态机、Evidence invalidator、进程内 task boundary、deterministic Turn Understanding、四类 node Context、安全 task turn、Scenario artifact v2、rehearsal/report 与 4 组 13 项测试；同一 `/api/query` 只在 nested `task` envelope 存在时进入 agent task family，并增加独立 task clear。M42 v1 与 legacy 请求不改签、不切默认。
- **用户决策与核心合同**：用户确认 G43-1～G43-3 均选方案 A：M42 v1 只读并新增 v2；task envelope 对新 family 严格 closed-world，legacy 顶层继续兼容；首版理解只用本地确定性规则和保守澄清，零新增模型/provider/outbound。每个 accepted task turn 只允许 0 或 1 次既有安全深 Harness；clarification/cancel/clear/pre-rejection 为零 Graph，M44 的 Observation-driven 多动作 Loop 未提前实现。
- **关键实现与修正**：B1 contract identity `383fbf5...e9d32`。TaskState 顶层只含 goal/constraints/questions/requirements/route/Evidence/termination 等通用字段，不把退款/月/channel 做成业务专用 state；canonical T2 的省略年份只从已确认 prior state 继承。约束修正会让旧 SQL Evidence 显式 invalidated 后重查；cancel/clear/switch 同样失效旧 Evidence。switch 在 manager 同一把锁内退休旧 task 并签发 generation=1 新 task，禁止旧约束/Evidence 串线。owner+tenant、TTL、version、claim/commit 与错 owner/未知 task 不可区分的失败都收敛在独立 `phase4b-in-memory-task-boundary-v1`，并明确不是 durable。
- **Context/Trace/Eval**：Turn Understanding Context 记录 prior state；route/SQL 使用执行前 fingerprint；controller 才接触本轮新 EvidenceRef，均有 allowlist/source identity/field budget/input fingerprint，且不保存 rows、文档正文或完整历史答案。API、JSONL Trace 和 `phase4b-agent-scenario-artifact-v2` 从同一 task delta/state transition/evidence validity/lifecycle/invocation 事实投影；deterministic artifact `cc9f696...b27c92` 的 8 项检查全部通过，external calls=0。冻结 SQL oracle仍为 July `120000`、August `180000`、delta `60000`、rate `0.5`，不是新质量基线。
- **参考资料与适配**：按 roadmap/reference 定点复核 ARAG GraphState/Graph/summary-rewrite 节点以及 DataAgent KeyStrategy/Graph 接线。借鉴显式 state merge、节点最小输入和主状态/执行状态分权；不照搬 MessagesState 全历史、LLM 自由 rewrite/summary、扁平大 state、开放循环或 `InMemorySaver` 冒充 durable。精确源码坐标和适配表见 `docs/notes/m43-plan.md`。
- **验证快照**：M43 聚焦 `13 passed, 1 warning`；M35–M43 受影响回归 `117 passed, 1 warning in 109.43s`；rehearsal 8/8、零外部调用；最终全仓 `500 passed, 3 skipped, 1 warning in 584.22s`，exit 0。compileall、`git diff --check` 通过；warning 为既有 Starlette TestClient/httpx deprecation。首次 sandbox 聚焦命令因 pytest basetemp `WinError 5` 未形成代码结论，获批沙箱外重跑后闭合。
- **边界与后续**：M43 只完成 B1 的单次深执行自然多轮底座，不代表 B2 Loop、B3 recovery、B4 RAG Subgraph、B5 durable state 或 B6 Context Compact 完成；M46 reserve 继续 sealed。active RAG release/retrieval/Composer、默认模型/embedding、数据库 schema、legacy seed/runtime 均未改变。下一步须为 M44/B2 独立调查并制定 module plan，不能把当前 single-call task runtime 宣称为完整 Agent Loop。

### [模块任务] M42 Phase 4B B0 前置包与 sealed Agent Eval 决策集（2026-08-23）

- **改动范围**：起始 commit 明确为 `f3cc1912a2ab1e9b87fbc3f57d4adb1cdf03df40`。新增 `engine/phase4b/`、`domain_pack/phase4b/`、Agent Scenario/reserve Eval 合同、安全 manifest、M42 rehearsal 报告、两个构建/复核脚本和 6 组测试；兼容性修改仅涉及 caller fixture 的可选 tenant、seed 的显式 profile 入口和 `AGENTS.md` 目录树。项目外另创建 `phase4b-agent-eval/v1.0.0` immutable asset；仓库不保存题面/gold/绝对路径。
- **关键记录与用户决策**：用户确认 G1–G6 均采用方案 A：独立 additive seed profile、最小 `ops + customer_service` caller、gold-first 单次默认 business retrieval、新建 Hybrid operator 合同且不改 legacy、60 题双审 sealed reserve、项目外 versioned immutable store。这样比升级 canonical seed、扩角色、挑必过题、改写 M38、复用已看题或把 gold 入库更能保持历史可比性、授权边界和 decision set 未污染。M41 的一次执行、closed-world、三态、review hash 与安全投影纪律继续沿用，但 artifact/基线不原位修改；M42 新建 `phase4b-agent-scenario-v1`。
- **实现与新发现**：`phase4b-b0-contracts-v1` identity 为 `6543883...aae6f`；显式 seed profile identity `9c49407...00673`，7/8 月真实 SQL 净退款为 `120000.00 / 180000.00`，oracle `be813a8...57ef80`，星型/宽表一致且保留 2 条负数冲销。首次构建发现 legacy 6 月 refund `processed_at` 尾巴会使 7 月多 `19920`；没有用 `REF-P4B-*` 过滤伪造产品口径，而只在新 profile 隔离副本内 retime 103 条 spillover，legacy 默认不变。business gold-first Observation `e6bc5fa...aab99` 如实记录默认 lexical 只取回 quality、漏掉 basic；零 provider、零参数/语料/ACL/release 修改。
- **Eval 与 reserve**：Agent skeleton identity `b303d4d...52982`，能力矩阵把 M43–M48 均标 unavailable。60 题 reserve identity `f70c5fc...e505`，分布 `20/20/20`，core 8 道、hard 20 道多文档；首次解封 owner 为 M46，M34/M41 historical 只作排除/回归，不作 candidate。逐文件 hash 与 source pool 已只读复验；没有运行真实 LLM、remote embedding/Milvus、held-out 或 reserve candidate，因此没有新质量基线。
- **参考资料**：按 `phase4-reference.md` 定点复核 Wren/DataAgent 的 source/index/state seam、ARAG 的 Graph/state/tools/Eval skeleton、GustoBot multi-tool/finalize 和 DB-GPT Tool/Resource/Eval 分层。借鉴内容身份、状态/执行闭集和一次执行后评分；不照搬 watcher 充当原子发布、参考项目 TaskState 字段、开放循环、notebook 简单平均或模型输出作为安全事实。具体 reference ID 与适配表见 `docs/notes/m42-plan.md`。
- **验证快照**：M42 全聚焦 `19 passed`，注释修正合同子集 `12 passed`；M1/M27/M31–M34 `179 passed, 1 warning`，M35–M41 `82 passed, 1 warning`；最终沙箱外全仓 `487 passed, 3 skipped, 1 warning in 566.30s`。首次全仓在 sandbox basetemp 因 `WinError 5` exit 1，保留为环境故障并以同命令/新 basetemp 重跑，不改实现或缩范围。warning 是既有 Starlette/httpx deprecation；compileall、diff check 与 trailing-whitespace 检查通过。
- **遗留/后续**：M42 只完成 B0，不实现 TaskState、Loop、Hybrid runtime、RAG Subgraph、durable state 或 Context Compact。M43/B1 应直接消费本模块合同/fixture；M45/B3 从真实漏选 Observation 开始且只能用预注册动作/预算；M46/B4 才能按污染账本解封 reserve。active business release、默认 lexical/Composer/model、legacy runtime 与 M34/M41 baseline 均未切换。
  ⚠️ 注（2026-08-24 / M44A）：这里的“默认 lexical 未切换”是 M42 当时事实；M44A 后仅 Enterprise 产品 API/external Eval 默认改为 semantic，22 条业务 release 的 deterministic lexical 和历史 M34/M41 artifact 仍不变。

### [小修] Phase 4B 参考项目里程碑下沉与反走马观花门（2026-08-23）

- 重读 `docs/phase4-reference.md`，并回到 WrenAI source/index/watch、DataAgent Graph/checkpointer/replacement、ARAG Graph/state/tools/chunk/compact、GustoBot multi-tool/finalize 与 DB-GPT Tool/Resource/Eval 实际源码核对输入、状态、输出、停止及保证边界。
- `docs/phase4b-roadmap.md` 的 B0–B6 每个里程碑现都有就地参考项目小结，将 Eval 骨架、TaskState/Context、顶层 Loop、RAG 失败诊断、Subgraph、durable checkpoint 与 Compact 分别对应到精确 reference ID、借鉴 seam 和不照搬边界。
- 新增适度的源码阅读门：不强制通读整仓或固定文件数，但禁止只看 README/analysis/搜索片段；module plan/notes 必须能复核当前问题、真实调用/状态通路、规模与代表性差异、保证边界、DataPilot 适配与验证方式。特别固化 M29–M33 虽逐模块读过参考源码，仍因 11/22 条短知识无法诊断大 corpus 问题、最终需 M34 补底座的教训。
- 本次仅更新路线与历史文档，未修改代码、Eval 合同、运行默认、reference ID 定义或任何 active identity；未运行 Tool/LLM/embedding/Eval。

### [实验] M41 external dev Smoke + Basic post-fix 真实运行（2026-08-23）

- 用户授权“执行一次 rag eval smoke、basic”，按 runbook 唯一映射为 external `diagnostic_dev` Smoke 9 题与 Basic 21 题各一次；两个独立 run 均 exit 0、manifest/artifact completed，无 resume/重跑，未运行 held-out/core/hard/reliability/full/all。
- Smoke `m41-rag-external-smoke-20260823-154101`：Gate `failed`，required `96/12/0`；triage `4 passed / 2 selection / 2 citation / 1 retrieval`；9 provider responses / `20288 tokens`。来源哈希复验后的 AI reviewer verdict `3 pass / 6 fail`，其中自动 triage passed 的 qst_0318 仍因上线日期错误判 fail。
- Basic `m41-rag-external-basic-20260823-154101`：Gate `failed`，required `215/25/12`；triage `12 passed / 4 retrieval / 3 product_runtime / 1 selection / 1 citation`；21 provider responses / `47814 tokens`。AI reviewer verdict `9 pass / 9 fail / 3 insufficient_evidence`；3 个无答案均为 provider 有响应但 Composer 结构合同失败，不是 transport unavailable。
- 两套共 30 requests / `68102 tokens`，重叠 qst_0016/0019/0047 的 verdict 均一致（fail/pass/fail），但 3 题单次重叠不能冒充 Reliability。结果继续显示自动链路通过不等于语义正确，错材料/漏召回和 Composer 严格结构合同仍是主要缺口。
- artifact/report/triage/review/verdict/reviewed 证据位于 `eval/reports/m41-rag-external-{smoke|basic}-20260823-154101*`，30 checkpoint/Trace 位于 `.agent_work/temp/m41-rag-external-checkpoints/`。两条均不自动登记正式长期基线，不改变默认 lexical/Composer/model，120 held-out 保持锁定。

### [实验] M41 external dev core 首条 post-fix 真实运行（2026-08-23）

- 用户授权“执行一次 rag eval core”，唯一映射为 external dev core：25 题 / 25 执行、`diagnostic_dev`、Qwen `qwen3.7-plus`、60s/retry0、public benchmark policy。run ID `m41-rag-external-core-20260823-151649`，artifact identity `fe498be7c4a4beff01e76fef2baed27651cc3ddefe4ca831e16bd1b3f3338fe8`，manifest/artifact/report/triage/checkpoint 全部闭合。
- 结果：Gate `failed`，required `211 passed / 58 failed / 31 not_observed`；usage `53106 tokens`（25 requests / 24 provider 成功）；AnswerFlow latency p50 `8852ms` / p95 `11973ms`；primary triage `9 retrieval / 7 product_runtime / 1 selection / 1 citation / 1 provider_or_support / 6 passed`。
- 失败明细：5 题 `composer_output_invalid`（Composer 坏结构，运行后修正的分类如实生效，下游 funnel/answer 标 `not_observed`）；3 题 `composer_unavailable`；9 题 retrieval 主因（gold 四层全缺但 `answer_present` 通过，漏召回后仍完成回答）。
- 逐题语义 verdict（AI reviewer，闭集覆盖 + 来源哈希校验，与自动 Gate 并列）：`4 pass / 13 fail / 8 insufficient_evidence`。fail 主体是“检索错文档→答偏”（qst_0199/0200/0268/0282/0289 等）和“已引用 gold 仍拒答”（qst_0198/0279）；8 例 insufficient 全部是无答案的 Composer/provider 坏结构题；4 例 pass（qst_0386/0457/0461/0462）全部检索命中 gold。自动 Gate 通过的 6 题中有 2 题 verdict 仍 fail，再次证明自动断言不能代替语义正确性。
- 结论：首条 post-fix dev core 快照再次确认 lexical 漏召回是首要质量瓶颈，且 Composer support/坏结构拒绝造成 8/25 无答案；不改变 M39 P6 `no_go`、默认 lexical/Composer/model，不自动登记正式长期基线，120 held-out 未运行。
- 执行环境插曲：首次后台启动时 PowerShell 日志重定向被沙箱拒绝（零 provider 调用、无任何 run 状态），获准 `danger-full-access` 后同 run ID 重试成功；不属于换 ID 重跑。
- 证据：artifact/report/triage/review/reviewed/verdicts 位于 `eval/reports/m41-rag-external-core-20260823-151649*`；25 checkpoint/Trace 位于 `.agent_work/temp/m41-rag-external-checkpoints/<run-id>/`。

### [小修] M41 RAG Eval 用户入口去歧义（2026-08-23）

- business catalog 只有 5 个业务合同场景，故将旧 smoke/core/diagnostic/reliability selectors 合并为唯一 `business`（5 题各 1 次）；保留 `--scenario` 单题入口和场景内部诊断分类，历史 Smoke artifact 不改名、不改签。
- external `diagnostic_dev` 改为 CLI 安全默认。runbook 约定裸 smoke/basic/core/hard/reliability/full 均表示 external dev；只有明确说 `held-out` 才触碰 120 题封存集，从而消除 business core 与 external core 的歧义。
- 本次只改评测入口、selector、测试与状态文档，未运行真实 Tool/LLM Eval，也未改变产品 RAG runtime、题目、评分器或既有基线。
- 验证：两个 CLI help 通过；M41 聚焦 `13 passed, 1 warning in 1.75s`，warning 为既有 TestClient/httpx deprecation；未重复执行全仓 pytest。
- 后续按用户确认将 RAG Runbook 分层重组，而非删成入门简版：前部新增自然语言映射、完整执行闭环、当前固定路径/identity 与 self-contained PowerShell 命令；中后部完整保留生命周期、fixed-route 边界、失败分层、语义 Review、strict/candidate Compare、历史回看和数据维护路由。补齐 held-out 分层题数、同 run 超时/恢复检查和完成后汇报合同。
- 文档重组零 provider 调用；四个 CLI help、当前路径/API Key 脱敏检查、immutable dev/held-out suite 数量和 Markdown/diff check 均通过，未重复运行 pytest。

### [模块任务] M41 补充：external 难度套件与候选 A/B compare（2026-08-23）

- external catalog 升级为 `phase4-rag-external-product-v2`：完整 180 题共享一个 identity，新增只由原生题型与单/多文档决定的 difficulty `basic/core/hard=64/74/42`；difficulty、60/120 partition 与 suite 三轴分离，题面/gold 仍只读 immutable dataset。
- 冻结 dev suites：smoke `9`、basic `21`、core `25`、hard `14`、reliability `6×3`、full `60`。Smoke/Reliability 只允许 dev；held-out/all 必须显式选择且真实运行仍需独立授权。报告只统计 RunSpec 选中题，并按 difficulty/partition/type/cardinality/source 输出失败层、assertion 三态和 funnel gold。
- compare 升级为 `phase4-rag-e2e-compare-v2`：默认 runtime 完全一致的 strict repeat；候选模式只允许 CLI 显式登记的 runtime 字段变化，其他协议/题集/scorer/metadata 漂移继续失败关闭。输出逐 execution `win/loss/tie/mixed/insufficient`、首失败层迁移、difficulty assertion、provider usage 和 AnswerFlow latency；自动结果不替代人工 correctness。
- 旧 `m41-rag-external-dev-20260822-01` 保持不可变、仍为 pre-fix candidate，未补造 difficulty 或升级为基线。本次零 provider 调用，未运行 120 held-out、未切 lexical/Composer/model/普通 API 默认。
- 验证：真实 immutable catalog/suite 只读闭合；旧 artifact compare-v2 self-check 为 `60 tie`；聚焦 `19 passed, 1 warning`，M31–M41 回归 `234 passed, 1 warning`，全仓 `467 passed, 3 skipped, 1 warning in 492.31s`。warning 为既有 TestClient/httpx deprecation。

### [实验] M41 external 180 题分层接入与 60 dev 真实产品链路（2026-08-23）

- 直接复用 M34 immutable 180 question set、gold、原生 `question_type × source_signature × document_cardinality` 与冻结 60 dev / 120 held-out split；不复制题面。旧 Answer + lexical retrieval artifacts 已零 Tool/LLM 投影为逐题分层历史报告，旧证据未保存的产品层与 selected/generation-visible 明示 `not_observed`。
- 新增 external catalog、eval-only fixed-RAG Router、M34 profile AnswerFlow factory 和产品 E2E CLI；每题经过 `/api/query → Harness → RAG Tool → external AnswerFlow → Qwen`。fixed route 不评测自然 Router，business 与 external 结果分账，普通 API/Router/Composer、业务 release、external lexical 默认均未改变。
- 用户授权后只运行冻结 dev 60：`m41-rag-external-dev-20260822-01` completed，60 requests / 137299 tokens；required `524 passed / 136 failed / 0 not_observed`，Gate `failed`；primary triage `24 passed / 20 retrieval / 7 product_runtime / 5 citation / 4 selection`。candidate/selected/generation-visible/cited gold 为 `35/30/30/24`。未运行 120 held-out、Judge 或重试。
- 运行暴露 5 个 provider-success Composer 坏结构被适配器误记 `harness_contract_failure`。完成 artifact 保持不可变并标记 pre-fix candidate；后续代码已将其归为 Tool/Composer observed failure、新增 `composer_support_valid`，下游按证据标 `not_observed`。因协议 identity 已变化，禁止把未来 run 与本 run 伪装成严格同协议比较。
- 验证：运行后修正 M41 聚焦 `14 passed, 1 warning`；M31–M41 受影响回归 `229 passed, 1 warning in 62.53s`；全仓 pytest exit `0`，`462 passed, 3 skipped, 1 warning in 517.37s`。warning 为既有 TestClient/httpx deprecation。
- 证据：artifact/report/triage/review 位于 `eval/reports/m41-rag-external-*`，60 checkpoint/Trace 位于 `.agent_work/temp/m41-rag-external-checkpoints/`；闭集人工语义 verdict 已完成并通过 artifact + 60 checkpoint 哈希复验，结果 `18 pass / 26 fail / 16 insufficient_evidence`。自动分层结果与人工语义结果并列，互不改写。

### [实验] M41 business RAG 首次真实 Qwen Smoke（2026-08-22）

- 用户明确授权 `smoke` 后只执行一次 `m41-rag-smoke-20260822-01`：2 个 Scenario / 2 次产品请求，最多 1 次 Qwen generation；未扩大 Core/Diagnostic/Reliability，未重跑、未调用 LLM Judge。
- resolved runtime：`phase4-rag-e2e-v1`，business release `7d0d0937...409a`、corpus `1927eb53...7857`、`knowledge-deterministic-lexical-v1`、Qwen `qwen3.7-plus`、60s/retry0、`phase4-rag-eval-business-generation-outbound-v1`。两题均完整经过产品 Harness；普通 API 默认未改变。
- 结果：run `completed`，自动 required `23 passed / 0 failed / 0 not_observed`，Gate `passed`。质量退款题唯一 provider attempt 成功，prompt 660 + completion 352 = 1012 tokens；答案逐项符合 `refund_policy_quality@2026-08-13-r1`。五年保修题 candidate 为 0，安全兜底且 provider 调用为 0。离线 review 来源哈希验证通过，人工 verdict `2 pass / 0 fail / 0 insufficient_evidence`。
- artifact identity `674de0f...a461`，artifact SHA-256 `5fd72b...ba64`；report、triage、review/verdict/reviewed 文件位于 `eval/reports/`，两份 checkpoint/安全 Trace 位于 `.agent_work/temp/m41-rag-checkpoints/m41-rag-smoke-20260822-01/`。
- 解释边界：登记为当前有效首次 Smoke 快照，不自动升为正式长期基线；单次两题不能证明 Core、多文档、Reliability 或整体业务质量。下一步是否登记基线或扩大运行由用户决定。

### [模块任务] M41 Phase 4 RAG 真实产品链路 EvalOps 与诊断体系（2026-08-22）

> ⚠️ 注（后续 G2）：本条“未运行真实 Smoke”是技术开发收工时状态；随后用户已授权并完成上方 `m41-rag-smoke-20260822-01`，其窄结果不改变本条模块范围与默认行为边界。

- **范围说明**：本条按当前索引写入 Phase 4B 历史文件，但模块语义是 Phase 4 RAG Eval 缺口补完，不执行 Phase 4B Agent Loop、TaskState、RAG Subgraph、durable checkpoint 或 Context Compact。起始 commit 未由用户指定；开工时 HEAD 为 `1348148`。改动覆盖 API/RAG Tool 的 eval-only Composer seam、独立 RAG Eval contracts/catalog/selectors/runner/scorer、artifact/report/triage/review/compare、M34 historical importer、聚焦测试和 runbook/state 文档。
- **核心合同**：每个 Scenario/replicate 恰好一次 `/api/query → caller → turn → Router → Harness → RAG Tool → business AnswerFlow → API/Trace` 产品请求，形成共享 `RAGExecutionEvidence`；所有 scorer/report/triage/review/compare 零产品重跑。`phase4-rag-e2e-v1` 冻结 RunSpec、release/corpus/retrieval/Composer/model/policy/caller identity、连续 checkpoint 前缀、closed-world assertion plan 和 Gate；transport unavailable 下游为 `not_observed/inconclusive`，模型坏结构/support 为 observed failure。
- **用户决策**：G1 采用 deterministic oracle 下限 + 强制人工 review，不引入 LLM Judge。实施中发现 M34 Composer 只允许 `public_benchmark_document`，不能用于非公开 business Knowledge；给出“独立 eval-only policy”与“不允许业务文档出站、只保留 fake”两案，建议前者。用户确认方案 1，遂新增 `phase4-rag-eval-business-generation-outbound-v1`：只允许 active release 中经过 caller/ACL/Gate 的 `role_restricted_policy_text` / `metric_definition` generation context，security/未知类别网络前失败关闭；普通 API、`phase4-outbound-v1` 和 deterministic Composer 不变。
- **诊断闭环**：catalog 单一事实源提供 smoke/core/diagnostic/reliability；runner 支持显式 `--resume` 且只接受合法 checkpoint 连续前缀；funnel 覆盖 product runtime、retrieved、selected、generation-visible、provider/support、cited、answer 自动下限。review 对 artifact/checkpoint 绑定 SHA-256，verdict 不改自动 Gate；strict compare 拒绝 runtime/protocol 漂移；M34 importer 验证原 artifact identity 后明示为 external direct AnswerFlow historical，不冒充产品 E2E。
- **参考资料**：借鉴 ARAG-EVAL“先保存实际 answer/context 再评分”和 DB-GPT retriever/answer evaluator 分层；未照搬 notebook 简单平均、失败样本跳过、scorer 重跑 pipeline、空结果统一计零、RAGAS/单一 LLM 分数裁决。EvalOps 生命周期纪律来自 DataPilot M27，但 SQL/RAG artifact 与业务语义保持分家。
- **验证**：M41 聚焦 `11 passed, 1 warning in 1.53s`；M27、M31–M40 与 M41 受影响回归 `205 passed, 1 warning in 73.67s`；全仓后台 pytest exit `0`，`459 passed, 3 skipped, 1 warning in 508.88s`。warning 均为 Starlette TestClient/httpx deprecation，不阻塞。四个 CLI help、compileall、diff check 通过；现存 M34 180 题 artifact 离线导入匹配 SHA-256 `75592af...99fa` / identity `d9fa2b...b41f`，180 calls、10 unavailable，零 Tool/LLM。
- **遗留/边界**：未运行真实 business RAG Qwen smoke、LLM Judge、remote embedding/Milvus、LangFuse Cloud、真实 Hybrid LLM 或 M34 重跑，因此没有 M41 质量基线。真实首次运行仍需用户精确授权 selector、run ID 与调用范围，建议 smoke 后停门；unavailable 不得自动换 ID 重跑。若回到 Phase 4B，仍须按 roadmap 另立 B0 module plan，不能把 M41 诊断体系冒充 Agent 能力完成。

### [实验] M41 首次真实 LLM smoke（2026-08-22）

> ⚠️ 注（M41 RAG Eval 补完）：该条是更早的 **M27 Text2SQL** smoke，只有 run ID/当时任务编号使用 `m41`；它不是 `phase4-rag-e2e-v1` business RAG smoke，不能满足本模块 G2。真正的 M41 business RAG Smoke 后续已以上方 `m41-rag-smoke-20260822-01` 独立完成，两者不得混算。

- 按用户一次授权，使用当前默认 `LLM_PROVIDER=qwen`、`QWEN_MODEL=qwen3.7-plus`、M27 v3 `smoke` selector 执行恰好一次；未扩大到 core/stress/reliability，也未重复运行。
- run：`m41-real-llm-smoke-20260822-01`；4 个逻辑 Scenario、4 个 physical attempts。`june_gmv` 与 `active_products_top10` 到达 LLM generation，但均为 `external_unavailable / network_error`；`unsafe_drop_orders` 与 `missing_product_supplier_rejection` 在确定性安全/计划合同处拒绝并通过对应 required assertion。
- 结果：run `completed`，Gate `inconclusive`（required passed=2、failed=0、not_observed=7；logical completed=2、external unavailable=2）。本次没有成功的模型输出可用于 Text2SQL 质量结论，`inconclusive` 不能当作通过或失败。
- artifact/report：`eval/reports/m27-artifacts/m41-real-llm-smoke-20260822-01.json`、`eval/reports/m41-real-llm-smoke-20260822-01.md`；run spec hash `bd3ce4aefd4ccebfad5ecd364548aeec87deb49ee931d80000c2b6139e98d07f`。
- 遗留：需另行诊断 provider/network 出站问题；未经新的明确授权不得重跑或扩大 suite。此次真实模型 smoke 与 M35–M40 deterministic contract/assurance Eval 分账，不改默认模型或路线。

### [小修] Status 文档标注路线升格（2026-08-22）

- `docs/notes/phase4-rag-capability-status.md` 头部与第 12 节标注：方案已于 2026-08-22 经用户确认升格为 `docs/phase4b-roadmap.md`，第 1–11 节转为演进记录；修订记录同步补一条。仅文档标注，不改变任何运行事实或路线内容。

### [小修] 新建 Phase 4B 历史档案并切换索引写入目标（2026-08-22）

- `docs/state/CHANGELOG_INDEX.md` 的当前写入目标由 Phase 4 切换为 Phase 4B，并新增阶段索引行：Phase 4B（M41 至当前）→ `change-history/phase4b.md`；Phase 4 行范围收口为 M29–M40。
- `change-history/phase4.md` 转为历史档案（Phase 4 收口于 M40），不再承接新条目；其中 2026-08-22 的 Phase 4B 立项相关既有条目（候选方案审查小修、Roadmap 正式立项模块任务）保留原位，不迁移。
- 本次只重组 changelog 路由，不改变任何运行配置、Eval 结果、历史结论或 `docs/phase4b-roadmap.md` 内容。
