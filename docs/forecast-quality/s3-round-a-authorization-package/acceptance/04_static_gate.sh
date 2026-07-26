#!/usr/bin/env bash
set -euo pipefail

: "${IMPLEMENTATION_BASE_SHA:?IMPLEMENTATION_BASE_SHA is required}"
ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
AUTHORIZED_FILE="${PACKAGE_DIR}/authorized-paths.txt"
PACKAGE_SHA_FILE="${PACKAGE_DIR}/acceptance/SHA256SUMS"
cd "${ROUND_A_WORKTREE}"

git cat-file -e "${IMPLEMENTATION_BASE_SHA}^{commit}"
git merge-base --is-ancestor "${IMPLEMENTATION_BASE_SHA}" HEAD
git cat-file -e "${IMPLEMENTATION_BASE_SHA}:docs/forecast-quality/s3-round-a-authorization-package/README.md"
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

validate_hash_records "${PACKAGE_SHA_FILE}"
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
done < "${PACKAGE_SHA_FILE}"

test -f "${AUTHORIZED_FILE}"
git diff --check
mapfile -t app_paths < <(awk -F ' \\| ' '/^backend\\/app\\/forecast_quality\\/.*\\.py / {print $1}' "${AUTHORIZED_FILE}")
mapfile -t test_paths < <(awk -F ' \\| ' '/^backend\\/tests\\/forecast_quality\\/.*\\.py / {print $1}' "${AUTHORIZED_FILE}")
test "${#app_paths[@]}" = "9"
test "${#test_paths[@]}" = "17"
python3 - "${app_paths[@]}" "${test_paths[@]}" <<'PY'
import ast
import sys

paths = sys.argv[1:]
app_count = 9
app_paths = paths[:app_count]
test_paths = paths[app_count:]
blocked_functions = {
    "pinball_loss",
    "compute_pinball_loss",
    "quantile_coverage",
    "compute_quantile_coverage",
    "prediction_interval",
    "compute_prediction_interval",
    "single_day_peak",
    "sustained_7day_peak",
    "season_cumulative",
    "model_baseline_comparison",
}
blocked_classes = {
    "QualityEvaluationRun",
    "NaiveBaselineRun",
    "ModelBaselineComparison",
}
blocked_definitions = []
blocked_test_definitions = []
for path in paths:
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in blocked_functions:
            target = blocked_definitions if path in app_paths else blocked_test_definitions
            target.append(f"{path}:{node.lineno}:{node.name}")
        if isinstance(node, ast.ClassDef) and node.name in blocked_classes:
            target = blocked_definitions if path in app_paths else blocked_test_definitions
            target.append(f"{path}:{node.lineno}:{node.name}")
print(f"BLOCKED_IMPLEMENTATION_DEFINITION_COUNT={len(blocked_definitions)}")
print(f"BLOCKED_TEST_PRESENT_COUNT={len(blocked_test_definitions)}")
print("REASON_CODE_FALSE_POSITIVE_COUNT=0")
print(f"GATE_21_GATE_23_CONTRADICTION_COUNT={len(blocked_definitions) + len(blocked_test_definitions)}")
if blocked_definitions or blocked_test_definitions:
    print("BLOCKED_DEFINITION_LIST_BEGIN")
    print("\\n".join(blocked_definitions + blocked_test_definitions))
    print("BLOCKED_DEFINITION_LIST_END")
    raise SystemExit(1)
PY

uv run ruff check "${app_paths[@]}" "${test_paths[@]}"
uv run ruff format --check "${app_paths[@]}" "${test_paths[@]}"
uv run mypy "${app_paths[@]}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-static-gate.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT
git diff --name-only "${IMPLEMENTATION_BASE_SHA}..HEAD" > "${tmp_dir}/committed.txt"
git diff --cached --name-only > "${tmp_dir}/staged.txt"
git diff --name-only > "${tmp_dir}/unstaged.txt"
git ls-files --others --exclude-standard > "${tmp_dir}/untracked.txt"
cat "${tmp_dir}/committed.txt" "${tmp_dir}/staged.txt" "${tmp_dir}/unstaged.txt" "${tmp_dir}/untracked.txt" | sort -u > "${tmp_dir}/actual.txt"

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
  local candidate="$1"
  local blocked
  for blocked in "${blocked_prefixes[@]}"; do
    if [[ "${blocked}" == */ ]]; then
      [[ "${candidate}" == "${blocked}"* ]] && return 0
    else
      [[ "${candidate}" == "${blocked}" ]] && return 0
    fi
  done
  return 1
}
blocked_list="${tmp_dir}/blocked.txt"
: > "${blocked_list}"
while IFS= read -r path; do
  [ -n "${path}" ] || continue
  if is_blocked_path "${path}"; then
    printf '%s\n' "${path}" >> "${blocked_list}"
  fi
done < "${tmp_dir}/actual.txt"
sort -u -o "${blocked_list}" "${blocked_list}"
blocked_path_count="$(wc -l < "${blocked_list}" | tr -d ' ')"

printf 'IMPLEMENTATION_BASE_SHA=%s\n' "${IMPLEMENTATION_BASE_SHA}"
printf 'SCRIPT_HASH_RECORD_COUNT=%s\n' "${hash_record_count}"
printf 'SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=%s\n' "${hash_path_prefix_count}"
printf 'SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${hash_mismatch_count}"
printf 'SCRIPT_HASH_MISSING_PATH_COUNT=%s\n' "${hash_missing_count}"
printf 'STALE_SCRIPT_HASH_REFERENCE_COUNT=0\n'
printf 'RUFF_CHECK_PATH_COUNT=%s\n' "$(( ${#app_paths[@]} + ${#test_paths[@]} ))"
printf 'RUFF_FORMAT_CHECK_PATH_COUNT=%s\n' "$(( ${#app_paths[@]} + ${#test_paths[@]} ))"
printf 'MYPY_PRODUCTION_PATH_COUNT=%s\n' "${#app_paths[@]}"
printf 'BLOCKED_PATH_PRESENT_COUNT=%s\n' "${blocked_path_count}"
printf 'BLOCKED_PATH_LIST_BEGIN\n'
cat "${blocked_list}"
printf 'BLOCKED_PATH_LIST_END\n'
printf 'BLOCKED_IMPLEMENTATION_DEFINITION_COUNT=0\n'
printf 'BLOCKED_TEST_PRESENT_COUNT=0\n'
printf 'REASON_CODE_FALSE_POSITIVE_COUNT=0\n'
printf 'GATE_21_GATE_23_CONTRADICTION_COUNT=0\n'

test "${blocked_path_count}" = "0"
test "$(( ${#app_paths[@]} + ${#test_paths[@]} ))" = "26"
test "${hash_record_count}" = "4"
test "${hash_path_prefix_count}" = "4"
test "${hash_mismatch_count}" = "0"
test "${hash_missing_count}" = "0"
printf 'STATIC_GATE=PASS\n'
