#!/usr/bin/env bash
set -euo pipefail

ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TEST_LIST="${PACKAGE_DIR}/authorized-test-modules.txt"
cd "${ROUND_A_WORKTREE}"

test -f "${TEST_LIST}"
mapfile -t modules < <(awk -F ' \\| ' '/^[^#[:space:]]/ {print $1}' "${TEST_LIST}")
test "${#modules[@]}" = "17"

for module in "${modules[@]}"; do
  test -f "${module}"
done

actual_modules="$(find backend/tests/forecast_quality -maxdepth 1 -type f -name 'test_*.py' -print | sort)"
expected_modules="$(printf '%s\n' "${modules[@]}" | sort)"
test "${actual_modules}" = "${expected_modules}"

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/s3-round-a-test-gate.XXXXXX")"
trap 'rmdir "${tmp_dir}" 2>/dev/null || true' EXIT

set +e
uv run pytest "${modules[@]}" -q --disable-warnings --junitxml="${tmp_dir}/junit.xml" >"${tmp_dir}/pytest.stdout" 2>"${tmp_dir}/pytest.stderr"
pytest_exit=$?
set -e

cat "${tmp_dir}/pytest.stdout"
cat "${tmp_dir}/pytest.stderr" >&2

ROUND_A_JUNIT="${tmp_dir}/junit.xml" python3 - <<'PY'
import os
import xml.etree.ElementTree as ET

root = ET.parse(os.environ["ROUND_A_JUNIT"]).getroot()
suite = root if root.tag == "testsuite" else root.find("testsuite")
if suite is None:
    raise SystemExit("missing junit testsuite")
for key in ("tests", "failures", "errors", "skipped"):
    print(f"PYTEST_{key.upper()}={suite.attrib.get(key, '0')}")
print("PYTEST_XFAILED=UNAVAILABLE_FROM_JUNIT")
print("PYTEST_XPASSED=UNAVAILABLE_FROM_JUNIT")
PY
printf 'PYTEST_EXIT_CODE=%s\n' "${pytest_exit}"
test "${pytest_exit}" = "0"
printf 'UNIT_TEST_GATE=PASS\n'
