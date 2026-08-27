# M49 收工后 RAG 真实链路探索重验

> 口径：本次发生在 M49 技术收工之后，只记为 `exploratory / baseline-ineligible / not-development-probe`。它不能倒算为开发期 Live Dev Probe，也不是 Formal Eval 或新基线。

## Implementation checklist

- [x] 明确场景、真实依赖、预算、数据边界与停止条件
- [x] 完成零 payload / 零 provider 的运行环境预检
- [x] R1：业务知识正常问答贯通 API、检索、生成、引用与 Trace
- [x] R2：无知识命中时失败关闭，不调用生成模型
- [x] R3：Enterprise semantic 贯通 Embedding、Milvus、SQLite authority、生成与引用
- [x] R4：experimental RAG Subgraph 已执行并定位生成前正文水化断点
- [x] R5：SQL+RAG Hybrid 在 R4R 产品链恢复后真实贯通
- [x] 固化真实命令、identity、attempt/token、首个失败层和证据边界

## 预注册

- **时间**：2026-08-27（Asia/Shanghai）
- **代码基线**：`7e1cec2b3cc3a617c08d91b5d9f2c02047fc6d1e`；登记时工作树干净。
- **用户授权**：用户明确要求“现在再进行整个 RAG 功能的相关真实 LLM 的 live dev Probe，检查相关功能与链路通畅”。按 runbook 将它收窄为收工后探索重验，不扩大为正式评测。
- **R1 / business happy path**：`quality_refund_materials`。验证 22-entry active release 上的业务知识检索、selection、Qwen composer、citation、Response/Trace。
- **R2 / business fail-closed**：`unsupported_warranty_rule`。验证无候选时安全收口且不触发生成调用。
- **R3 / enterprise pipeline**：`diagnostic_dev/qst_0386`。验证 DashScope query embedding → 既有 Milvus collection → SQLite profile authority → Qwen composer → citation/Trace。
- **R4 / enterprise subgraph**：`diagnostic_dev/qst_0431`，策略显式为 `subgraph`。验证 bounded recovery / formation、子预算、Evidence 合并和最终 composer；不改变默认 pipeline。
- **R5 / hybrid**：使用测试 MySQL 的只读业务数据和临时 task checkpoint/event 行，验证 SQL Evidence + business Knowledge Evidence 在 Phase 4B Task/Decision Loop 中连续汇合到 Response/Trace；运行后清理临时任务状态。
- **真实依赖**：Qwen `qwen3.7-plus`、DashScope embedding、Milvus、项目外只读 enterprise diagnostic snapshot/profile、测试 MySQL。
- **预算**：累计最多 10 次 provider attempt、35,000 个可观测 token；`retry=0`。embedding 若供应商不返回 token，只记 attempt，不估算 token。
- **数据边界**：只读业务 active release、`diagnostic_dev` 的两个固定题、既有 external collection/profile、测试数据库；禁止 held-out、sealed reserve、production data、full/reliability suite、索引重建、release/default 切换和 reseed/reset。
- **停止条件**：预检不健康则 `inconclusive` 且不发 payload；出现首个系统性/产品链路失败就停止后续场景并记录首个失败层；达到 attempt/token 上限立即停止；不自动重跑失败场景。
- **通过边界**：只证明这些固定场景在当前环境的一次真实纵向可运行性及代表性失败关闭；不能外推整体正确率、泛化质量、稳定性、生产能力或基线提升。

## 执行记录

### P0：零 payload 预检

- `docker ps` 首次在沙箱内因 Docker pipe 权限失败；按既有只读授权在沙箱外重试，三项依赖均 healthy：`milvus-standalone`、`milvus-minio`、`milvus-etcd`。这是执行环境权限问题，不是 RAG 产品失败。
- `scripts/check_enterprise_rag_runtime.py` 返回 `status=ready`；profile=`e8783fe0...75fa2`、semantic=`9aec12c8...e20`、manifest=`22c573...be97b`、collection=`datapilot_knowledge_enterprise_9aec12c8d05db192cf041b89`、unit-set=`17d5af0...905f` 全部匹配；`embedding_transport_called=false`、`composer_called=false`。
- Qwen/DashScope key 只检查到 `configured`，未输出密钥。附带状态打印误用了不存在的 `Settings.llm_timeout` 字段而抛 `AttributeError`，但 key 检查和独立 runtime preflight 均已完成；该错误不影响产品 runtime，也未产生 provider attempt。
- 决定：`continue`，允许 R1。当前累计 provider attempts=`0`，observed tokens=`0`。

