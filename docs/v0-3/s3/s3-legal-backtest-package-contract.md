# V0.3-S3-C legal backtest package contract R1

## Contract identity and boundary

~~~text
CONTRACT_ID=V0_3_S3_C_LEGAL_BACKTEST_PACKAGE_CONTRACT_R1
CONTRACT_VERSION=v0-3-s3-c-legal-backtest-package-contract-v1
TASK_ID=V0_3_S3_C_LEGAL_BACKTEST_PACKAGE_CONTRACT_R1
TASK_CLASS=READ_ONLY_DISCOVERY_AND_CONTRACT_FREEZE
AUTHORIZATION_SCOPE=S3_C_LEGAL_BACKTEST_PACKAGE_CONTRACT_ONLY
BASE_MAIN_SHA=3b31f390a69ed8984570fe7d3d5ec9eb6c0d6349
PARENT_PR=570
PARENT_MERGE_COMMIT=3b31f390a69ed8984570fe7d3d5ec9eb6c0d6349
S3_C_LEGAL_BACKTEST_PACKAGE_CONTRACT_FROZEN=true
S3_C_LEGAL_BACKTEST_PACKAGE_IMPLEMENTATION_AUTHORIZED=false
LEGAL_BACKTEST_PACKAGE_IMPLEMENTED=false
S3_C_BACKTEST_EXECUTION_PERFORMED=false
S3_METRIC_EXECUTION_PERFORMED=false
S3_D_ATTRIBUTION_EXECUTION_PERFORMED=false
TEST_REMAINS_SEALED=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This document freezes the prerequisite package contract for a future lawful
S3-C point-in-time backtest. It records current-main discovery and defines the
minimum typed, identity-bound package that a later implementation must produce.
It does not implement a package, run S3-C, calculate a metric, access TEST, or
convert authorization into execution.

## 1. Current-main discovery verdict

The discovery was performed against the current main commit identified above.
The current §4.4 live-state block, the production pairing APIs, the trusted
registries, and the PIT forecast provider were inspected. Older append-only
historical snapshots in the planning document are not treated as replacements
for the current implementation state.

~~~text
TRAIN_PAIRING_PACKAGE_PRODUCIBLE=true
VALIDATION_PAIRING_PACKAGE_PRODUCIBLE=true
TRAIN_PAIRING_PACKAGE_LIVE_RUN_PERFORMED=false
VALIDATION_PAIRING_PACKAGE_LIVE_RUN_PERFORMED=false
TRAIN_PAIRING_PACKAGE_PUBLISHED=false
VALIDATION_PAIRING_PACKAGE_PUBLISHED=false
TRAIN_AUTHORITY_RECORD_TRUSTED=false
VALIDATION_AUTHORITY_RECORD_TRUSTED=false
IN_SCOPE_FORECAST_CUTOFF_COUNT_IF_DURABLY_KNOWN=1
FULL_HISTORICAL_CUTOFF_COVERAGE_AVAILABLE=false
LEGAL_BACKTEST_PACKAGE_CURRENTLY_AVAILABLE=false
GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED=UNRESOLVED_BLOCKING
~~~

Here, PRODUCIBLE means that current code has a materialization path capable of
returning partition-scoped candidate pairing packages when its lawful live
dependencies are present. It does not mean that a package was produced in this
contract task, published, issued, or legally usable.

### 1.1 The six required questions

| Question | Current-main answer | Evidence and interpretation |
| --- | --- | --- |
| Can live pairing materialization produce TRAIN? | Yes, as a candidate package path | materialize_train_validation_pairing_inputs(...) constructs a TRAIN package through build_candidate_train_validation_pairing_package(...). The module explicitly says it does not publish packages. |
| Can live pairing materialization produce VALIDATION? | Yes, as a candidate package path | The same materializer constructs a separate VALIDATION package using the accepted validation partition identity. |
| Are real package identities durably published in the trusted pairing registry? | No | PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_REGISTRY.count() is 0. The materializer validates and returns candidate packages but does not publish them. |
| Are real authority records present in the trusted issued registry? | No | PRODUCTION_TRUSTED_ISSUED_AUTHORITY_REGISTRY.count() is 0 and the issued partition-authority schema-version set is empty. A carrier dataclass or policy allowlist is not an issued record. |
| Are all S3-C historical cutoffs represented? | No | The current reviewed origin artifact exposes one cutoff, 2026-02-16T00:00:00+08:00, for the three reviewed quantiles. The current loader accepts one cutoff and no durable complete cutoff set was found. |
| Is a complete legal package constructible today without production-code changes? | No | There is no S3LegalBacktestPackage implementation or legal-package identity. Trusted package publication, trusted authority issuance, complete cutoff-set coverage, and package construction remain unresolved. |

