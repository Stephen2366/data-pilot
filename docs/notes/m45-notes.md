# M45 Phase 4B B3 开发记录

> 模块计划：`docs/notes/m45-plan.md`
>
> 开工基线 HEAD：`7d254ff4b5c5e2a0a8c5fc83f4bfdb8a74d79ec9`
>
> 开工日期：2026-08-25

## Implementation checklist

### M45-A：campaign、失败漏斗与 artifact 骨架

- [x] 核对四个 `diagnostic/dev` Scenario、两张 B0 candidate card、runtime/corpus identity 与 reserve sealed 边界。
- [x] 实现六层三态 failure funnel 与唯一首失败层，保持上游缺失向下游传播 `not_observed`。
- [x] 实现 closed-world diagnostic execution/campaign artifact、identity/hash/budget validator 与仓库安全投影。
- [x] 只读导入 M42/M39/M41/M44A historical initial Evidence identity；禁止为评分重跑旧 pipeline。
- [x] 覆盖缺失/额外/重复 action、identity/hash/budget 篡改，以及 reserve/held-out selector 拒绝测试。

### M45-B：deterministic query rewrite action

- [x] 从 retrieval 前已签名 typed requirement slots 与 initial unsupported-slot Observation 生成至多两个 focused subquestions。
- [x] 复用现有 Knowledge Tool/runtime/ACL/Evidence seam，合并至多 5 candidates、3 selected Evidence；不接产品 Loop。
- [x] 覆盖 trigger、错误 action 排除、gold/title 注入拒绝、ACL/runtime unavailable、duplicate/no-progress 与子预算测试。
- [x] 完成第一条真实纵向链路后执行 `M45-P1`；结果 `passed/continue`，放行 M45-C。

### M45-C：external context expansion action

- [x] 先实现并如实保留已失败的 immediate-neighbor v1；再按 G45-4 实现同物理文档 bounded sibling v2（每 seed 最多扫描 8 个 identity、最多新增 4 条 Evidence）。
- [x] 每个新 unit 回到 SQLite authority 重水化并重新授权，拒绝跨 physical document、identity 漂移、ACL deny 与重复 unit。
- [x] 完成 external rewrite seam 后执行 `M45-P2`；Round 2 为 `failed/revise`，随后按用户确认的 G45-3/G45-4 经 P2C/P2D 闭合 continuation sibling v2。
- [x] 执行 `M45-P3` 两个 Scenario；两题均 `failed/stop`，按 plan 进入 M45-D no-go review。

### M45-D：qualification 与 M46 handoff

- [x] 汇总两张 action card 的 trigger、gain、cost、ACL、duplicate/no-progress、stop 与 actual EvidenceDelta。
- [x] 生成 machine-readable qualification、仓库安全报告/失败切片、external immutable artifact 与 SHA-256 manifest。
- [x] 验证只有两卡全绿且同 external runtime 由 Observation 选择不同 action 时才输出 `go_for_M46`；本次 direct expansion card 未完成，稳定输出 `review_required/no_go`。
- [x] 运行 deterministic rehearsal、聚焦测试与受影响兼容回归；因 C5 no-go 不进入模块完成门，未启动耗时全仓 pytest。
- [x] `finish-module`：M45-H/P5/v4 已将 C5 更新为 `go_for_M46`，按最终 plan 完成技术收工。

### M45-E/F：structured proposal 重开切片

- [x] 新增 question + authorized Evidence 的 closed-world proposal schema、prompt 和确定性 validator；模型 coverage 结论不作安全事实。
- [x] 新增 diagnostic-only Qwen outbound policy/client adapter；普通 API/default policy 不变。
- [x] 从 P3 immutable artifact 重水化两题 initial Evidence，覆盖 lineage/hash/ACL、字段/数量/答案值/gold/reserve 拒绝、provider unavailable、invalid JSON、budget 与 safe projection 测试。
- [x] 完成第一条 fake transport 纵向链路后预登记并执行 `M45-P4`；真实发送前另做精确 payload/额度授权检查。
- [x] P4 两题未全绿，v2 qualification 稳定输出 no-go；未解除 finish/M46 阻塞。

### M45-G：P4 最小 repair

- [x] 新建 additive v3 campaign/P4R，保留 v1/v2 campaign、P4 和两个 no-go review。
- [x] 仅为 proposal slot 增加 bounded token-overlap，旧 exact slot/signature 不变；prompt 明示 marker 数量，validation failure 私有保留 raw/prompt。
- [x] 用 P4 qst_0461 immutable response 离线重放；通过后才放行 qst_0431 唯一 1 次 Qwen。
- [x] P4R/v3 qualification 未全绿，已固化第三次 no-go 并停止；不再扩规则/调用，也不进入 finish。

### M45-H：procedure boundary continuation

- [x] 新建 additive v4 campaign/P5，保留 v1～v3 campaign、三份 no-go review 与累计 11 次 provider attempt。
- [x] 实现默认关闭的 procedure-shaped intent + forward same-document unit 结构 trigger；旧 coverage/signature/default 行为不变。
- [x] 覆盖无 procedure intent、末 unit、反向/跨文档、ACL deny、duplicate/no-progress、预算和安全投影测试。
- [x] 用 P3 qst_0431 immutable Evidence 执行一次零 provider P5；通过并生成 `go_for_M46` v4 qualification。

## 已冻结决策与边界

- G45-1：用户确认方案 A。M45 只使用 deterministic requirement split/focused rewrite；模型 rewrite 是 AI_CONTEXT 中带硬重开门的未来候选，不是本模块备用方案。
- G45-2：用户确认方案 A。长期完整 artifact 使用与 sealed reserve 物理分离的 external diagnostic store；仓库只保存安全投影、identity、SHA-256 与汇总。
- 拟用长期路径：`D:\.Work\Practice\AI-Project\data-pilot-datasets\phase4b-rag-action-diagnostics\v1.0.0`。首次写入前必须核对该路径不位于 `phase4b-agent-eval/v1.0.0` reserve store，并取得 workspace 外写入授权。
- 不改产品 B2 Loop/budget、API、TaskState、active release、Enterprise semantic 默认、embedding、Composer 或 corpus/index recipe；不实现 M46 Subgraph。
- 不读取或运行 Phase 4B 60 题 decision reserve、M34 held-out/all；全部 Probe 为 `exploratory / baseline-ineligible`。

## Live Dev Probe 预登记

| Probe | 计划时点与阻塞门 | Scenario | 预算与禁区 | 初始状态 |
|---|---|---|---|---|
| `M45-P1` | after M45-B / before M45-C；只在 `continue` 后实现 expansion | business T4 canonical 问题 | initial retrieval 1 + rewrite action 1；零模型/Composer；只读 | `passed/continue` |
| `M45-P2` | after M45-C rewrite/loader seam / before P3 | `diagnostic_dev/qst_0420` | initial semantic retrieval 1 + rewrite action 1；rewrite 内至多 2 child retrieval；不切 lexical | Round 1 invalid；唯一修复重验 `failed/revise` |
| `M45-P2C/P2D` | G45-3/G45-4 后、before P3 | 续接 P2 Round 2 immutable qst_0420 Evidence | immediate neighbor v1 与 sibling v2 均零 provider；不覆盖旧失败 | P2C `failed/stop`；P2D `passed/continue` |
| `M45-P3` | after P2D continue / before M45-D | `diagnostic_dev/qst_0431`、`qst_0461` 各一次 | 每题 initial semantic retrieval 1；recovery 零额外 embedding/Composer | 两题均 `failed/stop` |

- 模块最终 campaign 边界：4 Scenario；G45-3/G45-4 与 P3 明确授权后硬上限修订为 embedding provider attempts ≤8，实际 8；chat/model/Composer calls=0、observed chat tokens=0。standing/追加授权来源与时点见 plan 和下方记录。
- Probe 执行后立即追加：时间、代码阶段、HEAD/模块 dirty、命令/依赖、Response/Trace/artifact identity、calls/tokens、总体及子能力三态、首失败层/根因、`continue/revise/stop`。
- 未经用户另行批准，不增加 Scenario、不触碰 reserve/held-out、不重跑质量失败、不改变 backend/参数或 active identity。

