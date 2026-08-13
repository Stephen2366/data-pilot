# M30 可信知识原件、Catalog Prototype 与 Text2SQL 隔离实施记录

> 状态：开发、`finish-module` 与 `finish-docs` 均已完成，等待用户人工检查 / `accept-module`。

## 1. Implementation Checklist

### 开工与调查（必须先完成）

- [x] 完整阅读 `AGENTS.md`、`m30-plan.md`、`AI_CONTEXT.md` 及其必读 state 文档。
- [x] 阅读 Phase 4 roadmap/reference 的当前里程碑、跨阶段不变量和 G2/G3 边界。
- [x] 定点复核 `WREN-INDEX`、`WREN-WATCH`、`DATAAGENT-REPLACE` 指定源码。
- [x] 检查工作区状态；确认只有已批准的 `m30-plan.md` 是开工前未跟踪文件。
- [x] 完成 `knowledge_docs` 反向影响清单和 10 条 seed disposition。

### 权威原件与 Catalog（必须完成）

- [x] 将政策/规则正文迁入可审查的 Markdown authority source。
- [x] 由 `metrics.yaml` 派生指标说明，消除指标正文第二事实源。
- [x] 实现最小且失败关闭的 staged catalog builder/interface。
- [x] 固化 document/revision/content/anchor/status/ACL/data class/use/authority identity。
- [x] 验证相同语义输入可重现 identity，语义变化可检测，遍历或 YAML key 顺序噪声不漂移。
- [x] 验证非法字段、缺字段、重复 identity、未知枚举和 inactive/revoked usable 泄漏均失败关闭。

### Text2SQL 隔离（必须完成）

- [x] 区分 14 张物理表与 Text2SQL queryable schema universe。
- [x] 从 Domain Schema、Schema Retrieval alias/prompt 和所有 SQL allowlist 移除 `knowledge_docs`。
- [x] 保持 M27 `knowledge_doc_order_attribution_rejection -> unsupported_relation` 合同。
- [x] 增加 planner/手工 SQL 反绕过与 queryable universe 一致性测试。
- [x] 计算并记录新的 Schema docs count/hash/runtime identity。

### 决策门与收工（按顺序）

- [x] 完成三种 G2 方案的 prototype/consumer/迁移/回滚/安全证据。
- [x] 在任何数据库 migration、seed 投影改造或物理删除前，向用户列出做法、影响、适用条件、风险和建议并等待确认。
- [x] 按 G2 选择完成条件分支；未触发的分支不进入验收分母。
- [x] 依次运行聚焦测试、M27 静态校验、deterministic 回归、全仓 pytest 和 `git diff --check`。
- [x] 调用 `finish-module` 完成注释扫描、验证快照和 notes 固化。
- [x] 调用 `finish-docs` 更新 changelog、AI_CONTEXT 和 dev-log。

## 2. 开工事实与边界

- Git 基线：`bc79ad1 M29 Phase 4 入口盘点与合同冻结`。
- 开工前工作区：仅 `docs/notes/m30-plan.md` 未跟踪；没有覆盖用户已有代码改动。
- 当前物理事实：数据库仍有 14 张表，`knowledge_docs` 有 10 条 seed；G2 前不迁移、不删表、不改写历史 migration。
- 当前 Schema corpus：195 docs，hash `8a8b6626a4cbec6197d9625ec12d5d40668025476f823eaa9458647cecd8d41a`；这是隔离前事实，完成后必须重新计算。
- 运行边界：本模块只产出 `staged` catalog，不接生成器、不建 active index、不跑真实 LLM/embedding/Milvus/LangFuse。

## 3. 参考源码复核与取舍

- 借鉴 `WREN-INDEX`：Markdown/配置原件与派生查询结构分离，删除或重建派生物不能伤害原件。
- 借鉴 `WREN-WATCH`：只有重建成功才能推进已观察状态；DataPilot prototype 用规范化正文 identity，不采用只看路径、大小、mtime 的 fingerprint。
- 借鉴 `DATAAGENT-REPLACE`：替换需要明确 identity 和失败清理；不照搬先增后删为“原子发布”，M30 也不实现在线切换或回滚承诺。
- DataPilot 自身补足：用纯函数、不可变结果、有限错误码和全量校验实现 staged 构建失败关闭；Text2SQL 隔离是本项目安全合同，不从参考项目的 collection/filter 推导。

## 4. 实施中事实、决策与问题

### 4.1 已确认的实现原则

