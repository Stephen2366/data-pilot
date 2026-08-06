# 阶段三C：Multi-Agent / Multi-SQL 规划上下文

> 本文件用于未来多 SQL / 多 Agent 实现参考，只有用户提出阅读本文件时才阅读本文件。本文写于 M24 结束时，可能存在过时的情况，因此仅作参考。
>
> 用途：供后续会话制定阶段三C正式计划。本文只定义推荐方向、优先级和边界，不代表具体实现已经批准。

## 1. 与 M25 的关系

当前建议明确拆分两阶段：

```text
M25
→ 只按 docs/notes/m25-planning-context.md 收口 Eval 可信度、失败归因、timeout 证据和 focused capability spike

阶段三C
→ 再研究 Multi-Agent、逻辑多步骤计划、并行 SQL 候选与真正的 Multi-SQL Plan-and-Execute
```

这样拆分的原因：

- 当前 Eval 仍有题面隐藏排序/LIMIT/时间范围、alias 白名单、重复样本和 timeout 混入能力分等问题。
- 如果在评测口径未收口前引入多 Agent / 多 SQL，即使分数变化也难判断是架构收益、更多重试、外部模型波动，还是 case/scorer 改动。
- 多 Agent 会增加模型调用量，多 SQL 会增加执行与合并风险；二者需要可信的 semantic、reliability、latency 和 cost 基线。
- M25 完成后，阶段三C可以直接使用更干净的失败集和评分视图，不再靠总分猜架构是否有效。

M25 原则上**不实现运行时 Multi-Agent 或 Multi-SQL Executor**。若 M25 发现相关证据，只记录为阶段三C输入，不顺手扩大范围。

## 2. 当前代码已经预留什么

`QueryPlan.steps` 已经是 `list[QueryPlanStep]`，单个 step 包含：

- `step_id`
- `step_index`
- `step_type = sql_query / analysis / rag_lookup`
- `depends_on`
- tables / columns / metrics / filters / joins
- aggregations / group_by / order_by / limit
- output_columns / output_expressions

这说明数据结构从一开始就为 Plan-and-Execute / Hybrid 留了接口。

但当前真实能力仍是**单 SQL**：

- `validate_query_plan()` 遇到多个 `sql_query` step 会返回 `unsupported_multi_step_plan`。
- pipeline 通过 `_first_sql_step()` 只取第一个 SQL step。
- `analysis` / `rag_lookup` 只是类型预留，没有真正的 step executor、状态传递和结果合并。
- 当前没有 DAG 校验、typed intermediate result、跨 step 参数绑定、失败恢复或一致性快照。

所以阶段三C不能只删除 `unsupported_multi_step_plan`。`steps` 是接口地基，不是已经完成的多 SQL 引擎。

## 3. 先区分三种能力

### 3.1 逻辑多步骤，最终单 SQL

让 QueryPlan 把复杂问题拆成多个可验证的业务步骤，最终仍生成一条包含 CTE/子查询的 SQL。

示例：商品退款率

```text
筛选六月成交订单
→ 确定订单明细商品
→ 整单退款回退 refunds.product_id
→ 分别计算成交订单数和退款数
→ 计算退款率并排序
→ 生成一条 CTE SQL
```

优点：保留一次数据库执行和统一口径，同时让计划更容易审查。它不是 Multi-SQL，但应成为阶段三C最先验证的能力。

### 3.2 Multi-Agent / 多角色 LLM 协作

由多个职责明确的角色完成规划、生成、批评或修复，例如：

```text
Planner
→ Plan Critic
→ SQL Generator
→ Guard + Fidelity
→ Repair Agent（最多一次）
```

重点是**受控角色分工**，不是让多个 Agent 自由讨论。确定性 Guard/Fidelity 继续做最终硬门。

### 3.3 真正的 Multi-SQL Plan-and-Execute

一个 QueryPlan 中存在多条可执行 SQL，后续 step 消费前面结果：

```text
SQL step_1
→ SQL step_2
→ analysis step
→ final answer
```

它适合两个时间段对比、多个独立数据源、SQL+RAG Hybrid 等场景，但会引入一致性、结果传递、重试和合并风险。

## 4. 总体设计原则

1. **Agent 数量不是目标**：只有某类失败能被明确角色解决时才增加一次模型调用。
2. **确定性规则优先**：SQL Guard、AST fidelity、projection、result contract 不交给 LLM 替代。
3. **先逻辑分解，再多次执行**：能用一条 CTE SQL完成的，不拆成多次数据库查询。
4. **有界调用**：默认最多一次 plan critique、一次 repair、两个并行候选，禁止无限自我反思。
5. **每一步都可观测**：prompt length、attempt、latency、token/cost、输入输出摘要、失败原因必须进入 trace。
6. **每条 SQL 都独立过安全门**：Multi-SQL 不能共享一次 Guard 后批量放行。
7. **不保存原始 CoT**：step 只保存 purpose、结构化输入输出和验证证据。
8. **A/B 先于默认切换**：任何新架构必须和当前单计划/单生成链路做同合同重复对照。

