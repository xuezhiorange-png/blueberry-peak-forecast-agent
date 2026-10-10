# V0.18 S1 资源授权发布者与访问边界评审 R1

TASK_ID=V0_18_S1_IDENTITY_AND_GRANT_AUTHORITY_PREFLIGHT_R1
基线 `52b5a80f89c59130917b29c9097d63076eab4acb`
范围：设计与适配评审；没有创建用户、Grant、授权数据库或生产代码。

## 评审结论

V0.17 S3 已有的 MCP `RunGrant` 能精确绑定一个**服务账号**、完整 `ForecastIdentity` 和 `source_result_hash`；`QualityGrant` 独立绑定质量模式与模型。它是良好的 exact-resource fail-closed 样例，但不是终端用户、组织关系或 HTTP 用户 ACL。V0.17 S1/S2 HTTP 使用单个服务器配置型 `TrialActorDep` 与 `may_read_forecast` / `may_read_quality`，没有每用户、每组织、每基地的授权目录。

目前无法从代码库确认谁是蓝莓业务用户/组织名册和基地/区域层级的权威发布者。现有 `Farm`、`Factory`、forecast entity 或记录创建人只能表示业务实体/记录，不被证明是身份/访问控制权威；禁止用其名称、创建人、source system 或前端传值推断用户权限。授权来源与责任人状态为 `UNVERIFIED`。

## 两种授权目录候选

| 方面 | 方案 A：受信任版本化授权配置 | 方案 B：独立授权存储与生命周期服务 |
| --- | --- | --- |
| 适用情境 | 小规模、低变更频率、隔离合成/受控试运行；每个 revision 可审阅和原子发布 | 用户/组织/记录 ACL 经常变化，业务访问责任人需要批准/撤销自助工作流，需及时状态可见 |
| 发布者 | Owner 指定的业务 Forecast Data Steward 批准用户/组织/资源授权；应用/平台 operator 仅部署批准的 bundle，建议双人发布 | 指定业务授权审批人通过独立管理流程写入；数据库 operator 不能因此自动拥有授予权；安全管理员管身份，不代替业务审批 |
| 典型实现 | 签名、版本号、只读配置 artifact；schema 严格校验；禁止 wildcard、重复/重叠隐式授权；revision 单调递增；原子替换；失败时不回退 allow-all | 新的独立 schema 与授权生命周期服务：Principal、组织成员/范围、Grant、revision、批准/撤销审计；带事务与并发冲突保护；业务查询仅由访问 facade 调用 |
| 优势 | 透明 review/diff、易审计、无需为本阶段建新 DB、可以做可复现 synthetic tests；依赖少 | 可处理高变更频率、有效期和撤销/审批工作流；可查询当前 revision 与授权状态；能把业务访问管理从部署发布中分离 |
| 限制/成本 | 大量用户/资源时文件膨胀；发布延迟等同部署节奏；并发更新和即时撤销困难；每次发布需严格完整性与双人控制 | 新数据库 schema/migration、API/管理界面、权限分离、运维、备份/恢复、审计保留、锁/缓存一致性和灾难恢复成本；可能形成新的高权力面 |
| 主要风险 | 配置仓库/签名密钥/部署 token 被攻破；旧 bundle 恢复可能复活已撤销 grant | 管理 API 权限错误、直接 SQL 改 ACL、事务竞争或缓存失效导致跨用户泄露 |
| 建议 | 首个隔离、合成、低频变更试运行的推荐候选，不代表已准备好生产人员与 grant 清单 | 真实持续多用户运营更适合评估的长期候选；任何新 schema/migration 必须另得 Owner 授权 |

**推荐不是既定 Owner 选择。** 初始受控合成 pilot 可采用经签名/审批的版本化配置；生产授权目录最终采用哪种存储取决于 Owner 对规模、撤销时效、审批职责和运维成本的选择。即使采用配置，生产运行也要求明确的身份责任人、grant 发布/撤销操作人、受保护 artifact 来源和可验证的 revision；仅把 YAML 放入普通应用仓库不够。

## 权威来源与组织边界

组织/实体边界应由 Owner 指定的业务主数据治理角色发布稳定 ID、有效期和版本：

- **身份主体**：可信身份提供方验证的 `(issuer, subject)` 映射到内部 `principal_id`；身份管理员负责账户映射/停用，不负责自动授予预测访问。
- **组织成员关系**：由明确的企业人员/合作方目录 owner 提供；必须说明员工、承包方、离职和跨组织的加入/移除时点。该来源在本次评审中未提供，状态 `UNVERIFIED`。
- **公司/区域/基地实体范围**：由 Owner 指定的数据治理人确认稳定 `company_id` / `region_id` / `base_id` 与组织归属版本。预测 hierarchy 的 `COMPANY/REGION/BASE`、现有 master-data 表或 entity display name 不自动证明其访问治理语义。
- **资源权威**：从已验证的 saved-run identity 与 canonical source hash 读取，不用“预测记录创建者”授予读取，不对当前 registry 的层级关系追溯重写历史快照。
- **授权审批**：建议业务 Forecast Data Steward 批准资源级访问；组织/基地 owner 只对其被明确授权的组织边界负责；安全/IAM owner 管身份提供方、认证策略和紧急停权。人名、岗位任命及职责分离目前未被确认，须 Owner 指定。

