# DataPilot 开发日志（学习复盘）

> 给"未来的我"读的：每个模块讲清楚做了什么、我该理解什么、面试怎么讲。当前进度看 `docs/state/AI_CONTEXT.md`「当前状态」；完整技术档案和历史实验统一从 `docs/state/CHANGELOG_INDEX.md` 进入，查 bug 时按需追溯。
>
> M0 ~ M28 的记录已被拆分到 `docs/dev-log(M0-M19).md`；本文件记录从 M29 开始。

## ★ M29 Phase 4 入口盘点与合同冻结

（2026-08-12）

**简述**：在写 RAG 代码前，先把 DataPilot 现有入口、安全漏洞面、知识来源和评测迁移边界盘清楚，冻结一套**能独立验收的 Phase 4 语义合同**，让后续模块不会一边实现一边改口径。

### 先用大白话讲

M29 像盖新楼前先做测绘、立施工红线：楼还没盖，先搞清楚地基上有哪些坑、红线画在哪里。

当时 DataPilot 已有的 `/api/query`、SQL 安全、Trace 和 Eval 都是为 Text2SQL 长出来的，直接加 RAG 会踩到四个坑：

- 客户端可以自己填 role，没人验证身份；
- 技术超时也会显示成“安全阻断”，用户以为自己越权了；
- 数据库里的知识正文还可能被 SQL 路径看见；
- 说不清谁有权看、用了哪份证据、为什么拒答、外发了什么。

所以本模块没有追求“马上能聊天”，而是先立下后续各部件共同遵守的红线：状态分开说、身份不能自报、证据要有生命周期、引用必须可校验、远程发送默认不继承旧授权。这样下一模块才能围绕一个明确问题做闭环，而不是把 API、权限、语料、检索、生成和 Eval 揉成一场失控的大改造。

### 这次做了什么

本模块处理的核心矛盾是：Phase 4 roadmap 已经描述了 RAG/Hybrid 的方向，但当前代码事实仍是 SQL-only 入口，若不先冻结接口与安全语义，后续每增加一个节点都会复制兼容分支和权限判断。最终产出不是运行能力，而是一份从现状证据推导出的**实施合同与风险地图**。

1. **把“回答发生了什么”拆成四条互不冒充的状态轴**

   原来的 `AgentResponse` 只有 route 和一组 safety/error 字段，Schema 没召回、模型超时、SQL 执行错误和 SQL Guard 拦截都可能被包装成 `safety_status=blocked`。这会误导用户，也会让 Eval 把“没观察到能力”判成“业务答错”。

   M29 因此把内部事实冻结为 **route / execution / answer / safety 四轴**：走哪条路、工具是否完成、答案是否完整、安全是否放行分别表达；并为澄清、不支持、无候选、证据不足、外部不可用、ACL 拒绝、引用非法等情况建立 reason registry（原因码注册表，每种结局对应一个稳定代号）。

   没有直接修改 `/api/query` 或删除旧字段，因为 Streamlit、Trace、M27 adapter 和大量测试仍在消费它们。推荐方案是后续保留端点并做单向兼容投影：新内部合同产生旧字段，而不是旧字段反过来控制新流程。聚焦 **40 个回归测试**和消费者反向清单证明现有行为未被 M29 改动；但这还不能证明未来投影实现正确，那要由对应开发模块测试。

2. **把身份、Evidence 和 citation 变成安全边界**

   当前 `QueryRequest.user_role` 是客户端自己填写的字符串，能用于 demo fixture（演示夹具），却不能证明生产身份。

   M29 因此冻结两项合同：

   - **trusted caller（可信调用者）**：只有认证、demo 或测试 adapter 能解析出可信 caller；未经验证的 role 声明默认拿不到文档 Evidence。
   - **typed Evidence（带类型的证据）**：不再随手塞进 `docs_used` 的字典，而是带 authority（权威来源）、content identity（内容身份）、revision（修订版本）、allowed uses（允许用途）和安全 reference 的对象，并区分 candidate、selected、generation-visible、cited 四个阶段。

   这个阶段划分解决一个常见错觉：**“检索到过”不等于“模型看过”，更不等于“答案真的引用它”**。

   - Citation 必须由代码检查 evidence id、revision、ACL、阶段和 anchor（原文定位坐标）；模型不能自造一个看似正规的编号。
   - 没有把权限判断交给 prompt，也没有默认让 admin 看全部文档，因为这会把确定性安全规则交给概率模型。
   - 桌面反例覆盖 role 篡改、未授权高分候选、旧版本文档、文档 prompt injection（提示注入）和伪造 citation；它证明合同能描述这些风险，不代表实现已经存在。

3. **治理首批知识与 Eval 交接，但不提前替后续模块选技术参数**

   反向盘点发现，10 条 `knowledge_docs` seed 不只是未来 RAG 语料：它还进入 ORM/Alembic、SQL RBAC、Domain Schema、Schema Retrieval、prompt 和旧 Eval。尤其 `sensitive_data_policy` 草稿容易暗示 admin 可看敏感明文，与现行“所有角色都禁止敏感字段”代码事实冲突。

   M29 为每条 seed 登记保留、改写、由 `metrics.yaml` 派生或淘汰的 disposition（处置决定），并规定知识原件只讲政策规则，实时订单事实仍由 SQL Evidence 提供。

   本模块没有直接删表、改 seed 或发布 corpus（正式语料），因为那会跨入 P1 实现并改变当前运行边界；也没有提前选择 chunk size（切块大小）、top-k、rerank、embedding 或 LangGraph 等参数。

   Phase 4 Eval 将使用独立 family（合同家族），复用 M27 的“一题一次执行、多 assertion 共享 evidence”、required/advisory Gate 和 artifact 身份纪律，但不往只读的 `m27-v3` 塞大量 RAG optional 字段。

   **验证**：全仓 **29 个测试文件、223 个 collected test** 已分段执行覆盖且无失败。这只能证明 M29 未破坏当前代码，不能说明 RAG 召回或答案质量已经提升。

### 新概念

- **Orthogonal status axes（正交状态轴）**：把几个不同问题分开记，像 HTTP status、业务状态和审计状态不会共用一个布尔值。工具超时可以是 execution unavailable，同时 safety 仍 passed；证据不足可以是 answer insufficient，也不等于系统异常。
- **Trusted caller（可信调用者）**：不是“请求里写自己是谁”，而是由可信入口解析出的身份上下文。可类比 Spring Security 的 `Authentication`：Controller 不应相信前端直接传来的 `ROLE_ADMIN`，业务层只消费认证链给出的 authorities。
- **Evidence lifecycle（证据生命周期）**：一份材料从候选到被选择、真正送给生成器、最后被答案引用的阶段记录。它让系统能回答“这句话究竟依据了什么”，也让 ACL、Trace 和 Eval 在同一个事实基础上工作。
- **Closed-world artifact（闭世界产物）**：评测产物不只要求“已有结果都合法”，还要求应有的 Scenario、replicate、assertion 和身份一个不少、一个不多；否则缺一半结果也可能投影出漂亮分数。
- **Outbound policy（出站策略）**：授权粒度是 receiver × node purpose × data class。即使 QueryPlan 已允许发给 Qwen，也不自动代表可以把受限政策正文、SQL rows 或完整答案发给同一家 provider。

### 代码阅读路线

1. **先读模块边界与最终合同**：`docs/notes/m29-phase4-entry-contract-plan.md` → `docs/notes/m29-phase4-entry-contract-notes.md`
   Plan 解释为什么 M29 只做 P0；notes 依次给出 inventory、决策、四轴真值表、reason registry、Evidence/citation handoff、10 条知识 disposition 和 Scenario matrix。阅读时先抓“不改运行代码”的边界，再看每项风险如何交给 P1/P2。

2. **再对照公开入口事实**：`app/schemas/agent.py` → `app/api/query.py` → `demo/streamlit_app.py`
   先看请求体 role 和当前 `AgentResponse`，再看 route 如何构造成功/失败响应，最后看 demo 消费了哪些兼容字段。这样能理解为什么 G0 选择保留 `/api/query`，以及为什么新状态必须先在内部稳定再向外投影。

3. **沿身份和知识旁路检查安全面**：`engine/sql_guard/rbac.py` → `domain_pack/schema_desc/knowledge_docs.md` → `engine/schema_retrieval/document_builder.py` → `scripts/seed_data.py`
   这条路线会看到 `knowledge_docs` 如何被 SQL 角色允许、如何成为 Schema 文档、正文从哪里生成。重点不是死记表结构，而是理解**只在 RAG 层加 ACL 不够**，还必须封住 Schema/prompt/SQL 的旁路。

4. **最后看 Trace、远端和 Eval 的消费者**：`engine/trace/` → `engine/nl2sql/generator.py` → `eval/contracts.py` / `eval/projector.py` / `eval/review.py`
   Trace 当前会保存较完整的请求/响应，模型与 judge 各有自己的 payload；M27 合同则以 SQL 证据为中心。对照 notes 的 outbound matrix 和 Eval migration matrix，可以看懂为什么授权不能按 provider 粗放继承，也为什么 Phase 4 需要独立合同 family。

核心阅读链路是：

`客户端声明`
→ `trusted caller adapter`
→ `route / execution / answer / safety`
→ `candidate → selected → generation-visible → cited Evidence`
→ `公开兼容投影 / 安全 Trace / Phase 4 Eval`

### 设计要点

- **保留一个稳定入口，内部合同先行**：避免同时迁移 API、demo、Trace 和旧 Eval；兼容字段只能是投影，不能继续做事实源。
- **安全 fail closed，但能力失败不冒充安全阻断**：身份、ACL、citation 和 outbound 缺失时拒绝；provider timeout、无候选和证据不足则用各自状态诚实表达。
- **知识 authority 只有一个**：政策来自经审查原件，metric 文档从 `metrics.yaml` 派生或校验，数据库表只是可重建投影，不能三处独立编辑。
- **滚动规划技术参数**：M29 冻结后续必须满足的语义和验收，不替尚未建立的 corpus 选择 chunk、top-k、rerank、图编排或向量后端。
- **边界**：trusted caller、Evidence、ACL、citation 和新 Eval family 目前都是冻结合同，不是已上线代码；当前 `user_role` 和 `knowledge_docs` SQL 暴露仍是 P1 风险。

### 有面试价值的亮点

1. **开工前先做“反向盘点”，再用四轴把“成功”拆开。**我逐个翻 API、RBAC、Schema Retrieval、知识 seed、Trace 和 M27 Eval，发现直接接 RAG 会带进客户端自报角色、技术超时被写成安全阻断、知识正文被 SQL 旁路读等一堆问题；于是把“这次请求发生了什么”冻结成 route/execution/answer/safety 四轴——技术超时是 execution failed，safety 照样 passed，Eval 也不会把“没观察到”误判成“答错了”。
2. **刻意不写功能代码，先把“什么算完成”定死。**这轮交付的是合同和风险地图：身份、Evidence 四阶段、citation 代码校验、outbound 默认拒绝全部写成后续模块必须满足的验收项；29 个测试文件、223 项回归无失败，证明的是“没改坏”，不是“RAG 更好了”。

### 面试官追问

1. **[基础追问] 为什么技术超时和安全阻断必须分开？**

   两者的用户动作、监控归因和评测结论完全不同。安全阻断说明请求或证据违反确定性政策，重试不应该绕过；provider timeout 说明本轮没有观察到答案，可能重试或降级。若都写成 blocked，用户会以为自己越权，Eval 也会把外部不可用算成业务错误。四轴状态允许 execution unavailable 与 safety passed 同时成立。

2. **[工程/深挖追问] 既然已有 SQL RBAC，为什么 RAG 还要 trusted caller 和两次 ACL 检查？**

   SQL RBAC 只保护表和字段，而且当前 role 来自请求体；文档还涉及 revision、allowed roles、tenant、存在性侧信道和生成阶段。检索前过滤避免把未授权正文交给 retriever，生成前再检一次防止缓存、索引漂移或实现错误。两次检查消费同一个 trusted caller 与 policy decision，并在 Trace 中只保留安全引用。

3. **[工程/深挖追问] 为什么不直接扩展 M27 Eval contract？**

   M27 的核心对象是 SQL-only execution 和 `user_role`，RAG/Hybrid 需要 caller identity、两类 Evidence、citation、文档 ACL、分支状态和用途分集。把它们全做 optional 会让 loader、projector、review 到处出现兼容判断，还可能重写历史解释。独立 family 复用评测纪律而不复用不合适的数据结构，M27 artifact 因此保持只读可追溯。

4. **[压力追问] 这个模块没有一行功能代码，是不是设计过度、工程自嗨？**

   这个质疑对“已经交付 RAG 能力”成立，M29 确实没有交付它，也没有这样宣传。它的目标是关闭会让后续实现返工或越权的入口歧义，而且证据来自现有代码：role 可自报、知识正文处于 SQL Schema/RBAC、技术失败统一 blocked、Trace/远端 payload 没有 RAG 数据分类。模块把这些风险转成可测试合同和两个可独立验收的 P1 切片。若直接实现一个 demo 会更快看到答案，但无法可靠说明谁能看、答案依据和失败含义；对于企业数据 Agent，这些不是装饰性设计。

### 验证与下一步

- **验证**：API/Trace/M27/数据库聚焦回归为 **`40 passed, 1 warning`**；全量 223 项因工具 300 秒上限分段完成，后半段 **`72 passed, 3 skipped, 1 warning`**，中断位置 M4 单独 **`7 passed, 1 warning`**，其余前段在中断前均通过；没有测试失败。`git diff --check` 通过。
- **Warning/skip**：warning 是既有 Starlette/httpx deprecation；3 个 skip 是未启用 Milvus/远端 embedding 的既有条件跳过，均不影响 M29。
- **尚未证明**：没有运行真实 LLM Eval，也没有 RAG recall、citation correctness 或 answer quality 数字；本模块证明的是合同完整和现有行为未被破坏。
- **下一步**：先规划并实现“可信知识原件、catalog prototype 与 Text2SQL 隔离闭环”，再规划 Evidence/citation/ACL/outbound 的安全发布；不直接跳到 Router/Hybrid。

可复制的确定性验证命令：

```powershell
# 聚焦检查现有公开响应、Trace、M27 合同和数据库边界；预计 40 passed。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -q tests/test_m5_agent_response.py tests/test_m16_trace_router.py tests/test_m27_foundation.py tests/test_database_upgrade.py --basetemp=.agent_work/temp/pytest-m29-contract

# 全仓回归；项目当前共收集 223 项，Milvus/远端 embedding 未启用时会有 3 个条件 skip。
D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/pytest-m29-full
```

**本地启动体验：** M29 暂无独立可交互入口，因为它交付的是后续 RAG 的合同和安全边界，没有修改 `/api/query` 的当前运行行为。要人工复盘，建议并排阅读 M29 plan/notes 与上述代码阅读路线；真正的知识问答体验要等 P1 安全发布和 P2 RAG 垂直切片完成后再开放。

## ★ M30 可信知识原件、Catalog Prototype 与 Text2SQL 隔离

（2026-08-13）

**简述**：把政策与指标整理成可审查、可重建、失败关闭的 **staged catalog**，并彻底封住 `knowledge_docs` 的 Text2SQL 查询旁路；根据 G2 选择保留 source-backed catalog 与隔离的 legacy 物理表。

### 先用大白话讲

M29 发现了一个**危险的中间状态**：知识政策只是数据库 seed 里的几段字符串，同时又被 Text2SQL 当成普通表暴露。这就像公司制度只有贴在走廊里的几张传单，谁都能撕下来改几笔，SQL 部门还照着传单当业务数据用。

M30 把这个问题完整关掉了：

- 政策和规则有了可审查的 **Markdown 权威原件**，像把传单换成了盖过章的正式制度册；
- 指标说明不再手抄，而是从 `metrics.yaml` 自动生成，公式只有一处；
- 一个确定性的 builder 会校验完整 metadata、ACL、revision、anchor 和 identity，任何错误都整体失败，不会出现“前半本没问题、后半本缺页”的半成品；
- `knowledge_docs` 从 Text2SQL 的 Schema、retrieval、prompt 和 SQL Guard 全部消失：数据库仍有 **14 张物理表**，但自然语言 SQL 只能看到 **13 张分析表**。

### 这次做了什么

本模块处理的核心矛盾是：**知识既没有可信原件，又能被 SQL 旁路读取**。最终方案不是先堆一个向量检索 demo，而是先让知识来源、构建身份和不可查询边界都能被代码验证。价值在于后续 Knowledge Tool 可以站在一个明确地基上继续实现 Evidence/citation/ACL，而不需要重新猜正文从哪里来、哪个版本有效、Text2SQL 是否还能绕过。全仓确定性回归和 MySQL seed 验证证明现有 SQL/数据库能力没有被破坏；但本模块没有运行真实 RAG，因此不能宣称召回或回答质量已经提升。

1. **把“数据库里的草稿”升级为可信原件**

   退款总则、质量问题、物流延迟、发票、VIP、敏感数据和 demo scope 被整理成 7 份 Markdown 原件。每份都带 document key、revision、anchor（定位坐标）、status、data class（数据分类）、用途和 allowed roles（允许角色）。

   正文也做了业务纠偏：例如 admin 不能因为角色名就经自然语言 Text2SQL 查看敏感明文；VIP 文档只定义资格规则，不记录某个客户当前是否达标。

   **原来的影响**：数据库草稿既不方便 code review（代码审查），也无法表达稳定版本和访问用途；继续宽松使用旧表，会让手工编辑、ACL 丢失和版本漂移同时存在。

   现在每条旧 seed 都有 disposition（处置决定）和 authority（权威来源）映射，合同测试检查必需 metadata 与非法 ACL；这证明原件结构可审计，但 **尚未证明这些政策已经通过业务法务审批**，它们仍是项目演示域内的受控语料。

2. **让指标说明只有一个事实源**

   GMV、优惠券和行为漏斗的公式已经在 `metrics.yaml`。如果再在知识文档里复制一遍，两个地方迟早会改得不一样。M30 的 projection 配置（派生投影）只声明 metric key（指标键）和展示/访问 metadata（元数据），正文在构建时由对应 metric 确定性生成。

   旧 `coupon_rule` 同时描述优惠券使用订单数和使用率，实际上对应两个不同指标。本次把它拆成 `coupon_order_count` 与 `coupon_usage_rate` 两个 entry，所以旧 10 条 seed 最终形成 11 个 catalog 条目。这不是多写了一份口径，而是把原来混在一起的两个概念分开。

   如果选择“projection YAML 也填写 formula”会更直观，却会重新制造第二事实源。因此测试明确检查 projection 文件没有 formula/description，且生成正文包含 `metrics.yaml` 的真实公式；**已经证明单一 authority 和确定性派生成立**，但没有证明未来所有指标都适合直接作为回答证据，公开用途仍需后续 ACL/outbound 模块裁决。

3. **实现一个小入口、深实现的 staged catalog**

   调用者只需要使用 `build_staged_catalog()`：文件发现、Markdown/YAML 解析、metric 派生、closed-world 校验、稳定排序、manifest（清单）和 hash 都封装在内部。

   成功返回 immutable（不可变的）`StagedCatalog`；任何条目非法就抛出有限 reason code（原因码），不会返回“前 10 条成功、第 11 条失败”的半成品。

   M30 特意区分两类身份：content identity（内容身份）表达知识语义，用来发现换 key 后重复塞入同样内容；corpus identity（语料身份）包含 document/revision/authority/anchor/ACL 等完整 manifest，用来判断整套 catalog 是否发生治理或内容变化。mtime（文件修改时间）、目录遍历顺序和 YAML key 顺序不会制造假漂移。

   更简单的“发现几个文件就返回几个对象”无法阻止半成功和静默默认值。

   M30 用反例测试覆盖缺字段、未知 enum/role/purpose、重复 revision/anchor/content、未知 metric key、inactive 泄漏和 expected identity 漂移；同输入重建 identity 一致，正文变化会改变 identity。

   **这证明 staged（分阶段）构建合同成立，不代表 active 发布、在线原子切换或回滚已经实现。**

4. **封住 Text2SQL 知识旁路**

   `schema_desc/knowledge_docs.md` 和 retrieval alias（检索别名）被移除，四种角色的 SQL allowlist（允许名单）都不再包含知识表。SQL Guard 的全部分析表集合从默认 Domain Schema 派生，减少 prompt 与权限名单各写一份造成的漂移。

   即使模型手工伪造 QueryPlan，planner 会因表不在局部 Schema 拒绝；即使跳过 planner 直接提交 SQL，SQL Guard 仍会拒绝。

   只在 prompt 里写“不要查”更省代码，但模型提示不是安全边界。

   测试同时验证 prompt 不可见、Schema Retrieval 无字段文档、伪造 planner 输出失败和四角色手工 SQL 被 Guard 拦截；M27 canonical（规范）归因题仍返回 `unsupported_relation`。Schema corpus（语料）因此从历史 195 docs 变为 **186 docs/new hash**；旧报告仍可追溯，但旧 Milvus collection 不能冒充当前索引。

5. **在证据出来后完成 G2（Phase 4 第二个决策门），而不是提前拍脑袋选数据库结构**

   prototype（原型）证明当前没有 API、Tool、生成器、retriever 或 demo 读取 `KnowledgeDoc`。

   用户比较三种方案后选择 B：运行时从 authority source 构建 catalog，物理表暂留为 legacy（遗留）兼容存储。seed 删除手写 `_KB_CONTENTS`，改为从同一个 catalog 生成 11 行；没有新增 migration（迁移），也没有删表。

   方案 A 会为尚不存在的多实例/运营后台提前冻结数据库 projection schema（投影结构）；方案 C 会立刻承担删表、外部消费者和回滚风险。

   方案 B 的代价是保留一个 **有损 legacy 表**，因此代码和 state 明确禁止从它恢复正式 ACL。MySQL `datapilot_dev` 已 reset 验证 14 表计数、11 条知识投影和固定事实；这证明兼容 seed 可重建，**不能证明仓库外永远没有旧表消费者**，未来退役仍需重新审计。

### 新概念

- **Authority source（权威原件）**：发生冲突时谁说了算。政策正文以 Markdown 原件为准，指标公式以 `metrics.yaml` 为准；数据库 legacy 行不是第三份真相。
- **Derived projection（派生投影）**：为了兼容或查询方便，从原件生成的副本。它可以随时重建，不能反向覆盖原件，也不能承担原件没有表达的 ACL 语义。
- **Fail closed（失败关闭）**：遇到未知字段、非法角色、重复 identity 或缺少 authority 时，整个构建失败。系统不能猜一个默认值后继续，因为“猜错权限”比“暂时不可用”危险得多。
- **Staged vs active**：原件状态 `active` 只表示这条 revision 可以进入 staged usable set；catalog 仍没有通过 G3 发布。可类比代码已经通过单元测试并进入 release candidate，但还没有部署到生产流量。
- **Physical schema vs queryable schema**：数据库里存在的表不等于自然语言 Agent 有权查询的表。就像 Java 项目里某个 Repository 存在，不代表每个 Controller 都应该暴露它。

### 代码阅读路线

1. **从权威输入开始**：`domain_pack/kb_docs/*.md`、`domain_pack/kb_docs/metric_projections.yaml`、`domain_pack/metrics.yaml`
   先看政策 front matter 如何表达 revision、anchor、ACL 和用途，再对照 projection 配置为什么只有 metric key、没有公式正文。阅读重点是理解**政策正文与指标 authority 是两种来源**；不用先死记每个字段取值。
2. **沿唯一构建入口理解完整流程**：`engine/rag/catalog.py`
   从主角函数 `build_staged_catalog()` 开始，先看它如何加载两类 source，然后看 `_validated_metadata()` 怎样失败关闭，最后看 `CatalogEntry`、`StagedCatalog`、content/corpus/build identity 如何协作。关键设计是调用者不编排半成品步骤，避免不同消费者各自漏掉一项校验。
3. **查看方案 B 的兼容投影**：`scripts/seed_data.py::_build_knowledge_docs`
   这里消费 staged catalog 并生成旧 ORM 行。重点理解 `audience_role` 只是有损兼容字段，不能反向恢复完整 ACL；这解释了为什么物理表可以暂留，却不能重新成为 runtime catalog。
4. **沿 Text2SQL 双重防线检查旁路**：`engine/nl2sql/schema_loader.py` → `engine/schema_retrieval/document_builder.py` → `engine/sql_guard/rbac.py`
   先看 `DEFAULT_QUERYABLE_TABLE_NAMES` 如何从分析 Schema 派生，再看 retrieval 不再生成知识字段文档，最后看 SQL Guard 如何复用同一 universe。三者协作实现“模型看不见 + 最终执行仍拒绝”。
5. **用反例和过程证据收尾**：`tests/test_m30_knowledge_catalog.py` → `docs/notes/m30-notes.md`
   测试覆盖 identity、失败关闭、inactive、metric authority、seed 派生和 SQL 反绕过；notes 则保存 10 条旧 seed disposition、G2 选项/风险/用户选择以及真实验证快照。二者分别回答“合同是否机器可验”和“为什么这样决策”。

核心数据流是：

`Markdown 政策原件 + metrics.yaml`
→ `build_staged_catalog()`
→ `immutable staged entries + manifest identity`
→ `legacy seed projection（兼容，不是 authority）`

Text2SQL 隔离链是：

`13 表 DomainSchema`
→ `Schema Retrieval / prompt / QueryPlan`
→ `SQL Guard 最终 allowlist`

### 设计要点

- **深模块减少调用者认知负担**：外部只有一次完整构建；解析与校验细节留在 implementation 内部。
- **正文与治理 identity 分层**：既能识别重复内容，又能追踪 revision/authority/ACL 变化。
- **两道安全门**：prompt/planner 看不见知识表，SQL Guard 最终仍拒绝；不依赖模型“自觉不查”。
- **旧证据不改写**：历史 M27 的 195-doc hash 继续解释旧 artifact；当前 corpus 是 186 docs/new hash，不能复用不匹配的 Milvus collection。
- **滚动规划**：短文尚未出现 chunk 失败，不引入 parent/child、embedding、rerank 或在线发布机制。

### 有面试价值的亮点

1. **知识从“数据库里的几段字符串”升级成有权威原件和稳定身份的受治理资产。**政策迁到带 revision、anchor、ACL 的 Markdown 原件，指标正文从 `metrics.yaml` 生成而不是手抄；一个失败关闭的 builder 要么整体成功、要么整体拒绝，content/corpus 两层 identity 让重复内容和治理变化都能被发现。
2. **封 SQL 旁路用了两道防线，宁可留 legacy 表也不乱迁移。**知识表从 Schema、prompt、retrieval 里消失，SQL Guard 仍按 allowlist 拦截伪造 QueryPlan 和手工 SQL；用户选了方案 B，旧表只做兼容投影且禁止恢复 ACL——技术债登记在案，而不是假装不存在。

### 面试官追问

1. **[基础追问] 为什么不直接把数据库表当知识库？**

   数据库适合做派生查询结构，但原表字段没有 revision、authority、anchor、完整 ACL 和 build identity，也允许被独立修改。直接把它当事实源会让内容审查、重建和漂移定位都变得含糊。保留表可以兼容，但读取方向必须从原件到投影，而不是反过来。

2. **[工程/深挖追问] 为什么 content identity 不包含 document key 和 revision？**

   如果包含，复制同一正文后只改 key 就会得到不同 hash，重复内容检测失效。content identity 只描述语义内容；document key、revision、anchor 和 authority 由 corpus manifest identity 追踪。两个 identity 分工后，重复检测和版本审计都能成立。

3. **[工程/深挖追问] 既然 planner 看不到 `knowledge_docs`，为什么 SQL Guard 还要拦一次？**

   planner 是能力引导，不是最终安全边界。调用方可能传入手工 SQL，模型也可能因 bug 绕过局部 Schema。最终执行前必须按 AST 提取真实物理表并用 allowlist 再判一次，这类似 Controller 参数校验不能替代数据库事务层的权限检查。

4. **[压力追问] 你保留一个没人用的 legacy 表，不就是在留下技术债吗？**

   这个质疑有合理部分：legacy 表确实是技术债，所以 M30 没把它包装成正式投影。模块目标是先关闭双 authority 和 SQL 旁路，而仓库扫描只能证明仓库内没有消费者，不能证明外部脚本不存在。立即删表会引入 migration、数据删除和回滚成本，却不给当前功能带来收益。现在通过 Text2SQL 隔离、source-backed seed 和 state 风险登记控制它；未来出现明确退役窗口、多实例或运营后台需求时，再用消费者审计决定删除或升级。

### 验证与下一步

- **聚焦验证**：seed/数据库/核心合同 `70 passed, 1 warning`。
- **全仓验证**：`231 passed, 3 skipped, 1 warning`；warning 是既有 Starlette/httpx 弃用提示，skip 是未启用的 Milvus/远端 embedding 条件测试。
- **身份快照**：Text2SQL 为 13 tables / 186 docs / hash `6b67606d...`；staged catalog 为 11 entries / corpus identity `abdc9aed...`。
- **MySQL 验证**：`datapilot_dev` 已按当前 seed 确定性重建；Alembic head/check 正常，14 表计数匹配，`knowledge_docs=11`，固定业务事实保持不变。
- **尚未证明**：没有运行真实 LLM、embedding、Milvus 或 LangFuse；M30 不代表回答质量、召回率或 citation 已上线。
- **下一步**：继续 P1 的 trusted caller、Document Evidence/citation、ACL/outbound 和安全发布，经过 G3 后才能把 staged catalog 交给生成器。

可复制验证命令：

```powershell
# Catalog、Text2SQL 隔离和历史归因合同；预计 37 passed，另有既有 deprecation warning。
python -m pytest tests/test_m30_knowledge_catalog.py tests/test_phase3a_schema_retrieval.py tests/test_m22_eval_contract.py -q --basetemp=.agent_work/temp/pytest-m30-review

# 全仓确定性回归；当前结果为 231 passed、3 skipped。
python -m pytest -q --basetemp=.agent_work/temp/pytest-m30-full-review

# 只读查看 staged manifest；不调用网络，也不会 active 发布。
python -c "from engine.rag import build_staged_catalog; print(build_staged_catalog().manifest())"
```

**本地启动体验：** 本模块暂无独立 API 或页面，因为它只建立 staged catalog 和 Text2SQL 安全地基，尚未通过 G3 接入 Knowledge Tool。人工体验可先阅读 `domain_pack/kb_docs/`，再运行上面的只读 manifest 命令，重点检查 `lifecycle_status=staged`、11 个 entry、authority reference 和 identity；环境未激活时，把 `python` 换成 `AGENTS.md` 中的项目 Python 完整路径。

## ★ M31 可信证据与安全发布

（2026-08-13）

**简述**：把 M30 的 11 条 staged 知识推进为一个经过身份、ACL、出站、Evidence/citation 和故障发布合同保护的 **active release**，但刻意不提前实现检索和问答。

### 先用大白话讲

M30 像把 11 份公司制度整理进了档案室，但门还没正式打开。M31 做的是档案室的**门禁、借阅单、引用凭证和版本切换**：前端自己写“我是管理员”不能开门；一份文档即使被找到，也要在选中和真正交给生成器前各检查一次权限；答案里的引用不能临时编个文件名；新版本只有完整写好、校验好、重新加载成功后，才把门牌从旧版本切到新版本。

用户最终批准了 **G3 方案 A**，所以当前 11-entry release 已正式 active。这里的“active”只表示它可以被后续 P2 安全消费，不表示 DataPilot 已经会检索政策、生成 RAG 答案或在 API 中展示 citation。

### 这次做了什么

本模块处理的核心矛盾是：知识内容已经治理好，但系统还不能证明“谁在用、能不能用、实际给模型看了什么、引用是否真实、发布失败会不会暴露半成品”。最终结论是先把这些确定性地基做成小而深的接口，再让下一模块只组合接口，不在 Knowledge Tool、Graph、Trace 和 Eval 中各写一份安全判断。

1. **先把“用户自报角色”与可信身份彻底分开**

   原来的 `QueryRequest.user_role` 是客户端传来的字符串。如果未来直接拿它做文档 ACL，攻击者只要把 role 改成 `admin` 就可能读到受限政策。

   M31 引入 **Trusted caller（可信调用者）**：它像 Spring Security 已完成认证后的 `Authentication`，业务层只接收解析好的 caller，不读取 token、cookie 或原始角色声明。production authenticated、demo fixture 和 test fixture 可以成为授权主体；请求体声明只能变成 `unverified_request_claim`（未验证请求声明），其 `resolved_roles` 固定为空。

   文档授权再按 trust、active revision、purpose、`public/allowed_roles` 的固定顺序判断，admin 也没有隐式全读权。

   - 候选构造前做 `pre_selection` 检查，真正进入生成器前做 `pre_generation` 二次检查；
   - 拒绝投影统一显示 `not_authorized`，避免标题、文档 ID、revision、正文甚至“某文档是否存在”成为侧信道（旁路泄露）。

   没有采用“相信前端 role”或“让模型看 prompt 自己守规矩”的宽松方案，因为安全边界必须由确定性代码控制。

   **验证**：11 entries × 角色 × 用途矩阵、role 篡改和 admin 非全读反例都已通过；但生产 JWT/OAuth 和 RAG API 尚未实现。

2. **让 Evidence 和 citation 记录真实使用过程，而不是事后拼来源**

   “检索命中过”不等于“被选中”，更不等于“模型真正看过并用于回答”。M31 建立 **Typed Evidence（带类型证据）**：公共外壳保存 run、authority、revision、content identity、anchor 和用途，内部 payload 分为 Document 与 SQL；授权决策、runtime 和 outbound 仍是独立引用，不塞进万能大对象。Evidence 只能沿 `candidate → selected → generation_visible → cited` 同轮单步前进。

   **Citation slot（引用槽位）**由代码按 run 和 claim 预分配，validator（校验器）再检查 slot、run、阶段、文档 safe-ref、revision/content identity、anchor、用途和入模前授权。

   - 模型自造 ID、引用只到 selected 的证据、跨轮引用、旧 revision、错误 anchor 或拿另一份文档的 allow decision 冒用，都会整体得到 `citation_invalid`；
   - 同一份真实 Evidence 可以支持多个 claim，但 ledger 只推进一次。

   没有采用“答案末尾拼文件名/sources”的简单方案，因为它证明不了生成器看过什么、也不能阻止越权引用。

   **验证**：篡改和多 claim 复用测试已通过；开放语义上“这段证据是否真的支持这句话”仍要在 P2 用 gold/人工/advisory judge 验证。

3. **用不可变 release 和独立 Phase 4 Gate 完成安全发布**

   如果直接覆盖一个运行目录，写到一半崩溃时，服务可能看到新旧内容混合。

   M31 采用 **Immutable release bundle（不可变发布包）**：完整正文投影、corpus/build、policy 和 contract 一起计算 canonical hash（规范哈希）；相同 identity 的文件不允许出现不同字节。新的 candidate（候选包）独立写入并重载成功后，才原子替换 `active.json`；pointer 记录 current/previous 和 G3 approval（审批标记）。

   故障语义也按安全优先设计：

   - 即使故障注入先破坏目标 pointer 再报错，也恢复精确旧 pointer；
   - 启动发现 active 损坏会失败关闭，不自动复活可能已撤销的 previous；
   - 显式 rollback（回滚）也要重新对照当前 authority、revision、ACL 和 policy，而不是“旧文件还在就能回去”。

   用户比较过方案 A“验证后激活”和方案 B“继续 staged（分阶段）”：A 能让 P2 开工，但派生 bundle 保存正文，未来真实敏感内容要补 retention/delete（保留/删除策略）；B 更保守，却会暂停 RAG 主线。建议并最终选择 A。

   独立 **`phase4-v1` contract/security family（合同/安全家族）** 用 8 个 Scenario、12 个 required assertion 检查 caller、ACL、outbound、Evidence、citation 和发布；每题只执行一次，artifact 对 caller/runtime/policy/corpus/release/Scenario/assertion 做 closed-world（闭世界）对账。

   **验证**：最终 Gate 为 `12/12 passed`，全仓为 `276 passed, 3 skipped`。这些证据证明确定性合同和兼容性，没有证明 retrieval、答案正确率或真实 LLM 效果。

### 新概念

- **Active pointer（活动指针）**：一个很小的文件，只说明当前服务应读取哪个完整 release，并保留上一版 identity。可以类比数据库里的“当前版本号”：先准备好新数据，再原子改版本号，消费者不会读到半成品。
- **Immutable release bundle（不可变发布包）**：生成后不原地修改的完整运行投影。内容变化就产生新 identity，像带内容哈希的制品包；它不是新的正文编辑入口，authority 仍是 Markdown 和 `metrics.yaml`。
- **AuthorizationDecision（授权决定）**：一次确定性 allow/deny 结果，记录 policy、caller/document safe-ref、阶段和用途。它不是角色字符串，也不能拿一份文档的 decision 给另一份 Evidence 冒用。
- **Citation integrity（引用完整性）**：代码能证明引用 ID 存在、同轮、已入模、有权、版本和 anchor 正确。它与 semantic support 不同：前者是确定性真伪，后者还要判断证据内容是否足以支持自然语言 claim。
- **Closed-world Eval（闭世界评测）**：不仅检查已有结果，还要求该有的 Scenario、replicate、assertion 和 identity 一个不少、一个不多。否则少跑一半也可能得到“现有结果 100% 通过”。

### 代码阅读路线

1. **从身份与两类策略开始**：`engine/governance.py`
   先看 `TrustedCaller` 的四种 trust level，再看 `DocumentAuthorizationPolicy.authorize()` 的固定检查顺序，最后看 `OutboundPolicy.decide()` 的精确白名单。这里解决“谁可信、文档能否使用、数据能否外发”三个确定性问题；重点理解默认拒绝和 safe projection，不需要死记 hash 实现。

2. **跟一份文档走完 Evidence 生命周期**：`engine/rag/evidence.py`
   从 `make_document_evidence()` 看 `pre_selection` decision 如何绑定 document safe-ref；再看 `EvidenceLedger.transition()` 为什么在 `generation_visible` 前要求第二次授权；最后看 `allocate_citation_slot()` 与 `validate_citations()` 如何把 claim 绑定到同轮真实入模 Evidence。这一层不负责检索和写答案，只保证证据事实可靠。

