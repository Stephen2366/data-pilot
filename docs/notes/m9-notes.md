# M9 Schema Retrieval 与 JoinPath notes

- [x] 方案确认：用户选择选项 A，M9 使用 deterministic in-memory vector index，保留 Milvus adapter 边界，不新增 `pymilvus` / Docker / 网络依赖。
- [x] TDD：先写 `tests/test_phase3a_schema_retrieval.py` 红灯，再实现 `engine/schema_retrieval/*`。
- [x] Schema docs：从 `DomainSchema` 和 `relations.yaml` 生成 `field_doc` / `metric_doc` / `relation_doc` 三类文档。
- [x] Retriever：输出 `keyword_hits`、`vector_hits`、`merged_hits`，每条 hit 带 `score/source/rank/doc_type`。
- [x] SchemaGraph：从命中结果补齐相关表字段、指标和 JoinPath，Join 条件只来自 `relations.yaml`。
- [x] 诊断：跑 10 条 formal、16 条 challenge、32 条 diagnostic 中 schema / join capability 的召回摘要。
- [x] 验证：跑 M9 聚焦 pytest、必要旧测试、`git diff --check`。

## 验证素材

- 红灯：`pytest tests\test_phase3a_schema_retrieval.py ... pytest-m9-red` 失败于 `ModuleNotFoundError: No module named 'engine.schema_retrieval'`，符合 TDD 预期。
- 绿灯：`pytest tests\test_phase3a_schema_retrieval.py ... pytest-m9-tmp` 6 passed，1 个既有 Starlette/httpx warning。
- 相关回归：`pytest tests\test_phase3a_eval.py tests\test_phase3a_schema_retrieval.py ... pytest-m9-related` 19 passed，1 个既有 warning。
- 全量回归：`pytest ... pytest-m9-full-rerun` 50 passed，1 个既有 warning；第一次 120 秒超时停在 `tests/test_m3_query.py` 中途，改 300 秒复跑通过。
- `git diff --check`：无 whitespace error，仅 `relations.yaml` Windows LF→CRLF 提示。

## 关键决策素材

- Milvus 边界：本模块只实现协议和未配置时报错的 adapter 占位，不声明真实 Milvus 可用；后续阶段三 RAG 或 M12 README 再补真实 adapter smoke。
- 关系来源：JoinPath 优先消费 `domain_pack/schema_desc/relations.yaml`，不依赖 Markdown 自然语言关系猜测。
- 关系补齐：`relations.yaml` 原缺 `refunds.order_id -> orders.id`、`refunds.product_id -> products.id`、`refunds.user_id -> users.id` 三条结构化关系；这些已在 `refunds.md` 中存在，本模块补入 YAML，保证退款相关 JoinPath 不靠自然语言猜测。
- 召回素材：详见 `.agent_work/temp/m9-recall-summary.md`。