授权关系使用稳定 ID，不用 entity 名称、邮箱域、组织字符串相似度或知道 `run_id` 推断。组织成员关系是额外的必要限制，不替代资源级 grant。

## Grant 逻辑合同

### 主体和能力

Grant 仅对一个受信任主体生效，必须含 `principal_id` 与不可混淆的 `principal_type`（`END_USER` / `SERVICE_ACCOUNT`）。用户不得在 HTTP body、query、MCP tool args 或普通 Header 里指定 principal。`capability` 按既有 S1/S2 权限映射：预测/决策支持读取对应 `may_read_forecast`，历史 Quality 对应 `may_read_quality`；Quality 永远需要独立批准，预测授权不派生 Quality 权限。

### Exact forecast grant

至少绑定：

`principal_id`, `principal_type`, `organization_scope_id`, `capability`, `source_kind`, `forecast_family`, `run_id`, `hierarchy_level`, `entity_id`, `target_season`, `origin_date`, `baseline_id`, `policy_version`, `expected_source_result_hash`, `grant_id`, `grant_revision`, `valid_from`, `valid_until`, `revoked`, `approved_by`, `approval_reference`。

字段均来自服务器授权发布与 canonical S1 authority，不接受客户端生成。grant 不替代 S1 canonical hash/完整性验证；canonical result 的 identity 或 hash 与 grant 有任何偏差，拒绝并不显示该结果。

BASE、REGION、COMPANY 是**彼此独立**的资源 scope。给一个 BASE 的 grant 不授权其 REGION/COMPANY 聚合；区域权限也不自动扩展到子基地；公司 aggregate 单独批准，因为它能暴露聚合范围。只有 grant 明确覆盖一个层级和 entity ID 时，才可读取那个保存层级；不运行新 reconciliation、不查询当前 hierarchy registry 代替历史快照。

### 独立历史质量 grant

Quality grant 单独绑定 `principal_id`, `principal_type`, `capability=may_read_quality`, `model_id`, `source_split`, `target_season`, `scope`, `evidence_policy/hash`, `grant_revision`, 生效/到期/撤销和审批来源。它不依赖/不继承 Operational Peak run grant，也不含 current-season actual 访问权。S1 暂时不批准 `CURRENT_PRODUCTION_ACCURACY`；该模式保持 `NO_CURRENT_ACTUAL`。

### ServiceAccount

服务账号有独立 machine principal 注册、独立凭据/rotation、明确 client/resource identity 与 exact grants。模拟 API 必须先拿到 forecast curve exact grant，随后才可调用 S2，不得因 service account 通道而跳过用户/资源判断。若未来支持受托用户访问，允许集合应为 `用户权限 ∩ MCP client/service 范围 ∩ exact resource grant`；不得让一个宽权限 service account 替代调用者授权。

## HTTP、Dashboard、MCP 的共享判定顺序

```text
验证可信会话/token 或独立 ServiceAccount
  → 解析内部 Principal 与状态
  → 检查 capability
  → 在只读授权目录中检查组织边界和 exact grant / revision
  → 通过后才查询 canonical forecast / quality evidence
  → 验证完整 identity、parent/child completeness 和 source hash 与 grant 一致
  → 对 simulate/compare 才调用原 S2 service
  → 返回前复核 Principal/grant revision；若中途撤销则丢弃响应
```

登录和授权策略目录是认证/授权元数据，不是 forecast payload。未授权请求不得查询 saved-run 表、每日行、历史 quality 文件，不得建立模拟输入/调用 `simulate()`。如果未来 Grant 放入 DB，授权表与业务数据访问必须仍有逻辑边界，测试区分“授权元数据读取”与“业务数据读取”；拒绝 case 的预测 repository、quality-file 和 simulation 计数必须均为零。

### 防止存在性泄露

在 exact grant 校验前，缺失 run、猜测 run、错误 entity/hash、跨组织、错误层级对调用者返回同一脱敏 denial（推荐固定 403 code/body），不得查询业务记录来区分“存在但无权”与“不存在”。只有一个完全匹配且仍有效的 grant 已验证后，canonical read 才可查记录；若此时记录已删除，允许向该已授权主体返回 404。hash drift 对已授权主体返回 409、清空冲突结果并要求重选。禁止错误响应包含实体/组织名、数量、SQL、路径、授权名单或 raw token。

### 缓存、cursor、handoff 和撤销

