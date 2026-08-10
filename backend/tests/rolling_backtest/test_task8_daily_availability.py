from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import sqlite

from backend.app.rolling_backtest.availability import evaluate_authority_visibility
from backend.app.rolling_backtest.enums import AvailabilitySourceType, ExecutionMode
from backend.app.rolling_backtest.node_orchestration import (
    Task9Task8AuthorityMismatchError,
    _load_exact_pinned_candidate,
    _verify_task8_daily_exact_set,
)
from backend.app.rolling_backtest.orchestration import ResolvedInputOutcome
from backend.app.rolling_backtest.resolution import _query_task8_daily_prediction_candidates
from backend.app.rolling_backtest.schemas import (
    ParentAuthorityIdentity,
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    Task8DailyPredictionAvailabilitySnapshot,
    UpstreamSemanticIdentityPayload,
)


def _daily_snapshot(*, created_at: datetime) -> Task8DailyPredictionAvailabilitySnapshot:
    return Task8DailyPredictionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        prediction_date=date(2026, 3, 1),
        created_at=created_at,
        parent_authority=ParentAuthorityIdentity(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            authority_schema_version="task11-parent-auth-v1",
            authority_policy_version="task11-parent-auth-policy-v1",
            authority_timestamp=datetime(2026, 3, 1, 3, 59, tzinfo=UTC),
            authority_status="completed",
            canonical_payload_hash="a" * 64,
        ),
    )


def test_task8_daily_prediction_post_cutoff_row_is_blocked() -> None:
    result = evaluate_authority_visibility(
        snapshot=_daily_snapshot(created_at=datetime(2026, 3, 1, 4, 0, 1, tzinfo=UTC)),
        execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
        forecast_cutoff_at=datetime(2026, 3, 1, 4, 0, tzinfo=UTC),
        as_of_local_date=date(2026, 3, 1),
        business_timezone="Asia/Shanghai",
    )
    assert result.allowed is False
    assert result.blocker_code == "AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF"


def test_task8_daily_prediction_cutoff_equality_is_allowed() -> None:
    cutoff = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
    result = evaluate_authority_visibility(
        snapshot=_daily_snapshot(created_at=cutoff),
        execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
        forecast_cutoff_at=cutoff,
        as_of_local_date=date(2026, 3, 1),
        business_timezone="Asia/Shanghai",
    )
    assert result.allowed is True


@pytest.mark.asyncio
async def test_task8_daily_candidate_sql_filters_daily_row_created_at() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result
    node = SimpleNamespace(
        forecast_cutoff_at=datetime(2026, 3, 1, 4, 0, tzinfo=UTC),
        forecast_start_local_date=date(2026, 3, 1),
        forecast_end_local_date=date(2026, 3, 1),
    )

    await _query_task8_daily_prediction_candidates(
        session,
        node,
        execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
    )

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=sqlite.dialect()))
    assert "maturity_daily_prediction.created_at <=" in sql


def _pinned_daily_input(daily_id: int = 901) -> ResolvedInputOutcome:
    semantic = ResolvedUpstreamSemanticIdentity(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        source_role="task8_daily_prediction:2026-03-01",
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-upstream-v1",
            display_label="task8:daily_prediction",
            semantic_payload_hash="a" * 64,
            input_signature="b" * 64,
            result_hash=None,
            canonical_payload_hash="c" * 64,
            business_version="task8-v1",
        ),
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_row_id",
            reference_value=daily_id,
        ),
    )
    return ResolvedInputOutcome(
        source_role=semantic.source_role,
        source_type=semantic.source_type,
        semantic_identity=semantic,
        persistent_reference=semantic.persistent_reference,
        authoritative_available_at=datetime(2026, 3, 1, 4, 0, tzinfo=UTC),
        canonical_identity_hash="d" * 64,
        canonical_payload_hash="c" * 64,
    )


