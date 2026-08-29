# DataPilot 本地 MCP Adapter

这个目录把现有 FastAPI `/api/query` 包装成一个本地 `stdio` MCP Server。它只负责协议转换、网络合同校验和结果裁剪；Router、SQL、RAG、任务状态和权限判断仍由 Python 服务端负责。

## 能力边界

- 只暴露一个 Tool：`data_pilot_query`。
- 支持 `query`、`status`、`clear` 三种 operation；继续任务时必须使用上一次服务端返回的 `task_id` 和 `task_version`。
- Client 不能提交 role、tenant、model、corpus、RAG strategy 或 backend URL。
- 只连接无凭据的 loopback HTTP 地址，默认 `http://127.0.0.1:8000`。
- mutation 不自动重试；超时或响应合同漂移后的结果按 unknown 处理，需要显式执行 `status` 对账。
- 这是本地演示适配器，不是远程 MCP、生产认证或多租户方案。当前完成声明覆盖真实 SQL、协议和 task lifecycle；真实政策 RAG/Hybrid happy path 留给 `M51R`。

## 安装、构建与启动前置

在仓库根目录执行：

```powershell
npm ci
npm --workspace @datapilot/contracts run build
npm --workspace mcp run build
```

MCP Host 启动 adapter 前，FastAPI 必须已经在 loopback 地址运行。展示数据库的安全准备方式：

```powershell
python -m scripts.prepare_m50_demo preflight --confirm-database datapilot_demo
python scripts/run_m50_demo_api.py --rag-strategy pipeline
```

preflight 应显示 migration `20260827_0005`、7/8 月 oracle `120000.00/180000.00`、synthetic task rows `0/0` 和 `ready=true`。若 provider 需要本机代理，由操作员给 API 启动命令显式追加 `--proxy http://127.0.0.1:7897`；不要修改 `.env` 或让 MCP Client 选择 strategy。

## MCP Host 配置

Windows 上建议使用绝对路径，因为 Host 的工作目录不一定是仓库根目录。以下路径按本仓库当前位置填写：

```json
{
  "mcpServers": {
    "datapilot": {
      "command": "D:\\.Programs\\nodejs\\node.exe",
      "args": [
        "D:\\.Work\\Practice\\AI-Project\\data-pilot\\mcp\\dist\\index.js"
      ],
      "env": {
        "DATAPILOT_API_BASE_URL": "http://127.0.0.1:8000",
        "DATAPILOT_MCP_USER_ROLE": "ops",
        "DATAPILOT_MCP_TIMEOUT_MS": "310000"
      }
    }
  }
}
```

### Cursor

把上面的对象保存为项目根目录 `.cursor/mcp.json`。在 Cursor 的 MCP 设置中确认 `datapilot` 已启动，并且只列出 `data_pilot_query`。

### Claude Code / Claude Desktop

Claude Code 可在仓库根目录注册同一启动命令：

```powershell
claude mcp add datapilot -- "D:\.Programs\nodejs\node.exe" "D:\.Work\Practice\AI-Project\data-pilot\mcp\dist\index.js"
```

若使用支持本地开发 MCP 配置的 Claude Desktop 版本，可采用上面的 `mcpServers` 配置；新版 Desktop 也可能要求通过 Settings → Extensions 安装本地 DXT。界面和安装方式会随版本变化，应以 Anthropic 当前文档为准，本模块没有打包 DXT。

### MCP Inspector

Inspector 会自己拉起 stdio 子进程：

```powershell
npx @modelcontextprotocol/inspector "D:\.Programs\nodejs\node.exe" "D:\.Work\Practice\AI-Project\data-pilot\mcp\dist\index.js"
```

连接后进入 Tools，只应看到 `data_pilot_query`。可先调用：

```json
{
  "operation": "query",
  "question": "查询 2026 年 7 月实际净退款金额。"
}
```

## task 使用示例

首次查询由服务端创建 task：

```json
{
  "operation": "query",
  "question": "查询 2026 年 7 月实际净退款金额。"
}
```

继续查询必须回传刚收到的身份和版本：

```json
{
  "operation": "query",
  "question": "再查询 2026 年 8 月实际净退款金额。",
  "task_id": "<上一次返回的 task_id>",
  "expected_version": 1
}
```

若 mutation 结果未知，先只读对账：

```json
{
  "operation": "status",
  "task_id": "<task_id>"
}
```

清理时必须采用 status 或最近一次完整响应确认的版本：

```json
{
  "operation": "clear",
  "task_id": "<task_id>",
  "expected_version": 3
}
```

## 常见问题

- **Host 看不到 Tool**：先确认 `mcp/dist/index.js` 存在；直接执行 Node 命令时，stderr 应打印 readiness，进程随后等待 stdin。stdout 不能出现人类日志，否则会破坏 JSON-RPC。
- **连接本地 API 失败**：检查 `GET http://127.0.0.1:8000/health`，并确认环境变量没有指向 HTTPS、带凭据 URL、非 loopback 主机或带路径/query/hash 的地址。
- **返回 timeout/unknown**：不要重复原 query/clear；使用 `status` 查询服务端最终版本，再决定下一步。
- **返回 task version conflict**：使用最新一次完整 MCP result 或 status 返回的版本，不要自行加一。
- **结果被裁剪**：查看 `truncated` 计数。adapter 会优先删除 rows/citations，再压缩 answer/SQL，但保留四轴、reason、trace 和 task/version。

## 参考

- [MCP TypeScript SDK：Build your first server](https://ts.sdk.modelcontextprotocol.io/v2/get-started/first-server)
- [MCP TypeScript SDK：Plug into a real host](https://ts.sdk.modelcontextprotocol.io/v2/get-started/real-host.html)
- [Anthropic：Getting Started with Local MCP Servers on Claude Desktop](https://support.anthropic.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
