# M15 LangFuse Cloud 接入基线 notes

## Implementation checklist

- [x] 读取 M15 计划、AGENTS.md、AI_CONTEXT.md，确认本模块只做 Cloud / SDK / ID / Settings 基线
- [x] 复跑 LangFuse Cloud SDK smoke，不打印任何 key
- [x] 固定 `datapilot_trace_id` / `langfuse_trace_id` 双 ID 策略
- [x] 把 LangFuse / judge 配置纳入 Settings 与 `.env.example`
- [x] 增加 `observability` optional extra，保持默认链路不强依赖 LangFuse SDK
- [x] 删除 Settings 中遗留 LangSmith 字段并验证无业务引用

## 关键结论

- LangFuse Cloud region：`https://jp.cloud.langfuse.com`（从 `LANGFUSE_BASE_URL` 读取；业务代码不写死）
- Python SDK 基线：`langfuse==4.14.1`
- 关键 API：`Langfuse(...)`、`auth_check()`、`start_observation(trace_context=...)`、`create_score(trace_id=...)`、`flush()`、`api.trace.get(trace_id)`、`api.scores.get_many(trace_id=...)`
- SDK 4.14.1 没有旧版 `client.trace()` builder；M16 实现时应使用 `start_observation` / `create_event` 这组 4.x API
- `flush()` 只保证事件送达 LangFuse API，不代表 UI / query 绝对同步完成；本次 Cloud 查询实际约 `0.6s` 可见

## 双 ID 策略

- `datapilot_trace_id`：继续使用 DataPilot 当前请求级 UUID，服务 API 响应、响应头、JSONL 和 eval 报告
- `langfuse_trace_id`：最终选定由 DataPilot 使用 `uuid4().hex` 生成的独立 32 位小写 hex
- 原因：SDK 4.14.1 明确要求传入 trace id 为 32 位小写 hex；`uuid4().hex` 正好满足格式，且不会让 LangFuse 接管 DataPilot 请求级 trace id
- 映射方式：M16 写 LangFuse metadata 时保存 `datapilot_trace_id`，JSONL 中后续回填 `langfuse_trace_id` / `langfuse_trace_url` / `langfuse_write_status`

## Smoke 快照

- 脚本：`.agent_work/temp/smoke_m15_langfuse_sdk.py`
- trace name：`datapilot-m15-cloud-smoke-20260728T144148Z`
- LangFuse trace id：`a5b22262bb154b3a9b08b0b09b5f8cc5`
- trace URL：`https://jp.cloud.langfuse.com/project/traces/a5b22262bb154b3a9b08b0b09b5f8cc5`
- `auth_check=PASS`
- `observation_write=PASS`
- `score_write=PASS`
- `flush=PASS`
- 查询验证：`.agent_work/temp/check_m15_langfuse_visibility.py a5b22262bb154b3a9b08b0b09b5f8cc5`，`visible_after_seconds=0.6`，`score_count=1`

## 配置与依赖

- `pyproject.toml [project.optional-dependencies]` 新增 `observability = ["langfuse==4.14.1"]`
- 建议安装命令：`python -m pip install -e .[observability]`
- `LANGFUSE_ENABLED=false` 是默认值；未启用 LangFuse 时原 JSONL / API / eval 链路不应要求安装 optional extra
- `.env` 已补本地非敏感字段：`LANGFUSE_ENABLED=false`、`EVAL_JUDGE_MODEL=`
- `.env.example` 已新增 LangFuse Cloud 模板和 `EVAL_JUDGE_MODEL`

## Self-host 迁移记录

- DataPilot Phase 3B 不默认执行 self-host，也不要求 `docker compose up`
- 后续 EvalBench self-host 迁移时，重点重新验证 base URL、SDK/server 版本、project / trace URL 形态、数据保留策略
- 当前代码边界：连接信息只走环境变量；Cloud trace 是实验记录，不作为长期资产

## 验证命令

- `python .agent_work/temp/smoke_m15_langfuse_sdk.py`
- `python .agent_work/temp/check_m15_langfuse_visibility.py a5b22262bb154b3a9b08b0b09b5f8cc5`
- `python -m pytest tests/test_config.py --basetemp=.agent_work/temp/pytest-m15-config`