3. **看 candidate 怎样变成 active**：`engine/rag/release.py` → `domain_pack/kb_releases/active.json`
   先读 `build_candidate_release()` 的 canonical serialization/独立重载，再读 `activate_release()` 的 current/previous 和失败恢复，最后读 `load_active_release()` 与 `rollback_active_release()` 的失败关闭。运行文件只是 builder 产物，不能反向编辑 authority。

4. **看现有远程调用怎样被约束**：`engine/nl2sql/llm_call.py` → `engine/nl2sql/generator.py`；`engine/schema_retrieval/embedding_provider.py`
   `llm_call` 把 `query_plan/sql_generation` 用途交给真实 chat client；client 和 embedding provider 在 fake/真实网络函数前调用 outbound gate。这样保留现有 Text2SQL 数据类别，却不会因为 provider 相同就自动放行 Document Evidence。

5. **最后读新的确定性评测与反例**：`eval/phase4_contracts.py` → `tests/test_m31_*.py`
   先看 8 个 Scenario 如何各执行一次并产出共享 `ExecutionEvidence`，再看 completed artifact 如何做 closed-world 对账；测试重点覆盖 role 篡改、ACL 侧信道、伪 citation、hash 篡改、pointer 故障、重启和 rollback。它与 M27 v3 分离，不会把 RAG 字段塞回旧 Text2SQL artifact。

核心数据流是：

`active release entry`
→ `trusted caller + pre-selection AuthorizationDecision`
→ `candidate/selected Document Evidence`
→ `pre-generation AuthorizationDecision`
→ `generation-visible Evidence`
→ `code-assigned citation slot`
→ `validated cited Evidence`

### 设计要点

- **安全判断集中且可删除测试**：P2 只依赖 caller/authorization/Evidence/release 小接口；删掉任一检查会直接让对应 required 反例失败。
- **同 provider 不继承权限**：Text2SQL 已登记的 Qwen 调用不代表 answer composer、Document Evidence 或 Eval Judge 获批；LangFuse Cloud 仍关闭。
- **发布失败不等于自动回退**：候选失败保持旧 active；但启动发现 current 损坏时失败关闭，因为自动复活 previous 可能恢复已撤销正文。
- **第一次发布没有 rollback 神话**：`previous=null` 是真实状态；只有未来第二版且旧版重新通过当前 policy/authority 校验，才允许显式 rollback。
- **能力边界不夸大**：`phase4-v1` 证明安全和发布合同，不是 RAG 召回率或答案质量分数。

### 有面试价值的亮点

1. **前端自报角色彻底失效：TrustedCaller 像 Spring Security 的 Authentication。**业务层只消费服务端解析好的 caller，请求体 role 最多变成 unverified claim；文档授权按 trust、revision、purpose 和显式 allowlist 固定顺序判断，检索前和入模前各查一次，admin 也没有隐式全读权。
2. **发布做成“先验货、再换门牌”。**immutable bundle 完整重载成功后才原子替换 active pointer；故障恢复精确旧版本，启动发现损坏就失败关闭，回滚还要重新过 authority/policy——不是“旧文件还在就能回去”。

### 面试官追问

1. **[基础追问] 为什么文档权限要检查两次，检索前检查一次不够吗？**

   候选阶段检查能减少未授权内容进入后续处理，但候选还可能经过缓存、去重、版本变化或调用链 bug。真正入模前再检查一次，才能证明生成器此刻看到的 revision、purpose 和 caller 仍然有效。它类似 Controller 入口鉴权后，执行敏感 Service 操作前仍检查资源级权限；两次检查共享同一个 policy，不是复制两套规则。

2. **[工程/深挖追问] 你怎么证明 citation 不是模型随便编的？**

   模型拿不到自由生成可信 ID 的权力。代码先为本轮 claim 分配 slot，validator 再从同轮 ledger 查 evidence id，要求它已经处于 `generation_visible`，并对照当前 active entry 的 document/revision/content identity/anchor、用途和 `pre_generation` decision。unknown、selected-only、跨轮、旧版本、错误 anchor、冒用另一文档 decision 都用反例测试拒绝。这里证明的是 citation integrity；语义支持度仍留给 P2 的 gold/人工评估。

3. **[工程/深挖追问] 原子改 `active.json` 就等于有完整事务和高可用发布了吗？**

   不等于。M31 的保证范围是当前单机文件系统：bundle 先完整写入并重载，pointer 用同目录 replace 切换，故障恢复精确旧 pointer。它没有解决多实例并发、对象存储一致性、分布式锁或在线无停机协调。当前项目没有这些真实需求，所以先用可测试的本地深模块；出现多实例/运营后台需求时，再替换 release storage adapter，而不是把单机保证包装成分布式事务。

4. **[压力追问] 你做了这么多安全对象，业务还不能回答 RAG，这是不是过度设计？**

   这个质疑合理：M31 没提升用户可见回答能力。它的目标也不是做展示层，而是关闭几条一旦接上生成器就难以补救的边界——客户端 role 越权、未入模证据被引用、同 provider 静默扩大外发、半成品发布。证据是 12 个 required contract assertion、发布故障注入和 276 项全仓回归，不是主观说“更安全”。复杂度也受控在三个深模块和独立 Eval family，没有引入 Graph、向量库或生产认证。下一步 P2 会直接复用这些接口形成可见 RAG 闭环；如果 P2 调用者仍需要理解 release 文件或重写 ACL，就说明本模块的抽象没有做好。

### 验证与下一步

- **模块专项**：M31 caller/ACL/outbound、Evidence/citation、release 和 Phase 4 artifact 共 `45 passed in 1.23s`。
- **跨模块 Gate**：M31 + M30 + Phase3A + legacy API/Trace + M27 foundation/review 为 `93 passed, 1 warning`。
- **全仓验证**：`276 passed, 3 skipped, 1 warning in 481.28s`；skip 是既有 Milvus/远端 embedding 条件测试，warning 是既有 Starlette/httpx deprecation。
- **发布与 Eval**：active release `4e86bdd...`、11 entries、previous `null`；`phase4-v1` artifact `197e0d62...`，required `12 passed / 0 failed / 0 not_observed`。
- **尚未证明**：未运行真实 LLM、远程 embedding、Milvus、LangFuse Cloud 或真实 RAG Eval；没有 Knowledge Tool、retrieval、Composer、公开 API citation、Graph/Router/Hybrid。
- **下一步**：进入 P2 确定性 RAG 垂直切片，只消费 active catalog 和 M31 治理接口，先做本地可替换 retrieval + Knowledge Tool，再形成薄 Gate/Composer/Citation 闭环。

可复制验证命令：

```powershell
# M31 确定性安全/发布专项；预计 45 passed，不访问网络。
python -m pytest tests/test_m31_governance.py tests/test_m31_evidence_citation.py tests/test_m31_release.py tests/test_m31_phase4_contracts.py -q --basetemp=.agent_work/temp/m31-review-focused

# 全仓确定性回归；当前结果为 276 passed、3 skipped、1 个既有 warning。
python -m pytest -q --basetemp=.agent_work/temp/m31-review-full

# 只读查看正式 active 状态；预计 active=true、11 entries、previous=None。
python -c "from engine.rag.release import inspect_release_state; print(inspect_release_state())"
```

**本地启动体验：** 本模块暂无独立 API 或页面，因为它提供的是 P2 将消费的安全地基，`/api/query` 仍未接 RAG。现在最直接的人工体验是运行上面的只读 `inspect_release_state()`，确认 current release、entry count 和 previous；环境未激活时，把 `python` 换成 `AGENTS.md` 中的项目 Python 完整路径。不要直接修改 `domain_pack/kb_releases/*.json`，内容变化应从 authority 重新 build/publish。

## ★ M32 确定性知识取证与 Knowledge Tool

（2026-08-13）

**简述**：把 M31 已发布的 11 条 active 知识安全、稳定地检索成 **selected Document Evidence**，并用独立 retrieval Eval 证明召回、ACL、失败归因和 artifact 完整性；本模块仍不生成最终答案。

### 先用大白话讲

M31 建好了带门禁的档案室，M32 开始真正办理“查档”。用户问“质量问题退款要什么材料”，系统先确认这个人能看哪些文件，再把允许看的文件交给检索器；检索器只负责排候选，不能自己越权开柜。选出文件后，系统还会在交给下一层之前再检查一次权限和版本，最后发出一组带身份的证据。

这像公司 Service 层调用搜索组件：搜索组件只接收已经过滤的数据，返回的是候选坐标，不是最终业务结论。M32 还专门建立了一份离线答卷，能区分“确实没有候选”“存在内容但调用者无权”“版本中途失效”和“检索后端坏了”。这样下一模块接生成器时，答错了可以先判断是**没找到证据**，还是**找到后没有正确作答**。

### 这次做了什么

本模块的**核心矛盾**是：active release 已经可信，但缺少一个安全、可替换、可评测的消费入口。如果直接把全部文档交给模型，既可能泄露未授权内容，也会把检索失败、生成失败和引用失败混成一个“回答不好”。最终采用用户确认的方案 A，先闭环取证层，再把回答层留给下一切片。

1. **把检索器做成可替换、可复现的 adapter**

   原来系统没有 Knowledge retrieval seam，后续若直接在 Tool 里写死向量库或 Milvus，安全过滤、检索算法和运行配置会绑在一起。这里的 **Retrieval Adapter（检索适配器）**，可以理解成 Java 里的 repository interface：上层只认输入输出合同，不依赖词法、向量或混合检索的内部实现。

   `engine/rag/retrieval.py` 冻结了 `RetrievalAdapter`、`RetrievalBatch`、`RetrievalMatch` 和有界 `RetrievalBudget`。首个本地 recipe（配方）的做法：

   - 用 NFKC 规范化（Unicode 标准归一化）、英文词和中文 2–4 gram（n 元词片段）分词；
   - 按 title/key/content 加权，再用 `0.05` 门槛过滤只共享“平台”一类公共词的极低相关候选；
   - 固定输入按明确 identity 打破并列，保证结果可复现。

   没有先上 embedding/hybrid/rerank，因为当前只有 11 条短知识，尚无失败簇证明这些复杂度必要，而且 G4（默认检索 adapter 的决策门）还没触发。

   **验证证据**包括相同输入重复结果一致、gold 命中、零候选、并列排序、重复输入、未知 entry、越预算、错误 query/runtime identity 和非法 rank/score。它证明本地 recipe 与 seam 的确定性，**尚未证明**长文、同义改写或真实语义召回质量。

2. **把 ACL、检索与 Evidence 组织成一个安全 Tool**

   最大风险不是“搜得不准”，而是未授权正文先进入检索器。即使最后不返回，未来远端 adapter、日志、score 或命中数量也可能泄露“某份文档存在”。`engine/rag/knowledge_tool.py` 因此固定执行：active load → **pre-selection ACL（候选前授权）** → 一次 adapter → candidate Evidence → 选择 → **pre-generation recheck（入模前复核）**。

   adapter 只看到已授权 entries；match 必须映射回同次 active bundle，才能构造 Document Evidence。

   - 通过第二次检查的证据只推进到 `selected`，因为 M32 还没有真的把正文交给 Composer，不能提前记成 `generation_visible`；
   - 内部 ledger（账本）保留候选供审计，但 `safe_projection()` 只显示最终 selected Evidence——这条规则是在收工审查中补强的，避免 revision/content identity 形成存在性侧信道。

   没有用“把所有失败都返回空列表”的宽松方案：

   - `no_candidate`、`no_authorized_evidence`、`stale_revision`、active release 不可用和 adapter 不可用在内部保持不同原因，技术故障也不会伪装成“政策不存在”；
   - 公开安全投影会让无候选与无权限收敛，防止反向探测知识库。

   **验证**：投毒正文、角色篡改、两次 ACL 间 revision 失效和故障注入均有测试；**尚未完成**真实入模、答案、claim、citation 和公开四轴状态。

3. **建立一次执行、闭世界的 retrieval Eval**

   如果每个 scorer 都重跑一次 Tool，六个指标可能来自六次不同检索，最终平均数看似精确却无法解释。`eval/rag_retrieval_contracts.py` 建立 **ExecutionEvidence（执行证据）**：每个 Scenario 只调用一次 Tool，再由 reason、coverage、rank、ACL、调用次数和 runtime 等 assertion 共同读取这份答卷。

   artifact 采用 **Closed-world validation（闭世界校验）**：不仅检查已有结果，还核对 Scenario、replicate、assertion、effect、caller/runtime/release/corpus/adapter/recipe identity 和 canonical hash 是否一个不少、一个不多。required Gate 与 retrieval-only advisory 分开；检索器技术不可用时，coverage 是 `not_observed`，不会记成业务错误，也不会靠 advisory 通过掩盖 required 失败。

   **验证**：

   - `phase4-rag-retrieval-v1` 有 **6 个 Scenario、20 条 required 全通过**，3 条 advisory 为 2 passed、1 technical-unavailable `not_observed`；
   - M32 聚焦 28 passed，全仓 304 passed、3 skipped；
   - 开发中两轮失败也被保留并修正：先处理公共词低分与 stale fixture，再修正 Eval safe-ref 和 returned-evidence 口径。

   以上证明合同、ACL 和离线 baseline（基线）可复现，**不能说明**真实 LLM 答案正确、citation 语义支持或 Milvus 更好。

### 新概念

- **Retrieval Adapter（检索适配器）**：把“怎样找到候选”藏在统一接口后面。Knowledge Tool 只依赖 match 合同，将来替换向量或混合检索时，不必把 ACL、Evidence 和回答逻辑一起改掉。
- **Query fingerprint（查询指纹）**：规范化问题和已确认条件后生成的 hash。它能比较“是不是同一份检索输入”，又不用在长期诊断里保存原始问题。
- **Pre-selection ACL / pre-generation recheck**：第一次保证未授权内容不进入检索器，第二次保证选中后权限或 revision 没有在真正使用前失效。可类比 Spring Security 的入口认证与资源级二次授权。
- **Retrieval recipe identity（检索配方身份）**：把分词、权重、低分门槛等实现配方标成稳定版本。调整算法就应该换 identity，避免两种不同检索行为混在同一 Eval 名下。
- **`not_observed`（不可观察）**：不是“答案错了”，而是外部技术故障导致本轮根本没有可评分答卷。它与 `failed` 分开，能避免把可用性问题误算成业务质量。

### 代码阅读路线

1. **先读最小检索合同**：`engine/rag/retrieval.py`
   从 `RetrievalBudget`、`RetrievalMatch`、`RetrievalBatch` 看清上层与后端交换什么，再读 `DeterministicLexicalRetrievalAdapter.retrieve()`。重点理解 adapter 只消费传入 entries、稳定排序和 recipe identity 为什么存在；中文 n-gram 的每个权重不需要死记。

2. **沿主流程读 Knowledge Tool**：`engine/rag/knowledge_tool.py`
   从 `KnowledgeRequest` 和 `RetrievalOutcome` 入手，然后顺着 `KnowledgeTool.retrieve()` 的四个步骤读。重点看 ACL 为什么在 adapter 前、match 怎样回到 active entry、为何第二次授权后只推进 selected，以及内部 ledger 与安全投影为什么不同。

3. **跟一次 Scenario 看共享答卷**：`eval/rag_retrieval_contracts.py`
   先看 `SCENARIOS` 冻结了哪些正常与失败路径，再看 `_execute_scenario()` 如何只调用一次 Tool，最后看 `validate_completed_artifact()`、`project_required_gate()` 和 retrieval effect summary。这里解决的是评测可信度，不是训练或调参平台。

4. **用测试反向理解边界**：`tests/test_m32_retrieval.py` → `tests/test_m32_knowledge_tool.py` → `tests/test_m32_rag_retrieval_contracts.py`
   先看算法确定性，再看 ACL、投毒、stale 与 adapter 故障，最后看 artifact 缺失、重复、identity 篡改和 required/advisory 分离。测试名称本身就是一份失败模式目录。

核心调用链是：

`active ReleaseBundle`
→ `pre-selection ACL 过滤`
→ `RetrievalAdapter 一次调用`
→ `candidate Document Evidence`
→ `pre-generation recheck`
→ `selected Evidence + 内部 ledger + safe diagnostics`
→ `一次 ExecutionEvidence`
→ `required Gate / advisory retrieval view`

### 设计要点

- **方案 A 的边界**：先把安全取证单独做深，避免 retrieval、generation、API 和 citation 同时变化；代价是本模块没有用户可见回答。
- **授权在 adapter 外集中控制**：未来即使换远程检索器，也不能自己决定能看什么；安全规则不会散落到每个后端。
- **审计事实不等于公开事实**：内部可以保留 candidate 方便归因，安全投影只暴露最终 selected，避免“可观测性”反过来成为数据泄露。
- **业务零结果不等于技术失败**：结构化 reason 与 `not_observed` 让系统能分别处理知识缺失、权限收敛和后端不可用。
- **G4 继续延后**：词法 adapter 是候选 baseline，不是 P3 默认；要等回答/citation 闭环和可比较证据成立后再决定。

### 有面试价值的亮点

1. **检索器做成可替换 adapter，权限检查发生在它之前。**像 Repository 接口一样把“怎么搜”藏起来，本地实现用中文 2–4 gram 和稳定排序保证固定输入可复现；ACL 在 adapter 外集中做，未授权正文连检索器都进不去。
2. **失败原因分开记，Eval 一次执行、多断言共享答卷。**no candidate、无授权证据、revision 失效、后端不可用各有代号，技术故障记 not_observed 而不是 0 分；每个 Scenario 只跑一次 Tool，20 条 required 断言从同一份 ExecutionEvidence 判卷。

### 面试官追问

1. **[基础追问] 为什么不让检索器自己做 ACL，反而先过滤再调用？**

   因为 adapter 是可替换的基础设施，未来可能变成远程 embedding、向量库或第三方服务。如果把 ACL 交给每个 adapter，不同后端很容易规则漂移，而且未授权正文已经在“检索之前”被发送或记录。现在 Tool 集中做授权，adapter 的输入集合本身就是安全边界；测试还用 counting fake 证明未授权 entry 从未进入 adapter。

2. **[工程/深挖追问] 检索后已经做了 pre-generation 检查，为什么 ledger 不直接推进 generation-visible？**

   检查通过只表示“此刻允许使用”，不表示正文已经真的进入 Composer。把 selected 提前写成 generation-visible，会让未来 citation validator 相信一份模型根本没看过的证据。M32 返回 decision 给下一层，只有下一层实际构造生成上下文时才执行阶段迁移，这样 ledger 记录事实而不是意图。

3. **[工程/深挖追问] 技术不可用时为什么 coverage 是 not_observed，而不是 failed 或 0 分？**

   后端故障时没有候选答卷，无法判断检索算法本来能不能覆盖 gold。记 failed 会把可靠性故障混进业务质量，记 0 更会错误惩罚算法；但也不能忽略这次运行，所以 execution/root-cause required assertion 仍然可观察，coverage advisory 单独记 `not_observed`。Gate 与效果视图分开后，两类问题都不会被藏掉。

4. **[压力追问] 你在 11 条文档上写词法检索和 20 条断言，这不是自己出题自己满分吗？**

   这个质疑合理：这组结果确实不能外推真实语义检索，更不能证明业务答案质量。M32 的目标是先验证接口、安全顺序、失败归因和评测分母，而不是宣称模型效果。证据中也保留了开发失败、技术不可用 `not_observed` 和全仓回归，没有只报一个满分。下一阶段先接 Evidence Gate/Composer/citation；只有出现稳定召回失败簇并冻结未污染对照后，才值得比较 embedding、hybrid 或 rerank，并触发 G4 默认 adapter 决策。

### 验证与下一步

- **M32 聚焦验证**：adapter、Knowledge Tool、ACL/Evidence 与 retrieval Eval 为 `28 passed in 0.71s`。
- **P1 回归**：M30 catalog 和 M31 release/governance/Evidence/Phase 4 contract 为 `56 passed in 2.26s`。
- **受影响回归**：API/Text2SQL/Eval 完整重跑为 `188 passed, 1 warning in 446.43s`；第一次 180.3 秒外层超时未计作成功。
- **全仓验证**：`304 passed, 3 skipped, 1 warning in 537.27s`；skip 是本机 Milvus 不可用的既有条件跳过，warning 是既有 Starlette/httpx 弃用提示。
- **尚未证明**：未运行真实 LLM、remote embedding/rerank、Milvus 或 LangFuse Cloud；没有回答、citation、公开 RAG API 或长文能力结论。
- **下一步**：从 selected Evidence 接 Shared Evidence Gate 和 Composer；实际入模后推进 `generation_visible`，citation validator 通过后推进 `cited`，再讨论用户可见投影。

可复制验证命令：

```powershell
# M32 取证与 retrieval Eval 聚焦门；预计 28 passed，不访问网络。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m32-review tests/test_m32_retrieval.py tests/test_m32_knowledge_tool.py tests/test_m32_rag_retrieval_contracts.py -q

# 全仓确定性回归；当前结果为 304 passed、3 skipped、1 个既有 warning。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m32-review-full -q

# 只读打印 M32 retrieval Gate 和 advisory 汇总，不写 report、不调用外部服务。
python -c "from eval.rag_retrieval_contracts import run_rag_retrieval_contract_suite,project_required_gate,project_retrieval_effect_summary; a=run_rag_retrieval_contract_suite(); print(project_required_gate(a)); print(project_retrieval_effect_summary(a))"
```

**本地启动体验：** 本模块暂无独立 API 或页面，因为方案 A 只做到内部安全取证，`/api/query` 还没有接 Knowledge Tool。当前最直接的体验方式是运行上面的只读 Gate 命令，观察 required 全通过和技术不可用 coverage 的 `not_observed`；环境未激活时，把 `python` 换成 `AGENTS.md` 中的项目 Python 完整路径。

## ★ M33 可信 RAG 回答与 Citation 闭环

（2026-08-15）

**简述**：把 M32 的 selected Document Evidence 真正送入受控回答流程，形成经过 Shared Gate、确定性 Composer 和 Citation Validator 验证的 **RAG answer/citation 闭环**；当前仍是内部深模块，尚未接公开 API。

### 先用大白话讲

M32 已经能从档案室里安全找出资料，但“找到资料”不等于“系统真的根据资料回答了问题”。M33 像给查档流程增加一张严格的**答复审批单**：资料必须仍是当前版本、调用者仍有权、内容确实足以回答、文档里没有伪装成系统命令的危险指令，才能交给写答复的人；每一句答复的引用位置由程序先编号，最后再由验真员核对引用是否来自本轮真正看过的资料。

因此，系统现在能区分“没找到”“找到了但不够”“没有权限”“后端坏了”“引用被篡改”等不同情况。通过验证的回答才会公开；失败时内部保留审计轨迹，但不会借日志或响应泄露某份受限文档是否存在。用户还在 **G4** 选择当前确定性词法检索器作为 P3 的首个工程 baseline，让下一阶段可以直接做 Router/Harness；这并不表示词法检索已经是最终最佳方案。

### 这次做了什么

本模块解决的**核心矛盾**是：M32 已经产生可信 selected Evidence，但项目仍不能证明生成器到底看了什么、回答里的 claim 是否受这些 Evidence 支持、citation 是否真实，也没有统一的四轴失败结果。最终方案是把这些责任收进一个 `RAGAnswerFlow` 深模块，并用独立、一次执行的 Answer Eval 验证，而不是提前把半成品接进 HTTP。

1. **建立 Shared Gate，让“允许使用”变成“真实入模”**

   原来的 Evidence 最远只到 `selected`。如果下一层仅凭“检索选中了”就标记 `generation_visible`，citation validator 可能相信一份 Composer 根本没看过的文档。这里的 **Generation context（生成上下文）**，就是本轮 Composer 实际收到的 typed Evidence 集合，不是事后重新检索或从答案猜来源。

   `engine/rag/answer_flow.py` 的 Gate 会检查 run/stage/purpose、当前 active revision、content/anchor identity、pre-generation authorization、结构化 Evidence requirement 和文档指令安全。

   - 只有检查通过且马上要交给 Composer 的那几份 Evidence 才推进 `generation_visible`；
   - Gate deny 时 Composer 调用数固定为 0。

   没有采用“先全部推进、生成失败再回滚”的宽松方案，因为 ledger 应记录已经发生的事实，而不是未来意图。

   测试覆盖 zero-hit、已有候选但缺少指定事实、ACL 拒绝、revision 中途失效、缺失 authorization 和 prompt injection。**验证证据**显示正常 context 与最终 cited Evidence 精确对应，拒绝路径不越过 selected；但这些是冻结短知识上的确定性规则，**尚未证明**开放语义充分性判断。

2. **让 claim 与 citation 从同一份 Evidence 身份链产生**

   过去常见的简单做法是生成完答案后，在末尾拼一个文件名或 `sources` 数组；它只能说明“可能检索过”，不能证明该来源真的支持某句话。M33 的 **Evidence-bound Composer（证据绑定生成器）** 首版采用离线 extractive（抽取式）方式：从真实 generation context 中抽取有界正文，每条 `ClaimDraft` 都携带支持它的 Evidence ID 和 anchor，但无权自己创建最终 citation。

   AnswerFlow 再按 run、claim 顺序和文本 hash 分配稳定 claim/citation slot（槽位），复用 M31 Citation Validator 校验同轮、阶段、revision、anchor、ACL 和 slot 完整性。

   - 只有全部引用通过，才构造 `ValidatedClaim`、用户 citation 和 answer，并把 ledger 推进 `cited`；
   - `docs_used` 也只能从 validated citation 单向派生；
   - 空 claim、未知 Evidence、杜撰文本、越预算、错误 anchor 或缺一条 citation 都会整体失败，不返回“半份看起来可信”的答案。

   没有直接接远程 LLM，因为当前 Knowledge generation/outbound 仍默认拒绝；伪造一个“以后可替换”的远程 adapter 反而会掩盖尚未授权的边界。**验证证据**包括 GMV 公式和质量退款正常回答、Composer 故障、杜撰 claim、partial citation 与篡改反例。它证明 citation integrity 和 extractive support，**不等于**自然语言回答质量已达到产品水平。

3. **集中四轴结果，并把内部审计与公开投影分开**

   如果所有失败都返回空字符串，上层无法区分业务证据不足、权限阻断和技术不可用。`RAGAnswerResult` 统一返回 **route / execution / answer / safety 四轴**：例如 retriever 故障是 `rag / external_unavailable / no_answer / passed`，citation 篡改是 `rag / completed / no_answer / blocked`，正常闭环才是 `rag / completed / complete / passed`。

   一个容易忽略的安全点：Composer 或 citation 失败后，内部 ledger 必须保留真实的 `generation_visible`，否则审计会撒谎；但公开 `safe_projection()` 不能把这些 Evidence identity 带出去，否则受限或投毒文档的存在性可能泄露。

   因此 M33 同时保留 **内部真相** 和 **最小公开真相**：失败公开投影会清空 Evidence/context、answer、claims 和 citations。

   没有在本模块修改 `AgentResponse` 或 `/api/query`。直接接线虽然更容易演示，却会迫使 M33 提前决定 Router、可信 caller 和 HTTP 兼容合同，甚至可能误用请求体 `user_role`。用户确认 **G-M33（本模块决策门）方案 A** 后，这些职责留给 P3 唯一顶层 Harness。

   全仓验证证明旧 API/Text2SQL 没被改坏；**尚未完成**的是公开 RAG、生产认证和全局 Trace。

4. **建立独立、一次执行的 Answer/Citation Eval**

   如果状态 scorer、citation scorer 和答案 scorer 各自重跑一次流程，它们看到的可能不是同一轮 Evidence。`eval/rag_answer_contracts.py` 因此为每个 Scenario 只运行一次 AnswerFlow，生成一份 **ExecutionEvidence（执行证据）**，再让所有 typed assertions 共享它。

   `phase4-rag-answer-v1` 有 9 个 Scenario，覆盖质量退款、GMV、no candidate、语义不足、ACL、prompt injection、stale revision、retriever unavailable 和 citation invalid。

   completed artifact 对 Scenario、replicate、assertion/effect、execution evidence ref，以及 release/corpus/adapter/recipe/composer/flow/policy identity 做 **Closed-world validation（闭世界校验）**；缺失、多余、重复或篡改都整体验证失败。required Gate 与开放措辞 advisory（建议性）分开，技术不可用时答案质量记 `not_observed`，不会冒充 0 分或被忽略。

   **验证**：最终 **60/60 required 全通过**；3 条 advisory 为 2 passed、1 retriever-unavailable `not_observed`。

   用户据此在 **G4（默认检索 adapter 决策门）选择方案 A**，让 `knowledge-deterministic-lexical-v1` 成为 P3 首个默认 baseline。这个结论只说明当前链路足以做工程起点，**不能说明** embedding/hybrid 没价值；未来仍要用 held-out 失败簇和单变量 A/B 决定是否替换。

### M33 的知识内容追加

用户随后选择方案 A，把知识库从 11 条补到 22 条：增加 8 条直接由 `metrics.yaml` 派生的指标说明，以及 3 份只讲处理边界的文档。它们不会另造退款金额、处理时限、优惠门槛或用户资格；遇到实时订单事实、证据不足和优惠券实际适用性，仍要求查业务系统、专项规则或转人工。

这次只扩内容，没有新开模块，也没有改 ACL、出站策略、词法检索默认值或 AnswerFlow 合同。

**验证**：

- 新 release 保留旧 11 条版本作为 previous（上一版本）；
- 三套 required Gate 仍为 12/12、20/20、60/60；
- 全仓更新为 `342 passed, 3 skipped, 1 warning`。

知识面更实用了，但仍只是短知识 baseline。

### 新概念

- **Generation context（生成上下文）**：Composer 本轮实际看见的 Evidence 集合。可以类比调用 Java Service 时真正传入的方法参数；数据库里查到但没有传进去的数据，不能事后声称被 Service 使用过。
- **Shared Answer Evidence Gate（共享回答证据门）**：在生成前集中检查 Evidence 当前是否有效、有权、用途匹配、足够支持问题并且内容安全。它不是 LLM 自评，而是确定性代码控制的硬边界。
- **Evidence-bound claim（证据绑定声明）**：每条用户可见结论都先声明支持它的 Evidence identity，再由代码分配 citation slot 和验证；不是答案生成完以后猜一个来源。
- **Extractive Composer（抽取式生成器）**：直接从允许的文档正文中抽取内容，不做开放改写。优点是支持关系容易证明，缺点是措辞可能生硬；它是当前可信 baseline，不是最终产品文案方案。
- **四轴结果**：把路由、技术执行、答案状态和安全状态分开，避免“没答案”同时代表没证据、系统坏了或被安全策略阻断。

### 代码阅读路线

1. **先从唯一入口看完整控制流**：`engine/rag/answer_flow.py`
   从 `RAGAnswerRequest` 和 `AnswerEvidenceRequirement` 开始，再顺着 **`RAGAnswerFlow.run()`** 的五个步骤读：Knowledge Tool、Gate、Composer、slot/validator、结果投影。重点理解每个子模块只负责一个决定，以及失败为何集中映射四轴；不需要先死记 hash 细节。

2. **停在 Gate 看真实入模边界**：`engine/rag/answer_flow.py::_gate`
   对照 `GenerationContext`、`GateDecision` 和 `EvidenceLedger.transition()`，看 selected Evidence 经过 revision/ACL/requirement/指令检查后，怎样只把实际 context 推进到 `generation_visible`。这里解决“检索过”和“模型看过”不能混为一谈的问题。

3. **继续跟 claim 走到 citation**：`DeterministicEvidenceComposer.compose()` → `_build_citation_drafts()` → `engine/rag/evidence.py::validate_citations`
   先看 Composer 只产 text + Evidence/anchor，再看流程代码分配 claim/slot，最后由 M31 validator 推进 cited。关键设计是 **identity 先于展示**：用户 citation 是验证结果的投影，不能反向构造内部 Evidence。

4. **最后看安全失败和一次执行评测**：`tests/test_m33_answer_flow.py` → `eval/rag_answer_contracts.py` → `tests/test_m33_rag_answer_contracts.py`
   AnswerFlow 测试是一份失败模式目录；Eval catalog 展示 9 个 Scenario 怎样共享同一次执行；artifact 测试则证明缺 Scenario、重复 replicate、改 policy/composer/hash 或断开 evidence ref 都会被拒绝。

核心调用链是：

`TrustedCaller + question + requirement`
→ `KnowledgeTool selected Evidence`
→ `Shared Gate`
→ `generation-visible context`
→ `deterministic ClaimDraft`
→ `code-assigned claim/citation slot`
→ `Citation Validator`
→ `cited ledger + validated answer/citations + 四轴安全投影`

### 设计要点

- **深模块而非步骤拼装**：P3 只调用 `RAGAnswerFlow.run()`，不需要知道 Gate、ledger、Composer 和 validator 的正确顺序，避免多个 controller 产生状态分叉。
- **内部审计不等于公开响应**：失败 ledger 保留真实阶段便于排障，公开投影清空未验证 Evidence，兼顾可审计和非泄露。
- **确定性 Composer 是刻意的 baseline**：当前先证明支持关系和 citation integrity；自然改写、远程模型和语义 Judge 需要新的 outbound 决策和效果证据。
- **G4=A 不是永久技术押注**：词法 adapter 只是 P3 首个可工作的默认值；长文、同义改写或跨文档失败出现后，才能用受控 A/B 讨论 embedding/hybrid/rerank。
- **公开能力仍未完成**：`/api/query`、生产 caller、Router/LangGraph、Hybrid、全局 Trace 和真实 RAG 效果都属于后续边界。

### 有面试价值的亮点

1. **“检索到”和“模型真正看过”之间加了一道 Gate，citation 是身份链的终点。**只有通过版本、ACL、用途、指令检查且马上要进 Composer 的 Evidence 才推进 generation_visible；每条 claim 绑定 Evidence/anchor，槽位由代码分配、validator 验真，杜撰或缺引用整体失败。
2. **失败分“内部真相”和“公开真相”，并刻意不接 API。**内部 ledger 保留真实阶段保证审计不撒谎，公开投影清空未验证引用防存在性泄露；Router 和 HTTP 合同留给唯一的顶层 Harness——60/60 required 全过证明的是合同闭环，不是语义回答质量。

### 面试官追问

1. **[基础追问] 你怎么证明 citation 指向的是生成器真正看过的资料，而不是检索命中过的资料？**

   我把 Evidence 阶段拆成 candidate、selected、generation-visible 和 cited。检索只能推进 selected；AnswerFlow 在实际构造 Composer context 的同一个边界才推进 generation-visible。citation slot 又由代码按 run/claim 分配，validator 只接受本轮 generation-visible Evidence，并复核 revision、anchor、ACL 和 current active entry。测试会捕获真实 Composer context，并与最终 cited Evidence identity 对账，所以不是靠答案末尾的文件名猜来源。

2. **[工程/深挖追问] citation 校验失败后为什么内部 ledger 还保留 generation-visible，不回滚到 selected？**

   因为正文已经实际进入 Composer，回滚会篡改审计事实。正确做法是内部保留 generation-visible，表明“看过但引用验证失败”；最终 answer/claims/citations 全部丢弃，公开 safe projection 清空 Evidence/context，避免泄露。这样阶段账本记录事实，响应层负责可见性，两者职责不会混在一起。

3. **[工程/深挖追问] 远程检索或 Composer 不可用时，为什么不是统一返回 insufficient evidence？**

   `insufficient_evidence` 是业务判断，表示系统正常执行但当前证据不够；后端不可用是 execution failure，本轮根本没有形成可评分答卷。如果混在一起，用户会误以为政策不存在，Eval 也会把可靠性故障算成答案质量差。M33 用四轴和稳定 reason 分开处理，技术不可用场景的 root cause assertion 仍可通过，开放答案质量则记 `not_observed`。

4. **[压力追问] 你的 Composer 只是复制文档，60/60 required 是不是又一次“自己出题自己满分”？**

   这个质疑有合理部分：60/60 不能证明自然语言回答好，也不能外推 11 条短知识之外的语义检索。我这轮的目标是先证明更底层、可确定性验证的合同——真实入模、ACL、阶段、claim/citation identity、失败非泄露和 Eval 分母没有造假。证据除了两条成功题，还包含七类失败和 artifact 篡改反例。选择 extractive Composer 是为了让支持关系可验证，而不是把它包装成最终产品能力。进入 P3 后先打通可信端到端；出现 held-out 语义失败后，再授权远程 Composer 或比较 embedding/hybrid，并用独立 A/B 证明收益。

### 验证与下一步

- **M33 聚焦验证**：AnswerFlow、Gate、Composer、citation、四轴结果和 Answer Eval 共 `33 passed in 0.84s`。
- **M31/M32 回归**：治理、Evidence/release、retrieval、Knowledge Tool 与历史 Phase 4 contracts 为 `73 passed in 1.44s`。
- **全仓验证**：知识内容追加后的结果为 `342 passed, 3 skipped, 1 warning in 466.33s`；skip 是既有条件跳过，warning 是既有 Starlette/httpx deprecation。
- **Answer Eval**：9 Scenario、60 required 全通过；3 advisory 为 2 passed、1 retriever-unavailable `not_observed`；最新 artifact `0dde3216...`。
- **尚未证明**：未调用真实 LLM、remote sufficiency/judge、embedding/rerank、Milvus 或 LangFuse Cloud；没有公开 API、生产认证、长文、同义改写、跨文档复杂问题或自然措辞结论。
- **下一步**：进入 P3 唯一顶层 Router/Harness，复用 Text2SQL pipeline 与 `RAGAnswerFlow.run()`，再解决可信 caller、同一 `/api/query` 兼容投影和全局 Trace。

可复制验证命令：

```powershell
# M33 回答与 Answer Eval 聚焦门；预计 33 passed，不访问网络。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m33-review tests/test_m33_answer_flow.py tests/test_m33_rag_answer_contracts.py -q

# 全仓确定性回归；当前结果为 342 passed、3 skipped、1 个既有 warning。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m33-review-full -q

# 只读复算 M33 required Gate 与 advisory summary，不调用外部服务。
python -c "from eval.rag_answer_contracts import run_rag_answer_contract_suite,project_required_gate,project_answer_effect_summary; a=run_rag_answer_contract_suite(); print(project_required_gate(a)); print(project_answer_effect_summary(a))"
```

