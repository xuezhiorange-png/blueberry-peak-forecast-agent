# Source Cohort, Grain, Inclusion, and Revision Formalization

## 1. Task authority and exact base

```text
TASK_ID=S1-REMAINING-03
TASK=FORMALIZE_SOURCE_COHORT_GRAIN_INCLUSION_AND_REVISION_ARTIFACTS
TASK_CLASS=DOCS_ONLY_SOURCE_COHORT_GOVERNANCE_FORMALIZATION
BASE_MAIN_SHA=b618e962b45844b037232befa9c0e066551996e9
TASK_AUTHORIZED=true
DEPENDENCIES=S1-REMAINING-01,S1-REMAINING-02
ADVANCES_GATE_IDS=S1-SOURCE-COHORT,S1-CANONICAL-GRAIN,S1-INCLUSION-EXCLUSION,S1-REVISION-WINNER
```

This workpaper records a decision-candidate reconciliation and formalization
package for Task 3. It does not issue a final source-cohort manifest, accept a
source cohort, promote a canonical gate, or authorize a later task.

## 2. Source 002 immutable identity

The following identity is reused from current-main Git-tracked governed
evidence. No raw source object, row-level record, database, or external source
system was read or recomputed in this task.

| Field | Current governed value |
|---|---|
| source system | `扫码称重系统` |
| source dataset | `田间商品果每日采摘净重汇总` |
| source owner role | `农场数据负责人` |
| source version | `scan-weight-export:v0_3_s1:002` |
| snapshot reference | `snapshot:v0_3_s1:002` |
| source SHA-256 | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` |
| source byte count | `28668416` |
| declared source row count | `233171` |
| schema version | `observed-source-schema-v1` |
| schema SHA-256 | `919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867` |

The row and byte counts are declared source metadata. They are not an
accepted S2 row count, cleaned row count, materialized row count, or training
row count.

## 3. Current approved owner decisions consumed

The package consumes the current decision record
`source-authority-and-scope-business-owner-decision-v1` (SHA-256
`d5f8e46b7d634def4c5e3ba968e0310925c7b710701850f75728edb589184e69`). The
relevant decisions are:

- D-003 approves July Option A: retain the two raw rows dated 2025-07-22,
  exclude them from the canonical S1 season cohort, and do not silently assign
  a season.
- D-007 fixes immutable IDFL label-side revision/correction/void direction,
  replacement identity/hash requirements, and downstream propagation.
- D-008 fixes the S1/S2 ownership boundary and the aggregate scope evidence.
- D-009 fixes the S1 business exclusion boundary without forbidding later S2
  technical or data-quality exclusions.

These decisions are reused as current authority. The Task-3 mapping policy is
identified as a formalization candidate pending independent review; it is not
misrepresented as a new business-owner approval.

## 4. Q2C, physical, and grain authority consumed

The Q2C business-owner decision record is
`q2c-business-owner-decision-v1` (SHA-256
`85d2718caa32ed4207a4afa7f68680a5c7e71132b7c59620b2eb94916c2ac66f`). Its
business semantic equivalence is closed for the recorded business label, but
formal Q2C acceptance remains unissued.

The applicable canonical grain is:

```text
SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
GRAIN_COMPATIBILITY=PROVEN_STRUCTURALLY_COMPATIBLE
```

Structural compatibility is not source-cohort acceptance and is not a PASS
for `S1-CANONICAL-GRAIN`.

## 5. Mapping formalization

Task 3 issues the candidate identity:

```text
MAPPING_POLICY_VERSION=source-002-mapping-policy-v1
FORMAL_MAPPING_ACCEPTED=false
```

The candidate binds the exact source and schema identities, the aggregate
scope package SHA-256
`6f07bc878935060f57a2ef24318d6d3b17e27c7f096885f813ac80bed6ac9d10`, the
farm/subfarm/variety array hashes, mapped season `2025~2026`, the canonical
grain, the Asia/Shanghai business-date rule, and the July Option-A rule.

The governed scope evidence is:

```text
FARM_COUNT=84
SUBFARM_COUNT=192
VARIETY_COUNT=20
MAPPED_CANONICAL_GROUP_COUNT=529
FARMS_ARRAY_SHA256=2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381
SUBFARMS_ARRAY_SHA256=921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13
VARIETIES_ARRAY_SHA256=fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209
```

The full identity arrays are not committed to Git. This workpaper does not
invent or reconstruct them.

## 6. July Option-A disposition

```text
UNMAPPED_DATE=2025-07-22
UNMAPPED_ROW_COUNT=2
UNMAPPED_DATE_POLICY=RETAIN_RAW_EXCLUDE_CANONICAL_COHORT_NO_SILENT_ASSIGNMENT
RAW_ROWS_RETAINED=true
CANONICAL_S1_COHORT_INCLUDED=false
SILENT_SEASON_ASSIGNMENT=false
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
```

The two rows are retained as part of the immutable source object identity and
are not assigned to `2025~2026` by this package. The historical preparation
artifact's earlier `PENDING` text is preserved as provenance; this current
section uses the later approved D-003 authority.

## 7. Inclusion/exclusion disposition

```text
INCLUSION_POLICY_VERSION=source-002-inclusion-exclusion-boundary-v1
NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE=true
KNOWN_BUSINESS_EXCLUSIONS=NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE
S2_TECHNICAL_AND_DATA_QUALITY_EXCLUSIONS_REMAIN_SEPARATE=true
ALL_SOURCE_ROWS_VALID=false
```

“No known business exclusions” is a boundary statement, not a claim that all
source rows pass future technical or data-quality validation. S2 retains its
separate cleaning/exclusion authority.

## 8. Canonical grain disposition

Task 3 formally records the exact current contract grain and
`PLOT_SUPPORTED=false`. It does not add plot identity, farm/subfarm/variety
arrays, or a final clean rowset. The final rowset remains an S2-owned artifact.

## 9. IDFL revision/winner disposition

Source 002 uses `IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1` for the actual-label
side. Accordingly:

```text
LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
REVISION_WINNER_REQUIRED=false
IDFL_WINNER_MANIFEST_REQUIRED=false
IDFL_REVISION_GRAPH_REQUIRED=false
REVISION_POLICY_VERSION=source-002-idfl-revision-policy-v1
REVISION_WINNER_ALGORITHM=NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE
LATEST_ROW_FALLBACK_ALLOWED=false
LARGEST_REVISION_FALLBACK_ALLOWED=false
DATABASE_ROW_ORDER_AUTHORITY=false
POST_CONFIRMATION_ROW_LEVEL_REVISION_ALLOWED=false
POST_CONFIRMATION_ROW_LEVEL_VOID_ALLOWED=false
SOURCE_REPLACEMENT_REQUIRES_NEW_IDENTITY=true
SOURCE_REPLACEMENT_REQUIRES_NEW_SHA256=true
DOWNSTREAM_INVALIDATION_PROPAGATION_REQUIRED=true
SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIRED=true
SOURCE_OBJECT_BOUND_ROW_LINEAGE_IS_SOURCE_SYSTEM_IDENTITY=false
```

`NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE` is a deliberate label-mode disposition.
It does not remove forecast-input point-in-time or replay-mode revision
requirements for source classes used as forecast inputs.

## 10. Custody binding

The candidate reuses `source-002-custody-record-v1` with custody record hash
`99edffb9d076e9ab938a9021e1950a7d909dd7303e6d4677a46a5c1b8db8dde6`,
withdrawal policy `source-002-withdrawal-policy-v1`, and void propagation
policy `source-002-void-propagation-policy-v1`. The record remains issued for
independent review only:

```text
CUSTODY_RECORD_ACCEPTED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
```

## 11. Source-cohort schema readiness matrix

The matrix evaluates every top-level required field in
`docs/v0-3/s1/schemas/source-cohort-manifest.schema.json`. It uses only the
allowed status vocabulary. `KNOWN_PENDING_INDEPENDENT_REVIEW` means a truthful
value/reference exists but the formal artifact is not accepted; it does not
mean the final manifest is ready.

| Manifest field | Current value/evidence | Status | Owner task | Final-manifest blocker |
|---|---|---|---|---|
| `manifest_version` | candidate version `source-002-cohort-manifest-candidate-v1` | KNOWN_AND_BOUND | S1-REMAINING-03 | Candidate is not final artifact |
| `cohort_id` | `source-002-s1-cohort-v1` | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Candidate identity not accepted |
| `source_system` | 扫码称重系统 | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Source authority not accepted |
| `source_dataset` | 田间商品果每日采摘净重汇总 | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Source authority not accepted |
| `source_version` | scan-weight-export:v0_3_s1:002 | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Source authority not accepted |
| `schema_version` | observed-source-schema-v1 | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Schema attestation not final |
| `schema_hash` | 919e63c4...7276867 | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Schema attestation not final |
| `source_snapshot_reference` | snapshot:v0_3_s1:002 | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Source authority not accepted |
| `source_owner_role` | 农场数据负责人 | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Final attestation absent |
| `attestation_version` | null | MISSING_FINAL_ATTESTATION | S1-REMAINING-01 | Final source attestation absent |
| `attestation_effective_at` | null | MISSING_FINAL_ATTESTATION | S1-REMAINING-01 | Final source attestation absent |
| `effective_time` | D-001 applicability: 2024-08-01, open-ended, Asia/Shanghai | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-01 | Not bound to final attestation |
| `attestation_status` | UNSIGNED | MISSING_FINAL_ATTESTATION | S1-REMAINING-01 | Must be ATTESTED for final authority |
| `attestation_hash` | null | MISSING_FINAL_ATTESTATION | S1-REMAINING-01 | No final attestation hash |
| `coverage_scope` | Aggregate counts/hashes; arrays and date bounds unavailable | MISSING_GOVERNED_VALUE | S1-REMAINING-03 | Final scope object incomplete |
| `revision_policy` | source-002-idfl-revision-policy-v1 candidate | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Final attestation binding absent |
| `withdrawal_and_void_policy` | Versioned policy references exist | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Final attestation binding absent |
| `known_exclusions` | No known S1 business exclusions | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Cohort acceptance absent |
| `mapping_policy_version` | source-002-mapping-policy-v1 candidate | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Mapping acceptance absent |
| `visibility_policy_version` | null | OWNED_BY_S1_REMAINING_04 | S1-REMAINING-04 | Later visibility correction/formalization |
| `inclusion_policy_version` | source-002-inclusion-exclusion-boundary-v1 | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Inclusion acceptance absent |
| `revision_policy_version` | source-002-idfl-revision-policy-v1 | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Revision disposition review absent |
| `split_policy_version` | null | OWNED_BY_S1_REMAINING_05 | S1-REMAINING-05 | Later split policy package |
| `grain` | SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Canonical gate remains blocked |
| `plot_supported` | false | KNOWN_AND_BOUND | S1-REMAINING-03 | None at candidate layer |
| `source_object_identity_hashes` | Source/schema/mapping references and hashes | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Final manifest not accepted |
| `declared_source_row_count` | 233171 | KNOWN_AND_BOUND | S1-REMAINING-03 | Not S2 accepted row count |
| `declared_source_byte_count` | 28668416 | KNOWN_AND_BOUND | S1-REMAINING-03 | Final manifest absent |
| `custody_record` | source-002-custody-record-v1 / hash 99ed... | KNOWN_PENDING_INDEPENDENT_REVIEW | S1-REMAINING-03 | Custody acceptance absent |
| `manifest_hash` | null | MISSING_FINAL_ATTESTATION | S1-REMAINING-03 | Cannot hash incomplete final manifest |
| `S1_FREEZES_SOURCE_COHORT_IDENTITY` | true | KNOWN_AND_BOUND | S1-REMAINING-03 | None at candidate layer |
| `S1_FREEZES_FINAL_CLEAN_ROWSET` | false | KNOWN_AND_BOUND | S1-REMAINING-03 | None at candidate layer |
| `S2_OWNS_FINAL_MATERIALIZED_ROWSET` | true | KNOWN_AND_BOUND | S1-REMAINING-03 | S2 remains unauthorized |
| `SOURCE_ROW_COUNT_IS_DECLARED_SOURCE_METADATA` | true | KNOWN_AND_BOUND | S1-REMAINING-03 | None at candidate layer |
| `SOURCE_ROW_COUNT_IS_NOT_S2_ACCEPTED_ROW_COUNT` | true | KNOWN_AND_BOUND | S1-REMAINING-03 | None at candidate layer |
| `SOURCE_ROW_COUNT_DOES_NOT_FREEZE_FINAL_ROWSET` | true | KNOWN_AND_BOUND | S1-REMAINING-03 | None at candidate layer |

## 12. Explicit later-task-owned fields

The following fields are not invented or pulled forward:

```text
visibility_policy_version -> S1-REMAINING-04
split_policy_version -> S1-REMAINING-05
```

Their presence in the final schema does not authorize either later task. The
final manifest also remains blocked by the missing final attestation, concrete
scope arrays/date bounds, and final manifest hash.

## 13. Canonical gate non-promotion

The authoritative acceptance record and current-main canonical reconciliation
are unchanged. Runtime status remains:

```text
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
S1-SOURCE-COHORT=BLOCKED
S1-CANONICAL-GRAIN=BLOCKED
S1-INCLUSION-EXCLUSION=BLOCKED
S1-REVISION-WINNER=BLOCKED
CANONICAL_GATE_STATUS_CHANGED=false
AUTHORITATIVE_ACCEPTANCE_RECORD_CHANGED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
```

Candidate formalization is evidence preparation and is not canonical PASS.

## 14. Data-safety boundary

```text
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
TEST_DATA_ACCESS=false
EXTERNAL_HOLDOUT_ACCESS=false
SOURCE_HASH_RECOMPUTED_IN_THIS_TASK=false
SOURCE_COUNTS_RECOMPUTED_IN_THIS_TASK=false
IDENTITY_ARRAYS_RECOMPUTED_IN_THIS_TASK=false
```

Only Git-tracked aggregate evidence and policy/contract artifacts were used.
No farm, subfarm, or variety identity array was invented.

## 15. Validation

The package validation will confirm JSON syntax, six unique CGR dispositions,
source identity parity, scope count/hash parity, July Option-A parity,
canonical grain and plot parity, inclusion/exclusion parity, IDFL disposition
parity, candidate/final-manifest separation, and Markdown/JSON consistency.
The decision-record SHA uses compact UTF-8 JSON with recursively sorted keys,
excluding only `decision_record_sha256`.

```text
TASK3_DECISION_RECORD_SHA256=1d737e1a6e2ce3cfaebf1d3449af86a51572d58333cdc1cdfe397a570084f955
SOURCE_COHORT_MANIFEST_CANDIDATE_REFERENCE=source-002-cohort-manifest-candidate-v1
FINAL_SOURCE_COHORT_MANIFEST_CREATED=false
FINAL_SOURCE_COHORT_MANIFEST_SCHEMA_READY=false
```

## 16. Stop condition

After the four authorized files are validated, committed, pushed, and covered
by a successful exact-head Draft PR CI run, this task stops. The next action
requires a separate independent review:

```text
S1_REMAINING_03_CANONICAL_CLOSURE=BLOCKED
S1_REMAINING_03_COMPLETE=false
NEXT_RECOMMENDED_ACTION=RUN_EXACT_HEAD_INDEPENDENT_REVIEW_OF_S1_REMAINING_03_FORMALIZATION
NO_STEP_IMPLIES_THE_NEXT=true
```
