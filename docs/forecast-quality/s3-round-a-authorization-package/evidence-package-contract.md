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
NEGATIVE_GATE_EXECUTION_COUNT=<actual>
NEGATIVE_EXPECTED_FAILURE_COUNT=<same>
NEGATIVE_UNEXPECTED_PASS_COUNT=0
PACKAGE_GATE_SELF_TEST_RESULT=PASS
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
SCRIPT_01_SHA256=464806cda8e86575c43d5b4297e97a9552c0e7109ed429076508ff7609895c3c
SCRIPT_02_SHA256=7157aaa0a302235227db2349d1f1db5e3eb635bb6bd87a8bd4ab7ddf86d6977e
SCRIPT_03_SHA256=56e24c5c5b28f9f823d1b7cbca5897a98b2c3a87655aea2a1905d56fa9626587
SCRIPT_04_SHA256=f3f6de562d397625bb5f5ea8e762211c0d3d975753a7950cad1eb97bfe14c32c
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