**本地启动体验：** 本模块暂无独立 API 或页面，因为用户确认的 G-M33 方案 A 只交付内部可信 AnswerFlow，`/api/query` 的 Router、生产 caller 和兼容响应要由 P3 唯一顶层 Harness 一次性接入。当前可运行上面的只读 Gate 命令观察 60 条 required 与 advisory 分层；也可阅读 `tests/test_m33_answer_flow.py` 的成功/失败用例理解四轴结果。环境未激活时，把 `python` 换成 `AGENTS.md` 中的项目 Python 完整路径。

## ★ ★ M34 EnterpriseRAG-Bench 真实语料接入

（2026-08-16）

**简述**：把项目外的 **36,417 篇企业文档、139,214 个检索单元和 180 道问题**真正接入 DataPilot 的 Knowledge Tool、Evidence、回答和引用链路，用真实构建与 Eval 取代“22 条短知识全部通过”的玩具化证据；最终确认链路已经成立，但答案质量的主要瓶颈仍是**漏召回、多文档上下文组织和严格支持合同失败**。

### 先用大白话讲

M31–M33 像是在一个只有 **22 张知识卡片**的小书架上，把门禁、权限、回答和引用流程练得很规范。它能证明“流程没乱”，却回答不了更现实的问题：如果书架突然变成几万篇 Confluence 页面、Google Drive 文档和 Jira 记录，系统还能不能建库、找到资料、把资料交给模型，并且让每句话都能追溯到原文？

M34 就是把这个“小书架实验”升级成一次真正的仓库压力测试。我们先审计数据，再按文档结构切片，建立项目外索引，然后让问题实际经过：

`真实大语料 → 检索 → 权限检查 → Evidence → 模型回答 → support_text → citation → Eval`

最终有两个很重要的结论。第一，**工程链路确实跑通了**，不再只是下载数据或写离线脚本。第二，跑通不等于答对：有些回答状态是 complete，也有合法引用，但引用的文档并不是标准答案需要的文档。这次 Eval 最大的价值，正是把这种过去看不见的问题暴露出来。

### 这次做了什么

这次工作的核心矛盾是：既要把大规模、长文档和多文档问题接进现有 RAG，又不能为了省事推翻 M31–M33 已经建立的权限、Evidence、发布和 citation 合同。最终采用了“**外部语料独立存放和建库，运行时复用现有可信链路**”的方式，并分别用 retrieval Eval 和 Answer Eval 判断“找没找对”与“回答链是否成立”。

1. **先把数据变成可核对的语料，而不是把一堆文件当作知识库**

   **原来的问题**是，外部数据即使已经下载，也不能直接等同于“可用知识库”。同一个 logical document ID 可能对应多份物理文件；题目里还存在重复 gold ID；如果读取时用 ID 覆盖写入，某些冲突信息题会在建库阶段就被悄悄改错。路径、文件数量或官方资产发生漂移，也会让两次评测看似使用同一数据，实际分母已经不同。

   M34 建立了 **closed-world dataset scanner（闭世界数据扫描器）**。所谓 closed-world，可以理解为仓库入库前先封一张完整清单：

   - 只接受 Confluence、Google Drive、Jira 三种来源，逐个核对官方资产的大小和 hash；
   - 区分 **logical document identity**（基准题怎样称呼一篇文档）与 **physical source-instance identity**（磁盘上这一份具体文件是谁）；
   - 发现冲突时保留，而不是覆盖；发现缺文件、未知来源、空题目或资产漂移时直接失败关闭。

   全量审计结果：

   - Confluence 5,189、Google Drive 25,108、Jira 6,120，**共 36,417 篇文档**；
   - 180 道题涉及 274 个唯一 gold document ID，0 个缺失，同时发现 3 个冲突 logical ID。

   `qst_0413` 的重复 gold 还被保留为 **multiset（多重集合）**，因为它要求找回同一 logical ID 对应的两份不同物理文档，不能偷懒去重。

   没有采用“能读就行”的宽松方案，因为那样最危险的不是程序报错，而是程序正常运行、分数也正常输出，却已经换了语料或丢了冲突文档。这里的验证证明了**数据分母、身份和来源可复现**；但 EnterpriseRAG-Bench 是模拟企业环境的合成数据，它仍不能证明真实公司的连接器噪声、权限继承和历史脏数据已经被覆盖。

2. **把长文档切成可定位、可回查、可替换的检索单元**

   **原来的问题**是，整篇文档直接入库虽然简单，但有些正文超过两万字符：检索词容易被大段无关内容稀释，命中后也会给模型塞入过多上下文。反过来，如果切得太碎或大量 overlap，又会放大索引、延迟和费用，还可能让 citation 只能指向一段脱离上下文的碎片。

   parser（解析器）先按三种来源的实际格式恢复正文中的结构性 `\\n`，但只处理明确的换行 token，不使用通用 `unicode_escape`，避免误改代码、JSON 或 Windows path。

   随后比较了 whole-document、paragraph-1200、paragraph-2400、paragraph-2400-overlap1 四种 **unit recipe（切分配方）**。这里的 unit recipe 就像切菜规格：它规定从哪里下刀、每块多大、是否重复搭边；一旦冻结，参数和 identity 必须一起版本化。

   在相同 corpus、parser 和 60 道 dev 题下做对照，最终选择 **`enterprise-unit-paragraph-2400-v1`、无 overlap**（共 139,214 units）：

   | recipe | lexical coverage@20 | 说明 |
   | --- | --- | --- |
   | whole-document | 0.724306 | 整篇入库，检索词被稀释 |
   | paragraph-1200 | 0.793056 | 切得偏碎 |
   | paragraph-2400-overlap1 | 0.793750 | 多出 21,301 个 units、约 19% 索引字符，却无稳定收益 |
   | **paragraph-2400（选中）** | **0.810417** | coverage 最高、无 overlap |

   > coverage@20 = 每道题取前 20 个候选时，标准答案文档被覆盖的比例。

   每个 unit 都绑定 normalized document revision、字符起止位置和正文 hash，citation 可以从 `normalized-char:<start>-<end>` 回切原文。

   没有用“先随便切，效果不好以后再换”的临时方案，因为切分会影响索引 identity、Evidence anchor 和 Eval 可比性。当前证据说明 2400/no-overlap 是这套 dev lexical 协议下较好的工程折中，**并不证明它对所有 embedding 模型、所有语言或生产文档都是全局最优**。

3. **建立独立 external profile，同时复用原来的权限和 Evidence 链路**

   **原来的问题**是，M31 的业务 `ReleaseBundle` 为 22 条短知识设计，正文直接内嵌；若把 139,214 个 units 强塞进去，会形成约 2.62 亿字符的 JSON/内存放大，而且同一长文的多个切片会争用原来的 `(document_key, revision)` citation key。更严重的是，把 benchmark 与业务 release 合并，会让测试数据参与业务默认检索、权限发布和回滚。

   因此 M34 建立了独立的 **external profile**：项目外的 immutable SQLite 保存 36,417 条 document metadata、139,214 条 unit metadata/context 和 FTS5（SQLite 全文搜索扩展）索引；构建完成前使用 `.building-*` 临时身份，经过 SQLite integrity、meta、数量、FTS、database hash 校验后，再原子 rename。benchmark 有自己的 active/previous pointer，业务 22 条 release 和 pointer 完全不动。

   运行时也没有重写第二套 RAG。`enterprise_runtime.py` 提供 metadata-only bundle（仅元数据包）、SQLite 检索 adapter 和命中后正文 loader（加载器）。

   Knowledge Tool 仍先做 pre-selection ACL，只有选中的 units 才加载正文，再做 pre-generation authorization，随后进入 M33 的 AnswerFlow、Evidence ledger 和 citation validator。每个 unit 使用独立 `enterprise-unit:<identity>` document key，同时保留 logical/physical document 和 normalized offsets（归一化偏移）。

   这相当于给原来的安全流水线换了一个“大仓库进料口”，但仓库里的门禁、验货和出库单没有被绕过。聚焦回归最终为 **158 passed**，说明 M30–M34 的 catalog、release、ACL、Evidence、AnswerFlow 和新 external runtime 合同能共同工作。它尚未证明公开 `/api/query`、生产认证、真实 Confluence/Drive/Jira connector ACL 或 Router 已经接好，因为这些明确不属于 M34。

4. **让 lexical 与 semantic 用同一把尺子竞争，而不是凭技术名词决定默认值**

   **原来的问题**是，“企业 RAG 就应该上向量检索”听起来合理，但如果 lexical 与 semantic 使用不同切分、不同题集或不同 top-k，分数没有可比性；更不能因为 embedding 更先进，就静默替换已经工作的默认 adapter。

   M34 先把 180 题按 `question_type × source signature × single/multi-document` 确定性分成 **60 dev + 120 held-out**。

   - dev 用来调查和选择，held-out 只有候选冻结后才打开；
   - gold document 不进入 runtime，只在检索返回后评分；
   - 两种 adapter 都固定 @20，并按 physical source identity 去重，评分同时计算 coverage、all-gold 和 MRR。

   两组 adapter 在同一把尺子下（coverage / all-gold / MRR）的结果：

   | adapter | dev | held-out |
   | --- | --- | --- |
   | lexical | 0.810417 / 0.766667 / 0.645303 | **0.823125 / 0.775000 / 0.723134** |
   | semantic candidate | 0.737500 / 0.700000 / 0.621421 | 0.773958 / 0.741667 / 0.630477 |

   两个 split（数据切分）都没有胜出，所以 semantic collection 保留为 candidate，external 默认仍是 lexical。

   这个结果不是“向量检索没用”，而是说明**当前 embedding + unit recipe + 检索协议没有证明收益**。没有继续加入 Hybrid、rerank 或 query rewrite，因为那会一次改变多个变量，也超出 M34 范围。下一轮如果改进召回，应生成新 identity，并继续用同一 split 做单变量 A/B。

5. **把真实回答、原文支持和最终引用绑在一起，再诚实记录答案质量**

   **原来的问题**有两层。第一，M33 的 extractive Composer 只能基本照抄原文，回答不自然；直接放开 LLM 改写后，又无法仅靠字符串证明改写内容真的受到 Evidence 支持。第二，早期 smoke 已经暴露：AnswerFlow 可以返回 complete 和 validated citation，但检索到的文档可能不是 gold，导致“流程完整、答案却错”。

   用户最终选择了 **方案 B**：每条 `ClaimDraft`（声明草稿）同时包含自然语言 `text`、同一 Evidence 中逐字存在的 `support_text`（支持原文）、`evidence_id` 和 `anchor`。可以把它理解为“对外说人话，对内必须附原文凭据”。

   代码只做严格且可证明的事情：

   - support_text 必须能在同一 Evidence 找到，Evidence/anchor/ACL/stage/citation slot 必须全部合法；
   - 它不假装字符串规则可以证明 paraphrase（改写）与 support 之间的语义蕴含；
   - 为了减少 JSON 换行造成的假拒绝，只做 whitespace canonicalization（空白规范化），不做 fuzzy（模糊）或语义近似放行。

   180 题 full Answer Eval 最终完成 **180 次 AnswerFlow、180 次 provider request、0 次自动 retry**，共使用 **405,305 tokens**。结果按“合同完整”和“真的答对”分开记：

   - 146/180 的 `answer_status=complete` 只表示回答合同完整走完；
   - 真正的 gold 对账显示，只有 **80/180（44.44%）** 题引用齐全部 gold 文档，平均 gold-document coverage 为 **49.3981%**；
   - 其中 multi-document all-gold 只有 **2/38（5.26%）**，semantic 题只有 **15/52（28.85%）**；
   - 另有 10 次 Composer unavailable 和 24 次 support contract rejected。

   因此 M34 最重要的结论不是“RAG 已经答得很好”，而是：**build → retrieve → authorize → answer → support → cite → score 已经成为可复现的真实链路，并且它可靠地暴露了系统还答不好的地方**。exact-fact 的逐字检查只有 1/180 全量命中，但这是保守字符串下限，也不能反向解释为开放语义正确率只有 0.69%；本模块没有引入 LLM Judge，不能给出尚未测量的语义正确率。

### 新概念

- **Closed-world validation（闭世界校验）**：先声明“合法输入和合法输出的全集是什么”，再拒绝缺失、多余、重复或身份漂移。它类似数据库迁移里的 schema checksum：不是只看程序能不能启动，而是确认程序处理的确实是那一版数据。
- **Logical ID / physical source instance**：logical ID 是 benchmark 对文档的业务编号，physical instance 是磁盘上的具体副本。可类比 MySQL 中的“业务单号”和“带版本的行记录”：业务单号相同，不代表两行正文可以互相覆盖。
- **Retrieval unit recipe**：从 normalized document 生成检索片段的一组版本化规则，包括长度、分段与 overlap。它不只是调参，因为会改变索引规模、Evidence identity、citation anchor 和 Eval 可比性。
- **External profile**：与业务知识 release 分开的不可变大语料构建物。它复用 Knowledge Tool 接口，但有独立 corpus/index identity 和 active pointer，避免 benchmark 污染业务知识。
- **Gold coverage / all-gold / MRR**：coverage 看标准文档找回了多少；all-gold 要求一题需要的文档全部找齐；MRR 关注第一个正确结果排得是否靠前。多文档题只命中一半时，MRR 可能好看，但 all-gold 会如实失败。
- **`support_text`**：模型为自然语言 claim 提供的原文支持片段。它解决“citation 指向哪份 Evidence”，但不能单独证明复杂改写在逻辑上一定成立，所以后续语义 Judge 仍是独立能力。
- **Checkpoint + identity**：长任务每完成一小段就原子记录进度，并绑定同一份配置身份。发生欠费、TLS EOF 或进程退出时，只能从已确认前缀续跑，不能拿数据库物理 row count 猜进度。

### 代码阅读路线

1. **从数据边界开始**：`engine/rag/enterprise_dataset.py`、`eval/cases/enterprise-rag-bench-v1.0.0-dataset.json`

   先看 dataset recipe 如何冻结 release、三种来源、官方资产 hash 和预期分母，再看 scanner 如何建立 logical/physical/corpus/question identities。重点理解 **为什么冲突 ID 不覆盖、重复 gold 不去重**；具体 SHA-256 拼接格式无需先死记。

2. **跟随一篇文档完成“清洗和切片”**：`engine/rag/enterprise_parser.py` → `engine/rag/enterprise_units.py`

   parser 负责保守恢复结构性换行并生成 normalized revision；unit builder 再按 paragraph-2400 recipe 输出稳定字符 offset、unit identity 和正文 hash。阅读时抓住 `raw → normalized document → retrieval unit → source anchor` 这条线，它解决的是**检索片段如何回到未经篡改的来源**。

3. **看大语料如何安全落盘和激活**：`engine/rag/enterprise_profile.py`

   先看 immutable profile 的 metadata/units/FTS 结构，再看 building、verify、atomic rename 和 active/previous pointer。这里最关键的不是 SQLite API，而是 **candidate 只有完整校验后才能成为可加载 profile**，损坏构建不能替换当前 active。

4. **看真实查询如何进入旧 Knowledge Tool**：`engine/rag/enterprise_runtime.py` → `engine/rag/knowledge_tool.py`

   `enterprise_runtime.py` 负责把 profile 适配成 metadata-only bundle、retriever 和 context loader；Knowledge Tool 先在 metadata 上做 pre-selection ACL，命中后才加载正文并复核 pre-generation authorization。这样既避免 14 万段正文常驻内存，也不让外部 adapter 绕过 M31/M32 的门禁。

5. **沿着 Evidence 走到自然回答和引用**：`engine/rag/evidence.py` → `engine/rag/answer_flow.py` → `engine/rag/enterprise_generation.py`

   先看 Evidence 新增的 logical/physical/unit/offset 坐标，再看 AnswerFlow 如何把 selected 推进 generation-visible，最后看 Qwen Composer 输出 `text + support_text + evidence_id + anchor`。重点理解 **support_text 先通过同 Evidence 逐字校验，citation 再由代码分配和验证**；模型不能自己宣布引用有效。

6. **最后读两层 Eval，理解数字从哪里来**：`engine/rag/enterprise_retrieval_eval.py` → `engine/rag/enterprise_answer_eval.py` → `scripts/run_m34_answer_eval.py`

   Retrieval Eval 只评价 Tool 找回了哪些文档；Answer Eval 每题只执行一次真实 AnswerFlow，再在返回后加入 gold 做 coverage、failure、latency 和 token 投影。脚本负责 checkpoint/resume，不负责放宽评分。这里解决的是**运行输入不泄露答案、失败不丢分母、长任务中断后不重复付费**。

核心数据流是：

`项目外 raw/extracted`
→ `strict scanner + identities`
→ `source-aware parser`
→ `paragraph-2400 units`
→ `immutable external profile / FTS or Milvus candidate`
→ `Knowledge Tool + ACL`
→ `Document Evidence + context loader`
→ `AnswerFlow + Qwen Composer`
→ `support_text + Citation Validator`
→ `retrieval/answer artifact + gold 后置评分`

### 设计要点

- **不合并业务 release**：benchmark profile 与 22 条业务知识分别发布和回滚，避免测试语料污染业务检索或改变既有 ACL。
- **身份先于分数**：dataset、corpus、parser、unit recipe、profile、split、adapter 和 artifact 都有 identity；没有这些身份，相同分数也不能证明两次实验可比较。
- **held-out 只用于裁决**：unit recipe 先在 60 道 dev 上确定，再打开 120 道 held-out，避免一边看最终答案一边调参。
- **semantic 用证据竞争默认值**：embedding 构建完成不等于方案更好；两个 split 都落后，所以保留 candidate，不切默认。
- **自然回答不放弃硬引用**：方案 B 允许 paraphrase，但 `support_text` 必须来自同一 Evidence；只修复空白差异，不用 fuzzy matching 偷渡不确定支持。
- **技术失败与业务质量分开**：provider unavailable、contract rejected、answer complete、gold coverage 是不同事实，不能全部压成一个“成功率”。
- **成本成为 artifact 的一部分**：full Eval 记录 prompt/completion/total tokens 和每题 attempt，取消 800-token 应用上限后不再宣称固定费用上界。
- **明确没有做的事**：没有接 Router、Hybrid、UI、通用评测平台或 LLM Judge；没有提交 raw/extracted/SQLite/Milvus 大文件，也没有证明生产 connector ACL。

### 有面试价值的亮点

1. **大语料只换“进料口”，门禁和验货流程一个没动。**36,417 篇文档独立建 external profile、原子切换；运行时仍走 Knowledge Tool 的 ACL、Evidence、AnswerFlow 和 citation validator——不是第二套 RAG。
2. **semantic 用同一把尺子输了，就不切默认。**lexical 在 dev 和 held-out 都更高，embedding 的沉没成本不构成切换理由；保留 candidate 和新 identity，等真实失败簇和单变量 A/B。
3. **“说人话”必须附原文凭据，最后诚实报告质量。**自然语言 text + 逐字 support_text 的合同让代码只证明字符串层面的事实；180 题真实 Eval 只有 44.44% all-gold、多文档 5.26%——链路通了，质量短板也诚实摆出来。

### 面试官追问

1. **[基础追问] 你怎么证明这不是“下载了数据，再写几个离线搜索脚本”？**

   M34 的验收证据跨过了四层：第一，36,417 篇文档经过 closed-world scanner、parser 和 unit builder，形成可校验 profile；第二，检索通过真实 Knowledge Tool adapter，而不是实验函数直接查 gold；第三，命中结果经过 ACL、Evidence 阶段和 AnswerFlow，真正进入 Composer；第四，citation validator 与 Answer Eval 对同一轮 Evidence 做后置评分。真实 artifact 有 180 个 flow/provider calls、token、延迟和失败结构，所以它证明的是在线运行链，而不只是数据准备。

2. **[基础追问] 为什么一题要同时看 coverage、all-gold 和 MRR？**

   三个指标回答的问题不同。MRR 看第一个正确文档排得靠不靠前，适合单文档快速命中；coverage 看需要的文档找回了几成；all-gold 要求全部找齐。比如一道题需要两份文档，只把第一份排在第 1 名，MRR 会很好，但 coverage 只有 0.5、all-gold 为失败。M34 的 multi-document all-gold 只有 2/38，正说明不能只看 MRR。

3. **[工程/深挖追问] 为什么要新建 external profile，而不是扩展原来的 ReleaseBundle？这是不是重复建设？**

   两者复用的是运行接口，不应强行复用存储形态。原 ReleaseBundle 面向 22 条短知识，内嵌正文且一个文档对应单 anchor；external corpus 有 139,214 个 units、约 2.62 亿正文字符，多切片还需要独立 unit identity。强塞会放大内存并破坏 citation key，同时把 benchmark 与业务发布、ACL 和回滚绑在一起。external profile 只解决大语料存储、索引和命中后加载，Knowledge Tool、Evidence、AnswerFlow、validator 都仍是原模块，因此不是复制第二套 RAG。

4. **[工程/深挖追问] embedding 构建花了不少时间，为什么最后仍用 lexical？**

   因为技术选择看 held-out 结果，不看投入沉没成本。semantic 在 dev 的 coverage@20 是 0.7375，低于 lexical 的 0.810417；held-out 是 0.773958，仍低于 lexical 的 0.823125，MRR 也更低。它可能需要更好的 embedding、query 表达、hybrid 或 rerank，但这些是新变量。正确做法是保留 collection 和 identity 作为 candidate，下一轮围绕明确失败簇做单变量 A/B，而不是为了证明前面的成本值得就切默认。

5. **[工程/深挖追问] 为什么 support_text 逐字存在，仍不能说回答一定正确？**

   它只能证明“模型给出的原文凭据确实来自这份 Evidence”，不能证明自然语言改写没有扩大、曲解或遗漏原意。M34 故意只让代码判断可确定的字符串与身份合同，没有把语义蕴含伪装成确定性规则。未来若要评价改写正确性，需要独立的人工标注或 Judge 合同；但在那之前，support_text 至少阻止了完全没有原文依据的 citation。

6. **[压力追问] 你跑了 180 题、花了真实调用费用，最后 all-gold 只有 44.44%，这是不是说明模块失败了？**

   这个质疑对“答案质量已经提升”是成立的：M34 没有证明这一点，而且多文档 5.26% all-gold 很差。但模块目标不只是刷一个总分，而是把原来玩具化的知识链换成可复现的真实压力证据。现在我们能区分是检索漏了 gold、Composer 不可用、support 合同被拒绝，还是回答链完整但引用错文档；此前 22 条短知识的全绿测试看不到这些问题。工程链已经打通，质量短板也被量化，下一步可以针对 retrieval 和 context packing 做受控实验，而不是盲目改 prompt。

### 验证与下一步

- **数据与构建证据**：36,417 documents、139,214 units；profile 独立 reload 后 identity、count 和 database SHA 一致，原始/派生大文件未提交仓库。
- **Retrieval Eval**：60 dev + 120 held-out 全部 completed；lexical 两个 split 都胜过当前 semantic candidate，因此 external 默认保持 lexical。
- **Answer Eval**：180/180 flow calls、180/180 provider requests、0 retry、405,305 total tokens；artifact identity 为 `d9fa2b20863c568cbc7091dea4724c5d69d74979b5b4ba3d3eb14ff101eeb41f`。
- **确定性回归**：M30–M34 相关聚焦套件 **158 passed in 4.47s**；生成/安全聚焦套件 **40 passed**；`compileall` 通过。
- **全仓边界**：full pytest 在非 M34 测试阶段长时间没有可靠终态，进程已停止，所以只能记录为 **inconclusive**，不能写成全仓通过。
- **下一步建议**：先离线分析 lexical top-k 漏召回、multi-document gold 分布和 selected context budget，再规划新的 retrieval/context-packing 模块；未经新计划和费用确认，不重跑大规模 provider、不切 semantic 默认、不放宽 support/citation 合同。

可复制验证命令：

```powershell
# M30–M34 相关合同回归；预计看到 158 passed，不访问真实 provider。
python -m pytest --basetemp=.agent_work/temp/pytest-run-m34 tests/test_m30_knowledge_catalog.py tests/test_m31_governance.py tests/test_m31_evidence_citation.py tests/test_m31_phase4_contracts.py tests/test_m31_release.py tests/test_m32_knowledge_tool.py tests/test_m32_rag_retrieval_contracts.py tests/test_m32_retrieval.py tests/test_m33_answer_flow.py tests/test_m33_knowledge_expansion.py tests/test_m33_rag_answer_contracts.py tests/test_m34_enterprise_answer_eval.py tests/test_m34_enterprise_case_split.py tests/test_m34_enterprise_dataset.py tests/test_m34_enterprise_generation.py tests/test_m34_enterprise_lexical_experiment.py tests/test_m34_enterprise_parser.py tests/test_m34_enterprise_profile.py tests/test_m34_enterprise_retrieval_eval.py tests/test_m34_enterprise_runtime.py tests/test_m34_enterprise_semantic.py tests/test_m34_enterprise_units.py -q

# 只做 Python 语法/导入编译检查；预计无输出并以 exit 0 结束。
python -m compileall -q engine app eval scripts tests
```

**本地启动体验：** M34 **暂无独立 API 或页面**，因为本模块只把 external corpus 接入内部 Knowledge Tool/AnswerFlow，并明确不扩展 Router、Hybrid 或 UI。最安全的体验方式是运行上面的离线聚焦回归，再只读查看 `.agent_work/temp/m34-answer-eval-full-v4.json` 的 summary、group summaries 和 failure counts。若要重建 profile 或重新调用真实 Qwen，必须显式提供项目外 dataset root，并重新确认数据路径、Milvus、provider 费用和运行范围；不要为了“体验一下”直接重跑 180 题。

## ★ ★ ★ Phase 4 上半阶段总结：M29–M34

（2026-08-18）

**简述**：Phase 4 上半阶段没有急着把 RAG 包进一个“会自己循环的 Agent”，而是先把 **知识从哪里来、谁能看、检索经过什么步骤、回答引用什么证据、失败时泄露什么，以及效果到底怎样** 做成可执行、可追踪、可评测的工程闭环。它对应 roadmap 的 **P0 合同冻结、P1 权威知识与治理、P2 确定性 RAG 纵切**；M35 开始的 P3 顶层 Harness 属于下半阶段，不计入本总结。

### 先用大白话讲

以前 DataPilot 会做 NL2SQL（把问题翻译成 SQL 查数据库），也有几张"知识文档"，但它还称不上一间可靠的企业资料室。当时有四个明显漏洞：

- **文档可能混进 SQL 通道**：政策文件可能被 SQL 引擎当成业务表去查；
- **访客身份靠自报**：请求里填什么角色就算什么角色，没有服务端认证；
- **没有流水账**：检索到了什么、最终引用了什么，对不上账；
- **跑通 ≠ 答对**：接口返回成功，不代表答案正确。

这一阶段做的事，就是给这间资料室补上制度和流水线，像管理一家真实公司的档案室一样：

- **明确岗位**：资料室（知识原件）、查询窗口（检索）、答复窗口（生成）、审计记录（Trace/Eval）各管一段，谁也不越权；
- **版本化管理**：制度原件登记成可发布、可回滚的知识版本，像发新版员工手册——要么整体生效，要么维持旧版，不能发一半；
- **门卫查两遍**：检索前查一次、材料交给撰稿人前再查一次，只认系统认证的身份，不认访客自报的角色；
- **检索员只管找**：找到材料就交差，能不能回答、答成什么样不是它说了算；
- **撰稿人只用真送进来的材料**：写进答案的每一句引用都必须能回指原文，不能凭记忆编；
- **最后上大考**：用 3.6 万篇文档、180 道固定题的外部基准压测，诚实记下"链路跑通"和"答案答对"之间的差距。

所以这一阶段最重要的成果不是一句"项目支持 RAG"，而是建立了一条 **从知识发布到可信引用、从安全失败到离线评测都有明确合同的 RAG 基线**。

### 这次做了什么

这一阶段处理的不是六个彼此独立的模块，而是一个连续工程矛盾：**怎样让“查文档并回答”从一个能跑的功能，变成一条知道资料来源、遵守权限、保留证据、能够失败、能被客观评测的可信链路。**整个过程分四段主线。

1. **先把“什么算成功”说清楚，避免后面的实现各说各话。**

   阶段起点不是缺一个向量库，而是缺共同合同：

   - 路由选对 ≠ 工具执行成功；
   - 工具执行成功 ≠ 生成了回答；
   - 生成了回答 ≠ 没有越权。

   为此，P0 先拆开两个基础口径：

   - **四轴状态**（`route / execution / answer / safety`）：一次请求用四条独立坐标分别记录“该走哪条路、执行成没成、回答完没完、安全过没过”，而不是把所有结果压成一个成功/失败布尔值。
   - **Evidence 四阶段**（`candidate → selected → generation_visible → cited`）：普通话解释就是“**搜到过、挑中了、真的给模型看过、最终被回答引用过，是四件不同的事**”。

   同时冻结了三项合同：

   - **TrustedCaller**：调用方身份必须由服务端解析，请求里自报的 `role` 不能当授权事实；
   - **outbound 默认拒绝**：数据要发给外部模型或服务，必须按“接收方 × 用途 × 数据类别 × 字段”显式放行，没有规则就拒绝；
   - **Eval 闭世界身份**：一次评测如果缺执行、重复执行或串了别的 run，也不能算通过。

   这样选择比“先写一个能返回答案的接口”更慢，但避免后续检索、回答、Trace 和 Eval 分别发明自己的成功口径。

   **P0 的证据**：既有 SQL 主链没有被破坏，合同与安全门完成冻结。它证明的是地基明确，不是 RAG 已经上线。

2. **再把知识变成有权威来源、能原子发布、也不会串进 SQL 的受治理资产。**

   原来的知识可能同时存在于 Markdown、seed 和旧表中，就像一家公司同时有三份“最新版制度”，出了冲突没人知道该信谁。

   上半阶段因此做了三件事：

   - **source-backed catalog（源头目录）**：政策 Markdown 与指标投影是唯一权威原件，数据库表和索引只是派生的运行时投影。7 份政策 Markdown 与 4 份指标投影先形成 11 条规范目录项，完整校验后发布成不可变 release；后续扩展为 22 条时，仍沿用同一发布合同。
   - **不可变 release + active pointer（原子发布）**：新版本完整构建、校验通过后，active pointer 才一次切换到新版本；失败时继续服务旧版本。rollback（回滚）同样要重新验证，不能在损坏时偷偷回落到某个旧版本。
   - **SQL 与知识隔离**：物理数据库仍保留 14 张表，但 Text2SQL 的可查询面收紧为 13 张。遗留 `knowledge_docs` 没被破坏性删除，却退出 schema 检索和 SQL 生成边界，schema 文档从 195 条降为 186 条。这个取舍兼顾兼容与隔离：**RAG 知识继续存在，但 SQL Agent 不能把政策文档误当业务表查询。**

   治理还覆盖运行期安全：

   - **双重 ACL（访问控制列表）**：文档权限在“候选选择前”和“生成上下文前”各检查一次；
   - **出站策略**：按 `receiver × purpose × data class × fields` 精确放行，缺规则就拒绝；
   - **安全错误投影**：对外错误只给安全文案，不能借拒绝信息暴露未授权文档的标题或 ID。

   所以权限不是接口末尾的一次过滤，而是 **从本地资料到模型上下文的完整数据流约束**。

   **验证**：首版治理落地后，全仓回归 **231 passed**；`phase4-v1` 的 8 个场景、12 个 required check 全部通过，全仓回归 **276 passed**。

3. **把检索和回答拆开，再用 Evidence 把它们严谨地接起来。**

   如果一个“RAG 工具”既找材料又写答案，召回错、权限错、生成错和引用错会混成一个黑盒。

   - **Knowledge Tool（知识工具）**：只负责取证，按 `pre-ACL → retrieve → candidate → select → post-ACL → selected → safe projection` 运行，产出受治理的 Document Evidence，却不替回答层下结论。
   - **首个 adapter 选确定性 lexical（关键词检索）**：不是因为它更先进，而是因为它 **离线可复现、失败容易定位、没有默认外发成本**，适合作为长期对照基线。对应检索 Eval 的 6 个场景、20 个 required check 全部通过，全仓回归 **304 passed**。

   在此之上，**AnswerFlow** 才把 selected Evidence 送入共享安全门和 composer（生成器）：

   - 只有真的进入模型上下文、并被 claim（答案断言）使用的材料，才升级为 `generation_visible`；
   - 只有 support（逐字证据片段）、anchor（原文定位）与 Evidence 身份全部通过代码校验，citation 才能升级为 `cited`；
   - composer 输出不合合同就 fail closed（失败关闭），不公开半成品 claim 和 citation。

   这比把 top-k 全部挂到答案后面更严格，但保证了 **“引用过”不是 UI 装饰，而是可回查的执行事实**。

   **验证**：回答合同 Eval 的 9 个场景、60 个 required check 全部通过，知识扩容后的全仓回归 **342 passed**。

4. **最后用大语料和真实模型揭露效果，而不是用小样例宣布胜利。**

   22 条业务知识足以证明合同，却不足以证明大规模检索质量。P2 后段因此接入独立 EnterpriseRAG-Bench profile：

   - 36,417 篇企业风格文档被解析为 139,214 个稳定检索单元；
   - 问题固定切成 **60 dev（诊断集）** 与 **120 held-out（保留集）**；
   - 外部 profile 与业务 22 条 active release 隔离，避免实验污染运行默认。

   在相同数据和 top-k 下做 A/B：

   | 检索方式 | held-out @20 gold coverage / all-gold / MRR |
   | --- | --- |
   | lexical | **0.823125 / 0.775000 / 0.723134** |
   | semantic candidate | **0.773958 / 0.741667 / 0.630477** |

   > **gold coverage** = 标准答案文档的召回覆盖；**all-gold** = 全部标准文档都被覆盖；**MRR** = 平均倒数排名，衡量相关文档排得靠不靠前。

   semantic 没赢，因此系统没有因为“向量检索更像 RAG”就切换默认。

   真实 Qwen Answer Eval 又执行了 **180 次 AnswerFlow、180 次 provider request、0 retry、405,305 tokens**：

   - 146/180 达到合同完整；
   - gold document all-cited 只有 **80/180（44.44%）**；
   - multi-document all-gold 只有 **2/38（5.26%）**。

   **阶段最终结论**：`build→retrieve→answer→cite→score` 的工程闭环已经成立，但回答质量远未完成。

   - `complete` 只说明结构和引用合同合法，不等于事实正确；
   - 合成企业基准也不能替代真实租户 ACL、真实连接器和线上容量证据。

   上半阶段最重要的价值，是把下一步问题从含糊的“RAG 效果不好”收敛成可定位的三类问题：**召回覆盖、多文档上下文、composer support**。

### 阶段主线图

```text
M29 合同冻结
  │  四轴状态 / Evidence 阶段 / trusted caller / outbound / Eval 闭世界
  ▼
M30 权威知识与 SQL 隔离
  │  source-backed catalog / staged publish / knowledge_docs 退出 Text2SQL
  ▼
M31 治理底座
  │  双重 ACL / typed ledger / citation slots / immutable release
  ▼
M32 Knowledge Tool
  │  确定性检索 / candidate→selected / 安全投影
  ▼
M33 AnswerFlow
  │  generation_visible→cited / extractive support / fail closed
  ▼
M34 大语料与真实 Eval
     独立 profile / dev-heldout / lexical-semantic A/B / Qwen Answer Eval
  ▼
交给 M35/P3：顶层 Harness、Router 与统一执行入口
```

这条主线的核心是：**先定义可信事实，再发布知识；先治理 Evidence，再做工具；先让单次 RAG 可解释，再交给 Agent 编排。**

### 关键知识点串联

- **RAG 不只是“向量库 + 大模型”**：

  完整 RAG 至少包含 **知识生产、版本发布、权限过滤、召回、上下文选择、生成、引用校验和效果评测**。向量检索只是其中一个可替换 adapter；M34 的结果甚至说明，在当前切分、模型和语料下，semantic candidate 并没有赢过 lexical baseline。

- **Evidence 是贯穿系统的中间语言**：

  Evidence ledger 把检索和回答从“两个黑盒函数”变成一条可追踪状态机：

  - `candidate`：检索器发现过；
  - `selected`：经过选择和权限门；
  - `generation_visible`：真的进入模型上下文；
  - `cited`：真的被回答引用且通过验证。

  因此系统能回答的不只是“最后说了什么”，还包括 **哪条材料在哪一步被留下或淘汰**。

- **安全必须参与数据流，而不是最后补一层过滤**：

  TrustedCaller、双重 ACL、安全响应投影和 outbound allowlist 共同约束了数据从本地知识到外部模型的路径。**拒绝本身也必须安全**：如果错误响应暴露了被拒文档的标题或 ID，权限门虽然拒绝了正文，仍可能发生侧信道泄露。

- **不可变发布解决的是“运行中的一致性”**：

  知识库不是把文件写进表就结束。不可变 release 和 active pointer 让一次发布要么完整生效，要么完全不影响当前版本；回滚也是显式动作。它与数据库 migration 很像，但对象是 **检索与回答依赖的知识快照**。

- **检索完成、回答完成、回答正确是三件事**：M34 最有价值的结论之一，是把指标分层：

  - provider 返回成功，只代表远程调用完成；
  - `answer_status=complete`，只代表回答和引用满足合同；
  - gold docs 被覆盖，才说明检索/引用碰到了标准材料；
  - 事实是否正确，还需要更可靠的语义 scorer 或人工/judge 证据。

  **146/180 complete 与 80/180 all-gold cited 同时成立**，正好说明不能拿运行成功率冒充回答质量。

- **Eval 的身份和切分也是产品合同**：

  M34 为物理数据、逻辑文档、corpus、question 和 split 都建立稳定 identity，并把 dev 与 held-out 分开。这样才能判断两次实验是否真的在比较同一份数据，也能防止边看最终答案边调参。

### 阶段设计取舍

