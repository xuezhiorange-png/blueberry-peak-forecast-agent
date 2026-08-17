# V0.3-S1 Real Business Data Contract and Source Cohort Freeze

## Document identity

```text
SLICE=V0.3-S1
ENGLISH_ID=REAL_BUSINESS_DATA_CONTRACT_AND_SOURCE_COHORT_FREEZE
TASK_NAME=V0_3_S1_REAL_BUSINESS_DATA_CONTRACT_AND_SOURCE_COHORT_FREEZE
PLAN_BASELINE_TAG=v0.3.0-plan
PLAN_BASELINE_COMMIT=7a42eecd9b54b8fd12c195e581889ee094ce51c8
SOURCE_PLAN_PATH=docs/v0-3/development-plan.md
S1_SCOPE_ONLY=true
```

This package freezes the decision contracts and acceptance records needed before
real business data can enter V0.3. It contains no business rows, source files,
fixtures, credentials, private source locations, or model changes. It does not
authorize data access or implementation.

## Package contents

| File | Purpose |
| --- | --- |
| `target-decision-and-quantity-contract.md` | Target decision, physical quantity boundary, and Q2C alignment contract. |
| `source-authority-and-cohort-manifest.md` | Source-owner evidence, source identity, cohort manifest, and hash contract. |
| `visibility-inclusion-revision-contract.md` | Point-in-time visibility, inclusion, revision winner, and correction rules. |
| `split-holdout-and-custody-contract.md` | Time-safe splits, external holdout feasibility, custody, and no-data-in-Git rules. |
| `metric-coverage-and-quality-contract.md` | Metric identities, coverage gates, quality thresholds, and S3 binding. |
| `s1-acceptance-package.md` | Complete S1 gate registry and fail-closed acceptance record. |
| `schemas/business-source-attestation.schema.json` | Machine-readable attestation shape without personal identity fields. |
| `schemas/source-cohort-manifest.schema.json` | Machine-readable aggregate cohort and source-object identity shape. |
| `schemas/s1-acceptance-record.schema.json` | Machine-readable gate and independent-review record shape. |
| `evidence/source-002-q2c-business-source-attestation.json` | Issued Q2C business-source attestation projection. |
| `evidence/source-002-q2c-final-decision.json` | Issued Q2C six-dimension decision record. |
| `evidence/source-002-q2c-business-attestation-and-decision-issuance.json` | Q2C issuance provenance, validation, and state evidence. |
| `workpapers/source-002-q2c-business-attestation-and-decision-issuance.md` | Q2C issuance workpaper and six-dimension reconciliation. |

## Authority precedence

The following precedence is binding for this package. A planning document or
this package cannot override a higher authority.

| Priority | Authority | Use |
| --- | --- | --- |
| 1 | `docs/forecast-quality/q2c-physical-target-equivalence-contract.md` | Physical event, quantity basis, marketability boundary, transformation authority, and Q2C outcome. |
| 2 | `docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md` | Canonical label grain, visibility, revision graph, winner selection, and immutable snapshot identity. |
| 3 | `docs/forecast-quality/q2a-actual-harvest-source-contract.md` | Source record fields, source status, revision semantics, and direct-source requirements. |
| 4 | `docs/forecast-quality/s3-quality-metrics-contract.md` | Metric identity, status, reason code, aggregation, Decimal, coverage, peak, and baseline semantics. |
| 5 | `docs/v0-1/core-forecast-contract.md` | Existing forecast output boundary and quantity vocabulary. |
| 6 | Production schemas | Shape checks only; schemas cannot authorize business evidence. |

When authorities disagree, the record is `BLOCKED` and the discrepancy is
preserved for an explicitly authorized contract amendment. Silent substitution
is prohibited.

## Current status and authorization boundary

The following are current facts, not acceptance claims:

```text
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
V0_3_S1_ACCEPTED=false
CURRENT_S1_TARGET_DECISION=OBSERVED_FARM_PICK_QUANTITY
CURRENT_S1_TARGET_DECISION_REVIEW_STATUS=PENDING_INDEPENDENT_REVIEW
CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=PROVEN_EXACT_PENDING_INDEPENDENT_REVIEW
CURRENT_Q2C_OUTCOME=PROVEN_EXACT
Q2C_DECISION_STATUS=ISSUED_PENDING_INDEPENDENT_REVIEW
CURRENT_FORECAST_TARGET=model_harvested_marketable_quantity_kg
CURRENT_ACTUAL_LABEL=actual_harvest_quantity_kg
TARGET_TRANSFORMATION=NONE
TRANSFORMATION_REQUIRED=false
PROPOSED_TARGET_DECISION=OBSERVED_FARM_PICK_QUANTITY
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=ACCEPTED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=ACCEPTED
CURRENT_SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=4
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=13
CURRENT_SOURCE_COHORT_ID=source-002-s1-cohort-v1
CURRENT_SOURCE_COHORT_MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
CURRENT_SOURCE_COHORT_MANIFEST_HASH=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
CURRENT_SOURCE_ATTESTATION_VERSION=source-002-final-source-owner-attestation-v1
CURRENT_SOURCE_ATTESTATION_STATUS=ATTESTED
CURRENT_SOURCE_ATTESTATION_HASH=2c7bd156da2eb3d7c2cb5906e23cb3d380f709b43e39e1c6a6ce38f5587971e1
CURRENT_Q2C_BUSINESS_SOURCE_ATTESTATION_VERSION=source-002-q2c-business-source-attestation-v1
CURRENT_Q2C_BUSINESS_SOURCE_ATTESTATION_HASH=09a1ccc02036d353ab1fb8cd7a25edcdc0458a736fec510cd1c3711f51137be2
CURRENT_Q2C_DECISION_VERSION=source-002-q2c-final-decision-v1
CURRENT_Q2C_DECISION_HASH=c7feccd6791b6e9879f82c034552e53d5cc96922314cffa4d21fe5ee1e5d0e18
CURRENT_S1_HOLDOUT_FEASIBILITY_DECISION=NOT_EVALUATED
PROPOSED_S1_HOLDOUT_FEASIBILITY_DECISION=BLOCKED
CURRENT_EXTERNAL_HOLDOUT_GATE_STATUS=BLOCKED
CURRENT_EXTERNAL_HOLDOUT_GATE_BLOCK_REASON=FEASIBILITY_NOT_YET_ACCEPTED
CURRENT_EXTERNAL_HOLDOUT_NOT_APPLICABLE=false
CURRENT_CROSS_FARM_GENERALIZATION_CLAIM_ALLOWED=false
CURRENT_V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

The six-dimensional Q2C business evidence package is issued on current main
with `Q2C_OUTCOME=PROVEN_EXACT`. The six dimensions are physical event,
quantity basis, marketability boundary, sorting boundary, post-harvest
boundary, and time/grain. Independent review and canonical Q2C acceptance are
still pending, so `Q2C_ACCEPTED=false` and the S1-Q2C-TARGET gate remains
`BLOCKED`.

The following requirements are future acceptance requirements:

```text
S1_ACCEPTANCE_REQUIRES_BUSINESS_SOURCE_ATTESTATION=true
S1_ACCEPTANCE_REQUIRES_SOURCE_COHORT_MANIFEST=true
S1_ACCEPTANCE_REQUIRES_Q2C_PHYSICAL_ALIGNMENT_OUTCOME=true
S1_ACCEPTANCE_REQUIRES_POINT_IN_TIME_VISIBILITY_CONTRACT=true
S1_ACCEPTANCE_REQUIRES_REVISION_WINNER_RULE=true
S1_ACCEPTANCE_REQUIRES_TRAIN_VALIDATION_TEST_SPLIT=true
S1_ACCEPTANCE_REQUIRES_EXTERNAL_HOLDOUT_FEASIBILITY_DECISION=true
S1_ACCEPTANCE_REQUIRES_METRIC_COVERAGE_AND_QUALITY_CONTRACT=true
S1_ACCEPTANCE_REQUIRES_INDEPENDENT_REVIEW=true
```

No requirement above authorizes its own implementation. The execution order is
`S1_ACCEPTED -> S2_MAY_BE_AUTHORIZED`; no step implies the next step.

## Missing external inputs

Source Authority and Source Cohort are accepted on current main from the merged
final Source Owner Attestation and the merged, independently reviewed final
Source Cohort Manifest. S1 remains blocked because downstream gates still
require the evidence listed below. This list is a contract of remaining
evidence, not a claim that any value exists.

- source system, dataset, and immutable source version;
- physical event, weighing point, measurement method, unit, and calibration
  authority;
- marketability, field sorting, packhouse sorting, rejection, and post-harvest
  loss boundaries;
- farm-local date policy, source-recorded-time authority, late entry, revision,
  void, correction, and finalization rules;
- canonical grain and mapping evidence for farm, subfarm, variety, season, and
  business date;
- coverage, exclusions, missing-day policy, and cohort summary;
- immutable object identity, schema/mapping hashes, and custody record;
- split and external-holdout feasibility evidence.

No row-level data is requested or read by this package.

## Non-scope and safety

This package does not implement S1, S2, model training, model change, API
change, database migration, frontend change, or CI change. It does not prove
real-business accuracy or business representativeness. Real business data may
not be committed to Git, and TEST or external holdout data may not be accessed
until separately authorized.

```text
REAL_DATA_IMPORT_AUTHORIZED=false
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
EXTERNAL_HOLDOUT_DATA_ACCESS=false
MODEL_CHANGE_AUTHORIZED=false
PRODUCTION_CODE_CHANGE_AUTHORIZED=false
MIGRATION_AUTHORIZED=false
FRONTEND_CHANGE_AUTHORIZED=false
V0_3_S1_IMPLEMENTATION_AUTHORIZED=false
V0_3_S2_IMPLEMENTATION_AUTHORIZED=false
V0_3_IMPLEMENTATION_AUTHORIZED=false
```

The final S1 decision must be recorded in the acceptance schema with a
separate independent reviewer. Until then, `CURRENT_V0_3_S1_ACCEPTANCE_STATUS`
remains `BLOCKED`.

## Historical post-PR238 Source Authority closeout mirror

```text
POST_PR238_CURRENT_MAIN_REVALIDATION=PASS
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=3
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=14
SOURCE_AUTHORITY_INDEPENDENT_REVIEW_ID=4946622009
SOURCE_AUTHORITY_EXACT_HEAD_CI_RUN_ID=31955752008
S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This is the historical post-PR238, pre-PR241 snapshot and is retained as
provenance only; it is not the current Source Cohort state.

