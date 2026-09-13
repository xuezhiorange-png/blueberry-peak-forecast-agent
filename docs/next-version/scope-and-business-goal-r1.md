# 下一版本：业务目标与最小范围提案 R1

## 1. 请 coordinator 决策什么

**只推荐方向 C：把已验收的历史基线变成业务操作员可发现、可调用、可回读、可下载的正式 API 闭环。**

最小业务变化：今天需要工程人员预先注册版纳 authority、找出 hash，再调用 empirical POST/GET；下一版让有权限的业务技术操作员按服务端列出的农场、品种、面积和期间选择已注册范围，创建预测并取得服务端 CSV，不查库、不改范围专用脚本、不手工编造 hash。不是承诺任意农场、任意期间都能预测。

首任务直接交付 empirical 范围发现及结果导出 API，并复用已有创建/回读链；不是再开一轮 readiness 审计。**本文件是待评审草案，下面的实施指令尚未授权执行。** 版本号不分配；不借此进入 V0.3-S5/S6，也不解除 pilot model approval gate。

```text
TASK_ID=NEXT_VERSION_SCOPE_AND_BUSINESS_GOAL_FREEZE_R1
SCOPE_PROPOSAL_STATUS=DRAFT_FOR_COORDINATOR_REVIEW
NEXT_VERSION_NUMBER=NOT_ASSIGNED
PLANNING_AUTHORIZED=true
IMPLEMENTATION_AUTHORIZED=false
IMPLEMENTATION_STARTED=false
NEW_MODEL_EXPERIMENT_AUTHORIZED=false
```

## 2. 检查基线与证据层次

Fresh fetch 后 origin/main = v0.3.1 peeled commit = `80724b0171107c8b2bdeeea17ea4a8a9457903ec`，没有新增 main 提交。原工作分支干净，HEAD 为 `5ebb5b4b8cf7f7bfe7c622dd0339c80f8b7af413`；保留该分支，从 origin/main 新建 `docs/next-version-scope-r1`。本轮没有 DB/API/runtime 探测、原始 XLS 内容读取或预测执行。

[Release v0.3.1](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/releases/tag/v0.3.1) 已发布，仅修 test fixture/CI parity，不改变业务基线。保护规则已实际回读：`full-suite-canary` 为 required check，strict=true。旧 recovery 文档中的“尚未配置”是当时事实，不是当前配置。

证据优先级与用途：

| 层次 | 本轮读取来源 | 可以证明什么 / 不能证明什么 |
| --- | --- | --- |
| 长期愿景 | [README](../../README.md) | 描述天气、加工匹配等远景；不是 next-version scope 或已验收清单 |
| 历史计划 | [development-plan](../v0-3/development-plan.md) 开头、§4.7/4.8、§4.59/4.60 | 原 S5/S6 有定义但未进入；最终 current pointer 优先于历史目标 |
| 当前版本终态 | [closeout](../v0-3/v0-3-version-closeout-and-acceptance-reconciliation-r1.md) | V0.3 closed、限定能力 PASS、S4 no-selection、天气排除 |
| 实际业务执行 | [R5 evidence](../v0-3/forecast-operational-acceptance/evidence/banna-empirical-first-forecast-r5.json) | 版纳运行、日行、峰值、持久化与 fresh readback；不证明其他范围或精度 |
| 当前代码/测试 | [API](../../backend/app/api/trial.py)、[empirical service](../../backend/app/planning/empirical_forecast.py)、[frontend API](../../frontend/src/features/forecast/forecastApi.ts) | 能定位接口兼容性；synthetic unit/browser fixture 不是新真实业务验收 |
| 测试修复历史 | [PR607 CI recovery](../v0-3/pr607-main-full-suite-failure-recovery-r1.md) | fixture FK 与 PR/main parity 根因；release live evidence 补充其后发生的发布 |

[JSON evidence](evidence/scope-and-business-goal-r1.json) 绑定本轮阅读文件的 SHA-256。没有回写旧 R1–R5、S1–S4 或 closeout。大 development-plan 采用相关章节与末尾 current pointer 定位阅读，不宣称逐行审核全部历史追加记录。

