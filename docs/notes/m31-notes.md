# M31 可信证据与安全发布开发素材

> 本文是 M31 开发过程事实源。实现中的决策、踩坑、验证证据和收工交接随进度即时补充，不在收工时凭记忆重建。

## Implementation checklist

- [x] 固化开工基线、变更范围和现有远程调用/投影反向清单
- [x] 实现 trusted caller 与明确标注的 production/demo/test/unverified 来源边界（C1）
- [x] 实现文档 ACL/用途/revision 的确定性 AuthorizationDecision 与安全拒绝投影（C2）
- [x] 实现 receiver × node purpose × data class × fields 的默认拒绝 OutboundDecision（C3）
- [x] 登记现有 Text2SQL 远程用途，证明不自动获得 Document Evidence 权限（C3）
- [x] 实现 Document/SQL typed Evidence、EvidenceRef、安全投影及四阶段 ledger（C4）
- [x] 实现代码分配 citation slot 与确定性 Citation Validator（C5）
- [x] 实现 immutable release bundle、hash/closed-world 校验、原子 active pointer、启动重载与显式回滚（C6）
- [x] 建立独立 `phase4-v1` contract/security Scenario、一次执行共享证据和 closed-world artifact 校验（C7）
- [x] 补齐聚焦合同/安全测试和候选 release manifest/inspect/diff 证据
- [x] 执行 G3 方案 A：全部 required 验证通过后激活当前 11-entry release；失败则不移动 active pointer
- [x] 运行模块聚焦验证、受影响回归、全仓确定性测试、compileall 与 `git diff --check`
- [x] 按 `finish-module` 完成四轮注释审查并固化本文件
- [x] 按 `finish-docs` 更新 state/changelog/dev-log 并完成三份文档交付门

## 开工基线与已确认选择

- 日期：2026-08-13。
- Git 基线：`7f2ca21`（M30 已验收）；开工时工作树只有未跟踪的 `docs/notes/m31-plan.md`，它是用户已确认的当前模块计划。
- M30 staged catalog：11 条 usable entry；corpus identity `abdc9aed2d4ee118e0b93890dad5b3b5b80c0b163f997ec275d1c92b3e99a858`；build identity `c5e6cf17b95573ee1deeb5b7f40620f53724c362e2f5f9be61214be2bbbf23a6`。
- 用户已确认 G3 **方案 A**：在 M31 required 验证全部通过后，把上述 11-entry candidate 正式激活；如果验证失败，保持旧 active 不变并先定位问题。
- 用户已确认发布形态为版本化 immutable release bundle；authority source 仍是 `domain_pack/kb_docs/` 与 `domain_pack/metrics.yaml`，release 只是可重建运行时投影。
- M31 严格停在 Phase 4 P1：不实现 Knowledge Tool、检索、生成、公开 API、Graph/Router/Hybrid、远程 Knowledge adapter 或 Knowledge Milvus。

## 开工调查结论

### 参考复核

- DB-GPT 的 Resource 能返回 chunk + structured references，而新 Tool 只返回编号正文和错误文本；借鉴“内容和身份一起贯穿”，不照搬纯文本 Observation、文件名/score 即 citation 的做法。
- GustoBot 的 `_collect_sources/finalize` 从多个可选 metadata 字段猜 source，且在最终答案阶段拼接；将其作为 citation 身份断裂反例，不照搬 Tool 内答案生成、级联 fallback 或字符串 sources 去重。
- ARAG 会保存实际 Tool context 并去重；借鉴“记录生成器真正看见的内容”，但 M31 用 typed Evidence identity/ledger，不以字符串 context 作为事实源，也不引入 Graph/loop/compact。
- WrenAI 证明 source/derived 分离以及 reindex 成功后才推进 watcher fingerprint；DataPilot 使用正文 hash、完整 bundle 校验和原子 pointer，不照搬 path/size/mtime fingerprint，也不把 watcher 状态说成原子发布。
- DataAgent replacement 是先加新、后删旧并 best-effort 清理；DataPilot 不把它当事务或回滚保证，而是保持旧 active bundle 不变，只有新 bundle独立重载通过才切 pointer。

### 当前入口分类（待实现前继续定点核对）

