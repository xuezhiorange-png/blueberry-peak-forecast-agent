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
CURRENT_S1_TARGET_DECISION=UNRESOLVED_PENDING_INDEPENDENT_REVIEW
CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
PROPOSED_TARGET_DECISION=NOT_PROPOSED
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=ACCEPTED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=3
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=14
CURRENT_SOURCE_ATTESTATION_VERSION=source-002-final-source-owner-attestation-v1
CURRENT_SOURCE_ATTESTATION_STATUS=ATTESTED
CURRENT_SOURCE_ATTESTATION_HASH=2c7bd156da2eb3d7c2cb5906e23cb3d380f709b43e39e1c6a6ce38f5587971e1
CURRENT_S1_HOLDOUT_FEASIBILITY_DECISION=NOT_EVALUATED
PROPOSED_S1_HOLDOUT_FEASIBILITY_DECISION=BLOCKED
CURRENT_EXTERNAL_HOLDOUT_GATE_STATUS=BLOCKED
CURRENT_EXTERNAL_HOLDOUT_GATE_BLOCK_REASON=FEASIBILITY_NOT_YET_ACCEPTED
CURRENT_EXTERNAL_HOLDOUT_NOT_APPLICABLE=false
CURRENT_CROSS_FARM_GENERALIZATION_CLAIM_ALLOWED=false
CURRENT_V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

`PROPOSED_TARGET_DECISION=NOT_PROPOSED` is intentional: no six-dimensional
business evidence package was supplied to this task. The six dimensions are
physical event, quantity basis, marketability boundary, sorting boundary,
post-harvest boundary, and time/grain. The package defines how the decision is
made; it does not make the decision.

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

Source Authority is accepted on current main from the merged final Source Owner
Attestation and exact-head independent acceptance. S1 remains blocked because
downstream gates still require the evidence listed below. This list is a contract
of remaining evidence, not a claim that any value exists.

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
- immutable object identity, schema/mapping hashes, manifest hash, and custody
  record;
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

## Current Source Authority closeout mirror

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

The Source Authority gate closeout is not Source Cohort acceptance and does not
authorize data access, Remaining-06, or V0.3-S2.