- Catalog 对外保持一个深接口：接收 authority source 与 build recipe，返回完整 immutable staged catalog 或整体失败；不暴露半成品步骤。
- content identity 只描述规范化知识语义；authority reference、revision、稳定 anchor、ACL/data class/use 等完整定位和治理事实进入 corpus manifest identity。mtime、目录遍历顺序和 YAML key 顺序不进入 identity。
- 物理表存在与 SQL 可查询性分开表达，并用测试约束 Domain Schema 与 SQL Guard 的 queryable universe 不漂移。

### 4.2 收工前待办状态

- G2 consumer matrix、用户选择和落地证据已经完成。
- 代码、测试、踩坑、修正、验证快照和 `finish-docs` 技术档案同步均已完成。

### 4.3 旧 seed → authority/revision → staged entry 追踪

| 旧 seed | 处理 | 新 authority / staged entry | 说明 |
|---|---|---|---|
| `refund_policy_basic` | 审查改写 | `refund-policy-basic.md` / 同 key / `2026-08-13-r1` | 只保留总则，显式指向质量专项规则 |
| `refund_policy_quality` | 审查改写 | `refund-policy-quality.md` / 同 key / `2026-08-13-r1` | 补充适用范围、必要证据与冲突优先级 |
| `shipping_delay_rule` | 审查改写 | `shipping-delay-rule.md` / 同 key / `2026-08-13-r1` | 区分出库与轨迹延迟；具体订单状态留给实时事实 |
| `invoice_rule` | 审查改写 | `invoice-rule.md` / 同 key / `2026-08-13-r1` | 明确实付金额与实时订单边界 |
| `vip_service_rule` | 审查改写 | `vip-service-rule.md` / 同 key / `2026-08-13-r1` | 只定义资格口径，不固化客户资格结果 |
| `sensitive_data_policy` | 安全纠偏 | `sensitive-data-policy.md` / 同 key / `2026-08-13-r1` | 明确 admin 也不能经自然语言 Text2SQL 明文直出 |
| `demo_user_scope` | 审查改写 | `demo-user-scope.md` / 同 key / `2026-08-13-r1` | 不把文档当作扩大 SQL/文档权限的凭据 |
| `gmv_metric_note` | 取消正文副本 | `metrics.yaml#metrics.gmv` / 同 key | 内容由 metric key 确定性派生 |
| `coupon_rule` | 拆解并取消正文副本 | `metrics.yaml#metrics.coupon_order_count` 与 `.coupon_usage_rate` | 旧条目混合计数和比率，拆成两个可追溯 entry，因此 catalog 总数为 11 |
| `behavior_funnel_rule` | 取消正文副本 | `metrics.yaml#metrics.add_to_pay_conversion_rate` / 同 key | 内容由 metric key 确定性派生 |

### 4.4 Prototype 与隔离证据（第一次聚焦验证）

- Staged catalog：11 entries / 11 usable；7 个 `policy_markdown`，4 个 `metric_projection`。
- 首次打印的 corpus/build identity 随后因修正 content identity 构成而作废，正式值待下一轮重算并写入收工快照。
- `tests/test_m30_knowledge_catalog.py` 首轮发现 duplicate content 测试未触发：原因是实现注释说 anchor 不进入 content identity，但代码仍包含 anchor。已立即移除该字段，保留“内容语义 identity”和“manifest 定位 identity”的职责分离；第二轮 `10 passed`。
- Text2SQL queryable tables：13；物理表仍为 14，二者不再混称。
- 新 Schema corpus：186 docs，hash `6b67606d782ec834efa2ffcdb94b3cbb8af148223f5a92a176b64f849e2e418d`。

### 4.5 `knowledge_docs` 反向扫描分类

- **authority 草稿**：`scripts/seed_data.py::_KB_CONTENTS` 与 10 行 seed。G2 前保留为待处置 legacy 数据；不得再作为新 catalog authority。
- **physical/legacy projection**：ORM model、`app.db.base` 注册、Alembic、M1 物理表测试和 seed count。它们证明 14 张物理表仍存在，不等于 Text2SQL 可查询。
- **Text2SQL 暴露**：`schema_desc/knowledge_docs.md`、Schema Retrieval alias、RBAC 已在本轮移除；prompt 随 DomainSchema 同步隔离。
- **当前合同测试**：M30 新测试保留字符串作为反绕过输入；M27 canonical `knowledge_doc_order_attribution_rejection` 保留为确定性 `unsupported_relation`。
- **只读历史/诊断**：`eval/cases/phase3a-diagnostic-benchmark.yaml`、`eval/cases_plan.md`、旧 reports/artifacts 与 changelog 历史段落不改写；它们继续由旧 runtime identity 解释。
- **活跃 state**：`AI_CONTEXT.md`、`database-current-state.md` 和 `schema-retrieval-milvus-embedding.md` 已同步当前事实；历史 baseline 的 195/hash 保留。

