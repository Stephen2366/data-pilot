# DataPilot

企业数据分析 Agent 系统。接受自然语言问题，自动判断查 SQL / 查文档 / 混合推理，生成结果 + 可视化 + 分析报告。

> **总路线**：[LEARNING_ROADMAP.md](D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP.md) — 总路线、优先级、量化验收标准、兜底策略。日常模块开发优先读 `CLAUDE.md / AGENTS.md`、`dev-log.md` 当前状态和 `phase2-plan.md` 当前模块；阶段切换、范围调整或技术取舍等情况时再读完整 `LEARNING_ROADMAP.md`。
>
> **进度和日志**：[dev-log.md](dev-log.md) — 记录了当前完成状态和下一步计划。
>
> **参考资料速查**：[REFERENCE_GUIDE.md](D:/.Work/Practice/Python-Practice/references/REFERENCE_GUIDE.md) — 参考项目的定位、可借鉴点、不要照搬的坑。写代码时按场景查对应项目，不用通读。

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

demo/                   # Streamlit 演示页
scripts/                # 本地脚本，例如 seed 数据
tests/                  # pytest 测试
.agent_work/temp/       # AI 工具共享临时目录，不区分 Claude / Codex
```

## 开发环境

- Python: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe`

## 工作目录约定

- 所有 AI 工具共享同一个临时目录：`.agent_work/temp/`，用于存放脚本中间产物、一次性 JSON、缓存、临时 smoke 摘要等。
- 可复用运行数据不要放临时目录；Agent Trace 写入 `eval/traces/`。

## 文档维护规则

- 路径、验收数字、Schema、命名只保留一个权威定义，优先登记在plan文档的“单一事实源”章节。
- 修改口径时，先搜旧值，改完再搜一次；废弃口径再次出现就清理。
- 新计划少复述字面值，必须复述时标注“以单一事实源为准”。
- `dev-log.md` 只记录实际验证结果；没验证就写“未验证”。
- 已废弃口径：`.codex/temp_work`、`.claude/temp_work`。

## 代码风格

本项目所有代码必须带详细注释，遵循以下规则：

- 注释覆盖完整（复杂或者非直观的地方都要加注释），但是内容要求简洁不啰嗦
- 通俗易懂，适合新手自学和面试复盘，适当用类比辅助理解，用 ★ 标记关键处
- 对于较长或者复杂的代码，需要添加分隔，大步骤用 `# 描述 =====`，小步骤用 `# 描述 -----`（描述必要时可添加序号`步骤 N：`和`步骤 N-M：`，每行总长度 100 个半角字符左右，使各行视觉对齐）

## 开发记录要求

- `dev-log.md` 顶部维护“当前状态速览”，每次追加日志时同步更新当前模块、下一步和阻塞项。
- 完成 `phase2-plan.md` 中每个模块里程碑后，必须在 `dev-log.md` 末尾追加一条开发日志；模块日志标题加 ★ 前缀，与补充记录区分。
- 日志不要写成流水账，要服务于后续 README、简历和面试复盘，日志用新手友好的语言，概念首次出现时加简短解释。
- 每条日志至少包含：
  - 日期与模块
  - 做了什么：列出核心交付物、涉及文件、可运行能力
  - 技术决策：说明为什么这样选型
  - 参考资料：列出依赖的文档、参考项目、外部文章等，方便后续追溯。如果查了 `references/` 项目，写清楚信息
  - 验证结果：记录实际跑过的关键验证结果，以及用户能直接复制的验证命令
  - 面试怎么讲：用 2-4 句话提炼成可对面试官讲清楚的项目亮点
  - 遗留问题 / 下一步：下一个模块要做什么、当前有哪些风险
- 如果只是配置修正、补充、文档调整或小修复等，不算完整模块，也可以追加“补充记录”。补充记录保持精简，写清楚：改了什么、为什么改、验证了什么、是否影响下一步。不要强行展开完整模块字段；内部小节不用 `###` 标题，用 `**改动**` 这样的加粗行即可。
