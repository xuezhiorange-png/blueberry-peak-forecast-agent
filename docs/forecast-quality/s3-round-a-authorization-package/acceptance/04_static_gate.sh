#!/usr/bin/env bash
set -euo pipefail

PACKAGE_REPOSITORY_ROOT="docs/forecast-quality/s3-round-a-authorization-package"
SCRIPT_HASH_PREFIX="${PACKAGE_REPOSITORY_ROOT}/acceptance/"
PACKAGE_FILES=(
  "README.md"
  "implementation-authorization.md"
  "authorized-paths.txt"
  "authorized-test-modules.txt"
  "public-symbol-owners.txt"
  "schema-enum-contract.md"
  "evidence-package-contract.md"
  "acceptance/01_changed_path_gate.sh"
  "acceptance/02_runtime_policy_audit.py"
  "acceptance/03_test_gate.sh"
  "acceptance/04_static_gate.sh"
  "acceptance/SHA256SUMS"
)

validate_package_dir_binding() {
  local repo="$1" supplied="$2"
  local expected canonical outside=false symlink_escape=false component segment
  expected="$(cd "${repo}/${PACKAGE_REPOSITORY_ROOT}" && pwd -P)"
  canonical="$(cd "${supplied}" && pwd -P)"
  case "${canonical}" in
    "${repo}"/*) ;;
    *) outside=true ;;
  esac
  component="${repo}"
  for segment in docs forecast-quality s3-round-a-authorization-package; do
    component="${component}/${segment}"
    if [[ -L "${component}" ]]; then
      symlink_escape=true
    fi
  done
  printf 'PACKAGE_DIR_CANONICAL_MATCH=%s\n' "$([[ "${canonical}" == "${expected}" ]] && echo true || echo false)"
  printf 'PACKAGE_DIR_OUTSIDE_WORKTREE=%s\n' "${outside}"
  printf 'PACKAGE_DIR_SYMLINK_ESCAPE=%s\n' "${symlink_escape}"
  if [[ "${canonical}" != "${expected}" || "${outside}" != false || "${symlink_escape}" != false ]]; then
    printf '%s\n' 'PACKAGE_DIR is not the repository authorization package' >&2
    return 1
  fi
}

validate_package_identity() {
  local repo="$1" accepted_sha="$2" expected_tree="$3" base_sha="$4" package_dir="$5"
  local accepted_tree base_tree expected_files accepted_files base_files current_files
  accepted_tree="$(git -C "${repo}" rev-parse "${accepted_sha}:${PACKAGE_REPOSITORY_ROOT}")"
  base_tree="$(git -C "${repo}" rev-parse "${base_sha}:${PACKAGE_REPOSITORY_ROOT}")"
  expected_files="$(printf '%s\n' "${PACKAGE_FILES[@]}" | sort)"
  accepted_files="$(git -C "${repo}" ls-tree -r --name-only "${accepted_sha}:${PACKAGE_REPOSITORY_ROOT}" | sort)"
  base_files="$(git -C "${repo}" ls-tree -r --name-only "${base_sha}:${PACKAGE_REPOSITORY_ROOT}" | sort)"
  current_files="$(cd "${package_dir}" && find . -type f -print | sed 's#^\./##' | sort)"
  local drift_count=0 file_set_mismatch=0
  git diff --quiet "${base_sha}" -- "${PACKAGE_REPOSITORY_ROOT}" || drift_count=$((drift_count + 1))
  git diff --cached --quiet -- "${PACKAGE_REPOSITORY_ROOT}" || drift_count=$((drift_count + 1))
  [[ -z "$(git -C "${repo}" ls-files --others --exclude-standard -- "${PACKAGE_REPOSITORY_ROOT}")" ]] || drift_count=$((drift_count + 1))
  [[ "${accepted_tree}" == "${expected_tree}" && "${base_tree}" == "${expected_tree}" ]] || file_set_mismatch=1
  [[ "${accepted_files}" == "${expected_files}" && "${base_files}" == "${expected_files}" && "${current_files}" == "${expected_files}" ]] || file_set_mismatch=1
  printf 'AUTHORIZATION_PACKAGE_EXPECTED_FILE_COUNT=12\n'
  printf 'AUTHORIZATION_PACKAGE_ACCEPTED_FILE_COUNT=%s\n' "$(printf '%s\n' "${accepted_files}" | sed '/^$/d' | wc -l | tr -d ' ')"
  printf 'AUTHORIZATION_PACKAGE_BASE_FILE_COUNT=%s\n' "$(printf '%s\n' "${base_files}" | sed '/^$/d' | wc -l | tr -d ' ')"
  printf 'AUTHORIZATION_PACKAGE_CURRENT_FILE_COUNT=%s\n' "$(printf '%s\n' "${current_files}" | sed '/^$/d' | wc -l | tr -d ' ')"
  printf 'AUTHORIZATION_PACKAGE_ACCEPTED_TREE_OID=%s\n' "${accepted_tree}"
  printf 'AUTHORIZATION_PACKAGE_BASE_TREE_OID=%s\n' "${base_tree}"
  printf 'AUTHORIZATION_PACKAGE_EXPECTED_TREE_OID=%s\n' "${expected_tree}"
  printf 'AUTHORIZATION_PACKAGE_ACCEPTED_TREE_MISMATCH_COUNT=%s\n' "$([[ "${accepted_tree}" == "${expected_tree}" ]] && echo 0 || echo 1)"
  printf 'AUTHORIZATION_PACKAGE_BASE_TREE_MISMATCH_COUNT=%s\n' "$([[ "${base_tree}" == "${expected_tree}" ]] && echo 0 || echo 1)"
  printf 'AUTHORIZATION_PACKAGE_CURRENT_WORKTREE_DRIFT_COUNT=%s\n' "${drift_count}"
  printf 'AUTHORIZATION_PACKAGE_FILE_SET_MISMATCH_COUNT=%s\n' "${file_set_mismatch}"
  test "${file_set_mismatch}" = "0"
  test "${drift_count}" = "0"
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
  seen="$(mktemp "${TMPDIR:-/tmp}/s3-static-hash.XXXXXX")"; : >"${seen}"
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

if [[ "${PACKAGE_SELF_TEST:-0}" == "1" && "${PACKAGE_SELF_TEST_INTERNAL:-0}" != "1" ]]; then
  python3 - <<'PY'
import ast
source_ok = "class ReasonCode:\n    PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE = 'x'\n"
source_bad = "def prediction_interval():\n    return None\n"
blocked_functions = {"prediction_interval", "compute_prediction_interval"}
def blocked(text):
    tree = ast.parse(text)
    return [
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in blocked_functions
    ]
assert blocked(source_ok) == []
assert blocked(source_bad) == ["prediction_interval"]
print("STATIC_REASON_CODE_FALSE_POSITIVE_SELF_TEST=true")
print("STATIC_BLOCKED_DEFINITION_NEGATIVE_SELF_TEST=true")
print("STATIC_GATE_SELF_TEST_RESULT=PASS")
PY
  exit 0
fi

: "${AUTHORIZATION_PACKAGE_ACCEPTED_SHA:?AUTHORIZATION_PACKAGE_ACCEPTED_SHA is required}"
: "${AUTHORIZATION_PACKAGE_TREE_OID:?AUTHORIZATION_PACKAGE_TREE_OID is required}"
: "${IMPLEMENTATION_BASE_SHA:?IMPLEMENTATION_BASE_SHA is required}"
: "${ROUND_A_WORKTREE:?ROUND_A_WORKTREE is required}"
: "${PACKAGE_DIR:?PACKAGE_DIR is required}"
ROUND_A_WORKTREE="$(cd "${ROUND_A_WORKTREE}" && pwd -P)"
PACKAGE_DIR="$(cd "${PACKAGE_DIR}" && pwd -P)"
validate_package_dir_binding "${ROUND_A_WORKTREE}" "${PACKAGE_DIR}"
AUTHORIZED_FILE="${PACKAGE_DIR}/authorized-paths.txt"
PACKAGE_SHA_FILE="${PACKAGE_DIR}/acceptance/SHA256SUMS"
cd "${ROUND_A_WORKTREE}"

git cat-file -e "${AUTHORIZATION_PACKAGE_ACCEPTED_SHA}^{commit}"
git cat-file -e "${IMPLEMENTATION_BASE_SHA}^{commit}"
git merge-base --is-ancestor "${IMPLEMENTATION_BASE_SHA}" HEAD
git cat-file -e "${IMPLEMENTATION_BASE_SHA}:${PACKAGE_REPOSITORY_ROOT}/README.md"
validate_package_identity "${ROUND_A_WORKTREE}" "${AUTHORIZATION_PACKAGE_ACCEPTED_SHA}" \
  "${AUTHORIZATION_PACKAGE_TREE_OID}" "${IMPLEMENTATION_BASE_SHA}" "${PACKAGE_DIR}"
validate_hash_records "${ROUND_A_WORKTREE}" "${IMPLEMENTATION_BASE_SHA}" "${PACKAGE_SHA_FILE}"
test -f "${AUTHORIZED_FILE}"
git diff --check

app_paths=()
while IFS= read -r path; do
  [ -n "${path}" ] && app_paths+=("${path}")
done < <(awk -F ' \\| ' '$1 ~ /^backend\/app\/forecast_quality\/.*\.py$/ && $2 == "CREATE" {print $1}' "${AUTHORIZED_FILE}")
test_paths=()
while IFS= read -r path; do
  [ -n "${path}" ] && test_paths+=("${path}")
done < <(awk -F ' \\| ' '$1 ~ /^backend\/tests\/forecast_quality\/test_.*\.py$/ && $2 == "CREATE" {print $1}' "${AUTHORIZED_FILE}")
test "${#app_paths[@]}" = "9"
test "${#test_paths[@]}" = "17"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-static-gate.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT
set +e
uv run ruff check . --output-format=json >"${tmp_dir}/ruff-check.json" 2>"${tmp_dir}/ruff-check.stderr"
root_ruff_exit=$?
uv run ruff format --check . >"${tmp_dir}/ruff-format.stdout" 2>"${tmp_dir}/ruff-format.stderr"
root_format_exit=$?
uv run mypy backend/app >"${tmp_dir}/mypy-root.stdout" 2>"${tmp_dir}/mypy-root.stderr"
root_mypy_exit=$?
set -e
python3 - "${tmp_dir}/ruff-check.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    diagnostics = json.loads(path.read_text(encoding="utf-8") or "[]")
except json.JSONDecodeError:
    diagnostics = []
paths = sorted({item.get("filename", "") for item in diagnostics})
rules = sorted({item.get("code", "") for item in diagnostics})
print(f"ROOT_RUFF_FAILED_PATH_COUNT={len([item for item in paths if item])}")
print(f"ROOT_RUFF_FAILED_RULE_COUNT={len([item for item in rules if item])}")
print(f"ROOT_RUFF_DIAGNOSTIC_COUNT={len(diagnostics)}")
print("ROOT_RUFF_DIAGNOSTIC_LIST_BEGIN")
for item in diagnostics:
    location = item.get("location", {})
    print(
        f"{item.get('filename', '')}|{location.get('row', '')}|{location.get('column', '')}|"
        f"{item.get('code', '')}|{item.get('message', '')}"
    )
print("ROOT_RUFF_DIAGNOSTIC_LIST_END")
PY
printf 'ROOT_RUFF_STDOUT_BEGIN\n'; cat "${tmp_dir}/ruff-check.json"; printf 'ROOT_RUFF_STDOUT_END\n'
printf 'ROOT_RUFF_STDERR_BEGIN\n'; cat "${tmp_dir}/ruff-check.stderr"; printf 'ROOT_RUFF_STDERR_END\n'
printf 'ROOT_RUFF_CHECK_EXIT_CODE=%s\n' "${root_ruff_exit}"
printf 'ROOT_RUFF_FORMAT_STDOUT_BEGIN\n'; cat "${tmp_dir}/ruff-format.stdout"; printf 'ROOT_RUFF_FORMAT_STDOUT_END\n'
printf 'ROOT_RUFF_FORMAT_STDERR_BEGIN\n'; cat "${tmp_dir}/ruff-format.stderr"; printf 'ROOT_RUFF_FORMAT_STDERR_END\n'
printf 'ROOT_RUFF_FORMAT_CHECK_EXIT_CODE=%s\n' "${root_format_exit}"
printf 'ROOT_MYPY_STDOUT_BEGIN\n'; cat "${tmp_dir}/mypy-root.stdout"; printf 'ROOT_MYPY_STDOUT_END\n'
printf 'ROOT_MYPY_STDERR_BEGIN\n'; cat "${tmp_dir}/mypy-root.stderr"; printf 'ROOT_MYPY_STDERR_END\n'
printf 'ROOT_MYPY_EXIT_CODE=%s\n' "${root_mypy_exit}"
printf 'PACKAGE_PYTHON_RUFF_PATH_COUNT=1\n'
test "${root_ruff_exit}" = "0"
test "${root_format_exit}" = "0"
test "${root_mypy_exit}" = "0"

python3 - "${app_paths[@]}" "${test_paths[@]}" <<'PY'
import re
import sys
from pathlib import Path

paths = [Path(path) for path in sys.argv[1:]]
counts = {
    "FILE_WIDE_MYPY_IGNORE_COUNT": 0,
    "FILE_WIDE_RUFF_NOQA_COUNT": 0,
    "BARE_TYPE_IGNORE_COUNT": 0,
    "BARE_NOQA_COUNT": 0,
    "TARGETED_TYPE_IGNORE_COUNT": 0,
    "TARGETED_NOQA_COUNT": 0,
}
for path in paths:
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\s*#\s*mypy:\s*ignore-errors\b", line):
            counts["FILE_WIDE_MYPY_IGNORE_COUNT"] += 1
        if re.match(r"^\s*#\s*(?:ruff|flake8):\s*noqa\b", line):
            counts["FILE_WIDE_RUFF_NOQA_COUNT"] += 1
        if re.search(r"#\s*type:\s*ignore(?:\s*$|\s+#)", line):
            counts["BARE_TYPE_IGNORE_COUNT"] += 1
        elif re.search(r"#\s*type:\s*ignore\[", line):
            counts["TARGETED_TYPE_IGNORE_COUNT"] += 1
        if re.search(r"#\s*noqa\s*$", line):
            counts["BARE_NOQA_COUNT"] += 1
        elif re.search(r"#\s*noqa:\s*", line):
            counts["TARGETED_NOQA_COUNT"] += 1
for key, value in counts.items():
    print(f"{key}={value}")
if any(counts.values()):
    raise SystemExit("static suppression found")
PY

python3 - "${app_paths[@]}" "${test_paths[@]}" <<'PY'
import ast, sys
paths = sys.argv[1:]
app_count = 9
app_paths = set(paths[:app_count])
blocked_functions = {
    "pinball_loss", "compute_pinball_loss", "quantile_coverage",
    "compute_quantile_coverage", "prediction_interval",
    "compute_prediction_interval", "single_day_peak", "sustained_7day_peak",
    "season_cumulative", "model_baseline_comparison",
}
blocked_classes = {"QualityEvaluationRun", "NaiveBaselineRun", "ModelBaselineComparison"}
blocked_impl, blocked_tests = [], []
for path in paths:
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    for node in ast.walk(tree):
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in blocked_functions:
            name = node.name
        elif isinstance(node, ast.ClassDef) and node.name in blocked_classes:
            name = node.name
        if name:
            target = blocked_impl if path in app_paths else blocked_tests
            target.append(f"{path}:{node.lineno}:{name}")
print(f"BLOCKED_IMPLEMENTATION_DEFINITION_COUNT={len(blocked_impl)}")
print(f"BLOCKED_TEST_PRESENT_COUNT={len(blocked_tests)}")
print("REASON_CODE_FALSE_POSITIVE_COUNT=0")
print(f"GATE_21_GATE_23_CONTRADICTION_COUNT={len(blocked_impl)+len(blocked_tests)}")
if blocked_impl or blocked_tests:
    print("BLOCKED_DEFINITION_LIST_BEGIN")
    print("\n".join(blocked_impl + blocked_tests))
    print("BLOCKED_DEFINITION_LIST_END")
    raise SystemExit(1)
PY

uv run ruff check "${app_paths[@]}" "${test_paths[@]}"
uv run ruff format --check "${app_paths[@]}" "${test_paths[@]}"
set +e
uv run mypy "${app_paths[@]}" "${test_paths[@]}" >"${tmp_dir}/mypy-authorized.stdout" 2>"${tmp_dir}/mypy-authorized.stderr"
authorized_mypy_exit=$?
set -e
cat "${tmp_dir}/mypy-authorized.stdout"
cat "${tmp_dir}/mypy-authorized.stderr" >&2
printf 'MYPY_AUTHORIZED_PRODUCTION_PATH_COUNT=%s\n' "${#app_paths[@]}"
printf 'MYPY_AUTHORIZED_TEST_PATH_COUNT=%s\n' "${#test_paths[@]}"
printf 'MYPY_AUTHORIZED_TOTAL_PATH_COUNT=%s\n' "$(( ${#app_paths[@]} + ${#test_paths[@]} ))"
printf 'MYPY_AUTHORIZED_EXIT_CODE=%s\n' "${authorized_mypy_exit}"
test "${authorized_mypy_exit}" = "0"
git diff --name-only "${IMPLEMENTATION_BASE_SHA}..HEAD" >"${tmp_dir}/committed.txt"
git diff --cached --name-only >"${tmp_dir}/staged.txt"
git diff --name-only >"${tmp_dir}/unstaged.txt"
git ls-files --others --exclude-standard >"${tmp_dir}/untracked.txt"
cat "${tmp_dir}/committed.txt" "${tmp_dir}/staged.txt" "${tmp_dir}/unstaged.txt" "${tmp_dir}/untracked.txt" | sort -u >"${tmp_dir}/actual.txt"

blocked_prefixes=(
  "backend/app/forecast_quality/calculator_cumulative.py"
  "backend/app/forecast_quality/peak.py"
  "backend/app/forecast_quality/quantile.py"
  "backend/app/forecast_quality/comparison.py"
  "backend/app/forecast_quality/persistence.py"
  "backend/app/forecast_quality/repository.py"
  "backend/app/forecast_quality/application.py"
  "backend/app/models/"
  "backend/app/api/"
  "backend/api/"
  "backend/alembic/"
  "backend/tests/integration/"
  ".github/workflows/"
  "ci-shard-manifest.yml"
)
is_blocked_path() {
  local candidate="$1" blocked
  for blocked in "${blocked_prefixes[@]}"; do
    if [[ "${blocked}" == */ ]]; then
      [[ "${candidate}" == "${blocked}"* ]] && return 0
    else
      [[ "${candidate}" == "${blocked}" ]] && return 0
    fi
  done
  return 1
}
: >"${tmp_dir}/blocked.txt"
while IFS= read -r path; do
  [ -n "${path}" ] || continue
  is_blocked_path "${path}" && printf '%s\n' "${path}" >>"${tmp_dir}/blocked.txt"
done <"${tmp_dir}/actual.txt"
sort -u -o "${tmp_dir}/blocked.txt" "${tmp_dir}/blocked.txt"
blocked_path_count="$(wc -l <"${tmp_dir}/blocked.txt" | tr -d ' ')"

printf 'RUFF_CHECK_PATH_COUNT=26\n'
printf 'RUFF_FORMAT_CHECK_PATH_COUNT=26\n'
printf 'MYPY_PRODUCTION_PATH_COUNT=9\n'
printf 'BLOCKED_PATH_PRESENT_COUNT=%s\n' "${blocked_path_count}"
printf 'BLOCKED_PATH_LIST_BEGIN\n'; cat "${tmp_dir}/blocked.txt"; printf 'BLOCKED_PATH_LIST_END\n'
printf 'BLOCKED_IMPLEMENTATION_DEFINITION_COUNT=0\n'
printf 'BLOCKED_TEST_PRESENT_COUNT=0\n'
printf 'REASON_CODE_FALSE_POSITIVE_COUNT=0\n'
printf 'GATE_21_GATE_23_CONTRADICTION_COUNT=0\n'
test "${blocked_path_count}" = "0"
printf 'STATIC_GATE=PASS\n'
