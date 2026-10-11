# V0.18 S0 简化本地认证补充合同 R1

## 身份、授权与生效状态

TASK_ID=V0_18_S0_SIMPLIFIED_LOCAL_AUTH_SCOPE_ADDENDUM_R1

VERSION=0.18.0

VERSION_NAME=BUSINESS_USABILITY_AND_SAFE_PILOT_FOUNDATION

基线：`6fb43c92c874de45c773f27c50d44cbe51835bc8`；最新正式 Release：`v0.17.0`。

Owner 已确认首期使用管理员创建的本地账号密码、ADMIN / BUSINESS_USER、独立业务资源授权和服务器会话。本文件是 **ADDENDUM 候选**，不是运行实现，也不是对历史 S0 的覆盖。原始版本名称、阶段编号、业务目标、质量路线图和历史批准事实保持不变。

`OWNER_AUTH_DIRECTION_CONFIRMED=true`；`S0_ORIGINAL_FORMAL_COMPLETE=true`；
`S1_PREFLIGHT_FORMAL_COMPLETE=true`；`S0_ADDENDUM_DRAFT_AUTHORIZED=true`；
`S0_ADDENDUM_FORMAL_APPROVAL_PENDING=true`；`S1_RUNTIME_AUTHORIZED=false`；
`LOCAL_AUTH_IMPLEMENTED=false`；`PRODUCTION_READINESS=NOT_READY`。

生效必须依次完成本补充合同的独立 exact-head 审核、Owner 明确 Ready/Merge 授权、合并及对应 main CI 成功。Draft CI 成功不代表补充合同已正式生效；生效也不授权 S1 生产开发。本执行快照以后不回填批准状态，后续治理事件独立记录。

实时核验 #710、#711、#712、#714 已合并，各自 push CI 成功。#714 合并提交为上述基线，push CI #38102232994 completed/success（4 success / 8 workflow-skipped）。它记录方案评审完成，不记录认证运行完成。正式完成身份来自 Owner 本次确认；本次 API 返回 #714 reviews/comments 为空，不编造独立 GitHub Review ID。来源字节在新 JSON 和离线测试中绑定。

## 逐项兼容与替代矩阵

下表的“替代”均为本补充合同待批准的修订，不修改旧文件，不将旧 OIDC 推荐写成错误或已实施。

| 原条款 / 技术前提 | 首期补充合同 | 不变约束 / 审批状态 |
| --- | --- | --- |
| S0 OIDC 方向、S1 企业 issuer 或独立 Keycloak 候选 | 不再作为首期实施前提；采用管理员 provisioning 的本地账号密码 | 可信身份仍必需；禁止匿名、共享默认账号和公开注册；替代待本补充合同正式批准 |
| trusted issuer + subject → Principal | 服务端密码认证后的 account_id → 不可变、不可复用的服务器 principal_id | 用户名不是权限主键；客户端 actor / source_system 不可信；END_USER 与 SERVICE_ACCOUNT 分离 |
| Authorization Code + PKCE、issuer/audience/nonce 和上游 tokens | 首期无 OIDC/OAuth 登录 flow，不配置伪 issuer 或 token 验证 | 保留 HTTPS、同源受控会话、Cookie、CSRF、登录失败限制与账号撤销；未来 OIDC 必须重新授权 |
| 同源 BFF 保存 IdP tokens | 保留同源服务器会话边界，不建设复杂 IdP token BFF 集成 | 浏览器不持机器凭据；会话不可伪造、可撤销；服务端授权不能下沉为隐藏菜单 |
| OWNER_TRUSTED_ISSUER_AND_POLICY_PUBLISHER_DECISION（S1 前提） | 替换为 OWNER_LOCAL_ACCOUNT_AND_POLICY_PUBLISHER_DECISION，加 ADDENDUM_FORMAL_COMPLETE | 账号/Principal 管理及组织主数据、grant 发布/审批责任仍须 Owner 指定；不是删除 publisher gate |
| 版本化可信配置优先、Schema 另行批准 | 管理员可管理账号/角色/资源授权；持久化位置与 Schema 不在本轮选定 | 不自动批准独立 IAM 平台、新表、迁移或 grant 管理 API；配置或存储必须有 revision、撤销和审批 |
| exact-run grant | 实体范围作为额外限制/管理分组，与完整 exact-run identity/hash 绑定同时成立 | 不扩大历史/未来记录权限；详细规则见下节 |
| CLIENT_DELEGATION_PROTOCOL_COMPATIBILITY（S3 前提） | 首期替代为 SERVICE_ACCOUNT_EXACT_GRANT_SAFETY_ACCEPTANCE | S1/S2 formal 依赖不变；新 gate 待测，不标 PASS；用户委托未验证、未实现、排除首期 |
| USER_CLIENT_RUN_SCOPE_INTERSECTION（S3 验收） | 首期验证 service principal、明确 client 边界、exact run/Quality grants 与共享判定一致 | 不声称用户权限交集或最终用户隔离通过；未来委托仍需原用户/客户端/记录交集及独立批准 |
| 全 IAM 管理排除项 | S1 内最小账号新增、禁用、管理员重置、角色及授权配置，具体界面/API 待批准 | 不建设企业 IAM、公开注册或新的 Dashboard 一级业务页；不能以管理权限绕过数据 ACL |