## 参考复核记录

- 已按 plan 与 `docs/phase4-reference.md` 定点复核 ARAG 的 child search/parent retrieval、条件边/去重/停止，以及 DB-GPT 的 structured references 与 retrieval/answer evaluator 分层。
- 借鉴：首次检索与恢复动作分权；恢复动作消费已授权 seed identity；同一次 execution 固化实际 context/次数后离线评分。
- 适配：DataPilot 使用 typed Observation、EvidenceRef/EvidenceDelta、ACL 双检、SQLite authority、closed-world budget 和 sealed reserve。
- 不照搬：字符串 Tool Observation、开放 LLM rewrite、顺序 parent ID、默认 parent expansion、正文/异常直接投影、为评分重跑 pipeline。

## 开发时间线

- 2026-08-25：读取 `codebase-design` 与 `finish-module` 技能、AGENTS、M45 plan、AI_CONTEXT、runbook/RAG 专项 state 和 Phase 4 reference；建立开工 checklist。模块外部 interface 计划保持为单一 diagnostic campaign/executor seam，复杂 funnel、action eligibility、budget、authorization 与 artifact validation 留在深模块内部；生产 runtime 仅作为注入 adapter，不新增产品接线。
- 2026-08-25（M45-A/B）：实现通用 expansion Protocol 时一度同时写出 concrete Enterprise adapter 草稿；复核 plan 后确认 P1 必须真实阻塞 M45-C，因此在测试/运行前立即删除 concrete adapter 与 neighbor loader 改动，只保留 B 阶段的 interface。没有执行 expansion、没有外部调用、没有形成可被误认作 P1 后能力的验证证据；P1 `continue` 前不再推进 M45-C。
- 2026-08-25（M45-A/B → P1 checkpoint）：campaign/manifest、六层三态 funnel、closed-world artifact/qualification、deterministic rewrite executor 与安全 Probe runner 已落盘。聚焦测试首次因测试 import 名称错误在 collection 阶段失败（0 个测试执行）；修正为既有 `test_caller` alias 后出现 3 个确定性失败：一处历史 hash 抄写转置、测试 child Evidence run_id 不一致。修复具体合同/fixture 后第三次为 `5 passed in 0.45s`。当前 HEAD 仍为 `7d254ff4b5c5e2a0a8c5fc83f4bfdb8a74d79ec9`；模块 dirty 为新增 `m45-notes`、B3 campaign 两文件、`rag_diagnostics.py`、`rag_action_diagnostics.py`、Probe runner 和 M45 测试，生产既有文件无行为改动。下一步按 plan 执行首次且仅一次 `M45-P1`，它阻塞 M45-C。

### 2026-08-25：M45-P1（after M45-B / before M45-C）

- 执行时间：`2026-08-25T08:54:25.157338+00:00`；代码阶段为 M45-A/B 已实现并通过聚焦测试、M45-C concrete adapter 尚未实现。
- HEAD / dirty：HEAD `7d254ff4b5c5e2a0a8c5fc83f4bfdb8a74d79ec9`；模块 dirty 为 `docs/notes/m45-notes.md`、B3 campaign/manifest、`engine/phase4b/rag_diagnostics.py`、`eval/rag_action_diagnostics.py`、`scripts/probe_m45_b3.py`、`tests/test_m45_rag_action_diagnostics.py`，无既有生产文件行为改动。
- 命令：`D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe -m scripts.probe_m45_b3 --probe M45-P1 --output .agent_work/temp/m45-p1-first.json`；只读 active 22-entry release，trusted `ops + customer_service` caller，零模型/embedding/Composer。
- 运行身份：release `7d0d0937...409a`、corpus `1927eb53...7857`、adapter `knowledge-deterministic-lexical-v1`、recipe `title-key-content-ngram-min005-v1`；artifact `0b2a488d...4416`，证据文件 `.agent_work/temp/m45-p1-first.json`。
- 真实 Observation：initial 恰好保留历史缺口（quality present、basic missing）；只有 `policy_scope` unsupported，eligible=`query_rewrite_candidate + stop`，错误 expansion 被拒绝。focused rewrite 新增 basic Evidence，quality 保留，ACL/EvidenceRef/duplicate/no-progress/budget 断言全通过。
- 三态：总体 `passed`；initial gap、trigger、wrong-action rejection、Evidence gain、retention、安全/预算均 `passed`，没有 `not_observed` 子能力。首失败层：无。
- usage：本次 retrieval calls `2`（initial 1 + rewrite child 1），embedding provider attempts `0`、chat/model `0`、Composer `0`、observed chat tokens `0`；模块累计同值。standing 上限 provider calls 8，剩余 8；M45 plan 更紧的 external embedding 上限 5 尚未消费。
- 决策：`continue`。P1 已实际放行 M45-C；不需要 revise/重验，也不追加 Probe。

### 2026-08-25：M45-C 实现 checkpoint（P2 前）

- 在 P1 `continue` 后才新增 `EnterpriseContextLoader.neighbor_unit_identities` 与 `EnterpriseNeighborExpansionAdapter`：先按 seed 的 physical document / normalized offset 只读相邻 identity，再经 SQLite authority 做 preselection 授权、正文水化和 pregeneration 二次授权；每侧至多一个 unit，跨 physical document、ACL deny、identity 漂移与重复 unit 均拒绝。
- expansion adapter 只注入 M45 diagnostic executor，没有连接 B2 产品 Loop、API 或默认 runtime；这保持 M45 是 action 资格诊断而非 M46 Subgraph 实现。
- 聚焦验证首次运行时，M45 的 7 个测试均通过，但 `tests/test_m34_enterprise_runtime.py` 的 4 个 `tmp_path` fixture 因 Windows sandbox 临时目录权限报错，pytest 收尾也出现同源 `WinError 5`；没有业务断言失败。改用已授权的独立 `--basetemp=.agent_work/temp/m45-c-1-approved` 重跑相同集合，结果为 `11 passed in 0.63s`。
- 当前已满足 P2 前置：rewrite/loader seam 与跨文档边界测试完成；尚未调用 external semantic runtime、尚未消耗 embedding provider attempt。下一步只做语法/配置预检与 external diagnostic store 隔离核对，然后执行预注册 P2 一次。
- P2 preflight：四个 M45 Python 文件经 AST parse 为 `syntax-ok`；诊断路径与 sealed reserve 路径规范化后 `same=false`、互不位于对方子树。`docker ps` 显示 Milvus/MinIO/etcd healthy；`scripts.check_enterprise_rag_runtime` 返回 `status=ready`，profile `e8783fe0...fa2`、semantic `9aec12c8...e20`、collection `datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`，且 `embedding_transport_called=false`、`composer_called=false`。尚未写 external store；下一动作仍是预注册 P2 首跑。
- P2 首跑命令在创建进程前被安全审批门拒绝，因此 **Probe 未执行、provider attempt=0、external store 未写入**。拒绝原因不是代码/runtime 故障，而是 qst_0420 原始问题及最多两个 deterministic focused query 将发送给第三方 DashScope embedding 服务，现有计划级 Probe 授权未被审批器视为对这批具体数据出境的明确授权。按门禁不得改走旁路；需用户知情确认该数据发送后，才可原样执行首跑，这不计质量失败或 Probe 重验。

### 2026-08-25：M45-P2 Round 1（after M45-C / before P3）

