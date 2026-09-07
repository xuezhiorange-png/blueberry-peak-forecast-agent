# V0.3-S3-C legal backtest package implementation R1

## Implementation identity

~~~text
ARTIFACT_ID=V0_3_S3_C_LEGAL_BACKTEST_PACKAGE_IMPLEMENTATION_R1
ARTIFACT_VERSION=s3-c-legal-backtest-package-implementation-r1-v1
TASK_ID=V0_3_S3_C_LEGAL_BACKTEST_PACKAGE_IMPLEMENTATION_R1
TASK_CLASS=AUTHORIZED_IMPLEMENTATION
BASE_MAIN_SHA=416e8d5d3e62511be384beb4a3b9cb4c728955d9
PARENT_PR=571
PARENT_MERGE_COMMIT=416e8d5d3e62511be384beb4a3b9cb4c728955d9
USER_GATE=可以执行评分
IMPLEMENTATION_AUTHORIZED=true
PACKAGE_BUILDER_IMPLEMENTED=true
S3_C_LEGAL_BACKTEST_PACKAGE_IMPLEMENTATION_AUTHORIZED=true
LEGAL_BACKTEST_PACKAGE_IMPLEMENTED=true
LEGAL_BACKTEST_PACKAGE_CURRENTLY_AVAILABLE=false
S3_LEGAL_BACKTEST_PACKAGE_SCHEMA_VERSION=v0-3-s3-c-legal-backtest-package-v1
LEGAL_PACKAGE_STATUS_VALUES=LEGAL,BLOCKED
LEGAL_PACKAGE_PARTIAL_STATUS_FORBIDDEN=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=true
S3_METRIC_EXECUTION_AUTHORIZED=true
S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=true
CURRENT_S3_C_BACKTEST_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_METRIC_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
CURRENT_S3_D_ATTRIBUTION_EXECUTION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
~~~

This workpaper records the implementation surface authorized by the
post-#571 contract. It does not claim that the prerequisites for a live legal
package are currently available.

## 1. Authorized change surface

Exactly five paths are authorized for this implementation:

~~~text
backend/app/forecast_quality/s3_legal_backtest_package.py
backend/tests/forecast_quality/test_s3_legal_backtest_package.py
docs/v0-3/s3/workpapers/s3-c-legal-backtest-package-implementation-r1.md
docs/v0-3/s3/evidence/s3-c-legal-backtest-package-implementation-r1.json
docs/v0-3/development-plan.md
~~~

The development-plan change is append-only. No existing production module,
schema, migration, frozen contract, or CI file was modified. The current
combined TrainValidationPairingMaterializationResult is accepted by the
implementation; the recommended split-name API is retained as a compatibility
surface without creating a second producer result.

~~~text
RECOMMENDED_API_ADAPTED_TO_CURRENT_COMBINED_MATERIALIZATION_RESULT=true
NO_SEMANTIC_CONTRACT_CHANGE=true
EXISTING_PRODUCTION_FILES_MODIFIED=false
EXISTING_FROZEN_CONTRACT_MODIFIED=false
DATABASE_MUTATION=false
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
MODEL_CHANGE=false
PARAMETER_CHANGE=false
~~~

## 2. Implemented typed package

The new module provides frozen dataclasses for:

~~~text
S3LegalBacktestPackage
S3LegalBacktestPackageDiagnostics
S3LegalBacktestPackageResult
S3LegalBacktestForecastCutoff
S3LegalBacktestForecastCutoffSet
S3GenericIncumbentForecastArtifactRequirement
~~~

It provides the public builder:

~~~text
build_s3_legal_backtest_package(...)
~~~

and package identity helpers:

~~~text
build_s3_legal_backtest_package_semantic_payload(...)
compute_forecast_cutoff_set_identity_sha256(...)
compute_s3_legal_backtest_package_identity_hashes(...)
verify_s3_legal_backtest_package_hash_replay(...)
~~~

The public builder is production-bound to the existing trusted published
pairing-package registry, trusted issued-authority registry, and current
issued schema-version set. It has no caller-controlled trust bypass. The
private registry-context helper exists only for synthetic in-memory tests of
future legal branches.

## 3. Fail-closed package controls

The builder validates the source and accepted TRAIN/VALIDATION partition
identities, stored pairing package hashes, row-set hashes, exact actual
pairing, cross-partition source-row overlap, forecast binding presence, PIT
cutoff membership, TEST sealing, and package identity replay. It reuses:

~~~text
verify_pairing_package_hash_replay=true
validate_published_pairing_package_invariants=true
verify_train_validation_coverage_authority=true
verify_authority_record_hash_replay=via_existing_authority_verifier=true
canonical_json_bytes=true
TWO_STAGE_PACKAGE_HASH=true
TWO_STAGE_HASH_SELF_REFERENCE=false
NATIVE_FLOAT_FORBIDDEN=true
~~~

