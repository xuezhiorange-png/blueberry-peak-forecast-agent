# V0.2-S3 Round A Implementation Authorization Package

```text
PACKAGE_FORMAT_VERSION=v0.2-s3-round-a-authorization-package-v1
PACKAGE_SOURCE_MAIN_SHA=4d7effe82c61e5fbd6ddcc22eefa61ab74a6663d
IMPLEMENTATION_BASE_SHA=NOT_BOUND_PENDING_PACKAGE_ACCEPTANCE_AND_MERGE
IMPLEMENTATION_BASE_BOUND_BY_THIS_PR=false
IMPLEMENTATION_BASE_REQUIRES_SEPARATE_CHARLES_AUTHORIZATION=true
PACKAGE_SOURCE_SHA_IS_IMPLEMENTATION_BASE=false
SOURCE_DESIGN_HEAD_SHA=c2fb3415dfdf6cb214cb7c2f246dc442e57778a9
PR131_MERGE_COMMIT_IS_ANCESTOR=true
PR131_DESIGN_DOCUMENT_COUNT=3
S3_IMPLEMENTATION_AUTHORIZED_BY_PR131=false

ROUND_A_IS_DOMAIN_ONLY=true
ROUND_A_POSTGRES_REQUIRED=false
ROUND_A_MIGRATION_REQUIRED=false
ROUND_A_CONCURRENCY_REQUIRED=false
ROUND_A_PUBLIC_HTTP_API=false
ROUND_A_FULL_S3_ACCEPTANCE_POSSIBLE=false

ROUND_A_AUTHORIZATION_PACKAGE_COMPLETE=true
ROUND_A_AUTHORIZATION_PACKAGE_ACCEPTED=false
ROUND_A_IMPLEMENTATION_AUTHORIZED=false
COMMIT_IMPLEMENTATION_AUTHORIZED=false
PUSH_IMPLEMENTATION_AUTHORIZED=false
OPEN_IMPLEMENTATION_PR_AUTHORIZED=false
ROUND_B_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This package is derived from the three design documents merged by PR #131:

- `docs/forecast-quality/s3-quality-metrics-contract.md`
- `docs/forecast-quality/s3-naive-baseline-decision.md`
- `docs/forecast-quality/s3-implementation-readiness-matrix.md`

It is an authorization boundary, not an implementation. It does not create
`backend/app/forecast_quality`, tests, migrations, persistence, APIs, or CI
changes. A future implementation round must use the exact-byte acceptance
scripts in `acceptance/` and must not treat this package's Draft PR, review,
Ready state, or merge as implementation authorization.

## Scope

Round A covers public domain schemas and enums, the exception hierarchy,
Decimal and canonical helpers, daily P50 point metrics, deterministic
breakdown cells, cross-quantile actual physical-row registration,
subfarm-to-farm daily forecast and actual aggregation, the prior-season analog point
baseline, baseline visibility, canonical payloads and hashes, and domain-only
unit/contract tests.

Round A excludes complete-window cumulative metrics, single-day and sustained
peak metrics, quantile coverage, pinball loss publication, prediction
intervals, model-versus-baseline comparison persistence, persistence,
repository/application/ORM/migration/API surfaces, integration/PostgreSQL/
concurrency tests, CI wiring, frontend work, real-data execution, and Issue
#102 mutation. The exclusion is proved by the path and symbol checks in the
acceptance scripts, not by adding placeholder production tokens.

## Package contents

The package root contains exactly the files listed by the package self-audit.
`authorized-paths.txt` and `authorized-test-modules.txt` are the only source
of truth for future repository CREATE paths and test modules. Every path is
repository-relative, normalized, unique, and owned by one requirement set.

The package must be reviewed and independently accepted before a separate
Round A implementation authorization is considered.

## Package self-audit snapshot

```text
PACKAGE_FILE_SET_EXACT=true
PACKAGE_FILE_COUNT=12
AUTHORIZED_PATH_COUNT=26
AUTHORIZED_TEST_MODULE_COUNT=17
PUBLIC_SYMBOL_OWNER_COUNT=35
ACCEPTANCE_SCRIPT_COUNT=4
ACCEPTANCE_SCRIPT_HASH_COUNT=4
ACCEPTANCE_SCRIPT_HASH_MISMATCH_COUNT=0
SCRIPT_01_SHA256=23433951b6fd8d83bcea043250d409ed811634009d90c15c3e702a1627b5e797
SCRIPT_02_SHA256=0fa3232ddeade11ef7b377d37f4ff95802e8854b525afc2c24e214e383ecb978
SCRIPT_03_SHA256=b03a3d527e2771bfbd5bde5d57ff278eece06ed541722c0a0732819a13b76883
SCRIPT_04_SHA256=6757d88d5f69c7a550c0a2475f96f462e3f41ba48a6dffeed844881a34eaa7eb
AUTHORIZED_MANIFEST_RECORD_COUNT=26
AUTHORIZED_MANIFEST_METADATA_LINE_COUNT=4
AUTHORIZED_MANIFEST_INVALID_RECORD_COUNT=0
AUTHORIZED_METADATA_PARSED_AS_PATH_COUNT=0
AUTHORIZED_TEST_MODULE_COUNT=17
AUTHORIZED_TEST_METADATA_LINE_COUNT=5
TEST_METADATA_PARSED_AS_MODULE_COUNT=0
INVALID_TEST_MODULE_RECORD_COUNT=0
SCRIPT_HASH_RECORD_COUNT=4
SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=4
SCRIPT_HASH_MISMATCH_COUNT=0
SCRIPT_HASH_MISSING_PATH_COUNT=0
EMPTY_MACHINE_READABLE_FIELD_COUNT=0
CROSS_DOCUMENT_CONTRADICTION_COUNT=0
UNOWNED_PUBLIC_SYMBOL_COUNT=0
ROUND_A_REQUIREMENT_WITHOUT_TEST_OWNER_COUNT=0
TEST_MODULE_WITHOUT_REQUIREMENT_COUNT=0
S3R11_TEST_OWNER_PRESENT=true
S3R12_TEST_OWNER_PRESENT=true
S3R12_ROUND_A_STATUS=IMPLEMENTED_DOMAIN_OUTCOME
S3R12_IMPLEMENTED_BY_ROUND_A=true
S3R12_RUNTIME_AUDIT_CLAIM=true
BASELINE_CANONICAL_ROOT_FIELD_COUNT=26
BASELINE_CANONICAL_CELL_FIELD_COUNT=15
BASELINE_ROOT_FIELD_SET_EQUALITY=true
BASELINE_CELL_FIELD_SET_EQUALITY=true
BASELINE_CANONICAL_FIELD_NAME_DRIFT_COUNT=0
INTERNAL_REASON_CODE_PRESENT=false
INTERNAL_REASON_CODE_MEMBER_COUNT=0
FROZEN_VERSION_NAME_SET_EQUALITY=true
FROZEN_VERSION_VALUE_SET_EQUALITY=true
GENERIC_VERSION_BRANCH_SHADOW_COUNT=0
PACKAGE_GATE_SELF_TEST_RESULT=PASS
GATE_SATISFIABILITY_CONTRADICTION_COUNT=0
STALE_SCRIPT_HASH_REFERENCE_COUNT=0
DESTRUCTIVE_COMMAND_COUNT=0
PACKAGE_SELF_AUDIT_RESULT=PASS
```
