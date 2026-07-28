# DataPilot Phase 3B Plan：引入 LangFuse 可观测性与评测基座

> 阶段三B：用 LangFuse 替代当前 JSONL Trace + 规则评分体系，为阶段三 RAG/Hybrid 和独立 agent-eval-ops 项目打好可观测性基座。
>
> **核心目标**：在不改动 `/api/query` 响应契约的前提下，把 trace 存储从 JSONL 文件迁移到 LangFuse 自部署实例，并补齐 LLM-as-Judge 评分能力。

## 前置状态（供新 AI 会话续接）

### 项目当前状态快照

| 维度 | 事实 |
|------|------|
| 当前阶段 | Phase 3A（M14-lite）刚收口，Phase 3 RAG/Hybrid 尚未开工 |
| 当前 trace 实现 | `engine/trace/recorder.py`：`TraceRecord` Pydantic 模型 → `append_trace()` 写 JSONL 到 `eval/traces/traces.jsonl` |
| trace 写入入口 | `app/api/query.py` 的 `_record_trace()` 函数，在 `_success_response()` / `_blocked_response()` 中调用 |
| trace 路径可覆盖 | 通过 `app.state.trace_path` 指向临时文件，测试/smoke/实验各自写入不同路径 |
| 当前评测体系 | `eval/run_eval.py`：YAML 用例 → 调 `/api/query` → 纯规则评分（contains/equals/expected_value）→ Markdown 报告 |
| A/B 实验 | `scripts/run_qwen_ab_experiments.py`：子进程运行 eval、解析 Markdown 报告 → 汇总表格 |
| 已有配置预留 | `Settings` 中已有 LangSmith 字段（`langsmith_tracing/endpoint/api_key/project`），当前未启用 |
| LangFuse 现状 | ❌ 代码库中无任何 LangFuse 引用或配置 |
| 独立评测项目 | agent-eval-ops 尚在规划阶段，计划做成独立项目 |

### 本次对话分析结论摘要

上一轮对话对当前方案、LangFuse、LangSmith 做了详细对比，关键结论：

1. **当前自研 JSONL trace + 规则评分**：在当前 Text2SQL 阶段刚好够用，但缺乏三个关键能力——(a) LLM-as-Judge 语义评分、(b) Trace 可视化和查询、(c) 实验管理平台化
2. **LangSmith vs LangFuse**：功能相近；LangSmith 仅 SaaS（国内网络不稳定），LangFuse 开源可自部署（BSL 协议，非生产级使用免费）
3. **那个员工的方案**（业务埋点 → LangFuse trace → LLM-as-Judge + 规则计算 → Experiment）：思路完全正确，是行业主流做法，适合作为 agent-eval-ops 的参考架构
4. **对 DataPilot**：建议暂不切，先抽象 trace 接口，等 RAG/Hybrid 阶段再评估
5. **对 agent-eval-ops**：强烈建议直接基于 LangFuse 构建，省 6-8 周基建工作量

用户决定：**趁 Phase 3A 刚收口、Phase 3 未开工的窗口期，新增 Phase 3B 引入 LangFuse。** 本文档即为该阶段的执行计划。

### 关键文件索引

| 文件 | 作用 | 本阶段是否修改 |
|------|------|---------------|
| `engine/trace/recorder.py` | Trace 数据模型 + JSONL 写入 | ✅ 重构为抽象接口 + 双写 |
| `app/api/query.py` | `/api/query` 路由，`_record_trace()` 入口 | ✅ 注入 LangFuse trace |
| `app/core/config.py` | Settings 配置类 | ✅ 新增 LangFuse 字段 |
| `.env.example` | 环境变量模板 | ✅ 新增 LangFuse 配置项 |
| `eval/run_eval.py` | 评测执行器 | ✅ 增加 LLM-as-Judge 评分器 |
| `eval/scorers/` | 评分器模块（新目录）| ✅ 新建 |
| `engine/trace/langfuse_backend.py` | LangFuse 适配器（新文件）| ✅ 新建 |
| `domain_pack/metrics.yaml` | KPI 指标定义 | 📋 参考，不修改 |
| `docs/AI_CONTEXT.md` | 技术档案 | ✅ 更新当前状态 |
| `docs/AI_CONTEXT_CHANGELOG.md` | 变更记录 | ✅ 记录本阶段 |