未列为替代的前提全部继续有效。旧 OIDC issuer 未核实状态、历史推荐、历史 S1_AUTHORIZED=false 等快照原样保留。

## 本地账号、角色、会话合同

账号由指定管理员创建，无公开注册、共享默认账户或生产测试凭据。服务端生成稳定 account_id 和不可复用 principal_id；用户名规范化、改名、账号删除与新建不得重用 Principal 或自动继承原授权。只有成功的服务器密码验证和有效服务器会话可以解析 END_USER；客户端输入身份只是待验证请求字段，不是信任凭证。

密码必须为安全的带盐自适应哈希，不得明文或可逆存储。具体维护中的库、参数、密码/重置策略、Session idle/absolute TTL、随机性与存储 Schema 留待单独 S1 实施合同。管理员重置不得暴露旧密码；重置、禁用、退出及必要权限撤销必须使相关会话失效。会话建立/权限变化应防 fixation，账号状态及 revision 每请求重新核验。

浏览器 Cookie 使用 Secure、HttpOnly、明确 SameSite 策略及受控域/路径，HTTPS 强制；不在 URL、localStorage、DOM 或日志存认证凭据。服务器 CSRF 防护、Origin/可信代理边界、登录失败限制、错误脱敏和基本审计必需；SameSite 不能单独替代 CSRF。缺失必要配置默认拒绝。

角色恰好 ADMIN、BUSINESS_USER。ADMIN 管账号、角色和业务授权配置；管理动作本身仍需经过服务器校验及审批/审计。ADMIN 不自动拥有任何 forecast 或 Quality grant；BUSINESS_USER 只使用显式获准能力。组织边界、主数据 owner、授权审批人和紧急撤权责任不能从用户名、记录创建人或实体名称推断。

## 实体范围与 exact-run 兼容合同

访问的必要条件是：有效 Principal ∩ capability ∩ 经批准组织/层级/实体范围 ∩ 经批准 exact-run binding，随后 canonical integrity 校验。BASE、REGION、COMPANY 各自独立；任一层级不自动授权上下级；COMPANY/REGION aggregate 独立批准，不能由当前 registry 重建历史授权或 hierarchy。

每条范围必须明确 principal_type/id、organization_scope、capability、hierarchy_level/entity_id、forecast_family、target_season、source_kind、baseline_id、policy_version、来源 authority/version、有效期、grant_revision、撤销和审批来源。没有可核实组织/实体权威数据时默认无授权。

范围不是“该基地所有记录”。首期保守规则：仅允许可信发布者显式批准的 exact-run allowlist；每个 binding 包含 source_kind、forecast_family、run_id、hierarchy_level、entity_id、target_season、origin_date、baseline_id、policy_version、expected_source_result_hash，并继续校验来源 authority/version。知道 hash 只证明完整性，不授予权限。历史记录需逐条批准；rerun 新 identity 需独立批准；source/hash/policy/version 漂移不能自动改 grant 或回退旧结果。

未来记录自动纳入策略=`PENDING_OWNER_DECISION`；当前 `FUTURE_RUN_AUTO_ENROLLMENT_ALLOWED=false`。实体授权不得默认覆盖未来或其他 season/family 的记录。未来若批准安全的 catalog 自动发布规则，必须另行冻结过滤边界、可信发布者、版本化审批与 exact binding 生成规则，不由前端或全库 latest 扩展权限。

历史 Quality grant 独立绑定 model、split、season、scope 和 evidence policy/hash，不继承 forecast 权限，也不授予 current-season actual 权限。新 discovery 仅查询批准 allowlist 内元数据，过滤先于分页，signed cursor/handoff 绑定 Principal/client/revision/identity/hash；handoff 不是 bearer authorization。

## 授权与撤销：继续保留的安全规则

认证与授权目录元数据可读取；在 capability、组织边界和完整资源 grant 验证前，敏感预测 repository/日行/Quality evidence 读取及模拟执行计数都必须为 0。未授权已存在与不存在记录同一脱敏拒绝，不先查询存在性；只有匹配有效 grant 后才允许 canonical read，删除可返回授权主体 404，漂移 409 且不返回冲突数据。

`PRE_RESPONSE_GRANT_REVISION_RECHECK=true`，并重新核验 Principal active。读取或模拟开始不锁定永久权限；请求中撤权、禁用或版本变更时，返回前丢弃已失效敏感结果，不向原主体发送。该要求 **尚未实现**，必须由未来 S1 并发/撤销测试证明，离线文本测试不是运行安全验收。

