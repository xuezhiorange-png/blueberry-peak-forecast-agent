from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.harvest_state.canonical import (
    make_result_hash,
    make_season_record_hash,
)
from backend.app.harvest_state.enums import (
    RESULT_HASH_SCHEMA_VERSION_V1,
    RESULT_HASH_SCHEMA_VERSION_V2,
)
from backend.app.harvest_state.schemas import (
    ForecastSeasonIdentitySnapshot,
    Task9ABlockedOutput,
    Task9ACompletedOutput,
    Task9ARequest,
)
from backend.app.harvest_state.service import run_harvest_state_model
from backend.tests.harvest_state.conftest import make_request


def _snapshot(**updates: object) -> ForecastSeasonIdentitySnapshot:
    values = {
        "season_id": 123,
        "season_code": "2026",
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 4, 30),
    }
    values.update(updates)
    values["season_record_hash"] = make_season_record_hash(
        season_id=int(values["season_id"]),
        season_code=str(values["season_code"]),
        start_date=values["start_date"],  # type: ignore[arg-type]
        end_date=values["end_date"],  # type: ignore[arg-type]
    )
    return ForecastSeasonIdentitySnapshot.model_validate(values)


def test_season_record_hash_exact_golden() -> None:
    assert (
        make_season_record_hash(
            season_id=123,
            season_code="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 30),
        )
        == "4ab22bae36fb53732b501957b90426e1cdc041e6923c85bf1052d8d576f22a3c"
    )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"season_id": 0}, "season_id must be > 0"),
        ({"season_code": ""}, "season_code must be non-empty"),
        (
            {"start_date": date(2026, 5, 1), "end_date": date(2026, 4, 30)},
            "end_date must be >= start_date",
        ),
    ],
)
def test_snapshot_rejects_invalid_business_identity(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _snapshot(**updates)


def test_snapshot_rejects_malformed_or_mismatched_hash() -> None:
    valid = _snapshot().model_dump(mode="python")
    with pytest.raises(ValidationError, match="lowercase SHA-256"):
        ForecastSeasonIdentitySnapshot.model_validate({**valid, "season_record_hash": "INVALID"})
    with pytest.raises(ValidationError, match="does not match"):
        ForecastSeasonIdentitySnapshot.model_validate({**valid, "season_record_hash": "0" * 64})


@pytest.mark.parametrize(
    "field",
    ["season_id", "season_code", "start_date", "end_date"],
)
def test_season_record_hash_changes_with_each_business_field(field: str) -> None:
    original = _snapshot()
    updates: dict[str, object] = {
        "season_id": 124,
        "season_code": "2026-v2",
        "start_date": date(2025, 12, 31),
        "end_date": date(2026, 5, 1),
    }
    changed = _snapshot(**{field: updates[field]})
    assert changed.season_record_hash != original.season_record_hash


def test_task9_v2_result_hash_binds_complete_season_snapshot() -> None:
    original = run_harvest_state_model(make_request())
    assert original.output_schema_version == "task9a-output-v2"
    assert original.forecast_season_id == 2026
    assert original.input_snapshot["input_snapshot_schema_version"] == ("task9a-input-snapshot-v2")

    payload = original.model_dump(mode="python")
    assert payload["result_hash"] == make_result_hash(
        payload,
        result_hash_schema_version=RESULT_HASH_SCHEMA_VERSION_V2,
    )
    assert "season_resolution_policy_version" not in str(payload)
    assert "season_resolution_policy_config_hash" not in str(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("season_id", 2027),
        ("season_code", "2026-v2"),
        ("start_date", "2025-12-31"),
        ("end_date", "2026-05-01"),
        ("season_record_hash", "f" * 64),
    ],
)
def test_each_season_snapshot_field_changes_v2_result_hash(
    field: str,
    value: object,
) -> None:
    output = run_harvest_state_model(make_request())
    payload = output.model_dump(mode="python")
    original_hash = make_result_hash(
        payload,
        result_hash_schema_version=RESULT_HASH_SCHEMA_VERSION_V2,
    )
    changed = output.model_dump(mode="python")
    changed["input_snapshot"]["forecast_season_identity"][field] = value
    if field == "season_id":
        changed["forecast_season_id"] = value
    assert (
        make_result_hash(
            changed,
            result_hash_schema_version=RESULT_HASH_SCHEMA_VERSION_V2,
        )
        != original_hash
    )


def test_new_task9_request_requires_forecast_season_snapshot() -> None:
    payload = make_request()
    payload.pop("forecast_season_identity")
    with pytest.raises(ValidationError, match="forecast_season_identity"):
        Task9ARequest.model_validate(payload)


def test_v2_completed_and_blocked_outputs_require_matching_top_level_id() -> None:
    completed = run_harvest_state_model(make_request())
    completed_payload = completed.model_dump(mode="python")
    completed_payload.pop("forecast_season_id")
    with pytest.raises(ValidationError, match="requires forecast_season_id"):
        Task9ACompletedOutput.model_validate(completed_payload)

    blocked_request = make_request()
    blocked_request["farm_timezone"] = "Bad/Timezone"
    blocked = run_harvest_state_model(blocked_request)
    blocked_payload = blocked.model_dump(mode="python")
    blocked_payload["forecast_season_id"] = 999
    with pytest.raises(ValidationError, match="IDs must match"):
        Task9ABlockedOutput.model_validate(blocked_payload)


def test_mixed_v1_v2_output_versions_are_rejected() -> None:
    output = run_harvest_state_model(make_request())
    payload = output.model_dump(mode="python")
    payload["output_schema_version"] = "task9a-output-v1"
    with pytest.raises(ValidationError, match="v1 output cannot contain v2"):
        Task9ACompletedOutput.model_validate(payload)


def test_v1_blocked_output_without_season_remains_readable() -> None:
    payload = {
        "output_schema_version": "task9a-output-v1",
        "status": "blocked",
        "input_snapshot": {"as_of_date": "2026-02-28"},
        "resolved_parameter_snapshot": None,
        "daily_pool_state_rows": [],
        "daily_member_state_rows": [],
        "cohort_transition_rows": [],
        "future_arrival_schedule": [],
        "source_ref_catalog": [],
        "warnings": [],
        "blockers": ["LEGACY_BLOCKER"],
        "config_hash": "a" * 64,
    }
    result_hash = make_result_hash(
        payload,
        result_hash_schema_version=RESULT_HASH_SCHEMA_VERSION_V1,
    )
    output = Task9ABlockedOutput.model_validate({**payload, "result_hash": result_hash})
    assert output.forecast_season_id is None
    round_trip = output.model_dump(mode="python")
    round_trip.pop("forecast_season_id")
    assert (
        make_result_hash(
            round_trip,
            result_hash_schema_version=RESULT_HASH_SCHEMA_VERSION_V1,
        )
        == result_hash
    )


def test_harvest_state_has_no_agent_imports() -> None:
    package = Path("backend/app/harvest_state")
    offenders: list[str] = []
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "backend.app.agent"
            ):
                offenders.append(str(path))
            if isinstance(node, ast.Import):
                offenders.extend(
                    str(path) for alias in node.names if alias.name.startswith("backend.app.agent")
                )
    assert offenders == []