### R1 启动门：外发数据授权被执行环境拦截

- 按预注册命令尝试启动 `quality_refund_materials`，执行环境在创建 Python 进程前拒绝：真实 Qwen Composer 会把该业务问题，以及检索到的业务知识片段作为上下文发送给 DashScope/Qwen；现有“执行真实 RAG Probe”授权没有被权限审查器视为对这类具体数据外发的明确授权。
- 进程未创建，provider attempts=`0`、observed tokens=`0`、无 Response/Trace/artifact；这不是产品链路失败，也没有消耗 Probe 预算。
- 当前决定：`stop / awaiting explicit outbound-data authorization`。禁止绕过权限或换入口间接执行。

### R1：Business happy path

- 用户随后明确授权上述固定测试数据外发。原命令成功执行一次，未重跑：`quality_refund_materials`，run=`m49-rag-postprobe-r1-20260827`。
- HTTP `200`，trace=`ab484a91-b196-43fd-aa19-6849be759a06`，`route=rag`、`execution=completed`、`answer=complete`、`safety=passed`；Gate=`14 passed / 0 failed / 0 not_observed`，artifact=`ddb4d7e9...3bfea`。
- 真实链路：确定性业务检索调用 1 次，3 条授权 Evidence 进入 generation context；Qwen Composer 1 call / retry0，usage=`655 prompt + 358 completion = 1013 tokens`；引用落到 `refund-policy-quality`，Trace 同步保存 route、tool observation、Evidence ledger 和 citation stage。
- Warning 只有既有 Starlette/httpx deprecation，不影响本场景。
- 决定：`continue`，允许 R2。累计 provider attempts=`1 chat`，observed tokens=`1013`。

### R2：Business fail-closed

- 单次执行 `unsupported_warranty_rule`，run=`m49-rag-postprobe-r2-20260827`；HTTP `200`，trace=`c9946a7f-4a5f-443e-a702-4fa10667c830`，Gate=`9/0/0`，artifact=`dfcbfe51...09439`。
- 真实结果为 `execution=completed / answer=insufficient_evidence / safety=passed / reason=evidence_no_candidate`；Knowledge Tool 检索 1 次、候选/上下文/引用均为 0，Composer=`0`、tokens=`0`，返回“当前无法形成可公开的答案”。
- 这证明代表性的无证据路径会在生成前关闭，不会让模型凭空编答案。Warning 仍只有既有 Starlette/httpx deprecation。
- 决定：`continue`，允许 R3。累计 provider attempts=`1 chat`，observed tokens=`1013`。

### R3：Enterprise semantic Pipeline

- 单次执行 `diagnostic_dev/qst_0386`，run=`m49-rag-postprobe-r3-20260827`，策略显式 `pipeline`；artifact=`e7b40484...b8724`，trace=`2fc60b60-f3d4-4141-ab31-137a1a7af6f3`。
- required Gate=`12 passed / 0 failed / 0 not_observed`；`execution=completed / answer=complete / safety=passed / reason=answer_completed`。漏斗=`candidate 5 → selected 3 → generation-visible 3 → cited 1`，gold document 在四层均命中。
- 真实 provider 结构：query embedding 1 attempt（供应商未给 token，保持 unknown）+ Qwen Composer 1 attempt / retry0，`1729 + 353 = 2082 observed chat tokens`。runtime identity 与 P0 冻结值一致；Milvus 只选 unit，SQLite profile 提供正文，Trace/Response 一致。
- 自动 required Gate 通过；advisory 为 `2 passed / 1 failed`。因此本场证明链路闭合和该固定题可答，不把 advisory 失败抹掉，也不外推整体语义质量。
- 前台工具回传先结束而 Python 子进程短暂继续；只等待原 PID，未启动第二份或换 run ID，最终正常产出完整 artifact。
- 决定：`continue`，允许 R4。累计 provider attempts=`3（2 chat + 1 embedding）`，observed tokens=`3095`。

