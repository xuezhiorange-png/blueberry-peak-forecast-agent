# V0.18 S1 身份提供方与 BFF 适配评审 R1

TASK_ID=V0_18_S1_IDENTITY_AND_GRANT_AUTHORITY_PREFLIGHT_R1
基线 `52b5a80f89c59130917b29c9097d63076eab4acb`
评审日期：2026-10-10
范围：`DESIGN_AND_ADAPTATION_REVIEW_ONLY`

## 结论先行

仓库当前没有可核实的企业身份提供方、OIDC issuer、应用注册、用户登录回调、BFF 会话或最终用户 Principal 映射。代码搜索只确认了 V0.17 的服务器配置型 Trial actor 与独立 MCP ServiceAccount。**公司是否已有可用企业 SSO/OIDC：`UNVERIFIED`，不是“没有”。** 现阶段不能配置 issuer 或假定某个 OAuth client、租户、群组声明或密钥已获批准。

条件性首选是“经验证的企业 OIDC 提供方 + 同源 BFF + 服务器端会话”。若 Owner/IT 不能提供合格的企业 issuer 和运维责任人，备选是独立运行的 OIDC 提供方（例如 Keycloak）并采用同一 BFF 模式；这会新增 IdP 本身的高可用、升级、备份、密钥轮换和账户生命周期责任。当前两项都未配置，二者均不是已交付能力。

S1 的身份验证必须产生可信的 `END_USER` Principal，但身份认证本身不授予任何基地、区域、公司或历史质量权限。具体提供方、BFF 托管边界、账户映射责任人及授权发布者仍需 Owner 决策；S1 生产实施未获授权。

## 现有实现适配审查

| 现有组件 | 已确认行为 | 可复用部分 | 不能据此声称 |
| --- | --- | --- | --- |
| `ActualHarvestActorContext` / `TrialActorDep` | `get_actual_harvest_actor()` 从服务器 `TRIAL_ACTOR_*` 环境变量建立单个 actor；缺少/错误配置返回 503。身份字符串、source system、channel 与 capability 是服务器配置，不是浏览器用户登录结果。 | 可保留既有 `may_read_forecast`、`may_read_quality` 等能力名，供受控兼容适配使用。 | 不能识别当前最终用户，不能证明 issuer/subject，也不能区分同一 API 上的多个真实用户或他们的组织范围。客户端传 actor 字段不可信。 |
| V0.17 S1 HTTP | 六个 GET 路由依赖 `TrialActorDep` 和 `ForecastIntelligenceReadService`；`_permission()` 在路由函数体中调用。Service 依赖包含 `get_db_session`。现有测试验证权限拒绝时没有调用预测 repository 或读取历史 quality evidence。 | 六项响应模型、S1 服务、现有 capability 语义及 fail-closed 的不可用状态保持不变。 | 当前合同不是 OIDC；现有测试证明已覆盖用例下无 repository/evidence 读取，不等于已存在逐用户资源 ACL，也不证明任意未来路由都能先于业务 session 进行 grant 校验。SQLAlchemy session 对象可能先被依赖创建；业务查询必须继续由测试计数证明为零。 |
| V0.17 S2 HTTP | Business Loss、simulate、compare 复用 S1 read service；三个路由使用相同 Trial actor capability。模拟在得到预测曲线后才调用 S2/S6。 | S2 请求/响应、synthetic cost 和冻结的计算/排名结果完全不变；`may_read_forecast` 仍是旧兼容 capability。 | `may_read_forecast` 不足以授权任何具体 run、成本选择或组织；主体认证和逐记录权限不能在前端补做。 |
| V0.17 S3 MCP | 独立 MCP ASGI 使用服务器配置的 `ServiceAccount`、必填 `X-Forecast-Intelligence-Key`、exact `RunGrant` 和独立 `QualityGrant`；工具参数不能自授权限。 | 8 个工具名称、Pydantic 输入输出、服务调用、payload/hash、Quality 独立 grant 和服务账号精确 grant 可保持。 | ServiceAccount 是调用方，不是豆包中的终端用户；现有自定义 header 不是 OAuth 用户委托 token，也不传递最终用户身份。 |
| V0.17 Dashboard | React Dashboard 通过同源 HTTP client 读取 API；技术人员入口可输入完整保存身份后由 S1 校验。 | 五页、UI 状态、数据 schema 和服务器权威数值保持。 | 输入完整 identity/hash 只证明请求选择了哪些字段，不是认证、授权、组织成员资格或 grant。当前没有正常的登录/授权 run discovery 后端。 |