1. **先做确定性 vertical slice，再做 Agent loop**：上半阶段需要一个稳定、可复现的被编排能力；否则循环只会反复调用一个边界不清的黑盒。
2. **source-backed catalog，而不是数据库双权威**：Markdown/metrics 是原件，数据库和索引是派生产物，避免内容漂移后无人知道该改哪里。
3. **保留遗留表但移出 SQL 可见面**：不为了表面整洁做破坏性删除，同时立即消除 Text2SQL 越界查询风险。
4. **ACL 前后各一道门**：第一道减少越权候选，第二道守住真正进入模型的上下文；两者防御的故障位置不同。
5. **Knowledge Tool 与 AnswerFlow 分层**：工具交付 Evidence，回答层消费 Evidence；这样召回、生成和 citation 可以分别评测、替换和复用。
6. **citation 由代码校验，不让模型自证**：模型可以建议引用，但不能自己宣布“引用合法”。
7. **semantic 失败就不切默认**：技术名词的新旧不构成上线依据，held-out 结果才构成依据。
8. **严格区分 contract complete 与 correctness**：宁愿公开 44.44% 的 all-gold cited，也不把 81.11% 的 complete 包装成准确率。这个阶段选择的是可证伪、可继续优化的基线，而不是好看的演示数字，汪。

### 有面试价值的亮点

一句话总起：我在 DataPilot 负责把"查文档回答问题"做成一条可信的企业 RAG 基线，这一阶段最有记忆点的是四件事。

1. **先把"什么叫成功"定义清楚了。**以前一次请求就是一个布尔值：路由错、执行挂、回答缺、越权，全混成同一个 failed。我把它拆成 route / execution / answer / safety 四轴，证据也拆成 candidate → selected → generation_visible → cited 四阶段——"搜到过"和"真的被引用过"是两回事。后来所有模块都沿这套口径走，8 个场景、12 个 required 合同锁死。
2. **知识从"三处随便改"变成"一处权威 + 原子发布"。**政策文档原来同时躺在 Markdown、seed、旧表里；我改成 source-backed catalog，发布用不可变 release，active pointer 一次切到位，坏了不偷偷回滚。权限在检索前和生成前各查一次，外发按"接收方×用途×数据类别×字段"显式放行——政策文档再也不会被 Text2SQL 当业务表查。
3. **检索和回答拆开，citation 不让模型自证。**Knowledge Tool 只管取证，AnswerFlow 才生成答案；只有真正进过模型上下文的证据才能被引用，support 和 anchor 全部由代码回查。这样召回错、生成错、引用错能分开定位，而不是一个黑盒。
4. **拿 3.6 万篇文档做了诚实的基线。**36,417 篇文档、180 题真实 Qwen Eval：semantic 候选在 held-out 上没赢 lexical，就没切默认，不为"向量检索"这个标签买单。结果是 81.11% 合同完成、all-gold cited 只有 44.44%——把"链路跑通"和"答案答对"分开了，下一步要优化什么也锁定了。

### 面试官追问

1. **[基础追问] 你说做成了“可信 RAG 基线”，可信具体体现在哪里，怎么避免只是在堆功能？**

   我把可信拆成了可以验证的工程合同：知识必须来自可追踪原件并通过不可变 release 发布；调用方身份必须由服务端解析；Evidence 必须记录 candidate、selected、generation_visible、cited 阶段；citation 必须由代码回查 support 和 anchor；Eval 必须绑定唯一执行。**每一层都有输入、输出、失败状态和验证证据**，所以它不是把向量库、模型和接口拼起来后统称为可信。

2. **[基础追问] 这一阶段最能说明效果的指标是什么？为什么不能只报 81.11% 的回答完成率？**

   81.11% 只说明 146/180 的回答满足 composer、support 和 citation 合同，不说明引用到了标准答案需要的文档。真正观察召回与引用质量，还要看 held-out retrieval coverage、gold document all-cited 和 multi-document coverage。**80/180 all-gold cited 与 2/38 multi-document all-gold** 才暴露当前质量短板；如果只报 complete，就会把“格式合法”误讲成“答案正确”。

3. **[工程/深挖追问] 为什么要先花一个模块冻结合同？直接实现后再重构不是更快吗？**

   在单一接口里可能更快，但这里同时涉及 SQL、RAG、权限、外部模型、Trace 和 Eval。若不先定义四轴状态和 Evidence 阶段，路由成功、工具成功、回答成功会被压成同一个布尔值，后续重构不仅改代码，还会改 API、报告和历史基线。**先冻结少量跨层不变量，代价是前期多做设计，收益是后续每个模块都能沿同一口径增量验证。**M30 到 M34 的能力扩展没有推翻这套合同，就是它有效的实际证据。

4. **[工程/深挖追问] ACL 检查两次会增加复杂度，你怎么证明这不是重复防御？**

   两道门保护的边界不同。pre-ACL 防止未授权文档进入正常候选与选择流程，post-ACL 保护真正送入生成上下文的数据，因为中间还可能出现缓存、合并、重排或新 adapter。测试不仅覆盖允许路径，还覆盖拒绝后的安全投影，确保外部看不到被拒文档身份。**如果只保留第一道门，任何中间层缺陷都可能把越权 Evidence 带到外部模型；只保留第二道门，则内部候选和日志面会无谓扩大。**

5. **[工程/深挖追问] semantic retrieval 没赢，是 embedding 模型不行、切分不行，还是评测有问题？**

   当前证据只能说明：在冻结的 corpus、paragraph-2400 unit recipe、问题切分、top-k 和当前 semantic candidate 下，它没有赢 lexical，不能直接归因到单一组件。dev 与 held-out 方向一致，降低了偶然性，但还不能排除 embedding、query 表达、索引参数、rerank 或 context packing 的影响。**所以正确工程动作是保留可复现实验身份与 lexical 对照，针对错因继续 A/B，而不是笼统宣布“向量检索不适合”。**

6. **[工程/深挖追问] 你用逐字 support 校验 citation，会不会过于严格，导致模型明明答对了也被拒绝？**

   会，这正是 24 次 composer contract rejected 所揭示的代价。当前代码能可靠证明 support 出现在 Evidence 中、身份和 anchor 合法，却不能可靠证明任意 paraphrase 与原文语义等价。为了不把未经证明的自然语言关系包装成安全保证，这一阶段只允许 claim 自然改写，同时要求附带逐字 `support_text`，并只做 whitespace canonicalization。**它牺牲一部分完成率，换来 citation 可审计；语义蕴含应由独立 scorer 或 judge 补充，不能偷偷放宽成 fuzzy match。**

7. **[工程/深挖追问] 知识 release 为什么要不可变和原子切换？普通数据库更新有什么实际问题？**

   普通逐条更新可能让一个请求读到半新半旧的知识集合，也会让 Eval 无法复现当时到底查询了什么。不可变 release 先在旁路完整构建和校验，再通过 active pointer 一次切换；失败时旧版本继续服务，回滚目标也必须重验。**这和蓝绿发布相似，解决的是运行一致性与可追溯性，而不只是保存文件。**

8. **[压力追问] 你做了这么多治理，最后 all-gold cited 只有 44.44%，是不是典型的工程自嗨？**

   这个质疑对“已经做成高质量企业问答”的说法完全成立，因为 44.44% 和 multi-document 5.26% 明确不够好。我的阶段目标不是用治理替代质量，而是先建立一条不会把权限、引用和成功率说假的纵向基线；已完成的证据是 36,417 篇文档能够经过同一 Knowledge Tool、AnswerFlow 和 citation 链完成 180 题闭环，并且 dev/held-out、失败类型和 token 用量都可复现。下一步应该根据这份基线优化召回、上下文打包和多文档覆盖，再用同一 held-out 口径判断是否真实提升。**所以可以说治理闭环完成、质量问题被量化，不能说 RAG 效果已经完成**，喵。

### 阶段成果与边界

**已经具备：**

- **权威知识生命周期**：source-backed catalog、不可变 release、原子 active pointer、显式 rollback；
- **SQL/RAG 数据边界**：知识文档不再暴露给 Text2SQL；
- **可信安全链**：TrustedCaller、双重 ACL、默认拒绝的出站策略和安全失败投影；
- **可审计 Evidence 链**：candidate、selected、generation_visible、cited 全阶段可追踪；
- **可组合 RAG 深模块**：Knowledge Tool 与 AnswerFlow 职责分离；
- **可复现评测基线**：小型合同 Eval + 大规模外部 profile + dev/held-out + 真实 Qwen Answer Eval；
- **诚实的默认选择**：semantic candidate 未赢就不切默认，业务 22-entry release 也不被外部基准污染。

**没有完成或刻意不在上半阶段做：**

- **没有顶层 SQL/RAG Router 和统一 API 执行入口**：这是 M35/P3 的职责；
- **没有有界 Agent loop、多轮 thread、恢复或人工介入编排**：属于下半阶段 Harness 能力；
- **没有 Hybrid retrieval 和查询级自动策略选择**：上半阶段只留下 lexical 默认与 semantic 候选的可信基线；
- **没有解决大语料 multi-document 召回和上下文打包质量**：M34 已量化问题，但没有假装已经优化完；
- **没有生产级认证、真实租户 ACL、外部 SaaS 连接器和线上容量证明**；
- **没有把合同完整率当成语义正确率**：开放语义质量仍需要更强 scorer、judge 或人工证据。

所以更准确的阶段结论是：**Phase 4 的 P0–P2 已完成，企业 RAG 的治理与评测地基已经建立；RAG 质量、Agent 编排和生产化仍是后续工程，不应被提前宣布完成。**

### 下一阶段怎么接

从上半阶段交接视角，下一步是 M35/P3：让顶层 LangGraph Harness 消费已经稳定的 SQL 与 RAG 深模块，统一 Router、Trace、API 和 Eval 的执行语义。之后再逐步加入有界循环、thread 状态、恢复、Hybrid retrieval、上下文治理和失败策略。

这个顺序成立的原因是：**M29–M34 已经把“工具调用一次时必须满足什么”说清并做实，M35 以后才能安全回答“Agent 何时调用哪个工具、失败后怎么办、何时继续或停止”。**下文 M35–M40 记录的正是这条下半阶段路线；它们不反向算入本总结的完成范围。

## ★ M35 顶层 LangGraph Harness 与 SQL/RAG Router

（2026-08-16）

**简述**：用一个**单轮顶层 LangGraph Harness** 统一接管 SQL、RAG 和保守终止，让 `/api/query`、Trace 与 Eval 对同一次执行说同一种“四轴语言”。

### 先用大白话讲

M35 解决的是“系统已经有两支专业队伍，却没有统一调度台”的问题。Text2SQL 会查数据库，RAG AnswerFlow 会查文档、做权限检查和引用校验；但此前它们各自成立，普通 `/api/query` 还没有一个可信的总入口决定：**这题该交给谁、能不能执行、最后到底是答完了、需要澄清、技术不可用，还是被安全规则拦住**。

这次的 Harness 可以类比一栋楼的**前台 + 固定排班**：你问“6 月 GMV 是多少”，前台把你引到数据库窗口；问“退款政策是什么”，引到文档窗口；问“帮我删掉订单表”，前台直接拒绝，连门都不让进。Router 就是那个前台，Harness 是那套排班规则——**一次请求只派一个专家、办完就收工**。它不把 SQL 生成、知识检索重新实现一遍，只负责路由、调用一个深 Tool、汇总状态并停止；**API、JSONL Trace 和 Eval 都从同一个 `AgentRunResult` 投影**，不会再出现 API 说成功、Trace 说 blocked、Eval 又按另一套规则判卷的情况。

这个版本刻意只做**单轮、最多一个 Tool**：没有恢复循环、thread、Hybrid 双路汇合、远程 Router 或生产登录系统。M35 的价值是先把“调度一次并诚实结束”做成可靠地基，下一阶段才有资格讨论失败后要不要重试或补问。

### 这次做了什么

这一步的矛盾是：SQL 和 RAG 必须走进同一个用户入口，但引入 LangGraph 不能拆坏已经验证过的 Text2SQL、ACL、Evidence、AnswerFlow 和 Citation Validator。最终答案是**浅编排、深 Tool、单一事实投影**——Graph 只负责调度，两条专业链路原样保留，所有出口从同一份执行结果读数据。

1. **建立唯一的单轮 Harness，而不是再写一套业务流水线**

   M35 之前，`/api/query` 基本是 SQL 专属入口，M33 的 `RAGAnswerFlow.run()` 虽然内部可信，却没被接到统一 Router、HTTP 响应和全局 Trace。摆在面前的是两个坑：继续在 API 里堆 `if SQL / elif RAG`，路由、状态和失败话术会散落在不同层；反过来把 Text2SQL 和 AnswerFlow 的每个内部步骤都画成 Graph 节点，顶层图又会和深模块争夺控制权。

   于是有了 **Harness**——一张受控执行地图，不是“更聪明的模型”。拓扑固定为 `START → route → (sql_tool | rag_tool | terminal) → controller → END`：Router 只选路径，Tool 只交回 Observation（工具执行回执），controller 是唯一能写最终四轴（route / execution / answer / safety）和终止动作的地方。DB Session、Router 和 Tool adapter 通过 LangGraph runtime context（每次执行注入的依赖容器）传入，不塞进要持久化的 state；`graph_steps` 用显式 reducer（只追加、不覆盖的合并规则），将来加分支也不会悄悄抹掉审计顺序。

   这张图刻意不做 checkpoint、Store、interrupt 或循环——那些是 P4 才处理的问题。测试覆盖了固定拓扑、每轮最多一个 Tool、terminal 可终止、非法 caller 失败关闭，全仓 397 条测试通过；但它只证明“调度一次并诚实结束”，不证明多轮恢复或长期记忆。

2. **把 Text2SQL 与 RAG 保持为两个深 Tool，并让失败各归各位**

   旧 SQL 链路有个很坑的习惯：不管出了什么事，都往 `blocked_reason`（安全拦截原因）里塞。“数据库暂时不可用”和“你触碰了安全规则”天差地别，对外却长成一个样子——用户以为是自己违规，Eval 也把技术故障误判成安全拦截。RAG 那边还有一层隐患：如果为了接入 Graph 就让它重新拼答案，M33 做好的 Gate（证据门）、Composer（撰写器）、Citation Validator（引用校验器）就全被绕过了。

   所以两个 adapter 的活儿压得很薄：**只做翻译，不重写逻辑**。SQL 侧只有真正执行成功，才生成 fingerprint（可复算的“结果指纹”）、SQL Evidence（结构化证据）和 ledger（记录本轮证据来源的账本）。失败则按性质分开出口：

   - SQL Guard 拦截 → 安全 `blocked`；
   - QueryPlan 输出投影不匹配 → 执行前确定性合同拒绝，`completed / no_answer / blocked`；
   - 确定性语义拒绝（比如请求了不存在的字段）→ `completed / unsupported / blocked`；
   - LLM 解析 JSON/SQL 失败 → `external_unavailable`（外部不可用）/ `no_answer` / `passed`，不写 `blocked_reason`；
   - 其余 driver、pipeline 技术故障 → `failed`，safety 仍为 passed。

   这是用户确认的**方案 A**。没有沿用“两类都 blocked”的旧兼容做法——那会让安全和故障继续混在一起；也没有把投影拒绝降级成普通技术错误——那会丢掉 SQL fidelity（SQL 与计划的输出一致性）这道保护。

   RAG 侧同样克制：每轮只调用一次 `RAGAnswerFlow.run()`，把四轴、validated citations、`docs_used` 和 EvidenceRef 的安全投影交给 Graph，**文档正文从头到尾不进入顶层 Trace**。

   这组映射有 7 条聚焦合同测试和全仓回归兜底，旧行为没有被接线冲掉；但本轮没跑真实 Text2SQL LLM Eval，证明的是“失败被正确分类”，而不是“远程模型更稳了”。

3. **让 caller 先可信，再允许 Router 调 Tool**

   请求体里的 `user_role` 本质上只是客户端自报的一行字符串：写什么就是什么。直接拿它去过 SQL RBAC 或文档 ACL，等于把权限判断交给用户自己——写个 `admin` 就可能提权。M31 虽然已经定义了 `TrustedCaller`（可信调用者），但普通 API 一直缺一个组装它的入口。

   用户确认的**方案 A**把这件事收窄成一个明确的 seam（接缝）：只有 `local/demo/test` 三个环境，由应用启动时注入 fixture resolver（测试夹具身份解析器）。它先给出一组固定的 caller 和完整角色集，请求里的 role 只能从中选一个 active role，不能现场造出新身份；其他环境没有 authenticated resolver，就在任何 SQL/RAG Tool 之前以 `caller_untrusted` 停下。Trace 会记 caller safe ref 和 fixture 来源，但不会把 demo 身份包装成生产认证。

   方案 B 要求所有环境手工注入 resolver，被否了：本地学习/demo 的默认入口会全部失效，还容易逼着开发者为“跑起来”在 API 里重新直信 role。方案 A 的风险是环境配置错误会让人误解信任等级，所以边界和测试必须一直保留。unknown role 在 Tool 前失败的 API/Trace 反例已经通过——它证明的是**本地 fixture 不越过自己的角色集合**，不是 JWT/OAuth、企业目录或 tenant/thread owner 已经实现。

4. **让 API、Trace 和 Eval 只读同一份执行事实**

   最难排查的 bug 不是直接报错，而是三个出口各自“合理地”解释同一次请求：API 按异常拼话术，Trace 按旧字段记状态，Eval 再重跑一遍或重新猜 route。这样哪怕测试全绿，测的也可能是三次不同的执行。

   M35 于是把 `AgentRunResult` 定为**单一事实源**，三个出口都只做投影、不许反写：
   - **API projector**：保留旧 SQL/rows/chart/docs_used 兼容字段，另加 execution/answer/reason/citations；
   - **Trace**：记录 route decision、graph steps、caller safe ref、Tool Observation、EvidenceRef 和 termination action；
   - **Eval**：独立的 `phase4-harness-v1` 对 Scenario、execution 和 assertion 做 closed-world（封闭清单）校验，并断言一题只 invoke 一次 Graph。

   两个“不做”也一起写进了合同：Eval 不为评分重新调用 Tool；M27、M31–M34 的历史 artifact 一律不改写成新格式，否则“一次执行、多处只读”的证据身份就破了。全仓 397 passed、compileall 和 diff check 通过，且 RAG Trace 不含文档正文。真实远程 Router、Milvus、external Composer/Judge 和 LangFuse Cloud 都没在 M35 运行，所以这一节证明的是投影一致性，不是这些外部链路的质量。

### 新概念

- **Harness（执行框架）**：包住多个专业 Tool 的薄编排层。可以类比 Spring MVC 的 DispatcherServlet：它决定请求交给哪个 handler、怎样统一收口，但不自己实现每个业务。
- **LangGraph runtime context**：每次执行临时注入的依赖容器，里面放 DB Session、Tool 和 Router。它类似 FastAPI `Depends` 或 Spring 注入的 service；与 Graph state 不同，它不是要跨节点审计或持久化的业务事实。
- **Reducer（归并器）**：多个节点写同一个 state 字段时采用的合并规则。M35 的 `graph_steps` 用 append reducer，类似给执行日志只追加、不覆盖，防止未来增加分支后丢失路径。
- **Tool Observation**：Tool 对本轮执行结果开的“结构化回执”，包含四轴、reason、EvidenceRef 和安全诊断；它不是最终回答，controller 才决定产品层怎样结束。
- **Fail closed（失败关闭）**：身份、路由或合同无法确认时宁可停止，也不猜一个默认 Tool 或默认权限。它类似 SQL Guard 遇到无法证明只读的语句时拒绝执行。
- **单向投影**：内部完整事实只能向 API/Trace/Eval 的安全视图转换，出口不能反过来修改 controller 判断。这样 `error_type` 只是兼容诊断，不会偷偷变成第二套状态机。

### 代码阅读路线

1. **先看系统在传递哪些事实**：`engine/harness/contracts.py`

   从 `HarnessRequest`、`RouteDecision`、`ToolObservation` 读到 `AgentRunResult`。重点看四轴、caller、EvidenceRef 和 termination 的不变量：这些 dataclass 就像 Java service 层的 DTO + invariant，不是一个什么都能塞的 `Map<String, Object>`。

2. **再看 Router 为什么会保守停下**：`engine/harness/router.py`、`engine/harness/caller.py`

   Router 只返回封闭的结构化决定，不直接调用 DB/RAG；caller resolver 则先把请求 role 限制在可信角色集合内。阅读重点是 **unknown/Hybrid 不 fallback、未解析 caller 不进 Tool**，具体关键词规则只是首版 deterministic fixture，不必背。

3. **沿 SQL/RAG 两条深 Tool 接口读失败翻译**：`engine/harness/adapters.py`

   先看 `Text2SQLToolAdapter.run()` 怎样在新/legacy pipeline 之间选择，再看 `_sql_observation()` 如何区分 Guard、语义拒绝、projection、provider 与 driver；最后看 `RAGToolAdapter.run()` 为什么只消费 `RAGAnswerFlow` 安全结果。这里解决的是**接线而不重写专业模块**。

4. **看 Graph 怎样保证一轮只走一条路**：`engine/harness/graph.py`

   从 `_route_node()` 开始，沿 conditional edge 到 SQL、RAG 或 terminal，再到 `_controller_node()`。主角是 `run_harness()` 和唯一 controller；理解节点职责与终止即可，不需要先研究 LangGraph 所有高级功能。

5. **从 HTTP 入口检查“没有旁路”**：`app/main.py` → `app/api/query.py` → `app/schemas/agent.py`

   `app/main.py` 组装环境级 resolver；query route 依次解析 caller、构造 runtime、调用一次 Harness、投影 response 和 Trace；schema 保留旧字段并增加四轴/citations。关键设计是 `force_new_pipeline=false` 仍在 Tool 里面，API 不再分叉成第二条顶层链。

6. **最后读 Trace 与 Eval 如何复用同一结果**：`engine/trace/recorder.py` → `eval/harness_contracts.py` → `tests/test_m35_*.py`

   Trace 看安全白名单字段，Eval 看 execution/assertion identity 和 one-invoke 闭合，测试则覆盖 topology、caller tamper、SQL failure mapping、RAG citation 非泄露和 API/Trace 一致性。这里证明的是**同一执行事实被多个消费者读取，而不是多个消费者各跑一次**。

核心调用链是：

`POST /api/query`
→ `CallerResolver`
→ `HarnessRequest + HarnessRuntime`
→ `route`
→ `Text2SQLToolAdapter | RAGToolAdapter | terminal`
→ `controller / AgentRunResult`
→ `AgentResponse + JSONL Trace + Harness Eval`

**模块闭环**：M30–M33 已建立知识原件、ACL/Evidence、Knowledge Tool 与可信 AnswerFlow；M35 把它和既有 Text2SQL 一起接入公开查询入口。至此 Phase 4 P3 的“**一次请求、一个可信 caller、至多一个 Tool、一个最终状态**”已经可演示。

### 设计要点

- **深 Tool、薄 Graph**：Graph 只负责编排与最终状态，Text2SQL/RAG 内部验证继续由原深模块负责，避免双控制权。
- **四轴不混用**：execution 描述技术执行，answer 描述能否回答，safety 描述确定性安全裁决；`blocked_reason` 不再装技术异常。
- **caller 不是请求字段**：role 只能选择可信 resolver 已解析的权限，不能凭 JSON 自我授权；demo fixture 与生产认证必须明确区分。
- **保守 Router**：未知或 Hybrid 停止，不默认落到 SQL、RAG 或双后端；开放能力不足要如实暴露。
- **一个 result，多种投影**：API、Trace、Eval 不重新判断 route/四轴，减少口径漂移和重复执行。
- **当前边界**：没有 P4 loop/thread/context、P5 Hybrid、生产认证、远程 Router，也没有把 M34 external profile 接入默认 RAG。

### 有面试价值的亮点

1. **“接 LangGraph 最容易犯的错，就是把成熟流水线拆成一张大图”**：很多人一上 LangGraph 就把 Text2SQL 的 schema 检索、QueryPlan、SQL Guard 每一步都画成节点，图看着很完整，实际上顶层图和深模块开始抢控制权，安全步骤还可能被图跳过或重排。我反着来：Graph 固定成 `route → tool → controller`，两个成熟流水线整个包成深 Tool，顶层只管可信 caller、一次调用和唯一收口。一句话总结：**节点边界应该跟控制权一致，而不是跟函数数量一致**。

2. **“四轴状态把‘没答上’和‘触红线’分家”**：旧系统把 LLM 解析失败、数据库不可用和 SQL Guard 拦截全写成 blocked，监控和 Eval 全乱套。我按 route / execution / answer / safety 四轴拆开：LLM 挂了是 `external_unavailable`（execution 轴），没拿到答案是 `no_answer`（answer 轴），只有 SQL Guard 拦截才写 `blocked_reason`（safety 轴）。核心逻辑一句话：“服务暂时不可用”不是“用户违规”。

3. **“请求体里的角色，我只信一半”**：`user_role` 是客户端自报字符串，写个 `admin` 就能提权。我的做法是：local/demo/test 环境由 fixture resolver 注入固定身份，请求的 role 只能从解析出的角色里选一个，不能现场造；其他环境没有认证 resolver，就在任何 Tool 之前失败关闭。这是标准的 fail-closed：身份不明确时宁可停，也不猜一个默认权限。

### 面试官追问

1. **[基础追问] 为什么你把 Text2SQL 和 RAG 当成两个 Tool，而不是把内部每一步都做成 LangGraph 节点？**

   因为节点边界应该跟控制权一致，而不是跟函数数量一致。Text2SQL 已经拥有 Schema Retrieval、QueryPlan、SQL Guard 和执行合同；RAG 已经拥有 Knowledge Tool、Gate、Composer 和 Citation Validator。全部拆开会让顶层 Graph 也能跳过或重排这些安全步骤，形成双控制权。M35 只需要跨 Tool 路由和最终四轴，所以深 Tool 能让 Graph 更小、接口更稳定，也更容易注入 fake 做拓扑测试。

2. **[工程/深挖追问] LLM 生成失败为什么是 safety passed？用户明明没有拿到答案。**

   四轴回答的是不同问题。没有答案由 `answer_status=no_answer` 表达，provider/解析故障由 `execution_status=external_unavailable` 表达；safety 只回答有没有触发确定性安全裁决。若把技术故障也写成 blocked，监控会误以为用户违规，Eval 也无法区分模型不稳定和 Guard 拒绝。M35 仍把 QueryPlan projection mismatch 标成 blocked，因为它是执行前确定性 SQL 输出合同，而不是远程服务波动。

3. **[工程/深挖追问] 你怎么保证 API、Trace 和 Eval 不会各说各话？**

   三者都只消费同一次 `run_harness()` 产生的 `AgentRunResult`。API projector 不能重新路由，Trace recorder 不能重新计算四轴，Eval 也不重跑 Tool；closed-world artifact 还校验 Scenario、execution、assertion identity 和一题一次 invoke。测试会对照 response/JSONL 中的 route、steps、reason、caller 和 EvidenceRef，并检查 RAG Trace 没有正文泄露。

4. **[压力追问] 你的 Router 只是关键词规则，这也能叫 Agent 吗？是不是为了用 LangGraph 而用 LangGraph？**

   这个质疑对“通用智能路由”是成立的，M35 没有证明那项能力。模块目标是先建立可信的执行和停止合同：caller 必须可信、未知问题不能乱调用 Tool、每题最多一次执行、失败能按四轴归因。LangGraph 在这里提供显式状态迁移、conditional edge、runtime context 和后续 P4 的稳定 seam，而不是用来包装关键词。当前 Router 是可替换 baseline；只有 Trace/Eval 出现真实失败簇、远程出站得到授权后，才值得增加模型 fallback喵。

5. **[压力追问] 你加了一层 Graph，却没有让答案质量变高，这是不是工程自嗨？**

   如果目标是当场提高召回或生成质量，这个模块确实没有做到，也没有这样宣称。它解决的是原系统无法安全组合 SQL/RAG、状态口径会漂移、请求 role 不可信以及评测可能重复执行的问题。397 条回归、caller tamper、one-invoke、Trace 非泄露和错误分类证明这些工程合同成立。下一阶段的恢复或 Hybrid 如果没有这层预算、终止和证据 seam，很容易变成无界重试或双 Tool 乱跑；但是否进入 P4、先恢复哪类失败，仍要用真实失败数据决定喵。

### 验证与下一步

- **方案 A 聚焦合同**：`7 passed, 1 warning in 23.00s`，覆盖 output-projection blocked 与 LLM `external_unavailable` 的最终映射。
- **全仓确定性回归**：`397 passed, 1 warning in 555.68s (9:15)`；warning 是既有 FastAPI TestClient/Starlette `httpx` deprecation，不影响 M35 合同。
- **静态交付**：`compileall -q app engine eval demo tests` 与 `git diff --check` 通过；注释审计 `113/113` 覆盖。
- **尚未证明**：未运行真实 LLM Router/Text2SQL Eval、Milvus/embedding、M34 external Answer Eval、远程 Composer/Judge 或 LangFuse Cloud。
- **下一步建议**：先读 Harness Trace/Eval 的 reason、execution 和 termination 失败簇，再规划 P4/G5 首个有界恢复切片；M34 召回/context packing 继续作为独立候选，不自动并入。

可复制验证命令：

```powershell
# 最终全仓确定性回归；预计看到 397 passed 和 1 个既有 TestClient deprecation warning。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m35-full-recheck

# 只检查 Python 语法/导入编译；预计无输出并以 exit 0 结束。
python -m compileall -q app engine eval demo tests
```

**本地启动体验：** M35 已有可交互后端入口。先确认 MySQL/seed 和项目环境符合 `docs/state/runbook.md`，然后启动 API：

```powershell
# 启动 FastAPI；环境未激活时使用 AGENTS.md 中的完整 Python 路径。
python -m uvicorn app.main:app --reload
```

打开 **Swagger UI**：`http://127.0.0.1:8000/docs`，选择 `POST /api/query`。可以先提交 SQL 示例 `{"question":"各渠道订单量是多少？","user_role":"ops"}`，观察 `route=sql`、四轴、SQL/rows/chart 和 trace id；再提交明确的政策/指标口径问题，观察 `route=rag`、validated citations 与 `docs_used`。如果提交未知 role，应该在 Tool 前得到 `caller_untrusted`；如果题目同时要求 SQL 与文档汇合，M35 会保守返回 unsupported，而不是偷偷运行两个 Tool。这里使用的是 **local/demo fixture caller**，只能用于学习和演示，不能当作生产认证。

## ★ M36 结构化澄清恢复与轻量 Thread Checkpoint

（2026-08-16）

**简述**：在 M35 单轮 Harness 外增加一次**安全、可审计、只能消费一次的结构化澄清恢复**，让问题缺条件时可以先暂停，补齐后再继续调用 SQL 或 RAG。

### 先用大白话讲

M35 已经像一个靠谱的调度台：每个问题只交给一个 SQL 或 RAG 专家，也知道什么时候该停。但它碰到“这个怎么处理？”或“退款情况怎么样？”时，只能告诉用户“信息不够”；下一次用户补充“退款政策”或“2026 年 6 月、按渠道统计”时，系统并不知道这句话是在补哪一个任务，只能当成全新问题。

M36 给调度台加了一张有安全规则的**待办卡**。比如你问“这个怎么处理？”，前台不再干巴巴回一句“信息不够”，而是给你一张表：“缺主体，请填，比如‘退款政策’”；你回来填“退款政策”，系统就把原问题和补充值合成同一个任务继续办。这张卡只认**你本人 + 你的租户 + 你当前角色 + 正确的版本号**，还有 15 分钟有效期：别人拿你的卡号续办会被拒，同一张卡交两次只办一次，卡过期了也作废；办完之后无论成败，卡都会被撕掉，不会自动“再来一次”。

这不是通用聊天记忆，也不是完整的 LangGraph interrupt/resume。它只完成 **pre-Tool clarification（调用工具前澄清）**的一次恢复闭环：先把“暂停、补问、继续”最容易出安全问题的生命周期做扎实，再决定以后是否需要 Evidence 重取证、更多 Context 模板或持久化。

### 这次做了什么

这一步要解决的两难是：任务得跨两个 HTTP 请求活下去，但 thread id 不能当权限、重复请求不能重复调 Tool、聊天历史不能随便塞回 Prompt，也不能为了一个小闭环提前建一整套会话平台。答案是**把生命周期收进一个轻量深模块**，Graph、API、Trace 和 Eval 只消费它给出的受控结果。

1. **把“不清楚”变成可填写、可校验的结构化任务**

   以前系统说“信息不够”就完了——用户不知道到底缺什么，系统手里也没有一张可以核对的清单。更麻烦的是，用户下一轮随便发一段文字，上层既没法确认字段补齐了没有，还可能把用户的话误当成系统控制信息。

   M36 于是新增 **`ClarificationSpec`（结构化澄清说明）**：它像一张 Pydantic 表单定义，写清楚字段 key、中文标签、值类型、允许枚举和最大长度。首版只冻结两个真实场景：`subject` 补“具体政策、规则、指标或业务对象”，`analytics_scope` 补时间范围和分组维度。`ClarificationContextBuilder` 先做 closed-world（封闭世界：只认已登记字段）校验——字段必须不多不少——再用固定模板拼出最小 current task，而不是让 LLM 自由改写整段历史。

   没有做通用槽位抽取、长对话 summary 或远程 query rewrite，那些会带来新的准确率、Prompt Injection、token 和出站评测问题。缺字段、额外字段、非法枚举、主体恢复到 RAG、分析范围恢复到 SQL 都有测试兜底；非法补充值在 claim 之前就被拦下，不会消耗 checkpoint version。这些测试证明两个冻结模板能保真恢复，不代表开放问法都能自动识别缺失条件。

2. **用 versioned checkpoint 保证只有正确的人能恢复一次**

   如果只用一个 `dict[thread_id] = question` 存待办，麻烦会一个接一个：任何拿到 id 的人都能继续别人的任务；两个并发请求可能同时读到 pending，然后各自调一次 SQL/RAG；服务端也说不清任务到底是过期了、被清理了还是重启后丢了。

   **`ThreadCheckpointManager`（线程检查点管理器）**把待办卡建成一条单调状态机：`pending → claimed → resolved/cleared`，每次迁移都递增 version。领取动作叫 claim：在一个 `RLock` 里完成 owner、tenant、active role、TTL（有效期）、state version、expected version 和补充值校验，全部通过才原子领取；慢 Graph/Tool 在锁外执行，不会堵住其他 thread。这很像 MySQL 的乐观锁——请求必须带着自己看到的版本号，只有一个竞争者能更新成功，其他人拿到稳定的冲突结果。

   安全审查还揪出一个细节：`TrustedCaller.audit_ref` 不含 tenant，不能单独当 owner。最终默认 owner 是 `audit_ref + tenant_id` 的内部哈希，认证适配器如果提供了专门的 `thread_owner_ref` 就用它做作用域。错误 owner 和“thread 不存在”对外统一返回 `conversation_unavailable`，避免攻击者靠返回差异试探某个 thread 是否存在。

   也没有采用“Tool 失败就把状态退回 pending 再试一次”的宽松做法：claim 之后执行权已经被消费，自动回滚可能让副作用重复执行。并发测试证明同一 expected version **恰好一个 claim 成功**，输家在 Graph 前就被拒绝；跨 tenant、过期、clear、重启丢失、状态版本不兼容、重复恢复都有确定性反例。当前 checkpoint 仍是单进程内存，所以这里不承诺重启恢复、多 worker 共享或长期容量。

3. **在 M35 Graph 外增加 turn seam，不拆坏原来的深 Tool**

   暂停/恢复这件事放错地方，代价会很大：塞进 Router 或 SQL/RAG Tool，每个专业模块都得开始认识 thread、version 和 HTTP 生命周期；把 M35 Graph 改成可中断 Graph，又会破坏“一次 invoke → 一份结果”的稳定合同。

   所以 M36 在 Graph 外面加了一层 **`run_turn()`（回合级入口）**：initial turn 先跑一次 M35 Graph，只有结果是 clarification 才创建 pending checkpoint；resume turn 先 claim，再把 Context Builder 拼好的当前任务交给同一个 M35 Graph，结束后推进 resolved。生命周期层面的拒绝不调用 Graph；accepted turn 恰好调用一次 Graph，Graph 内仍然至多一个 SQL/RAG 深 Tool。补充完还是不清楚，就返回 `budget_exhausted` 结束，不创建第二层 pending。

   用户确认的方案 A 是**应用持有轻量进程内 checkpoint**。另一个选项是用 LangGraph 自带的 checkpointer + interrupt/resume，好处是未来能恢复任意节点，代价是这个模块就得重写 Graph 生命周期、API、Trace 和异常关闭。选 A 不是“先写个假接口以后替换”，而是明确本模块只做 pre-Tool clarification；实现里没有预建 storage port，也没有伪装持久化。M36/M35/config 聚焦回归 31 passed、M31–M33 安全回归 111 passed，说明旧单轮 SQL/RAG、可信 caller 和 Evidence 边界没有被恢复层绕过——这不代表 Tool retry、Evidence 跨轮复用或 Hybrid 已经完成。

4. **让 API、Trace 和 sequence Eval 能共同还原两轮过程**

   M35 的单题 Eval 只能证明系统“正确停在澄清”，证明不了第二个 turn 的 owner、version、并发、过期和预算对不对；如果 API、Trace、Eval 再各自拼 thread 状态，多轮事实又会开始各说各话。

   所以这一轮把两个出口一起收紧。`/api/query` 增量接受 `thread_id + expected_version + clarification_answers`，三者必须成组出现；首次 pending 响应返回可填写字段和合法 owner 可见的 thread 投影。JSONL Trace 只记不可逆的 `thread_safe_ref`、前后 version、action、`context_ref`、Graph 次数和 checkpoint runtime，**不保存 raw thread id、补充值字典或完整 checkpoint**——排障再方便也不能把这两样写进日志，raw thread id 可能被拿去尝试恢复任务，用户补充的条件会扩大长期数据暴露面。Streamlit 能按服务端 spec 画最小补充表单，但本轮没做浏览器人工体验检查。

   Eval 这边升级成 **Sequence Eval（序列评测）**：不再把每个请求当孤立题目，而是把 initial、resume、clear 和 rejected attempt 组成同一条 sequence。`phase4-harness-turn-v1` 覆盖 8 组场景：主体到 RAG、分析范围到 SQL、错误 owner、过期版本、TTL、clear、并发单 claim、恢复预算。每个 accepted turn 一份 ExecutionEvidence，多条 assertion 只读同一份证据；artifact 会拒绝漏 turn、重复 execution、缺 assertion 或多次成功 resume。没有给 M35 的单轮 artifact 强行补 turn 字段，而是另立版本的 sequence family，避免历史分母和证据身份被改写。

   全仓 deterministic pytest 416 passed、1 个既有 warning，compileall 和 diff check 通过。这一节证明的是确定性生命周期、API/Trace 投影和回归兼容；真实 LLM Router/Text2SQL Eval、M34 external Answer Eval、Milvus/embedding、remote Composer/Judge、LangFuse Cloud 都没有运行，不能把它读成开放对话能力提升。

