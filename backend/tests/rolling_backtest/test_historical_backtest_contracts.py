"""Deterministic V0.2-S2 historical binding contract tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.rolling_backtest.orchestration import build_s2_binding_rows
from backend.app.rolling_backtest.schemas import (
    S2ActualLabelAuthority,
    S2ForecastAuthorityBundle,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingCandidate,
)
from backend.app.rolling_backtest.signatures import s2_instance_hash, s2_request_hash

_CUTOFF = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
_LABEL_CUTOFF = datetime(2026, 3, 5, 4, 0, tzinfo=UTC)


def _request(**changes: object) -> S2HistoricalBacktestRequest:
    payload: dict[str, object] = {
        "season_business_keys": ["season:2026"],
        "farm_business_keys": ["farm:alpha"],
        "subfarm_business_keys": ["subfarm:alpha-1"],
        "variety_business_keys": ["variety:legacy"],
        "master_identity_resolver_version": "master-v1",
        "mapping_policy_version": "mapping-v1",
        "resolved_identity_snapshot_hash": "a" * 64,
        "authority_selection_policy_version": "authority-v1",
        "forecast_cutoff_at": _CUTOFF,
        "label_observation_cutoff_at": _LABEL_CUTOFF,
        "label_visibility_mode": "AS_OF_EVALUATION",
        "requested_horizons_days": [7, 14, 21],
    }
    payload.update(changes)
    return S2HistoricalBacktestRequest.model_validate(payload)


def _forecast(horizon: int) -> S2HistoricalBindingCandidate:
    return S2HistoricalBindingCandidate(
        horizon_days=horizon,
        target_date=_CUTOFF.date() + timedelta(days=horizon),
        forecast_cutoff_at=_CUTOFF,
        forecast_value_kg=Decimal(horizon),
        forecast_authority=S2ForecastAuthorityBundle(
            forecast_run_identity_hash=f"{horizon:064x}",
            daily_row_identity_hash=f"{horizon + 1:064x}",
            task9_authority_identity_hash="c" * 64,
            task10_authority_identity_hash="d" * 64,
            forecast_code_identity="code-v1",
            model_identity="model-v1",
            parameter_identity="parameter-v1",
            data_identity="data-v1",
            available_at=_CUTOFF,
        ),
        authority_verification="SYNTHETIC_ENGINEERING",
    )


def _actual(*, target_date=None, verified: bool = True) -> S2ActualLabelAuthority:
    target_date = target_date or (_CUTOFF.date() + timedelta(days=7))
    return S2ActualLabelAuthority(
        label_snapshot_identity_hash="e" * 64,
        label_row_identity_hash="1" * 64,
        label_winner_identity_hash="2" * 64,
        source_identity_hash="f" * 64,
        actual_source_identity_hash="3" * 64,
        target_date=target_date,
        season_business_key="season:2026",
        farm_business_key="farm:alpha",
        subfarm_business_key="subfarm:alpha-1",
        variety_business_key="variety:legacy",
        business_grain_hash="4" * 64,
        revision_or_winner_evidence={"revision": 1},
        observed_weight_kg=Decimal("12.500000"),
        visibility_timestamp=_LABEL_CUTOFF,
        physical_alignment_status="VERIFIED" if verified else "UNVERIFIED",
    )


def test_request_hash_uses_business_keys_not_numeric_lookup_ids() -> None:
    first = _request(
        season_business_keys=["season:2026", "season:2025"],
        farm_business_keys=["farm:z", "farm:a"],
    )
    second = _request(
        season_business_keys=["season:2025", "season:2026"],
        farm_business_keys=["farm:a", "farm:z"],
    )
    assert s2_request_hash(first) == s2_request_hash(second)
    assert "season_id" not in str(first.model_dump())
    assert "farm_id" not in str(first.model_dump())


def test_identity_resolver_version_changes_request_hash() -> None:
    assert s2_request_hash(_request()) != s2_request_hash(
        _request(master_identity_resolver_version="master-v2")
    )


def test_caller_arbitrary_node_identity_hash_is_rejected() -> None:
    with pytest.raises(ValidationError, match="derived canonical S2 node identity"):
        _request(single_node_identity_hash="b" * 64)


def test_unverified_caller_authority_is_rejected_before_binding() -> None:
    request = _request(requested_horizons_days=[7])
    candidate = _forecast(7).model_copy(update={"authority_verification": "UNVERIFIED"})
    with pytest.raises(ValueError, match="not accepted without persisted verification"):
        build_s2_binding_rows(request, (candidate,))


def test_visibility_cutoff_combinations_are_fail_closed() -> None:
    with pytest.raises(ValidationError, match="requires label_observation_cutoff_at"):
        _request(label_visibility_mode="AS_OF_EVALUATION", label_observation_cutoff_at=None)
    with pytest.raises(ValidationError, match="requires null"):
        _request(
            label_visibility_mode="FINAL_ADJUDICATED",
            label_observation_cutoff_at=_LABEL_CUTOFF,
        )


def test_horizons_are_sorted_and_duplicates_are_rejected() -> None:
    assert _request(requested_horizons_days=[21, 7, 14]).requested_horizons_days == (7, 14, 21)
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        _request(requested_horizons_days=[7, 7])
    with pytest.raises(ValidationError, match="subset of 7, 14, 21"):
        _request(requested_horizons_days=[30])


def test_missing_actual_is_explicit_unknown_exclusion_not_zero() -> None:
    request = _request(requested_horizons_days=[7])
    row = build_s2_binding_rows(request, (_forecast(7),))[0]
    assert row.row_status == "EXCLUDED"
    assert row.reason_code == "NO_APPROVED_REAL_DATA"
    assert row.actual_value_kg is None
    assert row.actual_label is None


def test_unverified_physical_alignment_is_excluded() -> None:
    request = _request(requested_horizons_days=[7])
    candidate = _forecast(7).model_copy(update={"actual_label": _actual(verified=False)})
    row = build_s2_binding_rows(request, (candidate,))[0]
    assert row.row_status == "EXCLUDED"
    assert row.reason_code == "PHYSICAL_TARGET_ALIGNMENT_UNVERIFIED"
    assert row.actual_value_kg == Decimal("12.500000")


def test_three_horizon_rows_are_deterministic_and_comparison_ready() -> None:
    request = _request()
    candidates = tuple(
        item.model_copy(
            update={
                "actual_label": _actual(
                    target_date=_CUTOFF.date() + timedelta(days=item.horizon_days)
                )
            }
        )
        for item in (_forecast(21), _forecast(7), _forecast(14))
    )
    rows = build_s2_binding_rows(request, candidates)
    reversed_rows = build_s2_binding_rows(request, tuple(reversed(candidates)))
    assert [(row.horizon_days, row.target_date) for row in rows] == [
        (7, _CUTOFF.date() + timedelta(days=7)),
        (14, _CUTOFF.date() + timedelta(days=14)),
        (21, _CUTOFF.date() + timedelta(days=21)),
    ]
    assert [row.row_hash for row in rows] == [row.row_hash for row in reversed_rows]
    assert all(row.row_status == "COMPARABLE" for row in rows)
    assert s2_instance_hash(request, rows) == s2_instance_hash(request, reversed_rows)


def test_future_forecast_authority_is_rejected_before_binding() -> None:
    request = _request(requested_horizons_days=[7])
    candidate = _forecast(7).model_copy(
        update={
            "forecast_authority": _forecast(7).forecast_authority.model_copy(
                update={"available_at": _CUTOFF + timedelta(seconds=1)}
            )
        }
    )
    with pytest.raises(ValueError, match="availability violates forecast cutoff"):
        build_s2_binding_rows(request, (candidate,))