- legacy SQL：`QueryRequest.user_role` 和 Streamlit 选择仍服务现有 SQL 路径，不能转化为文档可信身份。
- Phase 4 新路径：M31 新模块只提供 caller/ACL/outbound/Evidence/citation/release 深接口，不接 `/api/query`。
- 远程 receiver：Qwen/DeepSeek chat、SiliconFlow/DashScope schema embedding、LangFuse Cloud、Eval score/judge；M31 只建立并测试明确登记矩阵，不新增真实远程调用。
- 长期投影：默认只允许 stable refs/hash、状态和白名单 reason；不写 Document 正文、标题、未授权存在性或 SQL rows。
- 短期投影：测试/debug 只能通过显式接口取得，M31 不提前固定生产保留期。
- 历史只读：M27 v3 Scenario/artifact/report/review 不修改；Phase 4 使用独立 `phase4-v1` family。

## 关键决策与过程记录

- **出站接线边界**：chat transport 由 `llm_call` 把 `query_plan/sql_generation` 精确用途传到真实 client；Qwen/DeepSeek 仅允许 `text2sql_prompt` 的 `prompt/system_prompt/model`。Schema embedding transport 只登记 `schema_text`；相同 receiver 的 `document_evidence`、answer composer、judge 等仍因缺策略拒绝。LangFuse Cloud 当前 payload 更宽且默认关闭，本模块不伪造安全放行，也不扩成 Cloud 脱敏改造。
- **caller 防提升**：`unverified_request_caller` 会校验声明角色是否合法，但把 `resolved_roles` 固定为空；因此请求体写 `admin` 仍不能通过文档 ACL。production authenticated 只建立 verified identity 的适配 seam，不实现 JWT/OAuth provider。
- **ACL 两次检查**：Document Evidence 只能由 `pre_selection` allow 构造；推进 `generation_visible` 时必须提供同轮 `pre_generation` allow。拒绝公开投影统一为 `not_authorized`，不返回 document key/title/revision/命中数。
- **Evidence/citation**：Evidence ID、citation slot 都由代码按 run/authority/claim 生成；阶段账本不可变且只允许单步正向迁移。Validator 一次校验 slot、run、stage、revision/content identity、anchor 和入模前授权，任一失败整体返回 `citation_invalid`，不产生部分可信引用。
- **注释审查中的合同补强**：同一份 generation-visible Evidence 可以合法支持多个 claim，citation 逐条保留但 ledger 只推进一次；AuthorizationDecision 必须与当前 document safe-ref 精确绑定，不能拿另一份文档的 allow decision 冒用。
- **release lifecycle**：bundle identity 覆盖完整正文投影、corpus/build、policy 和 contract；同 identity 文件只接受逐字节相同内容。active pointer 独立带 hash/current/previous/G3 approval，候选写入和重载成功后才原子 replace。启动时 active 损坏失败关闭；rollback 必须重新与当前 staged authority/policy 对账。
- **G3 方案 A 已执行**：用户已在本轮明确选择 A。前置 candidate manifest、`phase4-v1` required Gate 和跨模块回归全绿后，正式激活 release `4e86bdddbf15ca7ce1284f27b7507fedac70a69c098f5a1952cf6e71001e95a7`；pointer identity `8bf9e82aaa44386ce9d9d1a624b99c6cfce8781848a352aba122e18694225cc9`，首次发布所以 `previous=null`。独立重载的 pointer/bundle 与写入对象完全一致。
- **故障注入发现**：pointer replace 的注入异常会保留旧 pointer；active bundle 篡改不会自动 fallback previous；revision 被撤销/authority 改变时 rollback 被拒绝。这些是 C6 的预期保守语义，不是待修 bug。
- **切换恢复补强**：审查时增加“replace 已破坏目标 pointer 后才抛异常”的更强故障注入；activation 会恢复精确旧 pointer，rollback 切换失败同样恢复回滚前 pointer。只处理 `active.json`，不删除 bundle 或 authority。
- **Eval 可重复性补强**：最初 8 个 contract Scenario 共用 runtime 目录，执行顺序会让第二次同目录运行看到上次 active 状态。现改为 candidate 与每个 Scenario 各自隔离子目录；同一 runtime root 连续运行两次 artifact 完全相同。
- **循环导入踩坑与修正**：最初为了方便把 M31 Evidence/release 全部 re-export 到 `engine.rag.__init__`，受影响回归立即暴露 `governance → catalog → rag package → evidence → governance` 循环。修正为聚合入口只保留 M30 catalog，M31 调用者从 `engine.governance`、`engine.rag.evidence`、`engine.rag.release` 精确导入；这也符合 deep module 的窄接口和单向依赖原则。
- **旧 fake client 兼容踩坑**：首次给 LLM client 透传 `node_purpose` 后，M4 只接受 `prompt` 的 fake 同时不认识 `system_prompt/node_purpose`，Python 错误文本先点名 `system_prompt`，旧兼容分支没有继续降级，导致 legacy API 被误判 blocked。修正为只对“未知这两个新增参数”的 TypeError 分两级降级；真实 client 内部 TypeError 仍不会被吞掉。