- 用户明确允许把 qst_0420 及最多两个 deterministic focused query 发送给 DashScope 后执行。时间 `2026-08-25T09:04:34.914235+00:00`；HEAD `7d254ff4b5c5e2a0a8c5fc83f4bfdb8a74d79ec9`；代码阶段为 M45-C adapter/loader seam 已实现、P3 未执行。
- 命令：`python -m scripts.probe_m45_b3 --probe M45-P2 ...`；安全证据 `.agent_work/temp/m45-p2-first.json`，外部完整证据 `phase4b-rag-action-diagnostics/v1.0.0/probes/m45-p2-first-private.json`。安全 artifact `0fe41644...4e1f`，private artifact `f8f2182c...eede`。
- runtime identity 与 preflight 一致：profile `e8783fe0...fa2`、semantic `9aec12c8...e20`、semantic adapter `knowledge-enterprise-milvus-semantic-v1`；reserve access 保持 `sealed`。
- Observation/action：initial 的两个 requirement slot 均判 unsupported，eligible=`query_rewrite_candidate + stop`、expansion rejected；rewrite 执行 2 个 child batch并新增 3 条当前 authority/ACL Evidence，budget/identity/stop/错误动作/零模型均通过。
- 三态：总体 `failed / revise`。失败断言只有 `added_evidence_supports_gap=false` 与 `offline_gold_overlap=false`；新增三条证据均非两个 expected logical document。usage 为 retrieval/embedding provider attempts `3`（initial 1 + child 2），chat/model/Composer/tokens 全 0；模块 external 累计 3，standing 8 尚余 5。
- 离线根因定位发现 **冻结实现偏离 C4**：P2 slot/query 内写入了 `0.085`、`sampled bytes` 等答案事实；同一问题也存在于尚未运行的 P3 slots。这违反“slot 来自服务端 requirement 分解、不得来自 gold/答案文本”，因此 Round 1 不能作为 action 质量 no-go 证据。处理为 plan 允许的“一次最小实现修复重验”：只把 slots 改成由问题实体、所求字段和通用 authority/completeness 语义构成，增加 gold/title/answer-fact 静态拒绝测试；不换题、backend、top-k、budget、runtime identity 或 action 算法。修复后仅重验 qst_0420 一次；若仍无增益立即进入 C5 no-go，不再调词或重跑。
- Round 2 前修复已完成：qst_0420 只保留问题中的 EXP-002/route、`rate`/`measurement basis` 与通用 current-authority 语义；qst_0431/qst_0461 同步在首次运行前移除时长、日期、具体步骤等答案事实，只保留问题实体和所求范围。新增静态测试显式拒绝已知答案值、gold doc id/title 泄漏；与 runtime/neighbor 组合测试共 `12 passed in 0.63s`。该修改恢复原 C4 合同，不更改 action/budget/runtime；下一步为 qst_0420 唯一允许的最小重验。

### 2026-08-25：M45-P2 Round 2（唯一最小重验）与停门

- 执行时间 `2026-08-25T09:07:49.063852+00:00`；命令/runtime 与 Round 1 相同，仅使用修复后的非 gold requirement slots。安全证据 `.agent_work/temp/m45-p2-round2.json`，外部完整证据 `probes/m45-p2-round2-private.json`（文件 SHA-256 `f534f9bb...afa2`）；安全 artifact `ae534a34...ea22`。
- Observation 仍正确选择 `query_rewrite_candidate + stop` 并拒绝 expansion；rewrite 两个 child batch新增 3 条当前 authority/ACL Evidence。新增中包含一个 expected logical document `dsid_7b2f...3f16`，所以 offline gold overlap 为真；但命中的只是该文档首个 unit，正文只有“measurement model updated”等概述，没有 rate 数值，两个 unresolved requirement 均未被完整支持。
- 三态：总体仍为 `failed`。通过：trigger、expected/wrong action、stop、ACL/authority、identity、Evidence identity gain、offline gold overlap、预算、零模型/Composer/token；失败：`added_evidence_supports_gap=false`。这是真实的 context completeness failure，不再是实现偏离，不能继续改 query、top-k、backend 或重验。
- usage：本轮 embedding provider attempts `3`；P2 两轮累计 `6`，chat/model/Composer/tokens 全 0。Round 2 是 plan 明确允许的修复重验；JSON campaign 的 `max_embedding_provider_attempts=5` 与 plan 正文“首次尝试预计 ≤5、实现偏离可最小重验”和 runbook standing 上限 8 存在口径冲突，当前没有继续消耗，需在修订 plan 时一并澄清。
- 停门：P2 未得到 `continue`，因此 P3 的 qst_0431/qst_0461 **不得执行**，expansion card 为 `not_observed`；M45-D 只能进入 `review_required/no_go`，M46 强制开工条件不成立，当前 M45/B3 不得宣称完成，也不得调用 `finish-module` 做完成收工。
- 证据指向的设计信号：rewrite 已找到正确 logical document 的首个 fragment，但缺失答案在同文档后续 context；若允许“rewrite 后再 neighbor expansion”，很可能形成组合恢复链，但这会突破“一题最多一个 recovery action”和两卡独立资格合同，属于核心范围变更，不能在当前 plan 内自行实现。

### 2026-08-25：G45-3 用户确认与续接开工登记

- 用户确认方案 A：M45 改为有界 `rewrite → context expansion` 组合恢复链。已先修订 module plan，再继续实现；保留两个 B0 action identity，scenario chain 上限 2、同 action 最多一次，第二步只能消费第一步新增并重新授权的 fragment，零 embedding/retrieval/model/Composer。
- campaign budget 随新合同改为 `max_recovery_actions_per_scenario=2`、`max_action_repetitions=1`、累计 embedding provider attempts 硬上限 8；campaign identity 更新为 `7ed3dbd3...a1ed`。旧 P1/P2 artifact 保留其执行时的旧 campaign identity，不改签；最终 artifact 必须同时记录合同修订与 prior artifact identity lineage。
- 新增 Live Probe `M45-P2C`（after G45-3 / before P3）：输入只允许 P2 Round 2 safe/private immutable artifact；先核验 safe/private identity 与文件 SHA，再从 unit identity 回 SQLite authority 重水化并双授权；根据 signed requirement 与已授权 Evidence 内容做通用相关度排序，最多 2 seeds、每 seed 前后各 1 neighbor；provider attempts=0。它阻塞 P3，失败后不得重验/扩窗口/换题。
- P2C 预期观察：先前 rewrite 命中的 `dsid_7b2f...3f16` 首 unit 成为高相关 seed；相邻 unit 若补齐 rate/measurement requirement，则 `passed/continue`，否则 `failed/no_go`。gold doc/title 只用于动作后离线 oracle，不参与 seed ranking 或 materialize。
- P2C 实现 checkpoint：新增 `observe_after_rewrite`，把当前 SQLite authority 重水化后的 initial+rewrite Evidence 统一绑定到 continuation run，再计算新 unsupported slots；只有 rewrite 新增 Evidence 可做 seed。Enterprise adapter 用 signed focused requirement 与已授权 title/body 的通用 token overlap 排序，document key/scenario expected ID/gold 不进入 score。首次聚焦测试暴露测试 fixture 仍混用 child run_id，触发 EvidenceLedger `evidence_run_mismatch`；修正为 continuation authority rehydration 的统一 run identity 后，同一集合 `13 passed in 0.61s`。尚未执行 P2C，provider 累计仍为 6。

### 2026-08-25：M45-P2C 与第二次停门

