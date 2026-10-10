# Peak Business R0 — 基地与加工厂产能权威合同候选 R1

状态：设计候选，不是实际主数据，不授权建表、连接业务系统、导入或生产计算。当前 `FACTORY_ASSIGNMENT_AUTHORITY=NOT_AVAILABLE`、`FACTORY_PROCESSING_CAPACITY_AUTHORITY=NOT_AVAILABLE`。

## 1. 必须区分的业务量

| 概念 | 含义/单位 | 允许的 authority | 当前边界 |
| --- | --- | --- | --- |
| 基地预测采收量 | 某 saved forecast 对特定 BASE、业务日期预测的采收 kg/day | 完整绑定且通过 canonical verification 的 saved curve | Operational Peak 可提供 BASE point curve；不等于实际采收或送厂量。 |
| 基地实际采收量 | 实际采摘/采收的 kg/day | 经 Owner 授权的 actual 系统、时间与版本证据 | 本轮未授权访问，当前季 actual 不可用；不得用预测代替。 |
| 加工厂计划接收量 | 业务计划送到特定加工厂的 kg/day | 经批准的计划/调拨 authority | 不等同基地预测或实际收获量；需要映射、物流/时间转换和计划发布者。 |
| 加工厂设计处理能力 | 设备或产线名义设计吞吐 kg/hour 或经批准折算 kg/day | 经批准设计/设备能力来源及版本 | 不是当日可用能力，也不是实际处理量。 |
| 加工厂实际可用处理能力 | 指定日期/班次/产品的可用吞吐 | 经批准的生产计划、设备/停机/工时等来源 | 当前无权威发布源；不能从面积、人员数或设计能力猜测。 |
| Core Forecast `effective_harvest_capacity_kg` | Core Forecast 内部 harvest/inventory 模型的 effective harvest capacity 字段 | 该 Core Forecast 自己的 saved curve/result authority | 不是 factory processing throughput，不允许改名、映射或投入 Operational Peak 作为加工能力。 |

`V0.16 S2` 的 `daily_handling_capacity_kg` 是用户显式输入的情景参数；合成 cost contract 下的结果仍是 `SYNTHETIC_LOSS_UNIT`。它不是已核实工厂值，不会创建生产 capacity authority。

## 2. BASE → FACTORY 映射候选

映射不是预测层级，不改变 `BASE → REGION → COMPANY` hierarchy，也不代表每个 BASE 只属于一个 FACTORY。候选版本化记录字段：

```text
mapping_id
mapping_revision
base_id                 # 稳定主数据 ID，不用名称匹配
factory_id              # 稳定主数据 ID
valid_from_business_date
valid_to_business_date  # 约定为 exclusive，边界待 DECISION-06 签署
allocation_method       # SHARE | EXPLICIT_QUANTITY | NOT_AVAILABLE
allocation_share        # canonical Decimal string，SHARE 时 [0,1]
quantity_basis          # EXPLICIT_QUANTITY 时必须声明 kg/time basis
assignment_type         # STANDARD | TEMPORARY_TRANSFER
supersedes_mapping_id
source_system / source_record_id / source_revision
source_sha256
published_at / approved_by / approved_at
reason_code / status / revoked_at
```

`source_system` 必须来自受信任发布目录/接口元数据，而不能由客户端字符串或旧 run 猜出。每条关系必须可回放到原始发布件及批准记录。组织边界、基地 ID 和加工厂 ID 由指定主数据权威签发；记录创建人、显示名称、地理邻近、仓库路径均不能推断关系。

### 多加工厂和分配守恒

同一基地在同一业务日可对应多个加工厂，但必须有同一有效 revision 的显式分配规则：

* SHARE 模式下，在被声明为完整的基地/日期/forecast scope 中，各工厂分配比例精确合计 1；否则必须有显式 `UNALLOCATED_SHARE`，不能把缺失余数摊派。
* EXPLICIT_QUANTITY 模式下，每个数量绑定实际计划来源和相同单位/时段；其和不得超出被授权可分配预测量，未分配部分需保留为 unallocated，不得默认送往任意工厂。
* 单一分配版本内不得对同一 BASE/日期/目标 scope 重叠两种有效 assignment。SHARE 与 EXPLICIT_QUANTITY 不可混用，除非另有获批的确定性分配合同。
* 对已汇总 REGION/COMPANY，必须先有可审计且同一历史 hierarchy/同一日曲线的 BASE 明细及映射授权；不可拿当前 registry 回填旧 forecast snapshot，也不可将 child peak 进行分配。
* 缺 child、重复/冲突分配或 assignment revision 变化时，工厂分解为 `PARTIAL` / `AUTHORITY_MISMATCH`，不伪造 100% 完整分配。

