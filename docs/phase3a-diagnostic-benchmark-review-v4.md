# Phase 3A Diagnostic Benchmark Proposal v4 — Review

> 审查对象：[phase3a-diagnostic-benchmark-proposal-v4.md](phase3a-diagnostic-benchmark-proposal-v4.md)
> 审查依据：[AI_CONTEXT.md](AI_CONTEXT.md)、[phase3a-plan.md](phase3a-plan.md)
> 审查日期：2026-07-23

## 总体评价

v4 是一份质量很高的 proposal。三层结构清晰、能力维度映射完整、YAML 示例具体可落地、improvement 分类有说服力、golden path 和 pseudocode 都是好的补充。相比 v3，v4 在 `pipeline_mode`、`source_case_id`、`expected_tables_alternatives`、`accept_paths`、`chart_decision` 等边界的处理明显更成熟。

但仍有可优化空间，以下按优先级列出。

---

## P0 — 建议落地前必修（影响实现正确性或 M12 报告可信度）

### 1. 32 条 benchmark 中 16 条 challenge 的重复维护 drift 风险

v4 建议"独立维护 benchmark YAML 中的 16 条 challenge + 用 `source_case_id + --check-consistency` 防 drift"。这是一个**事后检测**方案——等到跑一致性检查时发现 drift，还是要回头修。

**问题**：同一道题（如 `db_core_001`）的 `question`、`expected_tables`、`expected_sql` 同时存在于两个 YAML 文件中。任何一方修改（例如修 expected_columns）都会导致另一方过期，`--check-consistency` 能发现但不能解决。

**建议方案**：benchmark YAML 只维护**新增的 16 条** capability-focused case，runner 通过参数组合拼出 32 条：

```bash
# 跑完整 32 条 diagnostic benchmark
python -m eval.run_eval \
  --cases eval/cases/database-upgrade-challenge.yaml \
  --extra-cases eval/cases/phase3a-diagnostic-benchmark.yaml \
  --report eval/reports/phase3a-diagnostic-baseline.md
```

这比物理复制 16 条更低维护成本，且没有 drift 问题。如果一定要独立文件，至少用 CI 级别的 `diff` 校验而非"建议运行"级别的 `--check-consistency`。

### 2. 能力覆盖矩阵中的数字多处不一致

v4 中有三组数字需要对齐：

| 位置 | schema_retrieval | join_path | query_plan | trace_steps |
|---|---|---|---|---|
| 能力覆盖矩阵表（行数） | 14 | 12 | 15 | 6 |
| M12 报告示例 Capability Summary | 12/15 pass | 8/11 pass | 10/15 pass | 6/6 complete |
| A 部分 16 条继承 challenge 的 capability 分配 | 粗略估算约 10-11 条 | 约 7-8 条 | 约 8-9 条 | 约 3 条 |

第一个问题：**矩阵表的数字和 Capability Summary 示例的分母不一致**。例如 schema_retrieval 覆盖了 14 条 case，但示例写的是 "12/15"。多出来的那条是哪来的？

第二个问题更根本：**"分母"的定义需要明确**。14 条 case 中有 `phase3a_blocking=false` 的（如 `db_hard_003`、`db_schema_003`），有 `manual` 的——它们是否计入通过率分母？v4 在"困难诊断口径"段落中说了困难题不要求自动通过，但没有给出精确的计算规则。

**建议**：在 v4 中增加一段"capability 通过率计算规则"：

```text
capability 通过率分母 = 该 capability 下 phase3a_blocking=true 且 check.type != manual 的 case 数
分子 = 分母中实际通过的 case 数
non-blocking + manual case 单独列出为"诊断通过"，不计入自动通过率
矩阵表中的数字是 case 总数（含 blocking + non-blocking + manual），
Capability Summary 中的分母是 blocking 且非 manual 的 case 数
```

### 3. `pipeline_mode` 字段的 case 内默认值 vs runner 覆盖语义

v4 说"runner 可覆盖，但报告必须记录实际模式"。但新增的 16 条 capability case 全部写死了 `pipeline_mode: new_text2sql`。当首次跑 diagnostic baseline（应该用 baseline 模式）时：