### R4：Enterprise experimental Subgraph——failed，停止后续真实调用

- 单次执行 `diagnostic_dev/qst_0431`，run=`m49-rag-postprobe-r4-20260827`，策略显式 `subgraph`；artifact=`94aaa54e...829f6`，trace=`5c536360-8df4-4d06-8d7e-a0be156b7604`。
- Subgraph 前半段真实工作正常：initial semantic retrieval 1 attempt、candidate=5；确定性 procedure admission 准入 `context_expansion_candidate`，扫描 2 个 sibling、加入 2 条新 Evidence，最终 selected/generation-visible=`3/3`，child termination=`answer_ready`、detail=`recovery_evidence_merged`、child budget 未超限。
- 最终结果为 `execution=failed / answer=no_answer / safety=passed / reason=composer_unavailable`；required Gate=`9 passed / 1 failed / 2 not_observed`，漏斗=`3→3→3→0`。Qwen transport 成功但返回坏结构，Composer attempt=`1`、usage=`398 prompt + 9 completion = 407 tokens`、subtype=`composer_response_invalid_cardinality`；失败关闭，没有发布答案或 citation。
- **首个表面失败层**：Composer response schema/cardinality validator。
- **确定性根因定位**：不是单纯模型随机抽风。external profile 的 active bundle 为控制 139k 单元内存只加载 metadata，代码明确把 `CatalogEntry.content` 设为 `""`（`engine/rag/enterprise_runtime.py:135`）；正常 Pipeline 会通过 SQLite materializer 用 `replace(entry, content=content)` 水化正文（同文件 `:293`）。但 Subgraph recovery 的 `_reauthorize_and_merge()`（`engine/phase4b/rag_subgraph.py:614`）从 metadata bundle 找到 entry 后，直接在 `:655` 调 `make_document_evidence(entry=entry)`，没有走 materializer。因此 artifact 虽有 3 条 generation-visible Evidence，`context_characters=0`，Composer prompt 仅 398 tokens，实际没有正文可依据；无论模型返回空 claims 还是尝试作答，都不可能稳定满足逐字 support 合同。
- **为什么测试没挡住**：`tests/test_m46_b4_external_chain.py` 的 external fixture 自己构造带正文的 `CatalogEntry`，不复现产品 profile 的 metadata-only 布局。针对 qst_0431 类 procedure 的聚焦测试仍为 `1 passed in 0.76s`，反而证明这是“fixture 通过、真实接线断”的覆盖缺口。
- 真实 provider 结构为 embedding 1 attempt + Composer 1 attempt；formation 0。累计 provider attempts=`5（3 chat + 2 embedding）`，observed chat tokens=`3502`；embedding token 均未观测，不估算。
- 决定：`stop`。按预注册的首个产品链路失败停止条件，R5 SQL+RAG Hybrid 不执行，不用剩余预算掩盖 R4 断点，也不自动重跑 R4。本轮不改代码。

## 当前证据边界

- 已真实证明：业务 RAG happy path、业务无候选失败关闭、Enterprise semantic Pipeline 固定题的完整检索/生成/引用链；experimental Subgraph 的 retrieval、procedure admission、sibling expansion、Evidence merge 与失败关闭均真实运行。
- 修复后新增证明：external Subgraph recovery Evidence 已从 SQLite 水化并进入 Composer/citation 完成态；真实 Qwen/MySQL/business Subgraph Hybrid 也在同一 task turn 形成 SQL/Document 双 Evidence。qst_0431 的 cited-gold 与精确事实质量 Gate 仍未通过。
- 本轮不是开发期 Probe、Formal Eval 或质量基线；不能外推整体正确率、稳定性、生产能力或 semantic/Subgraph 质量胜出。

## State impact 与收尾检查

