# V0.18 S1 本地认证与资源授权实施合同 R1

## 1. 结论、基线和生效条件

TASK_ID=V0_18_S1_LOCAL_AUTH_IMPLEMENTATION_CONTRACT_R1。版本 0.18.0 / BUSINESS_USABILITY_AND_SAFE_PILOT_FOUNDATION；最新正式 Release v0.17.0。
最新 main 为 `5b07acee24a56ffb9c7b7f6b697c6763e96e06b8`；fresh fetch、工作树及开放 PR 核验通过，无并行 S1 实施合同 PR。历史残留 S1 分支属于已合并 #711/#714，不复用。
#715 已合并至该 main，push CI #38114257884 completed/success。Owner 本次确认 S0 补充正式完成；GitHub reviews 返回为空，不编造 Review ID。旧 addendum 的 pending/false 是历史执行快照，字节不改。

本文件一次定义下一步 S1 的 Schema、密码、会话、API、授权、迁移边界及验收，不再拆分设计前置任务。
AUTH_MODE=LOCAL_USERNAME_PASSWORD；HUMAN_ROLES=ADMIN,BUSINESS_USER。
仅本合同和离线测试获授权；S1_IMPLEMENTATION_AUTHORIZED=false，LOCAL_AUTH_IMPLEMENTED=false，PRODUCTION_READINESS=NOT_READY。
合同独立审核、Owner Ready/Merge 授权、合并及 main CI 成功后，仍需 Owner 单独授权 S1 代码、Schema、依赖和实施参数；CI 不能代替批准。

## 2. 现有架构审查与复用结论

| 来源 | 实际能力 | S1 适配决定 |
| --- | --- | --- |
| backend/app/db/base.py、session.py | DeclarativeBase、asyncpg/AsyncSession、现有 PostgreSQL 连接池；未发现本地用户表 | 复用基础设施；认证事务与只读业务事务分开；拒绝之前不创建业务读取 session |
| backend/alembic/env.py、models/__init__.py | metadata 导入及 async Alembic | 单独增量迁移，注册新模型；不改历史迁移 |
| Alembic heads（只读取脚本，无 DB 连接） | 当前唯一 head：0040_hierarchical_forecast | 下一步执行时重新检查 heads，生成新 revision；本合同不预设 revision ID，不运行 upgrade |
| models/trial.py | TrialResourceBindingModel.owner_identity 与历史 Trial 资源归属 | 不是认证账号或人类 Principal；不改名复用，不将历史 owner 自动授权 |
| models/master_data.py、hierarchical_forecast.py | Farm/Factory、保存层级快照 | Farm/Factory 不是 BASE/REGION/COMPANY ACL 主数据；不从名称/当前 registry 推断组织或权限 |
| actual_harvest_import/api_auth.py、trial.py | 环境配置粗粒度 TrialActorDep | 不作为本地身份，不继承其实际采收/创建权限；新请求禁止降级回旧 actor |
| api/forecast_intelligence_read.py、forecast_intelligence_decision.py | 六 GET、成本查询及两 POST，授权在 endpoint 内 | 在 transport adapter 前置新认证/资源判定；共享 S1/S2 服务不改 |
| forecast_intelligence/read_access.py、mcp/forecast_intelligence_auth.py、http.py | 独立 MCP ServiceAccount + exact grants、HTTPS/Host/Origin | 保持服务账号路线和现有八工具；人类 cookie 不转换成机器权限；S3 运行改造另行授权 |
| frontend/src/dashboard/api/client.ts | same-origin cookie transport，尚无登录或 CSRF token 接入 | S1 不改前端；新增 CSRF 后生产 Dashboard POST 接入留给 S4，不为兼容临时豁免 |
| pyproject.toml、uv.lock | 无直接 Argon2 密码库 | 下一步依赖审查后加 argon2-cffi；本轮不安装、不改锁 |

数据库主张是复用 PostgreSQL，加四个认证对象，不复制预测 repository。没有核实真实生产数据库、用户或组织主数据；所有运行验收仅隔离合成数据。

## 3. 最小持久化 Schema（拟定，不是 migration）

