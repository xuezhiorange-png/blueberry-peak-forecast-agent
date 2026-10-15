"""Compose S6 coverage with the immutable S5 owned-resource/cancellation runner.

Only test command selection changes. PostgreSQL startup, ownership verification,
signal handling, secret scanning and shutdown remain the exact S5 implementation.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from backend.tests.safe_pilot import run as owned_runner


def main():
    original = owned_runner.command
    if "--s6-only" in sys.argv:
        sys.argv.remove("--s6-only")
        owned_runner.TESTS = ["backend/tests/acceptance_s6"]
    else:
        owned_runner.TESTS = [*owned_runner.TESTS, "backend/tests/acceptance_s6"]

    def command(arguments, environment, log, **kwargs):
        root = Path(environment["TMPDIR"]).parent
        sources = [
            *owned_runner.ROOT.joinpath("backend/tests/acceptance_s6").glob("*.py"),
            owned_runner.ROOT / "frontend/e2e/dashboard-s6-acceptance.spec.ts",
            owned_runner.ROOT / "frontend/e2e/support/acceptance_s6_pg.py",
        ]
        checkpoint = root / "s6-executed-sources.json"
        if not checkpoint.exists():
            checkpoint.write_text(
                json.dumps(
                    {
                        "SYNTHETIC": True,
                        "source_sha256": {
                            str(p.relative_to(owned_runner.ROOT)): hashlib.sha256(
                                p.read_bytes()
                            ).hexdigest()
                            for p in sorted(sources)
                        },
                    },
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            )
            versions = {"python": sys.version}
            for tool in ("node", "pg_ctl", "pg_dump", "pg_restore"):
                versions[tool] = subprocess.check_output(
                    [tool, "--version"], text=True, env=environment
                ).strip()
            (root / "s6-toolchain.json").write_text(
                json.dumps(versions, sort_keys=True, indent=2) + "\n"
            )
        if arguments[:3] == ["npx", "playwright", "test"]:
            arguments = [
                *arguments[:3],
                "dashboard-business-flow.spec.ts",
                "dashboard-s6-acceptance.spec.ts",
                *arguments[4:],
                "--reporter=list,json",
            ]
            environment = dict(
                environment, PLAYWRIGHT_JSON_OUTPUT_FILE=str(root / "browser-results.json")
            )
        return original(arguments, environment, log, **kwargs)

    owned_runner.command = command
    try:
        owned_runner.main()
    finally:
        owned_runner.command = original


if __name__ == "__main__":
    sys.exit(main())
