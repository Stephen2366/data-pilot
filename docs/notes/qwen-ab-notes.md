# Qwen A/B Notes

- 目标：先接 Qwen 主模型和 Qwen embedding 的可选实验路径，不改变 DataPilot 默认 DeepSeek / in-memory。
- 主模型第一轮：`deepseek-v4-pro` 对比 `qwen-plus`，固定 deterministic schema retrieval。
- Embedding 第一轮：固定 DeepSeek 主模型，对比 Milvus + SiliconFlow `BAAI/bge-m3` 与 Milvus + DashScope `qwen3.7-text-embedding`。
- `qwen3.7-text-embedding` 先只用 dense 1024 维；sparse / instruct 留给后续单独实验。
- 输出文件统一放 `.agent_work/temp/qwen-ab/`，不覆盖 `eval/reports/phase3a-*.md`。
- `.env` 中 `DASHSCOPE_API_KEY` 字段名可用；代码新增 `DASHSCOPE_BASE_URL`、`DASHSCOPE_EMBEDDING_BASE_URL`、`QWEN_MODEL`、`QWEN_EMBEDDING_*`。
- embedding 组依赖本地 Milvus 可用；如果未启动，脚本会在该组 eval 失败，不影响主模型 A/B 代码路径。