---

## 阶段三B 总目标

1. **LangFuse 自部署**：在本机 Docker 上搭建 LangFuse 实例（PostgreSQL + LangFuse Server），可通过 `http://localhost:3000` 访问 Web UI
2. **Trace 后端抽象**：把 `append_trace()` 从 "只能是 JSONL" 重构为 "默认 JSONL + 可选 LangFuse" 的双写模式，调用方代码不改
3. **带 Span 的分步 Trace**：LangFuse trace 里用嵌套 span 表达 pipeline 的每一步（schema_retrieval → join_path → query_plan → sql_generation → sql_guard → sql_execution），替代当前扁平的 `TraceStep` 列表
4. **LLM-as-Judge 评分器**：新增 `eval/scorers/` 模块，实现 answer correctness、hallucination、faithfulness 三个语义评分器，通过调外部大模型做裁判
5. **评测链路打通**：`eval/run_eval.py` 跑完 cases 后，trace 自动出现在 LangFuse；评分结果通过 LangFuse Score API 回写到对应 trace
6. **为 agent-eval-ops 探路**：本阶段验证 LangFuse 的 trace/score/experiment 能力，确认可以作为独立评测项目的基座

### 非目标（明确不做）

- ❌ 不在本阶段开启 LangFuse Experiment（留着 agent-eval-ops 做）
- ❌ 不引入 LangFuse Prompt Management（当前 prompt 仍走 `domain_pack/` 文件）
- ❌ 不做 Dataset 管理 UI（继续用 YAML cases）
- ❌ 不把 LangFuse 作为生产强依赖（默认仍走 JSONL，LangFuse 不可用时自动降级）
- ❌ 不删除现有 JSONL 逻辑（保留作为本地兜底和轻量实验场景）

---

## 架构设计

### 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│                    /api/query                             │
│  app/api/query.py                                        │
│  _record_trace() ──→ TraceRouter ──┬──→ JSONLBackend     │
│                                     │    (eval/traces/)   │
│                                     │                     │
│                                     └──→ LangFuseBackend  │
│                                          (localhost:3000)  │
└──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────┐
│              LangFuse Server (Docker)                     │
│  ┌─────────┐  ┌──────────┐  ┌──────────────────────┐    │
│  │ Traces   │  │ Scores   │  │ Web UI (localhost:    │    │
│  │ (Spans)  │  │ (评分)    │  │   3000)               │    │
│  └─────────┘  └──────────┘  └──────────────────────┘    │
└──────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌──────────────────────────────────────────────────────────┐
│              eval/run_eval.py                             │
│  1. 跑 case → 调 /api/query → 拿到 trace_id              │
│  2. 规则评分 (contains/equals/expected_value)            │
│  3. LLM-as-Judge 评分 (correctness/hallucination/        │
│     faithfulness)                                         │
│  4. 评分结果写入 LangFuse Score API                      │
└──────────────────────────────────────────────────────────┘
```

### Trace Backend 抽象

```python
# engine/trace/recorder.py（重构后）

class TraceBackend(Protocol):
    """Trace 存储后端接口。
    
    当前实现：JSONLBackend（文件）、LangFuseBackend（Web）
    调用方只依赖这个协议，不关心底层是文件还是平台。
    """
    def record(self, record: TraceRecord) -> None: ...
    def close(self) -> None: ...  # 优雅关闭（flush 缓冲区）

class JSONLBackend:
    """当前的 append_trace 逻辑，保持完全兼容。"""
    def record(self, record: TraceRecord) -> None: ...
    def close(self, record: TraceRecord) -> None: ...

