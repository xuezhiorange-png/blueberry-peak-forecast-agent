#!/usr/bin/env python3
"""Run one read-only prospective S4 authority feasibility scan."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from backend.app.db.session import AsyncSessionMaker, dispose_db_engine  # noqa: E402
from backend.app.forecast_quality.canonical import canonical_json_bytes  # noqa: E402
from backend.app.s4_prospective_authority import (  # noqa: E402
    scan_prospective_validation_authority,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one read-only S4 prospective validation authority scan"
    )
    parser.add_argument("--execution-main-sha", required=True)
    parser.add_argument("--runner-commit-sha", required=True)
    return parser


def _git(ref: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", ref],
        cwd=ROOT,
        text=True,
    ).strip()


def _identity_blocker(*, execution_main_sha: str, runner_commit_sha: str) -> str | None:
    try:
        if _git("HEAD") != runner_commit_sha:
            return "REPOSITORY_IDENTITY_MISMATCH"
        if _git("origin/main") != execution_main_sha:
            return "REPOSITORY_IDENTITY_MISMATCH"
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
            return "REPOSITORY_NOT_CLEAN"
    except (OSError, subprocess.CalledProcessError):
        return "REPOSITORY_IDENTITY_UNAVAILABLE"
    return None


def _blocked_payload(*, reason: str) -> dict[str, Any]:
    return {
        "EXECUTION_STATUS": "BLOCKED",
        "LIVE_PROSPECTIVE_SCAN_STATUS": "BLOCKED",
        "LIVE_PROSPECTIVE_SCAN_BLOCK_REASON": reason,
        "LIVE_PROSPECTIVE_SCAN_REASON_CODE": reason,
        "PROSPECTIVE_FORECAST_CAPTURE_COUNT": 0,
        "POST_TEST_FORECAST_CAPTURE_COUNT": 0,
        "PIT_READABLE_FORECAST_COUNT": 0,
        "ELIGIBLE_LABEL_SNAPSHOT_COUNT": 0,
        "PROSPECTIVE_COMMON_COMPARABLE_ROW_COUNT": 0,
        "PROSPECTIVE_COVERAGE_RATIO": None,
        "VALID_INCLUDED_CANONICAL_GROUP_COVERAGE": None,
        "MISSING_DATA_PROPORTION": None,
        "EARLIEST_ELIGIBLE_FORECAST_CUTOFF": None,
        "LATEST_ELIGIBLE_FORECAST_CUTOFF": None,
        "EARLIEST_ELIGIBLE_TARGET_DATE": None,
        "LATEST_ELIGIBLE_TARGET_DATE": None,
        "PROPOSED_FORECAST_AUTHORITY_SET_HASH": None,
        "PROPOSED_ACTUAL_LABEL_SET_HASH": None,
        "PROPOSED_BUSINESS_GRAIN_SET_HASH": None,
        "PROPOSED_HORIZON_SET_HASH": None,
        "PROPOSED_COMMON_COMPARABLE_SET_HASH": None,
        "PROSPECTIVE_VALIDATION_EXTENSION_FEASIBLE": False,
        "TEST_ACCESS": False,
        "WRITES_PERFORMED": 0,
        "EVALUATION_LEDGER_EVENTS_CREATED": 0,
    }


def _json_payload(payload: dict[str, Any]) -> str:
    return canonical_json_bytes(payload).decode("utf-8")


async def _scan() -> dict[str, Any]:
    async with AsyncSessionMaker() as session:
        result = await scan_prospective_validation_authority(session)
        payload = result.payload()
        payload["EXECUTION_STATUS"] = "PASS"
        return payload


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    identity_blocker = _identity_blocker(
        execution_main_sha=args.execution_main_sha,
        runner_commit_sha=args.runner_commit_sha,
    )
    if identity_blocker is not None:
        print(_json_payload(_blocked_payload(reason=identity_blocker)))
        return 2
    try:
        payload = asyncio.run(_scan())
    except (OSError, ConnectionError, TimeoutError, SQLAlchemyError):
        payload = _blocked_payload(reason="POSTGRESQL_AUTHORITY_STORE_UNAVAILABLE")
        print(_json_payload(payload))
        return 2
    except Exception:
        payload = _blocked_payload(reason="PROSPECTIVE_AUTHORITY_SCAN_FAILED")
        print(_json_payload(payload))
        return 2
    finally:
        try:
            asyncio.run(dispose_db_engine())
        except Exception:
            pass
    print(_json_payload(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
