# DataPilot

企业数据分析 Agent 系统。接受自然语言问题，自动判断查 SQL / 查文档 / 混合推理，生成结果 + 可视化 + 分析报告。

> **总路线**：[LEARNING_ROADMAP.md](D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP_v3.md) — 总体规划。日常模块开发优先读 `CLAUDE.md / AGENTS.md`、`docs/state/AI_CONTEXT.md`、当前阶段路线与约束文件，以及 `AI_CONTEXT.md` 指向的当前活动模块 plan；阶段切换、范围调整或重大技术取舍时再读完整总 ROADMAP。
>
> **技术档案**：[AI_CONTEXT.md](docs/state/AI_CONTEXT.md) — AI 续接 / 查 bug 优先阅读，只保留当前状态、默认配置、最新基线、关键结论和活跃坑；运行入口 / 模型链路 / LangFuse / eval 命令矩阵见 [runbook.md](docs/state/runbook.md)，完整改动历史统一从 [CHANGELOG_INDEX.md](docs/state/CHANGELOG_INDEX.md) 进入，长期评测账本见 [eval-baselines.md](docs/state/eval-baselines.md)，数据库状态速查见 [database-current-state.md](docs/state/database-current-state.md)，RAG / 知识库状态速查见 [rag-current-state.md](docs/state/rag-current-state.md)。
>
> **状态文档阅读规则**：`docs/state/AI_CONTEXT.md` 只是续接仪表盘。凡涉及运行命令、模型 / embedding / LangFuse 开关、eval 数字或失败归因、数据库事实、历史取舍，必须按 `AI_CONTEXT.md`「必读规则」继续读取对应 state 文档；其中运行入口必须读 `docs/state/runbook.md`，不能只读 AI_CONTEXT 摘要后执行。
>
> **学习复盘日志**：[dev-log.md](docs/dev-log.md) — 面向用户阅读，记录模块故事、关键概念和面试讲法。
>
> **参考资料速查**：[REFERENCE_GUIDE.md](D:/.Work/Practice/Python-Practice/references/REFERENCE_GUIDE.md) — 参考项目的定位、可借鉴点、不要照搬的坑。写代码时按场景查对应项目，不用通读。

## 用户背景
- 2028 届硕士研究生，目标 10 月找到 AI 应用开发 / Agent 开发 / 后端开发的日常实习，DataPilot 项目服务简历和面试
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
  harness/              # 顶层单轮 LangGraph Harness（M35）
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
  state/                # AI 续接 / 排障状态事实源
    AI_CONTEXT.md       # 技术档案（AI 续接 / 查 bug 入口）
    CHANGELOG_INDEX.md # 技术历史唯一入口与跨阶段路由
    change-history/    # 按 Phase 拆分的模块档案、实验和取舍
    runbook.md          # AI / 本地运行入口，模型、检索、LangFuse、eval 命令矩阵
    eval-baselines.md   # 长期评测基线、A/B 结果、失败结构和错因账本
    database-current-state.md # 数据库 14 表现状、固定事实、指标口径速查
    rag-current-state.md # RAG 知识原件、运行基线、外部语料与评测证据边界速查
  notes/                # 模块计划与过程素材库（mX-plan.md / mX-notes.md）
  ref-discussion/       # 网上技术讨论原文收集（未筛选素材）
  dev-log(M0-M19).md    # 用户学习复盘（M0~M19）
  dev-log.md            # 用户学习复盘（M20以后）
  module-plan-template.md # 模块计划模板（新模块开工时复制为 docs/notes/<m>-plan.md）


demo/                   # Streamlit 演示页
scripts/                # 本地脚本，例如 seed 数据
tests/                  # pytest 测试
.agent_work/temp/       # AI 工具共享临时目录，不区分 Claude / Codex
```

## 开发环境

- Python: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe`

## 工作约定

- 所有 AI 工具共享同一个临时目录：`.agent_work/temp/`，用于存放脚本中间产物、一次性 JSON、缓存、临时 smoke 摘要等。
- 可复用运行数据不要放临时目录：模块 smoke 脚本放 `scripts/`（如 `scripts/smoke_m2_api.py`），Agent Trace 写入 `eval/traces/`，eval 报告（report / triage / compare）写入 `eval/reports/`，开发过程中的 notes / 实验 / 审查等 写入 `docs/notes/`（见「开发素材与收工」）；smoke 的一次性输出摘要仍放临时目录。
- 当前阶段的能力顺序和长期边界以阶段 roadmap 为准；当前模块合同和验收以独立 `<module>-plan.md` 为准；运行配置、Eval、数据库和索引事实分别以对应 state 文档为准。模块 plan 只引用这些事实源，不复制形成第二份权威定义。
- README 只在阶段结束时统一整理和更新。

## 开发素材与收工

- 开始较完整的模块开发时，先在 `docs/notes/<module>-notes.md` 写几条 implementation checklist。
- 开发中遇到关键决策/踩坑/验证素材/临时取舍/判断与修正/实验结论/新发现等，先把素材写入 `docs/notes/<module>-notes.md`。提前记录素材是为了供收工流程复用，防止后面记录日志时只能根据代码来。
- 模块开发完成后调用`finish-module` 收工。

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

- `docs/state/AI_CONTEXT.md` 是 AI 续接技术档案，记录 git 和代码查不到的信息：当前状态、默认配置、评测基线、关键结论和活跃坑；保持短小，优先服务快速续接。
- `docs/state/CHANGELOG_INDEX.md` 是 changelog / 技术历史的唯一入口。无论写入小修、模块档案、实验，还是查询以前的设计和结论，都必须先读索引，再进入其指定的 Phase 文件；禁止绕过索引直接猜测目标文件。
  - 普通小修改如果会影响后续理解，就在索引指定的当前 Phase 文件增加简短记录；不记录文档整理、表达润色、无技术含义等修改。
  - 较完整模块开发、影响默认行为/安全口径/评测口径/架构边界的修改，才需要写结构化记录，建议包含：改动范围、关键记录（比如关键决策、实验结果、新发现）、参考资料、验证快照、遗留/后续。
- 跑过真实 LLM eval、A/B 实验、smoke，或者决定“不采用某方案 / 不切默认 / 不追某指标”时，必须先读 `docs/state/CHANGELOG_INDEX.md`，再同步到索引指定的当前 Phase 文件，并把会影响当前路线的最新结论摘要同步到 `docs/state/AI_CONTEXT.md`。若新结论推翻或修正旧判断，按索引定位旧条目并在原位加一行 `⚠️ 注`。

## 长时间命令与余额控制

- 开发过程中优先运行与当前改动直接相关的测试；允许在当前轮等待，但应设置合理等待时间并稀疏检查，禁止高频心跳轮询。
- 测试失败后优先修复并重跑相关失败用例，不立即重复运行完整测试。
- 完成全部代码修改后，完整测试、完整 Eval、构建或数据处理任务如果预计超过 2 分钟，使用后台进程运行，不进行 AI 心跳轮询。
- 后台任务必须将日志、退出码和完成标记写入 `.agent_work/temp/`。
- 后台任务启动后，向用户报告命令、PID、日志路径、完成标记路径和检查方法，然后结束当前回复。
- 用户稍后要求检查时，再读取一次退出码、结果摘要和必要的失败信息。
- 后台验证尚未完成或结果尚未检查时，不宣称模块完成。
- 相关代码和验证条件未变化且已有可信结果时，不重复验证。
