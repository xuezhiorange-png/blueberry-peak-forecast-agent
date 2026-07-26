# Round A Evidence Package Contract

This contract defines evidence for a future implementation worktree. A
summary, a pytest collection result, or a `PASS` string without raw output is
not evidence.

## Required evidence members

The future evidence package must contain:

```text
identity-and-authorization
authorization-package-identity-and-sha
source-worktree-pre.txt
source-worktree-post.txt
implementation-worktree-identity.txt
authorized-paths.txt
actual-union-paths.txt
path-comparison.txt
blocked-surface-scan.txt
acceptance/01_changed_path_gate.meta.txt
acceptance/01_changed_path_gate.stdout.txt
acceptance/01_changed_path_gate.stderr.txt
acceptance/02_runtime_policy_audit.meta.txt
acceptance/02_runtime_policy_audit.stdout.txt
acceptance/02_runtime_policy_audit.stderr.txt
acceptance/03_test_gate.meta.txt
acceptance/03_test_gate.stdout.txt
acceptance/03_test_gate.stderr.txt
acceptance/04_static_gate.meta.txt
acceptance/04_static_gate.stdout.txt
acceptance/04_static_gate.stderr.txt
pytest-node-list.txt
pytest-statistics.txt
baseline-fixture-matrix.txt
season-calendar-matrix.txt
daily-metric-oracles.txt
cross-quantile-registry-audit.txt
schema-enum-audit.txt
symbol-owner-audit.txt
implementation-file-hashes.txt
archive-manifest.txt
99_final_report.md
```

The exact package format may add metadata files, but it may not omit these
semantic members or include credentials, connection strings, raw business
rows, personal data, or unrelated repository content.

## Required raw facts

Each gate record must contain:

```text
script_path
expected_script_sha256
actual_script_sha256
exact_command
working_directory
start_utc
end_utc
exit_code
stdout_path
stderr_path
```

The pytest record must contain the complete node list and exact collected,
passed, failed, error, skipped, xfailed, xpassed, and exit-code counts. The
required machine-readable keys are:

```text
PYTEST_EXPECTED_MODULE_COUNT
PYTEST_COLLECTED_MODULE_COUNT
PYTEST_COLLECTED_TEST_COUNT
PYTEST_PASSED_COUNT
PYTEST_FAILED_COUNT
PYTEST_ERROR_COUNT
PYTEST_SKIPPED_COUNT
PYTEST_XFAILED_COUNT
PYTEST_XPASSED_COUNT
PYTEST_EXIT_CODE
PYTEST_NODE_LIST_BEGIN
PYTEST_NODE_LIST_END
PYTEST_MODULE_WITH_ZERO_COLLECTED_TEST_COUNT
PYTEST_MODULE_WITH_ZERO_COLLECTED_TEST_LIST_BEGIN
PYTEST_MODULE_WITH_ZERO_COLLECTED_TEST_LIST_END
PYTEST_UNEXPECTED_COLLECTED_MODULE_COUNT
PYTEST_UNEXPECTED_COLLECTED_MODULE_LIST_BEGIN
PYTEST_UNEXPECTED_COLLECTED_MODULE_LIST_END
```

The runtime record must contain real outputs for seven daily metric oracles,
six baseline fixtures, eight calendar cases, Decimal rejection cases,
cross-quantile retention/conflicts, subfarm-to-farm forecast and actual aggregation,
canonical field sets, owner identity, and blocked-surface checks. S3R-11 and
S3R-12 must each have an executable test owner:

```text
ROUND_A_REQUIREMENT_WITHOUT_TEST_OWNER_COUNT=0
TEST_MODULE_WITHOUT_REQUIREMENT_COUNT=0
S3R11_TEST_OWNER_PRESENT=true
S3R12_TEST_OWNER_PRESENT=true
S3R12_ROUND_A_STATUS=IMPLEMENTED_DOMAIN_OUTCOME
S3R12_RUNTIME_AUDIT_CLAIM=true
INTERNAL_REASON_CODE_PRESENT=false
INTERNAL_REASON_CODE_MEMBER_COUNT=0
BASELINE_CANONICAL_ROOT_FIELD_COUNT=26
BASELINE_CANONICAL_CELL_FIELD_COUNT=15
BASELINE_ROOT_FIELD_SET_EQUALITY=true
BASELINE_CELL_FIELD_SET_EQUALITY=true
BASELINE_CANONICAL_FIELD_NAME_DRIFT_COUNT=0
FROZEN_VERSION_NAME_SET_EQUALITY=true
FROZEN_VERSION_VALUE_SET_EQUALITY=true
GENERIC_VERSION_BRANCH_SHADOW_COUNT=0
PUBLIC_SCHEMA_COUNT=11
PUBLIC_SCHEMA_FIELD_SET_EQUALITY_COUNT=11
PUBLIC_SCHEMA_FIELD_ORDER_EQUALITY_COUNT=11
PUBLIC_SCHEMA_TYPE_EQUALITY_COUNT=11
PUBLIC_SCHEMA_REQUIREDNESS_EQUALITY_COUNT=11
PUBLIC_SCHEMA_DRIFT_COUNT=0
DAILY_METRIC_VALUE_ORACLE_COUNT=7
DAILY_METRIC_STATUS_ORACLE_COUNT=7
DAILY_METRIC_REASON_ORACLE_COUNT=7
DENOMINATOR_ZERO_RUNTIME_CASE_COUNT=3
DAILY_METRIC_ORACLE_FAILURE_COUNT=0
F16_BASELINE_NO_ANALOG_FIXTURE_FIXED=true
F17_REAL_GATE_SELF_TEST=true
F18_ALL_17_MODULES_COLLECT_TESTS=true
F19_ALL_PUBLIC_SCHEMAS_EXACT=true
F20_METRIC_STATUS_REASON_ORACLES=true
```

The package gate supports `PACKAGE_SELF_TEST=1`. It creates an isolated
temporary Git repository with a package base commit, a positive 26-path
implementation commit, and adversarial clones. It invokes all four gate
scripts through their normal entrypoints. The raw self-test output must
include:

```text
POSITIVE_GATE_EXECUTION_COUNT=<actual>
POSITIVE_GATE_PASS_COUNT=<same>
NEGATIVE_GATE_EXECUTION_COUNT=41
NEGATIVE_EXPECTED_FAILURE_COUNT=41
NEGATIVE_UNEXPECTED_PASS_COUNT=0
PACKAGE_GATE_SELF_TEST_RESULT=PASS
```

```text
FINAL_CLOSEOUT_C1_PACKAGE_DIR_BOUND=true
FINAL_CLOSEOUT_C2_SOURCE_FIELDS_CORRECTED=true
SOURCE_MAP_DOCUMENT_RUNTIME_MISMATCH_COUNT=0
```

Negative gate fixtures are real, isolated failures: wrong four-entry script
hash, missing script blob, invalid metadata record, a 27th implementation
path, a blocked `backend/app/models/` path, an authorized test module that
collects zero nodes, baseline root drift, baseline cell drift, an invalid
`FrozenVersion` value, and a blocked AST implementation definition. Pure
string comparisons, fixed cardinality snippets, `bash -n`, and `py_compile`
are not positive evidence.

## Path and hash proof

The implementation path union is the normalized union of committed paths
relative to the separately authorized implementation base, staged paths, unstaged tracked paths, and
untracked paths. It must equal `authorized-paths.txt` exactly. The future
evidence package must record:

```text
EXPECTED_AUTHORIZED_PATH_COUNT=26
ACTUAL_UNION_PATH_COUNT=26
MISSING_AUTHORIZED_PATH_COUNT=0
UNAUTHORIZED_PATH_COUNT=0
MODIFIED_BASE_PATH_COUNT=0
DELETED_PATH_COUNT=0
BLOCKED_PATH_PRESENT_COUNT=0
BLOCKED_IMPLEMENTATION_DEFINITION_COUNT=0
BLOCKED_TEST_PRESENT_COUNT=0
REASON_CODE_FALSE_POSITIVE_COUNT=0
GATE_21_GATE_23_CONTRADICTION_COUNT=0
IMPLEMENTATION_FILE_HASH_COUNT=26
MISSING_HASH_PATH_COUNT=0
EXTRA_HASH_PATH_COUNT=0
HASH_RECOMPUTE_MISMATCH_COUNT=0
```

