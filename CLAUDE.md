# DataPilot

企业数据分析 Agent 系统。接受自然语言问题，自动判断查 SQL / 查文档 / 混合推理，生成结果 + 可视化 + 分析报告。

> **施工图纸（启动必读）**：[LEARNING_ROADMAP.md](D:/.Work/Practice/Python-Practice/LEARNING_ROADMAP.md) — 分阶段计划、P0-P3 优先级、量化验收标准、兜底策略、面试准备清单。**每次新会话启动后，在回答任何问题或执行任何操作之前，必须先 Read 这个文件。**
>
> **参考资料速查**：[REFERENCE_GUIDE.md](D:/.Work/Practice/Python-Practice/references/REFERENCE_GUIDE.md) — 10 个参考项目的定位、可借鉴点、不要照搬的坑。写代码时按场景查对应项目，不用通读。

## 目录结构（暂定）

```
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

demo/                   # Streamlit 演示页
```

## 开发环境

- Python: `D:\.Programs\Python\anaconda3\envs\fastapi0614\python.exe`

## 当前状态

🚧 阶段二 Week 2：DataPilot v0（7/16 周三）

本周目标：
- [ ] 7 张表 ER 图 + SQLAlchemy 模型 + Alembic 迁移
- [ ] 模拟数据生成脚本（含 RBAC users.role 字段）
- [ ] FastAPI 基础 CRUD 接口 + 统一日志/异常处理
- [ ] `eval/cases_plan.md` 32 条评测问题清单
- [ ] 模板 SQL 端到端跑通（硬编码 → sqlglot 检查 → 执行 → 返回）
- [ ] README 初版（ER 图 + 项目结构截图）