## 验证证据

- 首轮 caller/ACL/outbound + Evidence/citation + release/fault injection 聚焦测试：`26 passed in 0.66s`。命令使用项目 Python 与 `--basetemp .agent_work/temp/m31-focused-1`；无网络、warning 或 skip。
- 首轮受影响回归在 collection 阶段失败：新增聚合 re-export 引发循环导入，未执行测试；已按上条过程记录修正，后续用新 basetemp 重跑，不把该失败隐藏为通过。
- 第二轮受影响回归：`59 passed, 3 skipped, 1 warning`，但 M4 legacy fake-client case 1 条失败；定位为新增 `node_purpose` 的兼容分支问题，不是 SQL/ACL 默认行为变化。修复后定点重跑 M4 + M25 + M31 outbound 为 `29 passed, 1 warning in 11.35s`。warning 为既有 Starlette/httpx deprecation。
- G3 candidate 实跑：11 entries；corpus `abdc9aed...`、source build `c5e6cf17...`、release `4e86bdd...`；`phase4-v1` artifact `052a5f36...`，required `12 passed / 0 failed / 0 not_observed`，Gate `passed`。
- G3 前置跨模块回归：M31 + M30 catalog/Text2SQL isolation + Phase3A pipeline + legacy Trace/API + M27 foundation/review，`93 passed, 1 warning in 138.69s`。warning 为既有 Starlette/httpx deprecation。
- 正式 activation：`active=true`、current `4e86bdd...`、previous `null`、entry count 11；启动重载 `restart_match=true`。
- 注释/正确性审查补强后的 M31 聚焦：先 `44 passed in 1.01s`，完成 Scenario 隔离与同目录重复测试后为 `45 passed in 1.24s`。
- 最终 contract 复算：active release 与当前 staged corpus 一致；artifact `197e0d62...`，required `12 passed / 0 failed / 0 not_observed`，Gate `passed`。早期 artifact `052a5f36...` 是补齐 caller/runtime identity 前的过程证据，不作为最终快照。
- 最终模块专项：`45 passed in 1.23s`；随后 `compileall app engine eval tests` 通过，`git diff --check` 无 whitespace error。Git 仅提示 4 个既有 tracked Python 文件下次写入会按配置把 LF 转成 CRLF，不是内容错误。
- 最终全仓确定性回归：`276 passed, 3 skipped, 1 warning in 481.28s`。3 skip 为既有 Milvus/远端 embedding 条件跳过；warning 为既有 Starlette/httpx deprecation；未调用真实 LLM、远程 embedding、Milvus 或 LangFuse Cloud。
- 最终身份对账：staged/active 都是 11 entries、corpus `abdc9aed...`；active release `4e86bdd...`；Text2SQL queryable 13 tables；Schema Retrieval 186 docs/hash `6b67606d...`。
- 身份对账首条一次性命令因漏传 `build_schema_documents(domain_schema)` 必需参数而报 `TypeError`；读取函数签名后改为注入 `load_domain_schema()`，同一检查成功。未改变代码或运行默认。

## 模块总结与文件清单

M31 把 M30 的 staged catalog 推进成了一个可安全消费但尚未接 RAG 的 P1 地基：caller 来源先确定信任，文档在候选/入模前双重授权，所有远程调用先过精确 outbound policy，Document/SQL 使用 typed Evidence 和四阶段账本，citation 只能指向同轮真实入模 Evidence；发布采用不可变 bundle 和原子 active pointer。用户批准的 11-entry corpus 已正式 active，首次发布没有 previous。

本模块文件范围：

