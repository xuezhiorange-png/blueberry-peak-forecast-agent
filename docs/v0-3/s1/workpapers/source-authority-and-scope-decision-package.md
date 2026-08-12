# V0.3-S1 Source Authority and Scope Decision Package

## 1. Scope and authority

```text
WORKPAPER_ID=V0_3_S1_SOURCE_AUTHORITY_AND_SCOPE_DECISION_PACKAGE
TASK=V0_3_S1_SOURCE_AUTHORITY_AND_SCOPE_DECISION_PACKAGE
TASK_ID=S1-REMAINING-01
TASK_CLASS=DOCS_ONLY_BUSINESS_GOVERNANCE_DECISION_PREPARATION
BASE_MAIN_SHA=e2611e6625c00803c36d95c19303ebb9bf999db4
WORKPAPER_STATUS=PREPARED_FOR_BUSINESS_OWNER_DECISION
RECOMMENDED_DOES_NOT_EQUAL_APPROVED=true
```

This package prepares the source-authority and Source 002 scope decisions that
remain after the current-main evidence reconciliation. It consumes only
Git-tracked aggregate evidence, existing hashes, manifests, policy identities,
and business statements. It does not reopen the Source 002 raw export, read
row-level business data, issue an attestation, freeze a cohort, or accept any
S1 gate.

The authority precedence remains the current S1 package and its higher-
precedence forecast-quality contracts. The `business-source-attestation`
schema requires both source-identity fields and physical/Q2C fields. Therefore
this package cannot issue a final schema-valid attestation; the physical,
unit, and time formalization dependency is reserved for
`S1-REMAINING-02`.

## 2. Current canonical runtime state