- 执行时间 `2026-08-25T09:25:26.068047+00:00`；输入 lineage 为 P2 Round 2 safe artifact `ae534a34...ea22`，P2C safe artifact `e8bda78c...d6e6f`，private 文件 SHA-256 `2707dce6...9545`。campaign identity `7ed3dbd3...a1ed`、external runtime identity保持不变，reserve access=`sealed`。
- 调用与预算：只读回查 SQLite/profile，retrieval/embedding/chat/model/Composer/token 全 0；P2 两轮累计 provider attempts 仍为 6。source identity、authority rehydration、ACL、chain action=2、rewrite 禁止重复和 stop 均通过。
- Observation：rewrite 后两个 slot 仍 unsupported；adapter 对最多 2 个相关 seed 检查前后各 1 个 neighbor，没有 neighbor 单独满足完整 typed gap，因此 expansion preview=0，eligible 只有 `stop`，动作正确停止。总体 `failed/stop`；未新增 Evidence。
- 离线只读根因对账：rewrite 命中的目标文档首 unit 为 normalized `0-2218`，已含 updated measurement 概述；直接后邻 `2220-4278` 只有 experiment matrix/EXP-002 概览；完整 `+$0.085/GiB` rate 位于同 physical document 的 `6027-7658`，与 seed 相隔 3 个 unit。即使修正 preview 让“seed+neighbor 联合支持”而非“neighbor 单独支持”，当前 ±1 window 仍拿不到 rate，不能作为实现缺陷重验。
- 结论：方案 A 的“两步组合”方向成立，但“只补直接相邻 unit”的 action card 对该真实文档仍能力不足。继续扩大到 3-hop、整篇 parent 或 section-aware unit selection 都会改变 expansion scope/context budget，属于新的核心合同决策；当前 plan 的 P2C 禁止重验，P3 继续被阻塞，M45/B3 仍不能完成或调用 `finish-module`。

### 2026-08-25：G45-4 用户确认与 P2D 预登记

- 用户确认方案 A：不写死 ±3 hop，改为同一 physical document 内的有界 sibling 搜索。plan 已先修订；immediate-neighbor v1/P2C 失败证据永久保留，新的实现 identity 与 Probe 使用 v2/P2D。
- 新 action budget：最多 2 seeds；每个 seed 按 unit 距离稳定顺序最多检查 8 个 sibling identity；每项 pre-selection ACL 后才加载正文；用 `seed + sibling subset` 对 signed requirement 做 deterministic 最小组合搜索；最终最多新增 4 Evidence 并逐项 pre-generation ACL。零 embedding/retrieval/model/Composer，禁止跨文档、gold/title/答案 selector、无限扫描和加入无 coverage 贡献的中间 unit。
- 新 Live Probe `M45-P2D`（after G45-4 / before P3）：复用并核验 P2 Round 2 immutable lineage，验证 sibling v2 能补齐 qst_0420 rate + measurement；provider attempts=0。`passed/continue` 才放行 P3；失败即 C5 no-go，不再扩大 scan/add budget或重验。
- P2D 实现 checkpoint：loader 改为 identity-only `sibling_unit_identities(max_units<=8)`，按距 seed 由近到远稳定排序且不跨 physical document；adapter v2 对授权 sibling 做最多 4 项的 closed-world 组合搜索，优先 coverage 更多、再取更小组合，不加入无贡献 unit。`cost rate` 由 signed focused query 通用推导“必须出现货币数值”的 value-shape，不写具体答案。campaign 最终 identity 更新为 `469b5ec0...12fe`，预算字段改为 scan 8/add 4。
- 聚焦测试首次只因新测试漏导入 `DocumentEvidencePayload` 发生单个 `NameError`，实现断言未失败；补齐 import 后相同集合 `14 passed in 0.64s`，覆盖同文档最小联合支持组合（跳过中间无贡献 unit）、距离边界、ACL、continuation run identity、zero retrieval/model。P2D 尚未执行，provider 累计仍为 6。

### 2026-08-25：M45-P2D（after G45-4 / before P3）

- 执行时间 `2026-08-25T09:35:47.621074+00:00`；source 为 P2 Round 2 safe artifact `ae534a34...ea22`，P2D safe artifact `23eea7f1...e630`，private 文件 SHA-256 `2f55d404...1343`；campaign `469b5ec0...12fe`、external runtime/profile/semantic/unit-set identity均与前序一致，reserve=`sealed`。
- Observation/action：rewrite 后 `current_egress_rate`、`measurement_basis` 仍 unsupported；sibling-v2 形成 2-unit 最小支持组合，eligible=`context_expansion_candidate + stop`、rewrite repetition rejected。新增同一 expected Google Drive 文档 `2220-4278`（EXP-002 概览）与 `6027-7658`（current rate），跳过无贡献中间 unit。
- 三态：总体 `passed/continue`；source identity、trigger、wrong-action rejection、stop、Evidence gain、remaining slots supported、gold-doc-only、ACL/identity、chain action=2、zero provider 全部通过，无 `not_observed`。usage 为 retrieval/embedding/chat/model/Composer/token 全 0；模块 provider 累计仍 6。
- 决策：P2D 放行 P3。P3 两个 external 问题各只有一次 initial semantic query、expansion 零额外 embedding，预计再消费 2 provider attempts并到达模块硬上限 8；不得重验。
- P3 前补强：runner 现在只执行 campaign 为该 Scenario 预注册的 expected action；若 expansion trigger 不成立，即使 generic Observation 会允许 rewrite，也强制选择 `stop` 并记录 `expected_action_not_eligible`，避免偷偷发送 child rewrite query或突破 provider 上限。聚焦回归仍为 `14 passed in 0.63s`，Probe runner AST parse 通过。
- P3 首跑命令在创建进程前被数据出境审批门拒绝，**Probe 未执行、provider attempt 仍为 6、external P3 artifact 未写入**。审批器要求用户在对话中明确允许两条具体 benchmark payload 发送至 DashScope；不得旁路。待授权内容仅为 qst_0431/qst_0461 原始问题各一次，不含 gold、文档正文或 reserve。

### 2026-08-25：M45-P3（after P2D / before M45-D）

- 用户明确允许 qst_0431/qst_0461 两条 synthetic benchmark 问题各发送一次给 DashScope 后执行。时间 `2026-08-25T09:38:22.692836+00:00`；safe artifact `5c4592ed...d38b`，private 文件 SHA-256 `96ed4057...4a65`；runtime/campaign identity 与 P2D 一致，reserve=`sealed`。
- qst_0431：initial selected Evidence 已让 `rollback_core/hosted_completion/dedicated_completion` 三个通用 marker slot 全部判 supported，unsupported=0、eligible 只有 `stop`，rewrite/expansion 均 rejected；没有执行 recovery、没有 EvidenceDelta。
- qst_0461：同样，initial 已让 `opened_items/old_item_discard/weekly_schedule` 全部判 supported，unsupported=0、eligible 只有 `stop`；没有执行 recovery、没有 EvidenceDelta。
- 三态：P3 整体 `failed/revise`，两题均为 trigger/expected-action/evidence-gain 未通过；安全负断言、wrong-action rejection、stop、zero extra embedding/model、runtime/ACL 均通过。runner 的 expected-action guard 生效，没有 fallback 到 rewrite。
- usage：两题 initial semantic retrieval/embedding 各 1，总计 2；chat/model/Composer/tokens=0。模块 external provider 累计 `8`（P2 Round1 3 + Round2 3 + P3 2），达到 G45-4 campaign/runbook 硬上限，不得重验或新增真实 Scenario。
- 根因：historical review 认为两题“命中 gold 但完整性不足”，而当前 deterministic question-derived slots 只能识别 Hosted/Dedicated/rollback、weekly/schedule/discard 等主题字段，不能在不读取 gold/答案的前提下知道缺的是哪些具体步骤/阈值/时点。因此没有真实 fragment Observation，expansion v2 action 本身虽在 P2D 证明可用，但 direct expansion admission 未在两题成立。
- 决策：进入 M45-D `review_required/no_go`。这满足 G45-1 方案 B 的重开证据信号（多个冻结 dev case 的 deterministic requirement understanding/coverage failure，action seam 已由 P1/P2D 证明），但本模块没有模型用途/outbound/provider 额度，不能自行启用；P3 不重验，M45/B3 不完成，M46 不开工。

### 2026-08-25：M45-D 离线 qualification

