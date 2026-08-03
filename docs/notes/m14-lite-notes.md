# M14-lite implementation notes

- Boundary: improve eval trust, LLM failure trace, security wording, diagnostic hygiene, and retrieval backend config.
- Do not chase diagnostic full score; stop before prompt/case-specific patches.
- Security decision: sensitive fields win over admin role; raw email/phone should be blocked for all roles.
- Keep Schema Retrieval default as inmemory + deterministic.
- Milvus/SiliconFlow must be explicit and must not affect pytest defaults.
- Use TDD: add focused failing tests before production changes.
- Related pytest: 54 passed, 1 existing Starlette/httpx warning.
- Full pytest: 84 passed, 1 existing Starlette/httpx warning.
- git diff --check currently blocked by pre-existing docs/dev-log.md trailing whitespace, not M14-lite code.