class LangFuseBackend:
    """把 TraceRecord 映射为 LangFuse trace + spans。"""
    def __init__(self, public_key: str, secret_key: str, host: str): ...
    def record(self, record: TraceRecord) -> None: ...
    def close(self, record: TraceRecord) -> None: ...

class TraceRouter:
    """根据配置决定写哪些后端：默认只写 JSONL，配置了 LANGFUSE 则双写。"""
    def __init__(self, backends: list[TraceBackend]): ...
    def record(self, record: TraceRecord) -> None:
        for backend in self.backends:
            try:
                backend.record(record)
            except Exception:
                # LangFuse 不可用时只记日志，不影响主链路
                pass
```

### TraceRecord → LangFuse Span 映射

当前 `TraceRecord.trace_steps: list[TraceStep]` 是扁平列表。映射到 LangFuse 时：

| TraceRecord 字段 | LangFuse 映射 |
|------------------|---------------|
| `trace_id` | trace.id（外部 ID） |
| `question` | trace.input |
| `answer` | trace.output |
| `route` | trace.metadata |
| `user_role` | trace.user_id / trace.metadata |
| `cost.latency_ms` | trace.metadata |
| `cost.prompt_tokens` / `cost.completion_tokens` | generation.usage（如有 LLM generation span） |
| `trace_steps[i]` | span（嵌套在 trace 下） |
| `trace_steps[i].name` | span.name |
| `trace_steps[i].step_type` | span.metadata |
| `trace_steps[i].latency_ms` | span 的 start_time / end_time |
| `trace_steps[i].input_summary` | span.input |
| `trace_steps[i].output_summary` | span.output |
| `trace_steps[i].status` | span.level（success/error） |
| `trace_steps[i].error_type` | span.status_message |

> ★ LangFuse trace 和 span 没有"固定 schema"——除了 input/output 外，其他业务字段（sql、tables_used、safety_status 等）全部放 metadata，不丢信息。

---

## 实施步骤

本阶段分 4 个 step，预计工作量约 1-2 天（碎片时间）。

### Step 1：LangFuse 自部署 + 环境配置

**目标**：在本地 Docker 上跑起 LangFuse，能打开 Web UI。

**操作要点**：

- 使用 LangFuse 官方 `docker-compose.yml`（含 PostgreSQL）
- 暴露端口 `3000`（Web UI）、`3030`（API，可选）
- 在 `.env` 中新增：

```env
# LangFuse self-hosted (Phase 3B)
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

- 在 `app/core/config.py` 的 `Settings` 中新增对应字段
- 更新 `.env.example`

**验收**：
- `docker compose up -d` 后 `http://localhost:3000` 能看到 LangFuse 登录/注册页
- `python -c "from app.core.config import get_settings; print(get_settings().langfuse_host)"` 输出正确

### Step 2：重构 trace 后端为可插拔架构

**目标**：把 `engine/trace/recorder.py` 的 `append_trace()` 变成 TraceBackend 协议 + TraceRouter，默认行为完全不变。

**改动文件**：

1. `engine/trace/recorder.py`：
   - 保留 `TraceRecord`、`TraceStep` 数据模型不动
   - 新增 `TraceBackend` 协议类
   - 把现有 JSONL 写入逻辑抽成 `JSONLBackend`
   - 新增 `TraceRouter`（管理多个 backend）
   - 模块级单例 `trace_router: TraceRouter` 按 Settings 初始化

2. `engine/trace/langfuse_backend.py`（新文件）：
   - `LangFuseBackend` 实现 `TraceBackend` 协议
   - 依赖 `langfuse` Python SDK（`pip install langfuse`）
   - `record()` 内把 `TraceRecord` 拆成 LangFuse trace + spans
   - 不可用时抛异常（由 TraceRouter catch + log）

3. `app/api/query.py`：
   - 把 `append_trace(record)` 替换为 `trace_router.record(record)`
   - 签名和行为完全不变