共同约束：UTC timezone-aware 时间；服务器 UUIDv4 标识；外键 RESTRICT；账号禁用留存、不硬删除或复用 principal；认证数据与预测业务数据不混存。SQLAlchemy 类型使用项目 UTCDateTime、Base 风格，UUID 在 SQLite 合成测试采用可验证兼容类型。账号和授权状态修改同事务写审计，失败整体回滚。auth_session 安全写和 auth_audit_event 写不是预测/经营 DML。

| 表 | 字段及约束 | 索引/生命周期 |
| --- | --- | --- |
| auth_account | account_id UUID PK；principal_id UUID UNIQUE NOT NULL immutable/non-reusable；username_normalized VARCHAR(64) UNIQUE；password_hash TEXT；role ADMIN/BUSINESS_USER；status ACTIVE/DISABLED；must_change_password bool；auth_revision、grant_revision BIGINT positive；created_at、updated_at、disabled_at；managed_organization_ids 经可信配置批准的管理边界 | username 唯一索引；principal 唯一；禁止用户名成为 grant FK；禁用及重置 auth_revision++，撤权 grant_revision++；两个 revision 不回退；管理边界仅由批准发布者配置，不能自增 |
| auth_session | session_id UUID PK；token_digest CHAR(64) UNIQUE（仅随机 token 的 SHA256 verifier）；kind PREAUTH/END_USER；account_id FK（PREAUTH 必须 null，END_USER 必须非 null）；csrf_token_digest；issued_at、last_seen_at、idle_expires_at、absolute_expires_at；auth_revision、grant_revision 快照；revoked_at、revoke_reason | token_digest 索引，account/revoked/expiry 索引；PREAUTH 无业务权限，短 TTL 300 秒候选；登录/密码变更旋转；退出撤单会话；禁用/重置/关键撤权撤全部相关会话；过期定期清理必须后续被授权，安全判断不依赖清理 |
| auth_resource_grant | grant_id UUID PK；principal_id FK→auth_account.principal_id；resource_kind FORECAST/QUALITY；capability；organization_id；approved_by_principal、approval_reference、reason；grant_revision；valid_from/valid_until（必填且后者大于前者）；revoked_at；created_at；typed binding 见下节 | principal/capability/kind/active 索引；绑定 canonical digest 索引；禁止 wildcard；授权范围/binding 不原位改写，撤旧增新；subject revision 单调更新与审计同事务 |
| auth_audit_event | event_id UUID PK；occurred_at；actor_principal_id nullable（匿名登录失败 null）；target_account/grant ID；action；result_code；revision_before/after；correlation_id；organization_id；login_bucket_digest（仅 HMAC 化限制键）；脱敏 reason code | append-only，禁止普通 API 修改/删除；组织/时间、登录限制 bucket/时间索引；授权管理审计失败即管理事务失败；保留和维护需批准，不能无限增长 |

FORECAST binding 列：source_kind、forecast_family、run_id（positive BIGINT）、hierarchy_level（BASE/REGION/COMPANY）、entity_id、target_season、origin_date、baseline_id、policy_version、expected_source_result_hash（lowercase SHA256）、source_authority_version。QUALITY binding 列：mode、model_id、source_split、target_season、scope、evidence_policy_version、evidence_hashes（排序公共文件 hash map）、evidence_set_digest。
数据库 CHECK 强制两种 binding 互斥、必填集完整、禁止混用；模型用 Pydantic discriminated union extra=forbid。Quality 模式仅绑定明确批准的历史证据或无实际数据的状态查询，绝不授权 actual 读取。
capability 只允许 may_read_forecast / may_read_quality。模拟仍用 may_read_forecast + 同一 exact forecast grant，不引入预测创建或经营执行权限。管理角色与业务 capability 分离。

无可信组织源时不能创建 grant。Owner 批准的版本化组织目录/发布者责任为 S1 配置输入，不新建企业组织平台。每条管理员管理边界也需发布者批准；ADMIN 不可把自己任意加入组织、授予超出发布边界的 grant 或批准自身越界。company grant 的审批参考可人工双签后录入，不要求建设审批流引擎。

## 4. 密码、初始化和登录限制

候选依赖 argon2-cffi（官方 stable 文档当前为 25.1.0）：使用高层 PasswordHasher 明确 Type.ID 和参数；随机盐由库产生，编码 hash 包含参数；verify 和 check_needs_rehash，不自写密码算法。该版本是审查候选不是锁定批准；实施时复核维护、安全公告、许可证、Python 3.12 wheel、跨平台及 lock 构建，批准后 pin。
历史合同推荐下限 19 MiB、t=2、p=1（OWASP），候选 salt16/hash32 bytes。部署实测峰值并发、CPU/内存、延迟后批准实际 cost，不能直接依赖库默认参数。未批准参数 fail closed。

