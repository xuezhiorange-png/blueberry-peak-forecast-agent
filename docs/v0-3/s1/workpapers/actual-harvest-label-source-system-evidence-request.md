# Actual-Harvest Label Source-System Evidence Request

## Request identity and boundary

```text
REQUEST_ID=V0_3_S1_ACTUAL_HARVEST_LABEL_SOURCE_SYSTEM_LIFECYCLE_EVIDENCE
SOURCE_CLASS=ACTUAL_HARVEST_LABEL
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
REQUEST_STATUS=MINIMUM_EXTERNAL_TECHNICAL_EVIDENCE_REQUIRED
REAL_SOURCE_EXPORT_REQUESTED=false
REAL_BUSINESS_ROWS_REQUESTED=false
REAL_RECORD_IDS_REQUESTED=false
REAL_TIMESTAMPS_REQUESTED=false
```

This request does not repeat the already confirmed business facts about the
physical event, quantity, immediate confirmation, or post-confirmation
business prohibitions. It asks only for source-system capability and field
semantics needed to bind the existing Q2A/I7 contract.

The acceptable response is a field dictionary, system capability statement,
redacted interface/export specification, or equivalent owner-approved
technical evidence. It must not include row values, personal data, credentials,
private URLs, or plaintext storage paths.

## Minimum questions for the source-system owner or technical custodian

### 1. Stable source record identity

```text
REQUEST_ITEM=SOURCE_RECORD_IDENTITY
QUESTION=扫码称重系统是否为每条实际采摘称重记录保存唯一且长期稳定的记录 ID？如果有，该字段的正式名称、是否跨导出保持不变、以及是否能与同一业务记录的后续修订关联？
WHY_REQUIRED=Q2A/I7 需要稳定 source logical identity；Source 002 的 observed seven-field export 没有该字段。
ACCEPTABLE_EVIDENCE=字段字典或技术规格中的字段定义和稳定性说明，不需要提供任何真实 ID。
```

### 2. Source-recorded time

```text
REQUEST_ITEM=SOURCE_RECORDED_AT
QUESTION=系统是否保存“该称重记录首次在扫码称重系统中生成/记录的时间”？正式字段名、时区、精度和生成时点分别是什么？该时间是否在历史导出中保持不可被后续导出时间覆盖？
WHY_REQUIRED=AS_OF_EVALUATION 只能使用可信 source_recorded_at <= label_observation_cutoff_at，不能用 harvest_business_date 或 import time 替代。
ACCEPTABLE_EVIDENCE=字段定义、时区/精度规则和生成时点说明，不需要提供真实时间值。
```

### 3. Source availability time

```text
REQUEST_ITEM=SOURCE_AVAILABLE_AT
QUESTION=系统是否保存该记录首次可被下游业务或导出流程看到的时间？如果有，正式字段名和“可见”的定义是什么；如果没有，source owner 是否批准该 source class 使用有版本的 policy-null 规则？
WHY_REQUIRED=S1 visibility contract 要求 source_available_at 或明确的 policy-null authority；空值不能自动通过。
ACCEPTABLE_EVIDENCE=字段定义或 source-class policy decision，不需要真实记录。
```

### 4. Post-confirmation mutation capability

```text
REQUEST_ITEM=POST_CONFIRMATION_MUTATION_CAPABILITY
QUESTION=扫码称重完成后，普通用户、管理员和后台维护流程是否都不能修改原称重记录的业务值？如果存在任何例外流程，请说明触发条件以及是否保留旧值和操作时间。
WHY_REQUIRED=已确认的 business rule 需要与 source-system technical capability 分离；该回答用于判断 candidate immutability rule 是否可正式绑定。
ACCEPTABLE_EVIDENCE=权限/流程说明或系统能力声明，不需要真实操作记录。
```

### 5. Correction representation and lineage

```text
REQUEST_ITEM=CORRECTION_LINEAGE
QUESTION=如果历史称重记录需要纠正，系统是修改原记录，还是新增一条关联原记录的新记录？如果新增，是否保存 predecessor ID、revision number、correction time 和完整 lineage？
WHY_REQUIRED=Q2A/I7 要求 correction 是可见的 lineage event，不能依赖 latest-row 或 database order。
ACCEPTABLE_EVIDENCE=修订模型/字段字典/流程规范，不需要真实记录或真实修订值。
```

