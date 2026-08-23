# DataPilot RAG Runbook

> 业务 RAG、M34 EnterpriseRAG-Bench、external 180 题产品链路、RAG review 与候选对比的运行入口。公共授权、Gate、长任务与重跑纪律先读 [`runbook.md`](runbook.md)。当前运行身份见 [`rag-current-state.md`](rag-current-state.md)，评测数字、兼容基线和历史 artifact 见 [`eval-baselines.md`](eval-baselines.md)。

更新时间：2026-08-24

## AI 快速执行入口

先把用户的话映射成唯一运行范围，再执行后文完整命令：

| 用户说法 | 唯一解释 | 当前题数 / executions | 不得自动做什么 |
|---|---|---:|---|
| business RAG Eval | Business 全量 | 5 / 5 | 不改成 external，不重复每题 |
| smoke RAG Eval | external dev smoke | 9 / 9 | 不扩到 full/held-out |
| basic RAG Eval | external dev basic | 21 / 21 | 不扩到 core/hard |
| core RAG Eval | external dev core | 25 / 25 | 不解释成 Text2SQL 或旧 Business Core |
| hard RAG Eval | external dev hard | 14 / 14 | 不扩到 held-out |
| reliability RAG Eval | external dev reliability | 6 题 × 3 = 18 | 不改重复次数，不指向 held-out |
| full RAG Eval | external dev full | 60 / 60 | 不扩到 all/held-out |
| held-out core RAG Eval | external held-out core | 49 / 49 | 只运行明确指定的 held-out suite |

表中的用户说法是语义示例，不要求逐字匹配。在 RAG Eval 语境中，裸 `smoke/basic/core/hard/reliability/full` 都属于 external，且安全默认是 `diagnostic_dev`。`dev` 是可反复诊断和改模块的 60 题开发集，日常不必说；`held_out` 是避免开发污染的 120 题封存集，只有用户明确说出时才运行。若用户只说“core”而没有说 RAG 还是 Text2SQL，仍需先消除跨评测类型的歧义。如果用户没有说 suite，先询问执行哪一个。

### 一次真实 Eval 的完整闭环

1. 读取公共 runbook、本文件、`rag-current-state.md`；需要解释基线或判断变好/变差时再读 `eval-baselines.md`。
2. 按上表冻结 suite、partition、题数和 replicate；一个授权只允许这一个范围执行一次。
3. 检查项目 Python、API Key 和 external 路径，不输出密钥内容。
4. 创建从未使用过的唯一 `run_id`；不得覆盖 completed artifact，也不得拿旧 ID 启动第二次运行。
5. 执行对应命令。预计超过 2 分钟时按公共 runbook/`AGENTS.md` 使用后台任务并保存日志、退出码和完成标记。
6. 前台超时不等于失败；检查同一 run 的进程、manifest、checkpoint 和 artifact，不得换 ID 重跑。
7. completed 后读取 artifact/report/triage，汇报运行范围、resolved runtime、Gate、usage、失败层、artifact identity 和 review 状态。
8. 只有存在兼容 baseline/candidate 且通过 compare 合同时，才能说模块“变好/变差”；单次绝对结果不能证明改动收益。

## 命令模板说明

本文档给出的 Powershell 命令是推荐的标准命令，不要求逐字复制。可以调整变量名、换行、前后台方式、唯一 run ID 和日志文件名；但不得改变用户授权范围、active identity、runtime 和 artifact 生命周期。若采用等价写法，执行前应确认最终参数与标准命令一致。

## 执行前固定参数与检查

所有命令从仓库根目录 `D:\.Work\Practice\AI-Project\data-pilot` 执行。当前可运行参数如下；external 运行前仍要与 `rag-current-state.md` 的 active profile 核对，若 identity 或路径变化，以状态文档为准并同步本快照。

```powershell
$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'
$ragDatasetRoot = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0'
$ragProfileRoot = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0\derived\enterprise_profiles'
$ragProfileIdentity = 'e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2'

Test-Path -LiteralPath $ragPython
Test-Path -LiteralPath $ragDatasetRoot
Test-Path -LiteralPath $ragProfileRoot
& $ragPython -c "from app.core.config import get_settings; print('DASHSCOPE_API_KEY=configured' if get_settings().dashscope_api_key else 'DASHSCOPE_API_KEY=missing')"
```

