# V0.2-S3 Round A Implementation Authorization Package

```text
PACKAGE_FORMAT_VERSION=v0.2-s3-round-a-authorization-package-v1
PACKAGE_SOURCE_MAIN_SHA=4d7effe82c61e5fbd6ddcc22eefa61ab74a6663d
IMPLEMENTATION_BASE_SHA=NOT_BOUND_PENDING_PACKAGE_ACCEPTANCE_AND_MERGE
IMPLEMENTATION_BASE_BOUND_BY_THIS_PR=false
IMPLEMENTATION_BASE_REQUIRES_SEPARATE_CHARLES_AUTHORIZATION=true
PACKAGE_SOURCE_SHA_IS_IMPLEMENTATION_BASE=false
SOURCE_DESIGN_HEAD_SHA=c2fb3415dfdf6cb214cb7c2f246dc442e57778a9
PR131_DESIGN_DOCUMENT_COUNT=3
S3_IMPLEMENTATION_AUTHORIZED_BY_PR131=false

ROUND_A_IS_DOMAIN_ONLY=true
ROUND_A_AUTHORIZATION_PACKAGE_COMPLETE=true
ROUND_A_AUTHORIZATION_PACKAGE_ACCEPTED=false
ROUND_A_IMPLEMENTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
ROUND_B_AUTHORIZED=false
ISSUE102_CLOSE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This Draft PR contains an authorization boundary only. It creates no Round A
production code or tests and does not modify the three PR #131 design documents.

## Scope

Round A covers public domain schemas/enums/exceptions, Decimal and canonical
helpers, seven daily P50 point metrics, deterministic six-axis breakdown cells,
cross-quantile actual registration, **subfarm-to-farm daily forecast and actual
aggregation**, prior-season analog point baseline and visibility, executable
requested P50/P80/P90 baseline outcomes, canonical payloads/hashes, and
domain-only tests.

Round A excludes complete-window cumulative metrics, peaks, quantile coverage,
pinball loss, prediction intervals, model-versus-baseline persistence,
repository/application/ORM/migration/API surfaces, integration/PostgreSQL/
concurrency tests, CI wiring, frontend work, real-data execution and Issue #102
mutation.

## Exact manifests

```text
AUTHORIZED_MANIFEST_RECORD_COUNT=26
AUTHORIZED_MANIFEST_METADATA_LINE_COUNT=4
AUTHORIZED_MANIFEST_INVALID_RECORD_COUNT=0
AUTHORIZED_METADATA_PARSED_AS_PATH_COUNT=0
AUTHORIZED_CREATE_PATH_COUNT=26

AUTHORIZED_TEST_MODULE_COUNT=17
AUTHORIZED_TEST_METADATA_LINE_COUNT=5
TEST_METADATA_PARSED_AS_MODULE_COUNT=0
INVALID_TEST_MODULE_RECORD_COUNT=0
```

Manifest parsers accept only legal repository records. Machine-readable
metadata lines can never enter path/module arrays.

## Script identity

`acceptance/SHA256SUMS` stores complete repository-relative paths. All four
gates reject absolute paths, `..`, package-root escapes, missing members,
unexpected members and byte drift.

```text
SCRIPT_01_SHA256=ea64e802fbca112217d9ab07ae3e02b91d2d062b3e4a5ba99e371d8bb1b9eef0
SCRIPT_02_SHA256=0fa3232ddeade11ef7b377d37f4ff95802e8854b525afc2c24e214e383ecb978
SCRIPT_03_SHA256=d4aba63856822fdf814adaa19a621223716b1073422abe3e81858586b9bb4fcf
SCRIPT_04_SHA256=0c44c1d7764f88c110d505e81e8dddfeefeeed25946cd2066ee93b04544e2347
SCRIPT_HASH_RECORD_COUNT=4
SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=4
SCRIPT_HASH_MISMATCH_COUNT=0
SCRIPT_HASH_MISSING_PATH_COUNT=0
STALE_SCRIPT_HASH_REFERENCE_COUNT=0
```

## Baseline and enum authority

The canonical root/cell names are copied exactly from
`s3-naive-baseline-decision.md`.

```text
BASELINE_CANONICAL_ROOT_FIELD_COUNT=26
BASELINE_CANONICAL_CELL_FIELD_COUNT=15
BASELINE_ROOT_FIELD_SET_EQUALITY=true
BASELINE_CELL_FIELD_SET_EQUALITY=true
BASELINE_CANONICAL_FIELD_NAME_DRIFT_COUNT=0

INTERNAL_REASON_CODE_PRESENT=false
INTERNAL_REASON_CODE_MEMBER_COUNT=0
PUBLIC_INTERNAL_REASON_CODE_DISJOINT=true

FROZEN_VERSION_NAME_SET_EQUALITY=true
FROZEN_VERSION_VALUE_SET_EQUALITY=true
GENERIC_VERSION_BRANCH_SHADOW_COUNT=0

S3R12_ROUND_A_STATUS=EXECUTABLE_DOMAIN_OUTCOME
S3R12_IMPLEMENTED_BY_ROUND_A=true
S3R12_RUNTIME_AUDIT_CLAIM=true
```

Requested P80/P90 baseline outcomes are `BLOCKED`, `NOT_COMPUTABLE`,
`BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED`, with a null point value.

## Package self-test

Run:

```bash
PACKAGE_SELF_TEST=1 bash docs/forecast-quality/s3-round-a-authorization-package/acceptance/01_changed_path_gate.sh
```

The self-test creates an isolated Git fixture under `/tmp`, runs positive
26-path and 17-module parser cases, proves metadata exclusion, and expects
failure for wrong/missing script hashes, a blocked path, a 27th path,
canonical root/cell drift and an invalid FrozenVersion.

```text
PACKAGE_FILE_COUNT=12
PACKAGE_FILE_SET_EXACT=true
UNAUTHORIZED_PACKAGE_PATH_COUNT=0
EMPTY_MACHINE_READABLE_FIELD_COUNT=0
CROSS_DOCUMENT_CONTRADICTION_COUNT=0
UNOWNED_PUBLIC_SYMBOL_COUNT=0
ROUND_A_REQUIREMENT_WITHOUT_TEST_OWNER_COUNT=0
DESTRUCTIVE_COMMAND_COUNT=0
NEGATIVE_FIXTURE_UNEXPECTED_PASS_COUNT=0
PACKAGE_GATE_SELF_TEST_RESULT=PASS
PACKAGE_SELF_AUDIT_RESULT=PASS
```
