#!/usr/bin/env bash
set -euo pipefail

PACKAGE_REPOSITORY_ROOT="docs/forecast-quality/s3-round-a-authorization-package"
SCRIPT_HASH_PREFIX="${PACKAGE_REPOSITORY_ROOT}/acceptance/"
SELF_PATH="${BASH_SOURCE[0]}"

parse_authorized_manifest() {
  local manifest="$1"
  awk -F ' \\| ' '
    $1 ~ /^backend\// && $2 == "CREATE" { print $1 }
  ' "${manifest}"
}

manifest_metadata_count() {
  grep -Ec '^[A-Z0-9_]+=.*$' "$1" || true
}

manifest_invalid_count() {
  awk -F ' \\| ' '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ || /^[A-Z0-9_]+=.*$/ { next }
    !($1 ~ /^backend\// && $2 == "CREATE") { count++ }
    END { print count + 0 }
  ' "$1"
}

validate_hash_records() {
  local repo="$1"
  local base_sha="$2"
  local sha_file="$3"
  local record_count=0 prefix_count=0 mismatch_count=0 missing_count=0 stale_count=0
  local expected_paths=(
    "${SCRIPT_HASH_PREFIX}01_changed_path_gate.sh"
    "${SCRIPT_HASH_PREFIX}02_runtime_policy_audit.py"
    "${SCRIPT_HASH_PREFIX}03_test_gate.sh"
    "${SCRIPT_HASH_PREFIX}04_static_gate.sh"
  )
  local seen_file
  seen_file="$(mktemp "${TMPDIR:-/tmp}/s3-hash-seen.XXXXXX")"
  : >"${seen_file}"
  while IFS= read -r line; do
    [ -n "${line}" ] || continue
    if [[ ! "${line}" =~ ^([0-9a-f]{64})[[:space:]][[:space:]]([^[:space:]]+)$ ]]; then
      stale_count=$((stale_count + 1))
      continue
    fi
    local expected_hash="${BASH_REMATCH[1]}"
    local repository_relative_path="${BASH_REMATCH[2]}"
    record_count=$((record_count + 1))
    if [[ "${repository_relative_path}" == "${SCRIPT_HASH_PREFIX}"* ]] \
      && [[ "${repository_relative_path}" != /* ]] \
      && [[ "${repository_relative_path}" != *"../"* ]] \
      && [[ "${repository_relative_path}" != *"/.." ]]; then
      prefix_count=$((prefix_count + 1))
    else
      stale_count=$((stale_count + 1))
      continue
    fi
    printf '%s\n' "${repository_relative_path}" >>"${seen_file}"
    if ! git -C "${repo}" cat-file -e "${base_sha}:${repository_relative_path}" 2>/dev/null; then
      missing_count=$((missing_count + 1))
      continue
    fi
    local actual_hash
    actual_hash="$(git -C "${repo}" show "${base_sha}:${repository_relative_path}" | sha256sum | awk '{print $1}')"
    if [[ "${actual_hash}" != "${expected_hash}" ]]; then
      mismatch_count=$((mismatch_count + 1))
    fi
  done <"${sha_file}"
  for expected_path in "${expected_paths[@]}"; do
    if ! grep -Fxq "${expected_path}" "${seen_file}"; then
      stale_count=$((stale_count + 1))
    fi
  done
  rm -f "${seen_file}"
  printf 'SCRIPT_HASH_RECORD_COUNT=%s\n' "${record_count}"
  printf 'SCRIPT_HASH_PATH_PREFIX_MATCH_COUNT=%s\n' "${prefix_count}"
  printf 'SCRIPT_HASH_MISMATCH_COUNT=%s\n' "${mismatch_count}"
  printf 'SCRIPT_HASH_MISSING_PATH_COUNT=%s\n' "${missing_count}"
  printf 'STALE_SCRIPT_HASH_REFERENCE_COUNT=%s\n' "${stale_count}"
  if [[ "${record_count}" == "4" && "${prefix_count}" == "4" \
    && "${mismatch_count}" == "0" && "${missing_count}" == "0" \
    && "${stale_count}" == "0" ]]; then
    return 0
  fi
  return 1
}

run_package_self_test() {
  local package_dir
  package_dir="$(cd "$(dirname "${SELF_PATH}")/.." && pwd)"
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-package-self-test.XXXXXX")"
  trap "rm -rf '${tmp}'" EXIT
  local repo="${tmp}/fixture"
  git init -q "${repo}"
  git -C "${repo}" config user.email "fixture@example.invalid"
  git -C "${repo}" config user.name "Round A fixture"
  mkdir -p "${repo}/${PACKAGE_REPOSITORY_ROOT}"
  cp -R "${package_dir}/." "${repo}/${PACKAGE_REPOSITORY_ROOT}/"
  git -C "${repo}" add "${PACKAGE_REPOSITORY_ROOT}"
  git -C "${repo}" commit -qm "fixture package base"
  local base_sha
  base_sha="$(git -C "${repo}" rev-parse HEAD)"

  local paths_file="${repo}/${PACKAGE_REPOSITORY_ROOT}/authorized-paths.txt"
  mapfile -t valid_paths < <(parse_authorized_manifest "${paths_file}")
  local metadata_count invalid_count metadata_parsed
  metadata_count="$(manifest_metadata_count "${paths_file}")"
  invalid_count="$(manifest_invalid_count "${paths_file}")"
  metadata_parsed=0
  for metadata in AUTHORIZED_CREATE_PATH_COUNT=26 AUTHORIZED_MODIFY_EXISTING_PATH_COUNT=0 AUTHORIZED_DELETE_PATH_COUNT=0 DUPLICATE_AUTHORIZED_PATH_COUNT=0; do
    if printf '%s\n' "${valid_paths[@]}" | grep -Fxq "${metadata}"; then
      metadata_parsed=$((metadata_parsed + 1))
    fi
  done
  test "${#valid_paths[@]}" = "26"
  test "${metadata_count}" = "4"
  test "${invalid_count}" = "0"
  test "${metadata_parsed}" = "0"

  validate_hash_records "${repo}" "${base_sha}" "${repo}/${PACKAGE_REPOSITORY_ROOT}/acceptance/SHA256SUMS" >/dev/null

  for path in "${valid_paths[@]}"; do
    mkdir -p "${repo}/$(dirname "${path}")"
    printf '# fixture\n' >"${repo}/${path}"
  done
  git -C "${repo}" add backend
  git -C "${repo}" commit -qm "fixture compliant implementation"
  local positive_head
  positive_head="$(git -C "${repo}" rev-parse HEAD)"
  IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${repo}" \
    PACKAGE_DIR="${repo}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    bash "${repo}/${SCRIPT_HASH_PREFIX}01_changed_path_gate.sh" >/dev/null

  local negative_expected=0 unexpected_pass=0
  expect_fail() {
    negative_expected=$((negative_expected + 1))
    if "$@" >/dev/null 2>&1; then
      unexpected_pass=$((unexpected_pass + 1))
    fi
  }

  cp "${repo}/${PACKAGE_REPOSITORY_ROOT}/acceptance/SHA256SUMS" "${tmp}/bad-sha"
  sed -i '1s/^[0-9a-f]\{64\}/0000000000000000000000000000000000000000000000000000000000000000/' "${tmp}/bad-sha"
  expect_fail validate_hash_records "${repo}" "${base_sha}" "${tmp}/bad-sha"

  git -C "${repo}" switch -q -c missing-script "${base_sha}"
  git -C "${repo}" rm -q "${SCRIPT_HASH_PREFIX}04_static_gate.sh"
  git -C "${repo}" commit -qm "fixture missing script"
  local missing_base
  missing_base="$(git -C "${repo}" rev-parse HEAD)"
  expect_fail validate_hash_records "${repo}" "${missing_base}" "${repo}/${PACKAGE_REPOSITORY_ROOT}/acceptance/SHA256SUMS"

  git -C "${repo}" switch -q master
  mkdir -p "${repo}/backend/extra"
  printf '# extra\n' >"${repo}/backend/extra/path_27.py"
  git -C "${repo}" add backend/extra/path_27.py
  git -C "${repo}" commit -qm "fixture 27th path"
  expect_fail env IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${repo}" \
    PACKAGE_DIR="${repo}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    bash "${repo}/${SCRIPT_HASH_PREFIX}01_changed_path_gate.sh"

  git -C "${repo}" switch -q -c blocked-fixture "${positive_head}"
  mkdir -p "${repo}/backend/app/models"
  printf '# blocked\n' >"${repo}/backend/app/models/blocked.py"
  git -C "${repo}" add backend/app/models/blocked.py
  git -C "${repo}" commit -qm "fixture blocked path"
  expect_fail env IMPLEMENTATION_BASE_SHA="${base_sha}" ROUND_A_WORKTREE="${repo}" \
    PACKAGE_DIR="${repo}/${PACKAGE_REPOSITORY_ROOT}" PACKAGE_SELF_TEST_INTERNAL=1 \
    bash "${repo}/${SCRIPT_HASH_PREFIX}01_changed_path_gate.sh"

  PACKAGE_SELF_TEST=1 bash "${package_dir}/acceptance/03_test_gate.sh" >"${tmp}/test-self.txt"
  PACKAGE_SELF_TEST=1 python3 "${package_dir}/acceptance/02_runtime_policy_audit.py" >"${tmp}/runtime-self.txt"
  grep -q '^TEST_GATE_SELF_TEST_RESULT=PASS$' "${tmp}/test-self.txt"
  grep -q '^RUNTIME_AUDIT_SELF_TEST_RESULT=PASS$' "${tmp}/runtime-self.txt"

  local runtime_negative
  runtime_negative="$(awk -F= '/^RUNTIME_SELF_TEST_NEGATIVE_EXPECTED_FAILURE_COUNT=/{print $2}' "${tmp}/runtime-self.txt")"
  negative_expected=$((negative_expected + runtime_negative))
  local runtime_unexpected
  runtime_unexpected="$(awk -F= '/^RUNTIME_SELF_TEST_NEGATIVE_UNEXPECTED_PASS_COUNT=/{print $2}' "${tmp}/runtime-self.txt")"
  unexpected_pass=$((unexpected_pass + runtime_unexpected))

  printf 'AUTHORIZED_CREATE_PATH_COUNT=26\n'
  printf 'AUTHORIZED_MANIFEST_RECORD_COUNT=26\n'
  printf 'AUTHORIZED_MANIFEST_METADATA_LINE_COUNT=4\n'
  printf 'AUTHORIZED_MANIFEST_INVALID_RECORD_COUNT=0\n'
  printf 'AUTHORIZED_METADATA_PARSED_AS_PATH_COUNT=0\n'
  cat "${tmp}/test-self.txt"
  cat "${tmp}/runtime-self.txt"
  printf 'POSITIVE_FIXTURE_PASS_COUNT=6\n'
  printf 'NEGATIVE_FIXTURE_EXPECTED_FAILURE_COUNT=%s\n' "${negative_expected}"
  printf 'NEGATIVE_FIXTURE_UNEXPECTED_PASS_COUNT=%s\n' "${unexpected_pass}"
  test "${unexpected_pass}" = "0"
  printf 'PACKAGE_GATE_SELF_TEST_RESULT=PASS\n'
}

if [[ "${PACKAGE_SELF_TEST:-0}" == "1" && "${PACKAGE_SELF_TEST_INTERNAL:-0}" != "1" ]]; then
  run_package_self_test
  exit 0
fi

: "${IMPLEMENTATION_BASE_SHA:?IMPLEMENTATION_BASE_SHA is required}"
ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
AUTHORIZED_FILE="${PACKAGE_DIR}/authorized-paths.txt"
PACKAGE_SHA_FILE="${PACKAGE_DIR}/acceptance/SHA256SUMS"

cd "${ROUND_A_WORKTREE}"
test "$(git rev-parse --show-toplevel)" = "${ROUND_A_WORKTREE}"
git cat-file -e "${IMPLEMENTATION_BASE_SHA}^{commit}"
git merge-base --is-ancestor "${IMPLEMENTATION_BASE_SHA}" HEAD
git cat-file -e "${IMPLEMENTATION_BASE_SHA}:${PACKAGE_REPOSITORY_ROOT}/README.md"
test -f "${AUTHORIZED_FILE}"
test -f "${PACKAGE_SHA_FILE}"
validate_hash_records "${ROUND_A_WORKTREE}" "${IMPLEMENTATION_BASE_SHA}" "${PACKAGE_SHA_FILE}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-path-gate.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT
parse_authorized_manifest "${AUTHORIZED_FILE}" | sort -u >"${tmp_dir}/authorized.txt"
metadata_count="$(manifest_metadata_count "${AUTHORIZED_FILE}")"
invalid_count="$(manifest_invalid_count "${AUTHORIZED_FILE}")"
metadata_parsed=0
while IFS= read -r metadata; do
  [ -n "${metadata}" ] || continue
  if grep -Fxq "${metadata}" "${tmp_dir}/authorized.txt"; then
    metadata_parsed=$((metadata_parsed + 1))
  fi
done < <(grep -E '^[A-Z0-9_]+=.*$' "${AUTHORIZED_FILE}" || true)

git diff --name-only "${IMPLEMENTATION_BASE_SHA}..HEAD" | sort -u >"${tmp_dir}/committed.txt"
git diff --cached --name-only | sort -u >"${tmp_dir}/staged.txt"
git diff --name-only | sort -u >"${tmp_dir}/unstaged.txt"
git ls-files --others --exclude-standard | sort -u >"${tmp_dir}/untracked.txt"
cat "${tmp_dir}/committed.txt" "${tmp_dir}/staged.txt" "${tmp_dir}/unstaged.txt" "${tmp_dir}/untracked.txt" | sort -u >"${tmp_dir}/actual.txt"
comm -23 "${tmp_dir}/authorized.txt" "${tmp_dir}/actual.txt" >"${tmp_dir}/missing.txt" || true
comm -13 "${tmp_dir}/authorized.txt" "${tmp_dir}/actual.txt" >"${tmp_dir}/unauthorized.txt" || true

modified_base_count=0
while IFS= read -r path; do
  [ -n "${path}" ] || continue
  if git cat-file -e "${IMPLEMENTATION_BASE_SHA}:${path}" 2>/dev/null; then
    modified_base_count=$((modified_base_count + 1))
  fi
done <"${tmp_dir}/actual.txt"
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

authorized_count="$(wc -l <"${tmp_dir}/authorized.txt" | tr -d ' ')"
actual_count="$(wc -l <"${tmp_dir}/actual.txt" | tr -d ' ')"
missing_count="$(wc -l <"${tmp_dir}/missing.txt" | tr -d ' ')"
unauthorized_count="$(wc -l <"${tmp_dir}/unauthorized.txt" | tr -d ' ')"
blocked_count="$(wc -l <"${tmp_dir}/blocked.txt" | tr -d ' ')"

printf 'AUTHORIZED_MANIFEST_RECORD_COUNT=%s\n' "${authorized_count}"
printf 'AUTHORIZED_MANIFEST_METADATA_LINE_COUNT=%s\n' "${metadata_count}"
printf 'AUTHORIZED_MANIFEST_INVALID_RECORD_COUNT=%s\n' "${invalid_count}"
printf 'AUTHORIZED_METADATA_PARSED_AS_PATH_COUNT=%s\n' "${metadata_parsed}"
printf 'AUTHORIZED_CREATE_PATH_COUNT=%s\n' "${authorized_count}"
printf 'ACTUAL_UNION_PATH_COUNT=%s\n' "${actual_count}"
printf 'MISSING_AUTHORIZED_PATH_COUNT=%s\n' "${missing_count}"
printf 'UNAUTHORIZED_PATH_COUNT=%s\n' "${unauthorized_count}"
printf 'MODIFIED_BASE_PATH_COUNT=%s\n' "${modified_base_count}"
printf 'DELETED_PATH_COUNT=%s\n' "${deleted_count}"
printf 'BLOCKED_PATH_PRESENT_COUNT=%s\n' "${blocked_count}"
printf 'AUTHORIZED_PATH_LIST_BEGIN\n'; cat "${tmp_dir}/authorized.txt"; printf 'AUTHORIZED_PATH_LIST_END\n'
printf 'ACTUAL_PATH_LIST_BEGIN\n'; cat "${tmp_dir}/actual.txt"; printf 'ACTUAL_PATH_LIST_END\n'

test "${authorized_count}" = "26"
test "${metadata_count}" = "4"
test "${invalid_count}" = "0"
test "${metadata_parsed}" = "0"
test "${actual_count}" = "26"
test "${missing_count}" = "0"
test "${unauthorized_count}" = "0"
test "${modified_base_count}" = "0"
test "${deleted_count}" = "0"
test "${blocked_count}" = "0"
printf 'PATH_SCOPE_ACCEPTANCE=PASS\n'