### 4.6 G2 前 prototype 与 consumer matrix

- 正式重算 staged catalog：11 entries / 11 usable，corpus identity `abdc9aed2d4ee118e0b93890dad5b3b5b80c0b163f997ec275d1c92b3e99a858`，build identity `c5e6cf17b95573ee1deeb5b7f40620f53724c362e2f5f9be61214be2bbbf23a6`。
- 活跃代码扫描未发现 API、Tool、生成器、检索器或 demo 查询 `KnowledgeDoc`。除 seed 外，只剩 ORM 聚合注册；测试只检查物理模型/表存在。
- 聚焦回归：`57 passed, 1 warning`；warning 是既有 Starlette/httpx 弃用提示。
- G2 前保持不动：`scripts/seed_data.py::_KB_CONTENTS`、`EXPECTED_SEED_COUNTS["knowledge_docs"] = 10`、ORM、Alembic 和物理表。
- G2 建议仍为方案 B：source-backed runtime catalog + 隔离 legacy 表；理由是当前没有数据库 runtime consumer，多实例共享、运营后台和在线发布需求也尚不存在。

### 4.7 G2 用户决策与落地

- 用户于 2026-08-13 明确选择 **方案 B：source-backed runtime catalog + 暂留隔离 legacy 表**。
- 已删除 `scripts/seed_data.py::_KB_CONTENTS` 这一可独立编辑的正文副本；`_build_knowledge_docs()` 改为调用同一 staged catalog builder 生成兼容行。
- 旧表字段不足以保存 revision、authority、identity、完整 ACL 等合同，因此该投影明确是有损 legacy storage，任何后续调用者不得从它恢复正式 catalog 或授权判断。
- `coupon_rule` 拆为两个 metric projection 后，legacy seed 从 10 行变为 11 行；这是 source-backed 派生数量变化，不是新增手写知识。
- 未触发 Alembic migration、ORM 大改或物理删除；数据库仍有 14 张物理表。
- 验证踩坑：第一次 G2 后聚焦命令误写了不存在的 `tests/test_m2_seed_data.py`，pytest 在收集前退出、没有测试失败；扫描后确认真实 seed 覆盖位于 `test_m1_models.py` 与 `test_database_upgrade.py`，随后使用正确路径重跑。
- 全仓首轮在约 8 分 44 秒完成为 `230 passed / 3 skipped / 1 failed`：`test_challenge_and_diagnostic_schema_capabilities_have_recall_summary` 仍要求历史 `db_plan_003.expected_tables` 的 `knowledge_docs` 被当前 Schema 召回。修正测试只对当前 queryable DomainSchema 中的 expected tables 计算漏召回；不改只读 diagnostic fixture，也不放宽 `unsupported_relation` 产品拒绝。

## 5. 模块最终状态

- M30 必须项已完成；G2 选择 B 的 seed 条件分支已完成。
- Catalog lifecycle 仍为 `staged`，没有 active pointer、正式 Knowledge index、生成器接线或 G3 声明。
- 14 张物理表继续存在；Text2SQL queryable universe 为 13 张表，所有角色均不能查询 `knowledge_docs`。
- Alembic migration、物理删表、Knowledge Tool、Evidence/citation、正式 ACL/outbound 与远程调用均未触发。

## 6. Implementation Checklist 摘要

- 已完成：7 份政策/规则 authority、4 份 metric-derived entry、确定性 catalog/manifest、失败关闭、legacy seed 派生、Text2SQL 全路径隔离和回归迁移。
- 建议项已完成：`StagedCatalog.summary()` / `manifest()` 提供薄只读检查入口和确定性 diff 投影；notes 保存旧 seed 追踪表。
- 条件项状态：G2 选择 B，仅触发 seed 派生；没有触发数据库 migration、ORM 大改、物理删除、active 发布、长文切分或远程 Eval。

## 7. 关键决策与取舍

