# DataPilot

企业数据分析 Agent 系统。接受自然语言问题，自动判断查 SQL / 查文档 / 混合推理，生成结果 + 可视化 + 分析报告。

> **总路线**：[LEARNING_ROADMAP.md](D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP_v3.md) — 总体规划。日常模块开发优先读 `CLAUDE.md / AGENTS.md`、`AI_CONTEXT.md` 和当前阶段计划文件（见 `AI_CONTEXT.md`「当前状态」）；阶段切换、范围调整或技术取舍等情况再读完整 ROADMAP。
>
> **技术档案**：[AI_CONTEXT.md](docs/AI_CONTEXT.md) — AI 续接 / 查 bug 优先阅读，只保留当前状态、默认配置、最新基线、关键结论和活跃坑；完整改动历史见 [AI_CONTEXT_CHANGELOG.md](docs/AI_CONTEXT_CHANGELOG.md)。
>
> **学习复盘日志**：[dev-log.md](docs/dev-log.md) — 面向用户阅读，记录模块故事、关键概念和面试讲法。
>
> **参考资料速查**：[REFERENCE_GUIDE.md](D:/.Work/Practice/Python-Practice/references/REFERENCE_GUIDE.md) — 参考项目的定位、可借鉴点、不要照搬的坑。写代码时按场景查对应项目，不用通读。

## 用户背景
- 2028 届硕士研究生，目标 10 月找到 AI 应用开发 / Agent 开发 / 后端开发的日常实习。项目服务简历和面试
- **已学习技术栈**：Java / SpringBoot / MySQL / Redis / Python / FastAPI / LangChain-LangGraph（讲解和注释时可适当用这些技术作类比）
- 用户使用 Claude Code 和 Codex 协作开发，项目 AGENTS.md 通过符号链接到 CLAUDE.md，从而实现文档同步

## 目录结构

> 本节是项目目录结构的单一事实源，随开发演进更新；其他文档中的结构描述仅为示意或引用，新增 / 调整目录时先改这里。

```
app/                    # FastAPI 后端服务
  api/                  # HTTP 路由
  core/                 # 配置、日志、异常处理
  db/                   # SQLAlchemy engine、Session、Base
  models/               # 业务表 ORM 模型
  schemas/              # Pydantic 请求 / 响应结构

alembic/                # 数据库迁移
  versions/             # Alembic migration 版本

engine/                 # 通用引擎，换行业不用改
  router/               # 意图路由（SQL / RAG / 混合）（暂无此文件夹）
  nl2sql/               # NL2SQL 流水线
  sql_guard/            # SQL 沙箱安全
  rag/                  # RAG 知识库检索
  tools/                # Agent tools 封装
  trace/                # 全链路追踪
  schema_retrieval/     # Schema 检索

domain_pack/            # 业务配置，换行业只换这里
  schema_desc/          # 表结构描述
  sql_examples/         # NL2SQL few-shot 示例
  kb_docs/              # RAG 语料（退款政策、客服规则…）
  metrics.yaml          # KPI 定义
  chart_templates/      # 图表模板

eval/                   # EvalOps-lite（评测前置），完整评测平台在独立项目 eval-bench
  cases/                # YAML 测试用例
  run_eval.py           # 批量执行入口
  scorers/              # 评分器
  reports/              # Markdown / HTML 报告
  traces/               # Agent 运行 Trace，默认不提交 JSONL

docs/                   # 项目文档（有时用户会自行把 `docs` 下的文档移入两个 archive 文件夹）
  archive-dormant/      # 存档1（暂时不用但以后可能复盘）
  archive-versions/     # 存档2（同文档的迭代链和不用的文档）
  AI_CONTEXT.md         # 技术档案（AI 续接 / 查 bug 入口）
  AI_CONTEXT_CHANGELOG.md # 技术档案完整变更记录 / 实验历史
  dev-log.md            # 学习复盘（用户阅读）
  database-current-state.md # 数据库 14 表现状、固定事实、指标口径速查
  phase3a-plan.md       # 阶段三A模块计划（历史；当前阶段计划见 AI_CONTEXT.md「当前状态」）
  phase3b-langfuse-plan-v6.md # 当前阶段（Phase 3B）计划文件


demo/                   # Streamlit 演示页
scripts/                # 本地脚本，例如 seed 数据
tests/                  # pytest 测试
.agent_work/temp/       # AI 工具共享临时目录，不区分 Claude / Codex
```