## 5. P0：先做高收益、低失控的受控协作

P0 目标：验证“多一步审查或修复”能否提高复杂 SQL 正确率，而不是直接建设完整多 Agent 平台。

### P0-1：逻辑多步骤计划 → 单条 SQL

优先 case：

- `db_core_002`：商品退款率
- `db_multi_002`：一级类目销售额
- `db_hard_001`：指定类目及子类目 GMV

建议动作：

- 让计划显式描述筛选、归因、聚合、递归/层级和最终投影。
- 先设计逻辑 step 输出合同，再编译/提示生成一条 CTE SQL。
- 为 CTE/derived scope 做 fidelity 离线正反例 spike；只放行有证据的 scope lineage。
- 不允许因为支持 CTE 而整体放宽 M24 的 `indeterminate` 边界。

### P0-2：Plan Critic

Planner 生成计划后，增加一次有明确 rubric 的审查：

- 用户题面中的时间、列、排序、LIMIT 是否完整进入计划；
- metric、分子分母和过滤口径是否匹配 DomainSchema；
- output_columns 是否最小且足够；
- 是否错误选择宽表、兼容字段或非规范类目路径；
- 是否需要 CTE/递归，而不是简单 `level=1` 过滤。

Critic 只能输出结构化问题和修订建议，不直接绕过 validator，也不执行 SQL。

### P0-3：Fidelity 失败后的单次 Repair

当前合同失败后直接阻断。阶段三C可以实验：

```text
candidate SQL
→ SQL Guard
→ AST fidelity failed
→ 将 reason code + planned/observed evidence 交给 Repair Agent
→ 重新生成一次
→ 再次 Guard + Fidelity
```

约束：

- 最多 repair 一次。
- Repair 不能修改 QueryPlan、DomainSchema 或安全策略。
- Guard failure 不进入普通语义 repair。
- repair 前后 SQL、reason code、latency 和最终结果全部写 trace。
- Repair 仍失败就结构化阻断，不继续循环。

### P0-4：受控 A/B

至少比较：

| 组 | 架构 |
|---|---|
| A | 当前 Planner → Generator |
| B | Planner → Plan Critic → Generator |
| C | Planner → Generator → Fidelity failure Repair |
| D | Planner → Plan Critic → Generator → bounded Repair |

主要指标：

- semantic answer pass rate
- provider timeout/error rate
- plan invalid rate
- fidelity first-pass / repaired-pass / repair-failed
- false repair：原本正确的候选是否被改坏
- 平均 LLM 调用次数
- p50/p95 latency
- token/cost

P0 验收重点不是总分最高，而是证明新增调用解决了对应失败，且没有让 timeout、成本或安全风险失控。

## 6. P1：并行候选与真正的 Multi-SQL Executor

P1 只在 P0 证明受控协作有收益后进入。

### P1-1：双 SQL Candidate + 硬合同筛选

同一个已验证 QueryPlan 并行生成两个候选：

```text
QueryPlan
├─ Candidate A
└─ Candidate B
      ↓
Guard + Fidelity + execution checks
      ↓
Selector
```

Selector 优先使用确定性证据：

- Guard 是否通过
- Fidelity 是否通过
- output contract 是否通过
- SQL 是否可执行
- 是否使用规范 metric/join path

只有两个候选都通过硬合同但需要比较语义质量时，才允许使用独立 Judge/critic；不能让 Judge 放行 Guard 或 Fidelity 失败的 SQL。

需要记录 `pass@1`、`pass@2`、候选分歧率和双倍调用成本，避免只展示最终最优结果。

### P1-2：Multi-SQL Plan-and-Execute 最小闭环

只选真正需要多次执行的场景，不用现有单 SQL case 强行证明多 SQL。

推荐首批场景：

- 两个时间窗口指标对比；
- 两个相互独立查询的差异分析；
- SQL 结果与 RAG 文档共同参与最终回答；
- 单条 SQL 无法安全表达的跨工具任务。

最小执行器至少需要：

1. **DAG validator**
   - step_id 唯一
   - depends_on 必须存在
   - 无循环依赖
   - 拓扑顺序稳定
2. **Typed result registry**
   - 每一步声明输出 schema
   - 后续 step 只能引用已声明字段
   - 禁止把整份任意 JSON 直接塞入下一步 prompt
3. **Step executor registry**
   - `sql_query`
   - `analysis`
   - 后续可加 `rag_lookup`
4. **逐步安全与预算**
   - 每条 SQL 独立 Guard/Fidelity
   - 最大 SQL step 数建议首版为 3
   - 中间结果行数/字节上限
   - 总延迟、调用次数和 token budget
5. **失败语义**
   - retryable / non-retryable
   - partial result 是否允许继续
   - fallback 与 blocked reason
