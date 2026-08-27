# Phase 4B（B0～B6 / M42～M48）整体审计报告

> 审计日期：2026-08-27  
> 范围：调查、代码/合同/报告审计、只读环境检查、一次经授权的真实连续 Probe 与一次安全失败 Probe；未修改业务代码、默认配置、数据库 schema、active release、Milvus、historical/held-out/reserve。  
> 真实运行分类：`exploratory / baseline-ineligible / not-development-probe`。模块已经收工，因此本次不能倒填为开发期 Live Dev Probe，也不登记质量基线。

## 1. 当前整体完成度和明确结论

**结论：Phase 4B 的主要技术组件已经存在，但当前不能通过最终验收，也不能证明已经形成一条真实、连续、可演示的 T1→T5 Agent 链。**

大白话：零件基本造出来了，很多安全开关也确实有效；但把真实模型、真实 SQL、真实任务状态接起来后，第二轮自然表达就断了，所以现在还不能说“整车能连续开完”。

| 里程碑 | 当前判定 | 已证明 | 仍未闭合 | 大白话 |
|---|---|---|---|---|
| B0 / M42 | 技术完成 | 独立 seed/oracle、最小 caller、Agent Scenario skeleton、sealed reserve 与污染账本存在；7/8 月 SQL oracle 为 `120000/180000` | reserve 只负责后续裁决，未运行不是 B0 缺口 | 起跑线和考试规则准备好了 |
| B1 / M43 | 合同存在，但自然多轮完成门未真正闭合 | TaskDelta/TaskState、失效、switch/cancel、task envelope、Context typed projection 可运行 | Turn Understanding 仍是退款/月/关键词窄规则；真实自然改写在本次 T2 被归为 `continue`，旧新 requirement 同时保留 | 只会几种固定说法，换一种正常说法就可能理解错 |
| B2 / M44 | 控制结构完成，真实纵向效果未闭合 | closed-world Action、父预算、no-progress/repair/termination、API/Trace 投影存在；历史真实 T1→T2 曾在特定措辞下通过 | 本次真实链 T2 失败；T3～T5 没有同一真实 sequence 的成功证据 | 循环和刹车都装了，但真实路线还没连续跑通 |
| B3 / M45 | 窄范围 diagnostic 完成 | 失败漏斗、rewrite/expansion action card、ACL/duplicate/no-progress 边界有真实 diagnostic 证据 | Evidence gain 不等于答案正确；部分动作依赖受控/冻结结构，不是开放问题泛化 | 知道几种故障该怎么补证据，但不代表随便一道题都能修好 |
| B4 / M46 | experimental 工程能力存在；与现行 roadmap 完成门冲突 | Pipeline/Subgraph seam、父子预算、child ledger、business P1 与 60×2 historical 都可复核 | real P2=`failed/revise`、P3 未执行；最终 historical 为 Subgraph `60/60 no_answer`；reserve sealed/not-run。M46 plan 后来允许 experimental-only 收口，但 roadmap §15.2 仍要求 reserve A/B | 子图能运行，但这版效果明确没赢；而总路线和模块特批规则没有统一 |
| B5 / M47 | 隔离环境控制能力完成；默认开发环境不可直接演示 | MySQL CAS、restart、多 worker 单胜者、TTL/clear/scrub/purge、claimed crash 停止有真实 MySQL 证据 | `datapilot_dev` 当前仍在 Alembic `0003`，产品 task runtime 要求 `0005`；maintenance 没有常驻 scheduler | 仓库里有耐久能力，但默认开发库还没装上对应表结构 |
| B6 / M48 | Compact/runtime 能力存在；阶段 assurance 不能承担完成证明 | Context codec、原子提交、source/identity 失败关闭、跨进程恢复与 local business Subgraph 在隔离 Probe 中通过 | M48 P2 的 SQL 是 `Phase4BOracleSQL` 假 Tool；budget trigger/fallback 被报告硬编码为 passed；本次真实链未到 Compact | 压缩机制本身能工作，但“真实全链已完成”的证书写得比证据更满 |

### 阶段级判断

