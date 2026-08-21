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
    SourceRowIdentity,
)
from backend.tests.s2_materialized_dataset.lane_c.conftest import make_timestamps


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