现有 S1/S2 路由在调用 service 之前检查旧 capability，但路由依赖图中 service/session 与 actor 是并列依赖，并非一个显式 `AuthorizedPrincipal → authorized context → business session/repository` 的依赖链。即使当前 session 创建通常不会立即执行 SQL，也不把这一实现细节当作访问控制保证。未来授权适配必须把可信身份和 exact grant 验证放在业务读取依赖之前，并对业务 SQL、quality 文件读取、模拟次数分别设置拒绝前计数断言。

## 候选架构比较

### 候选 A：企业托管 OIDC + 同源 BFF（条件性推荐）

**前提**：公司实际拥有并批准一个 OIDC issuer；IT/安全团队提供 issuer/discovery、tenant、应用注册及回调白名单、client 身份验证方式、token/API audience 规则、账户停用/群组生命周期支持、联系人和 SLA。上述条件尚未核实。

**流程**：浏览器只访问同源 Dashboard/BFF。BFF 以 confidential web client 启动 OIDC Authorization Code + PKCE（S256），使用一次性、与浏览器会话绑定的 `state`/`nonce`，完成 code 交换和 ID Token 验证；随后将 `(issuer, subject)` 映射成内部 `principal_id`，创建高熵不透明服务器会话。浏览器只持有 `Secure; HttpOnly; SameSite=Lax; Path=/` 的会话 cookie（可用 host-only `__Host-` 前缀）；ID/access/refresh token 留在服务器端，不进入 JS、URL、Dashboard storage 或日志。对 POST 等不安全方法使用服务器 CSRF token，并校验允许的 Origin；SameSite cookie 不是唯一 CSRF 控制。BFF 会话建立/权限变化时轮换 ID，退出、账户停用或 grant revision 变化时撤销/失效。

**优势**：复用公司已有账户和 MFA/停用生命周期（仅在实际支持并核实后）；浏览器不接触 bearer token；HTTP 与 Dashboard 可在单一同源信任边界工作，降低跨域和客户端密钥暴露面。

**限制/风险**：企业 issuer、claims、tenant 与外部回调审批未知；上游 outage、密钥/JWKS 轮换和账户禁用传播需要明确 fail-closed 与可用性合同；BFF 引入服务器会话存储/清理、CSRF、代理信任和注销语义。仅从可信域名或 email domain 自动推导公司/基地权限会产生跨组织授权风险，禁止。

**维护成本**：中等。平台团队维护 BFF、会话密钥、回调、session store、监控/撤销；企业 IdP 运维由公司既有团队承担（前提未证）。

**建议**：只有在 DECISION-01 的 issuer/app registration 和运营负责人被书面确认后，作为首选实施；否则不启用登录、不允许 anonymous fallback。

### 候选 B：独立部署 OIDC 提供方 + 同源 BFF（企业 IdP 不可用时的备选）

**前提**：Owner 批准单独部署与运行 IdP，指定安全/平台值守、用户邀请/停用/恢复责任、MFA 策略、域名/TLS、密钥保护、备份恢复、升级窗口、事件响应和成本预算。Keycloak 仅为可评估的开源例子，不代表仓库或公司已经部署它。

**流程**：新 OIDC issuer 取代候选 A 的企业 issuer，应用侧仍使用同一 confidential BFF、Authorization Code + PKCE 和会话合同。最小上线不允许任意自注册或只按邮件域自动纳入组织；账户须由受信任管理员显式开通，身份验证与业务资源 grant 分开审批。若以后用 Keycloak federation/broker 接入企业 IdP，仍须验证双方 issuer/subject 稳定性、账户 link 和组织 membership 规则。

**优势**：可控 issuer、claims、client、会话策略和联调环境；可以先用隔离合成数据验证完整 OIDC/BFF 流程。