用户名候选 ASCII [a-z0-9._-] 3–64、大小写不敏感、服务器规范化；显示名不是权限主键。密码候选 15–128 Unicode 字符，不 trim/截断/弱化 Unicode，不强制周期改密；有限请求 16384 bytes，拒绝超长后才哈希。具体值待 Owner 批准。无公开注册、默认管理员、共享账号、email/SMS reset、MFA 平台。

首次管理员通过独立受信任的单次 CLI bootstrap：仅授权运行环境、无管理员时执行，事务/锁防重复；口令交互输入不在 argv/日志/仓库；每人实名独立账户，创建审计和立即改密。bootstrap 不是 HTTP 匿名接口；本轮不创建账号。
管理员初始/重置密码通过经过 Owner 批准的受控线下交付，不在创建/重置响应中回传密码。必须首次登录改密；该会话只能访问 me/logout/change-password，不能管理账号或读取业务。保留至少一名 active、已完成改密的 ADMIN；禁用/降级最后管理员或自己导致无人管理时 409，事务锁验证。

登录失败 unknown/disabled/wrong password 统一 401 INVALID_CREDENTIALS；未知账号使用同成本 dummy hash，禁用同样不泄漏存在；禁止只用快速失败时间差声称无枚举风险。账号名重置请求仅管理员有权限，仍不返回旧密码。
候选 15 分钟内 5 失败后限制 15 分钟，按规范化用户名及可信客户端来源组合；并设来源桶和全局并发上限，避免分布式暴力/任意用户名存储洪泛。计数不能仅 worker 内存：auth_audit_event 的 HMAC login bucket + 最近失败窗口，在 PostgreSQL transaction advisory lock 内原子检查/写入；已锁请求不再执行昂贵 verify。unknown/disabled 适用相同限制；桶密钥仅服务端配置，IP 仅受信任 proxy 来源，不信任任意 X-Forwarded-For。bounded admission/retention、并发 hash semaphore、503/429 需测试；限制状态不可用默认 503。候选限制参数需部署验证，登录成功不能给其他桶解锁。不得以永久锁账号造成拒绝服务。只存脱敏桶与结果，不存密码或完整 Header。

## 5. Session、Cookie、CSRF 和撤销

SESSION_MODE=OPAQUE_SERVER_SIDE_SESSION。token 使用 CSPRNG 至少 32 bytes，服务器只存 digest；Cookie 候选 __Host-blueberry-session：Secure=true、HttpOnly=true、SameSite=Lax、Path=/、无 Domain。浏览器不持 MCP secret；不把 cookie/token 放 localStorage/URL/证据/日志。仅批准的 HTTPS same-origin 和可信 proxy，重复 Cookie 身份或异常 Host/Origin 拒绝，不开放 credentialed wildcard CORS。

会话候选 idle8小时、absolute24小时，preauth300秒；候选未批准，不是既有事实。last_seen 只在已认证合法请求推进，不能延长 absolute；过期/禁用/auth_revision 或 grant_revision 漂移=401 且清 Cookie。角色变化也撤相关会话防旧管理权限；退出仅撤当前 token，禁用/重置/关键权限撤销撤 subject 全部。密码成功变更撤旧 token，旋转生成新会话；不能为旧会话再次延寿。
preauth 可从 GET /api/v1/auth/csrf 获得临时服务器 CSRF 会话与 token；无登录/业务权限。登录验证该 token+同源 Origin 后销毁 PREAUTH 并发新 END_USER token，防 session fixation/login CSRF。
CSRF synchronizer token 仅同源响应体返回、前端未来保存在内存，服务器存 digest；变更请求必须 X-CSRF-Token + Origin exact allowlist + application/json，constant-time 比较，缺失/重复/跨站=403。GET 不得改变业务状态（必要 session last_seen 安全元数据单独记账）；SameSite 不替代 CSRF。登录、logout、改密、管理员操作和模拟 POST 全部覆盖，不为旧 Dashboard 暂时跳过。S1 测试 client 可真实完成握手，正式登录 UI/CSRF client 在 S4 另行授权。
凭据认证和授权决策数据访问可以在 auth transaction 内；任何 auth 失败都不能打开敏感预测 repository。安全配置或 auth DB 故障 503，无降级认证。