**验收**：
- `LANGFUSE_ENABLED=false` 时：行为与当前完全一致，trace 写入 JSONL
- `LANGFUSE_ENABLED=true` 时：JSONL 和 LangFuse 同时写入
- LangFuse 挂了：JSONL 仍正常写入，API 不返回 500
- 已有测试全部通过（`pytest tests/ -x`）

### Step 3：新增 LLM-as-Judge 评分器

**目标**：在 `eval/scorers/` 下实现三个能调外部大模型的评分器，评分结果通过 LangFuse Score API 写入。

**新建目录结构**：

```
eval/scorers/
  __init__.py           # 导出 scorer 注册表
  base.py               # Scorer 协议 + LLMJudge 基类
  correctness.py        # Answer Correctness 评分器
  hallucination.py      # Hallucination 评分器
  faithfulness.py       # Faithfulness 评分器（RAG 预留）
  factory.py            # 根据配置创建 scorer 实例
```

**评分器设计**：

| 评分器 | 输入 | 输出 | 评分逻辑 |
|--------|------|------|---------|
| Answer Correctness | question + answer + expected_answer | 0-1 分 + reason | LLM 判断回答是否与期望一致 |
| Hallucination | question + answer + sql + rows | 0-1 分 + reason | LLM 判断回答中是否有不存在于 rows 中的事实 |
| Faithfulness | question + answer + docs_used | 0-1 分 + reason | LLM 判断回答是否忠实于检索到的文档（RAG 预留）|

**关键设计决策**：

- ★ 评分器默认不启用 LLM-as-Judge（太贵 + 太慢），只在 `--judge-model` 显式指定时才走 LLM
- Judge 模型复用 Settings 中的 LLM 配置（默认 `LLM_PROVIDER`），也可单独指定 `EVAL_JUDGE_MODEL`
- 评分结果写入 LangFuse 作为 trace score（如果 LangFuse 可用），同时写入 EvalResult 的 issue_tags

**验收**：
- `python -m eval.run_eval --cases ... --judge-model deepseek-v4-pro` 跑完后能在 LangFuse Web UI 看到每条 trace 挂上了 score
- 规则评分结果也作为 score 写入（`rule:contains`、`rule:expected_value` 等）
- LangFuse 不可用时评分仍正常，只是不回写 score

### Step 4：文档收尾 + AI_CONTEXT 更新

**目标**：更新技术档案，确保下一轮 AI 会话能正确继承。

**改动文件**：

1. `docs/AI_CONTEXT.md`：
   - 「当前状态」section：更新为 Phase 3B
   - 「当前技术选型快照」section：补充 LangFuse 信息
   - 「最新事实快照」section：补充 LangFuse 默认值和配置

2. `docs/AI_CONTEXT_CHANGELOG.md`：
   - 记录本阶段的改动范围、关键决策、验收结果

3. `.claude/temp_work/phase3b-notes.md`（开发中记录）：
   - Docker 启动命令、初始账号密码、常见问题等

---

## 与独立评测项目（agent-eval-ops）的关系

Phase 3B 是 agent-eval-ops 的**前置探路阶段**。验证的核心问题：

| 问题 | 本阶段如何验证 |
|------|---------------|
| LangFuse API 是否稳定？ | 从 DataPilot 写入 trace + score，观察延迟和丢失率 |
| 自部署运维成本多高？ | 记录 Docker 资源占用、数据增长速率、备份需求 |
| LLM-as-Judge 评分质量如何？ | 人工抽查 10-20 条 judge 结果，统计与人工判断的一致性 |
| LangFuse SDK 是否好用？ | 实际写代码体验 `langfuse` Python SDK 的 API 设计和文档质量 |
| Experiment 功能是否满足需求？ | 浏览 Web UI，确认 Experiment 的工作流是否匹配 agent-eval-ops 的需求 |

