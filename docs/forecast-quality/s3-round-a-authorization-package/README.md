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
subfarm-to-farm daily actual aggregation, the prior-season analog point
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
EMPTY_MACHINE_READABLE_FIELD_COUNT=0
CROSS_DOCUMENT_CONTRADICTION_COUNT=0
UNOWNED_PUBLIC_SYMBOL_COUNT=0
ROUND_A_REQUIREMENT_WITHOUT_TEST_OWNER_COUNT=0
TEST_MODULE_WITHOUT_REQUIREMENT_COUNT=0
S3R11_TEST_OWNER_PRESENT=true
S3R12_TEST_OWNER_PRESENT=true
GATE_SATISFIABILITY_CONTRADICTION_COUNT=0
STALE_SCRIPT_HASH_REFERENCE_COUNT=0
DESTRUCTIVE_COMMAND_COUNT=0
PACKAGE_SELF_AUDIT_RESULT=PASS
```
