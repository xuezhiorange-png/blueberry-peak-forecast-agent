from types import SimpleNamespace

import pytest

from backend.app.agent.adapters.baseline_composer import (
    FORECAST_SEASON_ID_MISMATCH,
    SEASON_BINDING_UNAVAILABLE,
    SEASON_IDENTITY_CONFLICT,
    SEASON_REGISTRY_DRIFT,
    TASK9_SEASON_SCHEMA_UNSUPPORTED,
    _validate_task9_v2_season_identity,
)
from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import Blocker
from backend.app.harvest_state.enums import (
    OUTPUT_SCHEMA_VERSION_V1,
    OUTPUT_SCHEMA_VERSION_V2,
    RESULT_HASH_SCHEMA_VERSION_V1,
    RESULT_HASH_SCHEMA_VERSION_V2,
)
from backend.app.harvest_state.persistence import HarvestStateSeasonRegistryDriftError


def _scope(reason: str, extra=None) -> Blocker:
    return Blocker(
        code=BlockerCode.AUTHORITY_SCOPE_MISMATCH,
        message=reason,
        details={"reason": reason, **(extra or {})},
    )


def _identity(_field: str, reason: str) -> Blocker:
    return Blocker(
        code=BlockerCode.AUTHORITY_IDENTITY_MALFORMED,
        message=reason,
        details={"reason": reason},
    )


def _row(**updates):
    values = {
        "output_schema_version": OUTPUT_SCHEMA_VERSION_V2,
        "result_hash_schema_version": RESULT_HASH_SCHEMA_VERSION_V2,
        "forecast_season_id": 1,
    }
    values.update(updates)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        _row(
            output_schema_version=OUTPUT_SCHEMA_VERSION_V1,
            result_hash_schema_version=RESULT_HASH_SCHEMA_VERSION_V1,
            forecast_season_id=None,
        ),
        _row(forecast_season_id=None),
    ],
)
async def test_v1_and_null_season_binding_are_ineligible(row) -> None:
    blocker, selected = await _validate_task9_v2_season_identity(
        session=object(),
        row=row,
        row_id=1,
        requested_season_id=1,
        scope_mismatch=_scope,
        identity_malformed=_identity,
    )
    assert selected is None
    assert blocker is not None
    assert blocker.details["reason"] == SEASON_BINDING_UNAVAILABLE


@pytest.mark.asyncio
async def test_unsupported_task9_schema_is_ineligible() -> None:
    blocker, selected = await _validate_task9_v2_season_identity(
        session=object(),
        row=_row(output_schema_version="task9a-output-v99"),
        row_id=1,
        requested_season_id=1,
        scope_mismatch=_scope,
        identity_malformed=_identity,
    )
    assert selected is None
    assert blocker is not None
    assert blocker.details["reason"] == TASK9_SEASON_SCHEMA_UNSUPPORTED


@pytest.mark.asyncio
async def test_v2_canonical_conflict_fails_closed(monkeypatch) -> None:
    async def _load(_session, *, run_id: int):
        return SimpleNamespace(
            forecast_season_id=2,
            input_snapshot={"forecast_season_identity": {"season_id": 2}},
        )

    monkeypatch.setattr(
        "backend.app.harvest_state.persistence.load_harvest_state_output_by_id",
        _load,
    )
    blocker, selected = await _validate_task9_v2_season_identity(
        session=object(),
        row=_row(),
        row_id=1,
        requested_season_id=1,
        scope_mismatch=_scope,
        identity_malformed=_identity,
    )
    assert selected is None
    assert blocker is not None
    assert blocker.details["reason"] == SEASON_IDENTITY_CONFLICT


@pytest.mark.asyncio
async def test_registry_drift_maps_to_stable_identity_blocker(monkeypatch) -> None:
    async def _load(_session, *, run_id: int):
        raise HarvestStateSeasonRegistryDriftError("drift")

    monkeypatch.setattr(
        "backend.app.harvest_state.persistence.load_harvest_state_output_by_id",
        _load,
    )
    blocker, selected = await _validate_task9_v2_season_identity(
        session=object(),
        row=_row(),
        row_id=1,
        requested_season_id=1,
        scope_mismatch=_scope,
        identity_malformed=_identity,
    )
    assert selected is None
    assert blocker is not None
    assert blocker.details["reason"] == SEASON_REGISTRY_DRIFT


@pytest.mark.asyncio
async def test_persisted_season_mismatch_is_scope_mismatch(monkeypatch) -> None:
    async def _load(_session, *, run_id: int):
        return SimpleNamespace(
            forecast_season_id=1,
            input_snapshot={"forecast_season_identity": {"season_id": 1}},
        )

    monkeypatch.setattr(
        "backend.app.harvest_state.persistence.load_harvest_state_output_by_id",
        _load,
    )
    blocker, selected = await _validate_task9_v2_season_identity(
        session=object(),
        row=_row(),
        row_id=1,
        requested_season_id=2,
        scope_mismatch=_scope,
        identity_malformed=_identity,
    )
    assert selected is None
    assert blocker is not None
    assert blocker.details["reason"] == FORECAST_SEASON_ID_MISMATCH