@pytest.mark.asyncio
async def test_pinned_task8_daily_authority_uses_persisted_created_at() -> None:
    from backend.app.rolling_backtest.node_orchestration import _make_identity

    persisted_created_at = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
    identity = _make_identity(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        source_role="task8_daily_prediction:2026-03-01",
        schema_version="task8-maturity-v1",
        semantic_payload_hash="a" * 64,
        input_signature="b" * 64,
        canonical_payload_hash="c" * 64,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_row_id",
            reference_value=901,
        ),
    )
    daily_row = MagicMock(
        id=901,
        forecast_run_id=84,
        prediction_date=date(2026, 3, 1),
        created_at=persisted_created_at,
    )
    forecast_row = MagicMock(
        id=84,
        plan_id=501,
        source_signature="b" * 64,
        finished_at=datetime(2026, 3, 1, 3, 59, tzinfo=UTC),
    )
    plan_row = MagicMock(id=501, season_id=2026)
    session = AsyncMock()
    session.get.side_effect = [daily_row, forecast_row, plan_row]

    with (
        patch(
            "backend.app.rolling_backtest.node_orchestration.load_maturity_forecast_result",
            new=AsyncMock(return_value=MagicMock(status="completed")),
        ),
        patch(
            "backend.app.rolling_backtest.node_orchestration._task8_daily_prediction_payload_hash",
            return_value="e" * 64,
        ),
    ):
        candidate = await _load_exact_pinned_candidate(
            session,
            SimpleNamespace(season_id=2026),
            identity,
        )

    assert candidate.authoritative_available_at == persisted_created_at
    assert candidate.authoritative_available_at != forecast_row.finished_at


def _task9_verification_rows(*, available_at: datetime | None) -> list[dict[str, object]]:
    return [
        {
            "verification_snapshot": {
                "prediction_date": date(2026, 3, 1),
                "forecast_quantile": quantile,
                "maturity_daily_prediction_id": 901,
                "maturity_daily_prediction_forecast_run_id": 84,
                **(
                    {"maturity_daily_prediction_available_at": available_at}
                    if available_at is not None
                    else {}
                ),
            }
        }
        for quantile in ("P50", "P80", "P90")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("available_at", [None, datetime(2026, 3, 1, 4, 0, 1, tzinfo=UTC)])
async def test_task9_exact_cutoff_rejects_missing_or_post_cutoff_task8_row(
    available_at: datetime | None,
) -> None:
    row = MagicMock(
        id=901,
        forecast_run_id=84,
        prediction_date=date(2026, 3, 1),
        created_at=datetime(2026, 3, 1, 4, 0, 1, tzinfo=UTC),
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session = AsyncMock()
    session.execute.return_value = result
    session.execute.return_value = result

    with pytest.raises(Task9Task8AuthorityMismatchError):
        await _verify_task8_daily_exact_set(
            session,
            forecast_run_id=84,
            pinned_daily_inputs=(_pinned_daily_input(),),
            task9_snapshot_rows=_task9_verification_rows(available_at=available_at),
            source_ref_payload_by_hash={},
            forecast_cutoff_at=datetime(2026, 3, 1, 4, 0, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_task9_exact_cutoff_accepts_task8_row_at_equality_boundary() -> None:
    cutoff = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
    row = MagicMock(
        id=901,
        forecast_run_id=84,
        prediction_date=date(2026, 3, 1),
        created_at=cutoff,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session = AsyncMock()
    session.execute.return_value = result

    exact_set = await _verify_task8_daily_exact_set(
        session,
        forecast_run_id=84,
        pinned_daily_inputs=(_pinned_daily_input(),),
        task9_snapshot_rows=_task9_verification_rows(available_at=cutoff),
        source_ref_payload_by_hash={},
        forecast_cutoff_at=cutoff,
    )
    assert exact_set.db_daily_ids == frozenset({901})


@pytest.mark.asyncio
async def test_task9_verification_timestamp_must_match_persisted_daily_row() -> None:
    cutoff = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
    row = MagicMock(
        id=901,
        forecast_run_id=84,
        prediction_date=date(2026, 3, 1),
        created_at=cutoff,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    session = AsyncMock()
    session.execute.return_value = result

    with pytest.raises(Task9Task8AuthorityMismatchError, match="does not match persisted"):
        await _verify_task8_daily_exact_set(
            session,
            forecast_run_id=84,
            pinned_daily_inputs=(_pinned_daily_input(),),
            task9_snapshot_rows=_task9_verification_rows(
                available_at=datetime(2026, 3, 1, 3, 59, 59, tzinfo=UTC)
            ),
            source_ref_payload_by_hash={},
            forecast_cutoff_at=cutoff,
        )
