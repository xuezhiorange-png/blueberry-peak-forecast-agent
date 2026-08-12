# V0.3-S1 Q2C Physical / Unit / Time Formalization

## 1. Scope and authority

```text
WORKPAPER_ID=V0_3_S1_Q2C_PHYSICAL_UNIT_TIME_FORMALIZATION
TASK_ID=S1-REMAINING-02
TASK=Q2C_PHYSICAL_UNIT_TIME_FORMALIZATION
TASK_CLASS=DOCS_ONLY_BUSINESS_DECISION_AND_EVIDENCE_FORMALIZATION_PREPARATION
BASE_MAIN_SHA=0746e99a359f54e5916da482a750b723eca600f3
DEPENDENCIES=S1-REMAINING-01
ADVANCES_GATE_IDS=S1-Q2C-TARGET,S1-PHYSICAL-MEANING,S1-UNIT-AND-TIME-BASIS
WORKPAPER_STATUS=BUSINESS_OWNER_Q2C_DECISIONS_FORMALIZED_PENDING_INDEPENDENT_REVIEW
```

This workpaper records the four explicitly authorized business-owner Q2C
decisions and preserves the two repository-contract conclusions. It does not
issue a final governed Q2C outcome, create a final attestation, change a
canonical gate row, accept Source 002, or authorize S1/S2.

Current-main contracts and evidence take precedence over historical PR prose.
The Source 002 identity and the nine approved source-authority/scope decisions
from `source-authority-and-scope-business-owner-decision-v1` are reused without opening the source export or reading
row-level business data.

## 2. Current governance and formalization boundary

```text
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTED=false
CURRENT_V0_3_S2_AUTHORIZED=false
CURRENT_V0_3_S2_STARTED=false
CANONICAL_GATE_STATUS_CHANGED=false
AUTHORITATIVE_ACCEPTANCE_RECORD_CHANGED=false
Q2C_DECISION_STATUS=NOT_ISSUED
BUSINESS_SEMANTIC_Q2C_CANDIDATE_OUTCOME=PROVEN_EXACT
BUSINESS_SEMANTIC_EQUIVALENCE_CLOSED=true
FORMAL_Q2C_DECISION_STATUS=NOT_ISSUED
CURRENT_Q2C_OUTCOME=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
POSITIVE_OUTCOME_ALLOWED=false
POSITIVE_Q2C_OUTCOME_ISSUED=false
FINAL_BUSINESS_SOURCE_ATTESTATION_CREATED=false
FINAL_Q2C_DECISION_RECORD_CREATED=false
```

The actual-label facts and the six-dimensional business semantic comparison are
now recorded. The business-owner record authorizes exact equivalence for
Q2C-D001 through Q2C-D004; D005 and D006 remain repository-contract conclusions.
This semantic candidate outcome is not a final governed Q2C acceptance because
the schema-valid business-source attestation has not been issued.

## 3. Existing authority consumed

| Artifact | Role in this package |
|---|---|
| `docs/v0-3/s1/evidence/source-authority-and-scope-business-owner-decision-record.json` | Reusable Source 002 identity and D-001..D-009 decision authority; issued for independent review, not source acceptance |
| `docs/v0-3/s1/target-decision-and-quantity-contract.md` | Current candidate and no-silent-substitution rules |
| `docs/forecast-quality/q2c-physical-target-equivalence-contract.md` | Six-dimensional equivalence and positive-outcome gate |
| `docs/forecast-quality/q2c-physical-target-evidence-audit.md` | Current evidence assessment: actual/forecast comparison remains unresolved |
| `docs/v0-3/s1/evidence/q2c-physical-alignment-evidence-status.md` | Fact layer reconciled; Q2C remains blocked/not issued |
| `docs/v0-3/s1/workpapers/q2c-target-decision-draft.md` | Recorded-label facts and candidate target context |
| `docs/v0-3/s1/workpapers/business-source-attestation-draft.md` | Existing schema-aligned preparation and missing fields |
| `docs/v0-3/s1/workpapers/source-measurement-and-finalization-rules-draft.md` | Measurement, time, missingness and lifecycle facts |
| `docs/v0-3/s1/workpapers/recorded-harvest-label-boundary-correction.md` | V0.3 recorded-label boundary correction |
| `docs/v0-3/s1/evidence/canonical-acceptance-gate-current-main-reconciliation.json` | Package dependency and current 17-gate runtime boundary |
| `docs/v0-3/s1/schemas/business-source-attestation.schema.json` | Current schema required fields (36 top-level required entries) |