- **可以成立的表述**：B0～B6 的主要接口、状态机、预算、Subgraph、durable boundary 和 Compact 已实现，具备大量 deterministic 控制/安全回归。
- **不能成立的表述**：Phase 4B 已最终验收；真实 T1→T5 连续链已经闭合；Scenario v6/assurance 独立证明了十类真实场景；Subgraph 质量提升或生产就绪。
- **最终验收状态**：`blocked`，首要阻塞是本次真实 T2 失败，其次是 assurance 证据生成缺陷、roadmap/M46 完成门冲突、默认开发库未迁移和公开文档不一致。

大白话：现在适合说“技术骨架基本建成，真实联调发现关键断点”，不适合说“Phase 4B 已完整交付”。

## 2. 已经完整串起来的能力链

### 2.1 已有可信闭环

1. **真实单轮 SQL 链已通过。**
   - 本次 T1 真实经过 `/api/query → caller/task → TaskState → Decision Loop → Text2SQL → Qwen → SQL Guard → MySQL → Evidence → Response/Trace`。
   - 结果：HTTP 200、`answer_ready`、`net_refund_amount=120000`、task version=`1`、2 provider calls / 5,641 tokens。
   - 大白话：第一问确实不是假数据适配器，模型真的规划并查询了 MySQL。

2. **持久状态控制链在隔离 MySQL 中有真实证据。**
   - M47/M48 Probe 证明 checkpoint/event、CAS/fencing、跨进程 resume、单 worker winner、TTL/clear/scrub/purge 和 context content binding。
   - 大白话：任务状态“存得住、抢不重、过期能清”这部分不是只靠单测想象。

3. **business Subgraph 的控制链可运行。**
   - M46 business P1 与 M48 deterministic P2 证明一次父级 Knowledge action 内可以 initial retrieval→Observation→rewrite→merge/re-authorize→stop，并回写父子预算。
   - 大白话：政策漏一篇时，子图确实能按规则补一次，不会无限搜。

4. **安全失败关闭的核心行为有效。**
   - 本次 `APP_ENV=production` 且无 authenticated resolver 时，task 请求返回 `blocked/not_started`，runtime invocation=`0`、provider calls/tokens=`0/0`、未创建 task。
   - 大白话：没有可信登录身份时，系统没有先查库再拒绝，而是在工具前停住。

5. **旧合同兼容有大量回归证据。**
   - M48 最终全仓记录为 `662 passed, 1 warning`；M31～M41 legacy 与 M42～M48 additive family 均有回归。
   - 大白话：新功能没有明显把旧 SQL/RAG/Hybrid 接口整体改坏，但测试通过不代表真实自然语言效果通过。

### 2.2 尚未串成的连续链

当前真实证据只串到：

`T1 成功 → T2 TaskDelta/requirement 冲突并停止`

因此以下能力没有在本次同一真实 sequence 中被观察：T3 原因→商品双 SQL action、T4 SQL+business Subgraph、T5 correction、五轮后 Compact、跨进程 T6 resume、真实 Response/Trace/Eval 全链对账。

大白话：这些模块分别有测试或旧 Probe，但还没有在同一趟真实旅程里全部出现。

## 3. Dev Probe 的真实结果、首个失败层和证据边界

### 3.1 场景与边界

- 场景 P1：同一 task 的 T1→T5，并计划由新进程执行 T6 触发 Compact；真实 Qwen、真实 Text2SQL、SQL Guard、`datapilot_m48_test`、business active release、临时 server-controlled Subgraph。
- 场景 S1：production-like 环境无 resolver 的 task 请求，要求 Tool 前停止。
- 上限：14 provider attempts / 60,000 observed tokens，retry=0；首次系统性失败停止，不换措辞、模型、backend 或 run ID。
- 数据：隔离库已处于 `20260827_0005`，运行前 task/event=`0/0`；不 reset/reseed，未访问 `datapilot_dev`、Milvus、external、historical、held-out 或 reserve。
- 清理：运行前后 task/event=`0/0 → 1/3 → 0/0`。

证据：

