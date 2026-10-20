# V0.19 S3 真实数据权威准入方案 R1

TASK_ID=V0_19_S3_REAL_DATA_AUTHORITY_ADMISSION_PREFLIGHT_R1

## 1. 结论、基线与授权边界

本交付是**可执行的核验计划与授权申请材料**，不是已执行的数据核验。
十二项真实权威全部 NOT_VERIFIED，已核验 0 项；真实数据、实验、评分授权均为 false。
PHYSICAL_BASIS_ADMISSION=BLOCKED；PIT_EVIDENCE_ADMISSION=BLOCKED；
COMMON_COHORT_ADMISSION=BLOCKED；S3_REAL_SCORING=BLOCKED。
这些 BLOCKED 指真实实验准入，不表示本次文档交付或合成框架失败，也不证明数据不存在。

审查基线为 `0bc88ab1196e54b4ff9fc15d17bb7f4e05cf4bd1`，与 fresh fetch 一致。
PR #738 已合并，其修正 HEAD 为 `e363174c2b900c773f95735bdc311cc567dcbd33`。
合并后 main CI [39344070084](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/39344070084)
在本次起始核验时为 in_progress，不能预填成功；其成功是正式验收前置条件，
但不阻止本次独立 Draft PR。最终 HEAD/CI 与前置 CI 的后续实际状态在 PR 回执记录，
不在提交中制造自引用 Hash 或未来成功结果。最新正式 Release 为 v0.18.0。

本轮仅静态阅读仓库合同、Schema、研究源码及 GitHub PR/CI 元数据。
没有连接任何数据库、调用业务 API、探测本机私有数据目录、打开采收标签、
下载模型 artifact 或读取当前 2026–2027 actual。来源中的路径和环境变量不被解析执行。
只新增本文与 `../evidence/v0.19-s3-authority-preflight-r1.json`，不修改任何实现或旧证据。

## 2. 来源调查办法：先清单，后批准，再核验

1. 由未来指定的数据保管人先提供**不含标签值**的来源清单、字典、责任证明和权限申请。
   本轮不向未知系统试连；所有实际 source/dataset/version、责任人、授权主体均 UNKNOWN。
2. A 数据读取批准精确限定来源、字段、实体、时间、用途、留存及可读身份。
   未批准前不能为了“核验是否存在”打开数据。仅获 A 也不能评分。
3. 获 A 后，独立隔离环境只读取批准子集，逐项复核下表、原始字节/行集及签发证据。
   每个核验记录需记录核验者、UTC 时间、方法、结果、批准编号和来源 Hash；不记录凭据。
4. 来源可用与用途获准分开记账。代码存在不等于 AVAILABLE；实际未知保持 NOT_VERIFIED。
   MISSING 只用于获准调查后确证的物理缺失；BLOCKED 记录准入障碍，不伪造缺失事实。
5. B 实验评分批准另行签署。十二项权威、物理口径、时间证据、C0、隔离与独立封存
   全部满足且授权未过期才可准备未来实验；任何缺项均停止，不能以合成 AVAILABLE 补齐。

## 3. 十二项权威准入矩阵

以下每行状态均为 NOT_VERIFIED，实际证明引用均为空，责任人与授权主体均 UNKNOWN，
真实签发时间证据均未核验。JSON 的 authority_items 为逐项完整机器合同，包含字段类型、
单位、适用时段、候选映射、证明材料、验证方法、签发证据状态和阻断原因。
下列候选是源码声明，不是已确认的来源系统或真实记录。

