"""Smoke test for ``scripts/ci/parse_junit_failures.py``.

Exercises:
- success XML (no failures) → "(no failed nodeids reported ...)"
- failure XML with nodeids → bullet list with classname+name join
- malformed / missing XML → graceful "no JUnit XML found" note
- malformed XML (parse error) → graceful empty list

Run:
    .venv-3.12/bin/python -m pytest scripts/ci/test_parse_junit_failures.py -v

The test file is intentionally stdlib-only so it has no project
dependencies and runs in any CI job's setup-python step.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "ci" / "parse_junit_failures.py"


def _run_helper(xml_path: Path) -> tuple[int, str]:
    """Invoke the helper script as a subprocess and return (exit, stdout)."""
    proc = subprocess.run(
        [sys.executable, str(HELPER), "--xml", str(xml_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return proc.returncode, proc.stdout


def _write_xml(tmp_path: Path, body: str) -> Path:
    xml = tmp_path / "junit.xml"
    xml.write_text(textwrap.dedent(body).strip(), encoding="utf-8")
    return xml


def test_missing_xml(tmp_path: Path) -> None:
    """A missing XML file must emit a friendly note, never crash."""
    exit_code, stdout = _run_helper(tmp_path / "does-not-exist.xml")
    assert exit_code == 0
    assert "no JUnit XML found" in stdout
    assert "Failed pytest nodeids" in stdout


def test_success_xml(tmp_path: Path) -> None:
    """A JUnit XML with zero failures must report cleanly."""
    xml = _write_xml(
        tmp_path,
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <testsuites>
          <testsuite name="pytest" tests="2" failures="0" errors="0" skipped="0">
            <testcase classname="backend.tests.x.test_y" name="test_z" time="0.01"/>
            <testcase classname="backend.tests.x.test_y" name="test_a" time="0.02"/>
          </testsuite>
        </testsuites>
        """,
    )
    exit_code, stdout = _run_helper(xml)
    assert exit_code == 0
    assert "no failed nodeids reported" in stdout
    assert "Failed pytest nodeids" in stdout


def test_failure_xml_with_nodeids(tmp_path: Path) -> None:
    """A JUnit XML with failures must list nodeids in markdown bullets."""
    xml = _write_xml(
        tmp_path,
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <testsuites>
          <testsuite name="pytest" tests="2" failures="1" errors="1" skipped="0">
            <testcase classname="backend.tests.x.test_y" name="test_z" time="0.01">
              <failure message="boom">traceback</failure>
            </testcase>
            <testcase classname="backend.tests.x.test_y" name="test_a" time="0.02">
              <error message="kaboom">traceback</error>
            </testcase>
            <testcase classname="backend.tests.x.test_y" name="test_skipped" time="0.0">
              <skipped/>
            </testcase>
          </testsuite>
        </testsuites>
        """,
    )
    exit_code, stdout = _run_helper(xml)
    assert exit_code == 0
    # Both failures appear, joined classname::name; the skipped one does NOT.
    assert "backend.tests.x.test_y::test_z" in stdout
    assert "backend.tests.x.test_y::test_a" in stdout
    assert "test_skipped" not in stdout
    assert "(2 failed" in stdout
    assert "Failed pytest nodeids" in stdout


def test_malformed_xml(tmp_path: Path) -> None:
    """A syntactically broken XML must degrade safely (empty list, friendly note)."""
    xml = tmp_path / "broken.xml"
    xml.write_text("<<<not-xml>>>", encoding="utf-8")
    exit_code, stdout = _run_helper(xml)
    assert exit_code == 0
    # On parse failure the helper returns an empty failed list, so the
    # message says "no failed nodeids reported" (the file exists but
    # produced nothing parseable).
    assert "Failed pytest nodeids" in stdout
    assert "no failed nodeids reported" in stdout


def test_truncation_above_max_nodeids(tmp_path: Path) -> None:
    """When more than MAX_NODEIDS failures are present, the summary truncates."""
    cases = "\n".join(
        f'<testcase classname="backend.tests.x" name="test_{i}" '
        f'time="0.01"><failure message="x"/></testcase>'
        for i in range(150)
    )
    xml = _write_xml(
        tmp_path,
        f"""\
        <?xml version="1.0" encoding="utf-8"?>
        <testsuites>
          <testsuite name="pytest" tests="150" failures="150" errors="0" skipped="0">
            {cases}
          </testsuite>
        </testsuites>
        """,
    )
    exit_code, stdout = _run_helper(xml)
    assert exit_code == 0
    assert "(150 failed" in stdout
    assert "showing up to 100" in stdout
    assert "and 50 more" in stdout


@pytest.mark.parametrize("missing", [True, False])
def test_classname_absent(tmp_path: Path, missing: bool) -> None:
    """A testcase with no ``classname`` attribute must still produce a nodeid."""
    classname_attr = "" if missing else 'classname="backend.tests.x"'
    xml = _write_xml(
        tmp_path,
        f"""\
        <?xml version="1.0" encoding="utf-8"?>
        <testsuites>
          <testsuite name="pytest" tests="1" failures="1" errors="0" skipped="0">
            <testcase {classname_attr} name="test_lonely" time="0.01">
              <failure message="x"/>
            </testcase>
          </testsuite>
        </testsuites>
        """,
    )
    exit_code, stdout = _run_helper(xml)
    assert exit_code == 0
    assert "test_lonely" in stdout
    if not missing:
        assert "backend.tests.x::test_lonely" in stdout