**限制/风险**：自行托管不自动建立可信员工名册、组织关系或授权流程；自助注册、email 自动关联/合并、域名自动入组、管理账号被盗都可能扩大访问范围。它增加一个身份系统本身的关键安全面和可用性依赖。

**维护成本**：高于候选 A。需持续运维 IdP、数据库、密钥、升级/安全公告、日志、备份恢复、HA、故障响应与账户生命周期。仅将 IdP 装到测试容器不构成生产能力。

**建议**：仅在公司没有合格企业 issuer 且 Owner 批准长期运维责任时考虑；没有业务身份管理员时，该选项仍是 BLOCKER，不以“能登录”替代授权。

### 候选 C：浏览器 SPA 直接 OIDC/OAuth（不推荐）

浏览器可用 Authorization Code + PKCE，但 access token 会进入浏览器运行环境，必须处理 XSS、跨域 CORS、token 暴露、刷新和各 API audience。它不解决资源 grants，亦不能让 MCP 的服务账号自动变成最终用户。由于本产品已有 BFF/同源 UI 需求且涉及敏感预测范围，不作为首选；只有 BFF 运行约束经 Owner 与安全评审确认不可接受时才重新评估，不作为现在的默认退路。

| 维度 | A：企业 IdP + BFF | B：独立 IdP + BFF | C：SPA 直接 PKCE |
| --- | --- | --- | --- |
| 可信身份来源 | 公司可核验的 issuer（目前 UNVERIFIED） | 自建 issuer；账户创建者/员工关系必须另行治理 | 同 A/B，但 tokens 暴露给浏览器运行时 |
| 依赖条件 | IT issuer、tenant、client、回调与停用/撤销机制 | 专责 IdP 运维、生命周期、MFA、备份恢复 | Provider CORS、前端安全基线、token 生命周期 |
| 资源授权 | 需独立 grant 服务 | 需独立 grant 服务 | 需独立 grant 服务 |
| 主要风险 | 未核实 claims/停用传播；误信 email/group | 账户治理薄弱、IdP 运维失误、注册扩大范围 | XSS/token theft、CORS/刷新与多 API audience 复杂度 |
| 维护成本 | 中 | 高 | 中高且安全边界下沉浏览器 |
| 评审意见 | 条件性首选 / PENDING_OWNER_DECISION | 条件备选 / PENDING_OWNER_DECISION | 非首选 / 不默认启用 |

## OIDC 与会话验证合同建议

以下为实施前需冻结的安全检查，不是当前运行配置：

1. 只接受显式配置的 HTTPS issuer 精确值；验证 discovery `issuer` 与 ID Token `iss` 完全相同，不能只比 host 或 email domain。使用受信任 JWKS 验证签名与算法白名单，安全处理 key rotation；未知/错误 issuer 或算法 fail closed。
2. 每次登录交易绑定单次 `state`、PKCE `S256` verifier 和 OIDC `nonce`；精确匹配注册 redirect URI，不允许由 query param 决定跳转目标。验证签名、`iss`、`sub`、`aud`（必须含本 client ID）、需要时 `azp`、`exp`、`iat`，提供方若发出 `nbf` 则检查；请求时使用 nonce 必须比较 ID Token nonce。不能把 ID Token 当 API bearer。
3. OIDC 授权成功只回答“哪个 issuer 的哪个 subject 完成认证”；不能凭 token 中未经批准的组织、email、用户名、display name、`source_system` 或客户端参数授予 forecast scope。
4. BFF 使用随机不透明 session id，session record 在服务器侧关联内部 principal、issuer-session 元数据、签发/过期和授权 revision。登录/提权轮换 session id；cookie 不设置跨站 Domain；应用 API 不回传 OIDC token。读请求使用 `Cache-Control: private, no-store`；浏览器缓存按用户切换清空。
5. OIDC callback 的 `state`/PKCE 保护协议跳转；应用的 unsafe methods 另用 CSRF 防护。若多 issuer，加入 issuer mix-up 防护；redirect URI 精确 allowlist、Host/proxy 明确可信，绝不接受任意 `X-Forwarded-*`。
6. 登录、会话、JWKS、principal registry 或授权目录任一必要安全配置缺失时拒绝服务，不降级到旧 Trial actor、匿名、任意 Header 或 MCP key。认证失效返回不包含资源信息的 401；认证有效但 Principal disabled/无 grant 时统一拒绝，不查询业务数据。
7. 撤销/停用时长、session idle/absolute TTL、refresh-token 使用、MFA/step-up、审计留存及 IdP outage 可用性尚无 Owner 决策。没有该数据时不得宣称即时撤销或指定具体 SLA。