## 3. V0.3.1 已完成什么

已验收范围：版纳勐旺农场 / 勐旺加工厂 / Dx / 736.000000 亩，arrival = harvest。历史源 hash 为 `a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5`。

回归参照固定为：2026-10-15 至 2027-05-09，207 日，总量 968113.233000 kg；单日峰值 2027-04-28 / 15117.032000 kg；七日累计峰值 2027-04-26 至 2027-05-02 / 88757.236000 kg。empirical authority、Task9、正常 HTTP 创建、持久化、新 session 回读/hash parity 已通过；这些不是当前 blocker。

S1/S2/S3 COMPLETE；S4 = CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED，selected candidate NOT_ISSUED，V0.2 incumbent retained，MODEL_APPROVED_FOR_PILOT=false。S5/S6 NOT_ENTERED，TEST SEALED。

基线重放历史形状；P50=P80=P90，`NOT_CALIBRATED_IDENTICAL_POINT_SCENARIOS`，不是校准概率区间。多产季泛化、独立预测准确率、真实产季 pilot、production release 均未证明或未包含。

## 4. 面向业务的能力盘点

状态只描述对应子能力，不把 API 存在升级为真实范围验收；NOT_IMPLEMENTED 仅用于已检查代码中明确未接通的连接点。

| ID / 用户问题 | CURRENT_CAPABILITY / 状态 | CODE_OR_DOCUMENT_REFERENCE | ACCEPTANCE_EVIDENCE | BUSINESS_GAP |
| --- | --- | --- | --- | --- |
| CAP-01 给定农场/品种/期间能出日预测吗 | 预注册版纳范围 POST+GET：IMPLEMENTED_AND_ACCEPTED；任意调用参数入口：NOT_VERIFIED | empirical_forecast.EmpiricalForecastCreateRequest 只收 discriminator+authority_hash；api/trial.py 的 POST /forecasts 与 GET /empirical-forecasts/{run_id} | R5 HTTP 200、207 行、hash parity | 期间/面积已在 authority 中冻结，不能通过当前 request 任意替换。注册脚本固定 scope/as_of/season，并要求 canonical identities 预先存在 |
| CAP-02 能直接取得总量/单日/七日峰吗 | empirical JSON 指标与回读：IMPLEMENTED_AND_ACCEPTED；empirical CSV 连接：NOT_IMPLEMENTED | empirical_forecast 使用 core_forecast.metrics.compute_point_series_metrics；旧 export_forecast 调用 _load_verified_forecast | R5 固定三项指标；旧 browser e2e 是 retention-production fixture | 旧 CSV 只读 Core hash namespace，empirical 使用 integer run_id 独立 namespace，不能把 ID=1 发给旧 export 假装已接入 |
| CAP-03 换已有数据的农场/品种呢 | 纯 curve/Task9 参数化基础：IMPLEMENTED_NOT_ACCEPTED（其他真实范围）；无专用代码的完整多范围入口：NOT_VERIFIED | empirical_maturity.build_empirical_curve、empirical_authority；register_banna_empirical_authority_r5.py 与 probe_banna_harvest_baseline_r4.py 固定版纳/Dx | synthetic round-trip tests；唯一 R5 真实范围 | 各范围历史面积、完整账本/缺日语义、日期映射与授权没有共同验收证据；不能复制版纳 policy |
| CAP-04 能知道预测效果吗 | 质量评价/导入/比较工具：IMPLEMENTED_NOT_ACCEPTED（针对当前 empirical 独立精度）；独立效果：NOT_VERIFIED | QualityPage、trial.py quality methods；S3/S4 closure evidence | S3 historical PIT NOT_COMPUTABLE；S4 未选出替代；R5 明确 sanity 不是 scoring | 工具与旧标量结果不是 empirical 精度证明；不能同窗拟合再自证准确 |
| CAP-05 业务人员能直接调用吗 | 老 Trial browser 工程闭环：IMPLEMENTED_NOT_ACCEPTED（真实 empirical）；empirical browser 接线：NOT_IMPLEMENTED；当前 runtime 在线性：NOT_VERIFIED | ForecastPage→forecastApi→旧 Trial schemas；_load_forecast_authority_snapshot 只 join plan/subfarm/marketable policy，不列 empirical authority | forecast-flow.spec.ts 的工程 fixture；R5 是授权 HTTP，而非浏览器验收 | 页面不会发现 empirical hash，旧 summary parser 与 integer-ID GET 路径不兼容。先交付 API 闭环，不默认新 UI/服务器/Agent/MCP |