### 新概念

- **Thread Checkpoint（线程检查点）**：跨请求保存“一个未完成任务最少需要什么”的状态卡。M36 保存的是原问题、受控字段合同、owner、role、version 和 TTL，不是完整聊天记录。
- **Compare-and-set / 原子 claim（比较并交换式领取）**：只有“当前 version 仍等于我看到的 version”时才能把 pending 改成 claimed。可以类比 MySQL `UPDATE ... WHERE version = ?` 或 Redis `SET NX`；成功者获得执行权，失败者不能继续调用 Tool。
- **TTL（Time To Live，生存时间）**：checkpoint 的有效期。默认 900 秒，过期后即使 owner 和 version 正确也不能恢复，防止进程内状态无限期变成长期会话承诺。
- **Closed-world clarification（闭世界澄清）**：系统只接受事先登记的字段和值域，不把未知 key 当作“也许有用”的上下文。它类似 Pydantic `extra=forbid` 的思路，重点是让恢复合同可验证。
- **Turn-level seam（回合级接缝）**：位于 HTTP API 和单轮 Graph 之间的统一入口，负责 initial/resume/rejected 生命周期；Graph 继续只关心本轮 route、Tool 和 controller。
- **Tombstone（墓碑状态）**：resolved/cleared 后仍短期保留的不可重放记录。它能告诉合法 owner“已经消费或清理”，但当前会保留到进程结束，也形成容量技术债。

### 代码阅读路线

1. **先看客户端能提交和看到什么**：`app/schemas/agent.py`

   从 `QueryRequest.validate_resume_shape()` 看 resume 三字段为何必须成组，再看 `ClarificationView`、`ThreadView` 和 `AgentResponse` 的增量字段。这里定义的是**公开合同**：客户端能看到待填字段和自己的 raw thread id，但看不到 checkpoint 内部任务。

2. **看 Router 怎样形成结构化待补单**：`engine/harness/contracts.py` → `engine/harness/router.py`

   先读 `ClarificationFieldSpec` / `ClarificationSpec` 的 closed-world 约束，再看 `DeterministicRouter.decide()` 何时选择 subject 或 analytics scope。重点理解 Router 只报告“缺什么”，不保存 thread、不调用 Tool；具体关键词只是确定性 baseline，不需要背。

3. **深入待办卡的安全生命周期**：`engine/harness/thread.py`

   先读 `PendingThreadCheckpoint` 的字段，然后沿 `ThreadCheckpointManager.create_pending()`、`claim_resume()`、`resolve()`、`clear()` 阅读。主角是锁内的校验顺序和 version 迁移：先隐藏 wrong-owner/missing 差异，再检查 owner 自己的状态，最后在慢 Tool 前 claim。接着读 `ClarificationContextBuilder.build()`，理解为什么只允许两个模板。

4. **看两次 HTTP 请求怎样复用同一个单轮 Graph**：`engine/harness/turn.py` → `engine/harness/graph.py`

   从 `run_turn()` 分流 initial/resume，再重点读 `_run_resume()`：claim、锁外 Graph、budget stop、resolve。这里解决的是**跨 turn 生命周期与单轮业务执行分层**；M35 Graph 仍保持 route → 一个 Tool/terminal → controller，不需要重新学习 SQL/RAG 内部实现。

5. **回到 API 检查响应和 Trace 没有旁路**：`app/main.py` → `app/api/query.py` → `engine/trace/recorder.py`

   `app/main.py` 持有唯一进程内 manager；query endpoint 解析 caller、组装 runtime、只调用 `run_turn()`，再从 turn result 投影响应和 Trace。显式 clear 不调用 Graph，但会写 lifecycle Trace。阅读时重点核对 raw thread id 只出现在 owner 响应，不进入 JSONL。

6. **最后用测试和 Eval 复核失败边界**：`tests/test_m36_thread.py` → `tests/test_m36_turn.py` → `tests/test_m36_api_trace.py` → `eval/harness_turn_contracts.py`

   thread 测试覆盖 owner/tenant/TTL/version/并发，turn 测试覆盖一次 Graph/Tool 和 budget，API 测试对照两轮 JSONL，sequence Eval 再检查 8 组完整序列及 artifact 反例。这样可以从底层状态机一路看到公开证据，而不是只看一个 happy path。

核心调用链是：

`POST /api/query（问题缺条件）`
→ `M35 Graph 返回 clarification`
→ `ThreadCheckpointManager.create_pending()`
→ `AgentResponse 返回 spec + thread/version`
→ `POST /api/query（结构化补充）`
→ `owner/tenant/role/TTL/version 校验 + 原子 claim`
→ `ClarificationContextBuilder`
→ `M35 Graph → 至多一个 SQL/RAG Tool`
→ `resolved + AgentResponse + JSONL Trace + sequence evidence`

**模块闭环**：M35 解决“一次请求如何可信地选择并调用一个 Tool”，M36 解决“条件不足时如何安全暂停一次、补齐后继续一次”。两者合起来形成了 Phase 4 第一个可演示的**有界多 turn Agent 闭环**。

### 设计要点

- **应用内 checkpoint 是明确方案，不是假持久化**：当前目标是 pre-Tool clarification，重启丢失会如实返回 unavailable；只有恢复任意 Graph 节点成为 required Scenario，才重开 LangGraph/persistent checkpoint 决策。
- **claim 后不回滚、不自动 retry**：执行权已经消费，恢复 pending 可能重复 Tool 副作用；技术失败沿用 M35 原 reason，交给上层决定是否重新发起新任务。
- **thread id 不是权限**：owner、tenant、active role 和 version 都在 Tool 前检查；wrong owner 与 missing 对外同形，避免存在性侧信道。
- **最小 Context，而非聊天历史**：只保留恢复当前任务所需事实，Router/Tool 不读取 checkpoint 容器，Trace 不记录补充值或 raw id。
- **确定性 Eval 不冒充开放智能**：416 条全仓测试和 8 组 sequence 证明生命周期合同与兼容性，不证明真实 LLM 能理解任意省略、指代或长对话。
- **当前技术债**：checkpoint 不跨进程，resolved/cleared tombstone 暂不清扫，Streamlit 表单未做浏览器人工检查；下一轮需按真实失败和容量证据决定方向喵。

### 有面试价值的亮点

1. **“一张只能领一次、还会过期的待办卡”**：澄清恢复最怕三件事：别人拿你的卡号、同一张卡重复办理、卡片永久有效。我把 checkpoint 做成 `pending → claimed → resolved/cleared` 的单调状态机，配 version 和 900 秒 TTL（有效期），在 `RLock` 里原子 claim（领取）——等价于 MySQL 乐观锁，两个线程同时抢，恰好一个成功。卡片还绑定 owner + tenant + active role：换个人、换个租户、换个角色都领不走。

2. **“claim 之后不退票，哪怕 Tool 失败”**：很多人第一反应是“执行失败为什么不退回 pending 让用户重试”。因为 claim 意味着执行权已经消费，回滚会让 SQL 这类有成本、有副作用的操作重复执行。所以失败也推进 resolved，把技术原因如实记录，不自动重试。这是个刻意选择，面试时主动讲出来比被追问更好。

3. **“不接 LangGraph 原生 checkpoint，是决策不是偷懒”**：LangGraph 自带 InMemorySaver + interrupt/resume，好处是能恢复任意节点；代价是要重写 M35“一次 invoke → 一份结果”的合同，而 M36 只需要 Tool 前澄清这一次恢复。我选应用持有的轻量内存 checkpoint：重启即失、绝不伪装持久化，换来不改写 M35 生命周期、不为还没出现的需求预建 storage port。把 trade-off 讲清楚本身就是亮点。

### 面试官追问

1. **[基础追问] 用户补充条件后，系统怎么保证继续的是原任务，而不是把补充文字当成新问题？**

   首次 clarification 会把原问题和 `ClarificationSpec` 放进 owner-bound checkpoint。第二次请求不能只发一句自由文本，必须同时携带 thread id、expected version 和闭合的字段字典。Context Builder 从 checkpoint 读取原问题，用固定 subject 或 analytics 模板合成 current task；Router/Tool 只看到这个最小任务，不直接读取聊天历史。因此“退款政策”会与“这个怎么处理”合成 RAG 问题，“2026 年 6 月 + 渠道”会与“退款情况”合成 SQL 分析问题。

2. **[工程/深挖追问] 两个完全相同的 resume 请求同时到达，为什么不会执行两次 SQL 或 RAG？**

   manager 把状态检查和 `pending → claimed` 写入放在同一个 `RLock` 临界区，等价于 compare-and-set。两个请求都带 version 1，但只有先取得锁的请求能把状态改成 claimed/version 2；第二个进入锁后看到状态不再 pending，在调用 Graph 前返回 `thread_already_resumed`。慢 Tool 放在锁外，所以不会阻塞其他 thread。单元测试使用两个线程和 barrier 同时竞争，断言恰好一个 claim 成功、Tool 总调用不超过一次。

3. **[工程/深挖追问] 为什么非法补充值不消耗 version，但 Tool 失败后却不允许继续用原 version？**

   两者的执行事实不同。字段缺失、额外或枚举非法发生在 claim 之前，系统还没有给请求执行权，也没有调用 Graph，所以允许用户修正后继续使用同一 pending version。claim 之后即使 Tool 返回 unavailable，执行权已经真实消费；若把状态退回 pending，客户端重试可能再次调用具有副作用或成本的 Tool。M36 因此推进 resolved 并保留原技术 reason，不自动重试。

4. **[压力追问] 你叫它 Thread Checkpoint，但服务一重启状态就没了，这不是一个残缺实现吗？**

   这个质疑对“持久会话系统”成立，但 M36 的目标不是承诺持久会话，而是验证 pre-Tool clarification 的安全生命周期。方案 A 明确把 adapter identity、state version、TTL 和 restart loss 写进 Trace/测试，重启后返回 `conversation_unavailable`，没有伪装可靠性；它换来的是不改写 M35 Graph 生命周期，也不为尚未出现的中间节点恢复需求预建 storage port。现有证据证明 owner/tenant/version/并发和一次恢复成立；如果后续 required Scenario 要求跨进程或恢复 Tool/Evidence 中间态，我会重新评估 LangGraph checkpointer 或持久存储，而不是把当前内存实现偷偷包装成生产能力喵。

### 验证与下一步

- **M36/M35/config 聚焦**：`31 passed in 35.46s`，覆盖 thread、turn、API/Trace、sequence Eval 与 M35 兼容。
- **安全回归**：M31–M33 caller/ACL/outbound/Evidence/citation suites 为 `111 passed in 2.65s`。
- **全仓确定性回归**：后台运行退出码 `0`，`416 passed, 1 warning in 594.12s`；warning 是既有 Starlette TestClient/httpx deprecation，不影响 M36。
- **静态交付**：`compileall -q app engine eval tests demo` 与 `git diff --check` 通过。
- **尚未证明**：未运行真实 LLM Router/Text2SQL Eval、M34 external Answer Eval、Milvus/embedding、remote Composer/Judge 或 LangFuse Cloud；Streamlit 表单也未做浏览器人工体验检查。
- **下一步建议**：规划下一模块时先在 Evidence 失效/重取证与更一般的受控 Context Builder 之间选择；若需要恢复 Tool/Evidence/任意 Graph 节点或跨重启恢复，先重开 checkpoint 方案决策门。

可复制验证命令：

```powershell
# M36 + M35 聚焦回归；预计相关 thread/turn/API/Trace/Eval 合同全部通过。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m36-review tests/test_config.py tests/test_m36_thread.py tests/test_m36_turn.py tests/test_m36_api_trace.py tests/test_m36_harness_turn_eval.py tests/test_m35_harness.py tests/test_m35_harness_eval.py tests/test_m35_api_trace.py

# 全仓确定性回归；收工快照为 416 passed 和 1 个既有 TestClient deprecation warning。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m36-full-recheck

# Python 语法/导入编译；预计无输出并以 exit 0 结束。
python -m compileall -q app engine eval tests demo
```

**本地启动体验：** M36 可以通过 FastAPI Swagger 做两轮体验。先按 `docs/state/runbook.md` 准备数据库/seed 和本地环境，再启动服务：

```powershell
# 启动 FastAPI；环境未激活时使用 AGENTS.md 中的完整 Python 路径。
python -m uvicorn app.main:app --reload
```

打开 **Swagger UI**：`http://127.0.0.1:8000/docs`，先调用 `POST /api/query`，提交 `{"question":"这个怎么处理？","user_role":"ops"}`。预计得到 `answer_status=clarification_required`、`thread.status=pending`、`checkpoint_version=1`，以及只含 `subject` 的待补字段。复制返回的 `thread_id`，再次调用同一接口，提交：

```json
{
  "question": "补充结构化条件",
  "user_role": "ops",
  "thread_id": "替换为首次响应中的值",
  "expected_version": 1,
  "clarification_answers": {"subject": "退款政策"}
}
```

预计第二次走 `route=rag`、`turn_action=resume`，thread 变为 `resolved`。再次原样提交会在 Graph 前得到 `thread_already_resumed`，不会重复调用 Tool。也可以用“退款情况怎么样？”触发 `time_range + group_by` 表单。这里的 caller 是 **local/demo fixture**，checkpoint 只在当前 API 进程内有效；不要把这个体验解释成生产认证或持久会话。

## ★ M37 受控有限追问与 Document Evidence 窄复用

（2026-08-17）

**简述**：在 M36 的一次澄清恢复之后，为成功的 SQL/RAG 回答增加一次**显式开启、服务端限定、重新判断 Evidence 有效性**的追问；既让用户能继续问，又不把旧答案和旧权限当成永久事实。

### 先用大白话讲

M36 解决的是“问题缺条件，补一次再继续”，但回答成功后任务就结束了。如果用户接着说“改成 7 月、按商品看”或“把这条退款规则讲得通俗一点”，系统没有安全的继续方式。最偷懒的做法，是把上一轮问答整段重新塞给模型；问题在于上一轮 SQL 数据可能已经变了，文档可能更新或撤权，旧答案还可能把不该长期保存的 rows、正文和 citation 带进下一轮。

M37 把一次追问做成一张**医院取号单式的服务端票据**：只有上一轮成功、且你主动勾选了“允许追问”，才会拿到这张号；号上印死了你只能办哪几件事、每件事能填哪几个字段，而且**只能办一次**。比如“改成 7 月、按商品看”——数据窗口会**重新查库**，因为没人能证明刚才的数据没变；“把这条退款规则讲得通俗一点”——文档窗口先核对当前原件版本和你的权限，才为本轮重新开一张“证据证明”，而不是把上一轮的旧证明改个日期拿出来用。票据过期、填错字段、别人拿你的号，全都不予办理。它不是自由聊天，而是一条能说清楚“为什么继续、凭什么继续、什么时候必须停”的工程闭环。

### 这次做了什么

这一步要解决的矛盾是：追问需要上一轮上下文，但安全回答不能盲信上一轮结果。M37 没有用完整聊天历史解决它，而是把“任务条件”“允许修改的字段”“旧 Evidence 的审计坐标”“本轮重新取证决定”拆开保存，并让 accepted follow-up 仍然只经过一次 M35 Graph 和至多一个深 Tool。

1. **把成功回答变成一次可控、默认关闭的 follow-up-ready 状态**

   M36 的“补一次再继续”只在缺条件时生效，回答成功的任务还是就此结束。想让所有成功回答自动保存上下文，又会改变旧接口行为，让普通请求无意间进入会话生命周期。M37 的答案是 `enable_bounded_follow_up`：只有客户端显式置 `true`，且本轮确实成功并产生 Evidence，服务端才创建 `follow_up_ready` checkpoint；旧请求继续拿到 `thread=None`，行为完全不变。

   这张“追问许可”是 **closed-world follow-up（闭世界追问）**：服务端先签发动作和字段白名单，客户端只能从中选。SQL 只有 `adjust_sql_scope`，可调整时间和分组；RAG 有“解释同一 Evidence”和“询问相关 Evidence”两类动作。额外字段、非法枚举、控制指令、错误 owner/version、过期和并发输家，全都在 Graph 前拒绝，不消耗业务 Tool。选显式 opt-in 而不是默认建 thread，是为了保留兼容性，也避免把短期任务票据误当成永久聊天会话。

   默认 threadless、TTL、clear、重启丢失、错误 owner、非法 delta、预算重放和并发单赢家都有测试。它证明一次受控追问的生命周期成立，不代表第二次追问、长历史或跨进程会话已经存在。

2. **用 Evidence validity 决定“重新加载”还是“重新检索”**

   上一轮的 EvidenceRef 只能证明“当时用了什么”，证明不了现在：文档可能已经改版或撤权，caller 的权限可能变了，新问题也可能根本不想要同一份证据。直接复用旧正文，revision 变化和 ACL 撤销就被绕过了；但所有情况都无脑重检索，又浪费了业务文档已有的精确 identity，还掩盖了“同一证据仍有效”这个能力。

   用户确认的**窄 B**给了一个分界：只有 22-entry 业务 release 里的“同一 Evidence requirement 解释/改述”可以走 **rehydrate（重水化）**——拿旧审计坐标当索引，重新加载当前 active bundle，用 `authority_identity + revision + content_identity + anchor` 精确定位原件，再分别执行 pre-selection 和 pre-generation 授权；全部一致才为本轮重建 Evidence。identity 变化或 requirement 不等价时，同一个 RAG Tool 最多重新检索一次；ACL/用途拒绝则零 retrieval 停止，不能靠重新搜索去探测文档存不存在。

   注意 rehydrate 不是复用旧 Evidence 对象，而是生成新的 run-scoped（只属于本轮运行）Evidence、ledger（证据账本）和 citation。测试证明同一业务规则可以零 Knowledge retrieval 完成解释，但新旧 evidence/citation id 并不相同；revision、requirement、ACL 和 external runtime 也都有反例。这个结论只适用于当前业务 release，不能外推成“任意外部知识库都能安全缓存复用”。

3. **SQL 和 external profile 坚持重新取证，不用“看起来一样”冒充新鲜**

   对 SQL 和外部大语料，M37 的选择是**一律重新取证**。原因很实在：SQL Evidence 的 revision 接近查询时间，当前系统没有可靠的业务 snapshot identity，即使追问条件没变，也没法证明数据库数据没变；external profile 虽然也有 Evidence identity，但本模块没有建立通用的 external locator、权限同步和复用合同。所以 SQL follow-up 每次都重新走 Text2SQL、SQL Guard 和查询执行并签发新 SQL Evidence；external RAG 每次都重新检索。

   Trace 里会记下具体原因——`sql_has_no_snapshot`、`external_profile_always_retrieves`、`requirement_changed` 或 `document_identity_changed` 这类 **reacquisition reason（重新取证原因）**，而不是一句模糊的“缓存未命中”。这个边界比直接复用旧 rows 更贵，但它避免了把“结果 fingerprint 一样”误写成“数据仍然新鲜”。M37 sequence Eval 对 SQL 强制重查、external 强制检索和新 run Evidence 做了确定性断言；没有测量真实数据库高并发下的性能成本，也没有证明 external 复用永远不值得做——这里只证明在当前身份合同不足时，保守重新取证是对的。

4. **让 Router、API、Trace 和 Eval 都只看到自己该看的事实**

   多轮之后最危险的是“越界分享”：把旧 EvidenceRef 交给 Router，控制层可能根据旧证据偷偷改 route；把旧 answer、rows、正文或 raw thread id 写进 checkpoint/Trace，隐私、授权和重放风险一起变大。所以 M37 给每个角色划了明确的视野：

   - **Router**：进入前剥离 `follow_up_context`，只根据当前结构化任务决定原 route；
   - **同 route 深 Tool**：拿到旧 Evidence 审计坐标做 validity（有效性判断）；
   - **checkpoint**：只存最小 task snapshot、EvidenceRef、服务端 spec 和一次预算；
   - **Trace**：只存不可逆 thread/context ref、版本迁移、Graph/Tool 次数和安全 validity reason。

   顺手还修了一个 API 细节：半截 follow-up 请求暴露了 Pydantic v2 的一个坑——`ctx.error` 里的 `ValueError` 不能直接 JSON 序列化，统一 422 handler 先过一遍 `jsonable_encoder`，非法请求才能稳定返回 422 而不是意外 500。

   `phase4-harness-followup-v1` 用 Sequence Eval 记录 10 组完整序列、22 份 turn execution evidence 和 50 条 required assertion，拒绝漏 turn、重复执行、超预算和旧 Evidence id 注入。全仓 427 passed、3 skipped、1 warning，说明确定性合同和旧能力兼容；真实 LLM、远程 embedding/Milvus、LangFuse Cloud、M34 external 大评测都没跑，所以这些数字不能读成开放问法质量或生产性能提升。

### 新概念

- **Bounded follow-up（有界追问）**：不是“可以一直聊”，而是成功结果附带的一次性后续动作。它有明确 owner、version、TTL、字段白名单和消费预算，类似一张只能在指定窗口办理指定业务一次的号码票。
- **Evidence requirement（证据需求）**：描述新回答需要什么证据，而不是描述用户说了哪句话。两次问题文字不同，只要服务端确认它们仍要求同一证据，才可能进入业务 rehydrate；客户端不能自己宣称“它们等价”。
- **Evidence validity（证据有效性）**：回答“旧证据的审计坐标在当前时刻是否仍能支持新 claim”。它同时考虑 requirement、Evidence kind、revision/content/anchor、ACL 和用途，不等同于缓存是否命中。
- **Rehydrate（重水化）**：拿旧 EvidenceRef 当索引，重新读取当前权威原件并重新授权，再构造本轮新 Evidence。可以类比 JPA 根据主键重新从数据库加载实体，而不是继续信任一份脱离 Session 的旧对象。
- **Reacquisition（重新取证）**：旧证据不满足当前条件时，再执行 SQL 或 Knowledge Tool。它不是失败兜底，而是被 Trace/Eval 明确记录的正确分支。
- **Run-scoped identity（运行级身份）**：Evidence、ledger 和 citation 只属于一次 run。即使正文完全相同，新一轮也要生成新 id，避免把上一轮授权和审计事实偷渡到当前轮。
- **Runtime isolation（运行口径隔离）**：业务 22-entry release 与 EnterpriseRAG-Bench external profile 有不同的加载器、身份和证据能力，不能因为都叫 RAG 就共用一条复用规则。

### 代码阅读路线

1. **先看 HTTP 能提交什么、为什么不能混搭字段**：`app/schemas/agent.py` → `app/core/exceptions.py`

   从请求模型看 `enable_bounded_follow_up`、`follow_up_action` 和 `follow_up_fields` 如何与 clarification 字段互斥，再看响应中的 follow-up spec、status 和剩余预算。异常处理器展示了非法半截请求如何稳定投影成 422；重点理解**公开输入形状先阻止歧义**，不需要背每个 Pydantic 字段声明。

2. **读服务端如何冻结动作与 Evidence 上下文**：`engine/harness/contracts.py`

   主角是 `FollowUpActionSpec`、`FollowUpSpec` 和 `FollowUpExecutionContext`。先看动作与 requirement equivalence 为什么由服务端代码决定，再看 context 如何校验 route、Evidence kind、runtime 和 requirement identity。这里解决的是**客户端不能自报证据可复用**。

3. **沿一次性票据读生命周期和结构化 Context Builder**：`engine/harness/thread.py`

   先看 `FollowUpTask` 保存哪些最小事实，再沿 `create_follow_up_ready()`、`claim_follow_up()` 和 projection 阅读 `follow_up_ready → follow_up_claimed → resolved`。重点关注锁内 owner/version/TTL/spec 校验、控制指令拒绝与预算消费；然后看 SQL/RAG 三个服务端 action 怎样生成 current task。旧 answer、rows、正文和 citation 没出现在 task 中，正是这层的安全价值。

4. **看 turn seam 如何保证一次 Graph、一次 Tool**：`engine/harness/turn.py` → `engine/harness/graph.py`

   从 `TurnRequest` 的 clarification/follow-up 互斥开始，沿 `run_turn()` 看 initial、resume、follow-up、rejected 四条路径。follow-up 先原子 claim，再调用原 M35 Graph，结束后不再创建下一张追问票；Graph 的 route node 会把旧 Evidence context 剥离。这里要理解**跨轮控制在 Graph 外，单轮业务执行仍在 Graph 内**。

5. **比较 SQL、业务 RAG、external RAG 的取证分支**：`engine/harness/adapters.py` → `engine/rag/answer_flow.py`

   SQL adapter 只会生成新查询 Evidence，并解释没有 snapshot；RAG adapter 把可信 runtime kind、当前 requirement 和旧 refs 交给 AnswerFlow。重点读 `RAGAnswerFlow._obtain_evidence()`：无旧证据走正常检索，external/requirement 变化重检索，业务等价动作才尝试 active identity locator 与双阶段授权。后面的 Gate、Composer 和 citation validator 继续复用 M33 合同，不必重新精读全部回答流水线。

6. **最后从公开证据验证没有旁路**：`app/api/query.py` → `engine/trace/recorder.py` → `eval/harness_followup_contracts.py` → `tests/test_m37_*.py`

   API 只调用 `run_turn()` 并从同一结果投影响应/Trace；Trace 看不到 raw thread id 和旧内容；Eval 把 initial、accepted/rejected follow-up 组成序列。测试分别检查生命周期、业务重水化、HTTP/Trace 和 completed artifact 反例。这样能从“用户发请求”一路核对到“为什么重查或重水化”。

核心调用链是：

`POST /api/query（enable_bounded_follow_up=true）`
→ `M35 Graph → SQL/RAG 成功 + Evidence`
→ `ThreadCheckpointManager.create_follow_up_ready()`
→ `服务端返回 action/fields + thread/version`
→ `POST /api/query（结构化 follow-up）`
→ `owner/version/TTL/spec/budget 校验 + 原子 claim`
→ `Context Builder 形成 current task`
→ `Router（看不到旧 Evidence）`
→ `同 route Tool 做 validity / rehydrate / reacquire`
→ `新 run Evidence + resolved + Response/Trace/Sequence Eval`

**模块闭环**：M35 建立一次请求只调用一个可信 Tool，M36 允许缺条件时暂停并恢复一次，M37 又允许成功结果在重新判断 Evidence 后追问一次。三者共同形成了“**能停、能补、能继续，但不会无限跑或盲信旧证据**”的 P4 有界 Agent 主链。

### 设计要点

- **窄 B 是正式能力，不是临时占位**：业务同 requirement 的 Evidence 重水化、identity/requirement 变化后重检索、SQL/external 强制重取证都有实现和反例；不能以后悄悄退化成旧答案复用。
- **默认关闭保护兼容性**：旧客户端不建 thread；只有明确需要追问的调用方承担状态和 TTL 语义。
- **证据等价由服务端判断**：如果让客户端传 `reuse=true`，它就能绕过 revision、ACL 和用途裁决。
- **ACL deny 不 fallback retrieval**：否则攻击者可以借搜索结果差异探测已撤权文档；安全停止优先于“尽量回答”。
- **旧 Evidence 不进入 Router**：控制层不能用上一轮证据改 route，validity 只属于同 route 深 Tool。
- **当前边界是真实合同的一部分**：一次追问、单进程 checkpoint、三个 action、业务 release 窄重水化；第二次追问、自由历史、external 复用、跨 route/Hybrid、持久化和生产认证仍未完成喵。

### 有面试价值的亮点

1. **“追问不是重新塞历史，而是重新判断证据”**：最偷懒的多轮是把上一轮问答整段回灌模型，我却把上下文拆成四样东西分开管：任务条件、允许修改的字段、旧 Evidence 的审计坐标、本轮重新取证的决定。SQL 永远重查——没有业务快照版本就不敢说“数据没变”；external 语料永远重检索；业务文档只有“还是解释同一条规则”才允许 rehydrate（重水化）——而且重水化也不是复用旧对象，是拿旧坐标重新加载原件、重新授权、签发新 id。

2. **“结果一样 ≠ 数据新鲜”**：面试官常问“指纹相同为什么不能直接复用”。因为 fingerprint（结果指纹）只能证明两份结果长得一样，证明不了查询之前数据库没变。没有事务快照、CDC 或业务版本作为 freshness 依据时，复用就是拿运气当合同。我把“是否新鲜”和“是否碰巧相同”拆成两件事，并用 reacquisition reason 记进 Trace。

3. **“ACL 拒绝时，零检索停止而不是换关键词再搜”**：被权限拒绝后继续搜“也许还有别的公开文档”，会把文档存在性、命中数从侧信道漏出去。所以该分支直接停；如果产品确实需要“无权看原文就换公开材料”，那是另一个 requirement 和另一个服务端 action，得另立合同，不能在被拒分支里偷偷改任务。

### 面试官追问

1. **[基础追问] 同一条政策只是换种说法，为什么还要生成新的 Evidence 和 citation id？**

   旧 id 证明的是上一轮 run 当时选中了什么、谁有权限以及引用了什么。新一轮即使定位到相同正文，也必须重新读取 active 原件、核对 revision/content/anchor 并重新授权；只有这些条件仍成立，才用当前 run id 构造新 Evidence、ledger 和 citation。这样审计时可以明确区分“上一轮曾经有效”和“这一轮重新证明有效”，不会把旧授权跨轮继承。

2. **[工程/深挖追问] 为什么 SQL 不比较 result fingerprint，相同就直接复用？**

   fingerprint 相同只能说明两份已获得结果内容一样，不能在查询前证明数据库没变。当前系统没有事务快照版本、CDC offset 或业务数据版本可作为 freshness identity，因此跳过查询没有证据基础。M37 选择每次重新走 Text2SQL、Guard 和执行，再在 diagnostics 里记录新旧 fingerprint 的关系；这是把“是否新鲜”和“结果是否碰巧相同”分开。

3. **[工程/深挖追问] 业务文档 ACL 变化后为什么不重新检索，也许还能找到别的公开文档回答？**

   当前 action 的语义是“解释上一轮同一 Evidence”。当系统已经根据旧审计坐标定位到目标文档、又发现当前 caller 无权访问时，fallback retrieval 会暴露文档存在性，还可能把同一受限主题通过候选差异旁路出来。因此该分支零 retrieval 安全停止。如果产品需要“无权解释原文时，改为搜索其他公开材料”，那是一个不同 requirement 和不同服务端 action，需要独立定义泄露边界与 Eval，不能在 ACL deny 分支暗中改变任务。

4. **[工程/深挖追问] 你怎么证明并发追问不会执行两次 Tool？**

   follow-up-ready checkpoint 带 expected version，manager 在同一个 `RLock` 临界区完成校验与 `follow_up_ready → follow_up_claimed`。两个线程用 barrier 同时提交时，只有一个能消费 version 和预算；另一个在 Graph 前 rejected。Sequence Eval 和 turn 测试同时断言 accepted 数量不超过 1、rejected 的 Graph/Tool 次数为 0，以及新 Evidence 的 run id 只属于赢家。

5. **[压力追问] 你为了“一次追问”加了状态机、Evidence validity 和 50 条断言，这是不是过度设计？**

   如果追问只是无状态改写文本，这套设计确实太重；但 DataPilot 的回答可能执行 SQL、读取有 ACL 和 revision 的企业文档，并形成可审计 citation。真正的风险不是“模型没听懂”，而是重复执行、旧权限继承、过期文档复用和 Trace 无法证明发生了什么。M37 没有建设完整会话平台，只复用了 M36 manager，冻结三个 action、一次预算和一个业务 rehydrate seam；10 组 sequence/50 条断言分别覆盖重新取证和生命周期反例。它增加的复杂度对应已有安全合同，但还不能据此宣称生产多轮能力，跨进程、开放问法和性能成本仍需后续证据喵。

### 验证与下一步

- **M37 专项**：最终 `14 passed, 1 warning`，覆盖 turn 生命周期、业务 Document Evidence 重水化、API/Trace 和 Eval completed validator。
- **受影响回归**：M31–M37 为 `162 passed, 1 warning in 39.19s`；API/配置为 `19 passed, 1 warning in 92.14s`。
- **Sequence Eval**：10 sequences / 22 turn evidence / 50 required assertions，`50 passed`；artifact identity 为 `1185edf04c42439dedf5e3dc051be13060a462bd05e79c48d3b975fdce634b25`。
- **全仓确定性回归**：后台任务退出码 `0`，`427 passed, 3 skipped, 1 warning in 509.36s`；warning 是既有 Starlette TestClient/httpx deprecation，3 skip 为既有条件型远程/Milvus 用例。
- **静态交付**：`compileall -q app engine eval tests demo` 与 `git diff --check` 通过。
- **尚未证明**：未运行真实 LLM、远程 embedding、Milvus、LangFuse Cloud、M27 真实 Text2SQL Eval 或 M34 external 大评测；没有生产多 worker、性能或开放对话结论。
- **下一步建议**：重新对照 Phase 4 roadmap 选择剩余能力切片。M37 不等于 P4 完成，不能默认扩到第二次追问、external 复用、跨 route/Hybrid 或持久 checkpoint。

可复制验证命令：

```powershell
# M37 聚焦回归；预计看到 14 passed 和 1 个既有 TestClient/httpx deprecation warning。
python -m pytest -q -p no:cacheprovider tests/test_m37_followup_turn.py tests/test_m37_rag_rehydration.py tests/test_m37_api_trace.py tests/test_m37_followup_eval.py --basetemp=.agent_work/temp/m37-review

# 全仓确定性回归；收工快照为 427 passed、3 skipped、1 warning，通常需要数分钟。
# 按 AGENTS.md，预计超过 2 分钟时应使用后台任务并把日志/退出码/完成标记写入 .agent_work/temp/。
python -m pytest -q -p no:cacheprovider --basetemp=.agent_work/temp/m37-full-recheck

# Python 语法/导入编译；预计无输出并以 exit 0 结束。
python -m compileall -q app engine eval tests demo
```

**本地启动体验：** M37 可以通过 FastAPI Swagger 体验“成功 SQL → 一次结构化追问”。先按 `docs/state/runbook.md` 准备数据库/seed 和 local/demo 环境，再启动服务：

```powershell
# 启动 FastAPI；环境未激活时使用 AGENTS.md 中记录的完整 Python 路径。
python -m uvicorn app.main:app --reload
```

打开 **Swagger UI**：`http://127.0.0.1:8000/docs`，调用 `POST /api/query`，首次提交：

```json
{
  "question": "各渠道订单量是多少？",
  "user_role": "ops",
  "enable_bounded_follow_up": true
}
```

预计得到 `route=sql`、完整结果，以及 `thread.status=follow_up_ready`、`follow_up_budget_remaining=1` 和服务端签发的 `adjust_sql_scope` 字段说明。复制响应中的 `thread_id` 与 `checkpoint_version`，再次调用同一接口：

```json
{
  "question": "执行结构化追问",
  "user_role": "ops",
  "thread_id": "替换为首次响应中的值",
  "expected_version": 1,
  "follow_up_action": "adjust_sql_scope",
  "follow_up_fields": {
    "time_range": "2026年7月",
    "group_by": "商品"
  }
}
```

预计第二次返回 `turn_action=follow_up`、新的 SQL Evidence 和 `thread.status=resolved`。再次原样提交会在 Graph 前被拒绝，不会重复查询；增加 spec 外字段也会得到稳定 422 或 `follow_up_invalid`。这里使用的是 **local/demo fixture caller**，thread 只存在于当前 API 进程，不能解释成生产认证、持久会话或自由聊天。

## ★ M38 保守 Hybrid 双 Evidence 编排

（2026-08-17）

**简述**：让 DataPilot 在同一次请求中完成“查数据库事实 + 查业务规则”的**保守 Hybrid**回答；只有两类证据都经验证时才给跨来源结论，失败时宁可降级或停止，也不拼凑答案。

### 先用大白话讲

以前系统面对“退款原因是什么，同时政策怎么规定”这类问题，会知道它同时需要 SQL 和文档，却只能保守说“不支持”。如果直接把两个 Tool 的自然语言答案拼起来，表面上很方便，实际上很危险：SQL 可能被 Guard 拦下，文档可能没权限，两个结论也可能互相冲突；更糟的是，系统会失去“这句话到底由哪份证据支持”的证明。

M38 把 Hybrid 做成一张**双窗口办事单**。比如“6 月退款最多的原因是什么，按政策这些单该怎么处理？”——Router 在单子上写“去数据窗口查退款原因 Top1，去文档窗口取退款处理规则”，两个窗口各办一次。最后要说全这句话，必须**同时亮出两张回执**：数据窗口证明“退得最多的是质量问题”，文档窗口证明“质量问题的标准处理流程是这样”。只剩一张回执时，就只讲那张回执单独能成立的话（比如只报数据、不套政策）；两张回执打架、数据窗口亮红灯、或者最后合成环节出故障，都有固定的收口，绝不硬拼。这样它不是“更会聊天”，而是先把**双证据协作的责任边界**做清楚。

### 这次做了什么

这一步要解决的问题是：系统已有可信 SQL 和可信 RAG，但两条链路以前只能二选一；一旦问题同时需要数据事实和规则依据，既拿不到完整证据，也没有统一的失败合同。M38 在不增加远程出站的前提下，把两条深链路放进同一个 Harness，并让 API、Trace 与 Eval 都从同一次运行事实投影。

