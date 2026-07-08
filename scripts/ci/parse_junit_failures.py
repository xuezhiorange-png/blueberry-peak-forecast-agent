"""Parse a pytest JUnit XML file and emit a markdown summary of failed nodeids.

Batch 6 (Issue #54 / Issue #23 sub-area 6) — CI diagnostics helper.

This script is intentionally tiny and side-effect-free so it can run inside
a GitHub Actions step without affecting the workflow's overall pass/fail
status.  The CI step that invokes this script **always** runs after the
pytest step (using ``if: always()``) and **never** lets a parser failure
propagate as a workflow failure: the CI workflow wraps this script with
``|| true`` (see ``.github/workflows/ci.yml``).

Per Issue #54 §6 contract:

* Must work when tests fail and when JUnit XML exists.
* Must degrade safely when JUnit XML is missing / malformed / empty —
  emit a friendly note rather than crashing.
* Must not change the workflow's pass/fail status — pytest's exit code
  is the authoritative signal; this script only surfaces diagnostics.

Output format (markdown, suitable for ``$GITHUB_STEP_SUMMARY``):

    ### Failed pytest nodeids
    * `backend/tests/x/test_y.py::test_z`
    * ...

    Or, on a clean / missing / malformed XML:

    ### Failed pytest nodeids
    (no JUnit XML found — pytest step did not produce a report)
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Cap nodeid output so a mass-failure run does not flood the GH Actions
# summary tab. 100 nodeids is plenty for triage; the JUnit artifact
# retains the full list.
MAX_NODEIDS: int = 100


def parse_junit(xml_path: Path) -> list[str]:
    """Return the list of failed nodeids from a pytest JUnit XML file.

    Uses ``ElementTree`` (stdlib only) to avoid a hard dep on
    ``junitparser`` / ``lxml``. The parser is intentionally tolerant:
    a missing ``<testsuite>`` element or any other structural anomaly
    returns an empty list rather than raising.
    """
    if not xml_path.exists():
        return []
    try:
        tree = ET.parse(xml_path)
    except (ET.ParseError, OSError):
        return []
    root = tree.getroot()
    failed: list[str] = []
    # ``<testsuites>`` is the pytest root, ``<testsuite>`` is junit-xml
    # classic root.  Walk both shapes.
    for testsuite in root.iter("testsuite"):
        for testcase in testsuite.findall("testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")
            skipped = testcase.find("skipped")
            if (failure is not None or error is not None) and skipped is None:
                nodeid = testcase.get("name") or "<unknown nodeid>"
                classname = testcase.get("classname") or ""
                if classname:
                    failed.append(f"{classname}::{nodeid}")
                else:
                    failed.append(nodeid)
    return failed


def render_markdown(failed: list[str], xml_path: Path) -> str:
    """Format the failed-nodeid list as a markdown summary block."""
    lines: list[str] = ["### Failed pytest nodeids"]
    if not xml_path.exists():
        lines.append("(no JUnit XML found — pytest step did not produce a report)")
        return "\n".join(lines)
    if not failed:
        lines.append("(no failed nodeids reported in JUnit XML — pytest step exited cleanly)")
        return "\n".join(lines)
    lines.append(f"({len(failed)} failed, showing up to {MAX_NODEIDS})")
    for nodeid in failed[:MAX_NODEIDS]:
        lines.append(f"* `{nodeid}`")
    if len(failed) > MAX_NODEIDS:
        lines.append(f"* …and {len(failed) - MAX_NODEIDS} more (see JUnit artifact)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a pytest JUnit XML and emit a markdown summary of "
            "failed nodeids for GitHub Actions step summary."
        )
    )
    parser.add_argument(
        "--xml",
        type=Path,
        required=True,
        help="Path to the pytest JUnit XML file",
    )
    args = parser.parse_args(argv)
    failed = parse_junit(args.xml)
    sys.stdout.write(render_markdown(failed, args.xml) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