| # / 权威 | 必需字段、类型与单位 | 允许时间/来源候选 | 证明与核验方法；缺失即阻断 |
|---|---|---|---|
| 01 BASE_SUBFARM_VARIETY_IDENTITY | organization/base/subfarm/variety_id: string；父子成员、registry_version、mapping_hash: SHA256；有效起止: local date | 仅未来 A 批准季节/实体，映射在 origin/目标日适用；导入 farm_code/subfarm_or_plot_code/variety_code 与标签 business keys 为候选，不假定 farm=base | steward 签认的主数据及版本化别名/父子映射，逐行唯一映射、时间适用及成员完整性；无批准映射拒绝跨实体合并 |
| 02 AREA_AND_EFFECTIVE_DATE | area_mu: 正有限 Decimal string（mu）；area_basis、source、effective_from/to: date；area_hash | 原点及声明 support 适用的同一批准面积口径；OperationalPeak productive_area_mu、AreaAuthority 为声明候选 | 面积测量/登记证明、单位及有效期、修改历史；核对双方相同面积，kg/mu 不直接当 kg；无证据禁止猜面积或事后校准 |
| 03 RUN_AND_ISSUED_AT | 完整 ForecastIdentity、run_id、origin: aware datetime；issued_at、sealed_at: aware datetime；source_result_hash | issued_at 与 cutoff 均严格早于最早目标日本地 00:00；保存 run.created_at/completed_at 仅是存储候选时间 | 实际签发日志、可信时钟及独立封存回执、run/rerun 原身份；不得拿 origin_date、文件 mtime、后来重放时间替代原始签发 |
| 04 MODEL_PROFILE_FIT_HASH | model_id、policy/subpolicy、code_commit、profile/input/config/fit/source/result SHA256；fit_scope/cutoff | 只允许冻结 Operational Peak 基线与唯一 S2 候选；训练来源/版本在批准范围内；authority snapshot 仅声明候选 | 原始模型/配置与 fit provenance 的签认清单；获 A 后验字节并追溯训练范围；不得从其他 Ridge 模型借 Hash 或精度，不下载未知 artifact |
| 05 HARVEST_DATE_AND_UNIT | harvest_business_date: date；timezone: IANA；quantity: 有限非负 Decimal string；physical_event/basis/unit | 仅批准目标日，Asia/Shanghai 业务日；FARM_PICK/OBSERVED_WEIGHT/KG 声明来自 import schema/enums | 称重/采摘事件字典、单位和完整覆盖证明；区分田间采收、到厂、可售、成品、kg/mu 与日率；无法证明同物理量则 BLOCKED |
| 06 LABEL_AUTHORITY | source_system/dataset/version、logical_record/revision_id、record_status、label_authority_hash、label_row_set_hash | 仅 A 允许标签范围；B 评分前不得向预测阶段暴露标签；I7 winner/snapshot 字段为候选 | 保管责任和合法用途证明、原始链路、修订终态、去重规则；核对 winner/commit/mapping/label Hash，禁止从列名断言真实标签权威 |
| 07 AVAILABLE_AT_INGESTED_AT | source_available_at、import_received_at、ingested_at、revision_known_at: aware datetime；authority_reference | 所用输入各版本的实际可知/入库时点均不得晚于 cutoff；PIT adapter 的 known_at=import_received_at 是声明，不补造 source_available_at | 原系统可用日志、入库日志、首次版本与更正链；source_recorded_at 缺失或 user-asserted 不能冒充可信时点；缺证据维持 STRICT_PIT=false 与 BLOCKED |
| 08 INPUT_CUTOFF | cutoff: aware datetime；输入成员及各自可用时间；input_manifest_hash | input_available_at/ingested_at <= cutoff <= issued_at < target_start；history_cutoff: date 不等价于时刻 | 请求/配置封存和逐输入时间清单；核对 cutoff 时已可得版本，不读取目标日未来标签；截止时点不明不允许打分 |
| 09 LABEL_MATURITY_COMPLETENESS | mature_at、label_available_at、scoring_as_of: aware datetime；finalized/revision、完整日历与缺失状态、coverage Hash | mature_at 与 label_available_at 均 <= scoring_as_of；H7/H15/整季分别完整，整季需批准全季结束日 | 标签保管人终态/迟到更正政策和完整性清单；无记录不等于零，不能用 FINALIZED 或快照执行时间单独证明完整成熟 |
| 10 TRAIN_VALIDATION_EXPOSED_OOT_SPLIT | split、train/evaluation_scope_sha256、来源总体、season/base/origin/target 范围、暴露登记 | 只用未来明确批准范围；2025–2026 为 EXPOSED_HISTORICAL_BENCHMARK；2026–2027 actual 本轮禁读 | 训练/验证成员和污染/暴露账本，查重叠与标签可用边界；不随机切相邻日期、不重新命名 blind OOT、不混不同训练评价范围 |
| 11 COMMON_COHORT_MEMBERSHIP_HASH | comparison_family、source_population_sha256、evaluation_scope_sha256、C0/Cm 成员/日期/Hash、排除原因 | C0 在标签内容打开前固定；每 metric/split/window 的 Cm 由冻结规则产生，无事后选择 | 预注册成员清单与共同来源签认；逐单元配对身份/面积/季节/物理量一致；合法跨基地成员保留独立 input/profile Hash，拒绝未登记跨来源/季节/训练范围池化 |
| 12 PREDICTION_LABEL_SEALS | 双方 prediction/config/source/input Hash、prediction seal/time/receipt、label seal、custody identities、结果 Hash | 预测先封存再开评分标签；实际 issued_at 另须早于目标开始；两种时间约束不可相互替代 | 独立保管访问日志、签发/封存回执、核验者与更正链；SHA256 仅是内容摘要不是签名/时点/权限，单机自写时间戳不自动可信 |

