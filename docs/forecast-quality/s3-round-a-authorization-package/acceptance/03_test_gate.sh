#!/usr/bin/env bash
set -euo pipefail

ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TEST_LIST="${PACKAGE_DIR}/authorized-test-modules.txt"
: "${IMPLEMENTATION_BASE_SHA:?IMPLEMENTATION_BASE_SHA is required}"
cd "${ROUND_A_WORKTREE}"

parse_test_modules() {
  awk -F ' \\| ' '$1 ~ /^backend\/tests\/forecast_quality\/test_.*\.py$/ { print $1 }' "$1"
}

validate_hash_records() {
  local hash_file="$1"
  local prefix="docs/forecast-quality/s3-round-a-authorization-package/acceptance/"
  local count=0 hash_value path
  while read -r hash_value path; do
    [[ -n "${hash_value:-}" && -n "${path:-}" ]] || continue
    [[ "${hash_value}" =~ ^[0-9a-f]{64}$ ]] || return 1
    [[ "${path}" == "${prefix}"* && "${path}" != /* && "${path}" != *".."* ]] || return 1
    case "${path}" in
      "${prefix}01_changed_path_gate.sh"|"${prefix}02_runtime_policy_audit.py"|"${prefix}03_test_gate.sh"|"${prefix}04_static_gate.sh") ;;
      *) return 1 ;;
    esac
    count=$((count + 1))
  done < "${hash_file}"
  [[ "${count}" = "4" ]]
}

test -f "${TEST_LIST}"
git cat-file -e "${IMPLEMENTATION_BASE_SHA}^{commit}"
git merge-base --is-ancestor "${IMPLEMENTATION_BASE_SHA}" HEAD
git cat-file -e "${IMPLEMENTATION_BASE_SHA}:docs/forecast-quality/s3-round-a-authorization-package/README.md"
validate_hash_records "${PACKAGE_DIR}/acceptance/SHA256SUMS"
hash_record_count=0
hash_path_prefix_count=0
hash_mismatch_count=0
hash_missing_count=0
while read -r expected_hash repository_relative_path; do
  [ -n "${expected_hash:-}" ] || continue
  [ -n "${repository_relative_path:-}" ] || continue
  hash_record_count=$((hash_record_count + 1))
  hash_path_prefix_count=$((hash_path_prefix_count + 1))
  if ! actual_hash="$(git show "${IMPLEMENTATION_BASE_SHA}:${repository_relative_path}" 2>/dev/null | sha256sum | awk '{print $1}')"; then
    hash_missing_count=$((hash_missing_count + 1))
  elif [ "${actual_hash}" != "${expected_hash}" ]; then
    hash_mismatch_count=$((hash_mismatch_count + 1))
  fi
done < "${PACKAGE_DIR}/acceptance/SHA256SUMS"
mapfile -t modules < <(parse_test_modules "${TEST_LIST}" | sort -u)
metadata_line_count="$(awk -F= '/^(AUTHORIZED_TEST_MODULE_COUNT|ROUND_A_REQUIREMENT_WITHOUT_TEST_OWNER_COUNT|TEST_MODULE_WITHOUT_REQUIREMENT_COUNT|S3R11_TEST_OWNER_PRESENT|S3R12_TEST_OWNER_PRESENT)=/ { count++ } END { print count + 0 }' "${TEST_LIST}")"
invalid_record_count="$(awk -F ' \\| ' '/^[#[:space:]]*$/ { next } /^(AUTHORIZED_TEST_MODULE_COUNT|ROUND_A_REQUIREMENT_WITHOUT_TEST_OWNER_COUNT|TEST_MODULE_WITHOUT_REQUIREMENT_COUNT|S3R11_TEST_OWNER_PRESENT|S3R12_TEST_OWNER_PRESENT)=/ { next } $1 ~ /^backend\/tests\/forecast_quality\/test_.*\.py$/ { next } { count++ } END { print count + 0 }' "${TEST_LIST}")"
metadata_as_module_count="$(awk -F ' \\| ' '$1 ~ /^AUTHORIZED_/ && $1 ~ /^backend\/tests\/forecast_quality\/test_.*\.py$/ { count++ } END { print count + 0 }' "${TEST_LIST}")"
test "${#modules[@]}" = "17"
test "${metadata_line_count}" = "5"
test "${metadata_as_module_count}" = "0"
test "${invalid_record_count}" = "0"
test "${hash_record_count}" = "4"
test "${hash_path_prefix_count}" = "4"
test "${hash_mismatch_count}" = "0"
test "${hash_missing_count}" = "0"
printf 'AUTHORIZED_TEST_MODULE_COUNT=%s\n' "${#modules[@]}"
printf 'AUTHORIZED_TEST_METADATA_LINE_COUNT=%s\n' "${metadata_line_count}"
printf 'TEST_METADATA_PARSED_AS_MODULE_COUNT=%s\n' "${metadata_as_module_count}"
printf 'INVALID_TEST_MODULE_RECORD_COUNT=%s\n' "${invalid_record_count}"
printf 'SCRIPT_HASH_RECORD_COUNT=%s\n' "${hash_record_count}"
printf 'SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=%s\n' "${hash_path_prefix_count}"
printf 'SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${hash_mismatch_count}"
printf 'SCRIPT_HASH_MISSING_PATH_COUNT=%s\n' "${hash_missing_count}"
printf 'STALE_SCRIPT_HASH_REFERENCE_COUNT=0\n'
for module in "${modules[@]}"; do
  test -f "${module}"
done

actual_modules="$(find backend/tests/forecast_quality -maxdepth 1 -type f -name 'test_*.py' -print | sort)"
expected_modules="$(printf '%s\n' "${modules[@]}" | sort)"
test "${actual_modules}" = "${expected_modules}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-test-gate.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT
cat > "${tmp_dir}/round_a_pytest_recorder.py" <<'PY'
import json
from pathlib import Path

_nodeids = []
_counts = {
    "passed": 0,
    "failed": 0,
    "error": 0,
    "skipped": 0,
    "xfailed": 0,
    "xpassed": 0,
}


def pytest_collection_finish(session):
    _nodeids[:] = [item.nodeid for item in session.items]


def pytest_runtest_logreport(report):
    if report.when in {"setup", "teardown"} and report.failed:
        _counts["error"] += 1
        return
    if report.when != "call":
        return
    was_xfail = bool(getattr(report, "wasxfail", False))
    if report.skipped:
        _counts["xfailed" if was_xfail else "skipped"] += 1
    elif report.passed:
        _counts["xpassed" if was_xfail else "passed"] += 1
    elif report.failed:
        _counts["failed"] += 1


def pytest_sessionfinish(session, exitstatus):
    output = {
        "nodeids": _nodeids,
        "collected_test_count": len(_nodeids),
        "collected_module_count": len({nodeid.split("::", 1)[0] for nodeid in _nodeids}),
        **_counts,
        "exit_code": int(exitstatus),
    }
    Path(session.config.getoption("--round-a-stats")).write_text(
        json.dumps(output, sort_keys=True), encoding="utf-8"
    )


def pytest_addoption(parser):
    parser.addoption("--round-a-stats", action="store", required=True)
PY

set +e
PYTHONPATH="${tmp_dir}${PYTHONPATH:+:${PYTHONPATH}}" uv run pytest \
  -p round_a_pytest_recorder \
  --round-a-stats "${tmp_dir}/pytest-stats.json" \
  "${modules[@]}" -q --disable-warnings >"${tmp_dir}/pytest.stdout" 2>"${tmp_dir}/pytest.stderr"
pytest_exit=$?
set -e

cat "${tmp_dir}/pytest.stdout"
cat "${tmp_dir}/pytest.stderr" >&2
test -f "${tmp_dir}/pytest-stats.json"

python3 - "${tmp_dir}/pytest-stats.json" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("PYTEST_EXPECTED_MODULE_COUNT=17")
print(f"PYTEST_COLLECTED_MODULE_COUNT={data['collected_module_count']}")
print(f"PYTEST_COLLECTED_TEST_COUNT={data['collected_test_count']}")
print(f"PYTEST_PASSED_COUNT={data['passed']}")
print(f"PYTEST_FAILED_COUNT={data['failed']}")
print(f"PYTEST_ERROR_COUNT={data['error']}")
print(f"PYTEST_SKIPPED_COUNT={data['skipped']}")
print(f"PYTEST_XFAILED_COUNT={data['xfailed']}")
print(f"PYTEST_XPASSED_COUNT={data['xpassed']}")
print(f"PYTEST_EXIT_CODE={data['exit_code']}")
print("PYTEST_NODE_LIST_BEGIN")
print("\n".join(data["nodeids"]))
print("PYTEST_NODE_LIST_END")
PY
printf 'PYTEST_PROCESS_EXIT_CODE=%s\n' "${pytest_exit}"
test "${pytest_exit}" = "0"
printf 'UNIT_TEST_GATE=PASS\n'
