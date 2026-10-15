"""Capture actual static/offline/frontend checks without a CI workflow change."""

import hashlib
import subprocess
import sys
from pathlib import Path

from backend.tests.acceptance_s6.evidence import ROOT, canonical


def main(directory):
    directory.mkdir(mode=0o700)  # exclusive: never overwrite previous run evidence
    contracts = sorted(
        str(p.relative_to(ROOT))
        for p in (ROOT / "backend/tests/forecast_intelligence").glob("test_v0_18*.py")
    )
    commands = [
        ("ruff", ROOT, ["ruff", "check", "."]),
        ("format", ROOT, ["ruff", "format", "--check", "."]),
        ("mypy_app", ROOT, ["mypy", "backend/app"]),
        ("offline_contracts", ROOT, [sys.executable, "-m", "pytest", "-q", *contracts]),
        ("frontend_lint", ROOT / "frontend", ["npm", "run", "lint"]),
        ("frontend_format", ROOT / "frontend", ["npm", "run", "format:check"]),
        ("frontend_typecheck", ROOT / "frontend", ["npm", "run", "typecheck"]),
        ("frontend_unit", ROOT / "frontend", ["npm", "run", "test:unit", "--", "--run"]),
        ("frontend_build", ROOT / "frontend", ["npm", "run", "build"]),
    ]
    results = []
    for name, cwd, arguments in commands:
        path = directory / (name + ".log")
        with path.open("xb") as output:
            result = subprocess.run(arguments, cwd=cwd, stdout=output, stderr=subprocess.STDOUT)
        results.append(
            {
                "name": name,
                "arguments": arguments,
                "cwd": str(cwd.relative_to(ROOT)),
                "exit": result.returncode,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
        (directory / "checks.json").write_bytes(canonical(results))
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main(Path(sys.argv[1]).absolute())