The evidence identity must record both
`PACKAGE_SOURCE_MAIN_SHA` and the separately authorized
`IMPLEMENTATION_BASE_SHA`. The package source SHA is never an implementation
diff base. All four scripts must verify that the implementation base is a
commit ancestor of the worktree, contains this package README, and contains
the exact script hashes from `acceptance/SHA256SUMS`.

Every hash uses a repository-relative path and SHA-256. A safe archive must
be inspected before extraction for absolute paths, `..` traversal,
symlinks, hardlinks, devices, sockets, FIFOs, duplicate normalized paths,
and sensitive content. It must then be extracted into a fresh temporary
directory and independently rehashed.

The package snapshot must record the exact current script hashes from
`acceptance/SHA256SUMS`, including:

```text
SCRIPT_01_SHA256=8696e46835665b174300c8243e2739f7f7eccdeb29908273321a03c309c4dae4
SCRIPT_02_SHA256=4e5eb0ee3e1f49375c24fae5b7b0b6368d472992688ea2c3c48f1dba09d06d74
SCRIPT_03_SHA256=01b1d9cd3575147a9e79921d830f1e2c7b5af80cb9a01d9f8c80fd3e44eaebbb
SCRIPT_04_SHA256=e086c481a0b0d33587ac9143c7e4fa434375edde1d291d434d3b5b29a2cba1c9
```

## Finalization boundary

The final report may claim domain-layer readiness only when all four exact
scripts pass, the path union is exact, the tests execute and pass, and the
archive recheck is clean. Even then:

```text
ROUND_A_DOMAIN_IMPLEMENTATION_ACCEPTED=false
ROUND_A_FULL_S3_ACCEPTANCE=false
ROUND_B_PERSISTENCE_REQUIRED=true
COMMIT_COUNT=0
PUSH_COUNT=0
PR_CREATION_COUNT=0
AUTHORIZE_S3_ROUND_A_COMMIT_PUSH_OPEN_PR=NO
STOPPED_AWAITING_CHARLES_COMMIT_PUSH_OPEN_PR_AUTHORIZATION=true
NO_STEP_IMPLIES_THE_NEXT=true
```

The evidence package must be delivered as an externally accessible artifact
for final acceptance. A package left only under `/tmp` is not final review
evidence. This authorization package does not authorize implementation
commit, push, PR creation, Ready, Merge, Round B, or Issue #102 mutation.

## F21-F25 evidence additions

The evidence package must preserve raw root static diagnostics and package
self-test output:

```text
ROOT_RUFF_FAILED_PATH_COUNT=0
ROOT_RUFF_FAILED_RULE_COUNT=0
ROOT_RUFF_DIAGNOSTIC_LIST_BEGIN
ROOT_RUFF_DIAGNOSTIC_LIST_END
ROOT_RUFF_CHECK_EXIT_CODE=0
ROOT_RUFF_FORMAT_CHECK_EXIT_CODE=0
ROOT_MYPY_EXIT_CODE=0
PACKAGE_PYTHON_RUFF_PATH_COUNT=1
```

The runtime evidence must include the exact six-field `BreakdownSpec`, fixed
threshold owner/value, an explicit 26/15 baseline canonical source map with 41
machine-readable field-to-source records, canonical bytes and SHA256 replay identity, MAPE mixed/all-zero status and
zero-row reason, and the complete DailyMetricResult envelope/hash audit.

```text
BreakdownSpec_FIELD_COUNT=6
REQUIRED_BREAKDOWN_AXIS_COUNT=6
MIN_COMPARABLE_ROWS_FOR_REPORTING_OWNER=backend.app.forecast_quality.breakdown
MIN_COMPARABLE_ROWS_FOR_REPORTING_VALUE=10
BASELINE_CANONICAL_REQUIRED_FIELD_NULL_COUNT=0
BASELINE_CANONICAL_SOURCE_MAP_MISMATCH_COUNT=0
BASELINE_CANONICAL_SOURCE_MAP_RECORD_COUNT=41
MAPE_ZERO_REASON_SERIALIZATION_OWNER=mape_zero_actual_reason_code
DAILY_RESULT_ENVELOPE_VALUE_MISMATCH_COUNT=0
DAILY_RESULT_COUNTER_MISMATCH_COUNT=0
DAILY_RESULT_MASK_HASH_MISMATCH_COUNT=0
DAILY_RESULT_CANONICAL_HASH_MISMATCH_COUNT=0
```

