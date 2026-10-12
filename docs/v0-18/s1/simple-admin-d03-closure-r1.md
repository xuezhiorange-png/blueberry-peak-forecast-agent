# V0.18 S1 D03：极简管理员方案执行记录

TASK_ID=V0_18_S1_SIMPLE_ADMIN_CLOSURE_R1。Owner 本轮选择：ADMIN 直接管理普通账号，并为其分配/撤销服务端登记的精确资源；不设置独立授权审批人、组织管理员或逐笔人工审批单。本记录追加决定，不修改 #714–#717 的历史事实、合同、参数或哈希。

## 最小差异与运行方式

#717 的 PublisherBoundary 要求逐账号 manageable_account_ids，并要求完整授权请求先列入 approved_grants。新增 LOCAL_AUTH_SIMPLE_ADMIN_CATALOG_JSON 后，已认证、有效且已改密的 ADMIN 使用直接管理模式。不需要配置其 principal_id、预先登记新账号或准备整条审批请求。

配置必须由可信服务器运行环境提供，不能来自 HTTP、用户名、实体名称或现有业务 registry 推断。目录结构为 organization_ids 和 resources；每条资源绑定 organization_id、resource_kind、capability、完整 ForecastBinding 或 QualityBinding。组织必须同时存在于 LOCAL_AUTH_ORGANIZATION_IDS_JSON。目录发布前由 Owner 指定的首次运维人员验证真实组织、实体、来源版本、预测完整身份和 hash；代码检查结构与精确匹配，不能证明现实组织归属。本任务只使用 SYNTHETIC 测试目录，不签发真实配置。

新建普通账号的 managed_organization_ids 由服务器目录写入，而非请求参数。管理员可管理目录范围内的普通账号以及自身；不能管理范围外或空归属账号，也不能通过直接模式创建/提升其他管理员。旧账号归属的可信迁移不自动执行。单一普通系统目录是首期边界，不建设多租户管理平台。目录缺失时不自动全放行；历史显式边界仍保留兼容，非法直接目录必须 503，不回退。

授权请求不再需要审批单。原 approval_reference 字段为兼容保留，缺省 ADMIN_DIRECT_ASSIGNMENT 仅是操作来源标识，不产生权限。授权匹配目录的完整 binding，独立检查收件账号范围、有效期、CAS revision；不把主体、期限或原因预先列入审批清单。FORECAST / QUALITY 独立；BASE / REGION / COMPANY 不继承；新 run、season、hash 或来源版本必须先单独登记，未来记录不自动授权。

数据库不变：账号的可信归属和既有 grant / audit 字段复用。操作者、目标、资源、时间、revision 与原因仍在管理事务中记录。直接模式原因限制 1–64 字符，完整写入现有 reason_code，超长明确 422 并回滚，绝不截断。grant 还保留完整 reason。账号操作在目录组织下记录；资源操作按精确资源组织记录。密码、token 不作为操作原因输入；安全 Cookie、CSRF、首次改密、限流、最后管理员保护、撤权/禁用会话失效及 ASGI 响应前释放门禁不变。

ADMIN 仍没有默认预测或 Quality 权限。普通用户获得一条明确 grant 后才能读取；知道 run ID 或 hash 不构成授权。预测 Service、数学、Decimal、结果 hash、MCP Runtime、Dashboard、迁移和依赖均不改。旧正式入口默认拒绝仍有效。

## 历史证据与本轮验证

已合并 #717 的实施证据保持原字节。它绑定的本次合法变更源码使用固定合并提交 e9812e82067dceae444ff0707ceeb2f560c1018e 进行历史字节校验，旧预期 hash 不更新。260 份冻结文档/证据仍检查当前字节；新代码另外执行真实 PostgreSQL 与当前 HEAD 测试，历史 PASS 不替代本轮安全验收。

新增直接流程测试覆盖：创建后无需账号预登记即可列出/重置/禁用；无需审批单分配和撤销精确资源；错误组织、run、hash 拒绝；普通用户不能管理；ADMIN 无默认数据权；Quality/公司级不继承；撤权旧会话失效；最后管理员不可禁用；审计原因完整。A01–A20 现有测试完整重跑，CI 覆盖完整后端及既有前端回归。具体实际结果记录于同名 JSON 和 Draft PR exact-head 回执，不继承旧 CI。

## 治理边界

D03_SIMPLE_SCHEME_APPROVED=true；真实首次管理员及真实资源目录仍等待正式环境启用时 Owner 指定，REAL_ADMIN_CREATED=false；PRODUCTION_READINESS=NOT_READY。方案决策不代表真实组织数据已经验证。

本轮不启动 S2–S6、不开发前端管理页面、不操作生产数据库、不部署。S1_FORMAL_COMPLETE=false；READY_AUTHORIZED=false；MERGE_AUTHORIZED=false；TAG_AUTHORIZED=false；RELEASE_AUTHORIZED=false。完成 Draft PR 与 exact-head CI 后 STOP，等待独立复审。