## 4. Reconciled actual-label authority

| Field | Current authority |
|---|---|
| Business event | `HARVEST` |
| Measurement event | `VALID_FIELD_SCAN_WEIGH_RECORD` |
| Measurement boundary | `RECORDED_VALID_FIELD_SCAN_WEIGH` |
| Quantity | `RECORDED_MARKETABLE_NET_WEIGHT` |
| Unit | `KG` |
| Source of truth | `GOVERNED_SCAN_WEIGHT_RECORD` |
| Timezone | `Asia/Shanghai` |
| Local day | `LOCAL_CALENDAR_DAY_00_00_ASIA_SHANGHAI` |
| Canonical grain | `SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE` |
| Plot support | `false` |
| Pre-measurement reconstruction | `false` / not required for eligibility |

The pre-weigh transport/storage/post-harvest, tare-method, and scale-metrology
fields remain optional provenance/metrology evidence for this recorded-label
profile. Their absence does not block label eligibility and does not supply a
forecast-side transformation.

## 5. Forecast candidate boundary

```text
TASK9_HARVESTED_BASIS=MARKETABLE
FORECAST_TARGET_CANDIDATE=model_harvested_marketable_quantity_kg
Q2C_V1_FORECAST_TARGET=PROVEN_EXACT_BUSINESS_SEMANTIC_CANDIDATE
PHYSICAL_EQUIVALENCE_ASSUMED=false
BUSINESS_SEMANTIC_EQUIVALENCE_CLOSED=true
FORECAST_SIDE_TARGET_BINDING_CHANGED=false
SILENT_TARGET_SUBSTITUTION_ALLOWED=false
EFFECTIVE_MARKETABLE_TARGET_NOT_SELECTED=true
TRANSFORMATION_AUTHORITY=NOT_ISSUED
```

The candidate is retained exactly as named by the current contract. The
post-pick `effective_marketable_quantity_kg`, maturity/harvestable quantities,
arrival/receipt quantities, and `FactReceiptDaily.weight_kg` are not substitute
targets.

## 6. Six-dimensional Q2C decision matrix

| ID | Dimension | Actual-side authority | Forecast-side evidence | Current status | Owner decision required | Options | Effect on Q2C |
|---|---|---|---|---|---|---|---|
| Q2C-D001 | Physical event | HARVEST at valid field scan-weigh boundary | `YES_SAME_HARVEST_MEASUREMENT_BOUNDARY` | APPROVED_BY_BUSINESS_OWNER | false | A same boundary | Exact event equivalence authorized; final attestation remains pending |
| Q2C-D002 | Quantity / marketability | Recorded marketable net weight, KG, non-marketable fruit excluded | `EXACT_SAME_QUANTITY_BOUNDARY` | APPROVED_BY_BUSINESS_OWNER | false | A exact | Exact quantity/marketability equivalence authorized; no substitute target |
| Q2C-D003 | Sorting boundary | Field sorting before recorded label; later sorting not retroactive | `EXACT_SAME_SORTING_BOUNDARY` | APPROVED_BY_BUSINESS_OWNER | false | A exact | Exact field sorting boundary authorized; no retention transformation |
| Q2C-D004 | Post-harvest boundary | Recorded field scan-weigh; no later retention/receipt/rejection/return adjustment | `EXACT_SAME_POSTHARVEST_BOUNDARY` | APPROVED_BY_BUSINESS_OWNER | false | A exact | Exact recorded field boundary authorized; no later adjustment |
| Q2C-D005 | Time basis | Asia/Shanghai farm-local harvest business date and local calendar day | Contract requires same business date, not receipt/UTC/ingestion/latest | REPOSITORY_CONTRACT_PROVEN | false | PROVEN_COMPATIBLE_BY_CONTRACT; mismatch; unknown | Structurally compatible; final source/Q2C artifact still pending |
| Q2C-D006 | Canonical grain | Season × farm × subfarm × variety × harvest business date; plot false | Contract/audit structurally includes season/farm/subfarm/variety/date | REPOSITORY_CONTRACT_PROVEN | false | PROVEN_STRUCTURALLY_COMPATIBLE; mismatch; unknown | Structural compatibility only; cohort membership remains separate |

