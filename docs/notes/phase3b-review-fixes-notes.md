# Phase3B review fixes notes

- 2026-07-30: 用户确认按 `docs/phase3b-code-review-findings.md` 修复；P2-2 采用方案 B：把危险 SQL 预检下沉到 pipeline/tool 的统一 guard 边界，而不是在 API 层补临时 TraceStep。
- 本轮只处理 Phase3B code review findings，不扩大到 RAG/Hybrid 或 EvalBench 平台化。