The current A2 evaluation-instance registry and its live-bindable catalog are
not equivalent to the S3-B trusted published pairing registry. They establish
different identities and cannot substitute for partition pairing packages or
issued partition authority records.

## 2. Inherited source and partition authority

S3-C is limited to the accepted SOURCE-002 TRAIN and VALIDATION partitions.
The source cohort manifest remains the source of coverage scope; its farms and
subfarms are not re-derived from TEST and are not replaced by metric results.

~~~text
SOURCE_COHORT_MANIFEST=docs/v0-3/s1/evidence/source-002-final-source-cohort-manifest.json
SOURCE_COHORT_FARM_COUNT=84
SOURCE_COHORT_SUBFARM_COUNT=192
SOURCE_DATASET_ID=source-002
SOURCE_DATASET_VERSION=e5-live-v1
SOURCE_MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_PARTITION_IDENTITY_SHA256=55d8e97e73568def2cd368bcf76deeb13de5089361f70b08c8101ea8f745097b
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
TRAIN_ROW_COUNT=16224
TRAIN_DATE_RANGE=2025-08-05:2026-01-30
VALIDATION_PARTITION_IDENTITY_SHA256=006c80ff6bc88ecf7112fd082ab7e27e71655ebd2f00ff105d6110a8473244ba
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
VALIDATION_ROW_COUNT=8006
VALIDATION_DATE_RANGE=2026-01-31:2026-03-09
TEST_ROW_COUNT=0
TEST_REMAINS_SEALED=true
TEST_PAYLOAD_MUST_NOT_ENTER_PACKAGE=true
MISSING_DAY_POLICY=UNKNOWN_NOT_ZERO
~~~

The existing SourceDatasetIdentity, PartitionIdentity,
TrainValidationS3BindingPairingPackage, and S3EvaluationInput types are
upstream building blocks. A future legal package must bind their exact stored
identities; it must not replace them with a second source, partition, or row
hash algorithm.

## 3. Forecast authority and cutoff set

The forecast side is the incumbent model at the historical cutoff:

~~~text
FORECAST_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
FORECAST_SELECTION_MODE=historical_observed_pit_visible_unique_grain_forecast_run
FORECAST_CUTOFF_TIMEZONE=Asia/Shanghai
FORECAST_VISIBILITY_RULE=SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
FORECAST_CUTOFF_IS_NOT_HARVEST_DATE=true
REVIEWED_CUTOFF_AT=2026-02-16T00:00:00+08:00
REVIEWED_CUTOFF_BUSINESS_DATE=2026-02-16
REVIEWED_MODEL_ID=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
REVIEWED_QUANTILES=P50,P80,P90
REVIEWED_GRAIN_IDENTITY_SET_SHA256=76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3
REVIEWED_CUTOFF_MEMBER_COUNT=3
~~~

The existing PIT loader and provider perform exact cell, target-date, quantile,
and horizon lookup and reject ambiguous or unavailable forecast runs. This is
lawful authority support for a future package, not proof that every historical
cutoff has been supplied. A single reviewed cutoff is incomplete for a legal
backtest contract that declares an in-scope cutoff set.

### 3.1 Required cutoff-set binding

A future package MUST carry an explicit
IN_SCOPE_FORECAST_CUTOFF_SET and its deterministic
IN_SCOPE_FORECAST_CUTOFF_SET_IDENTITY_SHA256. The set is ordered
canonically and must bind, at minimum, each cutoff timestamp, model identity,
selection policy, and the exact forecast-authority identity used at that
cutoff. The cutoff set is not inferred from harvest dates, database row order,
or the number of observed forecast runs.

The legal package is BLOCKED if the set is empty, incomplete relative to the
declared S3-C evaluation window, has a mismatched identity, or lacks a
cell/target-date/horizon authority binding for any required member.