- 新增允许 no-go 的 closed-world review artifact builder/validator；固定 lineage 为 P1、P2 R1/R2、P2C、P2D、P3，逐项复算 artifact identity，provider usage 求和必须等于 campaign 8，删除 Probe/改 qualification/改 hash 均失败关闭。聚焦测试 `15 passed in 0.91s`。
- 离线 rehearsal 生成仓库安全产物：`eval/reports/m45/m45-b3-diagnostic-review.json`、`m45-b3-failure-slices.json`、`m45-b3-review.md`；review artifact identity `33efaf8f...9ea9`，decision=`review_required/no_go`，rewrite card=`completed`、context expansion card=`failed`。
- 外部 immutable manifest：`phase4b-rag-action-diagnostics/v1.0.0/m45-b3-private-manifest.json`，identity `b10b8230...a243`，文件 SHA-256 `467de737...ed3`；仓库 artifact 记录的 SHA 与实际文件 `match=true`，包含 5 个 private Probe artifact 的逐文件 SHA/identity，不混入 reserve。
- M45-D 结论：continuation sibling expansion passed，但 direct expansion trigger 在 qst_0431/qst_0461 均未观察到，`direct_expansion_card_complete=false`；M46 开工门失败。下一步只允许用户 review 后修订 M45 plan（优先重开 G45-1 structured requirement proposal 的 receiver/purpose/outbound/model/token 合同），不得把本次 no-go 当模块完成。
- 收尾复核第一次执行 rehearsal 时把 `--private-root` 误传为版本根下的 `probes/`，脚本因而寻找 `probes/probes/m45-p2-first-private.json` 并在读取前 `FileNotFoundError`；未写输出、未调用 provider，也不构成 Probe/Eval。修正为 `v1.0.0` 版本根后再执行。
- 修正后的离线 rehearsal exit 0，稳定重建 decision=`review_required/no_go`、review identity `33efaf8f...9ea9`、external manifest identity `b10b8230...a243`、provider attempts=8；没有网络或模型调用。M45 聚焦 + M34/M41/M44A 受影响兼容回归为 `36 passed, 1 warning in 2.24s`，warning 是既有 Starlette TestClient/httpx deprecation。
- 最终静态复核：7 个新增/修改 Python 文件 `compileall` exit 0；`git diff --check` 无 whitespace error（只有 Windows LF→CRLF 提示）；external manifest 实际 SHA-256 与仓库 review 记录均为 `467de737...ed3`、`match=true`。人工检索 TODO/FIXME/占位实现及 gold/reserve/answer 边界，未发现未解释的占位；Probe runner 的 gold 仅在动作后离线 oracle 使用，safe projection 继续显式拒绝 question/content/gold/prompt/thought。

### 2026-08-25：C5 用户 review 后重开 G45-1

- 用户在正式 `review_required/no_go` 后选择继续方案 A（即上一轮对话中建议的 structured requirement/rewrite proposal 路线，对应原 G45-1 方案 B），允许继续修订 M45；既有 no-go artifact、8 次 provider attempt 与 P1～P3 lineage 不覆盖、不改签。
- 实施前发现仍有长期安全分叉尚未冻结：proposal 是只发送两道 public benchmark question，还是同时发送 initial Document Evidence 正文。用户说明项目是 demo、优先效果，因此确认受控 A2：每题 question + 最多 3 个当前已授权 Evidence、每项最多 4000 字符发往 Qwen；不发送 title/key、gold、参考答案、review verdict、sibling 或 reserve。模型只提 requirement/rewrite proposal，本地 validator/coverage/ACL/budget/stop 仍掌握最终权力。
- 新切片冻结 `qwen_chat / rag_requirement_proposal / public_benchmark_question_with_authorized_evidence / prompt+system_prompt+model`，`qwen3.7-plus`、temperature0、thinking=false、retry0、每题一次、max completion 1600、两题新增最多 2 calls/8000 observed tokens。现阶段先实现 fake transport 与离线测试；真实 P4 前仍需对两条 question + Evidence payload 做执行授权检查。
- M45-E 首轮实现新增显式 value-shape、question/Evidence-only prompt、strict JSON validator、diagnostic-only outbound policy 和 fake transport 测试。首次聚焦结果 `15 passed / 1 failed`：百分比答案值正则在 `%` 后误用 word boundary，`30%` 未被拒绝；这是 validator 实现缺陷，零网络调用。已把尾界改为 `(?!\\w)`，保留失败证据后重跑同一集合。
- 修复后聚焦 `16 passed`；新增 additive v2 campaign `c86e3870...eaea`（predecessor=`469b5ec0...12fe`）、P3 immutable Evidence 的 `observe_existing` seam、P4 runner 和 v2 qualification/tamper gate。fake proposal→旧 initial Evidence→sibling expansion 第一条纵向链通过，随后聚焦增至 `19 passed`；旧 deterministic slot 的默认 signature 特意保持不变，P1～P3 不改签。
- P4 前静态/兼容验证：相关 Python `compileall` exit 0、runner `--help` 可用、`git diff --check` 无 whitespace error；M45 + M34/M41/M44A 受影响集合 `44 passed, 1 warning in 1.77s`，warning 为既有 Starlette/httpx deprecation。未调用网络/provider。
- P4 preflight 第一次直接使用 dataset `v1.0.0` 顶层作为 profile root，resolver 返回 `ExternalProfileError`；定位为坐标错误而非 runtime 故障。改用 state 对应的 `derived/enterprise_profiles` 与 `derived/enterprise_semantic` 后 status=`ready`，profile `e8783fe0...fa2`、semantic `9aec12c8...e20`、unit-set `17d5af0...905f`，`embedding_transport_called=false`、`composer_called=false`。P3 safe identity `5c4592ed...d38b` 复算通过，Qwen key存在、model=`qwen3.7-plus`、timeout=120s。
- 当前阻塞门：真实 P4 尚未执行。精确 payload 为 qst_0431/qst_0461 public benchmark question + 各自 P3 已授权 initial Evidence 最多 3 项/每项最多 4000 字符，receiver=DashScope Qwen；每题首次 1 call、retry0，总计最多 2 calls/8000 observed tokens，零新 embedding/retrieval/Composer，不含 gold/答案/reserve。须在发送前取得用户明确执行授权。

### 2026-08-25：M45-P4（after M45-E / before M45-F）

- 用户明确允许发送并继续 P4。执行时间 `2026-08-25T18:11:34.913973+08:00`；campaign v2 `c86e3870...eaea`、source P3 safe `5c4592ed...d38b`，runtime profile `e8783fe0...fa2` / semantic `9aec12c8...e20` / unit-set `17d5af0...905f`，reserve=`sealed`。
- usage：两题各 1 次 Qwen `qwen3.7-plus` proposal，总计 2 chat calls / 3877 observed tokens；零新 retrieval、embedding、Composer，retry0。模块累计为旧 8 embedding + 新 2 chat = 10 provider attempts，命中 v2 硬上限；未重跑。
- qst_0431：provider 成功返回，但 strict validator 在 `proposal_marker_group_invalid` 停止，action 未执行。prompt 只给了 JSON shape，没有告诉模型 validator 的“每组 1～4 markers”硬上限；失败 runner 又只记录 reason、没有把已收到 raw JSON 写入 private artifact，因此无法靠本地代码修复重放。这是 prompt/schema 对齐与失败证据保留的实现缺陷，不是 provider unavailable。
- qst_0461：proposal 合法，validator 从四项中只保留本地仍 unsupported 的 `weekly_cleanup_schedule`，但 expansion preview=0、eligible=`rewrite + stop`，runner 按 expected-action guard 安全 stop。只读回 SQLite authority 复核：同一 physical doc 的 sibling 明确包含 `Cleanup procedure`、`Weekly Friday 4pm quick tidy`；模型 marker 是 `weekly cleanup schedule / fridge tidy rota / cleaning routine`。现 matcher 对多词 marker 做整句 literal match，语义等价但字面不同，因此没有准入 sibling。
- safe artifact `a374f0c0...cfac`；private identity `82e1a3b9...b43a`、文件 SHA-256 `319c84d3...a0b`。v1.1 external manifest `bf69566d...d337`；additive v2 review `ce0d7615...40af` 为 `review_required/no_go`。P4 的预算、安全停止和禁止 fallback 均 passed，但 proposal validation/direct expansion card failed；M45/B3 仍未完成，M46 继续 blocked。
- 下一最小修复候选尚未授权：prompt 明示完整 schema 上限并在 validation failure 私有保留 raw；只对 model-proposed slots 增加 deterministic token-overlap marker mode、旧 exact slot 不变；qst_0461 用本次 immutable response 零 provider 离线重放，qst_0431 另加唯一 1 次 proposal revalidation。该方案会把 cumulative provider attempts 从 10 扩为最多 11，须新 campaign/Probe 与用户确认，不能按 P4 自动重验。

