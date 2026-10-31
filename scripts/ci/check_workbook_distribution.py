"""TD-01B path/object metadata guard, plus an explicit synthetic Docker probe.

No workbook is opened, hashed, parsed or downloaded. Git's lazy blob fetching
is disabled; tree entries suffice even when an offending blob is absent locally.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

WORKBOOK_NAMES = frozenset({"2024_2025_receipts.xls", "2025_2026_receipts.xls"})
# Independently observed Git metadata, not SHA256 of source rows or a licence.
WORKBOOK_BLOBS = frozenset(
    {"3413dbbc284312e75a2df98992a6ab66cfa87dbd", "a045348c4c72507ae367b4e30f267fcf19c490c1"}
)


def forbidden_members(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(name for name in names if PurePosixPath(name).name in WORKBOOK_NAMES))


def tree_violations(repo: Path, tree: str = "HEAD") -> tuple[str, list[dict[str, str]]]:
    if tree != "HEAD" and re.fullmatch(r"[0-9a-f]{40}", tree) is None:
        raise ValueError("EXPLICIT_HEAD_OR_FULL_OBJECT_ID_REQUIRED")
    environment = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0"}

    def git(*arguments: str) -> bytes:
        return subprocess.check_output(["git", *arguments], cwd=repo, env=environment)

    resolved = git("rev-parse", "--verify", tree + "^{tree}").decode().strip()
    entries = git("ls-tree", "--full-tree", "-r", "-z", resolved)
    violations = []
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        _mode, kind, oid = metadata.decode("ascii").split()
        if kind != "blob":
            continue
        path = raw_path.decode("utf-8", errors="surrogateescape")
        if oid in WORKBOOK_BLOBS:
            reason = "KNOWN_HISTORICAL_WORKBOOK_BLOB"
        elif PurePosixPath(path).name in WORKBOOK_NAMES:
            reason = "RESERVED_BUSINESS_WORKBOOK_NAME"
        else:
            continue
        violations.append({"path": path, "blob_id": oid, "reason": reason})
    return resolved, sorted(violations, key=lambda row: row["path"])


def docker_synthetic_probe(root: Path) -> dict[str, object]:
    """Exercise real Docker context rules with task-created text files only.

    FROM scratch, no network, image tag, container, database or user volume.
    The broken-policy case deliberately re-includes two synthetic copies.
    """
    policy = (root / ".dockerignore").read_text()
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="SYNTHETIC-TD01B-") as temporary:
        base = Path(temporary)
        for protected in (True, False):
            name = "protected" if protected else "deliberately-broken"
            context, output = base / (name + "-context"), base / (name + "-output")
            directory = context / "backend/SYNTHETIC_SCOPE"
            directory.mkdir(parents=True)
            for filename in (
                *sorted(WORKBOOK_NAMES),
                "LEGAL_SYNTHETIC.xls",
                "LEGAL_SYNTHETIC.xlsx",
            ):
                (directory / filename).write_text("SYNTHETIC_ONLY_NOT_A_BUSINESS_WORKBOOK\n")
            rules = policy
            if not protected:
                rules += (
                    "\n"
                    + "\n".join(
                        "!backend/SYNTHETIC_SCOPE/" + filename
                        for filename in sorted(WORKBOOK_NAMES)
                    )
                    + "\n"
                )
            (context / ".dockerignore").write_text(rules)
            (context / "pyproject.toml").write_text("# SYNTHETIC context only\n")
            (context / "Dockerfile").write_text("FROM scratch\nCOPY . /\n")
            subprocess.run(
                [
                    "docker",
                    "build",
                    "--network=none",
                    "--progress=plain",
                    "--output=type=local,dest=" + str(output),
                    str(context),
                ],
                check=True,
            )
            members = [
                str(path.relative_to(output)) for path in output.rglob("*") if path.is_file()
            ]
            blocked = forbidden_members(members)
            for legal in ("LEGAL_SYNTHETIC.xls", "LEGAL_SYNTHETIC.xlsx"):
                if "backend/SYNTHETIC_SCOPE/" + legal not in members:
                    raise ValueError("LEGAL_SYNTHETIC_FIXTURE_WAS_EXCLUDED")
            if protected and blocked:
                raise ValueError("BUSINESS_WORKBOOK_IN_DOCKER_CONTEXT")
            if not protected and len(blocked) != 2:
                raise ValueError("SYNTHETIC_NEGATIVE_CONTEXT_WAS_NOT_DETECTED")
            rows.append(
                {
                    "case": name,
                    "forbidden_member_count": len(blocked),
                    "result": "PASS" if protected else "REJECTED_EXPECTED",
                }
            )
    return {
        "data_class": "SYNTHETIC_TEST_FIXTURE",
        "cases": rows,
        "business_data_read": False,
        "images_or_volumes_created": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--tree", default="HEAD")
    parser.add_argument("--docker-synthetic-probe", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        tree, violations = tree_violations(args.repo, args.tree)
        report: dict[str, object] = {
            "status": "FAIL" if violations else "PASS",
            "tree": tree,
            "violations": violations,
            "workbook_content_read": False,
            "historical_exposure_eliminated": False,
        }
        if not violations and args.docker_synthetic_probe:
            report["docker_synthetic_probe"] = docker_synthetic_probe(args.repo)
        status = 1 if violations else 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        report = {
            "status": "FAIL",
            "error": type(exc).__name__,
            "workbook_content_read": False,
            "historical_exposure_eliminated": False,
        }
        status = 2
    text = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end="")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