```text
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
S1-SOURCE-AUTHORITY=BLOCKED
S1-SOURCE-COHORT=BLOCKED
S1-INCLUSION-EXCLUSION=BLOCKED
S1-MISSING-CORRECTION-CANCELLATION=BLOCKED
CANONICAL_GATE_STATUS_CHANGED=false
AUTHORITATIVE_ACCEPTANCE_RECORD_CHANGED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

The existing `s1-acceptance-record.json` remains untouched. This workpaper's
decision status is separate from canonical runtime gate status: a recommended
candidate or an owner decision would still require formal artifacts and
independent review before any canonical gate could change.

## 3. Current-main evidence sources reviewed

The package consumed the following current-main artifacts:

- `docs/v0-3/s1/source-authority-and-cohort-manifest.md`
- `docs/v0-3/s1/schemas/business-source-attestation.schema.json`
- `docs/v0-3/s1/schemas/source-cohort-manifest.schema.json`
- `docs/v0-3/s1/evidence/s1-acceptance-record.json`
- `docs/v0-3/s1/evidence/evidence-package-manifest.json`
- `docs/v0-3/s1/evidence/source-authority-evidence-status.md`
- `docs/v0-3/s1/evidence/source-cohort-evidence-status.md`
- `docs/v0-3/s1/evidence/data-custody-evidence-status.md`
- `docs/v0-3/s1/evidence/q2c-physical-alignment-evidence-status.md`
- `docs/v0-3/s1/evidence/source-002-mapping-and-scope-identity-manifest.json`
- `docs/v0-3/s1/evidence/source-002-inclusion-exclusion-manifest.json`
- `docs/v0-3/s1/evidence/source-002-custody-record.json`
- `docs/v0-3/s1/evidence/source-002-governed-snapshot-evidence.md`
- `docs/v0-3/s1/evidence/source-002-completeness-and-custody-business-evidence.md`
- `docs/v0-3/s1/workpapers/q2c-target-decision-draft.md`
- `docs/v0-3/s1/workpapers/source-measurement-and-finalization-rules-draft.md`
- `docs/v0-3/s1/workpapers/season-calendar-rule-draft.md`
- `docs/v0-3/s1/workpapers/actual-harvest-immutable-daily-label-compatibility-decision.md`
- `docs/v0-3/s1/workpapers/immutable-daily-final-label-contract-acceptance-decision.md`
- `docs/v0-3/s1/evidence/canonical-acceptance-gate-current-main-reconciliation.json`

The evidence shows a substantial fact layer, but it does not supply the
source-owner authority, applicability decision, complete-through authority,
or accepted cohort identity required by the S1 contracts.

## 4. Source 002 facts already available

The following identities are reused exactly from existing Git-tracked evidence;
they are not recomputed in this task:

```text
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_OWNER_ROLE=农场数据负责人
SOURCE_EFFECTIVE_SEASON=2024~2025产季起
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_BYTE_COUNT=28668416
SOURCE_ROW_COUNT=233171
SCHEMA_VERSION=observed-source-schema-v1
SCHEMA_SHA256=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
SOURCE_CLASS=ACTUAL_HARVEST_LABEL
LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
LABEL_MODE_VERSION=IDFL_V1
```

The current V0.3 recorded-label semantics are also already recorded:

```text
V0_3_RECORDED_LABEL_PROFILE=RECORDED_BUSINESS_LABEL
V0_3_ACTUAL_LABEL_MEASUREMENT_EVENT=VALID_FIELD_SCAN_WEIGH_RECORD
V0_3_ACTUAL_LABEL_QUANTITY_BASIS=RECORDED_MARKETABLE_NET_WEIGHT
V0_3_ACTUAL_LABEL_UNIT=KG
RECORDED_NET_WEIGHT_IS_BUSINESS_TRUTH=true
FARM_TIMEZONE=Asia/Shanghai
LOCAL_DAY_BOUNDARY=LOCAL_CALENDAR_DAY_00_00_ASIA_SHANGHAI
HARVEST_BUSINESS_DATE_RULE=扫码称重记录时间转换为 Asia/Shanghai 后直接取自然日日期
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
```

The aggregate scope preparation binds the following metadata without placing
the identity arrays in Git:

```text
MAPPED_SEASON_IDENTITIES=[2025~2026]
FARM_COUNT=84
SUBFARM_COUNT=192
VARIETY_COUNT=20
MAPPED_CANONICAL_GROUP_COUNT=529
FARMS_ARRAY_SHA256=2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381
SUBFARMS_ARRAY_SHA256=921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13
VARIETIES_ARRAY_SHA256=fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209
COVERAGE_SCOPE_IDENTITY_PACKAGE_SHA256=6f07bc878935060f57a2ef24318d6d3b17e27c7f096885f813ac80bed6ac9d10
IDENTITY_MODE=PREPARATION_ONLY_SOURCE_DERIVED
FORMAL_MAPPING_ACCEPTED=false
```

The source calendar is August 1 through June 30, inclusive. July is not
automatically assigned. Existing evidence records two retained, unmapped
rows on `2025-07-22`; this package does not silently assign them.

## 5. Governance facts and policy identities already present

The issued-for-review Source 002 custody record supplies reusable policy
identities and non-sensitive hashes:

```text
CUSTODY_POLICY_VERSION=source-002-custody-policy-v1
RETENTION_POLICY_VERSION=source-002-retention-policy-v1
WITHDRAWAL_POLICY_VERSION=source-002-withdrawal-policy-v1
VOID_PROPAGATION_POLICY_VERSION=source-002-void-propagation-policy-v1
REPLACEMENT_SOURCE_REQUIRES_NEW_HASH=true
REPLACEMENT_SOURCE_REQUIRES_NEW_IDENTITY=true
RAW_SOURCE_MUTATION_ALLOWED=false
WITHDRAWAL_PROPAGATES_TO_SOURCE_COHORT_FUTURE_SPLITS_FUTURE_SNAPSHOTS_AND_ACCEPTANCE=true
CUSTODY_RECORD_ACCEPTED=false
```

These are supporting governance artifacts issued for review, not an accepted
source authority or accepted custody gate. They do not authorize a new source
read. The Source 002 business evidence also records that completeness
declaration authority and formal completeness exception handling are not yet
formalized.

## 6. Nine-decision candidate matrix

| ID | Decision | Decision status | Known fact | Candidate | Recommended option | Requires owner approval | Effect if approved | Still blocked if not approved |
|---|---|---|---|---|---|---|---|---|
| D-001 | SOURCE_CLASS_APPLICABILITY | PENDING_BUSINESS_OWNER_DECISION | `SOURCE_EFFECTIVE_SEASON=2024~2025产季起`; season calendar is 08-01 through 06-30 in Asia/Shanghai | Actual-harvest source class effective from `2024-08-01T00:00:00+08:00`, open-ended | Source class applicable from 2024-08-01 Asia/Shanghai, open-ended | true | Binds applicability period only | Source authority and scope remain blocked |
| D-002 | FIXED_SOURCE_OBJECT_IDENTITY | PENDING_BUSINESS_OWNER_DECISION | Version, opaque snapshot reference, source/schema hashes, row/byte counts and package references exist | Accept fixed Source 002 identity for S1 governance | Accept fixed Source 002 identity for S1 governance | true | Future authority artifacts bind one immutable object | Source authority and cohort identity remain blocked |
| D-003 | SOURCE_UNMAPPED_JULY_DATE_POLICY | PENDING_BUSINESS_OWNER_DECISION | Two retained rows on 2025-07-22; July auto assignment false; policy pending | Retain raw rows, exclude from canonical S1 season cohort, no silent reassignment | Option A: retain raw, exclude canonical cohort until exception policy | true | Makes July disposition explicit without rewriting source | Cohort and inclusion policy remain blocked |
| D-004 | SOURCE_COMPLETENESS_AUTHORITY_MODEL | PENDING_BUSINESS_OWNER_DECISION | Complete-through date not issued; Q2 is only 产季结束核对; observed max date is not a watermark | Fixed snapshot without completeness watermark until exact owner date | Fixed snapshot without issued complete-through watermark | true | Prevents a full-season completeness claim | Completeness and source authority remain blocked |
| D-005 | COMPLETENESS_DECLARATION_OWNER_ROLE | PENDING_BUSINESS_OWNER_DECISION | Source owner role is 农场数据负责人; declaration role is not formalized | Candidate declaration owner role is 农场数据负责人, subject to explicit confirmation | Confirm whether 农场数据负责人 may declare completeness | true | Names a role that may issue completeness authority | Completeness authority remains blocked |
| D-006 | SOURCE_MISSING_DAY_SEMANTICS | ALREADY_FIXED_BY_EXISTING_AUTHORITY | Contract and workpapers freeze UNKNOWN_NOT_ZERO; numeric imputation is false | Keep UNKNOWN_NOT_ZERO | Retain UNKNOWN_NOT_ZERO and no numeric imputation | false | Existing fail-closed rule remains | Formal completeness/lifecycle evidence remains blocked |
| D-007 | REVISION_CORRECTION_VOID_AUTHORITY | PENDING_BUSINESS_OWNER_DECISION | Immediate final confirmation; no business correction/void after confirmation; formal source revision policy absent | Disable row-level post-confirmation revision/void; replacement gets new identity/hash and propagates | IDFL revision/void disabled; source replacement creates new identity/hash with propagation | true | Supplies a source-specific lifecycle disposition | Revision and missing/correction/cancellation gates remain blocked |
| D-008 | SOURCE_002_COVERAGE_SCOPE | PENDING_BUSINESS_OWNER_DECISION | Aggregate scope preparation exists; formal mapping false; arrays not stored in Git | Freeze Source 002 cohort identity only; leave S2 final clean rowset unfrozen | Freeze governed cohort identity, not final clean rowset | true | Defines S1 source universe without granting S2 | Cohort, grain and inclusion remain blocked |
| D-009 | INCLUSION_EXCLUSION_BOUNDARY | PENDING_BUSINESS_OWNER_DECISION | No known business exclusions at source scope; S2 technical/data-quality exclusions remain separate | Accept no known business exclusions and preserve separate S2 exclusions | Accept source-scope business boundary; keep S2 exclusions separate | true | Freezes business inclusion semantics without mutating raw source | Inclusion and cohort formalization remain blocked |

### 6.1 Decision-by-decision authority notes

#### D-001 — Source class applicability

The recorded `2024~2025产季起` statement and the confirmed cross-year season
calendar support a candidate effective time of
`2024-08-01T00:00:00+08:00`. They do not constitute an issued source-class
applicability authority. A source/business owner must confirm the period and
its open-ended interpretation.

#### D-002 — Fixed Source 002 identity

The object identity is already present in aggregate evidence. The requested
decision is whether the business owner accepts those exact identifiers as the
fixed S1 governance object. It is not permission to recalculate the digest or
to read the raw export.

#### D-003 — July unmapped date

The recommended Option A retains the two July rows in the immutable source
object but excludes them from the canonical S1 season cohort until a separate
exception rule is approved. Options B and C remain visible so an owner can
choose explicitly. No option is approved by this package.

#### D-004 — Completeness model

The current maximum observed business date (`2026-04-16`) is not a completeness
watermark. The reported process `产季结束核对` is a business fact, not a
formal declaration event or policy. The recommended fixed-snapshot mode
therefore avoids claiming complete coverage until an exact owner-issued date
exists.

#### D-005 — Completeness declaration role

`SOURCE_OWNER_ROLE=农场数据负责人` is not automatically a completeness
declaration authority. The candidate role is shown only for explicit owner
confirmation; no role is formalized here.

#### D-006 — Missing-day semantics

`UNKNOWN_NOT_ZERO` is already fixed by the current contract and repeated in
the current workpapers. This package does not reopen it, and no missing-day
observation is converted to a zero.

#### D-007 — Revision, correction, and void authority

The recommendation preserves the immutable daily final-label boundary and the
existing Source 002 withdrawal/void-propagation policy identities. The
candidate `source-002-idfl-revision-policy-v1` is only a proposed identity;
it is not accepted or issued by this package.

#### D-008 — Coverage and cohort scope

The reviewed counts and array/package hashes are preparation evidence. The
recommendation freezes only the governed source-cohort identity; it does not
freeze a final cleaned rowset, create a schema-valid cohort manifest, or
authorize S2.

#### D-009 — Business versus S2 exclusions

`NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE` does not mean that future S2
technical or data-quality exclusions are impossible. It means those later
exclusions must remain a separate, versioned layer and must not mutate the
immutable raw source object.

## 7. Decision readiness and unresolved owner inputs

```text
DECISION_COUNT=9
UNIQUE_DECISION_ID_COUNT=9
DECISIONS_ALREADY_FIXED_BY_EXISTING_AUTHORITY=1
DECISIONS_REQUIRING_BUSINESS_OWNER_APPROVAL=8
UNRESOLVED_DECISION_IDS=D-001,D-002,D-003,D-004,D-005,D-007,D-008,D-009
BUSINESS_OWNER_DECISION_REQUIRED=true
```

The eight unresolved decisions are not missing facts that this repository can
derive safely. They are explicit business/source/governance choices. In
particular, the package does not turn silence about exclusions into an empty
approved list, does not turn an observed maximum date into a watermark, and
does not equate a source-owner role with completeness authority without
confirmation.

## 8. Formal artifact and acceptance boundary

The final attestation schema requires source identity plus physical/Q2C fields
such as `physical_event`, `quantity_basis`, `measurement_method`, time basis,
missing/correction/void rules, grain, and coverage. This package intentionally
does not create `business-source-attestation.json` or any equivalent
`ATTESTED` artifact.

```text
FINAL_BUSINESS_SOURCE_ATTESTATION_CREATED=false
FINAL_BUSINESS_SOURCE_ATTESTATION_ISSUANCE_ALLOWED=false
FORMAL_SOURCE_COHORT_MANIFEST_CREATED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
CANONICAL_GATE_STATUS_CHANGED=false
AUTHORITATIVE_ACCEPTANCE_RECORD_CHANGED=false
```

The current S1 runtime remains blocked. Recommended candidates are not
canonical PASS states and do not provide S1 acceptance or S2 authorization.

## 9. Data safety and repository boundary

```text
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
TEST_DATA_ACCESS=false
EXTERNAL_HOLDOUT_ACCESS=false
SOURCE_HASH_RECOMPUTED_IN_THIS_TASK=false
SOURCE_COUNTS_RECOMPUTED_IN_THIS_TASK=false
SOURCE_DATE_DISTRIBUTION_RECOMPUTED_IN_THIS_TASK=false
PRIVATE_URL_OR_STORAGE_LOCATOR_RECORDED=false
CREDENTIAL_RECORDED=false
PERSONAL_IDENTITY_RECORDED=false
```

Only existing Git-tracked aggregate evidence and non-sensitive identity/policy
references were consumed. No raw source, real row, server address, storage
locator, credential, token, personal name, or row-level artifact was created.

## 10. Recommended next action

The next action is not independent S1 acceptance and not Task 2 execution:

```text
NEXT_RECOMMENDED_ACTION=OBTAIN_BUSINESS_OWNER_DECISIONS_FOR_SOURCE_AUTHORITY_AND_SCOPE_PACKAGE
NO_STEP_IMPLIES_THE_NEXT=true
```

After the owner decisions are supplied, a separately authorized formalization
task may prepare the source attestation/cohort artifacts. The Q2C physical,
unit, and time formalization remains a distinct dependency, and S2 remains
unauthorized until the complete S1 acceptance process closes.
