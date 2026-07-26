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
runtime record must contain real outputs for seven daily metric oracles, six
baseline fixtures, eight calendar cases, Decimal rejection cases,
cross-quantile retention/conflicts, canonical field sets, owner identity, and
blocked-surface checks.

## Path and hash proof

The implementation path union is the normalized union of committed paths
relative to the source base, staged paths, unstaged tracked paths, and
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
IMPLEMENTATION_FILE_HASH_COUNT=26
MISSING_HASH_PATH_COUNT=0
EXTRA_HASH_PATH_COUNT=0
HASH_RECOMPUTE_MISMATCH_COUNT=0
```

Every hash uses a repository-relative path and SHA-256. A safe archive must
be inspected before extraction for absolute paths, `..` traversal,
symlinks, hardlinks, devices, sockets, FIFOs, duplicate normalized paths,
and sensitive content. It must then be extracted into a fresh temporary
directory and independently rehashed.

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
