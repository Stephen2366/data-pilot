# DataPilot RAG Runbook

> 业务 RAG、M34 EnterpriseRAG-Bench、external 180 题产品链路和 RAG review 的运行入口。公共授权、Gate、长任务与重跑纪律先读 [`runbook.md`](runbook.md)。运行身份见 [`rag-current-state.md`](rag-current-state.md)，评测数字见 [`eval-baselines.md`](eval-baselines.md)。

更新时间：2026-08-23

## 先选评测类型

| 类型 | 负责验证什么 | 当前规模 | 是否可混算 |
|---|---|---:|---|
| business RAG | 业务 release、ACL、版本、安全拒绝和业务合同 | 小 catalog | 否 |
| external dev | 大语料检索、选择、Composer、引用和答案质量诊断 | 冻结 60 题 | 否 |
| external held-out | 最终未污染验证 | 冻结 120 题 | 否；默认锁定 |

## 当前链路与边界

产品链路：`POST /api/query → Caller → Turn → Router → Harness → RAG Tool → Retrieval → Selection → Composer → Citation → API/Trace`。

- 业务默认：22 条 active release + `knowledge-deterministic-lexical-v1` + deterministic Composer。
- M34 external：独立 immutable dataset/profile + SQLite FTS5 lexical adapter；semantic candidate 未激活。
- business 真实 Eval 使用 `phase4-rag-eval-business-generation-outbound-v1`，只允许已通过 caller/ACL/Gate 的指定业务类别发往 Qwen；普通 API 不继承该权限。
- external 真实 Eval 使用 public benchmark outbound policy 和 eval-only fixed-RAG route。fixed route 只固定进入 RAG 分支，不验证自然 Router 分类。
- 题面、gold、60/120 split 和原生分层直接读取 immutable external dataset，不在项目内复制第二份题库。

## Business RAG 真实 Eval

| 目标 | 最大 Qwen 调用 | 命令 |
|---|---:|---|
| 查看 CLI | 0 | `python -m eval.run_rag_eval --help` |
| Smoke | 最多 1 | `python -m eval.run_rag_eval --selector smoke --run-id <run-id> --report eval/reports/<run-id>.md` |
| Core | 最多 3 | `python -m eval.run_rag_eval --suite core --run-id <run-id> --report eval/reports/<run-id>.md` |
| Diagnostic | 最多 1 | `python -m eval.run_rag_eval --suite diagnostic --run-id <run-id> --report eval/reports/<run-id>.md` |
| Reliability | 最多 3 | `python -m eval.run_rag_eval --suite reliability --run-id <run-id> --report eval/reports/<run-id>.md` |
| 精确单题 | N × replicate | `python -m eval.run_rag_eval --scenario <scenario-id> [--scenario <id>] --replicate-count <n> --run-id <run-id> --report eval/reports/<run-id>.md` |

产物：

- manifest/checkpoint/Trace：`.agent_work/temp/m41-rag-checkpoints/<run-id>/`
- completed artifact：`eval/reports/m41-rag-artifacts/<run-id>.json`
- report/triage：CLI 指定路径

## External 180 题

### 零费用回看 M34 旧结果

```powershell
python -m eval.run_rag_m34_history `
  --source .agent_work/temp/m34-answer-eval-full-v4.json `
  --retrieval .agent_work/temp/m34-lexical-tool-dev-retrieval.json `
  --retrieval .agent_work/temp/m34-lexical-tool-heldout-retrieval.json `
  --split-manifest eval/cases/enterprise-rag-bench-v1.0.0-split.json `
  --output .agent_work/temp/m41-m34-180-layered-history.json `
  --report eval/reports/m41-m34-180-layered-history.md
```

该命令不调用 Tool/LLM。旧 artifact 没有保存的 API/Router/Harness、selected、generation-visible 层必须显示为 `not_observed`。

### 真实产品链路

先查看参数：`python -m eval.run_rag_external_eval --help`

```powershell
python -m eval.run_rag_external_eval `
  --dataset-root <dataset-root> `
  --profile-root <profile-root> `
  --profile-identity <profile-identity> `
  --partition diagnostic_dev `
  --run-id <run-id> `
  --report eval/reports/<run-id>.md
```

- `diagnostic_dev`：60 题。
- `held_out`：120 题，必须单独获得明确授权；不得因为 dev 运行完成而自动执行。
- manifest/checkpoint/Trace：`.agent_work/temp/m41-rag-external-checkpoints/<run-id>/`
- completed artifact：`eval/reports/m41-rag-external-artifacts/<run-id>.json`

当前已完成的 `m41-rag-external-dev-20260822-01` 是 Composer 误分类修正前的 pre-fix candidate。不得改写 artifact、使用同 ID 重跑，或与修正后的 protocol 假装进行严格同协议比较。

## 离线 review 与 compare

以下命令均不调用 Tool/LLM：

| 目标 | 命令 |
|---|---|
| 生成 review bundle | `python -m eval.run_rag_review --artifact <artifact.json> --checkpoint-dir <checkpoint-root> --reviewer <name> --output <review.json>` |
| 校验来源 | `python -m eval.run_rag_review --bundle <review.json> --verify-only --output <verified.json>` |
| 合并人工 verdict | `python -m eval.run_rag_review --bundle <review.json> --verdicts <verdicts.json> --output <reviewed.json>` |
| 严格 compare | `python -m eval.run_rag_compare --left <left.json> --right <right.json> --output <compare.json>` |

verdict 必须逐 execution 闭集覆盖，只与自动 Gate 并列，不修改自动 assertion。catalog、selector、runtime、policy 或 scorer identity 不同，strict compare 必须拒绝。

## 失败分层

按以下顺序定位，不要只看最终答案：

1. product API / Harness / Trace
2. retrieved gold
3. selected gold
4. generation-visible gold
5. Composer provider / structure / support
6. cited gold
7. answer correctness / completeness 人工 verdict

上游未观察到时，下游标 `not_observed`；模型输出坏结构或 support 合同失败属于已观察失败。`answer_status=complete`、召回 gold、citation 合法和字符串 exact-fact 都不能单独代表语义正确。

人工复核至少覆盖全部自动失败/`not_observed`、高风险题和多文档题，并抽样自动通过题。没有答案或引用/context 不足时标 `insufficient_evidence`，不要猜成 pass/fail。

## M34 数据维护边界

日常 runbook 不再保留 dataset audit、split 构建、profile 构建、semantic candidate 构建和旧三题 smoke 等一次性施工命令。需要重建 external dataset/profile 或复现实验时，先读 `rag-current-state.md`、`CHANGELOG_INDEX.md` 和对应 M34 notes/history；这类操作可能改变 identity，必须另立明确任务。