### 2026-08-25：用户确认 M45-G 最小 repair

- 用户选择方案 A 并继续：proposal-only token-overlap、qst_0461 immutable 离线重放、qst_0431 唯一一次新 Qwen。v3 累计上限为旧 8 embedding + P4 2 chat + repair 1 chat = 11 provider attempts；chat tokens 仍沿用总上限 8000，新调用最多使用剩余 4123。qst_0461 不重发，qst_0431 revalidation 后无第二次重验。
- qst_0461 首次 offline-preflight 在任何 provider 调用前以 `proposal_no_unsupported_requirement` 停止。定位为 proposal token-overlap coverage 把三份不相关 initial Evidence 拼接后交叉取词：一份贡献 `weekly`、另一份贡献 `afternoon`，错误合成 schedule complete。修复限定为 proposal slot 的 current coverage 必须由单条 Evidence 同时满足 marker+value-shape；同一 physical doc seed+sibling 的显式组合仍由 expansion adapter 调 `supported_by_text`。旧 exact slot 不变，本次 provider calls=0。
- 第二次 offline-preflight 仍在 provider 前安全 stop：proposal 保留两个真实缺口，但正确 Google Drive seed 的 query-token relevance=4，只排第 3，被分数 9/5 的两个无关 Jira seed 占满 max_seeds=2。修复仍限定 proposal slot：validator 已接受的 marker coverage 作为 seed ranking 高权重 hint；不读取 gold/title key、不扩大 2-seed/scan8/add4，旧 exact 排序不变。本次 provider calls仍为0。
- 第三次 qst_0461 immutable offline-preflight passed：chosen=`context_expansion_candidate`，新增 1 条同 physical document sibling；proposal marker mode、wrong rewrite rejected、stop、Evidence gain、全部 proposal gaps supported、offline gold-document-only、零 retrieval/embedding/Composer 和 expansion budget 全部通过。整体 preflight artifact 因显式 `offline_preflight_only` 未运行第二题而保持 stop，不冒充 P4R completed；provider calls=0。该结果放行 qst_0431 唯一一次 revalidation。

### 2026-08-25：M45-P4R qst_0431 唯一 revalidation 与停门

- P4R 前 `compileall`、`git diff --check` 和 M45/M34/M41/M44A 受影响回归通过：`49 passed, 1 warning in 1.83s`；warning 为既有 Starlette/httpx deprecation。qst_0461 在同一正式 runner 中先再次离线通过，随后才按用户确认执行 qst_0431 唯一 1 次 Qwen。
- qst_0431 provider transport 成功返回，但 structured validator 对模型 proposal 本地重算后没有留下任何 unsupported requirement，以 `proposal_no_unsupported_requirement` 停止；没有执行 expansion/rewrite/retrieval/embedding/Composer。该结果说明 revised prompt/schema 已不再触发 P4 的 marker-group 格式错误，但模型 proposal + 当前 coverage 仍未识别 Dedicated continuation 缺口。
- runner 缺陷：P4R qst_0431 分支没有像 P4 runner 一样 catch `RequirementProposalError`，进程以 exit 1 退出，导致已经返回的 raw response、provider usage 和完整 safe/private P4R artifact 未落盘。物理 chat attempt 明确为 1；observed tokens 已随进程内 client 丢失，必须标 `token_usage_observed=false`，不得估算/记 0 冒充观察值。qst_0431 本次就是 plan 允许的唯一 revalidation，禁止因证据落盘缺陷再次调用。
- 模块累计 provider attempts 明确为 11（8 embedding + P4 2 chat + P4R 1 chat）；P4R 新 tokens 不可观察。下一步只允许从 qst_0461 offline immutable artifact、exception reason、命令/exit 与已知 call count 构建显式 `evidence_incomplete` 的恢复 artifact 和 v3 no-go review，不得重发或宣称 go。

### 2026-08-25：P4R 离线恢复与 v3 最终 qualification

- 只用既有离线证据构建 recovered safe artifact `6426219b...a949`；项目外 private artifact SHA-256 `aed7e3f1...e8d6`。恢复件明确写入 `evidence_completeness=incomplete_raw_response_and_token_usage_lost`、chat call=1、tokens=`null/unobserved`，没有估算或补发。
- v3 review `8fb3cfad...14e4` 稳定输出 `review_required/no_go`：qst_0461 offline expansion passed，qst_0431 expansion failed；累计 provider attempts=`8 embedding + 3 chat = 11`。项目外 v1.2 manifest identity `30e5e547...0500`，仓库 review 记录的 manifest SHA 与文件实际 SHA 匹配。
- 新增 v3 qualification/tamper 测试与离线 rehearsal。聚焦 `25 passed`；受影响 M45/M34/M41/M44A 回归首次受 Windows sandbox `tmp_path` 权限影响，沙箱外原集合重跑为 `50 passed, 1 warning in 2.20s`；warning 是既有 Starlette/httpx deprecation。`compileall` 与 `git diff --check` 通过（仅 LF→CRLF 提示）。
- 最终开发决定：`stop`。当前 campaign 已耗尽唯一 qst_0431 revalidation，M45/B3 未完成、M46 blocked；按 plan 不调用 `finish-module`。如继续，需要用户确认新的核心 action trigger/模块范围，不能把它包装成当前 repair 的再重验。

### 2026-08-25：用户确认 M45-H 结构完整性方案 A

- 用户确认继续：不再让模型猜“还缺什么”，而是当 signed requirement 明确询问 procedure/workflow/steps/checklist，且 selected unit 在同一物理文档中确有后续 unit 时，确定性准入 forward continuation expansion。
- 适配边界：trigger 显式默认关闭，只在新 P5/v4 使用；不按 qst ID/title/gold 选文档，不把 arbitrary sibling 当支持事实，不增加 provider、retrieval、embedding 或 Composer；仍由 SQLite authority、ACL、同文档坐标、预算和去重门控制。
- P5 预注册：复用 P3 qst_0431 immutable Evidence，一次离线真实 runtime replay，provider calls=0；fake 合同测试先行。P5 失败不再扩大 heuristic 或调用模型，回到用户 review。

### 2026-08-25：M45-P5 前 checkpoint

- 代码阶段：`procedure_boundary_v1` 已形成第一条 fake 纵向链；默认关闭时旧 all-covered Observation 仍 stop，显式开启且 procedure-shaped query + forward authority unit 同时成立时才准入 expansion。新增 loader forward-only identity seam，materialize 仍走既有 ACL/identity/duplicate/budget。
- HEAD=`7d254ff4b5c5e2a0a8c5fc83f4bfdb8a74d79ec9`；模块 dirty 为 M45 既有未提交实现，加本切片 `engine/rag/enterprise_runtime.py`、`engine/phase4b/rag_diagnostics.py`、`engine/phase4b/rag_enterprise_diagnostics.py`、v4 campaign、P5 runner、M45 tests/plan/notes/state。
- 已完成验证：M45 聚焦 `28 passed`；M45 + Enterprise runtime 合并集合首次仅因 Windows sandbox `tmp_path` 权限 error，沙箱外原集合 `32 passed in 0.64s`；`compileall` exit 0，`git diff --check` 只有 LF→CRLF 提示。
- 待执行：P5 一次，只读 P3 safe/private identity 并回当前 SQLite authority 重水化 qst_0431；零 semantic retrieval、embedding、chat/proposal、Composer。safe 输出 `.agent_work/temp/m45-p5-first.json`，private 输出隔离的 `phase4b-rag-action-diagnostics/v1.3.0/probes/`；passed 才进入 v4 qualification，failed 立即 stop。