Each self-test negative fixture must record its fixture ID, gate, exact
command, expected non-zero exit class, actual exit code, and result. Round 5
requires at least thirty-seven real negative gate executions and zero
unexpected passes.

## F26-F32 evidence additions

The current evidence must include one full package-tree identity proof in
addition to the four script hashes. Every gate receives explicit
`AUTHORIZATION_PACKAGE_ACCEPTED_SHA`, `AUTHORIZATION_PACKAGE_TREE_OID`,
`IMPLEMENTATION_BASE_SHA`, `ROUND_A_WORKTREE`, and `PACKAGE_DIR` values and
verifies the exact 12-file package tree at both accepted and base commits.

```text
F26_COMPLETE_PACKAGE_TREE_IDENTITY=true
AUTHORIZATION_PACKAGE_EXPECTED_FILE_COUNT=12
AUTHORIZATION_PACKAGE_ACCEPTED_FILE_COUNT=12
AUTHORIZATION_PACKAGE_BASE_FILE_COUNT=12
AUTHORIZATION_PACKAGE_CURRENT_FILE_COUNT=12
AUTHORIZATION_PACKAGE_ACCEPTED_TREE_MISMATCH_COUNT=0
AUTHORIZATION_PACKAGE_BASE_TREE_MISMATCH_COUNT=0
AUTHORIZATION_PACKAGE_CURRENT_WORKTREE_DRIFT_COUNT=0
AUTHORIZATION_PACKAGE_FILE_SET_MISMATCH_COUNT=0

F27_CANONICAL_REAL_SOURCE_PROVENANCE=true
BASELINE_CANONICAL_BUILDER_INPUT=SOURCE_OBJECTS_ONLY
BASELINE_CANONICAL_SOURCE_MAP_RECORD_COUNT=41
BASELINE_CANONICAL_SOURCE_SCHEMA_MISSING_COUNT=0
BASELINE_CANONICAL_SOURCE_FIELD_MISSING_COUNT=0
BASELINE_CANONICAL_SOURCE_FIELD_NAME_MISMATCH_COUNT=0
BASELINE_CANONICAL_SOURCE_VALUE_MISMATCH_COUNT=0
BASELINE_CANONICAL_CALLER_INJECTION_SURFACE_COUNT=0
BASELINE_CANONICAL_PROVENANCE_MUTATION_FAILURE_COUNT=0

F28_CANONICAL_CONDITIONAL_NULLABILITY=true
BASELINE_CANONICAL_NULLABILITY_RULE_COUNT=5
BASELINE_CANONICAL_NULLABILITY_MISMATCH_COUNT=0
BASELINE_CANONICAL_NOT_COMPUTABLE_REPLAY_FAILURE_COUNT=0

F29_DAILY_RESULT_MASK_POLICY_VERSION=true
DAILY_RESULT_ENVELOPE_FIELD_COUNT=21
DAILY_RESULT_MASK_POLICY_VERSION_PRESENT=true
DAILY_RESULT_MASK_POLICY_VERSION_VALUE=v0.2-s3-metric-input-mask-v1
DAILY_RESULT_MASK_POLICY_VERSION_MISMATCH_COUNT=0

F30_ALL_COLLECTED_TESTS_MUST_PASS=true
PYTEST_MODULE_WITH_ZERO_PASSED_TEST_COUNT=0
PYTEST_NONPASSING_MODULE_COUNT=0
PYTEST_SKIPPED_COUNT=0
PYTEST_XFAILED_COUNT=0
PYTEST_XPASSED_COUNT=0
PYTEST_ALL_COLLECTED_TESTS_PASSED=true

F31_STATIC_SUPPRESSIONS_FORBIDDEN=true
FILE_WIDE_MYPY_IGNORE_COUNT=0
FILE_WIDE_RUFF_NOQA_COUNT=0
BARE_TYPE_IGNORE_COUNT=0
BARE_NOQA_COUNT=0
TARGETED_TYPE_IGNORE_COUNT=0
TARGETED_NOQA_COUNT=0

F32_SINGLE_CURRENT_STATE_BLOCK=true
CURRENT_ROOT_RUFF_FAILED_PATH_COUNT=0
CURRENT_ROOT_RUFF_DIAGNOSTIC_COUNT=0
```