## Current post-PR241 Source Cohort closeout mirror

```text
POST_PR241_CURRENT_MAIN_REVALIDATION=PASS
PR241_MERGED=true
PR241_HEAD_SHA=b856d3823e51bb6e4f8b780363203a1c477677ca
PR241_MERGE_SHA=5caa63a20ee45b7e725b3c2c696a41cd3dd4a06b
SOURCE_COHORT_INDEPENDENT_REVIEW_ID=4948013727
SOURCE_COHORT_INDEPENDENT_REVIEW_GRAPHQL_ID=PRR_kwDOS_gTTs8AAAABJuyynw
SOURCE_COHORT_REVIEWED_AT=2026-08-17T02:25:52Z
SOURCE_COHORT_EXACT_HEAD_CI_RUN_ID=31986614521
SOURCE_COHORT_EXACT_HEAD_CI_CONCLUSION=success
SOURCE_COHORT_ID=source-002-s1-cohort-v1
SOURCE_COHORT_MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
SOURCE_COHORT_MANIFEST_HASH=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=4
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=13
S1_FREEZES_SOURCE_COHORT_IDENTITY=true
S1_FREEZES_FINAL_CLEAN_ROWSET=false
S2_OWNS_FINAL_MATERIALIZED_ROWSET=true
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The Source Cohort closeout is gate-local. It freezes the Source Cohort identity
and manifest only; it does not accept Q2C, canonical grain, inclusion/exclusion,
visibility, revision, custody, split, holdout, overall S1, or V0.3-S2.