撤销使相关服务器缓存、cursor、handoff、Dashboard 已选上下文及必要会话失效；缓存不得跨 Principal/revision 复用，私有响应禁止共享缓存。撤销传播目标、重置策略、审计留存待批准。新登录不能降级回旧 Trial actor；旧 Trial/MCP 路由在未来 pilot 前须授权适配或网络默认隔离且实测，当前隔离未验证。

## MCP 首期 gate 的可验证定义

首期仅 SERVICE_ACCOUNT_ONLY + EXACT_RUN_GRANTS + INDEPENDENT_QUALITY_GRANTS。八个工具名称、输入输出、Decimal、业务数学/hash、不可用状态不变；HTTP/Dashboard END_USER 与 MCP machine Principal 不混淆，也不假设 service key 代表豆包最终用户。

SERVICE_ACCOUNT_EXACT_GRANT_SAFETY_ACCEPTANCE 必须在 S3 单独授权后实测：强制非空独立凭据、安全轮换、HTTPS/Host/Origin、账号/client 固定范围、每个 BASE/REGION/COMPANY exact grant 独立、Quality 独立、拒绝前零业务读/模拟、canonical hash 与响应前 revision 复核、并发不串权、旧入口无绕过、八工具与 HTTP 相同合法业务 payload/hash。当前状态 `PENDING_NOT_EXECUTED`。

原 CLIENT_DELEGATION_PROTOCOL_COMPATIBILITY 不被标 PASS，只在首期服务账号范围以该新 gate 待批准替代。最终用户委托=`NOT_IMPLEMENTED_UNVERIFIED_EXCLUDED_FIRST_RELEASE`；最终用户 MCP 隔离不能验收通过。如以后启用，重新批准协议/issuer/audience/撤销与用户∩client∩记录交集，不从本轮推断。

## 阶段目标与完整依赖

阶段名称保持原 S0 机器合同，以下仅补充实施方向，全部需单独 Owner 实施授权、独立评审、Ready/Merge 和 main CI。

| 阶段 | 目标 | 依赖 / 额外前提 |
| --- | --- | --- |
| S0 | 原始冻结与本补充合同 | v0.17.0 正式 Release；本 addendum 尚待正式批准 |
| S1 | 本地账号、会话、两角色、Principal、共享资源授权 | S0_FORMAL_COMPLETE、ADDENDUM_FORMAL_COMPLETE、OWNER_LOCAL_ACCOUNT_AND_POLICY_PUBLISHER_DECISION；密码/会话/Schema/责任人须独立批准 |
| S2 | 授权内 saved-run 查询、筛选、分页及可信选择 | S1_FORMAL_COMPLETE；不允许 global latest 或客户端伪 identity |
| S3 | MCP service account 兼容与安全验收 | S1_FORMAL_COMPLETE、S2_FORMAL_COMPLETE、SERVICE_ACCOUNT_EXACT_GRANT_SAFETY_ACCEPTANCE；该技术前提替代须本 addendum 正式批准 |
| S4 | Dashboard 正常登录与预测选择 | S1_FORMAL_COMPLETE、S2_FORMAL_COMPLETE、S3_FORMAL_COMPLETE；保留五页设计 |
| S5 | 隔离合成安全试运行验收 | S1–S4_FORMAL_COMPLETE、OWNER_OPERATION_PLAN_REVIEW；TLS、旧入口、审计、备份恢复/回滚独立验收，不部署 |
| S6 | 最终业务/安全/三端验收 | S1–S5_FORMAL_COMPLETE；保留 browser/accessibility/security 和冻结回归，不自动生产批准 |

原始阶段 allowed_paths/非目标和 Owner gate 继续有效；未来最小账号管理具体文件与必要迁移必须在 S1 独立合同中批准，不由此授权代码。版本 closeout、tag/release、真实部署仍各需单独授权。

## Owner 待决参数、责任与首期排除

待 S1 合同单独决定：身份/账号管理员、业务授权审批与组织实体主数据 owner；password 库/成本参数/用户名与重置策略；会话存储、期限、撤销传播与 CSRF/rate limits；Schema/migration、备份、审计期限及 COMPANY 授权审批；历史记录批准 catalog 和 future enrollment（尚未批准）；旧路由适配或网络隔离方案。

首期排除 Keycloak/企业 OIDC/SSO 集成、复杂企业 IAM、最终用户 OAuth 委托、公开注册、新预测算法、训练/refit/tuning/评分/校准、真实业务/当前季 actual 读取、Peak Business 功能启动。保留五页 Dashboard 与八工具计算权威，不填补 Upper80/90、Attribution、Child Contribution 缺失，不宣称生产就绪、精度、P50/P80/P90 分位或真实 ROI。

本轮仅新增 Markdown、canonical JSON 和离线合同测试；历史源/证据 SHA256 与原测试不可变。S1–S6 runtime、Ready、Merge、Deploy、Tag、Release、Version Closeout 均未授权。完成 Draft PR + exact-head CI 后 STOP，等待独立复审。