### 2026-08-25：M45-P5 procedure boundary replay

- 首次命令在进入 runtime 前以 `enterprise_rag_not_configured` 失败：进程未设置 profile root/identity。没有加载场景、执行 action、写 artifact 或调用 provider，因此记为 invalid preflight，不算 P5 质量 attempt。按 runbook 补固定 semantic profile/identity 后执行同一命令，未改代码、场景或预算。
- 有效执行时间 `2026-08-25T11:46:22Z`；代码阶段为 M45-H 第一版、HEAD=`7d254ff4...9ec9`，dirty 与前 checkpoint 相同。runtime profile=`e8783fe0...fa2`、semantic=`9aec12c8...e20`；P3 safe/private identity 重验并回 SQLite authority 重水化/重授权。
- P5 `passed/continue`：initial deterministic slots 全部显示 covered，但 `procedure_boundary_v1` 观察到 forward unit，eligible=`context_expansion_candidate + stop`、rewrite rejected，preview=2；动作新增 2 条 forward same-physical-document Evidence，Evidence gain/ACL/budget 全绿。
- usage：retrieval=0、embedding=0、chat/proposal=0、Composer=0、observed tokens=0；模块累计 provider attempts 仍为 11。safe identity `a3a4f7e8...4a72`；external private SHA-256 `16959220...39de5`。决定 `continue`，放行 v4 离线 qualification，不授权任何新增 provider。

### 2026-08-25：M45-H v4 qualification

- v4 campaign identity `15cda06e...e708`；P5 与 predecessor v3 review 的 canonical hash、lineage、reserve sealed 和零 provider usage 全部重算。final review `949a3b03...fbb4`=`go_for_M46`，两张 action card 均为 `completed`，累计仍为 `8 embedding + 3 chat = 11`。
- external v1.3 manifest identity `2d369472...d0f6`、文件 SHA-256 `bd771157...1450`；仓库 review 保存的 manifest SHA 与实际文件匹配。P5/private 正文仍只在项目外诊断仓库，仓库 review 不含 question/content/prompt/raw response。
- 聚焦 v4 qualification/tamper 后 M45 单文件 `29 passed`；最终受影响集合 M45/M34/M41/M44A `54 passed, 1 warning in 1.94s`。warning 为既有 Starlette/httpx deprecation，不影响 M45。

## finish-module 技术收工素材

### 模块名称与改动文件清单

- 模块：M45 / Phase 4B B3 RAG failure funnel 与 action-level Evidence admission；起始 commit 明确为 `7d254ff4...9ec9`，期间没有模块提交，当前范围均在工作树。
- 合同与代码：`domain_pack/phase4b/b3_diagnostic_campaign{,_v2,_v3,_v4}{,.manifest}.json`；`engine/phase4b/rag_diagnostics.py`、`rag_enterprise_diagnostics.py`、`rag_requirement_proposal.py`；`engine/rag/enterprise_runtime.py`；`eval/rag_action_diagnostics.py`。
- Probe/rehearsal：`scripts/probe_m45_b3.py`、`probe_m45_b3_reopen.py`、`probe_m45_b3_repair.py`、`probe_m45_b3_continuation.py`、`recover_m45_p4r_failure.py`、四个 `rehearse_m45_b3*.py`。
- 测试与证据：`tests/test_m45_rag_action_diagnostics.py`；`eval/reports/m45/` 下 v1～v4 review/failure slices；项目外 `phase4b-rag-action-diagnostics/v1.0.0`～`v1.3.0` private Probe/manifest。
- 文档：本 plan/notes、`docs/state/AI_CONTEXT.md` 与 `docs/state/change-history/phase4b.md`。无 ORM/Alembic、API schema、active release、默认模型/embedding 或产品 B2 Loop 改动。

### 关键决策与取舍

- G45-1 首轮选 deterministic rewrite，失败簇形成后用户再确认受控 structured proposal；原因是先隔离 action seam，再为 demo 效果补语言理解。风险是模型 proposal 不稳定，故只准出 closed-world JSON，本地 validator/coverage/ACL/budget 掌权。
- G45-3/G45-4 用户选择 `rewrite → expansion` 与 bounded same-document sibling scan，而非按题写死 hop；原因是真实 chunk 距离超过 immediate neighbor。风险由 scan8/add4、2 seeds、同文档与双 ACL 控制。
- P4/P4R 仍漏掉 qst0431 后，用户确认 M45-H 结构方案 A：procedure-shaped requirement + authority forward unit 才准入，默认关闭。它提高 demo 完整性但可能多取后续章节；不把后续正文宣称为答案事实，B4 仍需在产品 Subgraph/Eval 中验证净收益。

### 阶段 1 注释小结

- 完整审计 13 个模块 Python 文件、126 个类/函数；为 proposal 入口、campaign/review IO、Probe/rehearsal main、恢复证据、budget/signature/result projection 等补写或深化 25 个中文 docstring。
- 深化的新概念：模型只做 proposal、不做 Controller；`procedure_boundary_v1` 只证明物理 forward continuation，不证明答案正确；safe/private artifact 与 observed/unobserved token 分账。
- 剩余 17 个无独立 docstring 的符号均为 Protocol 空签名、简单 dataclass/projection 或局部闭包，已有所在类/函数注释且属于 skill 豁免；未发现 TODO/FIXME/placeholder，仍缺失数为 0。

### Live Dev Probe 开发时间线审计

- 适用：模块修改真实 business/external RAG action admission。P1 在 rewrite 首条纵向链后、P2/P2C/P2D 在 expansion 演进点、P3 在 direct expansion 后、P4/P4R 在 proposal 改动后、P5 在结构 trigger 后且 qualification 前执行；所有失败 attempt、用户扩额/出站授权、修复、最小重验、calls/tokens、identity、三态与 `continue/revise/stop` 均按时间记录在上文。
- P5 前 contemporaneous checkpoint 已记录代码阶段、HEAD/dirty、验证、真实依赖与输出路径；有效 P5 在 finish-module 前发生。不存在 `development_probe_missing`、收工补跑冒充 Probe、held-out/reserve 访问或 Formal Eval 混算。

### 参考资料

- 定点复核 ARAG child/parent retrieval、条件边与去重，以及 DB-GPT structured references/evaluator 分层。借鉴首次检索与恢复分权、identity 驱动 context continuation、确定性 dispatcher；适配为 SQLite authority、typed Observation/EvidenceDelta、ACL、预算和 sealed reserve。
- 不照搬自由 LLM tool call、字符串 Observation、顺序 parent ID、默认展开全文、用 gold/title 选 seed 或平台级大状态。

### Handoff

- **已完成且可依赖**：B3 两张 action card、failure funnel、typed Observation/action/Delta/budget/stop、同文档 sibling expansion、structured proposal 边界、默认关闭的 procedure forward trigger、v4 `go_for_M46` review 与 tamper-safe lineage。
- **未完成与风险**：这些仍是隔离 diagnostic runtime，不是产品 Agentic RAG；P5 只证明 qst0431 一次确定性 Evidence gain，未证明答案正确、总体质量、Reliability 或默认净收益。P4R raw/token usage 永久缺失并如实保留为历史不完整证据。
- **必须延续的边界与决策门**：M46 reserve 继续 sealed 到其 plan 冻结；产品 B2 Loop/default/API 未改；M46 不能把 proposal 当事实或自由 planner，必须保留 ACL、父子预算、duplicate/no-progress、stop 和 safe/private 投影。
- **下一模块入口与必读指针**：M46/B4 plan 优先从 v4 review、`rag_diagnostics.py` 的 Observation/execute seam、`rag_enterprise_diagnostics.py` 与本 notes 的 P2D/P4/P4R/P5 时间线开始；再按 roadmap 决定 Pipeline/Subgraph A/B 与首次 reserve 协议，不在 M45 提前冻结拓扑。