D005 and D006 are contract-level conclusions, not a positive governed Q2C
acceptance. They do not accept the Source 002 cohort or prove source-row
membership.

## 7. Q2C outcome derivation

```text
ALREADY_FIXED_DIMENSION_COUNT=0
CONTRACT_PROVEN_DIMENSION_COUNT=2
BUSINESS_OWNER_APPROVED_DIMENSION_COUNT=4
BUSINESS_OWNER_DECISION_REQUIRED_COUNT=0
UNRESOLVED_Q2C_DECISION_IDS=[]
CANDIDATE_Q2C_OUTCOME=PROVEN_EXACT
BUSINESS_SEMANTIC_EQUIVALENCE_CLOSED=true
CURRENT_Q2C_OUTCOME=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
```

The four owner-approved exact dimensions plus the two contract-proven
dimensions close the business semantic candidate outcome. No transformation is
required or authorized, and no silent target substitution is available. The
formal governed Q2C decision remains unissued until the remaining attestation
requirements and independent review are complete.

## 8. Business-source-attestation candidate

The companion candidate is:
`docs/v0-3/s1/evidence/business-source-attestation-candidate.json`.

It reuses the fixed Source 002 identity and records the actual-label facts without
inventing date ranges, missing-day statistics, identity arrays, late-entry
policy, or visibility authority. It classifies every schema-required field as
known/authorized, known-but-not-finalized, missing authority, missing governed
value, or owned by the later cohort task.

```text
ATTESTATION_TOP_LEVEL_REQUIRED_FIELD_COUNT=36
ATTESTATION_REQUIRED_LEAF_REQUIREMENT_COUNT=57
ATTESTATION_UNRESOLVED_TOP_LEVEL_FIELD_COUNT=14
ATTESTATION_UNRESOLVED_LEAF_REQUIREMENT_COUNT=31
Q2C_BUSINESS_OWNER_DECISION_RECORD_REFERENCE=q2c-business-owner-decision-v1
Q2C_BUSINESS_OWNER_DECISION_RECORD_SHA256=85d2718caa32ed4207a4afa7f68680a5c7e71132b7c59620b2eb94916c2ac66f
FINAL_ATTESTATION_SCHEMA_READY=false
FINAL_ATTESTATION_CREATION_ALLOWED=false
FINAL_BUSINESS_SOURCE_ATTESTATION_CREATED=false
ATTESTATION_STATUS=UNSIGNED
```

The candidate deliberately is not schema-valid: nulls mark unresolved values and
are not dummy strings. The final artifact may only be created after all required
values are truthful, governed, versioned and reviewed.

## 9. Business-owner Q2C decision formalization

The formal decision record is
`docs/v0-3/s1/evidence/q2c-business-owner-decision-record.json` with
`decision_record_sha256=85d2718caa32ed4207a4afa7f68680a5c7e71132b7c59620b2eb94916c2ac66f`.
It records the governance-session authorization without recording personal
identity. The matrix below distinguishes owner-approved semantic decisions from
repository-contract conclusions.

| ID | Previous status | Formal authority | Approved/proven value | Current status | Record |
|---|---|---|---|---|---|
| Q2C-D001 | BUSINESS_OWNER_DECISION_REQUIRED | BUSINESS_OWNER | `YES_SAME_HARVEST_MEASUREMENT_BOUNDARY` | APPROVED_BY_BUSINESS_OWNER | q2c-business-owner-decision-v1 |
| Q2C-D002 | BUSINESS_OWNER_DECISION_REQUIRED | BUSINESS_OWNER | `EXACT_SAME_QUANTITY_BOUNDARY` | APPROVED_BY_BUSINESS_OWNER | q2c-business-owner-decision-v1 |
| Q2C-D003 | BUSINESS_OWNER_DECISION_REQUIRED | BUSINESS_OWNER | `EXACT_SAME_SORTING_BOUNDARY` | APPROVED_BY_BUSINESS_OWNER | q2c-business-owner-decision-v1 |
| Q2C-D004 | BUSINESS_OWNER_DECISION_REQUIRED | BUSINESS_OWNER | `EXACT_SAME_POSTHARVEST_BOUNDARY` | APPROVED_BY_BUSINESS_OWNER | q2c-business-owner-decision-v1 |
| Q2C-D005 | REPOSITORY_CONTRACT_PROVEN | REPOSITORY_CONTRACT | `PROVEN_COMPATIBLE_BY_CONTRACT` | REPOSITORY_CONTRACT_PROVEN | q2c-business-owner-decision-v1 |
| Q2C-D006 | REPOSITORY_CONTRACT_PROVEN | REPOSITORY_CONTRACT | `PROVEN_STRUCTURALLY_COMPATIBLE` | REPOSITORY_CONTRACT_PROVEN | q2c-business-owner-decision-v1 |