## 6. 资源判定、响应前复核和并发撤权

END_USER_SERVICE_ACCOUNT_SEPARATE=true。人类账号 principal 由服务器验证密码/session 解析，无 issuer 伪造；不接受 actor/source_system/principal/role Header 作为身份。MCP 原有服务器凭据+exact grants 不迁入人类账号、不用 cookie 授权 MCP。

流程严格为 AUTHENTICATE → CHECK_CAPABILITY → CHECK_EXACT_RESOURCE_GRANT → CANONICAL_READ → VERIFY_IDENTITY_HASH → PRE_RESPONSE_PRINCIPAL_GRANT_RECHECK。
有效 scope 是批准 organization/entity ∩ capability ∩ exact-run allowlist；BASE/REGION/COMPANY 独立无继承；ADMIN_HAS_IMPLICIT_FORECAST_ACCESS=false；Quality 独立。
十项完整选择字段沿用 ForecastIdentity+expected_source_result_hash。S1 Schema 的 optional expected hash 不作为绕过：授权 facade 从准确 grant 注入并验证 hash；客户端如提供不符先固定403。身份无 grant（存在/不存在同样）在 canonical lookup 前 403；有 grant 的已删除记录404；合法 grant 绑定源发生 canonical identity/hash drift409 data=null，无 latest/rerun/family fallback。
来源 authority/version 同样固定，rerun/newseason/未来记录不自动授权。S1 仅管理已批准 binding，不扫描全库构造 grant，不实现 discovery/pagination/cursor/handoff；后续 S2 才对批准集合做元数据查询。

PRE_RESPONSE_GRANT_REVISION_RECHECK=true，包含 Principal active、role/auth_revision、grant_revision、session有效期、grant有效期/revoked和完整资源绑定。需要 fresh READ COMMITTED 检查，不用旧 ORM identity-map/长 REPEATABLE READ 快照。auth manager 与输出 release gate 使用同一 subject/account 行锁协议：撤权/禁用修改独占锁、更新 revisions、撤 session、审计并 commit；release gate 获取共享锁重读状态、构建非 streaming 敏感响应并在交给 ASGI send 前完成验证。若撤销 commit 在 release gate 前，丢弃结果403或会话失效401，data=null；不得靠 middleware 的 response 后清理替代。
定义可实现的线性化边界：release gate 与撤销提交先后排序；已在撤销前通过 gate 并发出的字节无法追回，不宣称网络上零竞态。不得在业务计算期间持有阻止撤权的长锁；严禁 streaming 提前发送敏感字段。测试用 barrier 在 canonical read 后、release gate 前撤销，必须零敏感 bytes；锁释放/取消/DB错误均 fail closed。实施时必须用真实 ASGI发送观测验证方案，无法实现就 BLOCKED，不降低合同。

所有 cache key 绑定 principal/client/auth_revision/grant_revision/full identity/hash，Cache-Control: no-store；禁共享缓存。撤权废止 server state；客户端上下文、cursor/handoff 失效属于 S2/S4 消费版本的后续实现，不冒称 S1 已提供这些功能。每请求独立 principal，不放进模块全局可变变量，支持并发 A/B，无跨请求 session/actor 复用。

## 7. 最小 API 合同（候选冻结，未创建接口）

统一 prefix /api/v1；auth/admin 成功 envelope：schema_version=V0_18_LOCAL_AUTH_R1、request_id、status=READY、data。认证错误：status=ERROR、code、data=null，固定安全文案。auth DTO forbid-extra、严格 enum/UUID/整数、不接受客户端 principal 或角色覆盖。所有响应 no-store。无 password_hash/token_digest/Session Secret；只有 CSRF token 可以按同源协议返回，raw session只在安全 Set-Cookie。