[Empirical tests](../../backend/tests/planning/test_empirical_forecast.py) 覆盖 synthetic persistence/Task9；[curve tests](../../backend/tests/planning/test_empirical_maturity.py) 覆盖确定性与零日；[browser test](../../frontend/e2e/forecast-flow.spec.ts) 使用工程 fixture。均只读检查，未在本轮执行。

现有 actual-harvest CSV/XLSX 上传、校验、commit 路径在 trial API / actual_harvest_import 中；它不是已接通“任意历史 XLS → empirical authority”的通用注册入口。导入原始历史不是推荐 C 的必要新增工作。

## 5. 授权数据盘点：够做什么，不够证明什么

本轮只读 tracked 文件清单、source attestation 和既有汇总。**INVENTORY_COMPLETE 指该限定盘点已完成，不代表穷尽所有外部数据、每个 farm×variety 的完整性或本机 DB 内容。** 未读两个 XLS payload，未读 materialized TRAIN/VALIDATION/TEST，不把元数据里的全局计数展开为已可预测组合。

| 数据/authority | 已确认范围、日期、面积与用途 | 尚未确认 / 不允许推断 |
| --- | --- | --- |
| data/raw/2024_2025_receipts.xls | 文件被跟踪；R2/R5 绑定 hash a55c…90d5。版纳/Dx/勐旺：3420 匹配行，2024-10-15—2025-05-09；181 observed + 26 zero = 207 日；总量 968113.233000。736 为明确授权的 calibration denominator，不是 subfarm 分摊 | 全文件其他 farm/variety 的完整季节、面积和业务使用资格 NOT_VERIFIED。本轮没有再聚合原始数量 |
| 版纳范围身份 | R2 在 2024/25 选择范围内 farm↔factory 1:1；三分场行数 1271/1159/990。Dx source label 蓝莓原果Dx | 736 不分给三分场；1:1 不外推到跨季/其他厂。R2 matched_relationship.csv 未独立挂载验证；不把 annual_t=1145 用作量值 authority |
| R5 empirical authority/result | authority_hash=723aac97a66e577a737c7fd62d42149e1d66d1108f1142709b13a83aeb9c6911；result_hash=8cba604985f5229b31bf729b4503da2175cfb277c2a9950e1273a5d70059b9be；2026/27 acceptance season；as_of=2026-09-11 | Git evidence 有 hashes/汇总，不包含完整 persisted payload；当前 runtime 是否仍可读 NOT_VERIFIED，后续实施前需合法 runtime binding，不能以 fixture 替代 |
| data/raw/2025_2026_receipts.xls / SOURCE-002 既有清单 | 文件存在；最终 source-owner attestation 描述 2025~2026 单季、84 farm/192 subfarm/20 variety，2025-08-05—2026-04-16。包含版纳及 Dx 等源标签 | 只读 metadata；未建立新业务复用授权，未读取 raw（可能包含 sealed 区间）。84×20 不是有效 scope 数，不证明每个 scope 有两季。未验证与 2024/25 的逐 scope 配对/面积 |
| 旧 master/planting/parameter templates | tracked template 路径存在，R2 搜索没有恢复已授权 observation library | 模板/配置/测试值不是业务数据；未读取私有外部文件、未声称全球不存在来源 |

来源：[R2 mapping](../v0-3/forecast-operational-acceptance/evidence/banna-scope-parameter-authority-r2.json)、[R5](../v0-3/forecast-operational-acceptance/evidence/banna-empirical-first-forecast-r5.json)、[最终 source-owner attestation](../v0-3/s1/evidence/source-002-final-source-owner-attestation.json)。SOURCE-002 的 missing-day authority 与版纳完整 receipt ledger 零日政策不可互换。