- 治理与现有 transport 接线：`engine/governance.py`、`engine/nl2sql/{generator,llm_call}.py`、`engine/schema_retrieval/embedding_provider.py`。
- Evidence/citation 与发布：`engine/rag/{evidence,release}.py`、`engine/rag/__init__.py`。
- 运行时发布投影：`domain_pack/kb_releases/active.json`、`domain_pack/kb_releases/releases/4e86bdddbf15ca7ce1284f27b7507fedac70a69c098f5a1952cf6e71001e95a7.json`。
- Eval：`eval/phase4_contracts.py`。
- 测试：`tests/test_m31_{governance,evidence_citation,release,phase4_contracts}.py`。
- 文档：`docs/notes/m31-{plan,notes}.md`；`finish-docs` 随后更新 state/changelog/dev-log。

## 决策档案

### G3 正式发布

- 方案 A：required Gate 全绿后激活 11-entry bundle。收益是 P1 发布闭环，P2 可只读 active catalog；风险是本地派生 bundle 保存正文，未来真实敏感内容需要更细 retention/delete 流程。
- 方案 B：保持 staged。风险更低但 P2 不能使用默认 corpus，主线暂停。
- 建议与最终选择：计划建议 A，用户明确选择 A；最终在 12/12 required 与 93 项跨模块回归通过后执行，current `4e86bdd...`、previous `null`。

### 发布存储形态

- 已确认候选包括 authority 多 revision 重构、只存进程内 snapshot、版本化 immutable bundle。
- 建议与最终选择：用户在计划阶段选择 immutable bundle。它比内存态可恢复，比立即重构 authority revision 范围更小；代价是要治理派生正文文件。M31 实际路径为 `domain_pack/kb_releases/`，这是 C6 未冻结的本地实现细节，不承诺未来多实例存储形态。

### 出站接线

- 可选做法是只写策略表不接 transport、一次性重构所有远程/Cloud 路径，或在当前集中 chat/schema embedding seam 强制检查并保持 LangFuse Cloud 关闭。
- 选择与理由：采用第三种，落实计划要求且不扩大为 Cloud 脱敏模块。现有 Text2SQL chat/schema embedding 明确放行既有数据类别；任何 Document Evidence/新节点用途缺规则即 deny。LangFuse 当前更宽 payload 不获放行，默认仍关闭。

## 注释审查小结

- 第 1 轮文件/类/函数：补齐四个生产模块和 Eval family 的职责、输入输出、失败语义；测试文件用模块说明和场景化命名表达合同。
- 第 2 轮复杂逻辑：重点复核 caller 防提升、ACL 双检、Evidence 单步迁移、citation 多 claim 复用、canonical hash、atomic pointer 恢复、rollback revalidation 和 artifact closed-world 对账。
- 第 3 轮关键路径：补充“为何不能聚合 re-export”“为何同文档 citation 只推进一次”“为何切换失败只恢复 active.json”“为何每个 Eval Scenario 隔离目录”等设计原因。
- 第 4 轮一致性：术语统一为 staged/candidate/active、pre-selection/pre-generation、generation-visible/cited、current/previous；没有把 fixture Gate 表述成端到端 RAG 或语义 citation support。

## 参考资料与适配结论

- `DBGPT-RESOURCE/TOOL`：借鉴 structured reference 随内容贯穿；不照搬纯文本 Tool Observation、异常正文或文件名 citation。
- `GUSTO-WORKFLOW/VECTOR`：作为末尾拼 sources、collection metadata 不足以授权的反例；不照搬 Tool 内回答、级联检索和 fallback。
- `ARAG-STATE`：借鉴记录生成器真实看到的 context；DataPilot 改成 typed Evidence ledger，不引入 Graph/loop/compact。
- `WREN-INDEX/WATCH`：借鉴 authority/derived 分离和成功后推进；不用 mtime fingerprint 充当 corpus identity，也不把 watcher 当原子发布。
- `DATAAGENT-REPLACE`：借鉴先形成 replacement 再移除旧对象的顺序；DataPilot 用完整 bundle + atomic pointer，明确拒绝把 best-effort cleanup 说成事务。

## Handoff