1. **用薄计划把“混合问题”变成两条受控分支**

   以前 Router 碰到“退款原因+政策规定”这类问题，只会回 `hybrid_unsupported`。把它改成能自由规划很多步骤，看起来能力强，实际是把 SQL QueryPlan、权限、Tool 执行和答案生成全搅在一起，预算和责任都查不清。M38 的解法是**让计划变薄**：

   **HybridPlan（混合计划）**只包含受控 operator、SQL/RAG 各自的问题和 RAG 的 Evidence requirement，相当于一张“去哪两个窗口、各办什么事”的短表单。当前只登记两类 canonical 问法：退款原因+规则、GMV 值+口径；没登记的 Hybrid 照样安全停止。Graph 固定为 `route → hybrid_sql_tool → hybrid_rag_tool → controller`，SQL/RAG 各至多一次、总计至多两次。

   这里没有为演示接远程 Planner，也没有让 Router 看正文——宁可覆盖窄，也要守住“Router 只计划、不执行、不授权、不写答案”。专项测试和 `phase4-harness-hybrid-v1` 都检查 branch budget 与单次 Graph，证明这两类受控操作能稳定执行，不代表系统能理解任意开放式跨来源研究问题。

2. **让 Synthesizer 看 Evidence，而不是拼两个子答案**

   两条链路内部其实都有完整证据——SQL adapter 能构造 typed SQL Evidence，RAG AnswerFlow 有完整的 Document Evidence——但公开的 `ToolObservation` 只保留安全投影。如果 Hybrid 只拿公开结果，就只能拼两个自然语言子答案：既验证不了原始证据，还可能把 RAG 的 Composer 重复调用一次。

   M38 于是在 Harness 内部加了一条 **private typed Evidence seam（私有类型证据接缝）**：SQL 分支照旧在 SQL Guard 之后构造 SQL Evidence；RAG 新增 `prepare_for_hybrid()`，复用 Knowledge Tool、active release、ACL 双检和 Shared Gate，但在 Composer 之前停下。也就是说，RAG 分支只交付“这些文档证据已经被允许给合成器看”，**不先写一段 RAG 答案**。

   唯一的 **Hybrid Synthesizer** 只消费同一 run、已到 `generation_visible`（允许进入生成器）阶段的 SQL/Document Evidence，跨来源 claim 必须同时绑定两种 evidence id。API 和 JSONL Trace 不读取完整 Evidence，所以文档正文和 Hybrid SQL 的完整 rows 都不会落盘。真实 API/Trace 测试验证了双 citation 和非泄露投影——这不意味着任意文档组合都能自动拼出高质量结论，检索质量是后面 P6 的事。

3. **把完整、partial、冲突和合成失败都交给唯一 controller**

   “两个 Tool 都能跑”不等于“结果可以安全回答”。缺了必需文档分支还输出完整结论，或者遇到冲突时让模型静默选边，用户看到的答案会比证据更自信。所以 M38 把最终裁决权全部收进 controller：

   SQL/RAG 默认都是 **required branch（必需分支）**——两支 Evidence 都可用，controller 才允许 `complete`；只有一支可用时，最多返回它独立成立的 `partial`（部分结果），并明确不形成跨来源结论。SQL Guard 是全局停止，不能用文档规则把危险查询包装成建议；RAG ACL 被拒绝时，公开 branch 摘要不含真实原因或 EvidenceRef，避免侧信道。

   冲突由结构化 fact key 固定为 `hybrid_evidence_conflict`，不让模型选边；Synthesizer invalid/unavailable 时也不重跑 SQL/RAG，只由独立 fallback 输出单来源 partial 或停止。complete、SQL/RAG partial、ACL 非披露、SQL Guard、conflict、Synthesizer failure 和 artifact 篡改都有测试。目前冲突只在受控计划的结构化事实键上裁决，不承诺自动冲突检测覆盖所有业务语义。

4. **把同一事实投影到 API、Trace 和独立 Eval**

   如果 API、Trace、Eval 各自重新猜一次 Hybrid 状态，很快就会出现“用户看到 complete、Trace 显示 partial”的口径漂移；反过来，Trace 为了调试直接落完整 Evidence，又等于新开一条数据泄露通道。

   M38 的做法还是老规矩：**从同一份事实投影，各取所需**。`AgentRunResult` 新增 Hybrid 私有事实，`/api/query` 只派生兼容 SQL 表格/图表视图、validated citation 和安全 branch summary；Trace 对 Hybrid 清空完整 SQL rows，不保存 Document body、private ledger 或被拒绝分支的真实原因。新的 **Hybrid sequence Eval** 采用“一题一次 Graph、多断言复用同一份 execution evidence”的协议，5 个 Scenario、25 条 required assertion，拒绝缺断言或伪造两次 execution 的 artifact。

   全仓 436 passed、3 skipped、1 warning，compileall 与 diff check 通过（3 个 skip 是既有 Milvus/远端 embedding 条件用例，warning 是既有 TestClient/httpx deprecation）。真实 Hybrid LLM、远程 embedding/Milvus、LangFuse Cloud 都没运行，所以这个结果证明的是**确定性控制与安全合同闭合**，不等价于真实线上质量、成本或开放问法效果提升。

### 新概念

- **HybridPlan（薄混合计划）**：只描述两个已知深 Tool 要做什么，不描述怎么回答。可以类比 Spring 服务层收到的受控 DTO：字段固定、职责很小，不能偷偷塞入执行结果或权限判断。
- **Required branch（必需分支）**：完整结论必须等所有声明必需的证据到齐；它像审批流程里的会签，少任何一个签字都不能把结果标成“已批准”。
- **Cross-source binding（跨来源绑定）**：一条同时谈数据和规则的 claim，要明确连接到 SQL Evidence 和 Document Evidence。不是“末尾放两个 sources”，而是能回查这句话的每个来源。
- **Gate-only RAG branch**：RAG 只做到检索、当前版本检查、ACL/用途授权和生成上下文，不提前生成子答案。这样一个 controller 才能对最终 claim 负责。
- **Safe partial（安全部分回答）**：不是“尽量回答一半”，而是只发布一份证据单独就能成立的结论，并明确不能推出跨来源关系。
- **Fail-closed（失败关闭）**：证据不足、权限拒绝、citation 非法或状态不闭合时，不猜一个看似合理的答案；这是企业数据 Agent 中“宁可少答，也不越权或乱答”的工程原则。

### 代码阅读路线

1. **从路由和薄计划开始**：`engine/harness/router.py` → `engine/harness/contracts.py`

   先看 `DeterministicRouter._hybrid_plan_for()` 怎样只为两类 canonical 问法签发 `HybridPlan`，再看 plan 的 required branch 校验。重点是理解 **Router 只决定“跑什么”**，不会看到正文、rows 或 Tool 输出。

2. **读双分支如何穿过同一张 Graph**：`engine/harness/graph.py`

   从 `_next_node()` 看 `hybrid` 如何进入 `hybrid_sql_tool`，再顺着 `_hybrid_sql_tool_node()`、`_hybrid_rag_tool_node()` 和 `_hybrid_controller()` 阅读。这里解决的是**预算和最终状态只有一个裁决点**；不必把每个 LangGraph API 背下来。

3. **看深 Tool 如何给出私有 Evidence**：`engine/harness/adapters.py` → `engine/rag/answer_flow.py`

   SQL 路径的 `_sql_observation()` 构造已 Guard 的 SQL Evidence；RAG 路径的 `prepare_for_hybrid()` 复用现有 retrieval/Gate，在 Composer 前返回。重点理解为什么 `raw_evidence` 只能留在进程内，不能直接加到 API schema。

4. **读本地合成与引用校验**：`engine/harness/hybrid.py`

   先看 `DeterministicHybridSynthesizer` 如何把受控 operator 变成结构化草稿，再看 `validate_hybrid_claims()` 如何检查 run、kind、stage 和双来源 binding。最后看 `build_safe_partial_drafts()`：它是合成器失败时的独立降级，不会重新调用 Tool。

5. **沿公开投影确认没有泄露旁路**：`app/api/query.py` → `app/schemas/agent.py` → `engine/trace/recorder.py`

   API 从同一个 `AgentRunResult` 派生兼容字段、citation 和 `hybrid_branches`；Trace 只拿安全摘要。这里要特别留意 denied branch 为什么统一显示 `branch_not_disclosed`。

6. **最后看可重复证据**：`eval/harness_hybrid_contracts.py` → `tests/test_m38_hybrid_*.py`

   Eval 固定 5 个 Scenario 和 25 条断言，测试再覆盖 API/Trace、partial、conflict、synth failure 与 artifact 篡改。它们共同回答“这一次到底跑了几支 Tool、凭什么 complete、失败有没有偷偷重跑”。

核心调用链：

`POST /api/query`
→ `run_turn()`
→ `Router 生成 HybridPlan`
→ `SQL Tool（Guard + SQL Evidence）`
→ `RAG Tool（retrieve + Gate + Document Evidence）`
→ `Hybrid controller / Synthesizer / validator`
→ `AgentRunResult`
→ `API + JSONL Trace + Hybrid Eval`

**模块闭环**：M35 建立单轮唯一 Harness，M36/M37 把澄清和一次追问做成有界流程，M38 再让同一次运行安全汇合两类 Evidence。它们共同把 DataPilot 推到 **P5 的保守 Hybrid 基线**：能双取证、能证明、也能在失败时收住。

### 设计要点

- **正式本地 Synthesizer，不是临时简化版**：当前目标是证明双 Evidence、required、partial/conflict 和 citation 的控制合同；远程 LLM 会新增 question、SQL 结果、Document Evidence 的出站决策，不能为了自然措辞偷偷放行。
- **不拼子答案**：两个已写好的自然语言答案各自可能省略条件或使用不同口径；直接拼接无法验证最终跨来源 claim，也会形成双 Composer 责任。
- **完整 Evidence 不公开**：Harness 内部需要它来验证，API/Trace 只需要最小安全投影；这和后端把 ORM 实体与 DTO 分开，是同一种边界控制。
- **P5 已闭环但范围仍窄**：两类 canonical operator、串行两支、一次 initial Hybrid；开放 Router、optional branch、Hybrid follow-up、远程 adapter、生产认证和长会话都不是本模块结论喵。

### 有面试价值的亮点

1. **“让合成器吃证据，而不是吃两个答案”**：Hybrid 最省事的做法是把 SQL 和 RAG 的自然语言答案拼一段。我让 RAG 分支在 Composer 前就停——只交付“这批文档证据已经过 Gate、允许给合成器看”，最后唯一 Synthesizer 直接消费 typed Evidence，跨来源 claim 必须同时绑定 SQL 和 Document 两个 evidence id。效果是“这句话凭什么成立”可以回查，而不是文末摆两个 source 装样子。

2. **“会签制：缺一支就 partial，冲突就停”**：SQL/RAG 默认 required（必需分支），像审批会签——少一个签字就不能标“已批准”。只剩一支时，输出它单独成立的 partial 并明说不能下跨来源结论；两支打架记 `hybrid_evidence_conflict`，不让模型选边；SQL Guard 拦截是全局停止，不能用文档规则把危险查询洗白。模型在这里没有自由裁量权，这是企业数据 Agent 和聊天机器人最大的区别。

3. **“合成失败不重跑已经成功的那支”**：Synthesizer 挂了怎么办？重跑 SQL/RAG 会超出分支预算、重复查询还可能得到不同数据。所以 fallback 只消费已经到手的一支 Evidence，输出安全 partial 或停止。已成功的事实不因为展示层失败而被浪费，这个降级边界我可以用测试反例现场讲。

### 面试官追问

1. **[基础追问] 为什么 Hybrid 不能直接把 SQL 和 RAG 的两个答案拼起来？**

   两个子答案只能证明各自“写过一段话”，不能证明最终那句跨来源结论同时受两类 Evidence 支持。它们还可能采用不同条件或遗漏权限状态。M38 让 RAG 分支停在 Gate，最终 claim 由唯一 Synthesizer/validator 生成并绑定两个 evidence id，因此可以检查 run、Evidence kind 和 stage；这比末尾拼两个 source 更可审计。

2. **[工程/深挖追问] 既然两支都是 required，为什么还允许 partial？会不会误导用户？**

   required 的意思是“不能形成完整跨来源结论”，不是成功分支的独立事实也必须丢掉。partial 只在计划预先允许、且一支 Evidence 单独能支持的情况下输出，并明确说明不能形成跨来源结论。SQL Guard 则更严格：它是安全拦截，RAG 不能拿来淡化危险请求；ACL 拒绝的文档分支也不泄露 ref/reason。完整、partial、blocked 的差异由 controller 的四轴状态和测试断言，而不是靠最终文案猜测。

3. **[工程/深挖追问] Synthesizer 不可用时为什么不重新跑 SQL/RAG，或切到远程 LLM？**

   已经成功的深 Tool 是本轮已获得的事实，重跑会超出父级预算，也会造成 SQL 结果变化或重复查询。M38 的 fallback 只消费已验证的单支 Evidence，给出安全 partial 或停止。远程 LLM 则是另一个数据出站用途，需要 question、SQL safe result、Document Evidence 的逐字段授权和真实运行证据；用户当前确认的是本地方案 A，所以不能把“兜底”变成未经授权的外发。

4. **[压力追问] 你只支持两类 Hybrid 问法，这不就是把 demo 规则写死了吗？**

   这个质疑合理。当前价值不是展示通用自然语言推理，而是先验证双 Evidence 的控制合同是否成立：两支预算、ACL、required、冲突、citation、API/Trace/Eval 要先有可信答案。两类 operator 让每一步都能确定性复现，5 个 Scenario/25 条 required 和全仓回归也能准确归因。如果后续开放问法确实形成稳定失败簇，才会比较规则扩充、远程 Router 或 Synthesizer，并先做 outbound、held-out 和预算决策；在那之前，把未知问题保守停止比假装通用更诚实喵。

### 验证与下一步

- **M38 专项/API Trace**：`9 passed, 1 warning in 12.04s`，覆盖 complete、partial、ACL 非披露、SQL Guard、conflict、Synthesizer failure、artifact 篡改和真实 HTTP/Trace。
- **M36/M37 回归**：`12 passed in 0.85s`，证明澄清和一次 follow-up 没被 Hybrid 扩张。
- **Hybrid Eval**：`phase4-harness-hybrid-v1` 为 5 Scenario / 25 required assertion；它是确定性控制/安全合同，不与 M27/M34 质量基线混算。
- **全仓确定性回归**：后台任务退出码 0，`436 passed, 3 skipped, 1 warning in 599.87s`；compileall 与 `git diff --check` 通过。
- **下一步**：按 P6 对 M34 的 lexical 漏召回、context packing、Composer support rejection 做 go/no-go。不要把 Router 放宽、远程 Synthesizer、optional branch 或 Hybrid follow-up混入同一模块。

可复制验证命令：

```powershell
# M38 合同与 API/Trace 聚焦验证；预计 9 passed 和 1 个既有 TestClient/httpx deprecation warning。
python -m pytest -q -p no:cacheprovider tests/test_m38_hybrid_harness.py tests/test_m38_hybrid_eval.py tests/test_m38_hybrid_api_trace.py --basetemp=.agent_work/temp/m38-review

# 全仓确定性回归；收工快照为 436 passed、3 skipped、1 warning，通常需要数分钟。
# 按 AGENTS.md，预计超过 2 分钟时请使用后台任务，并将日志/退出码/完成标记放入 .agent_work/temp/。
python -m pytest -q -p no:cacheprovider --basetemp=.agent_work/temp/m38-full-recheck

# Python 语法/导入编译；预计无输出并以 exit 0 结束。
python -m compileall -q app engine eval tests
```

**本地启动体验：** 先按 `docs/state/runbook.md` 准备数据库/seed 和 local/demo 环境，再启动 FastAPI：

```powershell
# 环境未激活时，使用 AGENTS.md 中的完整 Python 路径。
python -m uvicorn app.main:app --reload
```

打开 **Swagger UI**：`http://127.0.0.1:8000/docs`，调用 `POST /api/query` 并提交：

```json
{
  "question": "查询退款原因并说明退款政策",
  "user_role": "ops",
  "force_new_pipeline": false
}
```

预计返回 `route=hybrid`、`answer_status=complete`、两条分别标为 `sql` / `document` 的 citation，以及 `hybrid_branches` 中 SQL/RAG 的安全摘要。Trace 会有 `route → hybrid_sql_tool → hybrid_rag_tool → controller`，但不会保存文档正文或完整 Hybrid SQL rows。当前是 **local/demo fixture caller**，且 Hybrid 不会签发 M37 follow-up；不要把这次体验解释为开放 Hybrid、远程模型或生产认证。

## ★ M39 P6 RAG Subgraph 入场证据审计

（2026-08-17）

**简述**：用已经完成的 M34 证据做了一次**只读资格审查**，结论是当前没有资格建设多步 RAG Subgraph；保持 lexical 默认，比为了展示 Agent 而增加循环更可靠。

### 先用大白话讲

M34 发现了不少 RAG 问题：有些正确文档根本没被找到，有些找到了却没装进上下文，还有些是模型写出的内容过不了严格引用合同。它们都可能让最终回答不好，但**不是同一种病**——就像“片子没拍清、药没吃够、身体过敏”都会让人不舒服，治法却完全不同。

如果看到“答案不够好”就立刻加一个会反复搜索的 Agent 子图，等于医院看到所有病人发烧都开同一种药：多花钱多花时间，还治错位置。M39 做的是**先看片子再决定动不动手术**：只读已经冻结的 M34 结果，把 60 个病例分成“没找到文档 / 没装进上下文 / 引用合同没过 / 服务当时挂了 / 分不清”五类，再检查有没有证据证明“看完第一次结果再决定下一步取什么证据”真的能新增有效证据。结果没有：所以 P6 的正确结论是 **no-go**，先不建 Subgraph。这不是拒绝进步，而是拒绝没有依据的复杂化。

### 这次做了什么

这一步不写任何线上代码，只回答一个问题：M34 留下的失败数字，够不够支撑建设多步 RAG Subgraph？M39 把“是否值得增加复杂度”变成可复核的工程判断，避免把质量问题、外部不可用和架构选择混在一起。

1. **先把历史证据锁死，防止拿错材料做结论**

   M34 的 lexical、semantic、Answer Eval 是不同时间、不同配置的产物；文件被替换、split 混了、adapter 或 Composer 不一样，继续比较就像把不同班级的考试卷放进同一张排名表。所以审计的第一件事是**锁死输入**：`audit_paths()` 对六份指定 JSON 同时校验 SHA-256、dataset/question-set/split/profile identity、dev/held-out（开发集/保留决策集）、retrieval adapter+recipe 和 Composer identity。这叫 **closed-world（封闭输入）**——审计只承认这组冻结材料，缺文件或不一致就失败关闭，不会“凑一个 no-go”。

   真实审计的报告身份是 `324ec7f8...b726c6`，全程零 provider 调用。选择“只读旧材料”而不是“重新跑一次试试”，因为本模块要判断的是已有证据能不能支持路线，不是偷偷开一轮新实验。它证明输入可追溯，不证明答案质量提升。

2. **把失败按 Evidence 流转阶段分层，而不是把低分都叫检索差**

   低 citation coverage 的锅至少有四个候选：top-20 根本没召回 gold、召回了却没进入 generation-visible、Composer 的 support 合同拒绝、provider 暂时不可用。全当成“应该循环检索”，未来的实现就会针对错误层次优化。

   `build_p6_readiness_audit()` 用同一次 lexical retrieval 的 @20 覆盖和 AnswerFlow 的 `candidate → selected → generation_visible → cited` ledger（证据流转账本）分层，把 60 个 dev Scenario 互斥归为五类：**retrieval 11、context/packing 13、Composer 10、provider unavailable 2、not classifiable 24**。`not_classifiable` 不是偷懒，是承认阶段证据不足时不硬猜。这就像后端排障先分清是数据库没查到、DTO 丢字段、校验器拒绝还是外部服务超时——宁可保留“不知道”，也不把错误归因包装成一个看似更智能的 Graph。

3. **把 held-out 当期末卷，不拿来设计补救动作**

   120 条 held-out 已经跑过一次，里面当然也存着逐题信息。如果开发时按这些失败去挑 query rewrite、top-k 或 parent 扩展，后面的 A/B 就变成“看过答案后的考试”，分数再好看也不可信。所以 M39 只对 60 条 **dev** 逐题分类，held-out 只用于 split 和 identity 的闭合核验，给未来真正有候选动作时留一组没被调参污染的决策集。专项测试还守住两条线：provider failure 不得伪装成 retrieval gap；错误 runtime/split/hash 必须失败关闭。

   这一点的立场要说清楚：不是拒绝改进 RAG，而是保护未来改进的评测公信力；当前没有证据证明的是任何一个具体的 query rewrite、parent/child 或 rerank 会有效。

4. **用四项入场条件给出 no-go，而不是留下模糊“以后优化”**

   参考项目确实有 RAG Graph，但“别人有 Graph”不是 DataPilot 也加 Graph 的证据。真正的子图至少要能说清：第一次 Observation 看到了什么、允许做哪个下一步动作、能新增什么 Evidence、何时停止、增加的调用和延迟值不值得。

   M39 的报告把四项入场条件逐项列出：**可复现非 provider 失败簇**和**dev/held-out 隔离**满足；但没有任何已验证的 **Observation 驱动新增 Evidence 动作**，也没有**可比额外预算**。任一条件缺失即为 `no_go`。所以没有实现 Subgraph、没有切 semantic、没有改 `enterprise-lexical` 默认，也没有用“先做简化版以后再换正式方案”绕过门槛。

   5 项专项测试、203 项 M31–M38 相关回归和后台全仓 441 passed、3 skipped、1 warning 都通过，说明审计和既有合同没有被破坏；这不证明多轮 RAG 的质量、成本或生产价值已经被验证。

### 新概念

- **Readiness audit（入场审计）**：不是效果评测，而是判断“现有证据是否足以授权下一类复杂实现”。类似上线前的变更评审：不是问代码能不能写，而是问该不该写、依据够不够。
- **Closed-world input（封闭输入）**：只接受身份和哈希都匹配的一组文件。它像数据库迁移校验 schema version，避免把看似格式正确但来源不同的数据混进结论。
- **Failure taxonomy（失败分类）**：给每个 Scenario 一个互斥的主失败层，方便定位责任。它不是给系统贴标签，而是防止把 Composer 或 provider 问题误交给 retrieval 去解决。
- **Held-out pollution（保留集污染）**：用期末卷的逐题答案调参数后，再拿同一份卷子证明效果，会高估真实收益。M39 只消费 dev 的逐题信息，保留 held-out 的未来决策价值。

### 代码阅读路线

1. **先读审计核心**：`eval/subgraph_readiness.py`

   从 `audit_paths()` 开始看六份文件如何完成 hash/identity/runtime 闭合，再读 `build_p6_readiness_audit()` 如何严格限制为 dev 分类。重点是理解 **输入不可信时为什么失败关闭**，而不是记住每个 JSON 字段。

2. **再看失败分类**：`eval/subgraph_readiness.py` 的 `_classify_dev_execution()` 与 `_stage_document_counts()`

   前者按 provider、Composer、retrieval @20 和 ledger 阶段顺序选择唯一主层；后者把最终 ledger stage 还原为累计可见范围。它们解决的是“同一失败到底属于哪里”，并刻意保留 `not_classifiable`。

3. **看命令行入口和安全报告**：`scripts/audit_m39_p6_readiness.py` → `eval/reports/m39-p6-readiness.md`

   CLI 显式接收六个路径，只调用本地审计函数；Markdown 只输出身份、计数和条件，不写题目、正文、完整答案或 Evidence。阅读时留意 `sys.path` shim 只是让脚本能导入仓库模块，不会启动 RAG runtime。

4. **最后看反例测试**：`tests/test_m39_subgraph_readiness.py`

   测试用最小 JSON fixture 验证 held-out 不进入 taxonomy、provider 不被算成 retrieval、split/runtime/hash 篡改失败。它们比只看一次成功报告更能说明安全边界。

核心数据流：

`六份冻结 M34 JSON`
→ `SHA / identity / split / runtime 校验`
→ `仅 dev 的 retrieval + ledger 分层`
→ `四项 P6 条件`
→ `安全 JSON / Markdown no-go 报告`

### 设计要点

- **no-go 是交付，不是空白**：它明确保留了 lexical 默认，并给出以后重新打开 Subgraph 的证据门槛。
- **不把 gold 放回运行时**：gold 只作离线分类锚点，不能进入 Tool、Gate 或 Composer；否则相当于考试时偷看标准答案。
- **不替代现有安全链路**：审计不改 Knowledge Tool、AnswerFlow、ACL、outbound、Harness 或 Hybrid；它只读历史 artifact。
- **后续必须独立立项**：只有未污染 dev 证明具体允许动作可以新增 Evidence，并冻结 held-out 协议和可比预算，才可经用户确认另建 M40；否则按 P7 收口喵。

### 有面试价值的亮点

1. **“先看片子，再决定动不动手术”**：M34 有一堆失败数字，最诱人的结论是“加一个会反复检索的 Agent 子图”。但失败至少有四层：没召回、没装进上下文、Composer 拒绝、provider 挂了——只有第一层才可能靠检索循环解决。我把 60 个 dev 题互斥归层（retrieval 11 / packing 13 / Composer 10 / unavailable 2 / 不可分类 24），结论是：没有任何证据证明“看完第一次结果再取证据”能新增有效 Evidence，所以严格 no-go。

2. **“held-out 是期末卷，不是练习册”**：120 条 held-out 已经跑过，逐题信息就摆在那。拿它挑 query rewrite、top-k 或 parent 扩展，后面的 A/B 就变成“照着答案复习再考同一张卷”。我只核验它的身份和 split 闭合，不消费逐题结果，给未来候选留一组没被调参污染的决策集。

3. **“no-go 是交付物，不是空白”**：有人觉得“没写代码就是没产出”。这个模块交付的是一条可复核的路线结论：四项入场条件逐项打勾，缺了“Observation 驱动新增 Evidence”和“可比额外预算”两条，所以不建 Subgraph、不切 semantic、不改 lexical 默认。它拦下的是“因为别人有 Graph 所以我也要 Graph”的从众工程——这一句放在面试里非常有记忆点。

### 面试官追问

1. **[基础追问] 既然检索和上下文有 24 个失败，为什么不直接做多轮 RAG？**

   失败数量只能说明当前固定 Pipeline 有问题，不能说明循环动作能解决它。多轮 RAG 必须明确第一次 Observation 触发什么动作、该动作会新增什么 Evidence、何时停止以及额外成本。M39 只有固定单轮运行的证据，没有这条因果链；直接实现会把“猜测可能有效”伪装成工程结论。

2. **[工程/深挖追问] 为什么 held-out 只做身份核验，不能用来分析失败？**

   held-out 的作用是未来判断新候选是否真的泛化。如果先按它的逐题失败选择 rewrite、parent expansion 或参数，之后的提升很可能只是对这 120 题过拟合。M39 用 hash、split 和 execution 闭合确认它仍是同一份期末卷，但不消费逐题信息；这比“多拿一点数据调得更好”更能保证后续 A/B 的可信度。

3. **[压力追问] 你做了一堆审计，却没有提升答案质量，这是不是工程自嗨？**

   这个质疑合理：M39 的产出不是用户可见的更好答案。它解决的是路线风险——如果没有 Observation 驱动新增 Evidence 和可比预算的证据，直接加 Agent loop 可能只会增加延迟、费用、出站面和排障复杂度。M39 用冻结 artifact、5 项专项测试、203 项相关回归和 441 项全仓回归把 no-go 变成可复核结论；下一步若要追求质量，需要另立单变量 Pipeline 实验或按 P7 收口，而不是把未知收益说成已经实现喵。

### 验证与下一步

- **专项审计测试**：`5 passed in 0.43s`，覆盖 taxonomy、provider 隔离、split/runtime/hash 失败关闭。
- **真实历史证据审计**：读取六份 M34 artifact，得到 `recommendation=no_go` 和 audit `324ec7f8...b726c6`，没有 provider 调用。
- **相关与全仓回归**：M31–M38 为 `203 passed, 1 warning`；最终全仓为 `441 passed, 3 skipped, 1 warning in 517.57s`。skip 是既有 Milvus/远端 embedding 条件项，warning 是既有 TestClient/httpx 弃用提示。
- **下一步**：按 Phase 4 roadmap 另行规划 P7；若日后要重开 Subgraph，先满足未污染 dev 的新增 Evidence 证据、held-out 协议和可比预算门槛。

可复制验证命令：

```powershell
# M39 专项测试；预计 5 passed。
python -m pytest -q -p no:cacheprovider tests/test_m39_subgraph_readiness.py

# 只读审计。前提：六份冻结的 M34 JSON 仍存在于 .agent_work/temp；预计输出 recommendation=no_go。
python scripts/audit_m39_p6_readiness.py --split eval/cases/enterprise-rag-bench-v1.0.0-split.json --lexical-dev .agent_work/temp/m34-lexical-tool-dev-retrieval.json --lexical-held-out .agent_work/temp/m34-lexical-tool-heldout-retrieval.json --semantic-dev .agent_work/temp/m34-semantic-tool-dev-retrieval.json --semantic-held-out .agent_work/temp/m34-semantic-tool-heldout-retrieval.json --answer .agent_work/temp/m34-answer-eval-full-v4.json --output eval/reports/m39-p6-readiness.json --report eval/reports/m39-p6-readiness.md
```

**本地启动体验：** 本模块暂无独立 API 或页面，因为它是一个**离线只读路线审计**，不是新的 RAG 服务能力。运行上面的 CLI 后，直接查看 `eval/reports/m39-p6-readiness.md`：你会看到 dev 的五类失败计数、四项 P6 条件和 `no_go`。报告不会展示题目、文档正文、完整答案或私有 Evidence。

## ★ M40 P7 跨路径 Trace 运行身份与阶段保证包

（2026-08-18）

**简述**：给每条 SQL、RAG、Hybrid 和多轮请求的 Trace 补上可安全回查的“运行身份证”，再把已有 Phase 4 合同收成一份不凑分的技术保证包；它证明控制链路闭合，**不等于**整个 Phase 4 已人工验收。

### 先用大白话讲

之前 DataPilot 已经能处理 SQL、查规则、混合取证、澄清恢复和安全拒绝，也分别有很多测试。但如果有人看到一条 JSONL Trace，仍要自己猜：这次 SQL 用的是哪条 runtime、RAG 用的是哪套 release 和检索 recipe、Hybrid 的合成器是什么；而且单项测试全绿，也不保证没有漏掉某个阶段合同。

M40 做的事像给快递包裹补一张**物流单**：不把包裹里的正文、SQL rows 或 thread 参数写上去，只写“这单走了哪条受控链路、用了哪个版本、有没有缺关键身份”。然后它固定了**五条真实故事**——SQL 一题、RAG 一题、Hybrid 一题、澄清恢复一次、安全拒绝一次——每条只跑一遍，把 response 和同一次 Trace 的“身份证”对起来盖指纹。最后用一张**九格检查表**把 P1 到 P7 该有的证据逐格打勾：少一格、被换成历史报告、或者 no-go 结论被偷改，整张表都判失败。这样系统不是“看起来测试很多”，而是能说明**这次结果从哪来、哪些合同已经验证、哪些仍然没有证明**。

### 这次做了什么

这一步不新增 Tool、Subgraph 或模型调用，只做收口：把散在各处的运行身份收成 Trace 上可复核的证据链，把 P1–P7 的合同收成一份不凑分的保证包，同时保留 M39 的严格 no-go。

1. **给 Trace 增加最小 runtime identity，而不是再造一套运行状态**

   同一条 Trace，SQL 的运行身份在 Evidence ledger 里，RAG 的 release、corpus、recipe、policy identity 在 diagnostics 里，Hybrid 又多了薄计划和 Synthesizer。Trace 消费者自己拼字段，容易因为某条 route 漏字段而误判，甚至为了“补齐”去读 private Evidence、正文或完整 rows。

   M40 新增 `phase4-trace-runtime-v1`：`engine/trace/runtime.py` 只从同一个 `AgentTurnResult` 已有的**安全投影**取值——SQL 读 safe ledger 的 `runtime_ref`，RAG 读已公开 diagnostics，Hybrid 记录 thin plan、Synthesizer identity 和每支的安全摘要。可以把它理解为后端 DTO：只搬运允许长期保存的坐标，不把 ORM 内部对象整个塞进日志。

   缺字段时写 `status=unavailable` 和 missing path，但 Trace 是旁路，不能把一次本来完成的 API 请求打成失败；P7 的固定演练会把 canonical 成功路径的 `unavailable` 判失败，防止空字典伪装成身份。测试覆盖 SQL 只读 safe ledger、缺 identity 不影响结果，以及 SQL/RAG/Hybrid/拒绝路径的完整投影。这里不证明任何新的模型、检索质量或生产 receiver 行为。

2. **用五条真实 API 故事证明“response 和 Trace 是同一件事”**

   分别测试 SQL、RAG、Hybrid，证明不了整条用户路径没有在 Trace 侧重新判断状态，也不容易一次覆盖澄清恢复和安全拒绝。M40 于是固定了五条真实 API 故事：`tests/test_m40_trace_rehearsal.py` 在隔离 SQLite、fixture caller 和临时 JSONL 中各执行一次 SQL、RAG、Hybrid、澄清→恢复、安全拒绝，每个 Scenario 都核对 trace id、route、四轴状态、Graph 次数、Evidence/citation 坐标、lifecycle 和 runtime envelope。随后把这些**同次安全投影**计算为 `execution_identity`，像给一张已核对的收据盖不可逆指纹；artifact 本身不含 answer 正文、rows、raw thread id 或结构化参数。

   实施中发现一个真实的取舍：恢复 RAG 之后，用户可见的 answer 自然会提到用户补充的业务主题。如果把“Trace 不出现任何补充值”理解成任何相同的词都不能出现，就只能删掉既有 Trace answer，等于改变长期 Trace 合同。用户最终选的方案 A：保留 answer 的既有可观测性，但禁止直接保存 raw `thread_id`、`clarification_answers` 和 `follow_up_fields` 结构或独立参数副本——区分“答案正常谈业务”和“把 thread 请求参数当日志字段落盘”。

3. **把 P1–P7 收成 closed-world assurance，而不是把分数平均成“总能力”**

   安全发布、RAG retrieval、RAG answer、Harness、turn、follow-up、Hybrid 和 M39 no-go，各有各的分母和 Gate。把它们和 M27 历史结果、M34 质量数字、人工说明直接混在一起，很容易拼出一个漂亮但不诚实的总分。

   `eval/phase4_assurance.py` 于是用 **closed-world（封闭清单）**把保证包锁死成九个 family：P1、P2 retrieval、P2 answer、P3、P4 turn、P4 follow-up、P5、P6 no-go、P7 rehearsal。每项都要有自己的 contract/artifact identity 且必须 passed；漏项、重复、顺序漂移、hash 被改、M39 不再是 verified no-go，都会失败关闭。CLI `scripts/run_m40_phase4_assurance.py` 只读已验证 rehearsal 和冻结 M39 报告，输出 JSON 与 Markdown matrix。

   这里有个微妙的点：P6 的 `no_go` 也写成“通过”——它通过的是“路线决策被如实验证并纳入保证包”，不是“RAG Subgraph 质量通过”。M40 聚焦测试验证了 family 篡改、缺路径、runtime 不可用和 CLI 输出；M31–M39 回归证明旧合同没被破坏。它不证明生产认证、真实外部服务质量、开放 Router、长期会话，更不能把 P7 technical Gate 说成 Phase 4 已经结束。

### 新概念

- **Runtime identity envelope（运行身份信封）**：Trace 上统一的最小版本/配置坐标。它像一次接口调用的 build 信息，不记录用户完整数据，却能让人知道这次结果是哪套受控链路产生的。
- **Cross-path rehearsal（跨路径演练）**：把多个真实用户故事固定下来，每条只执行一次，再从同一份执行事实做很多断言。它避免“为了测试 Trace 又重新跑一遍业务”的双账本问题。
- **Execution identity（执行指纹）**：对 trace id、四轴、runtime、Evidence/lifecycle 和预算等安全投影做 hash。它不还原正文，但能发现后来换了另一份执行事实。
- **Closed-world assurance（封闭保证包）**：不是平均分，而是一张必须填满的检查表。每个格子只接受指定 family 的身份和结果，陌生或历史数字不能补洞。

### 代码阅读路线

1. **先看 Trace 身份从哪里来**：`app/api/query.py::_record_trace` → `engine/trace/runtime.py::build_trace_runtime_identity`

   API 仍只投影同一个 `AgentTurnResult`；runtime helper 再按 SQL/RAG/Hybrid route 读取安全 ledger 或 diagnostics。重点理解 **Trace 没有重新路由或重新执行 Tool**，它只是记录已发生的安全事实。

2. **再看 Hybrid 为什么需要额外身份**：`engine/harness/contracts.py::HybridResult` → `engine/harness/graph.py::_hybrid_controller`

   M40 只给 `HybridResult` 增加 Synthesizer identity，并在真正生成 complete/partial 结果的 controller 处赋值。这样 Trace 能知道谁合成了结论，却看不到 prompt 或完整 Evidence。

3. **读 rehearsal 和反例**：`tests/test_m40_trace_rehearsal.py` → `tests/test_m40_phase4_assurance.py`

   前者让五条 API 路径各执行一次，后者验证 missing runtime、漏 family、M39 no-go 和 CLI 输出。这里解决的是 **一次执行、多断言共享证据**，而不是增加新的业务能力。

4. **最后读总保证包**：`eval/phase4_assurance.py` → `scripts/run_m40_phase4_assurance.py`

   先看 rehearsal validator 怎样拒绝漏/重路径，再看 nine-family catalog 怎样拒绝历史质量数字。CLI 只负责读取已验证输入、运行 deterministic family、写出 JSON/Markdown；它不会启动真实 LLM 或重跑 M34。

核心数据流：

`同一 AgentTurnResult`
→ `安全 runtime identity + JSONL Trace`
→ `五路径 response/Trace rehearsal`
→ `execution identity`
→ `P1–P7 exact-nine-family assurance`
→ `JSON / Markdown capability matrix`

### 设计要点