The current S3-B quantile semantic state is separately recorded on main:
P50, P80, and P90 are marked as verified true upper quantiles. This does not
establish a legal S3-C package, complete daily-rowset evidence, or coverage
execution. Current daily-rowset completeness remains unverified with reason
COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING.

## 4. Future legal package envelope

The following is the frozen shape of a future S3LegalBacktestPackage. Names are
contract names; implementation must use the repository's existing types for
nested pairing inputs, authority records, S2 forecast bundles, and canonical
serialization.

~~~text
S3LegalBacktestPackage
  schema_version
  package_identity_sha256
  canonical_hash_sha256
  source_dataset_identity
  train_partition_identity
  validation_partition_identity
  train_pairing_package_identity
  validation_pairing_package_identity
  train_authority_record_identity
  validation_authority_record_identity
  train_evaluation_input_identity
  validation_evaluation_input_identity
  forecast_authority_identity
  in_scope_forecast_cutoff_set
  in_scope_forecast_cutoff_set_identity_sha256
  forecast_cutoff_authority_identity
  model_identity
  evaluation_window
  point_in_time_visibility_policy
  exact_actual_pairing_policy
  missing_day_policy
  diagnostics
  test_partition_status
~~~

Frozen package version:

~~~text
LEGAL_BACKTEST_PACKAGE_SCHEMA_VERSION=v0-3-s3-c-legal-backtest-package-v1
LEGAL_PACKAGE_STATUS_VALUES=LEGAL,BLOCKED
LEGAL_PACKAGE_SUCCESS_REQUIRES_ALL_PREDICATES=true
LEGAL_PACKAGE_PARTIAL_STATUS_FORBIDDEN=true
TEST_PARTITION_STATUS=SEALED_ABSENT
~~~

diagnostics contains aggregate counts and blocker codes, not an unbounded copy
of raw TRAIN, VALIDATION, or TEST rows. The package may retain the
partition-scoped binding inputs required for a lawful replay, but public
execution evidence must not publish raw rows or a full per-target value list.

### 4.1 Legal predicates

A package may be LEGAL only when every predicate below passes:

1. Source dataset identity exactly equals source-002/e5-live-v1 and the
   accepted materialized identity.
2. TRAIN and VALIDATION partition identities, content hashes, row counts, and
   date ranges match their accepted identities.
3. TEST is absent from package inputs and remains sealed.
4. TRAIN and VALIDATION pairing package identities resolve to trusted,
   published, immutable package records.
5. Both stored pairing packages replay their two-stage identity and canonical
   hash, and their S3EvaluationInput.s2_binding_row_set_hash values match.
6. TRAIN and VALIDATION authority record identities resolve to trusted,
   issued immutable authority records whose hashes replay.
7. Each authority record binds the exact corresponding pairing package,
   partition, row-set hash, policy version, and permitted partition set.
8. There is no cross-partition source-row identity overlap.
9. Actuals use exact canonical grain pairing. Missing actuals remain unknown and
   are never converted to zero.
10. Every required forecast cell, target date, quantile, and horizon resolves to
    the incumbent PIT authority for its cutoff.
11. Each forecast source satisfies SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT,
    using Asia/Shanghai cutoff semantics and no later label or final-season
    fact.
12. Every member of the declared cutoff set is represented and the cutoff-set
    identity replays.
13. No caller-fabricated dataclass, untrusted catalog, positional pairing,
    latest-row fallback, or TEST-derived member list is used as authority.
14. All business numeric values are Decimal values; native floats are
    forbidden at the canonical boundary.
15. The complete package identity and canonical hash replay exactly.

The evaluation window is inherited from the accepted S3-A1 window contract.
Package legality does not silently assert that a complete daily rowset exists.
Sparse point metrics may be considered only when the package predicates and the
downstream metric contract allow them; current daily-rowset completeness is
still a separate blocked state.

### 4.2 Pairing and authority registry boundary

The following existing components are distinct and must not be conflated:

| Component | Role | Legal-package requirement |
| --- | --- | --- |
| materialize_train_validation_pairing_inputs | Creates candidate partition packages | Candidate output alone is insufficient |
| TrainValidationS3BindingPairingPackage | Carries partition-scoped pairing provenance | Stored identity must resolve from the trusted published registry |
| TrainValidationCoveragePartitionAuthority | Carrier/handle used by the coverage gate | Carrier alone is insufficient |
| IssuedTrainValidationCoverageAuthorityRecord | Future issued authority record | Stored record must resolve from the trusted issued registry |
| A2 evaluation-instance catalog/registry | Incumbent catalog bindability | Not a pairing package or issued partition authority |

Current production counts are:

~~~text
PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_COUNT=0
PRODUCTION_TRUSTED_ISSUED_AUTHORITY_RECORD_COUNT=0
ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSION_COUNT=0
PRODUCTION_ISSUED_PAIRING_POLICY_COUNT=2
~~~

The two issued pairing policies do not publish packages or issue authority
records. Future registry population requires a separate implementation and
issuance grant.

## 5. Stable blocker domain

Future construction and validation use stable blocker codes. A blocker must
identify the failed control only; exception messages must not expose production
row values, raw payloads, or a full pair list.

At minimum, the stable domain is:

~~~text
SOURCE_DATASET_IDENTITY_MISMATCH
TRAIN_PARTITION_IDENTITY_MISMATCH
VALIDATION_PARTITION_IDENTITY_MISMATCH
TEST_PARTITION_PRESENT
TEST_NOT_SEALED
TRAIN_PAIRING_PACKAGE_MISSING
VALIDATION_PAIRING_PACKAGE_MISSING
TRAIN_PAIRING_PACKAGE_IDENTITY_INVALID
VALIDATION_PAIRING_PACKAGE_IDENTITY_INVALID
TRAIN_AUTHORITY_RECORD_MISSING
VALIDATION_AUTHORITY_RECORD_MISSING
TRAIN_AUTHORITY_NOT_TRUSTED
VALIDATION_AUTHORITY_NOT_TRUSTED
S2_BINDING_ROW_SET_HASH_MISMATCH
CROSS_PARTITION_ROW_OVERLAP
MISSING_EXACT_ACTUAL_PAIRING
MISSING_EXACT_FORECAST_BINDING_AUTHORITY
FORECAST_VALUE_NOT_PIT_VISIBLE
HISTORICAL_CUTOFF_SET_EMPTY
HISTORICAL_CUTOFF_SET_INCOMPLETE
HISTORICAL_CUTOFF_SET_IDENTITY_MISMATCH
NATIVE_FLOAT_FORBIDDEN
PACKAGE_IDENTITY_MISMATCH
PACKAGE_CANONICAL_HASH_MISMATCH
LEGAL_BACKTEST_PACKAGE_NOT_IMPLEMENTED
~~~

The current-main discovery maps to these additional partition-specific
observations:

~~~text
TRAIN_VALIDATION_PAIRING_PACKAGE_NOT_PUBLISHED
TRAIN_VALIDATION_AUTHORITY_RECORD_NOT_FOUND
TRAIN_VALIDATION_PARTITION_AUTHORITY_NOT_ISSUED
~~~

No unknown or partial condition may be promoted to LEGAL. There is no
pass-with-warnings state.

## 6. Hash and replay contract

All package and cutoff-set hashes use the existing
backend.app.forecast_quality.canonical.canonical_json_bytes behavior. The
contract does not create a second JSON canonicalizer.

### 6.1 Cutoff-set identity

The canonical cutoff-set preimage is ordered by cutoff timestamp, model
identity, selection policy, and authority identity. It includes every declared
cutoff member and excludes no semantic member. Its SHA-256 is stored as
IN_SCOPE_FORECAST_CUTOFF_SET_IDENTITY_SHA256.

### 6.2 Package identity

The package identity uses a two-stage, non-self-referential construction:

1. Build the complete semantic package payload with
   package_identity_sha256 and canonical_hash_sha256 blank.
2. Hash its canonical JSON bytes to obtain package_identity_sha256.
3. Insert that identity, leave only canonical_hash_sha256 blank, and hash the
   canonical JSON bytes again.
4. Store the second result as canonical_hash_sha256.

Neither hash may occur in its own preimage. Replay must perform the same two
stages and reject any mismatch. No timestamp, process id, filesystem path,
database connection detail, worker identity, or native float may enter either
preimage.

## 7. Future construction boundary

The recommended future API is:

~~~text
build_s3_legal_backtest_package(
    *,
    train_materialization,
    validation_materialization,
    train_partition_authority,
    validation_partition_authority,
    forecast_cutoff_set,
) -> S3LegalBacktestPackageResult
~~~

The implementation must bind the existing
TrainValidationPairingMaterializationResult,
TrainValidationS3BindingPairingPackage,
TrainValidationCoveragePartitionAuthority,
and IssuedTrainValidationCoverageAuthorityRecord types where applicable. It
must not alter those existing modules as part of this contract freeze.

The required future sequence is:

~~~text
SOURCE-002 governed obtain
  -> TRAIN/VALIDATION pairing materialization
  -> trusted package and authority verification
  -> historical cutoff-set completeness verification
  -> legal package construction
  -> package identity replay
  -> S3-C PIT backtest execution
  -> metric execution
  -> S3-D attribution
~~~

Each arrow is a separate gate. No step implies the next.

## 8. Generic incumbent artifact decision

The repository has a lawful PIT incumbent path with exact per-cell,
target-date, quantile, and horizon lookup, and the current A2 catalog is a
separate live-bindable authority. The repository does not contain a generic
versioned incumbent forecast artifact. Because trusted pairing/authority
publication and complete historical cutoff coverage are not established, the
contract deliberately records:

~~~text
GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED=UNRESOLVED_BLOCKING
GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_DECISION_NOT_FINAL=true
~~~

This does not silently require or waive a new artifact. A future decision may
set the requirement to false only after lawful PIT authority, exact
per-cell/horizon bundles, binding replay, trusted package and authority
verification, and full cutoff coverage are all evidenced. Existing snapshots
must not be overridden by an unverified artifact.

## 9. Execution and authority boundaries

Current main authorization remains distinct from current execution:

~~~text
S3_C_BACKTEST_EXECUTION_AUTHORIZED=true
S3_METRIC_EXECUTION_AUTHORIZED=true
S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=true
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_METRIC_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
S3_C_LEGAL_BACKTEST_PACKAGE_IMPLEMENTATION_AUTHORIZED=false
LEGAL_BACKTEST_PACKAGE_IMPLEMENTED=false
S3_C_BACKTEST_EXECUTION_PERFORMED=false
S3_METRIC_EXECUTION_PERFORMED=false
S3_D_ATTRIBUTION_EXECUTION_PERFORMED=false
BASELINE_VS_INCUMBENT_COMPARISON_AUTHORIZED=false
BASELINE_VS_INCUMBENT_COMPARISON_EXECUTED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
NO_PRODUCTION_CODE_CHANGE=true
NO_TEST_CODE_CHANGE=true
NO_DATABASE_MUTATION=true
NO_MIGRATION=true
NO_SCHEMA_CHANGE=true
NO_MODEL_CHANGE=true
NO_PARAMETER_CHANGE=true
NO_TEST_ACCESS=true
NO_NEW_METRIC_EXECUTION=true
NO_S3_C_EXECUTION=true
NO_S3_D_EXECUTION=true
NO_S4=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
~~~

The Farm-total baseline metrics recorded by PR #570 remain a sibling
reference only. They are not incumbent backtest inputs and no baseline-versus-
incumbent comparison is performed or authorized by this contract.

## 10. Current conclusion and next gate

~~~text
LEGAL_BACKTEST_PACKAGE_CURRENTLY_AVAILABLE=false
NO_LEGAL_BACKTEST_PACKAGE=true
CURRENT_LEGAL_BACKTEST_PACKAGE_BLOCKER=TRAIN_PAIRING_PACKAGE_NOT_PUBLISHED;VALIDATION_PAIRING_PACKAGE_NOT_PUBLISHED;TRAIN_AUTHORITY_RECORD_NOT_TRUSTED;VALIDATION_AUTHORITY_RECORD_NOT_TRUSTED;HISTORICAL_CUTOFF_SET_INCOMPLETE;LEGAL_BACKTEST_PACKAGE_NOT_IMPLEMENTED
NEXT_GATE=授权实施legal backtest package
~~~

This R1 contract freezes the legal package boundary and the current discovery
result. A separate user-authorized implementation task is required before
package construction, and separate execution authorization is required before
S3-C backtest or metric execution.