- 当前 active Knowledge release：`4e86bdddbf15ca7ce1284f27b7507fedac70a69c098f5a1952cf6e71001e95a7`，11 entries，corpus `abdc9aed...`，previous `null`；启动必须通过 `load_active_release()`，损坏时失败关闭，不自动 fallback。
- P2 调用顺序：从 active bundle 取得 entry → trusted caller → `authorize_document(..., pre_selection)` → `make_document_evidence` → 选择后 `authorize_document(..., pre_generation)` → ledger 推进 `generation_visible`；最终 citation 用代码 slot + `validate_citations`。P2 不解析 Markdown、不读 legacy `knowledge_docs`、不接触 release 文件布局。
- 新 Knowledge remote adapter 不得复用现有 Qwen/schema embedding 放行：必须新增精确 receiver × node purpose × data class × fields 规则，并按计划重新核对 provider 政策与用户决定。
- `phase4-v1` 当前仅是 8 个 deterministic contract/security Scenario、12 required assertions；它证明 caller/ACL/outbound/Evidence/citation/publish 合同，不证明 retrieval、答案质量或开放语义支持度。P2 在独立 family 上滚动增加 retrieval/answer contracts，不修改 M27 v3。
- 仍未实现且不得误报：Knowledge Tool、retrieval/index、Evidence Gate、Composer、公开 citations/API、Graph/Router/Hybrid/thread、真实 RAG Eval、Cloud 脱敏/恢复。
- 首次发布没有 previous，当前调用 rollback 会稳定返回 `rollback_previous_missing`；只有未来第二个 release 激活后，且 previous 仍与当前 authority/policy 完全一致，才允许显式 rollback。
- `finish-docs` 需把 active release、outbound 默认拒绝、phase4-v1 Gate、276 项回归和 P2 下一切片同步到 `AI_CONTEXT_CHANGELOG`、`AI_CONTEXT`、`dev-log`；README 不更新。

## finish-docs 执行清单

### dev-log 交付门（必须执行）

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

### 三文档交付门（必须执行）

- [x] `AI_CONTEXT_CHANGELOG.md`：本次完整模块有新的 `###` 条目，包含改动范围、关键记录、参考资料、验证快照、遗留/后续。
- [x] `AI_CONTEXT_CHANGELOG.md`：改动范围已经通过 `git status --short` 和对应 diff 命令核对，覆盖已提交、已暂存、未暂存和未跟踪的模块文件；文档中的归并范围与原始文件清单一致。
- [x] `AI_CONTEXT_CHANGELOG.md`：如果用户确认过关键方案，已经完整记录每个主要选项的做法、影响、适用条件和风险，以及 AI 的建议和用户最终选择；没有用“选择 A/B”代替决策上下文。
- [x] `AI_CONTEXT.md`：只同步影响续接的当前事实，不复制完整历史；当前模块、默认配置、最新基线和活跃边界均准确。
- [x] 涉及评测口径、文档入口、归档迁移、默认行为、安全边界或长期兼容边界时，已在 changelog 或当前事实摘要中留下可追溯记录。
- [x] 已检查本模块的新结论是否推翻或修正旧结论；如有，已经在旧条目原位添加 `⚠️ 注` 并指向本次新结论；如无，也已实际检查并确认不需要添加。
- [x] 三份文档刚写入的章节均已按照「阶段 5：收尾确认」完整回读，确认无截断、乱码、标题层级错误、事实夸大或未经 notes 支持的结论。

### finish-docs 检查结果

- 素材来源：完整固化后的 `docs/notes/m31-notes.md`，并用当前会话记忆、`AI_CONTEXT`、近期 changelog 与 Git 文件清单交叉核对；关键素材完整，未退回 `finish-module` 做二次补齐。
- dev-log 交付门：15/15 逐项检查并通过；M31 章节完整回读，无截断、乱码、层级错误或能力夸大。
- 三文档交付门：7/7 逐项检查并通过；M30/M29 旧“仍待 M31”结论已在原位补 `⚠️ 注`，其余历史结论不需修订。
- 改动范围复核：`git status --short`、`git diff --name-only`、`git diff --cached --name-only` 和 `git ls-files --others --exclude-standard` 已交叉检查；当前无暂存文件，tracked/untracked 均与模块清单一致。
- 最终 `git diff --check`：通过；仅出现 Git 的 LF→CRLF 工作树提示，不是 whitespace error。notes 中所有 implementation/finish-docs checkbox 已完成。