```text
Q2C_DECISION_DIMENSION_COUNT=6
UNIQUE_Q2C_DECISION_ID_COUNT=6
BUSINESS_OWNER_APPROVED_DIMENSION_COUNT=4
REPOSITORY_CONTRACT_PROVEN_DIMENSION_COUNT=2
PENDING_BUSINESS_OWNER_DECISION_COUNT=0
UNRESOLVED_Q2C_DECISION_IDS=[]
BUSINESS_SEMANTIC_Q2C_CANDIDATE_OUTCOME=PROVEN_EXACT
BUSINESS_SEMANTIC_EQUIVALENCE_CLOSED=true
FORMAL_Q2C_DECISION_STATUS=NOT_ISSUED
Q2C_ACCEPTED=false
```

The semantic candidate is exact, but formal Q2C acceptance remains blocked by
the missing schema-valid business-source attestation and independent review.
The later cohort task still owns mapping and cohort formalization.

## 10. Explicit non-acceptance and data-safety boundary

```text
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
TEST_DATA_ACCESS=false
EXTERNAL_HOLDOUT_ACCESS=false
SOURCE_COHORT_MANIFEST_CREATED=false
Q2C_ACCEPTED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

No source export, row-level artifact, database, test, or holdout was accessed.
The existing aggregate evidence was reused only as recorded.

## 11. Validation evidence

```text
JSON_SYNTAX=PASS
Q2C_DECISION_DIMENSION_COUNT=6
UNIQUE_Q2C_DECISION_ID_COUNT=6
BUSINESS_OWNER_APPROVED_DIMENSION_COUNT=4
REPOSITORY_CONTRACT_PROVEN_DIMENSION_COUNT=2
PENDING_BUSINESS_OWNER_DECISION_COUNT=0
Q2C_D001_APPROVED_VALUE_PARITY=PASS
Q2C_D002_APPROVED_VALUE_PARITY=PASS
Q2C_D003_APPROVED_VALUE_PARITY=PASS
Q2C_D004_APPROVED_VALUE_PARITY=PASS
Q2C_D005_CONTRACT_PARITY=PASS
Q2C_D006_CONTRACT_PARITY=PASS
BUSINESS_SEMANTIC_OUTCOME_DERIVATION=PASS
BUSINESS_SEMANTIC_Q2C_CANDIDATE_OUTCOME=PROVEN_EXACT
SILENT_TARGET_SUBSTITUTION_FOUND=false
UNDOCUMENTED_TRANSFORMATION_FOUND=false
Q2C_DECISION_RECORD_HASH_RECOMPUTE=PASS
Q2C_DECISION_RECORD_HASH_IS_LOWERCASE_SHA256=true
ATTESTATION_READINESS_RECOMPUTED=true
SOURCE_AUTHORITY_RECORD_FOUND=true
SOURCE_IDENTITY_PARITY=PASS
ACTUAL_LABEL_PARITY=PASS
FORECAST_CANDIDATE_PARITY=PASS
MARKDOWN_JSON_CONSISTENCY=PASS
GIT_DIFF_CHECK=PASS
```

## 12. Next action and stop condition

```text
Q2C_BUSINESS_OWNER_DECISION_REQUIRED=false
FINAL_Q2C_DECISION_RECORD_CREATED=false
FINAL_BUSINESS_SOURCE_ATTESTATION_CREATED=false
NEXT_RECOMMENDED_ACTION=RUN_PR198_EXACT_HEAD_INDEPENDENT_REVIEW_AFTER_Q2C_OWNER_DECISION_FORMALIZATION
NO_STEP_IMPLIES_THE_NEXT=true
STOPPED_AFTER_S1_REMAINING_02_DRAFT_PR=true
```

This package stops after owner-decision formalization. It does not start
S1-REMAINING-03, issue an attestation, issue a formal Q2C decision, change a
canonical gate, or authorize S2.
