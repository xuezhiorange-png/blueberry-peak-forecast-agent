"""Fail-closed shell for the not-yet-authorized S4-C03 execution lane.

The historical C03 control plane is retained in the application module, but
this command cannot self-authorize a validation evaluation.  A later owner-
authorized application path may call the internal durable execution seam with
an explicit authorization context and a synthetic or production-approved
scorer.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

CANDIDATE_ID = "03_phenology_offset"
CANDIDATE_EXECUTION_NOT_AUTHORIZED = "CANDIDATE_EXECUTION_NOT_AUTHORIZED"


class C03RunnerContractError(RuntimeError):
    """Stable error raised before any dataset or scoring work is reachable."""

    reason_code = CANDIDATE_EXECUTION_NOT_AUTHORIZED


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Retired-by-default S4-C03 execution shell.")
    parser.add_argument("--execution-main-sha")
    parser.add_argument("--runner-commit-sha")
    parser.add_argument("--candidate-run-ordinal", type=int)
    return parser


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    """Stop before any source, database, model, or scorer access."""

    del args
    raise C03RunnerContractError(CANDIDATE_EXECUTION_NOT_AUTHORIZED)


def _blocked_payload(reason_code: str) -> dict[str, Any]:
    return {
        "EXECUTION_STATUS": "BLOCKED",
        "BLOCKER": reason_code,
        "REASON_CODE": reason_code,
        "CANDIDATE_ID": CANDIDATE_ID,
        "C03_EXECUTION_READY": True,
        "C03_EXECUTION_AUTHORIZED": False,
        "VALIDATION_STARTED_CREATED": False,
        "SCORER_CALLED": False,
        "NEW_VALIDATION_SCORING_CALL_COUNT": 0,
        "TEST_EVALUATION_PERFORMED": False,
        "TEST_REMAINS_SEALED": True,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _execute(args)
    except C03RunnerContractError as exc:
        print(json.dumps(_blocked_payload(exc.reason_code), sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