- 每请求重新验证 Principal 状态、grant revision 和具体 grant；不能以登录 cookie 存续证明授权仍有效。
- 私有业务响应使用 `private, no-store`；若服务端确需短缓存，键至少含 principal/client、capability、grant revision、完整 identity/hash 和业务 projection authority；不得跨主体共享。
- 任何 cursor/handoff 必须服务端签名，绑定 principal、client、完整 identity/hash、grant revision、filters/sort/snapshot 和过期；消费时重新 authorization，不是 bearer grant。revision 不同、撤销或身份/hash 漂移时拒绝并作废所有有关 cursor/handoff/cache。
- 对已经启动的读取，响应发布前再检查 grant revision；不能保证在途取消时，必须保证旧主体/旧权限结果不被返回。失效后的客户端 context 清空受影响数据，不得用旧响应覆盖新主体。
- 具体撤销传播时限、缓存 TTL、审计保留期限和告警负责人仍未定，属于 Owner/运维决策；本评审不写未经批准的数字 SLA。

## S1 实施适配与验收提案

### 建议模块/接口边界（未创建）

| 候选单元 | 职责 | 不应拥有的职责 |
| --- | --- | --- |
| OIDC/BFF auth adapter | 验证 code-flow/session，输出不可变可信 Principal context | 查询业务预测或授予基地权限 |
| Principal registry | issuer+subject 到内部 ID 的映射、启停与 revision | 按 email/姓名自动并户、按组织名称推测权限 |
| Shared Resource Authorization Facade | 输入 Principal + capability + exact request identity/hash；授权或统一拒绝 | 重算 forecast、用最新 registry 替代历史 hierarchy、替代 S1/S2 service |
| Grant provider | 加载已签名/批准的 grant snapshot 或受批准的独立 policy store | 从全库 run 列表、created_by 或前端参数自动产生 grants |
| HTTP adapters | S1/S2 APIs 通过共享 Facade；未授权时不触达业务 repository | 放松现有 actor 权限或改变 S1/S2 response math/hash |
| MCP adapter（未来 S3） | 保留八个工具，校验 token/ServiceAccount 与同一 Facade | 把客户端参数当 actor；工具内重复一套 grant/业务算法 |

### 需要具体证明的安全测试

1. 用两个 END_USER、两个组织、两个基地和 BASE/REGION/COMPANY runs 的显式 SYNTHETIC fixture，覆盖允许/拒绝矩阵；Company/Region 需要独立 grants；Quality grant 完全独立。
2. 未认证/错误 issuer、audience、signature、expiry、nonce、CSRF、session fixation/复用、重复身份 Header/claims、禁用 Principal、授权配置丢失全部 fail closed。
3. 每种被拒绝请求埋点断言：repository query/read=0、quality public evidence read=0、S2 simulation=0；若有独立授权目录查询，单独计入 grant metadata read，不得混称业务查询。验证 auth dependency 完成前不会构造业务 read service/业务 session。并发请求使用不同 Principal 无上下文串用。
4. 创建同 hash / 改 hash、run 存在与不存在、未授权跨层级 / 跨组织的 denial response 同样；有效 grant 后删除才允许 404；有效 grant 后 source hash drift 为 409 且 response data null。
5. revision 更新和撤销期间重复验证缓存、cursor、handoff、logout 与 in-flight response；旧 session/旧 revision 不恢复权限。
6. HTTP、Dashboard（只经 HTTP）、MCP SDK 使用同一 access facade；同一个合法主体与 resource得到相同的 allow/deny 决定。MCP Authorization 如未能与真实客户端走 OAuth 用户委托，则只测试现有 service-account exact-grant 路径，并把终端用户矩阵标记 `BLOCKED_NOT_SUPPORTED`，不假设两者等价。
7. 旧 Trial / legacy MCP 路径检查为独立 trust boundary。S1 代码适配不能被误报为旧入口已网络隔离；隔离在安全 pilot 环境中另行验证。

## S1、S2、S3 责任边界

- **S1（当前只有前置评审授权）**：身份验证、Principal 映射、共享 capability/resource grant 判定、V0.17 HTTP/MCP service adapter 方案及拒绝前零业务读测试。暂不列出 saved runs、分页、cursor 或选择 handoff；不实施完整 IAM 管理门户、不改模型/数学/数据库迁移。Provider、publisher、存储决策未批准时 S1 implementation gate 仍关闭。
- **S2（未授权）**：只在 S1 formal 完成后增加授权集合内的 saved-run discovery/filter/page 和短期 handoff。查询须先据批准的 grant 形成 allowlist，再限于 allowlist 查询；不先扫全库后过滤，不返回全局 totals，不静默 latest/rerun fallback。handoff 不替代每请求再授权。
- **S3（未授权）**：确认具体 MCP client 实现 OAuth user delegation、resource audience、scope、撤销与身份委托后，才可能把 END_USER context 安全送到 MCP。若不能证明，保留 ServiceAccount-only + exact grants；不能宣称终端用户资源隔离通过。8 个工具和 business payload/hash 不改。

**本轮状态**：授权生产实现 `false`；新增 DB schema/migration `false`；真实企业 issuer、组织授权来源、授权审批人及 MCP 真实客户端委托 `UNVERIFIED`；无私有/生产数据访问；不得开始 S2。