| 方法/路径 | 请求 | 成功响应 | 权限与错误 |
| --- | --- | --- | --- |
| GET /auth/csrf | 无客户端身份；Origin/Host 校验 | 200 csrf_token+expires_in；PREAUTH Cookie或现有有效会话 token | 无业务权限；限流429/配置503 |
| POST /auth/login | username,password；CSRF+PREAUTH | 200 principal_id,role,must_change_password；旋转 Cookie | 401统一登录失败、429限制、403CSRF；不能提交 role/actor |
| POST /auth/logout | 空对象；CSRF | 200 logged_out=true；撤销/清Cookie | 有效session；过期401仍清Cookie；不得 logout GET |
| GET /auth/me | session | 200 principal_id,role,must_change_password,auth_revision,grant_revision | 401失效；不返回授权记录列表（S2） |
| POST /auth/change-password | current_password,new_password；CSRF | 200 password_changed=true；新Cookie | 当前账号，验证旧密码；reset临时密码同流程；失败固定401/422，旧session撤销 |
| POST /admin/users | username,initial_password,role；reason | 201 account_id,principal_id,role,status,must_change_password | ACTIVE ADMIN且已改密；角色允许两类；不随新账号授预测权；重复名409 |
| PATCH /admin/users/{id}/status | status ACTIVE/DISABLED,expected_auth_revision,reason | 200 account摘要及新revision | ADMIN批准管理边界；最后管理员保护409；重新激活不恢复旧session/grants |
| PATCH /admin/users/{id}/role | role,expected_auth_revision,reason | 200 account摘要及新revision | ADMIN管理边界；角色变更撤session，不自动 grant；revision冲突409 |
| POST /admin/users/{id}/reset-password | new_temporary_password,expected_auth_revision,reason | 200 reset=true,must_change_password=true | ADMIN受控交付；所有旧session失效；不返回密码 |
| GET /admin/users | page_size 1–100、after_account_id；默认20 | 200批准管理边界内账号安全摘要,next_account_id | ADMIN；仅账号管理分页，不是 saved-run发现，不泄露跨组织账号 |
| POST /admin/resource-grants | subject_principal_id,resource_kind,capability,完整typed binding,organization_id,validity,expected_grant_revision,approval_reference,reason | 201 grant_id,new_grant_revision,批准binding摘要 | ADMIN+可信发布管理边界；禁止越界/自批扩大边界；无canonical业务读取以猜测身份 |
| POST /admin/resource-grants/{id}/revoke | expected_grant_revision,reason | 200 revoked=true,new_grant_revision | ADMIN批准管理边界；原子撤session/cache及审计；重复已撤销在匹配版本下幂等 |
| GET /admin/resource-grants | subject_principal_id,page_size≤100,after_grant_id | 200批准范围内授权元数据 | ADMIN；不查全库 forecast，不等于业务发现 |
| GET /admin/audit-events | approved organization,from/to≤31日,page_size≤100,after_event_id | 200必要管理事件,next_event_id | ADMIN已批准管理边界，无业务数量/口令/密钥 |

全部管理修改依赖服务器配置的组织管理发布者边界，不因传 organization_id 自动获得权利。账户全局创建权须明确指定，不默认所有组织管理员可以创建管理员；在批准配置中控制可创建角色/可管理账户集合。跨边界已存在/不存在 account/grant ID 同一403，不先查敏感对象；合法管理集合中已删除对象404。reason候选1–500字符，approval reference≤200，body≤16384。未来管理员界面不在 S1，API client 合成测试足以验证。
Auth/admin 用 401未认证、403无管理/CSRF/资源权、404准确授权后缺失、409 revision或最后管理员冲突、413 body、415非JSON、422非法输入、429限制、503配置/DB/审计不可用；422/503 不回显 raw输入、SQL、私有路径或stack。不区分登录用户名不存在。S1/S2 现有业务 error envelope/schema 保留，403/401仍data=null；保持8192查询字节、131072 S2 body、20 scenarios、15days、workforce≤1000000、Decimal≤64。

Business Loss exposure 无 run，是冻结公共成本合同：session+may_read_forecast（至少一条有效forecast grant提供capability），不借此读取 forecast或Quality；显式成本ID/hash且 no default。simulate/compare 必须完整合法 forecast selection exact grant；场景二阶段验证沿用服务。Quality入口在文件读取前独立grant，复核pinned历史evidence set。当前 NO_CURRENT_ACTUAL 不触发actual API。

## 8. 既有路由适配和未来 S1 文件边界

