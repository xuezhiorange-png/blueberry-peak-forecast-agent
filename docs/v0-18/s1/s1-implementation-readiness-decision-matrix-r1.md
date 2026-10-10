# V0.18 S1 前置方案：Owner 决策页 R1

## 一句话结论

**建议方向**：若能核实公司已批准的 OIDC 身份提供方，使用“企业 OIDC + 同源 BFF + 服务器会话”；资源访问由独立、默认拒绝的共享授权 facade 判定。受控低频 pilot 可先评估签名版本化 grant 配置；真实多用户长期运营可评估独立授权存储。没有身份发行方、组织/基地授权发布责任人或 MCP 用户委托证明，就不能把登录成功称为业务可用，也不能报告逐用户隔离已完成。

本页提交 Owner 选择，不代表 Owner 已选择或批准实施。`S1_IMPLEMENTATION_AUTHORIZED=false`。

## 六项决策

| ID | 建议 | 可选项 / 当前证据 | 状态与 Owner 要回答的问题 |
| --- | --- | --- | --- |
| **DECISION-01 身份提供方** | 优先使用经核验的企业 OIDC issuer；固定 issuer、tenant、应用 registration、回调、安全联系人和停用机制。 | 若公司没有符合条件的 issuer，可评估独立 IdP（如自托管 Keycloak）+ 同一 BFF。代码库未发现 OIDC 登录实现；也未提供企业身份管理员信息、issuer URL、tenant 或 OAuth client。公司是否已有能力=`UNVERIFIED`。 | **OWNER_DECISION_REQUIRED / PENDING_OWNER_DECISION**：请指定 IT/IAM 责任人确认实际 issuer 和应用登记条件；未确认前不选供应商、不接入。 |
| **DECISION-02 BFF 与会话** | Dashboard/API 同源 BFF，Authorization Code + PKCE S256；opaque server-side session；Secure/HttpOnly/SameSite cookie；Unsafe API 防 CSRF；token 不入浏览器。 | Alternative：SPA 直接 PKCE bearer，仅在 BFF 经安全评审不可行时考虑，需承受 XSS/token/CORS 风险。当前无 BFF/session。 | **RECOMMENDED / PENDING_OWNER_DECISION**：Owner/平台需确认同源托管/反向代理、session store、cookie 域、会话有效期与撤销目标；这些基础设施当前未验证。 |
| **DECISION-03 内部 Principal 映射** | `(validated issuer, case-sensitive subject) → immutable internal principal_id`；单独映射状态和 revision；不以邮箱/姓名作主键，不自动合并；END_USER/SERVICE_ACCOUNT 隔离。 | 需要身份管理员负责首次绑定、停用、迁移和紧急撤销；人员名册/账户生命周期当前未核实。 | **RECOMMENDED / OWNER_DECISION_REQUIRED**：请指定身份映射/生命周期 owner，并确认是否使用邀请/审批式 provisioning；实现细节待 S1 formal authorization。 |
| **DECISION-04 Grant 发布者与组织边界** | 由 Owner 指定的 Forecast Data Steward/业务授权审批人发布 exact grants；组织、区域、基地 ID/关系由指定业务主数据 owner 签发并版本化；安全管理员只管认证，不替代业务 grant approval。 | 当前没有已核实的业务人员—组织—BASE/REGION/COMPANY 权限权威来源或审批岗位。Farm/Factory/entity 名称和预测记录创建人不是 grant authority。 | **BLOCKER / OWNER_DECISION_REQUIRED**：请指定业务授权审批角色、组织与实体边界数据源、替补与职责分离；未指定时默认无资源授权。 |
| **DECISION-05 Grant 存储** | 对第一阶段隔离 synthetic / 低变更 pilot，推荐评估签名、版本化、双人批准配置；每次请求检查 revision，禁止 wildcard，坏配置停服。 | 长期频繁人员/资源变更可另行评估独立授权存储与管理生命周期。需要新表、migration、审计及管理 API，当前未授权。 | **RECOMMENDED FOR LIMITED PILOT / OWNER_DECISION_REQUIRED**：请决定只用于合成试运行还是生产长期 ACL；若生产运维要高频变更，需另行授权独立存储设计与 DB schema。 |
| **DECISION-06 MCP 最终用户委托** | 在真实客户端的 OAuth/OIDC user-delegation、资源 audience、scope、撤销和调用方识别经 S3 测试通过前，保持现有 ServiceAccount-only、exact RunGrant/QualityGrant；明确显示服务账号范围。 | MCP HTTP Authorization 标准定义 OAuth resource-server delegation，但并不证明豆包客户端、当前服务部署或企业 IdP 支持兼容 flow。现有 V0.17 MCP 用自定义服务器密钥，不是用户 token。 | **BLOCKER / PENDING_OWNER_DECISION**：请指定要验证的豆包产品/版本/部署模式及 MCP 负责人。若客户端无法委托，接受 MCP 仅服务账号访问；终端用户隔离不能验收通过。 |