- 这些 case 的 `pipeline_mode: new_text2sql` 是跳过？还是降级为 baseline？
- 如果跳过，baseline 就只有 16 条 challenge + 0 条新增 → 实际上跑不了完整的 32 条 baseline
- 如果降级，case 中的 `expected_plan`、`expected_trace_steps` 等新 pipeline 专属字段在旧链路下无法验证，会产生大量假阴性

**建议**：明确三层优先级——

```text
1. case 中的 pipeline_mode 是"推荐默认值"，不是强制执行
2. runner --pipeline-mode 参数是权威覆盖
3. 报告记录实际使用的模式（已是共识）
4. 首次 baseline 时 runner 传 --pipeline-mode baseline，
   新增 case 中仅 baseline 链路能验证的字段（如 expected_sql）
   参与评分，新 pipeline 专属字段（如 expected_trace_steps）标记为 skipped_due_to_pipeline_mode
```

---

## P1 — 建议实现中迭代修正（影响 scoring 和验收判定）

### 4. `db_hard_002` 的 blocking 标记与困难题整体硬门矛盾

`db_hard_002`（行为漏斗转化率）在表格中标记为 `phase3a_blocking: true`，且没有 `case_properties: [difficult_diagnosis]`。但 v4 在"困难诊断口径"段落中写道困难题整体硬门是"至少 1/3 自动正确，3/3 可诊断"。

**歧义**：如果 `db_hard_002` 是 blocking=true 且不是 difficult_diagnosis，那 M12 要求它必须自动通过。但它在 baseline 中就是 11/16 失败的 5 条之一（对应设备转化率题），旧链路未必稳定。

**建议**：要么给 `db_hard_002` 加上 `case_properties: [difficult_diagnosis]` 并改为 `blocking=false`，要么承认这条题难度可控、blocking=true 是合理的，并在 phase3a-plan.md 的 M12 验收门中明确它的预期通过状态。

### 5. `local_schema_prompt` case 的评分缺乏分层标准

`db_prompt_001/002/003` 的 `expected_schema_context` 包含四个维度：`must_include_tables`、`max_tables`、`must_include_columns`、`must_not_include_tables`。但 v4 没有说这四个维度是什么关系：

- 四个全部满足才 pass？
- `must_include` 是硬门、`max_tables` 和 `must_not_include` 是加分项？
- `must_not_include_tables` 中出现了无关表，扣多少？

**建议**：定义分层评分：

```text
schema_context 评分：
  block: must_include_tables 缺失 → FAIL
  block: must_include_columns 缺失 → FAIL
  warn:  max_tables 超标 → 记录但不阻塞，报告中标注 "schema_bloat"
  warn:  must_not_include_tables 中出现无关表 → 记录但不阻塞，标注 "schema_noise"
```

这样既保证了"关键信息不丢"的硬门，又不会因为召回略多就判定失败。

### 6. `chart_decision` trace step 覆盖不充分

v4 只在 `db_trace_001` 的 optional_steps 中列了 `chart_decision`，`db_trace_002` 没有。但 phase3a-plan.md M11 验收门明确"图表成功时记录 chart_decision"。两个 trace case 中只有一个覆盖，另一个多表 join path case 的图表行为没有被观测到。

**建议**：在 `db_trace_002` 的 optional_steps 中也加入 `chart_decision`。此外可以考虑新增一条专门的 chart case（如"各渠道 GMV 柱状图"），check 类型为 `chart_spec_match`，作为后续扩展。

---

## P2 — 建议 M12 后或阶段四再优化（锦上添花）

### 7. 缺少 pipeline 自身错误路径的 case

32 条 case 都假设 pipeline 能正常走到 SQL 生成/执行。没有 case 覆盖"schema_retrieval 返回空结果时 pipeline 如何降级"、"plan_validation 内部异常时 trace 是否仍然完整"。这些更适合在 M10/M11 单元测试中覆盖，但 benchmark 中加 1 条会提高 M12 报告的完整性。

**建议**：不急于加入 32 条主 benchmark，可在 M10/M11 的 pytest 中覆盖这些错误路径，M12 报告中引用单测结果作为"pipeline robustness"一节。