- **先保留旁路性质**：Trace 缺 identity 只做诊断，不把观测系统变成业务失败源；但 canonical 演练不能接受这种缺口。
- **同词不等于参数泄露**：用户确认 A 后，answer 自然包含业务主题是兼容的；直接保存 raw thread id 或结构化参数副本才是禁止项。
- **no-go 也应被验证**：M39 的 no-go 是一项严格路线结论，不是“没做完”的空白；P7 负责保证它没有被悄悄翻转。
- **不做阶段总分**：不同 family 的分母和含义不同，P7 只核验它们是否齐全可追溯；它不证明模型质量、生产授权或整个 Phase 4 已完成汪。

### 有面试价值的亮点

1. **“Trace 只贴物流单，不拆包裹”**：运行时身份散在三个地方——SQL 在 ledger、RAG 在 diagnostics、Hybrid 有 Synthesizer。我给每条 Trace 加最小 runtime identity，只搬运版本/配置坐标，不碰正文、rows 和 thread 参数，就像快递单写“哪条链路、哪个版本”，不写包裹内容。缺身份标 `unavailable`，但 Trace 是旁路，不能把成功的 API 打成失败；真正把它判失败的是固定演练层——这个“旁路不阻断业务、演练才收紧”的双层设计可以展开讲。

2. **“五条故事证明 response 和 Trace 是同一件事”**：分开测 SQL、RAG、Hybrid，证明不了整条链没有在 Trace 侧重新判断状态。我固定五条真实 API 路径——SQL、RAG、Hybrid、澄清恢复、安全拒绝——每条只执行一次，把同次安全投影哈希成 `execution_identity`，像给收据盖不可逆指纹，事后换一份执行事实立刻现形。

3. **“保证包是九格检查表，不是加权总分”**：P1–P7 各 contract 的分母不可比，加权平均会让一个高分掩盖一个安全空洞。assurance 只认九个 family 的身份和结果，漏项、篡改、顺序漂移都失败关闭；连 M39 的 no-go 也要原样验证写进“通过”——通过的是“路线决策被如实验证”，不是“Subgraph 质量好”。M27/M34 的历史质量数字在这里没有可填的槽位。

### 面试官追问

1. **[基础追问] 为什么 runtime identity 不直接从每个 Tool 的内部对象读取，拿到的信息不是更全吗？**

   更全不等于更安全。Tool 内部可能有 Document 正文、完整 SQL rows、原始授权过程或 prompt；Trace 是长期旁路存储，直接读取会多出一个泄露面。M40 只消费已经经过白名单投影的 ledger 和 diagnostics，相当于 Controller 返回 DTO 而不是 ORM 实体。身份缺失时保守记 unavailable，由 rehearsal fail closed，而不是为了日志完整性跨越数据边界。

2. **[工程/深挖追问] 为什么 P7 不把各个 contract 的通过率加权成一个百分比分数？**

   这些 family 的分母根本不可比：P1 是安全发布断言，P2 有 retrieval/answer 两层，P4 是 sequence，P6 是 no-go 路线审计。加权后一个高分 family 可能掩盖另一个必须存在的安全合同。P7 的目标是“所有必要门都在、来源未被替换”，所以用 exact catalog 和 identity 闭合；质量趋势仍留在各自的 M27/M34 账本里。

3. **[压力追问] 这不就是日志字段加几个 hash，再包一层报告吗？业务价值在哪里？**

   这个质疑有道理：M40 没有让用户答案更自然，也没有提高 M34 的召回率。它解决的是复杂 Agent 最容易被忽略的工程问题——当 API、Trace、Eval 和路线决策分别变多后，如何证明它们还是同一条受控事实链，而不是各自讲一个故事。M40 用五条真实路径、family 篡改反例、208 项相关回归和 447 项全仓回归说明这个闭环存在；它仍不替代真实质量、生产认证或人工验收。若要继续提升业务能力，必须按 M39 的证据门另立计划，而不是把 P7 的可追溯性冒充成效果提升喵。

### 验证与下一步

- **M40 专项**：`7 passed, 1 warning in 13.04s`，覆盖 C1 runtime identity/降级、C2 五路径演练与反例、C3 family/M39 no-go/CLI 输出。
- **受影响回归**：M31–M39 为 `208 passed, 1 warning in 51.21s`，说明 Evidence、RAG、Harness、thread、Hybrid 和 P6 no-go 没有回归。
- **全仓确定性回归**：后台任务退出码 0，`447 passed, 3 skipped, 1 warning in 503.36s`。skip 是既有 Milvus/远端 embedding 条件项；warning 是既有 TestClient/httpx 弃用提示。`compileall` 与 `git diff --check` 通过。
- **下一步**：先由用户人工检查 P7 five-path Trace 和 capability matrix，再运行 `accept-module`。不要因为 P7 technical Gate 通过就宣布 Phase 4、RAG Subgraph、生产认证或真实外部质量已经完成。

可复制验证命令：

```powershell
# M40 的 Trace / rehearsal / assurance 聚焦验证；预计 7 passed 和 1 个既有 TestClient/httpx warning。
python -m pytest -q -p no:cacheprovider tests/test_m40_phase4_assurance.py tests/test_m40_trace_rehearsal.py --basetemp=.agent_work/temp/m40-review

# 检查 Python 语法与导入；预计无输出并以 exit 0 结束。
python -m compileall -q engine/trace eval scripts/run_m40_phase4_assurance.py

# 从已验证的 C2 rehearsal JSON 生成 P7 assurance JSON/Markdown。
# 前提：--rehearsal 指向由五路径演练产出的安全 artifact；此命令只跑本地 deterministic family。
python scripts/run_m40_phase4_assurance.py --rehearsal .agent_work/temp/<m40-rehearsal>.json --output .agent_work/temp/m40-assurance.json --report .agent_work/temp/m40-assurance.md
```

**本地启动体验：** M40 没有新页面，仍通过现有 FastAPI 接口观察 Trace。先按 `docs/state/runbook.md` 准备 local/demo 环境和数据库/seed，再启动：

```powershell
# 环境未激活时，使用 AGENTS.md 中的完整 Python 路径。
python -m uvicorn app.main:app --reload
```

打开 Swagger UI：`http://127.0.0.1:8000/docs`，调用 `POST /api/query`：

```json
{
  "question": "查询退款原因并说明退款政策",
  "user_role": "ops",
  "force_new_pipeline": false
}
```

预计返回 `route=hybrid`、`answer_status=complete` 和 SQL/document citation。随后查看 `eval/traces/traces.jsonl` 的同一 `trace_id`：你会看到 `runtime_identity` 中的 thin plan、Synthesizer 与两支 runtime 摘要，但看不到文档正文、完整 Hybrid rows、raw thread id 或结构化 thread 参数。当前仍是 local/demo fixture caller；不要把这次体验解释成开放 Hybrid、真实外部模型或生产认证。

## ★ ★ ★ Phase 4 中下半阶段总结：M35–M40

（2026-08-18）

**简述**：这一阶段把上半阶段已经可靠的 SQL/RAG 深能力装进统一 LangGraph Harness，再逐步补上受控恢复、一次追问、双证据 Hybrid、Subgraph 入场审计和跨路径技术保证，使 DataPilot 从“有两个工具”演进为一个 **能路由、能停、能恢复、能组合、也能用证据拒绝错误扩张的有界 Agent 系统**。

### 先用大白话讲

上半阶段把 SQL 和 RAG 做成了两台能独立干活的专业机器；这一阶段要解决的问题是：**两台机器各自都会转，但谁来决定开哪台、开多久、失败怎么办？**于是建了一间"总控调度室"，用一条总闸管住所有入口。

调度室的规矩很保守，也很像真实的工厂调度：

- **一次只开一台**：看不懂问题就先停下问清楚，绝不把两台机器都开一遍碰运气；
- **补充单只许填指定栏**：资料不足时发一张限定字段的补充单（比如只补"分析对象"或"时间范围"），用户不能想填什么填什么；
- **追问也要领券**：任务完成后，用户明确开启追问，也只能从系统签发的动作里选一次，不能无限制追问；
- **双机联合作业走薄计划**：确实需要"数据 + 制度"一起回答的问题，调度室按一张很薄的计划依次调用 SQL 和 RAG，最后在一个汇合点核对两边证据，而不是把两台机器吐出来的答案粗暴拼起来。

这间调度室还刻意没有装"自动驾驶"：旧评测只能证明检索、上下文和生成各有毛病，证明不了"多搜一轮"就能搜出新证据，所以 P6 被判严格 `no_go`——没有证据，就不加循环。最后 M40 像总验收前的一场消防演练，把 SQL、RAG、Hybrid、澄清恢复和安全拒绝五条路径放进同一套 Trace 和保证包，确认每个入口记录的是同一份运行事实。

所以这一阶段的核心价值不是让 Agent 能无限行动，而是建成了 **每一步有入口、每次调用有预算、每个状态有归属、每种失败能停止、每项能力有独立证据** 的 Harness Engineering 基线。

### 这次做了什么

这一阶段面对的核心矛盾是：**底层 Tool 已经比较可靠，但系统还缺少一个不会越权、不隐藏调用、不把失败混成成功的上层控制面。**如果直接加入循环、长对话和多工具自动选择，底层已有的 ACL、Evidence、citation 与评测口径很容易被新的编排层绕开。M35–M40 因此沿着“先统一一次执行，再增加有限状态，再组合双证据，最后审计与收口”的主线推进。

1. **先建立唯一 Harness，让路由、工具和结果只服从一个控制面。**

   原来的 SQL 与 RAG 都能独立运行，但缺少统一入口时，API、Trace 和 Eval 可能各自理解“这次到底执行了什么”。某些系统会在路由不确定时默认同时查询数据库和知识库，这看似积极，实际会扩大成本、泄露面和错误来源。

   这一阶段做了三件事：

   - **顶层 LangGraph Harness（统一调度层）**：把一次执行固定为 `route → tool/terminal → controller`，Graph 只控制路线、预算和终止。
   - **deep Tool（深工具）**：Text2SQL pipeline 与 `RAGAnswerFlow` 整体作为一个深 Tool 接入，内部 Schema Retrieval、SQL Guard、ACL、Composer 和 citation validator 不被拆成一堆浅节点。这样 Graph 不会和 Tool 抢控制权，Tool 的安全合同也不会因换了编排框架而失效。
   - **保守 Router（路由器）**：先采用可注入的 deterministic/conservative 规则，未知问题和未登记 Hybrid 保守停止，而不是自动双后端兜底。

   还有两个安全点：

   - **Caller fail-closed（身份失败关闭）**：调用方不再由请求中的 `user_role` 自行授权，只有 `local/demo/test` 可以通过明确 fixture resolver 选择已解析角色；其他环境没有认证 resolver 时在 Tool 前失败关闭。
   - **四轴各归各位**：SQL 的技术失败、输出合同拒绝和 SQL Guard 拦截分别落到 execution、answer、safety，避免所有错误都被写成 `blocked`。

   **验证证据**：`phase4-harness-v1`、API/Trace 同轮投影，以及全仓 deterministic pytest **397 passed**。这些证据证明统一单轮控制面、Caller 失败关闭和深 Tool 边界成立；没有证明开放问法路由质量、生产认证或真实远程服务质量。

2. **把单轮执行加深为有界 turn/thread，但拒绝把它包装成长对话记忆。**

   单轮 Harness 遇到“这个怎么处理”或缺少分析时间范围时，只能拒绝或猜测。直接保存完整聊天历史又会带来权限继承、上下文膨胀、并发重放和服务重启语义等一整套问题。因此这一阶段只保存继续当前任务必需的最小状态。

   **第一步：结构化澄清。**

   - Router 只能签发 closed-world `ClarificationSpec`（闭集澄清规格），例如补 `subject` 或 `analytics_scope`，不能自由问任意问题；
   - 应用持有 **versioned in-process checkpoint（应用级、进程内、带版本号的任务检查点）**，记录 owner、tenant/active role、TTL（过期时间）、state version 和最小 current task；不保存完整 MessagesState；
   - **原子单 claim（领取执行权）**：claim 在慢 Tool 前完成，同一 version 最多一个请求获得执行权；
   - 非法补充值在 claim 前拒绝，不消耗 version；一旦 claim 后 Graph 失败，不退回 pending、也不自动重试，避免同一 Tool 被重复调用。

   **第二步：一次 follow-up（追问）。**

   - 默认关闭、显式开启（`enable_bounded_follow_up=true`）才有；
   - 可选动作由服务端签发，客户端不能自造控制指令；
   - **Evidence validity（证据有效性）按来源分别处理**：
     - SQL 没有可证明稳定的业务快照 → 每次追问都重查；
     - external RAG → 每次重检索；
     - 业务 22-entry release → 只有“解释同一 Evidence”动作，才允许按当前 authority/revision/content/anchor 重新加载、重新授权并签发新 run Evidence；requirement 或 identity 变化时，同一 RAG Tool 最多重检索一次；ACL/用途变化则零 retrieval 停止。

   这里最关键的不是“记住了上一句话”，而是 **旧结果不能天然成为新一轮事实**。thread id 不是授权凭证，旧 answer、rows、正文和 citation 也不会写进 checkpoint 后直接复用。

   **验证**：M36 的 `phase4-harness-turn-v1` 覆盖 8 组 sequence，全仓 **416 passed**；M37 的 follow-up Eval 覆盖 **10 sequences / 22 turn evidence / 50 required，50/50 通过**，全仓 **427 passed、3 skipped**。它们证明一次澄清恢复、一次追问、owner/version/TTL/concurrency 和 Evidence validity 合同成立；没有证明自由多轮、长上下文 compact、持久 checkpoint 或多 worker 会话。

3. **在同一个 Harness 中组合 SQL 与 RAG，但只允许受控双证据结论。**

   真正的业务问题常常同时需要“数据库里发生了什么”和“制度上应该怎么解释”。简单做法是分别生成 SQL 答案和 RAG 答案，再拼成一段文字；问题是两边可能冲突、某一支可能越权，而且最终结论很难证明用了哪些证据。

   P5 因此加入 **薄 `HybridPlan`（混合计划）**：

   - Router 只对两类 canonical operator 签发计划；
   - Graph 按 `hybrid_sql_tool → hybrid_rag_tool → controller` 依次执行两支，各至多一次，总计至多两次；
   - RAG branch 只运行 retrieval + Shared Gate，交付 `generation_visible` Document Evidence，不先生成一个自然语言子答案；SQL branch 交付经过 Guard 的 typed SQL Evidence；
   - 完整 Evidence 只存在于 Harness 内部，API/Trace 不读取正文或完整 rows。

   **唯一 `DeterministicHybridSynthesizer`（确定性合成器）**是正式默认和长期 fallback（回退方案），不是等待日后替换的临时桩。合成规则：

   - 跨来源 claim 必须同时绑定 SQL 与 Document Evidence；
   - 两支 required 才能标记 complete；
   - 一支失败，只允许另一支事先声明可独立成立时返回 partial（部分结果）；
   - SQL Guard 全局停止；
   - Evidence 冲突时不静默选边；
   - Synthesizer 失败也不重跑深 Tool。

   **验证**：`phase4-harness-hybrid-v1` 用 5 个 Scenario、25 个 required assertion 覆盖 complete、两类 partial、SQL safety、conflict、双 citation 和篡改拒绝；全仓 deterministic pytest 为 **436 passed、3 skipped**。这证明两支预算、Evidence 绑定和安全失败策略，不证明开放 Hybrid 意图理解、远程综合质量或真实大语料收益。

4. **用 go/no-go 审计决定是否进入 RAG Subgraph，而不是看到失败就添加循环。**

   M34 已经暴露 lexical 漏召回、多文档 context packing、Composer support 拒绝和 provider unavailable。如果把这些失败全部归结为“需要 Agentic RAG”，系统可能增加搜索轮数和 token，却没有任何证据表明第二次动作能找到新材料。

   P6 没有直接开发 Subgraph，而是只读核验六份冻结 M34 artifact：

   - 输入必须同时匹配 SHA-256、dataset/question-set/split/profile、retrieval runtime 与 Composer identity；不一致就失败关闭，不能拿不可比数据凑结论；
   - 审计只分类 60 dev，120 held-out 只校验身份和闭合，不读取逐题失败来反向设计动作。

   **dev 失败分类**：retrieval `11`、context/packing `13`、Composer `10`、provider unavailable `2`、not classifiable `24`（审计规则下未能归入前四类失败层的样本，含证据链无缺口的成功样本）。

   **go/no-go 结论**：现有证据确实包含可复现的非 provider 失败，也保持了 dev/held-out 隔离；但没有证明一种“由首次 Observation 选择的允许动作”能够新增有效 Evidence，也没有可比的额外预算，因此严格结论是 **`no_go`**。external lexical 默认不变，零 provider 调用，也没有预埋一个空壳 Subgraph。

   **验证**：专项测试 **5 passed**，M31–M38 回归 **203 passed**，全仓 **441 passed、3 skipped**。`no_go` 既不代表 RAG 质量已经解决，也不代表 Subgraph 永久没有价值，它只说明当前证据不足以授权这次复杂度扩张。

5. **最后用安全运行身份和 closed-world assurance，把各条路径收成同一份技术事实。**

   随着 initial、resume、follow-up 和 Hybrid 都进入 `/api/query`，仅靠“每个模块各自测试通过”仍可能出现拼装缝隙：API 返回一种状态，Trace 记录另一种状态；某条路径缺 runtime identity，却被总分掩盖；历史质量数字甚至可能被误填进当前技术 Gate。

   P7 做了两件事：

   - **`phase4-trace-runtime-v1`（安全运行身份）**：从同一 `AgentTurnResult` 的安全投影构造。SQL 只读取 safe ledger runtime ref，RAG 只读取已有 diagnostics，Hybrid 只增加 thin plan、Synthesizer 和安全 branch 摘要。缺 identity 时 Trace 记 `unavailable`，不阻断正常 API；但 canonical assurance 会把它判为失败，从而同时保留 Trace 的旁路性质和验收的严格性。
   - **五路径 rehearsal（演练）**：对 SQL、RAG、Hybrid、澄清恢复和安全拒绝各执行一次，用同次 response/Trace 计算不可逆 `execution_identity`（执行身份摘要），检查四轴、EvidenceRef/citation、Graph 次数、thread lifecycle 与非泄露。P7 manifest 只接受 P1、P2 retrieval/answer、P3、P4 turn/follow-up、P5、M39 P6 verified `no_go`、P7 rehearsal 共九个 exact family（精确家族清单）；M27 历史数字和 M34 质量分数没有可填槽位。

   **验证**：M40 聚焦最终 **7 passed**，M31–M39 回归 **208 passed**，全仓 deterministic pytest **447 passed、3 skipped、1 warning**。这证明当前五条 API/Trace 路径与九类技术证据能够闭合；它不等于用户人工验收、生产认证、真实 provider 质量，也没有把 P6 `no_go` 翻成 Subgraph 完成。

### 阶段主线图

```text
用户请求
  ↓
TrustedCaller + conservative Router
  ↓
M35 单轮 Harness：route → deep Tool / terminal → controller
  ↓
M36 turn seam：pending clarification → versioned claim → 一次 resume / clear
  ↓
M37 显式 follow-up：server-signed action → Evidence 重新授权 / 重取证
  ↓
M38 Hybrid：thin plan → SQL Evidence + Document Evidence → 唯一 Synthesizer
  ↓
M39 P6 readiness：冻结 artifact → dev failure taxonomy → strict no-go
  ↓
M40 P7 assurance：五路径 response/Trace 同源 → exact nine-family technical Gate
```

这条主线串起来的是一个完整控制问题：**谁有权发起任务、Agent 选哪条路、一次允许调用几次、跨轮事实是否仍有效、双来源如何汇合、什么证据允许增加循环，以及最终怎样证明所有路径没有各说各话。**

### 关键知识点串联

- **Harness Engineering / deep Tool**：Harness 不是把所有内部步骤都画成 Graph 节点，而是统一掌握路由、预算、停止和投影；SQL/RAG 自己继续维护内部复杂度。类似 SpringBoot Controller 调用完整 Service，而不是把 Service 每个私有方法都提升成 Controller 路由。

- **Agent loop 的关键是预算和停止，不是循环语法**：M36/M37 虽然没有开放 `while` 循环，却已经具备 pending、claim、resume、follow-up budget 和终止原因。一个只能做一次但能明确拒绝第二次的 loop，比一个可以无限重试却说不清状态的 loop 更可控。

- **Thread state 不等于长期记忆**：checkpoint 保存的是继续当前任务所需的最小状态、owner 和版本，不是完整对话历史。它解决并发与恢复合同，不解决跨会话用户画像、长期事实提取或语义记忆召回。

- **Evidence validity 比“记得旧答案”更重要**：跨轮复用的核心问题不是能不能读到旧内容，而是 authority、revision、ACL 和 requirement 是否仍然成立。业务同 Evidence 解释可以重水化，SQL 和 external RAG 则必须重新取证。

- **Hybrid orchestration 不是答案拼接**：两支结果先保持 typed Evidence，最后由唯一 Synthesizer 和 validator 形成 claim。required、partial、conflict 和 safety stop 都是计划的一部分，不是出错后临时猜测。

- **Go/no-go 是 Agentic 系统的负向能力**：一个成熟 Agent 不仅要知道什么时候行动，还要能用证据说明什么时候不该增加动作。M39 的价值就在于把“有失败”和“循环能解决失败”分开。

- **Runtime identity / closed-world assurance**：Trace 的运行身份像一张不含敏感货物的物流单；assurance manifest 像只接受指定箱号的验收清单。两者结合，既能跨路径对账，也防止拿无关历史成绩填补当前缺项。

### 阶段设计取舍

1. **保守 Router 优先于远程 Router**：先证明 route、Tool 和终止合同；开放问法覆盖窄是已知代价，只有形成 decision set 和稳定失败簇后才有依据比较模型 fallback。
2. **应用持有轻量 checkpoint，而不是直接采用 LangGraph checkpointer**：当前只需要 pre-Tool clarification 和一次追问，方案 A 能把 owner/version/TTL/并发做深；代价是重启与多 worker 不恢复，但没有预建一个用不到的持久化平台。
3. **一次 follow-up + closed-world action，而不是自由对话**：服务端签发动作和字段，旧 Evidence 必须重新验证；它牺牲开放度，换来预算、权限和重放语义可证明。
4. **确定性 Hybrid Synthesizer 是正式方案，不是临时桩**：当前两类 operator 可由代码可靠综合，且无需新增数据出站；远程方案必须等真实失败簇、逐字段 outbound 许可和 held-out 证据。
5. **P6 允许得出 no-go**：已有失败不能自动证明 Subgraph 有用；宁愿暂时少一个“Agentic RAG”标签，也不把 held-out 污染、额外成本和无效循环带进默认路径。
6. **Trace 缺 identity 不阻断业务，但 canonical rehearsal 必须失败**：可观测性继续是旁路，不把记录故障升级成业务故障；技术验收同时保持严格，不能因降级语义掩盖缺口。
7. **P7 不凑总分**：九个 family 各自证明不同合同，M34 质量数字与 M27 历史结果不能互相补分。整个阶段选择的是分层、可追溯的保证，而不是一个看起来漂亮却无法解释的综合百分比，汪。

### 有面试价值的亮点

1. **“节点边界跟着控制权走，而不是跟着函数走。”** 接 LangGraph 最容易犯的错，是把 Text2SQL 的每一步都画成节点：图看着很完整，实际上顶层图和深模块开始抢控制权，安全步骤还可能被图跳过或重排。我反过来做——Graph 固定成 `route → tool → controller`，两条成熟流水线整个包成深 Tool，顶层只管可信调用者、一次调用、预算和收口。收尾时再用五条真实路径证明 API、Trace、Eval 记的是同一份执行事实：面试官问“你凭什么说它们不会各说各话”，我能拿 447 条回归和五路径排练现场讲。

2. **“多轮能力，我做的是‘够用就好’的版本。”** 澄清只问服务端登记过的字段，补完恢复一次；追问默认关闭，动作和字段由服务端签发，只有一次预算；checkpoint 是应用持有的、带版本和 TTL 的待办卡，领取动作在锁里原子完成——同一张卡只有一个赢家。更关键的是证据纪律：SQL 永远重查、外部语料永远重检索，业务文档只有“还在解释同一条规则”才允许重水化。旧答案不会因为“看起来一样”就变成新事实。

3. **“Hybrid 做的是会签，不是拼作文。”** 两个深 Tool 各跑一次，唯一的确定性合成器直接消费证据：跨来源结论必须同时绑定 SQL 和文档两类 evidence id；缺一支只给 partial，并明说不能下跨来源结论；两支冲突就停，不让模型选边；SQL Guard 拦截是全局停。全程没有一个“第二模型”出来圆场——这是企业数据 Agent 和聊天机器人最本质的区别。

4. **“整阶段最有记忆点的，是一个‘不做’的决定。”** M34 失败数据出来时，最诱人的动作是上 Agentic RAG 循环。我没有动工，而是把六份冻结结果做只读审计：60 条 dev 逐题归层，120 条 held-out 只验身份不消费。结论是没有证据证明“第二次观察驱动的动作真的能新增证据”，也没有可比预算，所以 strict no-go、零 provider 调用。面试时“用证据决定不做什么”，比“我加了个循环”更能打。

5. **“企业数据 Agent 的默认值是‘不信’。”** 请求体里的角色字符串不能授权，只能从注入的固定身份里选一个；权限被拒的文档连“存在性”都不许从侧信道漏出去；Trace 只贴物流单——记链路、版本和身份坐标，不记正文、rows 和 thread 参数；出站默认拒绝。一句话：宁可不答、宁可少记，也不越权、不泄露。

### 面试官追问

1. **[基础追问] 这一阶段为什么能称为 Agent 系统，而不只是给两个接口加了路由？**

   因为 Harness 管理的不只是分类结果，还管理可信调用方、当前任务、状态迁移、Tool 预算、Evidence validity、失败停止和统一运行投影。initial、resume、follow-up 和 Hybrid 都必须经过同一 turn/Harness seam；前置 lifecycle 拒绝零次 Graph，accepted turn 恰好一次 Graph，Tool 次数也有上限。**它具备感知任务状态、选择受控动作、观察结果并按预算终止的闭环，只是动作空间被刻意限制。**

2. **[基础追问] 你们的多轮能力和普通聊天历史有什么本质区别？**

   普通聊天历史通常保存 messages，再让模型自行理解上下文；这里保存的是 closed-world task state、owner、version、TTL、budget 和最小 EvidenceRef。补充字段由服务端 spec 约束，旧结果是否可用由代码检查 authority/revision/ACL，而不是让模型看见旧对话后自行判断。**所以它解决的是任务恢复与证据连续性，不是通用闲聊记忆。**

3. **[工程/深挖追问] 为什么不把 Text2SQL 和 RAG 内部步骤都拆成 LangGraph 节点？这样不是更“可编排”吗？**

   节点更多不等于边界更清楚。Text2SQL 已经有 Schema Retrieval、QueryPlan、SQL Guard，RAG 也已有 Knowledge Tool、Gate、Composer 和 Validator；如果 Harness 再控制这些内部步骤，就会出现两层 controller，失败状态和重试权归属不清。当前 Graph 只消费深 Tool 的 typed observation，既保留模块内聚，也能统一预算和四轴。**只有未来确实需要在某个内部步骤暂停、恢复或跨 Tool 交互，并且有独立合同证据时，才值得上移节点。**

4. **[工程/深挖追问] 两个并发 resume 同时拿同一个 version，会不会把 SQL 或 RAG 调两次？**

   checkpoint manager 在慢 Tool 前用 `RLock` 做 owner、version、state 和 answers 校验，并原子地把 pending 变成 claimed；锁外才执行 Graph。这样只有一个请求获得执行权，另一个在 Graph 前结束。非法答案在 claim 前不消费 version，但一旦 claim 后失败也不会退回 pending 自动重试。sequence Eval 覆盖 concurrent single claim，**预算事实是“最多一次执行权”，不是依赖客户端自觉去重。**

5. **[工程/深挖追问] 业务 RAG 可以重水化 Evidence，为什么 SQL 和 external RAG 不也直接复用，减少一次调用？**

   业务 22-entry release 有当前 active authority/revision/content/anchor，可以对“解释同一 Evidence”的 requirement 做精确等价判断并重新授权；SQL 的 rows 没有冻结的业务 snapshot，直接复用可能把旧数据当现状；external profile 的运行身份和大语料条件也不进入业务 rehydrate seam。**复用资格来自可证明的 freshness 与权限合同，而不是因为缓存方便。**因此 SQL/external 强制重取证，requirement 或 identity 变化也重检索。

6. **[工程/深挖追问] Hybrid 两支都 required，一支失败又允许 partial，这两个规则矛盾吗？**

   不矛盾。`complete` 表示 Hybrid 计划的双来源目标已经满足，所以必须同时具备合法 SQL 和 Document Evidence；`partial` 是明确降级状态，只能发布事先证明可独立成立的一支，不能伪装成完整跨来源结论。SQL Guard 会全局停止，Document ACL 拒绝不会泄露被拒 ref，Evidence conflict 也不会静默选边。**required 定义完整成功，partial 定义安全失败后的有限价值，两者不能混用。**

7. **[工程/深挖追问] M39 为什么只看 dev，不读取 held-out 逐题失败？这样会不会浪费已有数据？**

   held-out 的作用就是在候选和决策规则冻结后提供未污染验证。如果先读取 120 题逐题失败，再设计 Subgraph action、Prompt 或预算，最终评测就变成针对答案调参。M39 只用 held-out 的 identity 和既有 aggregate 做闭合核验，动作依据必须先从 60 dev 形成。**这不是浪费数据，而是保留后续结论的可信度。**

8. **[工程/深挖追问] Trace identity 缺失为什么不直接阻断 API？既然重要，降级不是自相矛盾吗？**

   Trace 是旁路可观测性，记录故障不应让一个本可安全完成的业务请求变成不可用；所以 runtime identity 缺失稳定标为 `unavailable`。但在 P7 canonical rehearsal 中，它代表保证证据不完整，必须判失败。**运行时可用性和验收完整性是两种不同责任：前者允许旁路降级，后者不允许拿降级结果冒充闭环。**

9. **[工程/深挖追问] 九个 assurance family 为什么不能算一个总分，方便做趋势比较？**

   这些 family 的分母和语义不同：安全/release、retrieval、answer、Harness、turn、follow-up、Hybrid、P6 no-go 与 Trace rehearsal 证明的是不同合同。做平均分会让某个 family 的大量简单断言掩盖另一个 family 的 required 缺失，也可能把 M34 质量数或 M27 历史结果错当成当前保证。**closed-world manifest 追求的是每个必需槽位都有正确身份的证据，不是用总分抵消失败。**

10. **[压力追问] 你们没有开放循环、没有长期记忆，Router 和 Synthesizer 还是确定性的，这也能叫 Agent 吗？**

    如果把 Agent 定义成“模型可以自由决定并无限调用工具”，这个系统确实不是开放 Agent；这项质疑是合理的。这个阶段的目标是企业数据场景下的有界 Agent Harness：让系统在可信身份、闭集动作、Evidence 和预算约束内完成路由、一次恢复、一次追问和双工具汇合。已有证据是 turn/follow-up/Hybrid 三类 sequence contract、五路径 API/Trace rehearsal，以及 M40 全仓 447 passed；它们证明控制与安全闭环，不证明开放自主性。若未来真实任务需要更多动作，扩展前仍要用失败簇、Observation 新增 Evidence 和可比预算证明价值。**所以我会称它为有界、证据驱动的 Agent 系统，而不会包装成通用自主 Agent**，喵。

### 阶段成果与边界

**已经完成：**

- **P3 单轮 Harness**：SQL/RAG 进入唯一 Graph seam，保持深 Tool、四轴和 Caller fail-closed；
- **P4 最小有界状态基线**：结构化澄清、一次 resume、一次显式 follow-up、owner/version/TTL/concurrency/budget 与 Evidence validity；
- **P5 保守 Hybrid**：薄计划、双 required branch、typed SQL/Document Evidence、确定性 Synthesizer、safe partial/conflict；
- **P6 入场裁决闭环**：冻结输入、dev-only failure taxonomy、held-out 隔离和 strict `no_go`；
- **P7 技术保证闭环**：五路径 response/Trace 同源、safe runtime identity、exact nine-family assurance；
- **持续回归证据**：各模块独立 contract family 与最终 **447 passed、3 skipped、1 warning** 的 deterministic 全仓结果。

**没有完成或刻意不做：**

- **没有实现 RAG Subgraph**：P6 当前是经过审计的 no-go，不是功能完成；
- **没有开放式 Agent loop**：只有一次 clarification resume、一次 SQL/RAG follow-up 和固定 Hybrid 双分支预算；
- **没有长期/短期记忆系统**：不存在用户画像、跨会话语义记忆、自动 memory extraction 或长期召回；
- **没有长上下文 compact**：checkpoint 保存最小任务状态，不保存和压缩完整 messages；
- **没有持久化 thread**：进程重启、多 worker 不共享，tombstone 也未做容量驱动清扫；
- **没有生产认证**：local/demo/test fixture caller 不能冒充 JWT/OAuth/SSO 或真实 tenant 权限；
- **没有开放 Router、远程 Hybrid Synthesizer 或 Hybrid follow-up**；
- **没有证明真实回答质量提升**：deterministic contract、P7 technical Gate 与 M34 的真实质量基线必须分账；
- **没有证明生产就绪**：真实 connector ACL、增量同步、删除传播、外部服务稳定性、性能与 LangFuse Cloud 出站仍未完成。

阶段结论必须准确表述为：**P3、P4、P5 和 P7 的既定技术基线已经闭合，P6 已完成严格入场审计并得到 no-go；DataPilot 已具备有界 Agent Harness，但开放 Agentic RAG、长期记忆、生产认证和真实质量优化仍未完成。**

### 下一阶段怎么接

M40 已经通过技术收口和用户验收，因此下一步不应机械地把模块号递增，也不能因为 Phase 4 有了 assurance 就宣布所有能力完成。应从 roadmap、M40 Handoff 和防遗忘能力账本重新选择一个有证据的切片。

当前可以调查的方向包括：**针对 M34 召回/context packing 缺口设计单变量候选**、为非本地部署接入正式认证 adapter、为 deterministic Router 建开放问法 decision set，或在“重启恢复/多 worker 会话”成为 required Scenario 后规划持久 checkpoint。它们的触发条件不同，不能合并成一个大而全的“继续增强 Agent”模块。

若未来重开 P6，硬门保持不变：未污染 dev 必须先证明一种由首次 Observation 选择的允许动作能新增有效 Evidence，再冻结 held-out decision protocol 和可比额外预算，并由用户确认独立计划。在这些证据出现前，**保持 external lexical 默认和 strict no-go，本身就是当前系统正确的下一步状态。**

## ★ M41 RAG 真实产品链路 EvalOps 与 180 题分层诊断

（2026-08-23）

**简述**：M41 把 RAG 评测从“各模块单独测过”升级为“同一道题真实经过产品链路，并能逐层定位失败”；随后又把 M34 的 180 道 external（外部基准）题接入这套诊断体系，完成 60 道真实 dev（开发集）运行和人工复核。

> **后续入口简化（2026-08-23）**：business 的四个小套件已合并为唯一 `business`（5 题各 1 次）；裸 `smoke/basic/core/hard/reliability/full` 只表示 external，默认跑 dev。`held-out` 是封存终考集，只有明确说出才运行。下文 Smoke 数字是合并前历史实验，原 artifact 保持不变。

### 先用大白话讲

可以把 RAG 想成一个企业资料室：**检索员**负责找材料，**选稿员**决定哪些材料交给模型，**撰稿人**负责写答案，**档案员**检查引用是否真的指向原件。

以前我们分别检查过这些岗位，但存在一个明显空洞：M34 的真实大规模评测绕过了产品 Harness（顶层调度器），而产品 Harness 里的 RAG 又主要依赖确定性测试。就像“每个员工都通过了岗位考试”，却没有验证一位真实访客从前台进入后，整套办事流程是否闭合。

M41 做了两件关键事：

- **一题只办理一次**：真实请求只跑一次，检索、选择、生成、引用和回答评分都读取同一份证据，避免每个评分器重新问一遍模型；
- **失败分楼层登记**：没有候选材料是检索问题，材料找到了却没交给模型是选择问题，模型输出坏结构是 Composer（答案编排器）问题，引用漏掉则是 citation（引用）问题。

最后得到的价值不是一个漂亮总分，而是能回答：**这道题究竟坏在产品入口、检索、选材、生成、引用，还是答案语义本身。**

### 这次做了什么

M41 的核心矛盾是：**真实 RAG 质量证据与产品运行链路彼此断开**。本模块先建立 business RAG（业务知识 RAG）的产品端到端评测，再把 external 180 题接进同一套 Evidence（证据）和 Gate（门禁）体系，最后用真实 Qwen 运行暴露质量缺口与一个诊断误分类缺陷。

1. **把“每个模块各测各的”改成“一道题贯穿整条产品链路”。**

   每个 `Scenario`（评测场景）只发起一次 `/api/query` 请求，真实经过 Caller（可信调用者）、Turn（一次任务轮次）、Router（路由器）、Harness（顶层调度器）、RAG Tool（检索工具）、AnswerFlow（回答流程）、API（接口）和 Trace（运行轨迹）；随后所有评分、报告和人工复核都消费同一个 `RAGExecutionEvidence`（RAG 执行证据）。

   - **原来的问题**：如果 retrieval scorer（检索评分器）、citation scorer（引用评分器）和 answer scorer（答案评分器）分别重跑 Pipeline（处理流水线），同一题可能得到三次不同模型输出，还会重复花费 token（模型计费文本单位），最后无法确认这些分数是否来自同一张答卷。
   - **解决机制**：runner（执行器）先固化一次 execution evidence（执行证据），再由 scorer（评分器）、report（报告）、triage（失败归类）、review（人工复核）和 compare（对比器）只读投影。它类似 SpringBoot 中一次请求生成一份不可变业务结果，后续审计和报表都引用这份结果，而不是再次调用 Service（业务服务）。
   - **重要取舍**：M41 没把 M34 的 direct AnswerFlow（直接回答流）冒充产品 E2E（端到端）；历史材料缺少 API、Router、Harness 或 selected 层时，明确记录 `not_observed`（没有观察到），不补造通过或失败。
   - **验证证据**：business Smoke 的 2 个 Scenario 都真实经过产品 Harness，自动 required assertions（必须通过的断言）为 **23 passed / 0 failed / 0 not_observed**；其中无候选题没有调用 Qwen。
   - **尚未证明**：这次 business Smoke 只有两个窄场景，不能外推整个业务知识库质量、开放问法 Router 能力或多轮 Agent 能力。

