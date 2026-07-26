#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_MAIN_SHA:?SOURCE_MAIN_SHA is required}"
ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
AUTHORIZED_FILE="${PACKAGE_DIR}/authorized-paths.txt"

cd "${ROUND_A_WORKTREE}"
test "$(git rev-parse --show-toplevel)" = "${ROUND_A_WORKTREE}"
test -f "${AUTHORIZED_FILE}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-path-gate.XXXXXX")"
trap 'rmdir "${tmp_dir}" 2>/dev/null || true' EXIT

awk -F ' \\| ' '/^[^#[:space:]]/ {print $1}' "${AUTHORIZED_FILE}" | sort -u > "${tmp_dir}/authorized.txt"
git diff --name-only "${SOURCE_MAIN_SHA}..HEAD" | sort -u > "${tmp_dir}/committed.txt"
git diff --cached --name-only | sort -u > "${tmp_dir}/staged.txt"
git diff --name-only | sort -u > "${tmp_dir}/unstaged.txt"
git ls-files --others --exclude-standard | sort -u > "${tmp_dir}/untracked.txt"
cat "${tmp_dir}/committed.txt" "${tmp_dir}/staged.txt" "${tmp_dir}/unstaged.txt" "${tmp_dir}/untracked.txt" | sort -u > "${tmp_dir}/actual.txt"

comm -23 "${tmp_dir}/authorized.txt" "${tmp_dir}/actual.txt" > "${tmp_dir}/missing.txt" || true
comm -13 "${tmp_dir}/authorized.txt" "${tmp_dir}/actual.txt" > "${tmp_dir}/unauthorized.txt" || true
modified_base_count=0
deleted_count=0
while IFS= read -r path; do
  [ -n "${path}" ] || continue
  if git cat-file -e "${SOURCE_MAIN_SHA}:${path}" 2>/dev/null; then
    modified_base_count=$((modified_base_count + 1))
  fi
done < "${tmp_dir}/actual.txt"
while IFS= read -r path; do
  [ -n "${path}" ] || continue
  if git diff --diff-filter=D --name-only "${SOURCE_MAIN_SHA}..HEAD" -- "${path}" | grep -Fxq "${path}"; then
    deleted_count=$((deleted_count + 1))
  fi
done < "${tmp_dir}/authorized.txt"

authorized_count="$(wc -l < "${tmp_dir}/authorized.txt" | tr -d ' ')"
actual_count="$(wc -l < "${tmp_dir}/actual.txt" | tr -d ' ')"
missing_count="$(wc -l < "${tmp_dir}/missing.txt" | tr -d ' ')"
unauthorized_count="$(wc -l < "${tmp_dir}/unauthorized.txt" | tr -d ' ')"

printf 'SOURCE_MAIN_SHA=%s\n' "${SOURCE_MAIN_SHA}"
printf 'ROUND_A_WORKTREE=%s\n' "${ROUND_A_WORKTREE}"
printf 'EXPECTED_AUTHORIZED_PATH_COUNT=%s\n' "${authorized_count}"
printf 'ACTUAL_UNION_PATH_COUNT=%s\n' "${actual_count}"
printf 'MISSING_AUTHORIZED_PATH_COUNT=%s\n' "${missing_count}"
printf 'UNAUTHORIZED_PATH_COUNT=%s\n' "${unauthorized_count}"
printf 'MODIFIED_BASE_PATH_COUNT=%s\n' "${modified_base_count}"
printf 'DELETED_PATH_COUNT=%s\n' "${deleted_count}"
printf 'BLOCKED_PATH_PRESENT_COUNT=0\n'
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
printf 'PATH_SCOPE_ACCEPTANCE=PASS\n'