## 开发环境

- Python: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe`

## 工作约定

- 所有 AI 工具共享同一个临时目录：`.agent_work/temp/`，用于存放脚本中间产物、一次性 JSON、缓存、临时 smoke 摘要等。
- 可复用运行数据不要放临时目录：模块 smoke 脚本放 `scripts/`（如 `scripts/smoke_m2_api.py`），Agent Trace 写入 `eval/traces/`；smoke 的一次性输出摘要仍放临时目录。
- 路径、验收数字、Schema、命名只保留一个权威定义，优先登记在当前阶段计划文件的“单一事实源”章节。
- README 只在阶段结束时统一整理和更新。

## 开发素材与收工

- 开始较完整的模块开发时，先在 `.agent_work/temp/<module>-notes.md` 写几条 implementation checklist。
- 开发中遇到关键决策/踩坑/验证素材/临时取舍/判断与修正/实验结论/新发现等，先把素材写入 `.agent_work/temp/<module>-notes.md`。提前记录素材是为了供收工流程复用，防止后面记录日志时只能根据代码来。
- 模块开发完成后按两步收工：
  1. `finish-module`：注释查漏 + 运行验证 + 把决策取舍/验证快照/注释小结固化到 `<module>-notes.md`（开发刚结束时调用，上下文最新鲜）。
  2. `finish-docs`：基于固化的素材/对话记忆/代码，更新 `AI_CONTEXT_CHANGELOG.md` / `AI_CONTEXT.md` / `dev-log.md`（可稍后或跨会话执行）。
- 收工完成后用户人工查看验收；最终由 `accept-module` 做验收门禁。

## 代码风格

> 本节是注释规则的单一事实源。

新增 / 大幅修改的代码默认写新手友好的注释，基本要求：

- 语言：叙述用中文，术语等用中文和英文里更常用或顺口的
- 覆盖位置完整和全面：每个文件/类/函数的开头、复杂处、关键处、新手容易不熟悉处等
- 注释写给“未来准备面试的用户”读，包括但不限于解释：职责、设计理念、新概念、新手易混点等
- 注释内容：完整详细，通俗易懂，直击要点；适当用类比或比喻帮助理解
- 适当用 ★ 标记关键点
- 较长或复杂的代码需要添加分隔注释：大步骤 `# 描述 ==========`、小步骤 `# 描述 ----------`，必要时加序号 `步骤 N：`/`步骤 N-M：`

## 开发记录要求

- `AI_CONTEXT.md` 是 AI 续接技术档案，记录 git 和代码查不到的信息：当前状态、默认配置、评测基线、关键结论和活跃坑；保持短小，优先服务快速续接。

- `AI_CONTEXT_CHANGELOG.md` 保存完整变更记录、模块档案、真实 LLM eval、A/B 实验、smoke 结论和历史取舍。
  - 普通小修改如果会影响后续理解，就在 `AI_CONTEXT_CHANGELOG.md` 加一段简短记录；不记录文档整理、表达润色、无技术含义等修改。
  - 较完整模块开发、影响默认行为/安全口径/评测口径/架构边界的修改，才需要写结构化记录，建议包含：改动范围、关键记录（比如关键决策、实验结果、新发现）、参考资料、验证快照、遗留/后续。

- 跑过真实 LLM eval、A/B 实验、smoke，或者决定“不采用某方案 / 不切默认 / 不追某指标”时，必须同步到 `AI_CONTEXT_CHANGELOG.md`，并把会影响当前路线的最新结论摘要同步到 `AI_CONTEXT.md`「最新事实快照」。若新结论推翻或修正旧条目的判断，在旧条目处加一行 `⚠️ 注` 指向新结论，防止过时判断被误读。

- `dev-log.md` 面向用户学习复盘。

  
