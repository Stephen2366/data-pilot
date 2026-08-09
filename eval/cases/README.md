# eval/cases 用例集说明

> **当前落地口径是 M27 canonical Scenario catalog**。一条业务问题只在 `eval/cases/catalog/scenarios.yaml` 定义一次；结果、Context、Plan、Trace、安全等检查作为它的 typed assertions 共享同一份执行证据。旧 formal / challenge / diagnostic YAML 保留为只读历史证据，不能用当前 `eval.run_eval` CLI 生成新的 M27 分数。

## M27 当前目录与维护规则

```text
eval/cases/
  catalog/
    scenarios.yaml             # 28 个 canonical Scenario 的唯一事实源
    selectors/
      smoke.yaml               # 轻量链路选择，不复制题面
      reliability.yaml         # 复用 Scenario + 明确 replicate protocol
      database-exception.yaml  # 选择异常/边界 Scenario
  *.yaml                       # formal/challenge/diagnostic 等 legacy 输入，只读保留
```

### Scenario、assertion 与 selector

- **Scenario**：一个唯一的业务问题，例如“六月各渠道 GMV 排名”。它声明题面、分类（Core / Stress / Manual Lab）和多个 assertion。
- **Assertion**：同一次答题的一个判卷规则。M27 支持 `result_match`、`output_contract`、`schema_context`、`query_plan`、`trace_complete`、`safety_block`、`expected_rejection`、`join_path`、`metric_mapping`；未知 kind 会在加载 catalog 时失败，禁止默认通过。
- **Selector**：从 canonical Scenario 中选题并定义 protocol / gate policy。Smoke、Reliability、Database Exception 不复制 YAML 正文，也不创建新的业务问题分母。

### 加 case / 改合同前的规则

- 新业务问题只加到 `catalog/scenarios.yaml`；同题的多个检查必须增加 assertion，不能复制成多条 case。
- 改题面、reference SQL、分母、Gate、selector、长期 artifact 或真实 LLM 基线范围前，先按 M27 确认门整理方案并取得用户确认。
- `result_match` 的候选和 reference SQL 必须共享同一 RunEnvironment snapshot；高风险口径需要 SQLite counterfactual，不能只依赖当前 seed 恰好通过。
- 旧 YAML、旧 report、trace、triage 和 M26 audit 只能读取/追溯；不要移动、重算或改写历史分数。

### 怎么运行

M27 CLI、真实 LLM 授权边界、artifact 路径和命令见 [docs/state/runbook.md](../../docs/state/runbook.md)。分母、Gate、首次真实基线和旧数字隔离见 [docs/state/eval-baselines.md](../../docs/state/eval-baselines.md)。

## Legacy：formal / challenge / diagnostic 三层用例

> 以下内容描述 M27 前的历史结构，只为理解冻结 YAML、旧 report 和 audit 输入保留；不再是当前加 case 或运行 eval 的规则。

当前三层不是三套完全独立的题，而是逐层扩展：

```text
formal 10
  ↓ 被包含
challenge 16 = formal 10 + challenge extra 6
  ↓ 再合并
diagnostic 32 = challenge 16 + diagnostic extra 16
```

通俗说：

- **formal** 是主硬门：核心能力不能退。
- **challenge** 是 formal 的加难版：多看 6 条更复杂的数据库问题。
- **diagnostic** 是能力体检：在 challenge 基础上再加 16 条专项题，用来定位边界，不追满分。

## Legacy 文件清单

| 文件 | 条数 | 定位 |
|---|---|---|
| `smoke.yaml` | 6 | **主链路冒烟门**：2 简单 + 2 聚合 + 1 多表 join + 1 安全拦截；每次回归先跑它，覆盖 API 契约 / Trace / 图表 / 安全 |
| `phase3a-regression.yaml` | 10 | **formal 主硬门**：Phase 3A 起验收与回归对照，不允许低于当前基线 |
| `database-upgrade-challenge.yaml` | 16 | **challenge superset**：包含全部 10 条 formal 问题 + 额外 6 条扩展数据库复杂度；轻量诊断门，每模块陪跑 |
| `phase3a-diagnostic-benchmark.yaml` | 16 | **diagnostic extra**：只维护新增 16 条 capability-focused case，不复制 challenge（32 条由 runner 合并） |

## Legacy 三层结构

- **formal（10）**：主硬门，验收与回归对照用
- **challenge（16）**：superset（含 formal 10 + 额外 6），日常陪跑诊断
- **diagnostic（32）**：16 challenge + 16 extra（`--cases + --extra-cases` 合并），**能力体检，不追满分**——定位边界和下一步问题

## Legacy 运行选择

| 场景 | 建议跑法 | 目的 |
|---|---|---|
| 刚改完 API / Trace / Eval 框架 | `smoke.yaml` | 先确认主链路没断 |
| 改了 Text2SQL 主流程 | formal + challenge | 看核心能力和复杂 SQL 是否退化 |
| 改了 schema retrieval / query plan | diagnostic | 看失败集中在哪个能力 |
| 模块收工 | smoke + formal + challenge，必要时 diagnostic | 留可复盘基线 |
| 做 A/B 对比 | 固定 formal 或 challenge 同一套 case | 保证对比口径稳定 |
| 排查具体失败 | 单条 case 或 diagnostic | 缩小问题范围，避免大批量日志干扰 |

