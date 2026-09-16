# 豆包工作伙伴：蓝莓 MCP Streamable HTTP

本手册是配置交接，不是已完成豆包注册或正式公网部署的证明。
`DOUBAO_RUNTIME_REGISTRATION=NOT_EXECUTED`，`DOUBAO_WORK_ASSISTANT_READY=false`。

## 后端与地址

复用 `backend.app.mcp.area_forecast.server`（`blueberry-area-forecast`）的十个工具。
stdio 与 HTTP 使用同一个 server、schemas、annotations、错误映射及业务服务。
不增加预测数学、训练、数据库表或迁移。

当前正式工具包括：

- `forecast_blueberry_by_area`（无副作用的 stateless forecast）
- `create_blueberry_area_forecast_run`、`get_blueberry_area_forecast_run`、
  `list_blueberry_area_forecast_runs`、`get_blueberry_area_forecast_daily`
- `create_blueberry_operational_peak_forecast_run`、
  `get_blueberry_operational_peak_forecast_run`、
  `list_blueberry_operational_peak_forecast_runs`、
  `get_blueberry_operational_peak_forecast_daily`
- `search_blueberry_operational_bases`（只读基地发现）

安装仓库锁定依赖，按已有数据库配置与迁移流程准备 PostgreSQL，然后启动：

```bash
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

`backend/Dockerfile` 默认端口也是 8000。若已有进程占用端口，不要终止未知进程；
可明确指定其他本地验收端口，并同步调整 origin。
开发验证用后端 origin；不要指向前端。后续 HTTPS 反向代理或经单独授权的验收
tunnel 必须指向后端端口。临时 tunnel 不是正式部署方案，本任务未开启公网 tunnel。

正式路径（无尾斜杠）：

- `POST /api/v1/blueberry/v1/mcp/sse`
- alias：`POST /api/v1/blueberry/v1/mcp`

两者均为 **Streamable HTTP / JSON response / stateless**。
initialize → tools/list → tools/call 全部 POST 到同一个 URL。
请求有 ID 时返回完整 `application/json`，不维持 SSE 长连接；协议 notification
可返回 202，无结果 body。不要求 session ID，不需要 GET 事件流；GET 返回 405。
alias 直接处理 POST，不依赖 trailing-slash redirect。

## 服务端配置

- `POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`：
  使用已有 settings/session factory，禁止放进工具参数。
- `AREA_YIELD_AUTHORITY_PATH`、`AREA_YIELD_AUTHORITY_SHA256`：服务端已有 hash-pinned
  authority；仅 stateless forecast 与 create 需要。历史 get/list/daily 不读取它。
- `BLUEBERRY_MCP_CONNECTOR_SHARED_SECRET`：可选共享密钥。设置后，每个 MCP POST 必须带
  `X-Blueberry-Connector-Key`，缺失/错误/重复 header 均返回 401。密钥不返回给客户端。
  未设置或空值仅适用于受控本地开发/验收；在对外可达的 origin 上必须先设置密钥并
  保护 TLS/网络入口。此 gate 不是 OAuth、用户身份或多租户 RBAC。

MCP stdio 不使用 HTTP connector key，原命令不变：

```bash
uv run python -m backend.app.mcp.area_forecast
```

## 豆包 UI 填写

按本任务确认的冷库接入路径：

豆包工作伙伴 → 技能 → 工具 → 添加工具 → 自定义工具 → 添加自定义 MCP 工具。

- 传输方式：**Streamable HTTP**。
- 请求地址：`https://<ORIGIN>/api/v1/blueberry/v1/mcp/sse`。
- 如果配置了密钥，Header：`X-Blueberry-Connector-Key: <secret>`。
- 不需要额外配置 Accept；Content-Type-only 或 `Accept: */*` 由薄传输层补 JSON。

不要选 SSE；不要填 bare origin；不要填 REST forecast URL；不要上传 OpenAPI；
不要等待 `event: endpoint`；不要 POST `/messages/`。
本任务没有实际登录豆包 UI，租户真实注册/可达性仍需后续单独验收。

## 本地协议自检

下面命令适用于未启用密钥的受控本地模式；启用时添加上述 connector header。

```bash
curl -sS http://127.0.0.1:8000/api/v1/blueberry/v1/mcp/sse \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"doubao-acceptance","version":"0.1"}}}'

curl -sS http://127.0.0.1:8000/api/v1/blueberry/v1/mcp/sse \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

curl -sS http://127.0.0.1:8000/api/v1/blueberry/v1/mcp/sse \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"forecast_blueberry_by_area","arguments":{"farm":"保山杨柳农场","productive_area_mu":"393.4","target_season":"2026-2027","season_start":"2026-10-15","season_end":"2027-05-09","as_of":"2026-09-12"}}}'
```

initialize/list 均应 HTTP 200，list 含十个工具。call 通过 `result.structuredContent`
读取原有业务 payload；工具错误仍在 HTTP 200 JSON-RPC result 内带 `isError=true`，
不可仅根据 HTTP 200 判断预测成功。

## 最小技能 routing

| 用户意图 | 工具 |
| --- | --- |
| 只要求预测 | `forecast_blueberry_by_area`（不写库） |
| 明确要求预测并保存/正式留档 | `create_blueberry_area_forecast_run` |
| 基地名称或 ID 不完整/不确定 | `search_blueberry_operational_bases` |
| 问历史列表 | `list_blueberry_area_forecast_runs` |
| 指定 run_id 查完整结果 | `get_blueberry_area_forecast_run` |
| 指定 run_id 查每日曲线 | `get_blueberry_area_forecast_daily` |

自然语言理解由豆包负责，后端不解析聊天原文。预测面积必须是 Decimal string，
不得填写 yield/model/authority/database override。未知农场、缺紧邻上一产季历史仍
fail closed，不恢复 Global fallback。list 的 filters、opaque cursor、20/100 分页
上限继续沿用已有合同。create 可选 rerun 仍只允许同 canonical farm/season/window。

请求错误、unsupported history、authority unavailable、not found、rerun scope conflict、
integrity failure、persistence failure 保持原机器码。数据库故障不会被称为 authority
错误；不向客户端暴露 SQL、连接串、文件路径、密钥或原始异常。历史工具不重新预测。
operational peak create 接受精确注册 `base_id` 或精确 canonical base name；部分名称或
未知名称应先调用 `search_blueberry_operational_bases`，搜索只返回候选，不自动选择。
搜索仅覆盖 server-owned authority 中的 active bases，采用 NFKC、trim、casefold 后的
精确/子串匹配，不做 fuzzy、拼音、地理或 LLM 匹配。

## 架构来源与验收

直接参考 cold-storage `ae9794d0454fa64ba7db6a94d9a3faeba5df00bd`：

- `backend/src/cold_storage/modules/aily/api/mcp_sse.py`
- `docs/tasks/V1_1-P5-aily-mcp-sse-contract.md`
- `docs/runbooks/v11-doubao-aily-connector.md`

蓝莓 SDK 2.x 的 `Server.run` 已不提供旧版 `stateless=True` 参数。
本实现使用同一 SDK 的公开 `StreamableHTTPSessionManager(stateless=True,
json_response=True)`，其内部创建无 session ID/event store 的 JSON transport，并处理
每次 POST 的生命周期与取消。没有复制冷库工具或其 legacy SSE 路径。

验收记录：[Streamable HTTP P1](../next-version/area-forecast-streamable-http-p1.md)。
