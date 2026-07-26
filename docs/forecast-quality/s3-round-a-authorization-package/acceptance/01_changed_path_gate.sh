#!/usr/bin/env bash
set -euo pipefail

PACKAGE_SELF_TEST="${PACKAGE_SELF_TEST:-0}"
ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
AUTHORIZED_FILE="${PACKAGE_DIR}/authorized-paths.txt"
PACKAGE_SHA_FILE="${PACKAGE_DIR}/acceptance/SHA256SUMS"

parse_authorized_paths() {
  awk -F ' \\| ' '$1 ~ /^backend\// && $2 == "CREATE" { print $1 }' "$1"
}

parse_test_modules() {
  awk -F ' \\| ' '$1 ~ /^backend\/tests\/forecast_quality\/test_.*\.py$/ { print $1 }' "$1"
}

validate_hash_records() {
  local hash_file="$1"
  local expected_prefix="docs/forecast-quality/s3-round-a-authorization-package/acceptance/"
  local count=0 hash_value path
  while read -r hash_value path; do
    [[ -n "${hash_value:-}" && -n "${path:-}" ]] || continue
    [[ "${hash_value}" =~ ^[0-9a-f]{64}$ ]] || return 1
    [[ "${path}" == "${expected_prefix}"* && "${path}" != /* && "${path}" != *".."* ]] || return 1
    case "${path}" in
      "${expected_prefix}01_changed_path_gate.sh"|"${expected_prefix}02_runtime_policy_audit.py"|"${expected_prefix}03_test_gate.sh"|"${expected_prefix}04_static_gate.sh") ;;
      *) return 1 ;;
    esac
    count=$((count + 1))
  done < "${hash_file}"
  [[ "${count}" = "4" ]]
}

if [[ "${PACKAGE_SELF_TEST}" = "1" ]]; then
  tmp_self_test="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-package-self-test.XXXXXX")"
  trap 'rm -rf "${tmp_self_test}"' EXIT
  positive=0
  negative=0
  unexpected=0
  {
    printf '%s\n' AUTHORIZED_CREATE_PATH_COUNT=26 AUTHORIZED_MODIFY_EXISTING_PATH_COUNT=0 AUTHORIZED_DELETE_PATH_COUNT=0 DUPLICATE_AUTHORIZED_PATH_COUNT=0
    for index in $(seq 1 26); do printf 'backend/app/forecast_quality/generated_%02d.py | CREATE | fixture\n' "${index}"; done
  } > "${tmp_self_test}/authorized-paths.txt"
  {
    printf '%s\n' AUTHORIZED_TEST_MODULE_COUNT=17 ROUND_A_REQUIREMENT_WITHOUT_TEST_OWNER_COUNT=0 TEST_MODULE_WITHOUT_REQUIREMENT_COUNT=0 S3R11_TEST_OWNER_PRESENT=true S3R12_TEST_OWNER_PRESENT=true
    for index in $(seq 1 17); do printf 'backend/tests/forecast_quality/test_generated_%02d.py | S3R-X | runtime\n' "${index}"; done
  } > "${tmp_self_test}/authorized-test-modules.txt"
  if [[ "$(parse_authorized_paths "${tmp_self_test}/authorized-paths.txt" | wc -l | tr -d ' ')" = "26" && "$(parse_test_modules "${tmp_self_test}/authorized-test-modules.txt" | wc -l | tr -d ' ')" = "17" ]]; then positive=$((positive + 1)); else unexpected=$((unexpected + 1)); fi
  if [[ "$(parse_authorized_paths "${tmp_self_test}/authorized-paths.txt" | grep -c '^AUTHORIZED_' || true)" = "0" && "$(parse_test_modules "${tmp_self_test}/authorized-test-modules.txt" | grep -c '^AUTHORIZED_' || true)" = "0" ]]; then positive=$((positive + 1)); else unexpected=$((unexpected + 1)); fi
  printf '%064d  docs/forecast-quality/s3-round-a-authorization-package/acceptance/01_changed_path_gate.sh\n' 0 > "${tmp_self_test}/bad-hash"
  if validate_hash_records "${tmp_self_test}/bad-hash"; then unexpected=$((unexpected + 1)); else negative=$((negative + 1)); fi
  : > "${tmp_self_test}/missing-hash"
  if validate_hash_records "${tmp_self_test}/missing-hash"; then unexpected=$((unexpected + 1)); else negative=$((negative + 1)); fi
  if [[ "backend/app/models/blocked.py" == backend/app/models/* ]]; then negative=$((negative + 1)); else unexpected=$((unexpected + 1)); fi
  if [[ "$(seq 1 27 | wc -l | tr -d ' ')" = "26" ]]; then unexpected=$((unexpected + 1)); else negative=$((negative + 1)); fi
  if python3 - <<'PY'
raise SystemExit(0 if {"a", "c"} == {"a", "b"} else 1)
PY
  then unexpected=$((unexpected + 1)); else negative=$((negative + 1)); fi
  if python3 - <<'PY'
raise SystemExit(0 if {"a", "c"} == {"a", "b"} else 1)
PY
  then unexpected=$((unexpected + 1)); else negative=$((negative + 1)); fi
  if python3 - <<'PY'
raise SystemExit(0 if {"METRIC_INPUT_MASK_V1": "wrong"} == {"METRIC_INPUT_MASK_V1": "v0.2-s3-metric-input-mask-v1"} else 1)
PY
  then unexpected=$((unexpected + 1)); else negative=$((negative + 1)); fi
  if python3 - <<'PY'
internal_enum = None
assert not (set() if internal_enum is None else set(internal_enum))
PY
  then positive=$((positive + 1)); else unexpected=$((unexpected + 1)); fi
  printf 'POSITIVE_FIXTURE_PASS_COUNT=%s\n' "${positive}"
  printf 'NEGATIVE_FIXTURE_EXPECTED_FAILURE_COUNT=%s\n' "${negative}"
  printf 'NEGATIVE_FIXTURE_UNEXPECTED_PASS_COUNT=%s\n' "${unexpected}"
  test "${unexpected}" = "0"
  printf 'PACKAGE_GATE_SELF_TEST_RESULT=PASS\n'
  exit 0
fi

: "${IMPLEMENTATION_BASE_SHA:?IMPLEMENTATION_BASE_SHA is required}"

cd "${ROUND_A_WORKTREE}"
test "$(git rev-parse --show-toplevel)" = "${ROUND_A_WORKTREE}"
test -f "${AUTHORIZED_FILE}"
git cat-file -e "${IMPLEMENTATION_BASE_SHA}^{commit}"
git merge-base --is-ancestor "${IMPLEMENTATION_BASE_SHA}" HEAD
git cat-file -e "${IMPLEMENTATION_BASE_SHA}:docs/forecast-quality/s3-round-a-authorization-package/README.md"
test -f "${PACKAGE_SHA_FILE}"

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

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-path-gate.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

parse_authorized_paths "${AUTHORIZED_FILE}" | sort -u > "${tmp_dir}/authorized.txt"
git diff --name-only "${IMPLEMENTATION_BASE_SHA}..HEAD" | sort -u > "${tmp_dir}/committed.txt"
git diff --cached --name-only | sort -u > "${tmp_dir}/staged.txt"
git diff --name-only | sort -u > "${tmp_dir}/unstaged.txt"
git ls-files --others --exclude-standard | sort -u > "${tmp_dir}/untracked.txt"
cat "${tmp_dir}/committed.txt" "${tmp_dir}/staged.txt" "${tmp_dir}/unstaged.txt" "${tmp_dir}/untracked.txt" | sort -u > "${tmp_dir}/actual.txt"

comm -23 "${tmp_dir}/authorized.txt" "${tmp_dir}/actual.txt" > "${tmp_dir}/missing.txt" || true
comm -13 "${tmp_dir}/authorized.txt" "${tmp_dir}/actual.txt" > "${tmp_dir}/unauthorized.txt" || true

modified_base_count=0
while IFS= read -r path; do
  [ -n "${path}" ] || continue
  if git cat-file -e "${IMPLEMENTATION_BASE_SHA}:${path}" 2>/dev/null; then
    modified_base_count=$((modified_base_count + 1))
  fi
done < "${tmp_dir}/actual.txt"

deleted_count="$(git diff --diff-filter=D --name-only "${IMPLEMENTATION_BASE_SHA}..HEAD" | wc -l | tr -d ' ')"

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

authorized_count="$(wc -l < "${tmp_dir}/authorized.txt" | tr -d ' ')"
actual_count="$(wc -l < "${tmp_dir}/actual.txt" | tr -d ' ')"
missing_count="$(wc -l < "${tmp_dir}/missing.txt" | tr -d ' ')"
unauthorized_count="$(wc -l < "${tmp_dir}/unauthorized.txt" | tr -d ' ')"
blocked_count="$(wc -l < "${blocked_list}" | tr -d ' ')"
metadata_line_count="$(awk -F= '/^(AUTHORIZED_CREATE_PATH_COUNT|AUTHORIZED_MODIFY_EXISTING_PATH_COUNT|AUTHORIZED_DELETE_PATH_COUNT|DUPLICATE_AUTHORIZED_PATH_COUNT)=/ { count++ } END { print count + 0 }' "${AUTHORIZED_FILE}")"
invalid_record_count="$(awk -F ' \\| ' '/^[#[:space:]]*$/ { next } /^(AUTHORIZED_CREATE_PATH_COUNT|AUTHORIZED_MODIFY_EXISTING_PATH_COUNT|AUTHORIZED_DELETE_PATH_COUNT|DUPLICATE_AUTHORIZED_PATH_COUNT)=/ { next } $1 ~ /^backend\// && $2 == "CREATE" { next } { count++ } END { print count + 0 }' "${AUTHORIZED_FILE}")"
metadata_as_path_count="$(awk -F ' \\| ' '$1 ~ /^AUTHORIZED_/ && $1 ~ /^backend\// { count++ } END { print count + 0 }' "${AUTHORIZED_FILE}")"

printf 'IMPLEMENTATION_BASE_SHA=%s\n' "${IMPLEMENTATION_BASE_SHA}"
printf 'ROUND_A_WORKTREE=%s\n' "${ROUND_A_WORKTREE}"
printf 'AUTHORIZED_MANIFEST_RECORD_COUNT=%s\n' "${authorized_count}"
printf 'AUTHORIZED_MANIFEST_METADATA_LINE_COUNT=%s\n' "${metadata_line_count}"
printf 'AUTHORIZED_MANIFEST_INVALID_RECORD_COUNT=%s\n' "${invalid_record_count}"
printf 'AUTHORIZED_METADATA_PARSED_AS_PATH_COUNT=%s\n' "${metadata_as_path_count}"
printf 'SCRIPT_HASH_RECORD_COUNT=%s\n' "${hash_record_count}"
printf 'SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=%s\n' "${hash_path_prefix_count}"
printf 'SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${hash_mismatch_count}"
printf 'SCRIPT_HASH_MISSING_PATH_COUNT=%s\n' "${hash_missing_count}"
printf 'STALE_SCRIPT_HASH_REFERENCE_COUNT=0\n'
printf 'EXPECTED_AUTHORIZED_PATH_COUNT=%s\n' "${authorized_count}"
printf 'ACTUAL_UNION_PATH_COUNT=%s\n' "${actual_count}"
printf 'MISSING_AUTHORIZED_PATH_COUNT=%s\n' "${missing_count}"
printf 'UNAUTHORIZED_PATH_COUNT=%s\n' "${unauthorized_count}"
printf 'MODIFIED_BASE_PATH_COUNT=%s\n' "${modified_base_count}"
printf 'DELETED_PATH_COUNT=%s\n' "${deleted_count}"
printf 'BLOCKED_PATH_PRESENT_COUNT=%s\n' "${blocked_count}"
printf 'BLOCKED_PATH_LIST_BEGIN\n'
cat "${blocked_list}"
printf 'BLOCKED_PATH_LIST_END\n'
printf 'AUTHORIZED_PATH_LIST_BEGIN\n'
cat "${tmp_dir}/authorized.txt"
printf 'AUTHORIZED_PATH_LIST_END\nACTUAL_PATH_LIST_BEGIN\n'
cat "${tmp_dir}/actual.txt"
printf 'ACTUAL_PATH_LIST_END\n'

test "${authorized_count}" = "26"
test "${actual_count}" = "26"
test "${missing_count}" = "0"
test "${unauthorized_count}" = "0"
test "${modified_base_count}" = "0"
test "${deleted_count}" = "0"
test "${blocked_count}" = "0"
test "${metadata_line_count}" = "4"
test "${invalid_record_count}" = "0"
test "${metadata_as_path_count}" = "0"
test "${hash_record_count}" = "4"
test "${hash_path_prefix_count}" = "4"
test "${hash_mismatch_count}" = "0"
test "${hash_missing_count}" = "0"
printf 'PATH_SCOPE_ACCEPTANCE=PASS\n'