6. **一致性**
   - 多 SQL 是否使用同一只读事务/一致性快照
   - 防止前后两次查询看到不同数据版本
7. **最终合并合同**
   - analysis step 如何对齐 key
   - 空结果、重复 key、单位和时间范围如何处理
   - 最终 output projection 由谁负责

### P1-3：Trace / Eval 扩展

每个 step 独立 span，并保留：

- parent/depends_on
- input binding 摘要
- output schema/row count
- Guard/Fidelity status
- retry/repair history
- latency/token/cost
- final synthesis 使用了哪些 step

Eval 应新增真正的多步 case，而不是把现有单 SQL题拆开后宣称提升。报告至少区分：plan success、step success、merge correctness、final answer correctness。

## 7. P2：Hybrid 与更完整的 Agent Orchestration

P2 面向阶段三后续扩展，不作为首轮必要项。

### P2-1：SQL + RAG Hybrid

利用已有 `step_type=rag_lookup`：

```text
SQL：查询退款率最高的商品
RAG：检索对应退款政策/客服规则
Analysis：结合数据和规则生成解释
```

需要增加 citation、retrieval coverage、faithfulness 和跨工具证据绑定，不能只验证 SQL。

### P2-2：领域 Specialist Agents

只有失败证据足够集中时才拆角色，例如：

- Metric/Business Semantics Agent
- Join/Schema Agent
- SQL Agent
- Result Analyst

不建议为每个表或每种 SQL 子句各建一个 Agent。角色边界应按失败责任划分，而不是按技术名词凑数量。

### P2-3：正式编排框架

当步骤分支、重试、并发和状态持久化明显增多后，再评估 LangGraph 或其他 orchestration runtime。

首轮 P0/P1 可以继续使用清晰的 Python module/interface 实现，避免为了“多 Agent”先引入框架复杂度。是否切编排框架应由以下需求触发：

- 动态分支
- 并行候选
- 可恢复 checkpoint
- human-in-the-loop
- 长任务状态持久化
- SQL/RAG/工具混合路由

## 8. 建议的阶段三C门禁

### P0 门禁

- M25 新合同和评分视图已经冻结。
- Plan Critic/Repair 的收益能落到明确 case 和 failure subtype。
- Guard/Fidelity 无回退，false repair 有独立统计。
- timeout、延迟和成本没有被总分掩盖。
- CTE/derived scope 只按已验证正反例扩展。

### P1 门禁

- 双候选报告同时展示 pass@1/pass@2 和额外成本。
- Multi-SQL DAG、typed result、预算、失败恢复和一致性策略齐全。
- 至少有专门的多步 eval case；不是把单 SQL题机械拆分。
- 任一 SQL step 都不能绕过 Guard/Fidelity。
- 中间结果与最终合并可通过 trace 复演。

### P2 门禁

- Hybrid 有独立的 retrieval/citation/faithfulness 合同。
- Specialist Agent 的存在由失败证据支持。
- 引入编排框架解决了真实状态管理问题，而不是只增加项目名词。

## 9. 明确暂不做

- 不在 M25 中顺手实现 Multi-Agent/Multi-SQL。
- 不直接删除 `unsupported_multi_step_plan`。
- 不让多个 Agent 自由循环讨论。
- 不使用 LLM Judge 替代 SQL Guard、AST fidelity 或 reference result。
- 不把能由一条 CTE SQL完成的问题强制拆成多次查询。
- 不因为 pass@2 更高就隐藏双倍调用成本和 timeout 风险。
- 不在没有 typed result 与一致性设计时传递多 SQL 中间结果。
- 不先上 LangGraph 再寻找使用场景。

## 10. 后续会话制定正式计划时应回答

1. 阶段三C首批目标是逻辑多步骤、Plan Critic、Repair、双候选，还是 Multi-SQL？
2. 哪些 M25 失败证据证明新增角色确有必要？
3. 哪些问题应该保持单 SQL/CTE，哪些问题确实需要多次执行？
4. 每增加一次 LLM 调用，预期解决哪个 failure subtype？
5. timeout、latency、token 和费用预算是多少？
6. Critic/Repair/Selector 的输出合同是什么？
7. Multi-SQL 如何保证依赖、类型、安全、一致性和最终合并正确？
8. 新架构相对当前 baseline 的 A/B 和回退条件是什么？
9. 什么时候才值得引入 LangGraph/持久化状态？

## 11. 推荐阅读

- `docs/notes/m25-planning-context.md`
- `docs/notes/m24-notes.md`
- `engine/nl2sql/planner.py`
- `engine/nl2sql/pipeline.py`
- `engine/nl2sql/fidelity_contract.py`
- `eval/reports/m24-ab-execution-manifest.md`
- `docs/state/eval-baselines.md`
- `docs/state/runbook.md`
- `docs/phase3b-langfuse-plan-v6.md`

