#!/usr/bin/env bash
set -euo pipefail

: "${IMPLEMENTATION_BASE_SHA:?IMPLEMENTATION_BASE_SHA is required}"
ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
AUTHORIZED_FILE="${PACKAGE_DIR}/authorized-paths.txt"
PACKAGE_SHA_FILE="${PACKAGE_DIR}/acceptance/SHA256SUMS"

cd "${ROUND_A_WORKTREE}"
test "$(git rev-parse --show-toplevel)" = "${ROUND_A_WORKTREE}"
test -f "${AUTHORIZED_FILE}"
git cat-file -e "${IMPLEMENTATION_BASE_SHA}^{commit}"
git merge-base --is-ancestor "${IMPLEMENTATION_BASE_SHA}" HEAD
git cat-file -e "${IMPLEMENTATION_BASE_SHA}:docs/forecast-quality/s3-round-a-authorization-package/README.md"
test -f "${PACKAGE_SHA_FILE}"

while read -r expected_hash relative_path; do
  [ -n "${expected_hash:-}" ] || continue
  [ -n "${relative_path:-}" ] || continue
  actual_hash="$(git show "${IMPLEMENTATION_BASE_SHA}:${relative_path}" | sha256sum | awk '{print $1}')"
  test "${actual_hash}" = "${expected_hash}"
done < "${PACKAGE_SHA_FILE}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-path-gate.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

awk -F ' \\| ' '/^[^#[:space:]]/ {print $1}' "${AUTHORIZED_FILE}" | sort -u > "${tmp_dir}/authorized.txt"
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

printf 'IMPLEMENTATION_BASE_SHA=%s\n' "${IMPLEMENTATION_BASE_SHA}"
printf 'ROUND_A_WORKTREE=%s\n' "${ROUND_A_WORKTREE}"
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
printf 'PATH_SCOPE_ACCEPTANCE=PASS\n'