The baseline source map must name an existing schema field or an explicit
frozen constant. Canonical provenance mutation cases, conditional-null replay
cases, and the complete per-module pytest statistics are raw runtime output;
summary-only assertions are not evidence.

## Round 6 gate evidence

Every gate must emit these package-directory binding facts before reading the
manifest:

```text
PACKAGE_DIR_CANONICAL_MATCH
PACKAGE_DIR_OUTSIDE_WORKTREE
PACKAGE_DIR_SYMLINK_ESCAPE
```

The runtime gate must emit executable source-map comparisons and conditional
nullability results:

```text
BASELINE_CANONICAL_SOURCE_MAP_RECORD_COUNT=41
BASELINE_CANONICAL_SOURCE_SCHEMA_MISSING_COUNT
BASELINE_CANONICAL_SOURCE_FIELD_MISSING_COUNT
BASELINE_CANONICAL_SOURCE_FIELD_NAME_MISMATCH_COUNT
BASELINE_CANONICAL_SOURCE_VALUE_MISMATCH_COUNT
BASELINE_CANONICAL_FROZEN_CONSTANT_MISMATCH_COUNT
BASELINE_CANONICAL_SOURCE_MAP_CROSS_DOCUMENT_MISMATCH_COUNT
EXPECTED_VALID_NULL_CASE_COUNT=6
ACTUAL_VALID_NULL_CASE_COUNT
VALID_NULL_CASE_FAILURE_COUNT
EXPECTED_INVALID_NULL_REJECTION_COUNT=5
ACTUAL_INVALID_NULL_REJECTION_COUNT
INVALID_NULL_UNEXPECTED_ACCEPT_COUNT
ROOT_NULLABILITY_VALIDATION
CELL_NULLABILITY_VALIDATION
```

The static gate must retain raw structured Ruff JSON and raw format/mypy
stdout and stderr, plus strict mypy coverage over every authorized file:

```text
ROOT_RUFF_DIAGNOSTIC_LIST_BEGIN
ROOT_RUFF_DIAGNOSTIC_LIST_END
ROOT_RUFF_CHECK_EXIT_CODE
ROOT_RUFF_FORMAT_CHECK_EXIT_CODE
ROOT_MYPY_EXIT_CODE
MYPY_AUTHORIZED_PRODUCTION_PATH_COUNT=9
MYPY_AUTHORIZED_TEST_PATH_COUNT=17
MYPY_AUTHORIZED_TOTAL_PATH_COUNT=26
MYPY_AUTHORIZED_EXIT_CODE
```

Each negative fixture records `fixture_id`, `gate_path`,
`expected_failure_marker`, `exact_command`, `actual_exit_code`,
`actual_failure_marker_found`, and `result`. Signature errors such as
`TypeError`, `SyntaxError`, `ImportError`, and `NameError` do not count as
semantic negative evidence. The package self-test is fixed at four positive
gate executions and 41 expected-negative gate executions.

```text
F33_PACKAGE_DIR_BOUND_TO_WORKTREE=true
F34_ALL_41_SOURCE_VALUES_COMPARED=true
F35_NULLABILITY_FAIL_CLOSED=true
F36_NEGATIVE_FIXTURE_SIGNATURES_VALID=true
F37_F27_F29_GATE_NEGATIVES_PRESENT=true
F38_MYPY_ALL_26_PATHS=true
F39_RUFF_STRUCTURED_EVIDENCE=true
POSITIVE_GATE_EXECUTION_COUNT=4
POSITIVE_GATE_PASS_COUNT=4
NEGATIVE_GATE_EXECUTION_COUNT=41
NEGATIVE_EXPECTED_FAILURE_COUNT=41
NEGATIVE_UNEXPECTED_PASS_COUNT=0
NEGATIVE_FIXTURE_WRONG_FAILURE_REASON_COUNT=0
NEGATIVE_FIXTURE_SIGNATURE_DRIFT_COUNT=0
PACKAGE_GATE_SELF_TEST_RESULT=PASS
```