### 6. Void/cancellation semantics

```text
REQUEST_ITEM=VOID_AND_CANCELLATION
QUESTION=系统是否存在对单条称重记录的作废或取消状态？如果存在，状态值、发生时间、原记录保留规则和后续记录关系分别是什么？如果不存在，请 source owner 明确批准该 source class 的 policy-null 规则。
WHY_REQUIRED=VOID 是 lineage terminal、不是 winner；record-level void 也不能替代 source-object withdrawal/custody policy。
ACCEPTABLE_EVIDENCE=状态字典、事件模型或明确 policy-null decision，不需要真实记录。
```

### 7. Finalization semantics

```text
REQUEST_ITEM=FINALIZATION
QUESTION=扫码称重系统是否存在独立于“扫码称重完成”的最终确认、冻结、结算、封账或其他不可再产生 successor 的 finalization event？如果存在，请说明正式状态/字段名称、finalized time 字段名称、事件发生条件、时间语义，以及该事件后是否不可再产生 successor；不需要提供任何真实时间值。如果不存在，请 source owner 或 technical custodian 明确确认 SOURCE_CLASS_HAS_INDEPENDENT_FINALIZATION_EVENT=false，并据此记录 ACTUAL_LABEL_FINAL_ADJUDICATED_SUPPORTED_BY_SOURCE_CLASS=false 和 ACTUAL_LABEL_FINAL_ADJUDICATED_ELIGIBILITY=BLOCKED。
WHY_REQUIRED=Q2A/I7 对 FINAL_ADJUDICATED 明确要求 record_status=FINALIZED、finalized_at IS NOT NULL 且 finalized_at <= snapshot_executed_at；业务上的 immediate confirmation 不能自动替代技术 finalization evidence，缺少 finalization event 或可信 finalized_at 不能通过 policy-null 满足 FINAL_ADJUDICATED。
ACCEPTABLE_EVIDENCE=状态机、字段字典或 source-class capability statement；如果不存在独立 finalization event，应提供明确的 false capability confirmation，不得声明 finalized_at 的 policy-null 已被 FINAL_ADJUDICATED 接受。
```

### 8. Late-entry semantics

```text
REQUEST_ITEM=LATE_ENTRY
QUESTION=如果采摘发生日期早于记录首次进入扫码称重系统的日期，系统是否允许补录？若允许，如何区分 harvest_business_date、source_recorded_at 和 source_available_at，并如何保留补录事实？
WHY_REQUIRED=BUSINESS_REPORTED_LATE_ENTRY_SCENARIO=NOT_APPLICABLE 不是技术能力证明；late entry 直接影响 AS_OF visibility。
ACCEPTABLE_EVIDENCE=补录规则、字段定义和可重建性说明，不需要真实补录样本。
```

### 9. Export preservation and schema identity

```text
REQUEST_ITEM=EXPORT_LIFECYCLE_FIELD_PRESERVATION
QUESTION=受控导出是否能够在不改变原始业务事实的前提下携带上述 source identity、source times、status、revision and lineage fields？导出 schema 是否有稳定版本或可复现的 schema identity？
WHY_REQUIRED=Source 002 的七个 observed fields 足以支持当前 canonical-grain preparation，但不足以支持 point-in-time authority；后续 source evidence 必须能绑定生命周期字段语义。
ACCEPTABLE_EVIDENCE=导出字段字典、schema version policy 和 mapping specification，不需要交付真实导出文件。
```

## Evidence acceptance boundary

回答这些问题不会自动产生正式 attestation 或 cohort manifest。后续仍
需要：

```text
FORMAL_SOURCE_ATTESTATION_CREATED=false
FORMAL_SOURCE_COHORT_MANIFEST_CREATED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
V0_3_S1_ACCEPTED=false
S1_VISIBILITY_GATE_CLOSED=false
V0_3_S2_AUTHORIZED=false
```

Record-level correction/void evidence must remain separate from whole-source
withdrawal and custody evidence. A replacement or withdrawn source object
requires a new governed identity and new hashes; no prior governance record is
rewritten in place.