四个检查结果应分别为三个 `True` 和一个 `configured`。需要外网代理时使用公共 runbook 的 `HTTP_PROXY/HTTPS_PROXY`；实验覆盖只在当前进程生效，不修改 `.env`、默认模型、检索器、embedding、active profile 或 release。Codex/脚本工具的每次 shell 调用可能互不共享变量，所以下面的真实运行代码块会重复声明必要变量；不要把变量定义和命令拆到两个独立 shell 中。

## EnterpriseRAG-Bench 语义检索产品运行（Milvus）

> 本节的产品运行链路在 M44A 建立；此处按长期运维入口维护，不随模块结束归档。

EnterpriseRAG-Bench 的产品 retrieval 默认是 `semantic`。lexical 只用于显式历史复现；semantic 配置或 Milvus 不可用时，`/health/rag` 与 RAG 请求明确 unavailable，**不会**回退 lexical 或仓库业务小语料。Schema Retrieval 的 `SCHEMA_VECTOR_BACKEND` 是 Text2SQL 的另一套配置，不能用它开启 Enterprise RAG。

### 启动配置、preflight 与 Uvicorn

```powershell
$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'
$env:ENTERPRISE_RAG_RETRIEVAL_MODE = 'semantic'
$env:ENTERPRISE_RAG_PROFILE_ROOT = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0\derived\enterprise_profiles'
$env:ENTERPRISE_RAG_PROFILE_IDENTITY = 'e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2'
$env:ENTERPRISE_RAG_SEMANTIC_ROOT = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0\derived\enterprise_semantic'
$env:ENTERPRISE_RAG_SEMANTIC_IDENTITY = '9aec12c8d05db192cf041b89d04f880267a7c1200f5130caf4915c436b9a0e20'

docker ps
& $ragPython -m scripts.check_enterprise_rag_runtime
& $ragPython -m uvicorn app.main:app --reload
```

preflight 只验证 profile/manifest/unit-set/collection/load state，不发送 query embedding、不调用 Qwen Composer、不创建或重建 collection。`docker ps` 应看到 `milvus-standalone` healthy；本仓库没有负责启动 Milvus 的 compose 文件，应用也不会暗中启动 Docker。

服务启动后先访问 `GET /health/rag`：

- HTTP 200、`status=ready`：同时核对 `retrieval_mode=semantic`、目标 `semantic_identity` 和 `milvus_collection`；
- HTTP 503：按 `reason_code` 检查缺失配置、API key、Milvus、manifest/collection 或 embedding identity；不要切 lexical 掩盖故障；
- `/health` 只表示整个 API 进程仍活着，不能证明 RAG ready。

上述变量必须和 Uvicorn 在同一个 PowerShell 会话中。若只想做历史 lexical 对照，把 mode 显式改为 `lexical`；这不代表产品默认，也不需要 semantic root/identity，但完整回答仍需要 Qwen 配置。

## Business RAG 真实 Eval

Business catalog 只保留一个用户套件：全部 5 个业务合同场景各运行一次，最多 4 次 Qwen generation；无候选的安全拒绝题不调用 Composer。场景内部仍保留分类元数据用于报告诊断，但旧 Business smoke/core/diagnostic/reliability 不再是运行入口。

```powershell
$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'
$ragRunId = "m41-rag-business-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
& $ragPython -m eval.run_rag_eval `
  --suite business `
  --run-id $ragRunId `
  --report "eval/reports/$ragRunId.md"
```

精确单题只在用户明确点名 Scenario 时使用；`--scenario` 可重复传入，`--replicate-count` 只有用户明确要求重复时才大于 1：

```powershell
$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'
$ragRunId = "m41-rag-business-one-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
& $ragPython -m eval.run_rag_eval `
  --scenario <scenario-id> `
  --replicate-count 1 `
  --run-id $ragRunId `
  --report "eval/reports/$ragRunId.md"