- 安全汇总：`.agent_work/temp/m48/phase4b-review-20260827/result-safe.json`
- T1/T2 Response 与 JSONL Trace：`.agent_work/temp/m48/phase4b-review-20260827/`
- 后台运行日志/退出码：`.agent_work/temp/m48/phase4b-review-20260827-run/`

### 3.2 连续 Probe 结果

| Turn | 结果 | Provider usage | 关键事实 |
|---|---|---:|---|
| T1 | passed | 2 calls / 5,641 tokens | version 1；SQL Evidence；`120000`；`answer_ready` |
| T2 | failed | 2 calls / 10,002 tokens | version 3；`comparison_requirement_ambiguous`；无答案 |
| T3～T6 | not exercised / inconclusive | 0 | 按首个系统性失败停止 |
| 累计 | failed | 4 calls / 15,643 tokens | 未越授权额度；未重跑 |

### 3.3 首个失败层与根因

**最早可确定失败层：Turn Understanding → TaskDelta/TaskState merge。**

- 输入是自然说法：“比较 2026 年 7 月和 8 月实际净退款金额，并计算差额和变化率。”
- `understand_turn()` 将其分类为 `continue`，而不是替换比较条件的 `modify_constraint`。
- `apply_delta()` 对 `continue` 采用追加 requirement 语义，最终同时保留：
  - `sql:net_refund_amount:2026-07`
  - `sql:net_refund_amount:2026-07,2026-08`
- comparison completion 发现两个 `metric_comparison` requirement，稳定停止为 `comparison_requirement_ambiguous`。
- 离线复现无需 provider 即可得到同样的 category 和两个 requirements，证明不是模型抖动造成的唯一问题。

大白话：用户把完整需求重新说清楚了，系统却理解成“在旧任务后面再加一条”，结果自己制造出两个互相抢主导权的比较任务。

**同一轮更深层还观察到：`sql_plan_contract_indeterminate`。**

- 实际 SQL action 调用了 Qwen 2 次、10,002 tokens，但 QueryPlan/SQL 没有形成可接受 Evidence。
- 最终公开 reason 被更早的 requirement ambiguity 收敛覆盖；两者都是真实问题，但应先修确定性的 TaskDelta/merge，再用同一最小 T2 重验判断 provider plan 是否仍失败。

大白话：即使先不看状态冲突，这轮模型生成的查询计划也没通过合同；只是当前最先该修的是百分之百可复现的状态合并错误。

### 3.4 安全失败结果

- 实际行为：`blocked`、`not_started`、runtime invocation=`0`、provider=`0/0`、task 未创建。
- 安全目标本身通过：未认证请求没有进入 Tool。
- 文档/错误码不一致：runbook 写“`caller_untrusted` 失败关闭”，task family 的公开 Response/Trace 实际统一为 `task_unavailable`。

大白话：门确实锁住了，但说明书写的报警代码和实际显示不一样。

### 3.5 证据边界

- 本次只有一个真实 sequence，不能外推自然语言泛化率、Reliability、吞吐或生产稳定性。
- T3～T6 未执行，必须记 `inconclusive/not_exercised`，不能被 T1 成功覆盖。
- business RAG 是 22-entry local release；未验证 Enterprise Milvus、external corpus 或大规模答案质量。
- provider usage 是实际观测值；没有估算缺失 token。
- 本次没有运行 Formal Eval，也没有读取 sealed reserve。

## 4. 最终验收前必须修复的问题

