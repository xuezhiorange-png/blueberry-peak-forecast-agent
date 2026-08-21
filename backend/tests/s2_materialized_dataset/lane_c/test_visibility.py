from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.rolling_backtest.canonical import canonical_json_dumps
from backend.app.s2_materialized_dataset.lane_c.hashes import (
    canonical_timestamp_string,
    compute_pit_visibility_content_hash,
)
from backend.app.s2_materialized_dataset.lane_c.schemas import (
    ForecastCutoffContext,
    PitVisibilityBlockReason,
    SourceRowIdentity,
    SourceRowLifecycleTimestamps,
)
from backend.app.s2_materialized_dataset.lane_c.visibility import evaluate_pit_visibility
from backend.tests.s2_materialized_dataset.lane_c.conftest import make_timestamps


def test_eligible_row_requires_source_available_at_on_or_before_cutoff(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
) -> None:
    decision = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=make_timestamps(source_available_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC)),
        cutoff_context=cutoff_context,
    )

    assert decision.eligible is True
    assert decision.blocked is False
    assert decision.block_reason is None
    assert len(decision.content_sha256) == 64


def test_future_source_available_at_blocks_row(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
) -> None:
    decision = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=make_timestamps(source_available_at=datetime(2026, 2, 28, 12, 0, 1, tzinfo=UTC)),
        cutoff_context=cutoff_context,
    )

    assert decision.eligible is False
    assert decision.blocked is True
    assert decision.block_reason == PitVisibilityBlockReason.SOURCE_AVAILABLE_AFTER_CUTOFF


def test_missing_source_available_at_blocks_row_without_fabrication(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
) -> None:
    decision = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=make_timestamps(source_available_at=None),
        cutoff_context=cutoff_context,
    )

    assert decision.eligible is False
    assert decision.blocked is True
    assert decision.block_reason == PitVisibilityBlockReason.SOURCE_AVAILABLE_MISSING


def test_unknown_timestamps_remain_explicit_nulls_in_hash_payload(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
) -> None:
    timestamps = SourceRowLifecycleTimestamps(
        source_recorded_at=None,
        source_available_at=datetime(2026, 2, 27, 9, 0, tzinfo=UTC),
        source_revised_at=None,
        source_finalized_at=None,
        source_cancelled_at=None,
    )
    first = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=timestamps,
        cutoff_context=cutoff_context,
    )
    second = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=timestamps,
        cutoff_context=cutoff_context,
    )

    assert first.content_sha256 == second.content_sha256
    assert first.timestamps.source_recorded_at is None


def test_contradictory_finalized_and_cancelled_timestamps_block_row(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
) -> None:
    decision = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=make_timestamps(
            source_finalized_at=datetime(2026, 2, 27, 10, 0, tzinfo=UTC),
            source_cancelled_at=datetime(2026, 2, 27, 11, 0, tzinfo=UTC),
        ),
        cutoff_context=cutoff_context,
    )

    assert decision.blocked is True
    assert decision.block_reason == PitVisibilityBlockReason.CONTRADICTORY_TIMESTAMPS


def test_cancelled_at_or_before_cutoff_is_not_pit_eligible(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
) -> None:
    decision = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=make_timestamps(
            source_available_at=datetime(2026, 2, 27, 9, 0, tzinfo=UTC),
            source_cancelled_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        ),
        cutoff_context=cutoff_context,
    )

    assert decision.eligible is False
    assert decision.blocked is True
    assert decision.block_reason == PitVisibilityBlockReason.SOURCE_CANCELLED


def test_source_revised_after_available_is_allowed_for_ordinary_revision(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
) -> None:
    decision = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=make_timestamps(
            source_available_at=datetime(2026, 2, 27, 9, 0, tzinfo=UTC),
            source_revised_at=datetime(2026, 2, 27, 15, 0, tzinfo=UTC),
        ),
        cutoff_context=cutoff_context,
    )

    assert decision.eligible is True
    assert decision.blocked is False


def test_naive_timestamp_blocks_without_utc_coercion(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
) -> None:
    decision = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=make_timestamps(
            source_available_at=datetime(2026, 2, 27, 9, 0),
        ),
        cutoff_context=cutoff_context,
    )

    assert decision.eligible is False
    assert decision.blocked is True
    assert decision.block_reason == PitVisibilityBlockReason.NAIVE_TIMESTAMP


@pytest.mark.parametrize(
    "available_at",
    [
        datetime(2026, 2, 28, 11, 59, 59, tzinfo=UTC),
        datetime(2026, 2, 28, 12, 0, 0, tzinfo=UTC),
    ],
)
def test_source_available_at_equal_or_before_cutoff_is_eligible(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
    available_at: datetime,
) -> None:
    decision = evaluate_pit_visibility(
        source_row_identity=synthetic_source_row_identity,
        timestamps=make_timestamps(source_available_at=available_at),
        cutoff_context=cutoff_context,
    )
    assert decision.eligible is True


def test_canonical_timestamp_string_uses_z_suffix_not_plus_zero_zero() -> None:
    value = datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
    encoded = canonical_timestamp_string(value)
    assert encoded.endswith("Z")
    assert "+00:00" not in encoded


def test_hash_payload_serializes_timestamps_with_z_suffix(
    synthetic_source_row_identity: SourceRowIdentity,
    cutoff_context: ForecastCutoffContext,
) -> None:
    timestamps = make_timestamps(source_available_at=datetime(2026, 2, 27, 9, 0, tzinfo=UTC))
    content_hash = compute_pit_visibility_content_hash(
        source_row_identity=synthetic_source_row_identity,
        timestamps=timestamps,
        cutoff_context=cutoff_context,
        eligible=True,
        blocked=False,
        block_reason=None,
    )
    payload = {
        "timestamps": {
            "source_recorded_at": timestamps.source_recorded_at,
            "source_available_at": timestamps.source_available_at,
            "source_revised_at": None,
            "source_finalized_at": None,
            "source_cancelled_at": None,
        },
        "forecast_cutoff_at": cutoff_context.forecast_cutoff_at,
    }
    serialized = canonical_json_dumps(payload)
    assert "Z" in serialized
    assert "+00:00" not in serialized
    assert len(content_hash) == 64


def test_naive_timestamp_in_hash_scope_raises() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_timestamp_string(datetime(2026, 2, 28, 12, 0))
