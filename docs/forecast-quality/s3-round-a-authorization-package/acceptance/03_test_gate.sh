#!/usr/bin/env bash
set -euo pipefail

PACKAGE_REPOSITORY_ROOT="docs/forecast-quality/s3-round-a-authorization-package"
SCRIPT_HASH_PREFIX="${PACKAGE_REPOSITORY_ROOT}/acceptance/"

parse_test_manifest() {
  local manifest="$1"
  awk -F ' \\| ' '
    $1 ~ /^backend\/tests\/forecast_quality\/test_.*\.py$/ { print $1 }
  ' "${manifest}"
}

test_metadata_count() {
  grep -Ec '^[A-Z0-9_]+=.*$' "$1" || true
}

test_manifest_invalid_count() {
  awk -F ' \\| ' '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ || /^[A-Z0-9_]+=.*$/ { next }
    !($1 ~ /^backend\/tests\/forecast_quality\/test_.*\.py$/) { count++ }
    END { print count + 0 }
  ' "$1"
}

validate_hash_records() {
  local repo="$1" base_sha="$2" sha_file="$3"
  local record_count=0 prefix_count=0 mismatch_count=0 missing_count=0 stale_count=0
  local current_mismatch_count=0 base_mismatch_count=0
  local expected_paths=(
    "${SCRIPT_HASH_PREFIX}01_changed_path_gate.sh"
    "${SCRIPT_HASH_PREFIX}02_runtime_policy_audit.py"
    "${SCRIPT_HASH_PREFIX}03_test_gate.sh"
    "${SCRIPT_HASH_PREFIX}04_static_gate.sh"
  )
  local seen
  seen="$(mktemp "${TMPDIR:-/tmp}/s3-test-hash.XXXXXX")"
  : >"${seen}"
  while IFS= read -r line; do
    [ -n "${line}" ] || continue
    if [[ ! "${line}" =~ ^([0-9a-f]{64})[[:space:]][[:space:]]([^[:space:]]+)$ ]]; then
      stale_count=$((stale_count + 1)); continue
    fi
    local expected_hash="${BASH_REMATCH[1]}" repository_relative_path="${BASH_REMATCH[2]}"
    record_count=$((record_count + 1))
    if [[ "${repository_relative_path}" == "${SCRIPT_HASH_PREFIX}"* ]] \
      && [[ "${repository_relative_path}" != /* ]] \
      && [[ "${repository_relative_path}" != *"../"* ]] \
      && [[ "${repository_relative_path}" != *"/.." ]]; then
      prefix_count=$((prefix_count + 1))
    else
      stale_count=$((stale_count + 1)); continue
    fi
    printf '%s\n' "${repository_relative_path}" >>"${seen}"
    if ! git -C "${repo}" cat-file -e "${base_sha}:${repository_relative_path}" 2>/dev/null; then
      missing_count=$((missing_count + 1)); continue
    fi
    local actual_hash
    actual_hash="$(git -C "${repo}" show "${base_sha}:${repository_relative_path}" | sha256sum | awk '{print $1}')"
    if [[ "${actual_hash}" != "${expected_hash}" ]]; then
      mismatch_count=$((mismatch_count + 1)); base_mismatch_count=$((base_mismatch_count + 1))
    fi
    local current_path="${repo}/${repository_relative_path}"
    if [[ ! -f "${current_path}" ]]; then
      missing_count=$((missing_count + 1))
    elif [[ "$(sha256sum "${current_path}" | awk '{print $1}')" != "${expected_hash}" ]]; then
      mismatch_count=$((mismatch_count + 1)); current_mismatch_count=$((current_mismatch_count + 1))
    fi
  done <"${sha_file}"
  for expected_path in "${expected_paths[@]}"; do
    grep -Fxq "${expected_path}" "${seen}" || stale_count=$((stale_count + 1))
  done
  rm -f "${seen}"
  printf 'SCRIPT_HASH_RECORD_COUNT=%s\n' "${record_count}"
  printf 'SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=%s\n' "${prefix_count}"
  printf 'SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${mismatch_count}"
  printf 'SCRIPT_HASH_MISSING_PATH_COUNT=%s\n' "${missing_count}"
  printf 'CURRENT_SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${current_mismatch_count}"
  printf 'BASE_SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${base_mismatch_count}"
  printf 'STALE_SCRIPT_HASH_REFERENCE_COUNT=%s\n' "${stale_count}"
  if [[ "${record_count}" == "4" && "${prefix_count}" == "4" \
    && "${mismatch_count}" == "0" && "${missing_count}" == "0" \
    && "${stale_count}" == "0" ]]; then
    return 0
  fi
  return 1
}

run_self_test() {
  local package_dir
  package_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  local manifest="${package_dir}/authorized-test-modules.txt"
  modules=()
  while IFS= read -r module; do
    [ -n "${module}" ] && modules+=("${module}")
  done < <(parse_test_manifest "${manifest}")
  local metadata_count invalid_count metadata_parsed=0
  metadata_count="$(test_metadata_count "${manifest}")"
  invalid_count="$(test_manifest_invalid_count "${manifest}")"
  while IFS= read -r metadata; do
    [ -n "${metadata}" ] || continue
    if printf '%s\n' "${modules[@]}" | grep -Fxq "${metadata}"; then
      metadata_parsed=$((metadata_parsed + 1))
    fi
  done < <(grep -E '^[A-Z0-9_]+=.*$' "${manifest}" || true)
  test "${#modules[@]}" = "17"
  test "${metadata_count}" = "5"
  test "${invalid_count}" = "0"
  test "${metadata_parsed}" = "0"

  local bad
  bad="$(mktemp "${TMPDIR:-/tmp}/s3-test-manifest-bad.XXXXXX")"
  cp "${manifest}" "${bad}"
  printf 'not/a/test.py | runtime | fake\n' >>"${bad}"
  local bad_invalid
  bad_invalid="$(test_manifest_invalid_count "${bad}")"
  test "${bad_invalid}" = "1"
  rm -f "${bad}"

  printf 'AUTHORIZED_TEST_MODULE_COUNT=17\n'
  printf 'AUTHORIZED_TEST_MODULE_COUNT_PARSED=17\n'
  printf 'AUTHORIZED_TEST_METADATA_LINE_COUNT=5\n'
  printf 'TEST_METADATA_PARSED_AS_MODULE_COUNT=0\n'
  printf 'INVALID_TEST_MODULE_RECORD_COUNT=0\n'
  printf 'TEST_MANIFEST_NEGATIVE_EXPECTED_FAILURE_COUNT=1\n'
  printf 'TEST_MANIFEST_NEGATIVE_UNEXPECTED_PASS_COUNT=0\n'
  printf 'TEST_GATE_SELF_TEST_RESULT=PASS\n'
}

if [[ "${PACKAGE_SELF_TEST:-0}" == "1" && "${PACKAGE_SELF_TEST_INTERNAL:-0}" != "1" ]]; then
  run_self_test
  exit 0
fi

ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TEST_LIST="${PACKAGE_DIR}/authorized-test-modules.txt"
: "${IMPLEMENTATION_BASE_SHA:?IMPLEMENTATION_BASE_SHA is required}"
cd "${ROUND_A_WORKTREE}"

test -f "${TEST_LIST}"
git cat-file -e "${IMPLEMENTATION_BASE_SHA}^{commit}"
git merge-base --is-ancestor "${IMPLEMENTATION_BASE_SHA}" HEAD
git cat-file -e "${IMPLEMENTATION_BASE_SHA}:${PACKAGE_REPOSITORY_ROOT}/README.md"
validate_hash_records "${ROUND_A_WORKTREE}" "${IMPLEMENTATION_BASE_SHA}" "${PACKAGE_DIR}/acceptance/SHA256SUMS"

modules=()
while IFS= read -r module; do
  [ -n "${module}" ] && modules+=("${module}")
done < <(parse_test_manifest "${TEST_LIST}")
metadata_count="$(test_metadata_count "${TEST_LIST}")"
invalid_count="$(test_manifest_invalid_count "${TEST_LIST}")"
metadata_parsed=0
while IFS= read -r metadata; do
  [ -n "${metadata}" ] || continue
  if printf '%s\n' "${modules[@]}" | grep -Fxq "${metadata}"; then
    metadata_parsed=$((metadata_parsed + 1))
  fi
done < <(grep -E '^[A-Z0-9_]+=.*$' "${TEST_LIST}" || true)

printf 'AUTHORIZED_TEST_MODULE_COUNT=%s\n' "${#modules[@]}"
printf 'AUTHORIZED_TEST_METADATA_LINE_COUNT=%s\n' "${metadata_count}"
printf 'TEST_METADATA_PARSED_AS_MODULE_COUNT=%s\n' "${metadata_parsed}"
printf 'INVALID_TEST_MODULE_RECORD_COUNT=%s\n' "${invalid_count}"
test "${#modules[@]}" = "17"
test "${metadata_count}" = "5"
test "${metadata_parsed}" = "0"
test "${invalid_count}" = "0"

for module in "${modules[@]}"; do test -f "${module}"; done
actual_modules="$(find backend/tests/forecast_quality -maxdepth 1 -type f -name 'test_*.py' -print | sort)"
expected_modules="$(printf '%s\n' "${modules[@]}" | sort)"
test "${actual_modules}" = "${expected_modules}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-test-gate.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT
cat >"${tmp_dir}/round_a_pytest_recorder.py" <<'PY'
import json
from pathlib import Path

_nodeids = []
_counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "xfailed": 0, "xpassed": 0}

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
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_modules = {
    "backend/tests/forecast_quality/test_aggregation.py",
    "backend/tests/forecast_quality/test_actual_dedup.py",
    "backend/tests/forecast_quality/test_baseline.py",
    "backend/tests/forecast_quality/test_baseline_cold_start.py",
    "backend/tests/forecast_quality/test_baseline_visibility.py",
    "backend/tests/forecast_quality/test_blocked_surfaces.py",
    "backend/tests/forecast_quality/test_breakdown.py",
    "backend/tests/forecast_quality/test_breakdown_min.py",
    "backend/tests/forecast_quality/test_calculator_daily.py",
    "backend/tests/forecast_quality/test_canonical.py",
    "backend/tests/forecast_quality/test_decimal.py",
    "backend/tests/forecast_quality/test_dedup.py",
    "backend/tests/forecast_quality/test_mape.py",
    "backend/tests/forecast_quality/test_public_contracts.py",
    "backend/tests/forecast_quality/test_season_calendar.py",
    "backend/tests/forecast_quality/test_smape.py",
    "backend/tests/forecast_quality/test_zero_policy.py",
}
collected_modules = {nodeid.split("::", 1)[0] for nodeid in data["nodeids"]}
zero_modules = sorted(expected_modules - collected_modules)
unexpected_modules = sorted(collected_modules - expected_modules)
for key, value in (
    ("PYTEST_EXPECTED_MODULE_COUNT", 17),
    ("PYTEST_COLLECTED_MODULE_COUNT", data["collected_module_count"]),
    ("PYTEST_COLLECTED_TEST_COUNT", data["collected_test_count"]),
    ("PYTEST_PASSED_COUNT", data["passed"]),
    ("PYTEST_FAILED_COUNT", data["failed"]),
    ("PYTEST_ERROR_COUNT", data["error"]),
    ("PYTEST_SKIPPED_COUNT", data["skipped"]),
    ("PYTEST_XFAILED_COUNT", data["xfailed"]),
    ("PYTEST_XPASSED_COUNT", data["xpassed"]),
    ("PYTEST_EXIT_CODE", data["exit_code"]),
):
    print(f"{key}={value}")
print(f"PYTEST_MODULE_WITH_ZERO_COLLECTED_TEST_COUNT={len(zero_modules)}")
print(f"PYTEST_UNEXPECTED_COLLECTED_MODULE_COUNT={len(unexpected_modules)}")
print("PYTEST_MODULE_WITH_ZERO_COLLECTED_TEST_LIST_BEGIN")
print("\n".join(zero_modules))
print("PYTEST_MODULE_WITH_ZERO_COLLECTED_TEST_LIST_END")
print("PYTEST_UNEXPECTED_COLLECTED_MODULE_LIST_BEGIN")
print("\n".join(unexpected_modules))
print("PYTEST_UNEXPECTED_COLLECTED_MODULE_LIST_END")
print("PYTEST_NODE_LIST_BEGIN")
print("\n".join(data["nodeids"]))
print("PYTEST_NODE_LIST_END")
PY
printf 'PYTEST_PROCESS_EXIT_CODE=%s\n' "${pytest_exit}"
test "${pytest_exit}" = "0"
python3 - "${tmp_dir}/pytest-stats.json" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "backend/tests/forecast_quality/test_aggregation.py",
    "backend/tests/forecast_quality/test_actual_dedup.py",
    "backend/tests/forecast_quality/test_baseline.py",
    "backend/tests/forecast_quality/test_baseline_cold_start.py",
    "backend/tests/forecast_quality/test_baseline_visibility.py",
    "backend/tests/forecast_quality/test_blocked_surfaces.py",
    "backend/tests/forecast_quality/test_breakdown.py",
    "backend/tests/forecast_quality/test_breakdown_min.py",
    "backend/tests/forecast_quality/test_calculator_daily.py",
    "backend/tests/forecast_quality/test_canonical.py",
    "backend/tests/forecast_quality/test_decimal.py",
    "backend/tests/forecast_quality/test_dedup.py",
    "backend/tests/forecast_quality/test_mape.py",
    "backend/tests/forecast_quality/test_public_contracts.py",
    "backend/tests/forecast_quality/test_season_calendar.py",
    "backend/tests/forecast_quality/test_smape.py",
    "backend/tests/forecast_quality/test_zero_policy.py",
}
actual = {nodeid.split("::", 1)[0] for nodeid in data["nodeids"]}
if expected != actual:
    raise SystemExit(f"pytest module set mismatch: missing={sorted(expected-actual)} unexpected={sorted(actual-expected)}")
if len(expected - actual) != 0 or len(actual - expected) != 0:
    raise SystemExit("pytest module coverage mismatch")
PY
test "$(python3 - "${tmp_dir}/pytest-stats.json" <<'PY'
import json, sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected={
"backend/tests/forecast_quality/test_aggregation.py","backend/tests/forecast_quality/test_actual_dedup.py","backend/tests/forecast_quality/test_baseline.py","backend/tests/forecast_quality/test_baseline_cold_start.py","backend/tests/forecast_quality/test_baseline_visibility.py","backend/tests/forecast_quality/test_blocked_surfaces.py","backend/tests/forecast_quality/test_breakdown.py","backend/tests/forecast_quality/test_breakdown_min.py","backend/tests/forecast_quality/test_calculator_daily.py","backend/tests/forecast_quality/test_canonical.py","backend/tests/forecast_quality/test_decimal.py","backend/tests/forecast_quality/test_dedup.py","backend/tests/forecast_quality/test_mape.py","backend/tests/forecast_quality/test_public_contracts.py","backend/tests/forecast_quality/test_season_calendar.py","backend/tests/forecast_quality/test_smape.py","backend/tests/forecast_quality/test_zero_policy.py"}
actual={x.split("::",1)[0] for x in data["nodeids"]}
print("0" if expected == actual else "1")
PY
)" = "0"
printf 'UNIT_TEST_GATE=PASS\n'