- **已更新**：`docs/state/AI_CONTEXT.md`（当前断点与待决事项）、`docs/state/change-history/phase4b.md`（实验历史）、`docs/state/rag-current-state.md`（当前链路与活跃风险）、`docs/state/eval-baselines.md`（baseline-ineligible 当前实验快照）。
- **已检查、无需修改**：`docs/state/runbook.md`、`docs/state/runbook-rag.md` 与 `docs/state/schema-retrieval-milvus-embedding.md`；本轮没有改变命令纪律、默认模型、embedding、collection、identity 或运行入口。
- **已检查、无需修改**：`docs/state/database-current-state.md`；R5 只读既有业务数据，只新增并 finally 清理 synthetic task/event，没有形成新数据库长期事实。
- 所有 R1～R5/R4R artifact 与本 notes 路径均已存在性复核；最终 `git diff --check` exit 0。Git 的 LF→CRLF 提示不是内容错误。
- 最终代码修改只覆盖 external Subgraph context-loader 接线、两个产品组装入口和聚焦回归测试；真实 provider 总计=`9 attempts（6 chat + 3 embedding）`，observed chat tokens=`15502`。没有 fallback、held-out、reserve、索引写入或默认切换。

## 修复实施 checklist（用户授权后追加）

- [x] 给 external Subgraph 注入既有 Enterprise SQLite context loader，不改变 Pipeline 默认或 Composer validator
- [x] recovery merge 对每条 metadata entry 先水化正文，再校验 identity/coordinates/ACL 并重建 Evidence
- [x] 新增 metadata-only external fixture，证明 recovery 后 Composer 实际收到非空正文
- [x] 运行 Subgraph/strategy/Eval 投影聚焦回归与既有兼容回归
- [x] 执行用户已授权的 R4 qst_0431 单次真实最小重验；失败即停止，不自动重跑
- [x] 仅当 R4 产品链恢复时执行原预注册 R5 Hybrid，并固化 usage、Trace 与清理证据

### 修复决策

- 不采用“放宽空 claims / support validator”或“让模型在无正文时自由回答”；这会掩盖产品接线错误并破坏 citation-bound 合同。
- 复用 `EnterpriseProfileRuntime.context_loader`，因为它已经是 SQLite 正文 authority，并验证 revision、anchor、content hash 和 offsets。修复只把 Subgraph recovery 接回与正常 Pipeline 相同的 authority seam，不新增数据源、默认行为或 fallback。
- 用户已明确授权下一次 Probe。授权精确映射为同一 `diagnostic_dev/qst_0431`、同一 semantic identity、`subgraph` 策略的一次 R4R；预算使用原 campaign 剩余额度，retry0。R4R 通过后才执行一次原 R5，不触碰 held-out/reserve/生产数据。

### 修复实现与本地验证

- `BoundedRAGSubgraphAcquirer` 新增受信 `context_loader` 依赖；external recovery merge 在 metadata identity/active status 通过后调用 loader，要求 hydrated document key/revision/content identity/anchor 完全相同且正文非空，再使用 loader 返回的真实 coordinates 重建 Evidence。loader 不可用、异常、identity 漂移或空正文均 typed fail-closed。
- `configure_external_acquisition()` 在 Subgraph 策略下把 context loader 纳入必需依赖；FastAPI product factory 与 external Eval factory 都显式注入 `EnterpriseProfileRuntime.context_loader`。Pipeline/business 接线和默认策略未改变。
- 新增 metadata-only external 纵向测试：active bundle 的 content 全为空，fixture loader 模拟 SQLite 回填；真实 `RAGAnswerFlow → Gate → recording Composer → citation` 必须 complete，并断言所有实际入模正文非空。
- 第一次聚焦运行逻辑显示 16 项通过，但 pytest session cleanup 在 sandbox basetemp 遇到 Windows `WinError 5`，没有形成完整 exit 0；未改代码，用新 basetemp 沙箱外原集合重跑=`17 passed, 1 existing warning`。
- 受影响 M44A/M45/M46 全集合=`84 passed, 1 existing warning`；compileall exit 0。warning 均为既有 Starlette/httpx deprecation，不影响修复。
- 当前决定：`continue`，放行已授权 R4R。修复前 campaign 累计仍为 5 attempts / 3502 observed chat tokens；本地验证新增 provider=`0`。

### R4R：修复后单次真实重验