这些合同依据当前规范基线：OAuth 2.0 Security BCP 要求保护 redirect flow、精确 redirect URI 和 PKCE；OIDC Core 定义 issuer/subject/audience/expiry 与 nonce 验证；HTTP MCP Authorization 规范把客户端授权绑定到特定 MCP resource/audience，并要求 MCP 服务端拒绝给其他 resource 签发的 token。规范合规不等于当前应用已经实现。

参考资料：

- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OpenID Connect Core 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-core-1_0-errata2.html)
- [MCP Authorization, protocol revision 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [Keycloak Server Administration Guide, identity brokering reference](https://www.keycloak.org/docs/26.8.0/server_admin/)

## Principal 映射建议

Human Principal 采用服务器注册的不可变内部随机 `principal_id`。外部身份唯一键为区分大小写的 `(issuer, subject)`；OIDC `sub` 在 issuer 内唯一，邮箱/用户名可变且不可作为主键或账户自动合并依据。首次映射、issuer 迁移、重复 identity 合并必须由指定身份管理员审核。记录中保存 principal type、状态、映射 revision 与最小审计元数据，不复制不必要的个人资料。

`END_USER` 与 `SERVICE_ACCOUNT` 使用不同的 principal type 和认证方式，不得共用登录 cookie、credential namespace 或可互相伪装的 actor 输入。服务账号身份来源为服务端注册/密钥或受标准协议保护的机器身份，不能通过浏览器 cookie 登录；最终用户 token 不得作为普通 service account key 透传。没有受 MCP 客户端支持的 user-delegation flow 时，八项 MCP 工具继续以 S3 的 ServiceAccount 和 exact grants 工作；只报告“服务账号授权范围”，**终端用户隔离验收为 BLOCKED**，不得把 MCP 用户名/提示词当身份。

MCP 官方 HTTP Authorization 规范定义的是 client 代表 resource owner 向受保护 server 请求，并要求 resource/audience 绑定、每次 HTTP 请求附 token；它并不证明具体“豆包工作助手”版本、部署模式或公司 IdP 已支持该流程。需在 S3 阶段用真实客户端版本与批准的测试 issuer 完成发现、授权、撤销和 token 受众验证。当前实际兼容性：`UNVERIFIED`。不得由此扩大本轮范围或加入第九个 MCP 工具。

## S1 适配建议与边界

在 Owner 选定 Provider 和 mapping owner 后，S1 可以单独提案以下非实现模块（名称为候选）：

- `backend/app/auth/oidc_bff.py`：可信 code-flow callback/session 边界，不包含业务授权。
- `backend/app/auth/principal_registry.py`：`issuer+subject → internal principal_id` 的可审计映射。
- `backend/app/forecast_intelligence/resource_authorization.py`：共享 capability + exact resource grant 决策。
- API 路由认证适配依赖：S1/S2 route 先通过认证、capability 与 grant，再构造访问业务 repository/service 的依赖。
- 独立 HTTP/MCP adapter：把可信 HTTP session principal 或已验证 MCP user token 转为同一内部 authorization context。MCP 在客户端委托未证实前不启用这条分支。

不建议把 OIDC 解析散落于 `trial.py`，也不修改 V0.16 math、S1/S2 response/payload/hash、八个工具名称/计算结果或 V0.17 历史 evidence。旧 Trial 与 legacy MCP 既有合同仍需兼容；但保护新路径不自动隔离旧路径。安全试运行必须在网络层默认拒绝旧 Trial/MCP 端点对受限客户端的访问，并用实际路由/网络测试证明，不能只靠前端隐藏菜单。

S1 只可实施 Owner 后续明确批准的身份、内部 Principal 和共享授权基础，不做 S2 的已授权 saved-run 列表/分页/cursor/handoff，不做 Dashboard selector，也不部署。身份 Provider、BFF 托管及资源 grant publisher 均未批准前，生产实现 gate 保持关闭。