**数据结论：足以提出/实现已注册版纳 empirical 结果调用与获取功能；真实验收还依赖合法 acceptance runtime 中相同 authority/result 可用。不足以现在承诺另一真实范围无代码预测，或跨季准确性。** C 不需要额外历史 actual、新天气或未来计划；发现运行库缺失只能报告具体依赖，不能偷偷恢复/重算/重新标定。

## 6. 三方向比较与唯一推荐

| 方向 | 业务问题 / 可复用能力 | 数据支持 | 主要新增工作 | 风险 / 另行授权 | 最小可验收结果 |
| --- | --- | --- | --- | --- | --- |
| A 扩大真实范围 | 其他有历史的 farm/variety 无专用代码出预测；复用 curve builder、Task9、持久化 | 两个文件存在；仅版纳完整 acceptance scope 被验证。其他范围来源/面积/完整性未完成资格确认 | 通用 source→scope registration、范围级政策与验收；不是重做已存在纯数学 | 必须批准新范围、历史使用、面积与缺日/日期政策；不能照搬736/零填/映射。工作量中到大、受数据条件影响 | 至少一个不同真实范围通过同一注册/POST/readback，无 scope 分支；本轮不能指定已合格第二范围 |
| B 明确预测效果 | 独立窗口比对；复用 canonical metrics 与 evidence serializer，不复用旧 S4 执行授权 | 只有一次 shape replay 的明确成功；两个文件不等于同 scope 两个完整合法评价季 | 独立冻结校准窗/评价窗、PIT与label使用规则、naive comparator、完整 evidence，再另行执行 | 新评价/实验与数据授权必需；旧预算不可转用；禁止同窗自证、sealed TEST。阈值没有新批准值 | 一份合法独立窗口比较报告，明确 computability；不承诺“90%”，区间校准另议 |
| **C 降低调用成本（推荐）** | 让操作员发现已注册范围并拿到结果；复用现有 empirical POST、GET、hash verifier、canonical metrics、actor contract | 已有版纳 authority/results 的验收与hash足够界定目标；不新增原始数据需求 | 服务端 empirical discovery + persisted CSV projection + 调用说明/契约测试；保留旧 Trial 路径 | 需另行批准实施与受控业务验收、合法 runtime binding；无新增模型/数据授权需求。不能承诺非技术人员 UI 已交付 | 不查库、不手工拼hash，按服务端范围返回创建/回读并下载同一结果CSV；版纳数值回归不变 |

优先 C 的依据不是技术偏好：A 的数据资格不能由全局计数证明；B 的独立评价边界需要新授权；C 已定位明确的发现/namespace/export 接线缺口，有不可变的真实验收参照，可在不改预测数学、不依赖未来数据的条件下交付。C 完成不自动启动 A/B。

## 7. 推荐最小版本与验收合同（全部待批准）

- NEXT_VERSION_PRIMARY_BUSINESS_GOAL：已授权历史基线的正式 API 调用与结果获取闭环。
- TARGET_USER_AND_USE_CASE：具备 API 调用能力、经过授权的业务技术操作员，获取版纳基线用于人工查看总量及峰期；不承诺免培训的普通用户界面。
- IN_SCOPE：列出当前 actor 可用的已注册 empirical scope/area/window；复用 POST /api/v1/trial/forecasts；独立 empirical namespace 的已存结果回读与 CSV；明确不确定性/基线版本/来源说明；可复制的 HTTP 调用步骤。
- OUT_OF_SCOPE：新 UI/Agent/MCP/服务器/部署平台；任意输入参数重标定、通用原始数据注册、扩 farm/variety、面积外推、任意日期移植；天气/未来生产计划/未来采摘安排；新实验/S4/S5/S6/试点批准/精度评分；跨厂分流、自动削峰、运输优化与production release。
- EXISTING_CAPABILITIES_TO_REUSE：empirical authority verifier/persistence、empirical create/read、Task9 与 canonical peak metrics；不重写算法，不把旧 Core export 直接当 empirical export。
- AUTHORIZED_DATA_AVAILABLE：§5 版纳 source metadata 与 R5 已验收 authority/result 引用；历史原始数据不因本提案获得新用途。
- DATA_OR_AUTHORIZATION_GAPS：coordinator 接受 scope、单独实施/受控执行授权、运行库及 actor 的合法可用性（本轮未探测）；其他范围与B评价仍另行决定。
- KNOWN_LIMITATIONS：只读/执行已注册并授权范围，不提供自由选择任意面积/期间的标定器；calling parameters 本身不是未来计划，但当前 authority 不支持任意改写它们。P50/P80/P90 identical，不宣称精度/多季泛化；不是进入 S5 pilot。
- ACCEPTANCE_CRITERIA：以下 AC-01—AC-08。不设置新准确率阈值；既有 S4 guardrails 原封保留且不执行。

