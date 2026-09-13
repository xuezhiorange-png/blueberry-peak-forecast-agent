# Area forecast Streamable HTTP inbound P1

TASK_ID=NEXT_VERSION_AREA_FORECAST_DOUBAO_STREAMABLE_HTTP_TRANSPORT_P1

Base main: `a06fa373b4ef7c70895dd0e9d0efdffc540020d4`。
范围仅新增 inbound transport 与配置 runbook；不注册豆包，不部署公网。

## Reuse and boundaries

EXISTING_MCP_INFRASTRUCTURE=backend.app.mcp.area_forecast.server
EXISTING_TOOL_REGISTRY=existing five Server callbacks/schema contracts
EXISTING_MCP_TRANSPORT=stdio
REUSED_COMPONENTS=Server, product/application/repository, shared database settings/session factory
NEW_MINIMAL_COMPONENTS=POST-only ASGI adapter, SecretStr configuration, exact URL mounts

固定路径 `/api/v1/blueberry/v1/mcp/sse`，alias `/api/v1/blueberry/v1/mcp`。
同一 Server 提供全部五个工具；未改 `area_forecast.py` 或 `persisted_runs.py`。
没有新增数据库 engine、业务 schema、migration、预测/幂等/lineage/cursor/error 算法。
使用 SDK 公共 stateless JSON session manager，适配 SDK 2.x，而非重建 MCP 协议。

冷库参考与豆包配置步骤见 [runbook](../runbooks/doubao-work-partner-mcp.md)。
参考 repo main 在只读审计时为 `ae9794d0454fa64ba7db6a94d9a3faeba5df00bd`。

## Acceptance

真实 authority、正常 configured PostgreSQL/actor、无 dependency override，使用实际
uvicorn TCP `127.0.0.1:8011`。默认 8000 当时被占用，未终止/修改原服务。
隔离本地验收 DB 新建 run 1；不是生产 run 或豆包线上注册。

- missing Accept initialize / list / alias 均为完整 JSON，5 tools。
- stateless Python、REST、CLI、stdio、Streamable HTTP payload/hash 一致且不写库。
- create 重复执行及 REST/CLI/stdio create 全部复用同一执行身份，仅 207 child rows。
- 停止本次临时 backend，移除其 authority 配置并重启；get/list/daily 与 REST、CLI、
  stdio 保持 parity；forecast/create 正确返回 authority unavailable。
- 总量 `484802.055989 kg`，207 days；daily sum `484802.055987 kg`，差
  `-0.000002 kg`，现有 Decimal tolerance 内 mass balance PASS。
- result hash `6d406e8a4a436b2c9bf347dca5f52b3f9b048ea4fb1602405225fc4f2ac39d1b` 未变。
- execution hash `1523fdbcd9f5ff702ff5462acc6baeca15f7987bc9cfa9924c811fd6989c0b89`。

私有受控产物目录 `blueberry-area-yield-artifacts/streamable-http-p1/`：
parity.json、saved-run.json、schemas.json。不提交模型/原始 XLS/完整业务日曲线。
聚合验收及 SHA256 见 [evidence](evidence/area-forecast-streamable-http-p1.json)。

## Tests

新增测试先执行得到 endpoint 404，然后实现 adapter。发现测试端 health URL 与 CLI daily
envelope 差异后按既有合同修正测试，未修改业务行为或削弱结果 parity。
协议、共享密钥、错误脱敏、真实 TCP/PostgreSQL、并发 create、五路 stateless 与四路
saved-run parity 均本地执行；既有 stdio discovery/schema hash tests 保持不变。
最终相关回归：**1001 passed / 140 warnings**（PostgreSQL enabled）；Ruff check、
format check（1023 files）、Mypy（440 source files）、JSON/reference/hash/diff 均 PASS。

```bash
APP_ENV=test RUN_POSTGRES_INTEGRATION=1 uv run pytest backend/tests/mcp -q
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/app
git diff --check
```

PostgreSQL tests 需要已有测试角色/数据库与正常 POSTGRES_* 配置；网络测试仅创建并删除
自己生成的隔离 fixture database，不删除验收数据。JSON notifications 的 202 不属于
initialize/list/call 有 ID 请求的 200 JSON 验收。

CI 以最终 exact HEAD 的 PR terminal verification receipt 为准；不会把本地测试或旧
#620 CI 当成该 PR 的 CI。保持 Draft。

FORECAST_MATH_CHANGED=false
PERSISTENCE_SCHEMA_CHANGED=false
MIGRATION_CHANGED=false
MCP_TOOL_CONTRACT_CHANGED=false
DOUBAO_RUNTIME_REGISTRATION=NOT_EXECUTED
DOUBAO_WORK_ASSISTANT_READY=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
RELEASE_AUTHORIZED=false
FINAL_STOP_GATE=COORDINATOR_AREA_FORECAST_DOUBAO_STREAMABLE_HTTP_TRANSPORT_P1_REVIEW