2. **建立能追到具体责任层的 RAG failure funnel（失败漏斗）。**

   评测不再只问“答案对不对”，而是按真实数据流逐层保存 document key（文档标识）和合同结果。

   - **诊断顺序**：product runtime（产品运行层）→ retrieved（已召回）→ selected（已选中）→ generation-visible（模型可见）→ Composer/provider/support（编排器、模型服务商与支持原文）→ cited（已引用）→ answer correctness/completeness（答案正确性与完整性）。
   - **失败语义**：上游服务没返回结果时，下游是 `not_observed`，不是批量判错；模型已经返回但 JSON 结构或 `support_text` 合同不合法，则属于已观察到的 Composer 失败。
   - **人工语义复核**：`answer_status=complete` 只表示回答、support 和引用合同闭合；召回 gold（标准文档）、引用合法或字符串完全匹配，也都不能单独代表答案语义正确。因此人工 verdict（裁决）与自动 Gate 并列保存，不能互相覆盖。
   - **防篡改来源**：review bundle（复核包）绑定 completed artifact（完整评测产物）和每题 checkpoint（任务检查点）的 SHA-256 文件摘要；来源文件被替换后，校验会失败。
   - **尚未证明**：首版没有使用 LLM Judge（大模型裁判）。这是刻意选择，因为一个未冻结模型、Prompt 和 rubric（评分规则）的单一分数不能直接成为 required truth（硬性真值）。

3. **把 M34 external 180 题接入产品 Harness，而不是重新造一套题库。**

   external catalog（外部题目目录）直接读取 immutable dataset（不可变数据集）中的 question（问题）、gold（标准答案/文档）、题型、来源和单/多文档属性；M41 不复制 180 道题面，也不重新构建语料 profile（索引配置快照）。

   - **旧证据再利用**：离线 importer（导入器）合并旧 Answer artifact（回答评测产物）、dev/held-out retrieval artifact（开发集/保留集检索产物）和冻结 split（切分清单），生成 180/180 的分层历史报告，全程零 Tool、零 LLM。旧材料没有保存的产品层和 selection（选择）层诚实标为 `not_observed`。
   - **真实产品接线**：external Eval 使用已有 SQLite FTS5 lexical profile（SQLite 全文检索配置）只读查询，并通过 eval-only fixed-RAG Router 固定进入 RAG 分支，再走 Harness、RAG Tool 和 external AnswerFlow。
   - **安全边界**：fixed-RAG 只用于评测产品 RAG 分支，**不代表自然 Router 分类正确**；普通 API、业务 22 条 release、默认 Composer 和 external lexical 默认均未改变。
   - **真实 60 题结果**：60 道 dev 每题只请求一次 Qwen，共消耗 **137,299 tokens**。自动 Gate 为 failed，人工复核进一步证明“链路闭合”不能代替“答案正确”。

   | 视图 | 结果 |
   |---|---:|
   | 自动 primary triage：全层通过 | 24 |
   | 自动 primary triage：retrieval | 20 |
   | 自动 primary triage：product runtime | 7 |
   | 自动 primary triage：citation | 5 |
   | 自动 primary triage：selection | 4 |
   | 人工语义 verdict：pass | 18 |
   | 人工语义 verdict：fail | 26 |
   | 人工语义 verdict：insufficient evidence | 16 |

   candidate / selected / generation-visible / cited 的 gold 命中分别为 **35 / 30 / 30 / 24**（分母均为 60）。`exact-fact=0/60` 只是严格字符串下限，不能解读成语义正确率为零。

4. **真实运行不仅测出了质量问题，也测出了诊断系统自己的误报。**

   5 道题的 provider 请求其实成功了，但 Composer 输出违反结构合同；旧 adapter 让 `AnswerFlowContractError` 逃逸，最终被顶层误记成 `harness_contract_failure`。

   - **为什么严重**：如果错误层标错，后续团队可能去改 Harness，而真正需要处理的是 Composer 输出约束或解析策略。诊断体系一旦“把医生的问题当成前台问题”，比没有诊断更容易误导。
   - **修正方式**：RAG Tool adapter 现在把该异常记录为已观察的 Tool/Composer 失败；没有 internal result 时从 Trace 恢复诊断；新增 `composer_support_valid` assertion，并把其后的 citation/answer 层按证据标为 `not_observed`。
   - **证据纪律**：已经完成的 60 题 artifact 不改写、不重新签名、不偷偷重跑，而是明确标为 **pre-fix candidate（修复前候选快照）**。未来新 run 必须使用新 identity，不能伪装成严格同协议对比。
   - **验证证据**：修正后 M41 聚焦测试 **14 passed**，M31–M41 受影响回归 **229 passed**，全仓 **462 passed、3 skipped、1 warning**。

5. **M41 收工时还缺少真正面向使用者的 external 运行档位。**

   180 题本身带有 question type、source 和 document cardinality，但这些属于题目属性；`diagnostic_dev/held_out` 属于实验切分。它们都不能替代 Text2SQL 那种直接可运行的能力层级。

   - **当时缺口**：external CLI 主要暴露 60 dev / 120 held-out partition（分区），还没有完整的 `smoke/core/basic/hard/reliability/full` suite（运行套件）。
   - **影响**：上次 60 题只能叫一次 dev 子集诊断，不能称为完整的 RAG 分层运行体系；也不能让使用者用低成本 Smoke 后逐级扩大到 Core、Hard 和 Full。
   - **后续补充（2026-08-23）**：该缺口现已完成。完整 180 catalog 新增 basic/core/hard `64/74/42`，并提供 smoke/basic/core/hard/reliability/full；difficulty、60/120 partition 与 suite 三轴分离。compare-v2 还允许通过显式 runtime allowlist 做候选 A/B，未声明漂移继续拒绝。旧 60 dev 仍是 pre-fix candidate，没有被改签成新基线。

### 新概念

- **共享执行证据（shared execution evidence）**：一题只运行一次，把请求、检索漏斗、provider 尝试、引用和运行身份固化成一张“原始答卷”。所有评分器只能批改这张答卷，不能重新让考生答题。

- **失败漏斗（failure funnel）**：按照数据真正经过的顺序定位问题。检索没找到、找到但没选中、选中但模型不可见、模型输出坏结构、引用漏掉、答案语义错误，是六类不同问题，不能都压成一个 `failed`。

- **`not_observed`**：不是“错了”，而是“上游没有产生足够证据，无法观察下游”。例如 provider 超时后，不能断言 citation 错误，因为压根没有生成可供引用的答案。

- **closed-world（闭集）合同**：RunSpec、Scenario、assertion plan、runtime identity 和 checkpoint 顺序都必须来自预先登记的集合。它像后端枚举和数据库约束：未知字段或身份漂移直接拒绝，不能临时解释成“差不多”。

- **pre-fix candidate（修复前候选快照）**：真实运行后发现评分协议有 bug，原 artifact 仍保留原样，只在档案中标明它属于修复前协议。这样既保留历史证据，也避免把重写旧结果伪装成原始事实。

### 代码阅读路线

1. **先看题目和运行合同**：`eval/cases/rag/`、`eval/rag_e2e_contracts.py`
   `scenarios.yaml` 和 selectors 定义 business RAG 的 canonical catalog；`RAGScenario`、`RAGRunSpec`、`RAGExecutionEvidence` 冻结“一道题是什么、用什么 runtime 跑、要检查哪些层”。阅读重点是 **identity 如何进入 artifact**，不需要先抠每个序列化字段。

2. **再看一题如何穿过真实产品链路**：`eval/rag_e2e_runtime.py`
   主角是 `RAGProductExecutor`。它负责给 FastAPI app 注入 eval-only Composer/Router/runtime，发送一次真实请求，再从 API、Trace 和 RAG internal result 汇总 Evidence；退出后恢复 app state，避免评测配置污染普通 API。external 路径中的 `FixedRAGEvalRouter` 只固定选 RAG，不负责证明自然语言路由能力。

3. **理解产品 seam 为什么能被评测而不改默认行为**：`app/main.py`、`app/api/query.py`、`engine/harness/adapters.py`
   app state 只提供可选的 eval seam（接缝）；普通运行没有注入时继续使用原来的 Router 和 deterministic Composer。`RAGToolAdapter` 把 AnswerFlow 成功与失败翻译成 Harness 能理解的 observation，并在修正后正确接住 Composer 合同异常。

4. **看一次执行怎样变成 checkpoint 和 completed artifact**：`eval/rag_e2e_runner.py`
   runner 负责 once-only execution（只执行一次）、连续 checkpoint 前缀、resume、终态和 artifact 身份。重点看“Trace 已写但 checkpoint 未提交”为什么失败关闭：它避免不知道 provider 是否收费成功时再次请求。

5. **沿失败漏斗看评分和报告**：`eval/rag_e2e_scoring.py`
   scorer 从同一 Evidence 计算 route、retrieved、selected、generation-visible、Composer、citation 和 answer assertions。这里最重要的不是某个布尔判断，而是 **上游失败后下游何时应该 `not_observed`**。

6. **看 external 180 题如何复用原始数据**：`eval/rag_external_catalog.py`、`eval/run_rag_external_eval.py`、`engine/rag/enterprise_runtime.py`
   catalog 读取外部 immutable questions 和 60/120 split；CLI 组装 fixed-RAG 产品执行器；enterprise runtime 以 SQLite `mode=ro` 打开已有 lexical profile。因此真实 60 题 Eval 只查询，不会像历史 Text2SQL 问题那样反复往 collection 灌数据。

7. **最后看离线复核和历史兼容**：`eval/rag_e2e_review.py`、`eval/rag_m34_history.py`
   review 对 artifact/checkpoint 做 SHA-256 来源绑定并合并人工 verdict；history importer 只读旧 M34 artifact，缺什么层就写 `not_observed`。两者共同保证“复核旧答卷”不会变成“偷偷重考一次”。

核心调用链：

`External / Business Scenario`
→ `RAGProductExecutor`
→ `/api/query`
→ `Harness + RAGToolAdapter`
→ `RAGAnswerFlow`
→ `RAGExecutionEvidence`
→ `Scoring / Report / Triage / Review`

**模块闭环**：M31–M33 建立 Knowledge、Evidence、Answer 和 Citation 合同，M35 把 RAG Tool 接入 Harness，M41 则让真实 Qwen 答卷也能沿同一产品路径被保存、分层诊断和人工复核。

### 设计要点

- **一次执行，多视图消费**：避免 scorer 重跑造成模型波动、重复费用和证据错位。
- **自动合同与人工语义分账**：Gate 判断产品链路和确定性合同，人工 verdict 判断自然语言 correctness/completeness；任何一方都不能覆盖另一方。
- **业务数据出站采用独立 eval-only policy**：只允许已通过 active release、Caller、ACL 和 Gate 的指定政策/指标材料进入 Qwen；普通 API 不继承这个权限。
- **external fixed-RAG 不冒充 Router 能力**：它证明产品 RAG 分支，不证明开放英文问法会被默认 Router 正确分类。
- **旧 artifact 不补造证据，新 bug 不回写历史**：缺失层标 `not_observed`，协议修复后旧 run 标 pre-fix candidate。
- **运行体验补充已完成**：external 180 现有 basic/core/hard 难度与 smoke/basic/core/hard/reliability/full 套件；held-out 仍保持独立授权门，不能把开发套件完成偷换成最终质量通过，汪。

### 有面试价值的亮点

1. **“一张答卷，多个评分器。”** 我把真实 RAG Eval 设计成一题一次产品请求，检索、选择、生成、引用和答案评分都读取同一份 `RAGExecutionEvidence`。这样既避免重复调用大模型，也避免不同 scorer 拿到不同回答却被放进同一份报告。这个设计本质上是在 Eval 侧建立事件溯源式的事实中心。

2. **“失败不是一个红灯，而是一张楼层图。”** 我没有只做最终 answer accuracy，而是记录 candidate、selected、generation-visible、Composer/support、citation 和人工语义 verdict。真实 60 题跑完后，可以明确看到主要问题集中在 retrieval，而不是笼统说“RAG 不行”；同时也发现自动链路通过的题仍可能语义答偏。

3. **“评测系统也必须接受审计。”** 真实运行暴露 5 个 Composer 坏结构被误报为 Harness failure。我没有修改旧 artifact 或重跑覆盖，而是保留原答卷、标记 pre-fix protocol，再修正未来 assertion 和错误归层。这个处理能证明我关注的不只是模型效果，还关注评测数据的不可篡改和可比性。

4. **“真实数据出站不是换个 API Key 就结束。”** business RAG 文档并非公开 benchmark 数据，所以我没有复用 M34 的 public policy，也没有直接扩宽普通 API。最终单独建立 eval-only outbound policy，把允许的数据类别、接收方、用途和运行 identity 写入合同；安全类和未知类别在网络请求前拒绝。

5. **“敢把未完成写清楚。”** 180 题已经接入，60 题也真实跑完，但 external CLI 仍缺少 `smoke/core/basic/hard/full` 运行档位。我会把它定义为下一次明确的接口设计任务，而不是用 dev/held-out 分区偷换成完整分层能力。面试中能清楚区分“底层证据能力已完成”和“用户可操作的评测产品仍不完整”，比报一个大数字更可信。

### 面试官追问

1. **[基础追问] M41 相比以前的 RAG 测试，最关键的变化是什么？**

   最关键的变化不是题更多，而是 **真实答卷与产品链路终于统一**。M34 以前有大规模真实 Qwen 结果，但绕过产品 Harness；M35–M40 的产品路径又主要是确定性合同。M41 让同一道题真实走 `/api/query → Harness → RAG Tool → AnswerFlow`，并把一次执行形成的证据交给全部评分器和人工 review。

2. **[工程/深挖追问] 为什么不让每个 scorer 自己调用一次最擅长的评测入口？**

   因为生成模型有随机性和外部失败，同一题重跑后可能得到不同候选、答案和引用。那样 retrieval score、citation score 和 answer score 并不属于同一张答卷，还会重复花费 token。M41 选择一次执行后保存共享 Evidence；scorer 只读，若需要新增指标就扩展 Evidence 或离线投影，而不是重新调用产品链路。

3. **[工程/深挖追问] `not_observed` 和 `failed` 为什么一定要分开？**

   `failed` 表示已经看到某个合同不满足，例如模型返回了坏结构；`not_observed` 表示上游没有产生足够材料，例如 provider 超时后根本没有 citation 可检查。如果把两者都记为失败，会把网络不可用、检索空结果和语义错误混成一个分数，团队无法判断应该修基础设施、检索还是答案生成。

4. **[工程/深挖追问] fixed-RAG Router 会不会让产品 E2E 名不副实？**

   它仍然真实经过 API、Harness、RAG Tool 和 AnswerFlow，所以能验证产品 RAG 分支；但它绕过了自然 Router 决策，因此不能声称验证开放问法路由。M41 把 `route_policy_identity` 写入 runtime，并在报告中明确这一边界。若要评测 Router，应建立独立 decision set，而不是为了让英文 benchmark 通过就改写问题或悄悄放宽规则。

5. **[工程/深挖追问] 60 道真实 Eval 最有价值的发现是什么？**

   第一，自动 primary triage 显示 **20/60** 主要失败在 retrieval，是最大的单一故障层；第二，人工复核只有 **18 pass**，证明链路通过、gold recalled 或 citation valid 都不能替代答案语义；第三，5 个 Composer 合同错误被误标为 Harness failure，说明诊断系统本身也需要真实流量审计。这三点分别指向质量优化、评测口径和可观测性修正。

6. **[压力追问] 你花了很多精力做评测基础设施，最终人工只通过 18 道，这是不是工程自嗨？**

   这个质疑有合理部分：M41 没有把 RAG 质量优化到可用水平，也没有完成 external 的 smoke/core/basic/hard/full 运行档位。它解决的是更前置的问题——以前我们甚至不能可靠判断失败发生在哪一层，模型坏结构还可能被错记为 Harness 故障。现在 60 道题能给出一次执行证据、分层漏斗、人工 verdict 和不可变 artifact，已经明确 retrieval 是最大失败层，也防止团队拿 complete rate 自我安慰。下一步必须以这些失败簇设计可比较的改进，而不是继续堆评测框架；所以它是诊断基础，不是质量胜利，喵。

### 验证与下一步

**验证结果：**

- M41 修正后聚焦测试：**14 passed，1 warning**；
- M31–M41 受影响回归：**229 passed，1 warning**；
- 全仓 pytest：**462 passed，3 skipped，1 warning**；
- business RAG Smoke：**2 Scenario，23 required 全通过，人工 2/2 pass**；
- external 60 dev：**60/60 checkpoint 与 Trace 闭合，137,299 tokens，人工 18 pass / 26 fail / 16 insufficient evidence**。

warning 是既有 Starlette TestClient/httpx deprecation，不影响当前合同。本轮没有运行 120 held-out、LLM Judge、remote embedding/Milvus、LangFuse Cloud 或真实 Hybrid LLM。

**后续补充（2026-08-23）**：external canonical suite 与候选 compare 已实现；聚焦 `19 passed`、M31–M41 回归 `234 passed`、全仓 `467 passed / 3 skipped / 1 warning`。下一步不是继续搭评测框架，而是在用户单独授权后建立 v2/post-fix dev baseline；在此之前不运行 120 held-out，也不重跑或改签已完成的 pre-fix 60 题。

可复制验证命令：

```powershell
# 1. 聚焦合同测试：预计看到 M41 测试全部通过；不调用真实 LLM。
python -m pytest tests/test_m41_rag_e2e_contracts.py tests/test_m41_rag_e2e_runtime.py tests/test_m41_rag_review_history.py -q --basetemp=.agent_work/temp/pytest-m41-doc-check

# 2. 查看 business RAG Eval 参数：只显示帮助，不调用 provider。
python -m eval.run_rag_eval --help

# 3. 查看 external RAG Eval 参数：只显示帮助，不运行 60/120 题。
python -m eval.run_rag_external_eval --help

# 4. 校验既有 60 题人工复核来源：离线读取 artifact/checkpoint，不调用 Tool 或 LLM。
python -m eval.run_rag_review --bundle eval/reports/m41-rag-external-dev-20260822-01-reviewed.json --verify-only --output .agent_work/temp/m41-rag-external-review-verified.json
```

真实 business/external Qwen Eval 会产生费用，而且每次授权只允许一个精确 run；不要把上面的帮助或离线校验命令替换成真实运行命令后直接执行。

**本地启动体验：**

```powershell
# 前置：本地数据库和 seed 已准备好；默认 RAG 使用业务 release + deterministic Composer，不调用 Qwen。
python -m uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000/docs`，进入 `POST /api/query`，提交：

```json
{
  "question": "质量问题退款规则需要准备哪些材料？",
  "user_role": "customer_service"
}
```

正常情况下可以看到 RAG 路由、回答、引用和 Trace 身份。这个本地体验验证业务默认链路，不等于运行 external 180 题或真实 Qwen Eval。

## ★ M42 Phase 4B B0：先把 Agent 的考场、账本和边界建好

（2026-08-23）

**简述**：M42 没有提前实现 Agent Loop（智能体循环），而是先冻结 Phase 4B 的业务数据、场景合同、兼容边界、首次失败证据和未污染决策题集，让 M43–M48 能在同一套可审计前提上继续开发。

### 先用大白话讲

可以把 Phase 4B 想成要训练一名会持续办事的“分析专员”。如果一上来就教它查 SQL、找政策、追问和重试，却没有固定客户身份、业务账本、考试题和停止规则，最后很容易变成：**功能看起来越来越多，但每次演示都在换题、换数据、换标准**。

M42 先搭了这套“入职与考试基础设施”：

- **业务账本**：专门准备一份 7 月、8 月退款数据，能够用真实 SQL 对账；旧账本继续原样保留。
- **工作说明书**：冻结 T1–T5 等任务故事、旧/新 runtime（运行时家族）、最小 caller（可信调用者）和哪些恢复动作目前还不能执行。
- **第一张真实错题**：先写标准答案，再让现有检索器答一次。它确实漏掉了一份基础政策，没有为了“绿灯”临时改参数。
- **密封试卷**：另做 60 道后续决策题，放在项目外并封存；到 M46 前不能拿它调参，否则整套试卷作废。

所以 M42 的价值不是“Agent 已经会做更多事”，而是 **后续每一步终于有固定起跑线、真实失败样本和防作弊规则**。

### 这次做了什么

M42 处理的核心矛盾是：Phase 4 已有 SQL、RAG（检索增强生成）、Hybrid（SQL 与文档混合）和单次 Eval（评测）能力，但 Phase 4B 要做跨 turn（轮次）的 Agent 时，旧数据、旧请求和旧评测合同都不能直接冒充新能力。最终方案是 **新增独立 B0 family，同时保持 legacy（历史兼容运行时）只读兼容**。

1. **先冻结机器可读合同，防止后续模块各说各话。**

   `phase4b-b0-contracts-v1` 把北极星场景、非 happy-path（非理想路径）、caller、runtime family、Hybrid operator（混合算子）、action catalog（动作目录）和 capability matrix（能力矩阵）放进一份带内容身份的合同。

   - **原来的风险**：M35–M38 的请求预算和字段属于单轮 legacy runtime；如果 B1 直接在旧请求上加字段，代码可能靠“哪个字段为空”猜运行时，历史测试也可能被静默改义。
   - **解决方式**：loader（加载器）执行 closed-world（闭集）校验。缺字段、多字段、列表项不是 object（对象）、identity（身份）漂移或 Scenario 顺序变化都失败关闭。
   - **动作边界**：区分 global（全局登记）、applicable（本次场景适用）和 eligible（当前已准入执行）。M42 中除了 `stop`，恢复动作都只是 `unproven`，不能因为出现在目录里就自动执行。
   - **验证证据**：合同篡改、重复 turn、重复 assertion（断言）、执行缺失和 hash（摘要）篡改均有反例测试；Agent skeleton（骨架产物）仍明确标记 M43–M48 unavailable（不可用）。

2. **新增独立 seed profile，让 7→8 月退款故事有真实 SQL oracle。**

   seed profile（种子数据配置）可以理解成一张“可重复生成的业务账本配方”；oracle（判定标准）不是把期望数字抄回来，而是数据库建好后再用真实 SQL 算一遍。

   - **冻结事实**：7 月净退款 `120000.00`，8 月 `180000.00`；原因、渠道、商品三种分解都分别守恒，宽表与星型表总额一致，每月保留一条负数冲销。
   - **真实踩坑**：第一次查询得到 7 月 `139920`。原因不是新数据算错，而是 legacy 6 月末订单的 completed refund（已完成退款）按处理时间自然滑进 7 月，多出 `19920`。
   - **关键取舍**：没有只筛 `REF-P4B-*` 来让测试通过，因为产品 SQL 不会认识测试编号。最终只在显式 `phase4b` 隔离副本内，把 103 条 legacy 时间尾巴固定回 6 月末；默认 seed 和历史 artifact（产物）完全不变。
   - **身份保证**：profile identity 同时绑定 recipe（生成配方）、content（内容）和 config（配置）；拼错 profile 会在任何删除或写入前失败，避免先清库再报错。

3. **用最小双角色 caller 生成一张不能美化的真实错题。**

   退款变化分析需要 `ops` 的 SQL 权限，政策解释又需要 `customer_service` 的文档权限。M42 没有扩张成全角色或生产认证，而是建立最小 fixture（测试身份）：resolved roles（已解析角色）为两者，active SQL role（本轮 SQL 角色）仍只有 `ops`。

   - **gold-first（先冻结标准答案）**：先冻结应当取回 `refund_policy_basic` 和 `refund_policy_quality`，再按当前默认 budget（预算）执行一次 deterministic lexical retrieval（确定性词法检索）。
   - **实际结果**：只选中 quality，漏掉 basic，`all_gold_selected=false`；provider（模型服务）调用为 0。
   - **为什么不修**：M42 的任务是建立可信起点，不是优化检索。为了通过而改 query（查询问法）、预算、ACL（访问控制列表）、语料或 active release（当前知识发布），会污染 M45/B3 要诊断的失败。
   - **兼容边界**：新 `refund_change_and_policy` Hybrid operator 只冻结语义方向；M38 的 `refund_reason_and_policy` 继续原样运行，M42 不提前实现新 operator。

4. **建立独立 Agent Scenario artifact，但不冒充 Agent runtime。**

   M41 已证明“一次执行后再评分、失败不可观察时写 `not_observed`、review（复核）绑定来源 hash”是可靠纪律，但它只处理单题或 replicate（重复运行），不能表达多轮任务。

   - **如何沿用 M41**：保留一次执行、resolved runtime identity（实际运行身份）、安全投影和闭集验证思想。
   - **如何保持历史**：新建 `phase4b-agent-scenario-v1`，不修改 M41 artifact、签名、基线或 scorer（评分器）。
   - **安全投影**：skeleton 只保存 turn ID、执行状态、Evidence kind/ref（证据类型与安全引用）和三态断言，不保存答案正文、SQL rows（查询结果行）或模型 Thought（思维过程）。
   - **真实边界**：B0 的 `passed` 只证明合同输入已经冻结；Hybrid、Loop、持久状态等执行能力仍由 capability matrix 标成 unavailable。

5. **密封 60 题 decision reserve，给未来动作决策留一套未污染试卷。**

   decision reserve（决策保留集）不是日常回归题，而是未来判断“某个恢复动作是否真的带来净收益”的裁决试卷。试卷如果在开发时被看过或用于调参，就不能再当公正裁判。

   | 难度 | 题数 | 多文档题数 |
   |---|---:|---:|
   | basic | 20 | 0 |
   | core | 20 | 8 |
   | hard | 20 | 20 |

   - **来源隔离**：从 20 份未进入既有 180 gold 的冻结 external 文档编写，不复用 M34/M41 已消费题目或 gold 文档。
   - **双重审核**：一遍核对 source coordinate/hash（来源坐标与摘要），另一遍核对 gold answer 与 answer facts（标准答案与事实）一致性；两个 reviewer 身份必须不同。
   - **存储边界**：逐题正文、gold、source pool 和访问账本放在项目外 versioned immutable store（版本化不可变存储）；仓库只提交不含绝对路径的安全 manifest（清单）。
   - **污染状态机**：M46 才允许首次解封；提前访问 gold、查看 candidate result（候选结果）或用于调参都会变成 `retired`，不能继续作为 decision set。
   - **验证边界**：本模块只创建、双审、密封和 hash 对账，没有运行候选，因此没有产生新的 RAG 质量分数或正式基线。

### 新概念

- **Content identity（内容身份）**：对规范化内容计算 SHA-256 摘要。它回答“这份内容到底是不是原来那份”，而不是“文件还在不在原路径”。路径移动不应改变语义身份，正文、配方或配置变化必须改变身份。

- **Seed profile（种子数据配置）**：同一数据库 schema（结构）下的一套独立数据世界。它类似 Spring Boot 的 profile，但这里不只是切环境变量，还绑定了生成配方、业务事实和 oracle，防止不同数据世界的评测结果混算。

- **Closed-world contract（闭集合同）**：只接受预先声明的字段、枚举、顺序和执行集合。它类似 Java 枚举加数据库约束的组合：未知内容不会被“宽容解析”，而是在消费前明确拒绝。

- **Decision reserve（决策保留集）**：专门留到模型或动作方案需要最终裁决时才解封的题集。它和训练集、日常开发集的区别，类似考试前密封的期末卷与平时练习册。

- **Global / applicable / eligible action**：global 表示动作在系统目录中存在，applicable 表示与当前语料和失败有关，eligible 才表示已经通过证据门、允许本次执行。三者分开能防止“代码里写了这个动作”被误解成“Agent 可以随便调用”。

### 代码阅读路线

1. **先读总合同和内容身份**：`domain_pack/phase4b/b0_contracts.json`、`engine/phase4b/identity.py`、`engine/phase4b/contracts.py`
   先看 T1–T5 和 capability matrix 定义了什么，再看 `load_b0_contract_bundle()` 如何校验 manifest、字段闭集和顺序。重点理解 **identity 是所有后续消费者共同的防漂移锚点**，不用先背每个 assertion 名字。

2. **再读 Phase 4B 业务账本怎么构建**：`domain_pack/phase4b/seed_profile.json`、`engine/phase4b/seed_profile.py`、`scripts/seed_data.py`
   `resolve_seed_profile()` 先在写库前解析 closed-world alias；`build_refund_fact_rows()` 用累计区间交集让原因、渠道、商品三种边际同时守恒；`append_phase4b_rows()` 隔离 legacy 时间尾巴并追加 23 组事实；最后 `verify_phase4b_business_facts()` 用真实 SQL 生成 oracle。

3. **看最小 caller 如何跨 SQL 与文档权限**：`engine/phase4b/caller.py`、`engine/governance.py`
   `Phase4BFixtureCallerResolver` 只接受 active role `ops`，但返回 `ops + customer_service` 两个 resolved roles 和固定 tenant（租户）。这说明 **本轮激活哪个 SQL 角色** 与 **caller 拥有哪些可信文档角色** 是两件事。

4. **沿 Agent Eval skeleton 看闭集证据**：`eval/agent_scenario_contracts.py`
   先看 `build_b0_fixture_evidence()` 如何把 catalog 投影成 sequence/turn evidence，再看 `build_completed_artifact()` 和 `validate_completed_artifact()` 如何逐层核对 execution、turn、assertion 与 identity。JSON round-trip（JSON 往返转换）用于避免 Python tuple（元组）与落盘 array（数组）形状不同。

5. **最后看 reserve 如何构建和封存**：`scripts/build_m42_decision_reserve.py`、`eval/agent_reserve_contracts.py`
   构建脚本定义 source pool、60 题和两类 reviewer；`seal_reserve()` 再检查数量、难度、多文档比例、历史排除、source hash、gold hash、访问账本和逐文件摘要。`apply_access_event()` 则表达解封与污染后的状态迁移。

6. **用固化报告把所有输入串起来**：`scripts/rehearse_m42_b0.py`、`eval/reports/m42/`
   rehearsal（演练）在内存 SQLite 中建 Phase 4B profile、执行一次默认业务检索、生成 Agent skeleton 并只读对账外部 reserve。首次报告不可覆盖，所以阅读现有 JSON/Markdown 即可，不要把重复运行伪装成第一次 Observation。

核心数据流：

`B0 contract + Phase 4B seed profile`
→ `最小 caller + 一次默认 business retrieval`
→ `Business Observation`
→ `Agent Scenario skeleton`
→ `Capability matrix + sealed reserve manifest`
→ `M43/B1、M45/B3、M46/B4 分别消费`

### 设计要点

- **新旧 runtime 分家**：共享 canonical hash（规范摘要）实现，但不把 seed、Scenario、reserve 合成一个万能合同；legacy 与 agent family 分别过 Gate。
- **真实失败比漂亮绿灯重要**：先冻 gold 再运行，漏选就保存漏选，不改问题、参数和语料来美化 B0。
- **产品 SQL 与测试 SQL 同口径**：不靠 `REF-P4B-*` 测试编号过滤数据，只在显式 profile 内修复时间世界边界。
- **存在不等于可执行**：action catalog 登记动作，eligible set 才能授权执行；M42 只有 `stop` 已准入。
- **未污染证据比更多题更重要**：60 题放在项目外并带访问状态机，M46 前禁止 candidate；M34/M41 继续只作历史回归。
- **刻意不做能力冒领**：M42 没有 TaskState、Loop、RAG Subgraph、durable checkpoint 或 Context Compact，报告和 state 都明确把它们留给 M43–M48，汪。

### 有面试价值的亮点

1. **“我先解决评测可信度，再扩 Agent 能力。”** 我没有直接往旧 Harness 里堆循环，而是建立独立 runtime family、内容身份、Scenario 闭集和 capability matrix。这样后续每个模块都必须在同一数据、身份和验收边界上增量开发，旧回归也不会被新字段静默改义。

2. **“测试失败时，我没有改 oracle，而是找到了时间口径污染。”** Phase 4B 7 月多出 `19920`，根因是 legacy 退款按 `processed_at` 滑月。我拒绝用测试编号过滤来凑答案，改为只在新 profile 隔离副本内封住时间尾巴，并用真实 SQL 对账三种边际和宽表。这个案例能体现数据工程、业务口径和兼容性判断。

3. **“我把负结果固化成后续研发资产。”** gold-first 检索真实漏掉基础政策后，我没有调参重跑，而是把首次 Observation 签名、固化并禁止覆盖。后续 B3 可以围绕这张真实错题验证动作是否新增 Evidence，而不是重新挑一题讲故事。

4. **“我的保留集有污染退出机制。”** 60 题不只是藏在另一个文件夹，而是绑定 source/gold/file hash、双 reviewer、首次解封模块和访问状态机。提前看 gold 或拿 candidate 调参后，系统会把它标为 retired；这比口头说“我们没偷看测试集”更可审计。

### 面试官追问

1. **[基础追问] M42 没有实现 Agent Loop，那它对项目的实际贡献是什么？**

   它把 Phase 4B 的起跑线变成了可执行合同：固定业务数据与 SQL oracle、可信 caller、任务 Scenario、旧/新 runtime 边界、首次真实失败和未污染 reserve。没有这些前置，后续 Loop 即使能跑，也无法证明是同一问题、同一预算和同一身份下的能力提升。

2. **[工程/深挖追问] 为什么 profile 里要 retime 103 条 legacy 退款，而不是直接让查询只统计新数据？**

   指标合同是 completed refund 按 `processed_at` 聚合，产品查询并不知道哪些行是“测试新增”。如果按 `REF-P4B-*` 过滤，测试通过但真实 Agent 生成的 SQL 会得到另一个结果。新 profile 本来就是隔离的数据世界，所以在这个副本内封住 legacy 时间尾巴，既保持产品 SQL 口径，也不改变 legacy 默认和历史 artifact。

3. **[工程/深挖追问] 60 题 reserve 怎么证明没有被污染？**

   我能证明的是工程过程，而不是绝对心理状态：source pool 排除既有 180 gold 文档，题目 ID 和文档 ID 做闭集排除；逐题 gold 经过两个不同 reviewer 的 source/gold hash 审核；项目外文件有逐文件摘要；access ledger（访问账本）只允许 M42 created→sealed，M46 前若发生 gold 或 candidate 访问就转 retired。这使污染有可检查的状态和后果。

4. **[压力追问] 你做了很多合同和哈希，但业务检索还是漏了一份政策，这是不是说明模块没有带来能力提升？**

   这个质疑是成立一半的：M42 确实没有提升检索质量，也没有宣称提升。它解决的是此前无法公正判断“哪个恢复动作真的有效”的问题，并交付了一张不可覆盖的真实错题、固定预算、动作准入边界和未污染裁决集。全仓 487 个测试证明兼容与合同闭合，但不能证明 RAG 更聪明；质量提升必须由后续模块在这些固定证据上做可比验证，而不是由 M42 抢跑宣称，喵。

### 验证与下一步

**验证结果：**

| 范围 | 真实结果 | 说明 |
|---|---:|---|
| 首轮 M42 聚焦 | 19 passed | 覆盖 profile、caller、Scenario、reserve 和固化 artifact；后续新增畸形输入反例由合同子集和全仓覆盖 |
| 注释修正合同子集 | 12 passed | 覆盖畸形 catalog 和 closed-world 篡改 |
| M1/M27/M31–M34 | 179 passed，1 warning | 验证 legacy seed 与 RAG/Evidence 兼容 |
| M35–M41 | 82 passed，1 warning | 验证 Harness、Hybrid、assurance 和 M41 Eval 兼容 |
| 全仓 pytest | 487 passed，3 skipped，1 warning | 用沙箱外同命令避开 Windows basetemp 权限故障 |

warning（警告）是既有 Starlette TestClient/httpx deprecation；3 个 skip（跳过）是既有 Milvus 专项环境跳过。`compileall`（字节码编译检查）、`git diff --check`、关键路径和外部 manifest 检查也都通过。本模块没有运行真实 LLM、remote embedding（远程向量嵌入）/Milvus、120 held-out（保留集）或 reserve candidate。

**下一步**：按 Phase 4B roadmap 为 M43/B1 单独制定 module plan，从 `phase4b-b0-contracts-v1`、TaskState family 和 turn boundary 开始。M45/B3 才消费首次漏选 Observation；M46/B4 才允许按污染门解封 reserve。

可复制验证命令：

```powershell
# 前置：在仓库根目录，已激活项目 Python 环境；以下命令不调用真实 LLM，也不解封 reserve。

# 1. 检查 B0 合同、Scenario skeleton 和 reserve 状态机；预计全部通过。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m42-devlog-contracts tests/test_m42_phase4b_contracts.py tests/test_m42_agent_scenario_contracts.py tests/test_m42_agent_reserve_contracts.py

# 2. 检查显式 Phase 4B profile 与 legacy 默认隔离；只使用内存 SQLite，不重置本机 MySQL。
python -m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m42-devlog-seed tests/test_m42_phase4b_seed_profile.py

# 3. 阅读已经固化的首次报告；不要重跑 rehearsal 覆盖 Observation。
Get-Content eval/reports/m42/m42-b0-deterministic-report.md
Get-Content eval/reports/m42/m42-capability-matrix.md
```

环境未激活时，把 `python` 替换成 `AGENTS.md` 中项目学习环境的完整 Python 路径。

**本地启动体验：** M42 暂无独立 API 或页面，因为它只交付 B0 数据/合同/Eval 前置，不把 M43 的 Agent runtime 提前塞进 `/api/query`。当前最合适的体验方式是运行上面的确定性测试，并阅读首次 deterministic report（确定性演练报告）和 capability matrix；它们会展示 7/8 月 oracle、最小 caller、真实漏选、Agent skeleton 与 M43–M48 未开放边界。