### State impact（初步）

- **待更新**：`AI_CONTEXT.md`（M45 完成、M46 planning unblocked、P5/v4 最新事实）；Phase 4B changelog（完整模块档案与旧 no-go 修正）。
- **已检查、预计无需修改**：`rag-current-state.md`、`schema-retrieval-milvus-embedding.md`（profile/semantic/collection/unit-set、产品默认与失败关闭均未改变）；`eval-baselines.md`（M45 是 exploratory/baseline-ineligible，不登记正式基线）；`runbook.md`/`runbook-rag.md`（现有运行、Probe、profile 坐标已覆盖）。
- **未命中**：数据库与 Text2SQL 专项 state。

### 阶段 2 收工验证 checkpoint

- 已完成：`compileall` exit 0；M45/M34/M41/M44A 受影响回归 `54 passed, 1 warning`；P5/v4 review/manifest hash 对账通过；`git diff --check` 无 whitespace error（仅 LF→CRLF 提示）。
- 已知风险：全仓 deterministic pytest 预计超过 2 分钟，须按 AGENTS 后台运行；未检查完成前不宣称 finish-module 完成。
- 待完成：启动并检查全仓 pytest，随后完成技术档案 checklist、AI_CONTEXT/changelog 回读、链接与最终 diff 检查。
- 后台全仓 pytest 已启动，PID=`66044`；命令为项目 Python `-m pytest -p no:cacheprovider --basetemp=.agent_work/temp/m45-finish-full/pytest-temp`。日志 `.agent_work/temp/m45-finish-full/pytest.log`，退出码 `.agent_work/temp/m45-finish-full/exit-code.txt`，完成标记 `.agent_work/temp/m45-finish-full/done.marker`。当前状态：**运行中，待检查**；未提前记录为通过。

### 阶段 2 最终验证快照

- 后台任务完成标记存在、exit code=`0`；同一任务未重启/resume。全仓结果 `582 passed, 1 warning in 665.44s (0:11:05)`。warning 仍是 `fastapi.testclient` 引入的 Starlette/httpx deprecation，不影响 M45 合同或行为。
- 结合前述验证：compileall exit 0；聚焦 `29 passed`；受影响 `54 passed, 1 warning`；全仓 `582 passed, 1 warning`；P5/v4 identity/manifest SHA 对账通过。没有 ORM/Alembic/数据库 reset、Formal Eval、held-out 或 reserve 运行。

### 技术档案 checklist

- [x] 模块最终文件范围已与 Git status、起始 commit `7d254ff4...9ec9`、无中间提交事实和本 notes 核对。
- [x] notes 已固化关键决策、注释小结、验证快照、参考资料、Handoff 和 State impact。
- [x] P1～P5 Live Dev Probe 时点、依赖切片、失败/修复/重验、usage/identity/三态与决策已审计；不存在 `development_probe_missing` 或 Formal Eval 混算。
- [x] 已读取 `CHANGELOG_INDEX.md` 并按索引更新 Phase 4B 完整模块记录，同时在旧 no-go 条目原位追加最终修正。
- [x] `AI_CONTEXT.md` 已替换 M45 no-go/待 P5 的失效状态，保留 M46 必须知道的诊断边界和 v4 handoff。
- [x] 命中的 `rag-current-state.md`、`eval-baselines.md`、`schema-retrieval-milvus-embedding.md`、`runbook.md`、`runbook-rag.md` 已完整检查；身份、默认、基线和运行入口均未变化，因此无需修改。
- [x] changelog、AI_CONTEXT、代码、tests、v4 review 和专项 state 不存在冲突或重复权威定义；旧 P4/P4R no-go 作为 lineage 历史保留，不再冒充当前状态。
- [x] changelog 新章节、AI_CONTEXT 和未改专项 state 已回读；新增/修改路径均存在。
- [x] 最终 `git diff --check` 通过（仅 Windows LF→CRLF 提示，无 whitespace error）。

### State impact（最终）

- **已更新**：`AI_CONTEXT.md`（M45/B3 技术完成、v4/P5 最新事实、M46 planning/验收门）；Phase 4B changelog（完整模块记录与旧 no-go 修正）。
- **已检查、无需修改**：`rag-current-state.md`、`schema-retrieval-milvus-embedding.md`（profile/semantic/collection/unit-set、产品默认和失败关闭未变化）；`eval-baselines.md`（M45 全部 Probe 是 exploratory/baseline-ineligible，不登记正式基线）；`runbook.md`/`runbook-rag.md`（现有 Probe 与固定 profile 坐标足够，P5 invalid preflight 正是按现行入口修正）。
- **未命中**：数据库与 Text2SQL 专项 state。

### finish-module 结论

- M45/B3 技术收工完成；v4 qualification=`go_for_M46`，reserve 仍 sealed。下一步值得做的 Formal Eval：**当前不运行**；应在 M46 产品 Subgraph 完成并冻结其 plan 后，才按精确授权首次运行 sealed decision reserve Pipeline/Subgraph A/B。

## finish-docs 执行清单

- [x] 有“简述”和“先用大白话讲”，准确说明问题、方案、价值和边界。
- [x] “这次做了什么”先有一段概览，再有至少 3 条一级编号 `1.`、`2.`、`3.`。
- [x] “这次做了什么”的每个编号点都交代：原问题/影响、关键概念的通俗解释、如何解决、重要取舍、验证证据、未证明的边界；不适用项可以省略。
- [x] 每个编号点没有挤成一个无断点大段：编号下先写一句可独立成立的结论，再用 `- **小标题**：` 或分段落拆分不同主题；任何自然段超过约 4 行、或包含 3 个以上独立主题时必须拆分。
- [x] 正文每个英文/代码术语首次出现时紧跟括号或一句通俗解释（如 `checkpoint（任务检查点）`）。
- [x] 需要对照的数字（A/B 结果、覆盖率、pass 数）优先用列表或表格呈现，不埋在长句中间。
- [x] 新概念存在时已用通俗语言解释；没有新增概念时不强行编造。
- [x] “代码阅读路线”是按真实调用或数据流组织，不止说明“看什么”，还需要说明“为什么/解决了什么”。
- [x] 有“设计要点”。
- [x] “有面试价值的亮点”有可背、可独立展开的亮点。
- [x] “有面试价值的亮点”只讲能在面试中拿得出手的、能让面试官认可能力的，禁止强行凑数。
- [x] 追问优先围绕亮点展开，没有强行凑数的低价值问题和回答。
- [x] “验证与下一步”只引用 notes 中的真实验证快照。
- [x] 复制命令安全、可重复，并标明必要前置条件。
- [x] 模块记录的各个小节的文本都用 `**...**` 加粗标出服务于扫读抓重点的关键词或关键短句。

检查结果：M45 新章节已完整回读；5 个一级工作点均按“独立结论 + 分主题 bullets”组织，数字使用验证表，边界与 AI_CONTEXT/Phase 4B 档案一致。第一次读者自检后补写了 `top_k`、business/basic Evidence、API、provider attempt、runner/raw response/token usage、adapter/loader、builder、tamper 和 Pipeline 等术语的就地解释；没有修订技术事实。

本轮范围复核：`finish-docs` 只修改 `docs/dev-log.md` 与本 notes，没有修改 `AI_CONTEXT.md`、`CHANGELOG_INDEX.md`、`change-history/`、代码、测试或 Eval 工件。
