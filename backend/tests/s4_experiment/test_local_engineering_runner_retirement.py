from __future__ import annotations

import json
import sys
from argparse import Namespace
from collections.abc import Callable

import pytest

from scripts import run_v03_s4_local_engineering_validation as runner


def _args() -> Namespace:
    return Namespace(
        source_object=None,
        config=None,
        execution_main_sha="execution-main-sha",
        runner_commit_sha="runner-commit-sha",
        host="127.0.0.1",
        port=55435,
        database="blueberry_peak_s4_local_engineering",
    )


def _spy(calls: list[str], name: str) -> Callable[..., None]:
    def record(*args: object, **kwargs: object) -> None:
        calls.append(name)

    return record


def test_retired_local_engineering_execute_blocks_before_any_scoring(monkeypatch):
    assert not hasattr(runner, "run_local_replay")
    calls: list[str] = []
    for name in (
        "run_local_replay",
        "_load_database_dataset",
        "controlled_materialize_source_002_from_environment",
        "load_frozen_engineering_dataset",
        "verify_frozen_source_object",
    ):
        monkeypatch.setattr(runner, name, _spy(calls, name), raising=False)

    with pytest.raises(runner.LocalRunnerContractError) as error:
        runner._execute(_args())

    assert str(error.value) == runner.CANDIDATE_01_RERUN_FORBIDDEN
    assert calls == []


def test_retired_local_engineering_main_returns_blocked(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_v03_s4_local_engineering_validation.py",
            "--execution-main-sha",
            "execution-main-sha",
            "--runner-commit-sha",
            "runner-commit-sha",
        ],
    )

    exit_code = runner.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload == {
        "BLOCKER": runner.CANDIDATE_01_RERUN_FORBIDDEN,
        "C01_NEW_STARTED_EVENT_CREATED": False,
        "C01_RESULT": "BLOCKED",
        "C01_RERUN_AUTHORIZED": False,
        "C01_RERUN_PERFORMED": False,
        "CANDIDATE_ID": "01_parameter_calibration",
        "CANONICAL_STARTED_COUNT": 0,
        "DATASET_EXECUTION_LOAD_CALL_COUNT": 0,
        "EFFECTIVE_CONSUMED": 4,
        "EXECUTION_ALLOWED": False,
        "EXECUTION_STATUS": "BLOCKED",
        "LEGACY_RECONCILED_VALIDATION_DEBIT": 4,
        "NEW_VALIDATION_SCORING_CALL_COUNT": 0,
        "REASON_CODE": runner.CANDIDATE_01_RERUN_FORBIDDEN,
        "REMAINING": 28,
        "RUN_LOCAL_REPLAY_CALL_COUNT": 0,
        "RUNNER_STATUS": "RETIRED",
        "TEST_ACCESS_CALL_COUNT": 0,
        "TEST_EVALUATION_PERFORMED": False,
        "TEST_REMAINS_SEALED": True,
    }


def test_retired_runner_does_not_debit_durable_budget_or_access_test(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(runner, "_load_database_dataset", _spy(calls, "database"), raising=False)
    monkeypatch.setattr(runner, "run_local_replay", _spy(calls, "replay"), raising=False)

    with pytest.raises(runner.LocalRunnerContractError):
        runner._execute(_args())

    assert calls == []
    payload = runner._blocked_payload()
    assert payload["CANONICAL_STARTED_COUNT"] == 0
    assert payload["EFFECTIVE_CONSUMED"] == 4
    assert payload["REMAINING"] == 28
    assert payload["C01_NEW_STARTED_EVENT_CREATED"] is False
    assert payload["TEST_ACCESS_CALL_COUNT"] == 0
    assert payload["TEST_EVALUATION_PERFORMED"] is False
    assert payload["TEST_REMAINS_SEALED"] is True


def test_retired_runner_has_no_bypass_flags():
    parser = runner._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--force",
                "--execution-main-sha",
                "execution-main-sha",
                "--runner-commit-sha",
                "runner-commit-sha",
            ]
        )