未来必须由 Owner 单独授权以下有限代码集合，本轮没有修改它们：
新增 backend/app/local_auth/{schemas,models,repository,passwords,sessions,service,authorization,audit,bootstrap}.py、__init__.py；
新增 backend/app/api/local_auth.py、local_auth_admin.py；
必要 backend/app/main.py（路由注册与明确legacy入口拒绝）、backend/app/core/config.py（可信配置）、backend/app/models/__init__.py（模型注册）；
仅 transport 授权适配 backend/app/api/forecast_intelligence_read.py、forecast_intelligence_decision.py；
backend/alembic/versions/<实际生成revision>_local_auth.py、pyproject.toml、uv.lock（经批准密码依赖）；
backend/tests/local_auth/、相关API负向/兼容测试、docs/v0-18/s1/新实施证据。
get_db_session 基础设施复用，不改变 forecast services/engines/read_schemas/decision_schemas。local_auth authorization facade 不改既有 read_access ServiceAccount合同；保持计算结果原值。
对六 read endpoints 逐项 auth、Quality独立；对两decision POST auth/CSRF+same exact source；成本GET capability独立判断。route adapter 在依赖授权后才通过 service factory懒创建业务session，业务输出走release gate，不能endpoint执行前依赖已经读取业务资源。必要 actor兼容桥只能由服务器已认证principal生成必要只读capability，不能透传旧TRIAL环境授权/actual权限。
旧 /api/v1/trial、旧 MCP /api/v1/blueberry/v1/mcp 与 /sse，以及其他历史saved-run/list/create/import路由，在未来local-auth受控入口使用显式路径allowlist默认拒绝；同时专有legacy信任域的历史合同不改。不要只封Trial而遗留其他旧业务入口。受控入口任何未列入路径都拒绝，健康探针单独批准。可信本地测试注入不得成为生产匿名fallback。网络隔离最终验证/部署另在S5，当前 legacy_isolation_verified=false。
MCP独立ASGI不能通过本地cookie/旧connectorsecret开放人类权限。S1不改MCP Runtime；S3再验证共享安全协议、响应前撤权和八工具HTTP parity；不是要求S1提前通过S3完成gate。
Dashboard现有五页保持不变；S1先提供真实auth/业务HTTP client合成测试，不声称现有Dashboard已有登录或POST CSRF兼容。S4完成受控cookie/CSRF/清上下文。S2才提供发现、cursor、handoff。其他文件确有必要时报告定向授权缺口，不扩大实施边界。

## 9. 下一步运行安全验收矩阵（PLANNED_NOT_RUN）

所有以下用例使用隔离 PostgreSQL/SQLite合成账号、grant与canonical saved runs，真实HTTP；读阶段 business DML guard；记录 authentication metadata reads 与敏感 repository/quality/simulation计数分离。公开证据只存策略与公共hash，不存凭据。SQLite不代替PG锁/事务验收。

| ID | 验收/负向条件 | 必须结果 |
| --- | --- | --- |
| A01 | ADMIN创建BUSINESS_USER，成功登录 | 服务器Principal稳定、账号无默认业务grant |
| A02 | 错误口令、未知用户名、禁用账号 | 固定401、敏感read=0、同成本处理 |
| A03 | reset+首次改密 | 旧session失效；未改密不能访问业务 |
| A04 | logout、idle/absolute过期、cookie重复/伪造 | 401/拒绝，跨worker无降级 |
| A05 | BUSINESS_USER调用所有管理API | 403，管理对象/业务读取=0 |
| A06 | ADMIN无forecast/Quality grant | 403；角色不绕过ACL |
| A07 | A访问B的BASE/跨组织/猜run或sourcehash | 403，存在/不存在相同；敏感read/模拟=0 |
| A08 | BASE/REGION/COMPANY独立、rerun/season/family漂移 | 无自动继承或新记录授权 |
| A09 | 有forecast无Quality、Quality文件缺失/漂移 | 前者403零文件读；合法grant后保留S1不可用/409语义 |
| A10 | canonical源identity/hash/日行损坏，合法grant | 保持既有failclosed错误，不退latest或POINT |
| A11 | canonicalread后、输出前禁用/撤权/expiry | fresh revision gate拒绝，零敏感响应字节，旧结果清除 |
| A12 | 多principal并发、重置/撤权冲突、取消连接 | 无串权；锁/事务释放；旧finally不发结果 |
| A13 | 旧Trial/MCP/其他旧业务路径、actor伪造 | 受控入口默认拒绝，无新认证fallback |
| A14 | 原HTTP与canonicalservice结果对照 | Decimal/identity/source/projection/engine/scenario/comparisonhash完全一致，不改数学 |
| A15 | CSRF缺失/重复/跨Origin、sessionfixation、cookie属性 | 403/拒绝；login/logout/admin/simulation全覆盖 |
| A16 | 5/15候选限流、unknown账号/并发多个worker、超长密码 | 原子限制、429/413/422；无昂贵不受限哈希，故障503 |
| A17 | 管理审批边界、lastADMIN、revision CAS、审计故障 | 无越界、自增权限或丢失审计；管理事务回滚 |
| A18 | bootstrap重复、重建账号/改名、密码hashrehash | 无principal复用/默认账户；生产无test注入 |
| A19 | 业务POST无经营DML、日志脱敏、依赖漏洞与cost基准 | auth写独立，无actual/train/评分/密钥日志 |
| A20 | authDB、配置、服务503与恢复 | failclosed、无内部信息，恢复后重认证，不跳过gate |