1. **内容 identity 与定位 identity 分层**：content hash 不混入 key/revision/anchor，便于发现同内容重复；corpus identity 包含完整 manifest，任何定位、治理或正文语义变化仍会改变 corpus。
2. **一个深 builder，不暴露半成品**：调用者只调用 `build_staged_catalog()`；解析、metric 派生、校验、排序和 identity 全由模块内部完成，失败只返回有限 reason code。
3. **G2 方案 B**：source-backed catalog 是正式读取方向；旧物理表只作为有损 legacy storage 暂留。当前无数据库消费者，不提前冻结 projection schema。
4. **历史 fixture 不改写**：旧 Phase 3A diagnostic 可以记录当时的 `knowledge_docs` 预期，但当前召回测试只要求 queryable tables；产品语义继续由 `unsupported_relation` 验证。

## 8. 验证快照

- G2 后 seed/数据库/核心合同聚焦回归：`70 passed, 1 warning`。
- 受影响测试修正后聚焦回归：`37 passed, 1 warning`。
- 全仓最终：`231 passed, 3 skipped, 1 warning`，耗时约 8 分 25 秒；warning 为既有 Starlette/httpx 弃用提示。
- M27 canonical catalog：28 scenarios 可加载；知识文档与订单归因问题仍得到 `unsupported_relation`。
- Text2SQL：13 queryable tables；Schema corpus 186 docs，hash `6b67606d782ec834efa2ffcdb94b3cbb8af148223f5a92a176b64f849e2e418d`。
- Staged catalog：11 entries；corpus identity `abdc9aed2d4ee118e0b93890dad5b3b5b80c0b163f997ec275d1c92b3e99a858`；build identity `c5e6cf17b95573ee1deeb5b7f40620f53724c362e2f5f9be61214be2bbbf23a6`。
- 收工后注释聚焦回归：`37 passed, 1 warning`；`compileall` 与 `git diff --check` 通过。
- MySQL 条件验收：只读确认 `127.0.0.1:3306/datapilot_dev`；Alembic `20260722_0003 (head)`，`alembic check` 无新操作；执行确定性 `seed_data --reset` 后 14 表计数全匹配，`knowledge_docs=11`，全部固定业务事实保持预期。
- 未运行真实 LLM、embedding、Milvus、LangFuse 或远程 provider；它们不在本模块验收分母。

## 9. 注释扫描小结

- 第 1 遍：补齐新增 package、Catalog 类型、builder、seed projection 和测试 helper 的职责说明。
- 第 2 遍：为 YAML 解析、closed-world metadata/ACL 校验、content identity、全局冲突检查和三步构建流程补充解释。
- 第 3 遍：在 staged/active、source/derived、physical/queryable、正式 ACL/legacy audience 等关键边界处增加或核对 ★ 注释。
- 第 4 遍：保留“深模块、失败关闭、identity 分层、双重安全门、历史 runtime identity”这些适合学习和面试复盘的设计说明；未添加逐行翻译式噪音注释。

## 10. 风险、遗留与后续

- legacy `knowledge_docs` 是有损投影，不能表达 revision、authority、content identity、完整 ACL 或 catalog build；不得成为新调用者的数据源。
- `status=active` 当前只表示 authority revision 可进入 staged usable set，不表示通过 G3 正式发布；后续发布模块必须建立独立 active identity/pointer。
- 当前短文不需要 chunk/parent-child/向量索引。只有后续真实 corpus 或 P2 failures 证明需要时再引入。
- 下一能力切片应继续 P1：Evidence/citation、trusted caller、文档 ACL/outbound 与安全发布闭环；M30 不替它提前确定接口细节。

## 11. finish-docs 二次补齐记录

- 首次写完三份文档后错误地跳过 `finish-docs` 硬性交付门自检，并提前向用户宣称完成。
- 二次补齐 `dev-log` 的 `**简述**`、工作总览、每个一级工作点的原问题/机制/取舍/证据/未证明边界、职责式代码阅读路线、调用链、分层面试追问、可复制命令和本地体验说明。
- `AI_CONTEXT.md` 当前状态修正为 skill 要求的 “M30 未验收（待 `accept-module`）”；changelog 补齐基线 diff/status 范围依据、G2 三方案风险/建议/最终选择，并在 M29 旧风险结论处添加 `⚠️ 注`。
- 过程偏差：MySQL 条件验证本应在 `finish-module` 完成后再进入 `finish-docs`，实际是在首次 docs 写作中发现缺口后才补跑；证据随后先固化到本 notes，再用于三份文档。该顺序错误不能被结果通过掩盖。
- 已重新回读 M30 dev-log、AI_CONTEXT 当前区、changelog M30/M29 相关区；逐项执行 dev-log 与三文档交付门检查，全部为 True，`git diff --check` 通过。未在二次文档自检阶段新增功能验证。