| 优先级 | 问题、依据与根因 | 影响 | 建议 | 大白话 |
|---|---|---|---|---|
| P0 | **自然 T2 产生双 comparison requirement。** 本次真实 Probe 和离线 `understand_turn/apply_delta` 均复现 | 北极星在第二轮即断；B1/B2/B6 连续演示无法通过 | 明确“完整显式重述/比较”是 replace 还是 merge；修正 category/merge 合同，增加非“改成”措辞的 paraphrase fixtures；只对本次 T2 做一次授权后最小重验 | 先让系统听懂正常人说话 |
| P0 | **Scenario v6/assurance 不是独立 required Gate。** `build_from_probe()` 对 `COMPACT_BUDGET_TRIGGER`、`COMPACT_FALLBACK` 等直接写固定 passed；每个 assertion 统一生成 passed；B0～B5 的 `evidence_identity` 直接等于 contract identity。用无 Trace、无 DB 执行的测试字典也能生成 `completed/technical_integration=completed` | 报告可以在能力未执行时仍全绿，无法支撑阶段完成声明 | artifact schema 增加 observed/not_observed/failed、source artifact identity 和闭集 assertion plan；每个 case 必须绑定实际 execution evidence；未观察分支必须使 Gate inconclusive | 现在这张“毕业证”主要证明格式正确，不证明考试真做过 |
| P0 | **没有真实 T1→T5+restart/Compact 成功证据。** 旧 M48 P2 的 SQL 是 `Phase4BOracleSQL`，本次真实链止于 T2 | roadmap §15.2(2)、B6 完成门和人工演示门未满足 | 修复 P0 后按同一数据边界重跑最小受影响 sequence；在通过前把阶段状态降为“technical components available / final integration unverified” | 必须真的从头跑到尾一次 |
| P0 | **roadmap 与 M46 特批完成门冲突。** roadmap 仍要求新 sealed reserve A/B；M46 plan 后改为 historical no-go + reserve sealed 即可 experimental-only 收口 | B4/Phase 4B 到底“完成”还是“例外完成”没有唯一合同 | 要么正式修订 roadmap/DoD 并记录用户批准的范围变化，要么按现行 roadmap 把 B4 标为未完成；不能让 module plan 静默覆盖阶段总合同 | 总规则和临时特批必须统一版本 |
| P0 | **默认 `datapilot_dev` 仅为 Alembic `0003`，task backend 默认却是 MySQL/0005。** 已只读实测 | 按默认 `.env` 启动无法直接演示 Phase 4B task family | 最终验收前选择并执行：迁移开发库到 0005，或提供明确、可重复的隔离 demo DB 启动入口；迁移仍需用户单独授权 | 功能在仓库里，但默认开发环境还没接上线 |
| P1 | **公开文档状态互相冲突。** `AI_CONTEXT` 写“M48/B6 已验收通过”，M48 notes/dev-log 又写等待人工演示与 `accept-module` | 后续 AI/用户会误判流程已完成 | 统一为真实状态；完成本次修复与人工门前不得写“已验收通过” | 仪表盘和施工记录说法相反 |
| P1 | **README 严重过期。** 仍写当前 M46、626 tests、conversation state 单进程、Milvus 非默认、后续 persistent state | 对外项目说明错误，掩盖 B5/B6 和当前默认/边界 | 阶段最终验收前统一更新 current status、测试快照、durable task 与 legacy thread 分账、Enterprise semantic 默认和本次真实失败边界 | README 还停在两个模块以前 |
| P1 | **演示/隐私文案与 Trace 合同不一致。** `m48-continuous-rehearsal.md` 要求 Trace 无 rows，但 runbook 明确 SQL 单路允许 guarded rows，现有 M48 P2 Trace 也确有 rows；Trace 还保存当前 question/user_role | 人工检查会把合法兼容字段误判为泄漏，或反过来漏查真正禁区 | 把“当前 turn question/guarded SQL rows”和“历史 recent turns/正文/Prompt/private payload”分开列清楚；按真实 contract 修改 checklist | 不是所有原文都禁存，必须说清楚禁的是哪一类 |
| P1 | **安全 reason 文档漂移。** production-like task 实际公开 `task_unavailable`，runbook 写 `caller_untrusted` | 自动化运维和演示断言不稳定 | 保留通用公开错误可减少枚举风险；建议修改 runbook，区分内部 cause 与公开 projection，并增加回归 | 门锁得对，但报警牌要统一 |

## 5. 不阻塞验收、但必须明确保留的能力边界

1. **Subgraph 仍是 experimental，Pipeline 继续默认。**
   - M46 historical v3 中 Subgraph 仍 `60/60 no_answer`，没有质量胜出证据。
   - 大白话：有实验功能，不等于应该给普通用户默认打开。