```

产物：

- manifest/checkpoint/Trace：`.agent_work/temp/m41-rag-checkpoints/<run-id>/`
- completed artifact：`eval/reports/m41-rag-artifacts/<run-id>.json`
- report/triage：`eval/reports/<run-id>.md` 与自动生成的 `<run-id>-triage.json`

历史 2 题 Business Smoke artifact 保持原样，不改名、不改签；它不代表当前 5 题 Business 已运行。

## External 180 题真实产品链路

### Suite、难度与 partition

难度、运行协议和数据分区是三个独立维度：`basic/core/hard` 是题目难度；`smoke/reliability/full` 是运行规模或重复协议；`diagnostic_dev/held_out/all` 决定从哪一份冻结题单取题。

| suite | dev 题数 / executions | held-out 题数 / executions | 说明 |
|---|---:|---:|---|
| `smoke` | 9 / 9 | 不允许 | basic/core/hard 各 3 题的冻结快速检查 |
| `basic` | 21 / 21 | 43 / 43 | 单文档直接事实题；全 180 共 64 题 |
| `core` | 25 / 25 | 49 / 49 | 单文档 semantic/constrained/miscellaneous；全 180 共 74 题 |
| `hard` | 14 / 14 | 28 / 28 | 多文档或 completeness/conflict/reasoning/project；全 180 共 42 题 |
| `reliability` | 6 / 18 | 不允许 | basic/core/hard 各 2 题，每题固定 3 次 |
| `full` | 60 / 60 | 120 / 120 | partition 内全部题 |

`held_out` 中同样包含 basic/core/hard；它表示封存裁决集，不表示“困难题”。CLI 拒绝把 smoke/reliability 重新指向 held-out。`all --suite full` 是 180 题里程碑运行，只有用户明确授权 `all` 时才允许，不能由 dev 或 held-out 自动扩大。

### Dev 命令（默认）

将 `$ragSuite` 设置为用户明确授权的 `smoke/basic/core/hard/reliability/full`。不传 `--partition` 时，CLI 安全默认 `diagnostic_dev`：

```powershell
$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'
$ragDatasetRoot = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0'
$ragProfileRoot = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0\derived\enterprise_profiles'
$ragProfileIdentity = 'e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2'
$ragSemanticRoot = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0\derived\enterprise_semantic'
$ragSemanticIdentity = '9aec12c8d05db192cf041b89d04f880267a7c1200f5130caf4915c436b9a0e20'
$ragSuite = 'core'
$ragRunId = "m41-rag-external-$ragSuite-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
& $ragPython -m eval.run_rag_external_eval `
  --dataset-root $ragDatasetRoot `
  --profile-root $ragProfileRoot `
  --profile-identity $ragProfileIdentity `
  --semantic-root $ragSemanticRoot `
  --semantic-identity $ragSemanticIdentity `
  --suite $ragSuite `
  --run-id $ragRunId `
  --report "eval/reports/$ragRunId.md"
```

当前省略 `--retrieval-mode` 即使用产品默认 semantic。只有复现历史 lexical baseline 时才显式增加 `--retrieval-mode lexical`；不得把 semantic failure 后的 lexical run 记成同一次授权的重试。

精确单题只在用户明确点名 external Scenario 时使用，且仍受 partition 约束。默认 `diagnostic_dev` 不能选择 held-out ID：

```powershell
$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'
$ragDatasetRoot = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0'
$ragProfileRoot = "$ragDatasetRoot\derived\enterprise_profiles"
$ragSemanticRoot = "$ragDatasetRoot\derived\enterprise_semantic"
$ragRunId = "rag-external-one-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
& $ragPython -m eval.run_rag_external_eval `
  --dataset-root $ragDatasetRoot `
  --profile-root $ragProfileRoot `
  --profile-identity 'e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2' `
  --semantic-root $ragSemanticRoot `
  --semantic-identity '9aec12c8d05db192cf041b89d04f880267a7c1200f5130caf4915c436b9a0e20' `
  --scenario <explicit-dev-scenario-id> `
  --run-id $ragRunId `
  --report "eval/reports/$ragRunId.md"
```

### Held-out 命令（必须明确授权）

只有用户明确说出 `held-out` 和具体 suite 后，才在同一命令中增加 partition。下面只展示命令形状，不构成运行授权；`smoke/reliability` 不可使用：

```powershell
$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'
$ragDatasetRoot = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0'
$ragProfileRoot = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0\derived\enterprise_profiles'
$ragProfileIdentity = 'e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2'
$ragSemanticRoot = 'D:\.Work\Practice\AI-Project\data-pilot-datasets\enterprise-rag-bench\v1.0.0\derived\enterprise_semantic'
$ragSemanticIdentity = '9aec12c8d05db192cf041b89d04f880267a7c1200f5130caf4915c436b9a0e20'
$ragSuite = 'core'
$ragRunId = "m41-rag-external-heldout-$ragSuite-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
& $ragPython -m eval.run_rag_external_eval `
  --dataset-root $ragDatasetRoot `
  --profile-root $ragProfileRoot `
  --profile-identity $ragProfileIdentity `
  --semantic-root $ragSemanticRoot `
  --semantic-identity $ragSemanticIdentity `
  --partition held_out `
  --suite $ragSuite `
  --run-id $ragRunId `
  --report "eval/reports/$ragRunId.md"
```