## 建议的共享访问判定

```text
可信身份/服务器 session
  → 内部 Principal 状态
  → capability（保留现有 may_read_forecast / may_read_quality 语义）
  → 组织边界 + exact BASE / REGION / COMPANY grant + 完整 identity/hash
  → 才允许 canonical business read
  → source hash/revision 复核
  → S1/S2 原服务与冻结计算
```

对未授权/不存在的 identity，在授权前统一拒绝且预测 repository、quality evidence 和模拟执行计数为零。有效 exact grant 之后，删除资源可向被授权主体返回 404；授权资源的 source/hash 漂移为 409 并不保留冲突数据。BASE 不继承到 REGION/COMPANY，aggregate 独立授权，Quality 使用独立 grant。Dashboard 只走 HTTP BFF；MCP 只有具备可信 delegation 才代表 end user，否则使用独立 ServiceAccount grants。

## 已核实兼容边界

- **可直接复用**：V0.17 S1/S2 typed business schemas、服务与冻结结果/hash；既有 capability 名称；V0.17 MCP ServiceAccount 精确 grants 作为机器身份样例；V0.17 五页 UI 与八个 MCP 工具。
- **需要适配（未来 S1 实施）**：新增 OIDC/BFF session→Principal 映射；引入共享资源授权 facade；S1 六个 GET 与 S2 business-loss/simulate/compare 的 HTTP routes 使用该 facade，并确保 auth/grant 依赖先于业务 service/session/repository；对 MCP 留清晰的 service-account 和 user-delegation 两种不混淆通道。
- **必须原样保留**：HTTP 预测/决策业务 response、Decimal/string 语义、source/projection/adapter/engine/scenario/comparison hashes、S1/S2 的数学、S3 8 工具名称及当前 NOT_AVAILABLE 语义、S4/S5 五页与旧 Trial 合同。
- **兼容/安全 blocker**：目前公开 API 没有可信 user session/grant adapter；当前 Trial actor 是服务器环境配置而非最终用户身份；legacy Trial/MCP 可形成旁路风险，不能因新 BFF 存在而声称其已不可达。未来 pilot 对不受信任客户端的 legacy route 必须网络默认拒绝并实测。

## 实施 gate 与范围分层

| 阶段 | 未来工作（全部需独立 Owner 授权） | 不得从本轮推断 |
| --- | --- | --- |
| S1 | 可信 issuer/BFF 与 Principal 映射；版本化或经另行批准的 grant provider；共享授权 facade；拒绝前零业务读/跨组织隔离测试；适配 S1/S2 route | 本轮未实现任何认证/授权代码；本次 Draft PR 不是生产实施许可 |
| S2 | 在已获授权集合中进行 saved-run discovery、过滤/分页和签名 handoff；继续 exact identity/hash 与授权复查 | 不做全局 latest、全库后过滤，不因 S1 而自动授权 S2 |
| S3 | 真实 MCP client user delegation compatibility；或者明确维持 service-account-only；共享同一 policy decision | 现有八工具不意味着 user delegation 可用；S3 无授权 |
| S4+ | Dashboard 正常业务选择、独立 synthetic safe-pilot、跨端安全验收 | 登录通过/本地合成测试不等于生产 ready 或 deployment |

## 当前未闭环事项

1. 公司可信 OIDC issuer、注册 app 的 owner、issuer/tenant/audience 信息：`UNVERIFIED`。
2. 企业 subject → 内部 principal 生命周期与员工/合作方名册责任人：`PENDING_OWNER_DECISION`。
3. 组织—区域—基地权威映射的业务 owner 和更新/撤销来源：`PENDING_OWNER_DECISION`。
4. Forecast Data Steward 授权审批责任、紧急 revoke 操作人及双人审批规则：`PENDING_OWNER_DECISION`。
5. 版本化配置与授权数据库的最终选择、改动频率/撤销时效需求：`PENDING_OWNER_DECISION`；schema/migration 不在当前授权范围。
6. 豆包/MCP 实际客户端版本、OAuth 委托能力、audience 与撤销测试：`UNVERIFIED`；未验证前仅 ServiceAccount-only。
7. 当前路由依赖顺序需要 S1 通过结构化依赖和 counters 证明先授权再触达业务数据；不能只依赖 route 函数中 permission check 的位置。

## 当前治理回执

`S0_FORMAL_COMPLETE=true`（已合并至本次精确基线并具备成功 post-merge push CI；见 evidence）。
`S1_IMPLEMENTATION_AUTHORIZED=false`；`PRODUCTION_CODE_AUTHORIZED=false`；
`DATABASE_MIGRATION_AUTHORIZED=false`；`S2_AUTHORIZED=false`；
`READY_AUTHORIZED=false`；`MERGE_AUTHORIZED=false`；`DEPLOY_AUTHORIZED=false`。

本文件提供方案及待决项，不伪造 Owner 选择、企业身份能力或资源 ACL。等待本 PR 独立审核与 Owner 后续决策。