## 4. 静态字段映射与物理口径

- `backend/app/models/operational_peak.py` 声明面积、产季、origin_date、authority/policy/
  baseline/result Hash、逐日 predicted_kg/kg_per_mu/reference_bin 及 created_at/completed_at。
  它没有证明某条运行在目标日之前实际签发；origin_date 是 date，不是签发时钟。
- `forecast_intelligence/read_schemas.py::ForecastIdentity` 与 `read_service.py::_source`
  定义精确 run/层级/实体/季节/origin/baseline/policy 和来源 Hash 核对。该接口的
  完整性验证不能单独证明训练可用时点、真实标签物理口径或预测发行时点。
- `actual_harvest_import/schemas.py/models.py/enums.py` 声明 FARM_PICK、OBSERVED_WEIGHT、KG、
  UNKNOWN_NOT_ZERO、source_recorded_at_authority_status、import_received_at/ingested_at。
  这为未来核验提供字段位置，不证明真实系统已提供可信 FARM_PICK 记录。
- `actual_harvest_labels/schemas.py` 声明 winner、标签快照、映射、行集/排除 Hash，
  可设计修订终态和审计映射；本轮不创建任何快照，不使用 empty-for-all 查询。
- `pit/actual_harvest.py` 在源码中把 receipt 当 known_at，并在缺 source_recorded_at 时
  使用回退时间。此回退不能被研究准入方案升级为 source_available_at 权威。
- `area_yield/data.py` 允许在 complete_ledger 为真时输出授权零日；S3 不可仅凭布尔值
  为缺标签填零。未来必须取得权威完整账本及零日证明，否则按 S1 不可计算。
- S1 历史对照公开声明部分历史量为
  ACCEPTED_MAPPED_FARM_SUBTOTAL_NOT_COMPLETE_FULL_SEASON_TOTAL。
  因此不能宣称既有历史数据已被证明是完整田间采收。没有读私有行，不能进一步断言
  所有历史数据都是到厂量；结论是**真实口径与覆盖未核验**，不是凭空更换来源标签。

准入口径必须分别登记：FIELD_HARVEST_KG、FACTORY_RECEIPT_KG、MARKETABLE_KG、
SORTED_FINISHED_KG、KG_PER_MU、DAILY_RATE_KG_PER_DAY。kg 是日桶内质量，kg/day 是率，
同一日期字段不使二者等价。不得通过重命名、单位乘除或未批准损耗比例建立映射。
未来如仅可证明到厂代理，则不得进入本次 ACTUAL_HARVEST_KG 比较；另行批准的代理
研究合同才能分面分析，不能在此放宽 S1、合成评分器或“换口径凑样本”。