### 8. `quality_win` 的判定条件太主观

v4 的 improvement 计算伪代码中 `quality_win` 的判定是：

```text
if new_result.schema_context_smaller_or_trace_better_or_plan_clearer
```

这个 OR 条件在代码中难以实现。建议 M12 实现时拆成可计算的子条件：

```python
def is_quality_win(old, new):
    """旧链路通过 + 新链路通过，但新链路有可量化的质量提升"""
    score = 0
    if new.schema_table_count < old.schema_table_count:
        score += 1
    if len(new.trace_steps) >= 8 and len(old.trace_steps) < 8:
        score += 1
    if new.has_valid_plan and not old.has_valid_plan:
        score += 1
    return score >= 2  # 至少满足两个条件才计为 quality_win
```

### 9. Golden path case 的选择可以更好

v4 选了三条 golden path：`db_core_001`（GMV）、`db_multi_003 + db_plan_001`（渠道 GMV 双验证）、`db_hard_001`（递归类目）。

`db_hard_001` 的问题：它在旧链路 baseline 中已经失败（11/16 中的一条），新链路也大概率是 manual review。用一条"新旧链路都搞不定"的 case 作为 golden path demo 效果不佳。

**建议**：将 `db_hard_001` 替换为 `db_join_002`（优惠券多对多 GMV），原因：
- 多对多桥接表是 Phase 2.7 新增的数据库复杂度
- 能展示 relations.yaml → JoinPath → QueryPlan 的完整链路
- 面试讲法更好："旧链路需要 LLM 自己猜 coupon→order_coupons→orders 的 JOIN，新链路直接从 relations.yaml 约束"

最后可考虑是否单独抽一条 chart 相关的 golden path case，用以展示 `chart_decision` trace step（可选）。

---

## 我的方案建议

核心思路：**不改 v4 的主体结构，只修 P0 的三个矛盾点 + P1 的评分细化**。

### 调整一：用 runner 参数组合替代物理复制 16 条 challenge

不创建包含全部 32 条的独立 YAML。改为：

- `eval/cases/phase3a-diagnostic-benchmark.yaml`：只放**新增的 16 条** capability-focused case
- Runner 支持 `--cases` 多次传参（或 `--extra-cases`）
- 32 条 diagnostic 通过命令组合：`--cases challenge.yaml --extra-cases diagnostic-benchmark.yaml`
- `source_case_id` 仍然保留在新增 case 中，但对 challenge 中的原始 case，通过 `--check-consistency` 校验 question 一致性而非复制

### 调整二：能力覆盖矩阵增加精确的计算规则

在能力覆盖矩阵表后面增加一段计算规则说明，明确：
- 分母 = blocking=true 且 check.type != manual 的 case 数
- 分子 = 分母中实际通过的 case 数
- non-blocking / manual case 单独列出为"诊断通过"，不计入自动通过率
- Capability Summary 示例数字需要与矩阵表对齐

### 调整三：pipeline_mode 三级优先级 + baseline 降级规则

```yaml
# case 中的 pipeline_mode 含义改为"推荐默认值"
pipeline_mode: new_text2sql  # 推荐模式，runner --pipeline-mode 可覆盖
```

首次 baseline 时传 `--pipeline-mode baseline`，新增 case 中仅 baseline 可验证字段参与评分，新 pipeline 专属字段自动标记 `skipped_due_to_pipeline_mode`。

### 调整四：local_schema_prompt 评分分层

按上面 P1-5 的建议，把 `expected_schema_context` 拆成 block 级（must_include）和 warn 级（max_tables / must_not_include）。

---

## 总结

v4 的 32 条结构、能力维度、improvement 分类、YAML 字段设计和落地步骤都**不需要大改**。需要修的是 3 个 P0 矛盾（重复维护、数字不一致、pipeline_mode 语义）和 2 个 P1 评分细化（hard_002 blocking、local_schema_prompt 分层），修完后可以直接按 v4 的落地步骤执行。

下一步：如果上述建议被接受，可以在 v4 基础上生成 v5，把这些修正落地到 proposal 正文中。