## Legacy 关键口径

- **capability 标签**：`schema_retrieval / join_path / query_plan / local_schema_prompt / trace_steps / security_guard`——diagnostic 报告按能力维度汇总，跑完直接看下一步修哪块
- **`skipped_due_to_pipeline_mode`**：旧链路跑新能力专属 check 时标记，**不算过也不算挂**，不伪装未实现的能力
- **pipeline_mode**：case 内是推荐模式，`--pipeline-mode` 参数是实际执行模式（`baseline` / `new_text2sql`），报告同时记录两者
- **expected_value**：固定事实数值校验（如 GMV `11285752.00`），不依赖列名，堵住"NULL 也算对"的伪通过
- **result_match**：最小结果集对比（执行 expected_sql 后按行/列值比较），当前仅 5 条核心 challenge case 启用

## Legacy 加 case 的规则

- formal 是验收硬门，**要克制**：只加真正的主链路能力题
- alias 只放**语义等价**别名，绝不用 alias 掩盖缺表或错表
- diagnostic 定位边界，**不怕失败**；不为了好看把失败 case 改弱
- expected_value / 固定检查值**以数据事实为准**（用参考 SQL 在确定性 seed 上执行得到），不拍脑袋

## Legacy 注意事项

- 不要为了通过率把 diagnostic 失败 case 改弱；diagnostic 的价值就是暴露边界。
- 不要把 challenge 当 formal 硬门；challenge 是复杂度压力测试，主要用于观察退化和定位问题。
- 不要同时改模型、prompt、case、scorer 后再做 A/B；变量太多会导致结果不可解释。
- 不要把 `skipped` 当 `passed`；skipped 只表示当前执行模式不支持或本次不适用。
- 不要把 5 条 LangFuse Dataset workflow smoke 当完整 benchmark；它只证明流程能跑，不证明模型能力稳定。

## Legacy 结果解读

1. 先看 summary：`passed / failed / skipped` 是否低于当前基线。
2. 再看 Score Summary：是哪类 scorer 失败，例如 `rule:table_hit`、`rule:expected_value`、`rule:result_match`。
3. 再看 capability summary：失败是否集中在 `schema_retrieval`、`query_plan`、`security_guard` 等能力。
4. 最后结合 trace / issue_tags：判断是 pipeline 问题、case 问题、scorer 问题，还是执行环境问题。
5. M19 后优先看 `Failure Triage Summary`：按 `failure_stage / needs_action` 决定下一步修哪里。

> M19 会进一步把失败 case 归因为 `failure_stage / failure_reason / needs_action`。本文件只定义 case 分层、运行口径和维护规则；失败归因规则以 Phase 3B M19 计划与实现为准。

## Legacy CLI 命令（不再适用于当前 `eval.run_eval`）

（默认在项目 Python 环境中运行，`<项目 Python>` 见 CLAUDE.md；真实 LLM 用例需要 DeepSeek key）

```powershell
$py = "D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe"

# 1. smoke 冒烟（预期 6/6 passed，不联网）
& $py -m eval.run_eval --cases eval/cases/smoke.yaml --report eval/reports/latest.md

# 2. formal 主硬门（真实 LLM，预期 10/10）
& $py -m eval.run_eval --cases eval/cases/phase3a-regression.yaml --report eval/reports/phase3a-new-pipeline.md --trace .agent_work/temp/formal-traces.jsonl

# 3. challenge 陪跑（真实 LLM，预期 14/16）
& $py -m eval.run_eval --cases eval/cases/database-upgrade-challenge.yaml --report eval/reports/phase3a-challenge-new-pipeline.md --trace .agent_work/temp/challenge-traces.jsonl

# 4. diagnostic 能力体检（真实 LLM，当前基线 23/32，不追满分）
& $py -m eval.run_eval --cases eval/cases/database-upgrade-challenge.yaml --extra-cases eval/cases/phase3a-diagnostic-benchmark.yaml --report eval/reports/phase3a-diagnostic-new-pipeline.md --trace .agent_work/temp/diagnostic-traces.jsonl

# 5. 强制走新 Text2SQL pipeline（默认请求仍模板优先）
& $py -m eval.run_eval --cases eval/cases/phase3a-regression.yaml --pipeline-mode new_text2sql --report eval/reports/phase3a-new-pipeline.md
```

## Legacy 基线

最新真实 LLM 基线与默认配置以 `docs/state/AI_CONTEXT.md`「最新评测基线」为准。

- **最近稳定基线**：M13 后 `formal 10/10`、`challenge 14/16`、`diagnostic 23/32`。
- **当前风险**：主模型在 2026-07-31 切换为 `deepseek-v4-flash` 后尚未重跑完整三层评测；需要重跑后才能把这些数字视为当前基线。
- **记录规则**：每次更新基线时，同步记录模型、pipeline mode、case 文件、report 路径和 trace 路径，避免只留下一个通过率数字。
