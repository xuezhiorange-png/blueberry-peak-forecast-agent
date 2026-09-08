#!/usr/bin/env python3
"""Retired historical S4-C01 local-engineering runner.

This file is retained for historical provenance only.  The four historical
C01 invocations are already represented by the immutable legacy validation
budget debit, and the current durable-authority policy forbids rerunning C01.
Execution is permanently fail-closed before any source, database, dataset,
materialization, replay, or scoring code can be reached.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

CANDIDATE_01_RERUN_FORBIDDEN = "CANDIDATE_01_RERUN_FORBIDDEN"
RUNNER_STATUS = "RETIRED"
EXECUTION_ALLOWED = False


class LocalRunnerContractError(RuntimeError):
    """A sanitized retired-runner contract failure."""


def _parser() -> argparse.ArgumentParser:
    """Accept the historical CLI shape without retaining an execution path."""

    parser = argparse.ArgumentParser(description=__doc__)
    # These options remain only so old provenance commands fail through the
    # stable retired-runner payload instead of an argument-shape error.
    parser.add_argument("--source-object")
    parser.add_argument("--config")
    parser.add_argument("--execution-main-sha", required=True)
    parser.add_argument("--runner-commit-sha", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=55435)
    parser.add_argument("--database", default="blueberry_peak_s4_local_engineering")
    return parser


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    """Reject direct internal invocation before any execution-side effect."""

    raise LocalRunnerContractError(CANDIDATE_01_RERUN_FORBIDDEN)


def _blocked_payload() -> dict[str, Any]:
    return {
        "EXECUTION_STATUS": "BLOCKED",
        "BLOCKER": CANDIDATE_01_RERUN_FORBIDDEN,
        "REASON_CODE": CANDIDATE_01_RERUN_FORBIDDEN,
        "RUNNER_STATUS": RUNNER_STATUS,
        "EXECUTION_ALLOWED": EXECUTION_ALLOWED,
        "CANDIDATE_ID": "01_parameter_calibration",
        "C01_RESULT": "BLOCKED",
        "C01_RERUN_AUTHORIZED": False,
        "C01_RERUN_PERFORMED": False,
        "C01_NEW_STARTED_EVENT_CREATED": False,
        "RUN_LOCAL_REPLAY_CALL_COUNT": 0,
        "DATASET_EXECUTION_LOAD_CALL_COUNT": 0,
        "TEST_ACCESS_CALL_COUNT": 0,
        "NEW_VALIDATION_SCORING_CALL_COUNT": 0,
        "LEGACY_RECONCILED_VALIDATION_DEBIT": 4,
        "CANONICAL_STARTED_COUNT": 0,
        "EFFECTIVE_CONSUMED": 4,
        "REMAINING": 28,
        "TEST_EVALUATION_PERFORMED": False,
        "TEST_REMAINS_SEALED": True,
    }


def main() -> int:
    args = _parser().parse_args()
    try:
        _execute(args)
    except LocalRunnerContractError as exc:
        payload = _blocked_payload()
        payload["BLOCKER"] = str(exc) or CANDIDATE_01_RERUN_FORBIDDEN
        payload["REASON_CODE"] = str(exc) or CANDIDATE_01_RERUN_FORBIDDEN
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    # _execute is intentionally unconditional, but retain a fail-closed guard
    # if that invariant is ever accidentally changed.
    print(json.dumps(_blocked_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 2


if __name__ == "__main__":
    sys.exit(main())
