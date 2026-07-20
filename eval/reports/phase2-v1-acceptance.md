# DataPilot Phase 2 v1 Acceptance

- date: 2026-07-20
- scope: M1-M6 phase-two v1 closeout
- latest_eval_report: `eval/reports/latest.md`
- automated_smoke: 6/6 passed

## v0 Capability Checklist

| item | status | evidence |
|---|---|---|
| MySQL migration path | passed | Alembic head `20260717_0001`; M1-M5 收工验证均通过 `alembic check/current` |
| deterministic seed data | passed | users 50 / products 30 / channels 6 / orders 500 / refunds 80 / tickets 120 / knowledge_docs 8 |
| resource APIs | passed | products / orders / refunds / tickets list API, pagination, filters, unified errors |
| request logging | passed | `method / path / status / latency_ms / trace_id` in API logs |
| template SQL | passed | 5 high-value template questions via `/api/query` |
| SQL Guard v0 | passed | DDL / DML blocked with structured AgentResponse |
| 32-case plan | passed | `eval/cases_plan.md` is the Phase 2 case source of truth |

## v1 Capability Checklist

| item | status | evidence |
|---|---|---|
| NL2SQL minimal path | passed | M4 smoke: 5/6 simple SQL passed; M6 smoke simple cases passed |
| SQL Guard enhanced policy | passed | read-only AST, sensitive field block, role table allowlist |
| AgentResponse v1 | passed | cost, tool_calls, docs_used, chart_spec, error_type, trace_id |
| SQL Tool and JSONL Trace | passed | `/api/query` records tool calls and trace JSONL |
| chart_spec | passed | channel orders, refund rate, GMV produce Vega-Lite-compatible specs |
| EvalOps-lite | passed | `python -m eval.run_eval` writes `eval/reports/latest.md`; 6/6 passed |
| Streamlit demo | passed | `demo/streamlit_app.py` calls `/api/query` and renders answer / SQL / table / chart / trace |

## M6 Smoke Result

| id | type | status | note |
|---|---|---|---|
| sql_001 | simple_sql | passed | active products |
| sql_006 | simple_sql | passed | Mobile App channel |
| agg_001 | aggregation | passed | refund-rate highest product |
| agg_002 | aggregation | passed | channel order count |
| join_002 | multi_table | passed | channels + orders + refunds join |
| sec_001 | security | passed | DROP TABLE blocked |

## Boundaries

- RAG and hybrid questions are planned in `eval/cases_plan.md`, but no formal retriever is implemented in phase two.
- LangGraph orchestration, MCP integration, and Skill packaging are not implemented in phase two.
- Trace storage is JSONL by design for phase two; a database or external EvalOps platform can replace only the storage layer later.
- EvalOps-lite currently implements smoke-level checks: HTTP success, route, expected tables, expected columns, security expectation, and simple content checks.

## Phase Three Inputs

- Use `domain_pack/kb_docs/` and `knowledge_docs` as the first RAG corpus boundary.
- Extend `eval/cases/smoke.yaml` or add a separate YAML file for RAG / hybrid cases after retriever behavior is stable.
- Keep `/api/query` AgentResponse fields stable when introducing RAG docs and hybrid reasoning.