| ID | 怎样判定完成 |
| --- | --- |
| AC-01 范围发现 | 正常 actor 经正式 API 得到版纳/Dx/736、2026-10-15—2027-05-09、HISTORICAL_CALIBRATION discriminator 与服务端 authority identity；旧 Core catalog 不变，无 dependency override |
| AC-02 正常调用 | 使用发现响应的 identity 调用现有 POST，而非查 DB/hash 常量或运行版纳注册脚本。随后通过 empirical read URL 获取 COMPLETED、run namespace、result hash |
| AC-03 结果可用 | 服务端 CSV 从 persisted verified payload 投影207日；总量/单日/7日峰与§3相同，arrival=harvest、单位明确；不在客户端或export时重跑模型/重算指标 |
| AC-04 来源可核 | 输出 source/authority/result hash、业务scope、policy与uncertainty标签；JSON/CSV指向同一run，不能混用integer与Core hash ID；新session读取相同result |
| AC-05 无范围专用代码 | 新 discovery/export handler 中无“版纳”、Dx、736或日期常量分支；synthetic第二scope/同整数ID不同namespace测试证明投影通用，但不把fixture称为第二真实范围验收；旧 pinned registration 原封保留 |
| AC-06 Fail closed | 无权限、无authority、错误namespace、缺/损坏payload或hash冲突均明确失败；不自动注册、重标定、扩大scope，跨actor访问按已批准权限合同约束 |
| AC-07 非破坏回归 | v0.3.0/v0.3.1 refs及旧R5文件不变，旧model/Trial路径测试保持通过；相同authority与同actor重复执行/回读遵循现有幂等性，不承诺跨actor result_hash相同（payload绑定actor） |
| AC-08 验收边界 | exact-head required CI含full-suite实际PASS；单独授权后在non-production acceptance runtime做真实API/CSV验证；不要求production deployment、模型approval、S5/S6或评分 |

## 8. 最多两个阶段，不无限拆规划

| 阶段 | 业务产出 | 复用 / 必要改动 | 验收 / 依赖 / 停止条件 |
| --- | --- | --- | --- |
| 1 交付服务端调用包（一个窄开发PR） | 可发现、调用、查询、下载已注册empirical基线的API和操作步骤 | 现有create/read/authority verifier；仅 discovery DTO/service/route、namespace-safe persisted CSV projection、tests/docs，默认无schema修改 | AC-01—08；依赖独立实施及受控验收授权。缺runtime/authority或必须更改算法时报告具体条件，不伪造数据。成功后停 coordinator review |
| 2 同范围业务交接（仅前阶段通过且另行授权后） | 操作员依步骤独立获取同一版纳结果，形成一页操作验收记录 | 复用阶段1；仅发现的调用说明小修，零新功能 | 不要求工程人员查库/改脚本；保存request/result identity与CSV核对记录。无新scope、UI或精度任务；完成即止 |

### 第一条可直接下发的执行草案（本轮不执行）