产物：

- manifest/checkpoint/Trace：`.agent_work/temp/m41-rag-external-checkpoints/<run-id>/`
- completed artifact：`eval/reports/m41-rag-external-artifacts/<run-id>.json`
- report/triage：`eval/reports/<run-id>.md` 与自动生成的 `<run-id>-triage.json`

## 运行生命周期、超时与结果汇报

### 同一个 run 应该检查什么

1. 先检查后台进程/退出码/完成标记和 stdout/stderr；前台工具超时但进程仍活着时继续等待。
2. 读取对应 checkpoint 根目录下 `<run-id>/manifest.json`。
3. `status=running` 且 checkpoint 数继续增长：仍在运行，不做第二次启动。
4. 进程已经结束但 manifest 未 completed：检查错误和已有 checkpoint；只允许用相同 RunSpec、相同 `run_id` 和显式 `--resume` 恢复合法前缀，不得用新 ID 掩盖失败。provider unavailable、合同失败或质量失败不是“多跑一次”的理由。
5. `status=completed` 后确认 completed artifact 存在，并以 artifact 为自动评测事实源。部分 checkpoint、Markdown report、triage 或历史投影不能冒充 completed run。

快速读取 manifest：如果这是新的 shell，先把 `$ragRunId` 设置成刚才实际使用的 ID，禁止生成新 ID：

```powershell
$ragRunId = '<existing-run-id>'
# Business
Get-Content ".agent_work/temp/m41-rag-checkpoints/$ragRunId/manifest.json" -Raw

# External
Get-Content ".agent_work/temp/m41-rag-external-checkpoints/$ragRunId/manifest.json" -Raw
```

### 完成后必须汇报

- 实际 suite、partition、Scenario 数、physical executions 和是否发生 resume；
- completed 状态、resolved runtime/profile/model/retrieval identity；
- required assertion 的 passed/failed/not_observed 与 Gate；
- provider request/token usage，以及 external unavailable 是否存在；
- primary failure 分层和最重要的失败样本；
- artifact/report/triage/review 路径与 artifact identity；
- 本次是否有兼容 baseline、能否合法得出“变好/变差”。

Gate 的含义继承公共 runbook：`passed` 仍要人工语义复核；`failed` 是已观察合同失败，不能靠重跑掩盖；`inconclusive` 表示存在 `not_observed`，不能当通过或失败，也不自动重跑。

## 当前链路与不可丢失的解释边界

产品链路：`POST /api/query → Caller → Turn → Router → Harness → RAG Tool → Retrieval → Selection → Composer → Citation → API/Trace`。

- Business：22 条 active release + `knowledge-deterministic-lexical-v1`；真实 Eval 使用独立 `phase4-rag-eval-business-generation-outbound-v1`，只允许已通过 caller/ACL/Gate 的指定业务类别发往 Qwen，普通 API 不继承该权限。
- External：独立 immutable dataset/profile + Milvus semantic 产品默认；Milvus 只选 `unit_identity`，正文/Evidence coordinates 仍由 SQLite profile 权威回查。lexical 仅显式 baseline；题面、gold、60/120 split 和原生分层直接读取项目外数据，不复制第二份题库。
- External 使用 public benchmark outbound policy 和 eval-only fixed-RAG route。fixed route 只固定进入 RAG 分支，因此验证产品 Harness/RAG Tool/AnswerFlow，但**不验证自然 Router 分类能力**。
- Business 与 external 的 catalog、runtime、分母和结果必须分账，不能混成一个 RAG 总分。

## 失败分层与人工语义 Review

按真实数据流定位，不要只看最终答案：

1. product API / Harness / Trace
2. retrieved gold
3. selected gold
4. generation-visible gold
5. Composer provider / structure / support
6. cited gold
7. answer correctness / completeness 人工 verdict

上游未观察到时，下游标 `not_observed`；模型已返回但结构或 support 合同失败属于已观察失败。`answer_status=complete`、召回 gold、citation 合法和字符串 exact-fact 都不能单独代表语义正确。

Review 是离线旁路，不调用 Tool/LLM，不修改 completed artifact、自动 assertion 分母或 Gate：以下表格假设当前 shell 已设置项目 `$ragPython`；新 shell 先执行 `$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'`。