- 零 payload preflight 再次 `ready`，identity/collection/unit-set 全部与 R4 相同，embedding/Composer transport=`false/false`。
- 单次运行 `diagnostic_dev/qst_0431`，run=`m49-rag-postprobe-r4r-20260827`，artifact=`1baf308f...4d921`，trace=`2895c904-2826-4390-9c32-54ba2946cbf4`；无 resume/重跑。
- 原产品断点已修复：`context_characters 0→5425`，Qwen Composer 成功，`execution=completed / answer=complete / safety=passed`，漏斗 `3→3→3→2`，child 仍为 initial retrieval + deterministic procedure + 2-unit expansion，Response/Trace 完整。
- 本次 provider=`1 embedding + 1 chat`，Qwen usage=`1692 prompt + 612 completion = 2304 tokens`。campaign 累计=`7 attempts（4 chat + 3 embedding）/ 5806 observed chat tokens`。
- 自动总 Gate 仍为 failed：required=`11/1/0`，失败项为 `cited_gold`；advisory=`2/1/0`，失败项为 exact-fact lower bound。也就是说技术链已接通，但答案没有引用 scorer 指定的 gold 文档，不能宣称该题质量通过。
- 停止条件按“首个系统性/产品链路失败”定义；本次 product runtime、Composer、citation 均完成，剩余为答案/引用质量问题。因此决定=`continue`，在总预算剩余 3 attempts / 29194 observed tokens 内放行原预注册 R5 Hybrid；不会重跑 R4R 或为过 Gate 调参。

### R5：真实 Qwen/MySQL/business Subgraph Hybrid

- 临时 runner 首次启动在 provider/数据库前因 ORM import order 循环导入失败；输出目录尚未创建，calls/tokens/DB writes=`0/0/0`。只调整临时脚本导入顺序后重试同一 R5，不改变产品代码、场景或预算。
- 有效执行为单个 start turn：问题“比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。”；隔离库=`datapilot_m48_test`，migration=`0005`，oracle=`120000/180000`。
- HTTP 200，trace=`4838e4e8-4464-4c24-8f27-9fdfb7d895ec`；`route=hybrid / execution=completed / answer=complete / safety=passed / reason=answer_ready`，task version=1，runtime invocation=1。
- 同一父 Loop 依次完成 `collect_sql_evidence` 与 `collect_document_evidence`；SQL 返回 8 行，TaskState 保存 4 条 Evidence，business Subgraph runtime identity=`business-release:7d0d0937...409a:strategy:subgraph`，最终 citation=2。
- provider calls=`2`、observed tokens=`9696`，均由真实 Qwen SQL 链产生；business RAG branch 只做 retrieval + Shared Gate，不额外生成子答案。临时 checkpoint/event=`0/0 → 1/1 → 0/0`，finally cleanup 通过。
- safe artifact=`.agent_work/temp/m49/rag-postprobe/r5/result-safe.json`，decision=`continue`。campaign 最终累计=`9 attempts（6 chat + 3 embedding）/ 15502 observed chat tokens`，低于 10/35000 上限。

### 最终本地验证

- 加强 external loader 必须返回非空正文和非空 coordinates；Subgraph strategy 缺 context loader 时在检索前失败关闭。
- 最终受影响 M44A/M45/M46 回归=`84 passed, 1 existing warning`，compileall exit 0；warning 仍为 Starlette/httpx deprecation。
- 本轮没有放宽 Composer/support/citation validator，没有切默认、fallback、索引、release、held-out 或 reserve。

### 修复文件清单

- 产品代码：`engine/phase4b/rag_subgraph.py`、`engine/phase4b/rag_strategy.py`、`app/main.py`、`eval/run_rag_external_eval.py`。
- 测试：`tests/test_m46_b4_external_chain.py`、`tests/test_m46_rag_strategy.py`。
- 技术档案：本 notes、`docs/state/AI_CONTEXT.md`、Phase 4B changelog、`rag-current-state.md`、`eval-baselines.md`。
- 临时 runner 与 Response/Trace/artifact 均位于 `.agent_work/temp/m49/rag-postprobe/`，不进入 Git 交付文件。
