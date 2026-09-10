#!/usr/bin/env python3
"""Run the one-time, fixed four-run C04 controlled validation authorization."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


def main() -> int:
    required = ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"BLOCKED:CONTROLLED_BUDGET_DATABASE_ENV_MISSING:{','.join(missing)}")
        return 2
    if os.environ.get("POSTGRES_PASSWORD", "") == "change-me-in-local-env":
        print("BLOCKED:DEFAULT_DATABASE_CREDENTIAL_FORBIDDEN")
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    from backend.app.s4_candidate_04_controlled_real_validation import (
        C04ControlledValidationError,
        run_authorized_c04_validation,
        write_evidence,
    )

    evidence_path = (
        repo_root
        / "docs"
        / "v0-3"
        / "s4"
        / "evidence"
        / "s4-c04-controlled-real-validation-r1.json"
    )
    try:
        evidence = asyncio.run(run_authorized_c04_validation(repo_root))
    except C04ControlledValidationError as exc:
        print(f"BLOCKED:{exc}")
        return 2
    write_evidence(evidence_path, evidence)
    print(evidence_path)
    print(evidence["RESULT"])
    print(evidence["FINAL_BUDGET_STATE"])
    return 0 if evidence["RESULT"] == "COMPLETED_AND_PUSHED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