The only package statuses are:

~~~text
LEGAL
BLOCKED
LEGAL_PACKAGE_PARTIAL_STATUS_FORBIDDEN=true
~~~

The stable blocker domain includes the frozen contract set:

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
GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_UNRESOLVED
GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED_BUT_NOT_AVAILABLE
~~~

Diagnostics contain counts and blocker codes only. They do not copy raw
TRAIN, VALIDATION, or TEST rows, per-target values, or exception payloads.

## 4. Current production result remains BLOCKED

Implementation is complete, but current production legality is intentionally
not claimed:

~~~text
LEGAL_BACKTEST_PACKAGE_CURRENTLY_AVAILABLE=false
TRAIN_PAIRING_PACKAGE_PUBLISHED=false
VALIDATION_PAIRING_PACKAGE_PUBLISHED=false
TRAIN_AUTHORITY_RECORD_TRUSTED=false
VALIDATION_AUTHORITY_RECORD_TRUSTED=false
PRODUCTION_TRUSTED_PUBLISHED_PAIRING_PACKAGE_COUNT=0
PRODUCTION_TRUSTED_ISSUED_AUTHORITY_RECORD_COUNT=0
ISSUED_PARTITION_AUTHORITY_SCHEMA_VERSION_COUNT=0
DURABLY_OBSERVED_IN_SCOPE_FORECAST_CUTOFF_COUNT=1
COMPLETE_IN_SCOPE_FORECAST_CUTOFF_COUNT=UNKNOWN
FULL_HISTORICAL_CUTOFF_COVERAGE_AVAILABLE=false
CURRENT_LEGAL_BACKTEST_PACKAGE_BLOCKERS=TRAIN_PAIRING_PACKAGE_NOT_PUBLISHED;VALIDATION_PAIRING_PACKAGE_NOT_PUBLISHED;TRAIN_AUTHORITY_NOT_TRUSTED;VALIDATION_AUTHORITY_NOT_TRUSTED;HISTORICAL_CUTOFF_SET_INCOMPLETE;GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_UNRESOLVED
~~~

The public builder preserves the unresolved generic-artifact decision. The
three-way branch is explicit:

~~~text
GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIRED=UNRESOLVED_BLOCKING
GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_DECISION_NOT_FINAL=true
GENERIC_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_REQUIREMENT_RESOLVED=false
REQUIRED_FALSE_ARTIFACT_PRESENCE_GATE=LEGAL_NO_OP
REQUIRED_TRUE_ARTIFACT_GATE=IDENTITY_BINDING_PROVENANCE_REPLAY_REQUIRED
~~~

No artifact identity, schema, content, or provenance is invented by this
implementation.

## 5. Synthetic test contract

All new tests are in-memory and synthetic. The documented 35 themes are
covered by 53 passing tests:

~~~text
TEST_THEME_COVERAGE_REQUIRED=35/35
NEW_SCORER_TEST_RESULT=PASS
NEW_SCORER_TEST_COUNT=53
NATIVE_FLOAT_TESTED=true
HASH_REPLAY_TESTED=true
DETERMINISTIC_FAIL_CLOSED_TESTED=true
PRODUCTION_REGISTRIES_MUTATION_TESTED=false
TEST_DATA_ACCESSED=false
TEST_LABELS_ACCESSED=false
~~~

The tests cover the legal hypothetical path only through immutable explicit
in-memory registries. They also prove that the production wrapper cannot
populate those registries and remains blocked.

## 6. Execution boundary

This task stops at implementation review:

~~~text
LIVE_PAIRING_MATERIALIZATION_PERFORMED=false
PAIRING_PACKAGE_PUBLICATION_PERFORMED=false
AUTHORITY_ISSUANCE_PERFORMED=false
LIVE_LEGAL_BACKTEST_PACKAGE_CONSTRUCTED=false
S3_C_BACKTEST_EXECUTION_PERFORMED=false
S3_METRIC_EXECUTION_PERFORMED=false
S3_D_ATTRIBUTION_EXECUTION_PERFORMED=false
BASELINE_VS_INCUMBENT_COMPARISON_EXECUTED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_EVALUATION_PERFORMED=false
TEST_ACCESS_PERFORMED=false
TEST_REMAINS_SEALED=true
S3_C_BACKTEST_EXECUTION_AUTHORIZED=true
S3_METRIC_EXECUTION_AUTHORIZED=true
S3_D_ATTRIBUTION_EXECUTION_AUTHORIZED=true
V0_3_S4_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
NEXT_GATE=COORDINATOR_LEGAL_PACKAGE_IMPLEMENTATION_REVIEW
~~~

Passing synthetic tests or implementing the package does not publish pairing
authority, resolve cutoff completeness, resolve the generic artifact
decision, execute S3-C, execute metrics, execute S3-D, unseal TEST, or
authorize S4.
