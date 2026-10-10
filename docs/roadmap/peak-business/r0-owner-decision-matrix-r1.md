# Peak Business R0 — Owner 业务决策表 R1

本表供业务、数据和版本 Owner 审核。所有选择仍为 `PENDING_OWNER_DECISION`；建议不构成批准或实现授权。

| ID | Recommendation | Alternatives | Required data / authority | Business impact | Owner decision required | Implementation blocker if pending |
| --- | --- | --- | --- | --- | --- | --- |
| DECISION-01 — 业务时区与自然日口径 | 保留 saved forecast 的已签发业务 `date`，不由浏览器转换；统一生产业务日期策略后以版本标记。Operational Peak 当前为 Asia/Shanghai 候选，Core Forecast 标注 HARVEST_BUSINESS_DATE。 | 逐来源保留日期域并在报告中显示；或由业务正式指定一个共同 IANA zone 和跨日切分时刻。 | 每个来源 date 的创建规范、签发时区/时刻、跨午夜采收归属规则。 | 影响日峰日、rolling 窗口、班次/产能日与跨端 parity。 | 确认统一 IANA timezone、business-day cutoff，以及保存曲线 date 是否直接代表最终业务日。 | 不同 date basis 的预测和厂能力不得合并或比较。 |
| DECISION-02 — 连续高产期规则 | 未批准阈值前不分类、不告警；优先先选可解释的绝对 kg/day 或与可信处理能力比值方案，再决定持续天数。 | 绝对日量；对版本化同季基准的比例；同日真实可用处理能力负荷比例。 | 绝对阈值/单位；可信基线及版本；或基地—工厂映射和日期级 available throughput；最短天数与缺日策略。 | 决定谁会看到“高产期”、能否用于人员/工厂计划，误报/漏报后果。 | 选择方法、比较符 `>`/`>=`、阈值、连续日数、有效范围及审批人。 | `HIGH_PERIOD_THRESHOLD=PENDING_OWNER_DECISION`；没有该决策不得展示正式高产区间/告警。 |
| DECISION-03 — 产量集中指标与比较区间 | 首选同时评估 `MAX_ROLLING_7_SHARE` 和 `DAILY_PEAK_TO_MEAN_RATIO` 的可解释性，但不设风险 band；N-day prefix share 仅在 N 与比较周期批准后启用。 | 只报告 rolling-7占全期；固定 D1–DN 前缀占比；峰量/全期均量；或批准的组合。 | 完整预测日期范围、N 值、分母是否为完整 D1–D15/其他范围、零分母政策、跨 origin 可比性。 | 改变“集中”含义与排序；与预测 horizon 不一致会产生误导。 | 批准指标集合、N、date window、是否跨 run 比较、报告层级与风险阈值。 | 未批准则值可为候选设计但业务 `READY`/风险等级不启用；阈值仍 null。 |
| DECISION-04 — 加工厂处理能力定义与计量口径 | 分开设计 `DESIGN`、`PLANNED_RECEIVING`、`AVAILABLE_PROCESSING`、`ACTUAL_PROCESSED`；产品接口应优先基于日期/班次的 available throughput，并声明 incoming kg 或其他 basis。 | 设计能力只作背景；计划接收能力用于计划；产线/班次 available throughput 用于情景负荷；更细产品线分类。 | 设备/产线、班次/工时、停机、物料/质量范围、gross/net mass basis、历史修订与审批。 | 决定情景负荷和工厂可行性；不同 kg basis 直接对比会高估/低估能力。 | 确认业务指标定义、统计周期、gross/net basis、停机/加班是否计入、负责发布的岗位。 | 没有同 basis 的日期级权威能力时不得展示真实 factory overload；S2 手填仍是 synthetic/assumption scenario。 |
| DECISION-05 — BASE→FACTORY 权威发布者 | 指定独立业务主数据 Owner 发布稳定 ID、有效日期和来源版本；Forecast Data Steward 审批访问，不以应用管理员代业务签字。 | 既有 ERP/主数据系统；独立受控的版本化 mapping package；其他正式业务系统。 | 稳定 base_id/factory_id、组织归属、source owner、授权审批责任、revision/revocation SLA 与 provenance。 | 决定基地量能否合法分解给工厂，授权/审计能否追责。 | 命名发布者、审批/备份人、主数据源、修订及撤销操作责任人。 | 当前 `FACTORY_ASSIGNMENT_AUTHORITY=NOT_AVAILABLE`；未确认之前禁止推断或上线映射。 |
| DECISION-06 — 多厂分配与异常调拨 | 建议使用生效日期明确的 `SHARE` 或 `EXPLICIT_QUANTITY` 单一分配模式；调拨作为审批事件 supersede 原 mapping；冲突 fail closed。 | 单一工厂绑定；按显式 share；按计划 kg；有 Owner 审批的临时转厂 overlay。 | 多厂业务事实、分配比例/数量、守恒规则、日期边界、临时调拨记录与审批源、工厂停产状态。 | 影响工厂流量守恒、重复计量、异常处理与历史重现。 | 决定比例/数量的优先级、残量表示、有效区间闭开边界、冲突/紧急调拨审批。 | 未有规则或授权记录，factory assignment 输出须 NOT_AVAILABLE/PARTIAL，不进行 routing。 |
| DECISION-07 — 报告使用范围、授权与审批 | 报告只基于调用者获准的完整 saved-run response 和服务端指标；报告用途限于内部规划，未批准前不外发/作正式经营结算。 | 管理内部摘要；工程可追溯明细；对外报表需独立审查和脱敏。 | 目标用户、数据分级、字段/导出许可、保留期、审计记录、报告 Owner 与批准人。 | 决定敏感预测/组织信息如何传播、报告能否用于财务或生产承诺。 | 指定可见受众、用途、导出审批、保留与撤销策略、最终报告签发角色。 | 未批准前不建一般导出/共享报告；no-store 与授权绑定由后续实施设计审查。 |
| DECISION-08 — 未来版本编号/名称及阶段边界 | 保持 V0.18 `BUSINESS_USABILITY_AND_SAFE_PILOT_FOUNDATION` 及原 S0–S6，不改名、不宣布被替代；把 PEAK_BUSINESS 仅作临时工作流。 | 后续采用新的 Owner 选定版本；或先批准 V0.18 正式范围修订并逐项评估冲突（本评估不推荐默默改范围）。 | 当前版本治理状态、跨线依赖、实施/数据授权链、产品目标与 closeout gate。 | 决定能力归属、发布承诺、授权和历史状态是否可审计。 | 选择未来版本号/名称、版本目标、阶段顺序、是否与 V0.18 安全身份工作存在显式依赖，以及各阶段 Owner。 | `FUTURE_VERSION_NUMBER=PENDING_OWNER_DECISION`; `FUTURE_VERSION_NAME=PENDING_OWNER_DECISION`; 不启动新版本或任何阶段。 |

## 一页式建议

建议先批准业务 date basis、rolling-7 与单日峰的表达/完整性规则，再由明确的业务阈值 Owner 选择是否需要“连续高产”分类。加工厂能力的关键不是先加一个数字字段，而是先任命基地—工厂主数据与工厂处理能力发布者，明确 kg basis、有效日期、多厂分配和异常调拨。只有这些决策与用户资源授权都存在，才可将结果称为业务可用。未来版本名/编号继续待 Owner 决定；不改写 V0.18。