### 临时调拨、停产与修订

临时调拨应是有生效区间、调出/调入范围、数量/比例、审批、理由、来源 hash 和 supersession 关系的独立事件，不能无痕覆盖正式映射。生产停产、部分停产、产线维修分别作为容量状态/可用时段的授权记录，不删除原 design capacity。冲突时间段、未经审批的人工覆盖或来源撤销必须 fail closed 并显示原因。

## 3. 加工处理能力合同候选

至少拆开：

1. `DESIGN_PROCESSING_CAPACITY`：铭牌/设计、配置的工艺范围、设备线、上游约束及来源修订。
2. `PLANNED_RECEIVING_QUANTITY`：业务计划的 factory/date/shift 接收 kg，单独发布和审批。
3. `AVAILABLE_PROCESSING_CAPACITY`：指定日期/班次/产线/产品条件下，考虑计划工时、停机、可用产线等的授权可用吞吐。
4. `ACTUAL_PROCESSED_QUANTITY`：真实生产结果，独立实际数据 authority，不是 capacity。

任何比较都必须声明输入基准：毛采收 kg、送达工厂 kg、进入分选线 kg 或合格商品果 kg。若 forecast basis 与 factory capacity basis 不同，需要 Owner 批准的收率/物流/时间转换合同，提供其版本、来源和不确定性；禁止默认它们 1:1 相等。

候选记录至少绑定 `factory_id`、business date/time interval、production line/product scope、capacity quantity + unit、quantity basis、operating hours/shift、gross/net basis、source/policy revision、source hash、publisher、approval、effective interval、downtime/exception overlays、issued/ingested timestamps、supersedes/revocation。`effective_at` 与记录入库时间分开，不能把 created_at 当生效证明。

聚合到 factory/date 的能力只能依据一个无重叠、完整、同 basis 的授权产线集合。不同单位、时段、产品/质量等级不能直接求和；部分能力只报 PARTIAL。历史日期用当时生效版本，不能用当前能力回填。

## 4. 匹配工作流和明确阻断

未来 factory-facing 计算至少需要：

```text
verified saved forecast
→ authorized BASE/entity scope
→ effective-dated BASE→FACTORY mapping
→ allocation method and completeness
→ same-basis planned intake or available processing capacity
→ metric/capacity policy version
→ server-side projected result and provenance
```

缺任何关系或容量 source 时，对应字段返回 `NOT_AVAILABLE`，不得用基地名、工厂名、Core Forecast 的 harvest capacity、用户输入或 S2 synthetic scenario 填补真实 authority。用户手填 S2 仍可作为明确标记的“假设情景”，但报告不可称为工厂能力已验证。

当前：

```text
FACTORY_ASSIGNMENT_AUTHORITY=NOT_AVAILABLE
FACTORY_PROCESSING_CAPACITY_AUTHORITY=NOT_AVAILABLE
BASE_TO_FACTORY_DAILY_ALLOCATION_AUTHORITY=NOT_AVAILABLE
FACTORY_PROCESSING_CAPACITY_BASIS=PENDING_OWNER_DECISION
```

## 5. 发布治理与审计

Owner 必须指定：业务主数据发布者、加工能力发布者、审批人/职责分离、修订与撤销责任人、应急调拨审批人。数据发布者不能由应用管理员或模型开发者自动兼任。

每一版本发布需有 immutable revision/hash、有效区间和 append-only 修订/撤销历史；更正不覆盖旧发布件。API 和报告在计算前确认 grants 与 source revision，返回时重新核验 revision/hash；发生变更时清理缓存、游标和 handoff，旧结果标记 stale/authority mismatch。

本轮没有选定实际系统、数据库、schema 或团队责任人。未来持久化/迁移、生产数据接入均须独立 Owner 授权；目前不建表、不连接数据源、不生成基地分配或工厂吞吐数字。