2. **sealed reserve 仍为 sealed/read0/not-run。**
   - 本次没有触碰它；不能用本次结果作默认策略裁决。
   - 大白话：期末卷还没拆封，不能假装已经考过。

3. **生产认证不在 Phase 4B。**
   - local/demo/test 仍是 fixture resolver；production-like 无 resolver 会安全停止。
   - 大白话：权限框架有门，但还没接企业真实门禁卡。

4. **durable task 不等于外部 Tool exactly-once。**
   - claimed crash 选择保守停止、不自动重放；这是安全边界，不是缺陷伪装。
   - 大白话：系统宁可让人确认，也不会冒险重复扣费或重复执行外部动作。

5. **Compact 不是长期记忆，也不是 Evidence authority。**
   - 只保留 typed facts、最近 2 个 raw turns 和来源 identity；使用 Evidence 前仍需重授权。
   - 大白话：压缩包只是目录，不是原始凭证。

6. **deterministic Gate、真实 provider showcase 和质量 Eval 必须分账。**
   - pytest/Scenario 能证明合同与安全；单次 Qwen Probe 只能证明该次链路；RAG/LLM 质量、Reliability 和生产能力仍需独立分母。
   - 大白话：单元测试、试驾和正式路测不是同一种证据。

7. **legacy thread 与 Phase 4B durable task 是两个 runtime family。**
   - M37 thread 仍为进程内；只有 strict nested task envelope 走 MySQL durable task。
   - 大白话：旧对话续接没自动升级，只有新 task 模式具备跨进程状态。

## 6. 现有测试、Scenario、assurance 与报告分别证明什么

| 证据 | 可以证明 | 不能外推 |
|---|---|---|
| M42～M48 pytest / 662 全仓回归 | 代码合同、篡改拒绝、兼容性和大量确定性边界 | 真实自然语言成功率、provider 稳定性、业务答案质量 |
| Agent Scenario v1～v5 | 各模块 additive schema、closed-world shape 和对应 deterministic fixture | 一条真实连续 execution 已发生 |
| M47 P1/P2 | MySQL durable boundary、CAS/restart/清理；P2 使用 frozen SQL oracle | 真实 Text2SQL、真实答案正确率 |
| M48 P1 | Context 与 state/event 原子提交、scrub、migration 对称 | 连续 Agent 效果 |
| M48 P2 | real MySQL boundary、local business Subgraph、Compact/restart/负例；SQL 为 fake oracle | 真实 Qwen/QueryPlan/SQL 链、开放问法、quality |
| Scenario v6 / assurance | 当前实现只可靠证明 artifact 形状、hash 与 claim 边界字符串未被篡改 | B0～B6 required capabilities 全部真实 observed |
| M46 historical 60×2 | 当前 Subgraph candidate 的真实失败结构、成本下限和 no-go | 未污染默认裁决、未来 candidate 上限、生产质量 |
| 本次真实 Probe | T1 真实链成功、T2 首个真实断点、安全 pre-Tool stop、清理闭合 | T3～T6、Reliability、生产与大规模质量 |

## 7. 最终建议

最终验收前按以下最短顺序处理：

1. 修复 T2 的 TaskDelta/requirement replace-vs-merge 合同，并增加正常改写的 deterministic 回归。
2. 修复 Scenario v6/assurance，使 `not_observed` 不能被硬编码 passed 覆盖。
3. 统一 roadmap 与 M46 experimental-only 完成门，明确 B4 的唯一验收定义。
4. 取得单独授权后只重验本次受影响的真实连续 sequence；通过后再执行人工 checklist。
5. 迁移或明确配置可重复的 0005 demo DB。
6. 更新 README、AI_CONTEXT、dev-log/continuous rehearsal 的状态与证据边界，再运行 `accept-module`。

在上述事项完成前，推荐项目状态写作：

> **Phase 4B technical components implemented; final continuous real-chain acceptance is blocked by a reproducible T2 task-merge defect and evidence-assurance gaps.**

大白话：Phase 4B 不是推倒重来，而是已经进入“最后联调发现真问题”的阶段；先把真实断点和证书可信度修好，再验收最稳妥。