| 目标 | 命令 |
|---|---|
| 生成 review bundle | `python -m eval.run_rag_review --artifact <artifact.json> --checkpoint-dir <checkpoint-root> --reviewer <name> --output <review.json>` |
| 校验来源 | `python -m eval.run_rag_review --bundle <review.json> --verify-only --output <verified.json>` |
| 合并语义 verdict | `python -m eval.run_rag_review --bundle <review.json> --verdicts <verdicts.json> --output <reviewed.json>` |

`<checkpoint-root>` 要传 Business 或 External 的公共 checkpoint 根目录，不要直接传 `<run-id>` 子目录。verdict JSON 必须按 bundle 的全部 `record_id` 闭集覆盖，不能只提交失败题：

```json
{
  "<scenario-id>:r1": {
    "verdict": "pass",
    "reason": "结合答案、gold 与引用证据给出具体理由"
  }
}
```

允许值只有 `pass/fail/insufficient_evidence`。人工或被明确委派的 AI reviewer 必须实际逐题检查答案与证据；没有答案、引用或 context 不足时用 `insufficient_evidence`，不得从自动 Gate 猜 verdict。至少复核全部自动失败/`not_observed`、高风险题、多文档题，并抽样自动通过题。

## 严格复现与候选 A/B Compare

以下 compare 命令离线运行，不调用 Tool/LLM：

```powershell
$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'
# 同一 runtime 的严格复现
& $ragPython -m eval.run_rag_compare `
  --left <baseline-artifact.json> `
  --right <repeat-artifact.json> `
  --output <strict-compare.json>

# 预先声明允许变化字段的 runtime 候选
& $ragPython -m eval.run_rag_compare `
  --left <baseline-artifact.json> `
  --right <candidate-artifact.json> `
  --allow-runtime-difference retrieval_adapter_identity `
  --allow-runtime-difference retrieval_recipe_identity `
  --allow-runtime-difference retrieval_mode `
  --allow-runtime-difference semantic_identity `
  --allow-runtime-difference semantic_manifest_identity `
  --allow-runtime-difference embedding_provider `
  --allow-runtime-difference embedding_model `
  --allow-runtime-difference embedding_dimensions `
  --allow-runtime-difference milvus_collection `
  --allow-runtime-difference unit_set_identity `
  --output <candidate-compare.json>
```

- strict compare 要求 catalog、selector、题序/replicate、assertion plan、scorer、Scenario metadata 和 resolved runtime 全部相同。
- candidate compare 只放行 `--allow-runtime-difference` 明确登记的 runtime 字段；任何未声明漂移继续失败关闭。允许多个字段只能证明“整体候选”变化，不能把收益归因给单个组件。
- 输出的逐题 win/loss/tie/mixed/insufficient、首失败层迁移、difficulty assertion、usage 和 latency 只描述自动证据变化，不能代替自然语言 correctness/completeness review。
- 运行 Compare 前必须从 `eval-baselines.md` 确认 left/right 协议兼容。当前已完成的 external 60 dev 是 Composer 误分类修正前、且缺 difficulty 的 pre-fix candidate；不得把它与当前 post-fix run 假装成严格复现。没有兼容 baseline 时，只能建立新候选证据，不能宣称模块已经变好或变差。

## 历史回看与数据维护

### 零费用回看 M34 旧结果

```powershell
$ragPython = 'D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe'
& $ragPython -m eval.run_rag_m34_history `
  --source .agent_work/temp/m34-answer-eval-full-v4.json `
  --retrieval .agent_work/temp/m34-lexical-tool-dev-retrieval.json `
  --retrieval .agent_work/temp/m34-lexical-tool-heldout-retrieval.json `
  --split-manifest eval/cases/enterprise-rag-bench-v1.0.0-split.json `
  --output .agent_work/temp/m41-m34-180-layered-history.json `
  --report eval/reports/m41-m34-180-layered-history.md
```

该命令不调用 Tool/LLM。旧 artifact 没有保存的 API/Router/Harness、selected、generation-visible 层必须显示为 `not_observed`，不得冒充产品 E2E。

日常 runbook 不展开 dataset audit、split/profile/semantic candidate 构建和旧三题 smoke 等一次性施工命令。需要重建 external dataset/profile 或复现实验时，先读 `rag-current-state.md`、`CHANGELOG_INDEX.md` 和对应 M34 notes/history；这类操作可能改变 identity，必须另立明确任务。