这些是下一步测试要求，本轮离线合同PASS不代表任何A01–A20运行通过。
S1正式完成需单独实施授权→全部安全测试→exact-headCI→独立review→OwnerReady/Merge→post-mergeCI。不得用S1CI替代S3安全完成、S5隔离部署或S6生产验收。

## 10. 仅剩 Owner 决策与阶段治理

一次批准以下四组参数/责任，不再拆设计PR：

1. D01：批准PostgreSQL四表、密码库锁定/许可与迁移范围，指定备份/恢复和审计责任及留存期限（候选180天）；实施时实际heads分配revision。
2. D02：批准密码/用户名、Argon2id实测cost、idle8h/absolute24h、失败5次/15min与15min限制、PREAUTH300s及Cookie/CSRF可信域代理；均PENDING_OWNER_APPROVAL，不是当前批准事实。
3. D03：指定bootstrap管理员、组织实体数据steward、授权发布/审批人及管理组织/账户/可创建角色边界、company审批及线下临时口令交付；不批准future-run自动加入，仍false。
4. D04：批准下一步S1代码allowlist与受控入口默认拒绝legacy策略、命名隔离验证责任；另行明确S1_IMPLEMENTATION_AUTHORIZED及schema/dependency范围。不授权部署/S2–S6。

S1依赖原S0+正式补充+Owner账号/授权发布者决策。S2依赖S1formal；S3依赖S1/S2formal+OWNER_SERVICE_ACCOUNT_MODE_AND_TEST_PLAN_APPROVED及独立实施授权；SERVICE_ACCOUNT_EXACT_GRANT_SAFETY_ACCEPTANCE=PENDING_NOT_EXECUTED仅S3完成条件，不能形成启动循环。S4依赖S1/S2/S3；S5依赖S1–S4及Owner操作方案；S6依赖S1–S5。原阶段名称和顺序不改。

## 11. 证据、验证与排除

新JSON绑定完整历史addendum/方案、实际审查代码、依赖锁和三交付文件中的doc/test原始SHA256（JSON不自hash）。排序键、UTF-8、缩进2、末尾换行；历史来源另有固定pins，不能更新旧断言。
只新增三文件，离线tests只读公共文本，不import生产服务、不访问DB/network；Ruff/Mypy和相关V0.18回归。exact-headCI写PR交接，不回写历史治理snapshot。
排除生产认证/迁移/账号创建、Keycloak/OIDC/SSO/IAM、MCP委托、Dashboard修改、发现API、PeakBusiness、actual读取导入评分、模型训练refit调参校准、部署/Tag/Release；未绑定上界/归因/贡献仍NOT_AVAILABLE；NOT_READY，无P50/P80/P90精度或因果/ROI声称。

安全设计参考：[argon2-cffi参数与实测](https://argon2-cffi.readthedocs.io/en/stable/parameters.html)、[OWASP密码存储](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[OWASP会话](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)、[OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)。2026-10-11查询；规范不证明运行实现或认证通过。

READY_AUTHORIZED=false；MERGE_AUTHORIZED=false；DEPLOY_AUTHORIZED=false；TAG_AUTHORIZED=false；RELEASE_AUTHORIZED=false；STOP=true。
