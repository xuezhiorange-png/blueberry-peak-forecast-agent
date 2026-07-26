#!/usr/bin/env bash
set -euo pipefail

ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TEST_LIST="${PACKAGE_DIR}/authorized-test-modules.txt"
: "${IMPLEMENTATION_BASE_SHA:?IMPLEMENTATION_BASE_SHA is required}"
cd "${ROUND_A_WORKTREE}"

test -f "${TEST_LIST}"
git cat-file -e "${IMPLEMENTATION_BASE_SHA}^{commit}"
git merge-base --is-ancestor "${IMPLEMENTATION_BASE_SHA}" HEAD
git cat-file -e "${IMPLEMENTATION_BASE_SHA}:docs/forecast-quality/s3-round-a-authorization-package/README.md"
while read -r expected_hash relative_path; do
  [ -n "${expected_hash:-}" ] || continue
  [ -n "${relative_path:-}" ] || continue
  actual_hash="$(git show "${IMPLEMENTATION_BASE_SHA}:${relative_path}" | sha256sum | awk '{print $1}')"
  test "${actual_hash}" = "${expected_hash}"
done < "${PACKAGE_DIR}/acceptance/SHA256SUMS"
mapfile -t modules < <(awk -F ' \\| ' '/^[^#[:space:]]/ {print $1}' "${TEST_LIST}")
test "${#modules[@]}" = "17"
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
