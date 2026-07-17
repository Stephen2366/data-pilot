# DataPilot

企业数据分析 Agent 系统。接受自然语言问题，自动判断查 SQL / 查文档 / 混合推理，生成结果 + 可视化 + 分析报告。

> **总路线**：[LEARNING_ROADMAP.md](D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP.md) — 总路线、优先级、量化验收标准、兜底策略。日常模块开发优先读 `CLAUDE.md / AGENTS.md`、`AI_CONTEXT.md` 和当前阶段计划文件（见 `AI_CONTEXT.md`「当前状态」）；阶段切换、范围调整或技术取舍等情况时再读完整 `LEARNING_ROADMAP.md`。
>
> **技术档案**：[AI_CONTEXT.md](docs/AI_CONTEXT.md) — AI 续接 / 查 bug 优先阅读，记录当前状态、决策理由、验证快照和已知坑。
>
> **学习复盘日志**：[dev-log.md](docs/dev-log.md) — 面向用户阅读，记录模块故事、关键概念和面试讲法。
>
> **参考资料速查**：[REFERENCE_GUIDE.md](D:/.Work/Practice/Python-Practice/references/REFERENCE_GUIDE.md) — 参考项目的定位、可借鉴点、不要照搬的坑。写代码时按场景查对应项目，不用通读。

## 用户背景
- **用户信息**：硕士研究生（2028 届），计划 9 月开始集中投递 + 面试，目标 10 月找到 AI 应用开发 / Agent 开发 / 后端开发的日常实习。实践项目服务简历和面试
- **用户已学习技术栈**：Java / SpringBoot / MySQL / Redis / Python / FastAPI / LangChain-LangGraph / （讲解和注释时可用这些技术作类比）

## 目录结构

> 本节是项目目录结构的单一事实源，随开发演进更新；其他文档中的结构描述仅为示意或引用，新增 / 调整目录时先改这里。

```
app/                    # FastAPI 后端服务
  api/                  # HTTP 路由
  core/                 # 配置、日志、异常处理
  db/                   # SQLAlchemy engine、Session、Base
  models/               # 7 张业务表 ORM 模型
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
- 向量数据库：ChromaDB；Milvus 本地暂不可用（兼容性问题），阶段三 RAG 主路径按 ChromaDB 规划

## 工作目录约定

- 所有 AI 工具共享同一个临时目录：`.agent_work/temp/`，用于存放脚本中间产物、一次性 JSON、缓存、临时 smoke 摘要等。
- 可复用运行数据不要放临时目录；Agent Trace 写入 `eval/traces/`。

## 文档维护规则

- 路径、验收数字、Schema、命名只保留一个权威定义，优先登记在当前阶段计划文件的“单一事实源”章节。
- 修改口径时，先搜旧值，改完再搜一次；废弃口径再次出现就清理。
- 新计划少复述字面值，必须复述时标注“以单一事实源为准”。
- 已废弃口径：`.codex/temp_work`、`.claude/temp_work`、dev-log「当前状态速览」。

## 代码风格

本项目所有代码必须带详细注释，遵循以下规则：

- 注释覆盖完整（复杂或者非直观的地方都要加注释），但是内容要求简洁不啰嗦
- 通俗易懂，适合新手自学和面试复盘，适当用类比辅助理解，用 ★ 标记关键处
- 对于较长或者复杂的代码，需要添加分隔，大步骤用 `# 描述 =====`，小步骤用 `# 描述 -----`（描述必要时可添加序号`步骤 N：`和`步骤 N-M：`，每行总长度 100 个半角字符左右，使各行视觉对齐）

## 开发记录要求

记录分两个文件：

- `AI_CONTEXT.md`（技术档案，AI 续接 / 查 bug 用）。收录标准只有一条：记录 git 和代码里查不到的信息，比如为什么这么做、验证过什么、有什么坑等信息。
  - 顶部「当前状态」是模块进度的唯一权威出处（当前阶段计划文件、当前模块、阻塞项、更新时间）；「已知的坑」维护活跃列表，过期即删。
  - 模块完成时在「模块技术档案」头部新增一节，至少包括以下部分：改动范围（细节看 git）、关键决策（决策 + 理由）、参考资料（查了什么、借鉴了什么、没照搬什么；没查就写“未查阅外部参考”）、验证快照（实际跑过的命令结论一行版）、遗留。
  - 配置修正、文档调整等小修复记入「补充记录」，每条 1-3 行：改了什么、为什么、验证了什么。
- `dev-log.md`（用户阅读用，学习复盘）。模块完成时追加日志，至少包括以下部分：简述（含类比）、这次做了什么（故事体：动机 → 做法 → 结果）、我该理解什么（新概念逐条解释，适当用类比）、面试怎么讲、验证与下一步。以上是底线骨架而非上限：篇幅随模块复杂度伸缩，写到足够详细、通俗易懂为止。
  - 用新手友好语言，概念首次出现时加简短解释。讲到具体改动时可以点名关键文件（谁负责什么），让修改有实感，但完整文件清单以 AI_CONTEXT / git 为准；「验证与下一步」可附用户验收用的可复制命令块。
- 验证快照必须来自实际执行过的命令；没验证就写“未验证”。命令的分工：README 只放长期有效的项目运行命令（安装、启动、迁移、seed、跑测试），模块专属的验收命令放 dev-log「验证与下一步」，AI_CONTEXT 只留结论加指针。
- 模块完成必须两个文件都更新；小修复只更新 AI_CONTEXT「补充记录」，dev-log 不动。