本阶段验证通过后，agent-eval-ops 可以直接复用以下资产：
- LangFuse Docker 部署方案（docker-compose.yml）
- `engine/trace/langfuse_backend.py` 的 TraceRecord → LangFuse 映射逻辑
- `eval/scorers/` 的评分器实现
- `.env` 配置模板

---

## 风险与降级策略

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Docker 在本机不可用或性能差 | 低 | 阻塞 Step 1 | 用 LangFuse Cloud 免费层临时替代（但需考虑国内网络）；或先只做代码抽象，Docker 部署留到 agent-eval-ops |
| LangFuse SDK 与旧 Python 版本不兼容 | 中 | 阻塞 Step 2 | 确认 Python 3.10+ 兼容性后再 `pip install`；不兼容则降级为仅抽象接口，暂不接入真实 LangFuse |
| LLM-as-Judge 评分太慢/太贵 | 高 | 影响 Step 3 实用性 | 默认不启用；只在少数 diagnostic case 上用；judge 用便宜的模型（如 DeepSeek-V3）而非旗舰模型 |
| LangFuse 数据库膨胀 | 中 | 长期运行后磁盘满 | 设置 PostgreSQL 数据保留策略；trace 数据 30 天自动清理 |
| LangFuse 服务挂了 | 低 | trace 丢失 | JSONL 始终作为第一优先级写入；LangFuse 是"追加"不是"替代" |

---

## 单一事实源

- 阶段三B 执行计划：以 `docs/phase3b-langfuse-plan.md` 为准
- 阶段三A 执行计划：以 `docs/phase3a-plan.md` 为参考（已完成）
- 数据库当前事实：以 `docs/database-current-state.md` 为准
- 项目技术档案：以 `docs/AI_CONTEXT.md` 为准
- LangFuse 官方文档：https://langfuse.com/docs
- LangFuse 自部署指南：https://langfuse.com/docs/deployment/self-host

---

## 架构底线

### P0：不可降级

| 约束 | 验证方式 |
|------|---------|
| `/api/query` 响应契约不变 | `tests/` 全部通过，AgentResponse 字段不增不减 |
| JSONL trace 始终可写，不因 LangFuse 挂了而丢 trace | 手动停掉 Docker → 调 API → 检查 `eval/traces/traces.jsonl` 有新行 |
| `append_trace()` / `_record_trace()` 调用方代码不改 | `rg "append_trace\(" app/` 只出现在 recorder.py 内部，外部调用方已切换到 `trace_router.record()` |
| 规则评分 (contains/equals/expected_value) 行为不变 | `python -m eval.run_eval --cases eval/cases/phase3a-regression.yaml` 通过率不退化 |
| 不因本阶段引入新的必须依赖 | `pip install langfuse` 是可选的（`LANGFUSE_ENABLED=false` 时不需要） |

### P1：可简化，接口保留

| 简化方案 | 预留接口/字段 | 后续何时补 |
|----------|-------------|-----------|
| LangFuse Span 先不完美映射 TraceStep 的嵌套关系 | `TraceStep.parent_step_id` 保留 | RAG/Hybrid 阶段 pipeline 变复杂后补 DAG 化 span |
| LLM-as-Judge 先只实现 Answer Correctness | Hallucination/Faithfulness 类占位 | RAG 上线后补 Hallucination 和 Faithfulness |
| 评分结果先不自动回写 LangFuse Score（手动触发） | `EvalResult.score_value` 字段 | Step 3 验收后开启自动回写 |

---

## 后续衔接

Phase 3B 完成后，后续阶段的受益：

- **Phase 3 RAG（检索增强生成）**：LangFuse 上看 retrieval span → generation span 的全链路；RAG 专用评分器（faithfulness、context_relevancy）直接可用
- **Phase 3 Hybrid（混合推理）**：多步 Agent 的每一步都是独立 span，debug 时不用翻 JSONL
- **agent-eval-ops（独立评测平台）**：直接复用 LangFuse 部署 + Trace Backend 抽象 + Scorer 模块，从"搭建基础设施"变成"构建评测方法论"
