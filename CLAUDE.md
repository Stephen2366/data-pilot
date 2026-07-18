# DataPilot

企业数据分析 Agent 系统。接受自然语言问题，自动判断查 SQL / 查文档 / 混合推理，生成结果 + 可视化 + 分析报告。

> **总路线**：[LEARNING_ROADMAP.md](D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP.md) — 总体规划。日常模块开发优先读 `CLAUDE.md / AGENTS.md`、`AI_CONTEXT.md` 和当前阶段计划文件（见 `AI_CONTEXT.md`「当前状态」）；阶段切换、范围调整或技术取舍等情况时再读完整 `LEARNING_ROADMAP.md`。
>
> **技术档案**：[AI_CONTEXT.md](docs/AI_CONTEXT.md) — AI 续接 / 查 bug 优先阅读，记录当前状态、决策理由、验证快照和已知坑。
>
> **学习复盘日志**：[dev-log.md](docs/dev-log.md) — 面向用户阅读，记录模块故事、关键概念和面试讲法。
>
> **参考资料速查**：[REFERENCE_GUIDE.md](D:/.Work/Practice/Python-Practice/references/REFERENCE_GUIDE.md) — 参考项目的定位、可借鉴点、不要照搬的坑。写代码时按场景查对应项目，不用通读。

## 用户背景
- **用户信息**：2028 届硕士研究生，计划 9 月开始集中投递 + 面试，目标 10 月找到 AI 应用开发 / Agent 开发 / 后端开发的日常实习。两个实践项目服务简历和面试
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
  router/               # 意图路由（SQL / RAG / 混合）
  nl2sql/               # NL2SQL 流水线
  sql_guard/            # SQL 沙箱安全
  rag/                  # RAG 知识库检索
  tools/                # Agent tools 封装
  trace/                # 全链路追踪

domain_pack/            # 业务配置，换行业只换这里
  schema_desc/          # 表结构描述
  sql_examples/         # NL2SQL few-shot 示例
  kb_docs/              # RAG 语料（退款政策、客服规则…）
  metrics.yaml          # KPI 定义
  chart_templates/      # 图表模板

eval/                   # EvalOps-lite（评测前置），完整评测平台在独立项目 agent-eval-ops
  cases/                # YAML 测试用例
  run_eval.py           # 批量执行入口
  scorers/              # 评分器
  reports/              # Markdown / HTML 报告
  traces/               # Agent 运行 Trace，默认不提交 JSONL

docs/                   # 项目文档
  archive/              # 旧版文档归档
  AI_CONTEXT.md         # 技术档案（AI 续接 / 查 bug 入口）
  dev-log.md            # 学习复盘（用户阅读）
  phase2-plan.md        # 阶段二模块计划（后续阶段计划也放这里）

demo/                   # Streamlit 演示页
scripts/                # 本地脚本，例如 seed 数据
tests/                  # pytest 测试
.agent_work/temp/       # AI 工具共享临时目录，不区分 Claude / Codex
```

## 开发环境

- Python: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe`

## 工作约定

- 所有 AI 工具共享同一个临时目录：`.agent_work/temp/`，用于存放脚本中间产物、一次性 JSON、缓存、临时 smoke 摘要等。
- 可复用运行数据不要放临时目录；Agent Trace 写入 `eval/traces/`。
- 路径、验收数字、Schema、命名只保留一个权威定义，优先登记在当前阶段计划文件的“单一事实源”章节。

## 代码风格

本项目代码服务新手学习、简历复盘和面试讲解，新增代码默认写新手友好注释。开发过程中先写核心注释；模块收工时调用 `finish-module` skill 统一查漏补缺。

注释基本要求：

- 覆盖完整，但不废话，内容简洁易懂。
- 适当用 ★ 标记关键点。
- 较长代码用 `# 描述 =====` / `# 描述 -----` 分隔步骤。

## 开发记录要求

- `AI_CONTEXT.md`（技术档案）：记录 git 和代码查不到的信息——决策理由、踩坑、验证结论等。顶部「当前状态」是模块进度唯一权威出处，「已知的坑」维护活跃列表，过期即删。
- `dev-log.md`（学习复盘）：面向用户，模块故事 + 新概念 + 面试讲法。
- 两者的详细模板和写作要求见 `finish-module` skill，模块完成后才调用该 skill 记录 `AI_CONTEXT.md` 和 `dev-log.md`。
- 开发中遇到关键决策/踩坑/验证命令/临时取舍，随手记入 `AI_CONTEXT.md`「补充记录」或 `.agent_work/temp/<module>-notes.md`，不要求格式——目的是给 `finish-module` skill 留素材。
- 配置修正、文档调整等小修复只更新 AI_CONTEXT「补充记录」，dev-log 不动，也不需要调用skill。