```text
TASK_ID=NEXT_VERSION_EMPIRICAL_FORECAST_API_ACCESS_AND_EXPORT_R1
STATUS=DRAFT_NOT_AUTHORIZED
OBJECTIVE=让已授权业务操作员通过正式API发现已注册empirical范围，调用既有预测并取得可回读、可核对的CSV结果；首个真实验收仅版纳/Dx/736。
INPUTS=
  coordinator另行接受本scope并授权实施及一次受控业务验收；
  最新已核验main与v0.3.1不可变回归基线；
  R5 authority_hash=723aac97a66e577a737c7fd62d42149e1d66d1108f1142709b13a83aeb9c6911；
  non-production acceptance runtime内已有合法empirical authority及正常actor配置；
  不读取新的原始历史/VALIDATION/TEST，不重新标定。
ALLOWED_CHANGES=
  在现有trial/planning模块增加actor-gated empirical authority discovery；
  建议GET /api/v1/trial/empirical-authorities（新增待批准route，不能声称已存在）；
  复用POST /api/v1/trial/forecasts与GET /api/v1/trial/empirical-forecasts/{run_id}；
  建议GET /api/v1/trial/empirical-forecasts/{run_id}/export.csv；
  CSV仅投影verified persisted daily_rows与metrics，保留单位、namespace、scope和hash；
  相应DTO、tests、API操作文档；只处理当前actor有权使用的已注册authority；
  如需扩schema/改变权限政策而非复用既有合同，先停止并报告，不默认授权。
FORBIDDEN_CHANGES=
  模型/参数/curve数学、标定/训练/评分、S4/S5/S6；
  weather、未来生产计划、未来采摘安排、任意area/date外推；
  新frontend/Agent/MCP/服务器/部署、原始数据导入或自动注册；
  fixture代替真实authority、修改旧evidence/tag、绕过CI、Ready/Merge/release。
ACCEPTANCE_TESTS=
  本提案AC-01至AC-08；先synthetic权限/namespace/CSV/hash回归；
  exact-head标准CI与full-suite-canary实际PASS；
  已获单独受控执行授权后真实Banna HTTP discovery→create→fresh read→CSV；
  207日、968113.233000总量、15117.032000单日峰、
  88757.236000七日峰与R5一致；不计算准确率。
DELIVERABLES=
  一个窄Draft PR：API接线/CSV投影、tests、可复制调用步骤、
  单独区分synthetic工程证据与真实non-production验收证据。
STOP_GATE=COORDINATOR_EMPIRICAL_FORECAST_API_ACCESS_AND_EXPORT_REVIEW
NO_STEP_IMPLIES_THE_NEXT=true
```

若授权后运行库没有既有authority，停止真实执行部分并报告确切依赖；不得升级为恢复数据库、新范围注册或要求新业务事实的大包任务。可交付代码/工程测试，但不能宣称真实验收PASS。

## 9. 不变边界与本轮验证

ARRIVAL_EQUALS_HARVEST=true；FORECAST_INPUT_DIRECTION=HISTORICAL_DATA_ONLY。WEATHER_WORK_AUTHORIZED=false；FUTURE_PRODUCTION_PLAN_INPUT_AUTHORIZED=false。S4不重开，TEST封存，预算零变化。最后接受预算快照8 consumed/24 remaining，不是本轮DB readback，不是新任务预算。

本轮只新增本文件和JSON evidence；没有新预测、标定、拟合、评分、DB操作或业务数据payload读取。文档/JSON一致性、引用存在与hash、两文件allowlist及git diff --check必须通过。推送后照常执行required CI；未结束报告PENDING，不修改workflow，也不以docs-only豁免canary。最终SHA/PR/CI状态由GitHub和最终回报绑定，避免把未完成CI写成PASS。

```text
FORECAST_CODE_CHANGED=false
MODEL_CHANGED=false
PARAMETER_AUTHORITY_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
API_CHANGED=false
CI_CONFIGURATION_CHANGED=false
HISTORICAL_EVIDENCE_REWRITTEN=false
V0_3_BASELINE_CHANGED=false
S4_REOPENED=false
NEW_MODEL_EXPERIMENT_EXECUTED=false
VALIDATION_BUDGET_DELTA=0
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
FINAL_STOP_GATE=COORDINATOR_NEXT_VERSION_SCOPE_R1_REVIEW
```