## 5. 时间、样本及预测/标签隔离合同

时刻一律要求明确 UTC offset，保留原 IANA 时区与 UTC 归一化证据；禁止 naive datetime。
业务 date 为 Asia/Shanghai 日期，不截断 UTC 日期。验证链为：
`available_at/ingested_at <= cutoff <= issued_at < target_start_local_midnight`。
刚好目标日 00:00 也拒绝；完整窗口有晚签发日不得删日后继续评分。
FULL_SEASON 必须在完整目标季开始前签发且完整覆盖，不能用 H15/remaining window
拼成整季。标签仅在 `mature_at/available_at <= scoring_as_of` 后开评分。

**历史重放特别阻断**：现在生成的 S2 候选不能冒充过去已签发预测。模拟 origin、
回填 issued_at、源码版本日期和事后 seal 均不能证明历史签发。若无法提供候选与基线
各自真实、目标前的签发证据，则按本合同停止历史评分。未来若要作明确标识的
retrospective replay，须 Owner 单独批准相应协议修订和边界；A/B 批准本身不自动豁免
当前冻结时点要求。STRICT_PIT=false 与已暴露样本限制继续保留，不声称 prospective。

未来执行顺序（本轮均未执行）：

1. 获 A 后，以批准的非标签清单登记 comparison_family、来源总体/训练/评价范围 Hash、
   实体/面积/季节/origin、完整日历及失败成员，预注册 C0 和成员 Hash。
2. 固定 Operational Peak 基线、S2 唯一候选方法/config/source commit；双方同一合法
   profile/input、面积、season anchor 和 support，逐 bin 微 kg 守恒；H7/H15 不重新归一化。
   预测阶段不能打开评分标签；若 profile 训练来源已用评价标签则先判定污染并阻断。
3. 在 B 批准的隔离环境生成/取得合法预测并封存双方身份、日值与来源、时间证据。
   预测保管人与标签保管职责必须指定；仅“先写一个 Hash 文件”不算独立保管。
4. 独立评分路径先验证 seal、时间和授权，再开成熟标签。每 metric/split/window
   使用双方共同可计算 Cm；成员与排除主因逐项保留。不能删困难基地、缺预测或缺标签。
5. 依 S1 十指标、分子分母、coverage/breadth 与预注册诊断完整报告改善/退化/不可计算。
   H7_PREFIX、H15_LOCAL、FULL_SEASON 不混汇；不同 comparison 身份用独立 seal/report。
   合法跨基地共同总体允许不同的基地 input/profile/面积，但每单元双方来源与口径匹配。
   Cm 不是评分后优化的第二个 C0；覆盖不同只允许 CONDITIONAL_ON_COMMON_COMPUTABLE_COHORT。

当前 S3 `v019_synthetic_validation.py` 仅接收字面 SYNTHETIC 数据；#738 已补共同来源/
评价范围隔离及目标前签发门禁。本方案不把它改成真实数据入口，不让“改名 SYNTHETIC”
成为读取许可。未来可信来源适配与执行路径须在独立授权中明确，不能由本文自动实施。

## 6. 两项分开审批的申请模板

所有占位值必须由有权主体明确填写并有可追溯决定；空白、UNKNOWN、过期或范围含糊均拒绝。
以下两表只是申请模板，未签署、未批准，没有真实来源、账号、路径或凭据。

### A — REAL_DATA_READ_AUTHORIZATION（当前 false）

| 必填项 | 待填写内容 |
|---|---|
| approval_id / approver / data_custodian | UNKNOWN；批准人的权限依据与责任角色；批准/生效/到期 aware 时间 |
| source_system / dataset / version / immutable_identity | UNKNOWN；确切版本/行集身份，禁止 wildcard、全库扫描或自动 latest |
| seasons / base/subfarm/variety allowlist / business_date range | UNKNOWN；逐项枚举；2026–2027 actual 在本轮明确排除 |
| field_allowlist / units / physical_basis | UNKNOWN；对应十二项矩阵；标签值与非标签元数据分开列，敏感字段最小化 |
| allowed purpose / reader / environment / access method | 只为经批准的 S3 权威核验；授权身份、隔离环境和只读方法待指定，不执行写入 |
| input_cutoff / available-time proof / label access stage | 待指定；预测阶段标签不可见，标签保管与评分解封条件单列 |
| retention / export / redaction / revocation / disposal | 允许保留的 Hash、审计、脱敏结果范围、期限与责任人待指定；原始标签不提交 Git |
| decision / signed reference | PENDING_OWNER_DECISION；不由 CI 或本文推定；不自动授予 B |

### B — REAL_EXPERIMENT_SCORING_AUTHORIZATION（当前 false）

| 必填项 | 待填写内容 |
|---|---|
| approval_id / approver / executor / independent reviewer | UNKNOWN；分别指定角色、审批来源和有效期 |
| prerequisite A / twelve-authority review / physical/PIT admission | 绑定具体已批准 A 与核验报告；任一未核验则不可开始；不因 B 豁免时间合同 |
| baseline / candidate / method/source/config identities | 固定 OPERATIONAL_PEAK:AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1 与 BIN_CENTER_LINEAR_PER_BIN_MASS_V1；实际预测及 config/source Hash 待核验 |
| comparison identity / season / split / C0 / windows | UNKNOWN；C0 manifest/hash、共同来源/训练/评价身份和完整日期事前登记 |
| metrics / diagnostics / exclusions | 严格 S1 十指标，冻结主因优先序、共同 Cm、分子分母、失败/退化保留；不选优，不调参 |
| isolation / two-phase sealing / label custodian | UNKNOWN；隔离环境、预测无标签访问、可信签发与独立解封日志；任何未满足项阻断 |
| audit / output / retention / stop rules | 绑定真实代码/config/预测/标签/seal/结果 Hash 与执行日志；缺权威/过期/Hash 漂移立即停止 |
| permitted operations / prohibited operations | 仅明确批准的对照评分；训练/重拟合/参数搜索/模型晋级/部署仍不授权 |
| decision / signed reference | PENDING_OWNER_DECISION；A 不蕴含 B；B 不扩大 A 的来源、字段、季节或实体 |

## 7. 阻断清单、风险及下一步

当前阻断：十二项真实证明全未核验、责任人与数据/标签保管人 UNKNOWN、A/B 未批准、
田间采收与到厂代理映射未证明、历史真实签发/PIT 不足、真实 C0 与独立保管未建立。
未知不等于实际不存在；不能填造来源、时钟、面积或审批。对缺证据项先请保管人提供
不含业务值的清单及责任说明，再由 Owner 决定 A；B 必须等待核验材料并另行批准。

2025–2026 仅为 EXPOSED_HISTORICAL_BENCHMARK；2026–2027 actual 禁止本轮访问。
不发布新 WAPE/峰时 MAE/改善率/显著性或精度达标结论，不改预测算法，不晋级模型。
15 项 V0.18 生产风险及其历史记录不在本任务变更范围；工程 CI 不代表生产验收。
PRODUCTION_READINESS=NOT_READY；S3_FORMAL_COMPLETE=false。

本轮成功标准仅为：两份方案内部一致、固定 Git 来源 SHA256 可复核、历史文件不变、
相关离线合同及 exact-head CI 通过、独立 Draft PR 可审查。真实准入继续 BLOCKED。
不新增合同测试文件；本轮以不入库的内存校验核对 JSON/canonical/来源/状态/白名单，
并运行已有纯合成合同回归。实际命令与结果在 PR 回执记录，不伪造已执行核验。
最终验收仍等待 #738 合并后 main CI 成功、独立复审和 Owner 授权。

READY_AUTHORIZED=false；MERGE_AUTHORIZED=false；RELEASE_AUTHORIZED=false；
DEPLOY_AUTHORIZED=false；REAL_DATA_ACCESS_AUTHORIZED=false；
REAL_EXPERIMENT_AUTHORIZED=false；REAL_SCORING_AUTHORIZED=false；STOP=true。
