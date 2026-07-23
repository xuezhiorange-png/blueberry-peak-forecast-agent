"""Deterministic V0.2-S2 historical binding contract tests."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from backend.app.actual_harvest_labels.hashes import (
    AGGREGATION_POLICY_VERSION,
    SNAPSHOT_POLICY_VERSION,
    WINNER_POLICY_VERSION,
    compute_exclusion_manifest_hash,
    compute_label_row_set_hash,
    compute_label_snapshot_hash,
    compute_snapshot_instance_identity_hash,
    compute_snapshot_request_identity_hash,
    compute_winner_manifest_hash,
)
from backend.app.actual_harvest_labels.persistence import (
    label_row_hash_for,
    winner_row_hash_for,
)
from backend.app.core_forecast.repository import Task9AuthoritySource, Task9MemberSource
from backend.app.rolling_backtest.canonical import canonical_json_value, sha256_payload
from backend.app.rolling_backtest.orchestration import (
    _task9_member_identity_hash,
    build_s2_binding_rows,
    resolve_s2_persisted_authorities,
    run_s2_historical_binding,
)
from backend.app.rolling_backtest.schemas import (
    S2ActualLabelAuthority,
    S2ForecastAuthorityBundle,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingCandidate,
    S2PersistedAuthorityReferences,
    s2_business_grain_hash,
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
            task9_member_identity_hash="5" * 64,
            task10_authority_identity_hash="d" * 64,
            task10_model_identity_hash="6" * 64,
            task10_replay_identity_hash="7" * 64,
            task10_prediction_row_identity_hash="8" * 64,
            forecast_code_identity="code-v1",
            historical_code_identity="historical-code-v1",
            model_identity="model-v1",
            parameter_identity="parameter-v1",
            data_identity="data-v1",
            available_at=_CUTOFF,
            task10_model_available_at=_CUTOFF,
        ),
        authority_verification="SYNTHETIC_ENGINEERING",
    )


def _actual(*, target_date=None, verified: bool = True) -> S2ActualLabelAuthority:
    target_date = target_date or (_CUTOFF.date() + timedelta(days=7))
    return S2ActualLabelAuthority(
        label_snapshot_identity_hash="e" * 64,
        label_row_identity_hash="1" * 64,
        label_winner_identity_hash="2" * 64,
        label_winner_set_identity_hash="5" * 64,
        source_identity_hash="f" * 64,
        actual_source_identity_hash="3" * 64,
        target_date=target_date,
        season_business_key="season:2026",
        farm_business_key="farm:alpha",
        subfarm_business_key="subfarm:alpha-1",
        variety_business_key="variety:legacy",
        business_grain_hash=s2_business_grain_hash(
            season_business_key="season:2026",
            farm_business_key="farm:alpha",
            subfarm_business_key="subfarm:alpha-1",
            variety_business_key="variety:legacy",
            target_date=target_date,
        ),
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


def test_production_runner_rejects_synthetic_authority() -> None:
    request = _request(requested_horizons_days=[7])
    with pytest.raises(ValueError, match="requires exact persisted authority"):
        asyncio.run(
            run_s2_historical_binding(
                object(),
                request=request,
                candidates=(_forecast(7),),
                season_id=2026,
            )
        )


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


def test_label_row_target_date_mismatch_is_rejected() -> None:
    request = _request(requested_horizons_days=[7])
    candidate = _forecast(7).model_copy(
        update={"actual_label": _actual(target_date=_CUTOFF.date() + timedelta(days=8))}
    )
    with pytest.raises(ValueError, match="target date"):
        build_s2_binding_rows(request, (candidate,))


def test_label_business_grain_mismatch_is_rejected() -> None:
    request = _request(requested_horizons_days=[7])
    candidate = _forecast(7).model_copy(
        update={
            "actual_label": _actual().model_copy(
                update={"farm_business_key": "farm:outside-request"}
            )
        }
    )
    with pytest.raises(ValueError, match="outside request scope"):
        build_s2_binding_rows(request, (candidate,))


def test_snapshot_hash_cannot_substitute_for_label_row_hash() -> None:
    request = _request(requested_horizons_days=[7])
    actual = _actual()
    candidate = _forecast(7).model_copy(
        update={
            "actual_label": actual.model_copy(
                update={"label_row_identity_hash": actual.label_snapshot_identity_hash}
            )
        }
    )
    with pytest.raises(ValueError, match="cannot substitute"):
        build_s2_binding_rows(request, (candidate,))


def _install_persisted_authority_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    duplicate_task9_member: bool = False,
    missing_core_run: bool = False,
    task9_cutoff: datetime = _CUTOFF,
    training_finished_at: datetime = _CUTOFF - timedelta(seconds=1),
    winner_recorded_at: datetime = _LABEL_CUTOFF,
    label_day_offset: int = 0,
    label_farm_business_key: str = "farm:alpha",
) -> tuple[Any, S2HistoricalBacktestRequest, S2HistoricalBindingCandidate]:
    target_date = _CUTOFF.date() + timedelta(days=7)
    label_target_date = target_date + timedelta(days=label_day_offset)
    task9_result_hash = "3" * 64
    task9_member = Task9MemberSource(
        state_date=target_date,
        forecast_quantile="P50",
        farm_id=11,
        subfarm_id=12,
        variety_id=13,
        destination_factory_id=14,
        natural_maturity_supply_kg=Decimal("20"),
        opening_mature_inventory_kg=Decimal("1"),
        available_mature_quantity_kg=Decimal("21"),
        mature_inventory_loss_quantity_kg=Decimal("0"),
        harvestable_mature_quantity_kg=Decimal("21"),
        allocated_harvest_capacity_kg=Decimal("15"),
        harvested_quantity_kg=Decimal("12.5"),
        closing_mature_inventory_kg=Decimal("8.5"),
        unharvested_backlog_kg=Decimal("6"),
    )
    members = (task9_member, task9_member) if duplicate_task9_member else (task9_member,)
    task9_authority = Task9AuthoritySource(
        run_id=301,
        status="completed",
        forecast_start_date=target_date,
        forecast_end_date=target_date,
        destination_factory_id=14,
        forecast_season_id=21,
        maturity_forecast_run_id=201,
        maturity_model_artifact_hash="a" * 64,
        result_hash=task9_result_hash,
        member_rows=members,
    )
    core_run = SimpleNamespace(
        id=401,
        result_hash="1" * 64,
        run_schema_version="core-code-v1",
        task8_artifact_hash="a" * 64,
        forecast_input_hash="b" * 64,
        status="completed",
        task9_harvest_state_run_id=301,
        task8_forecast_run_id=201,
        task9_result_hash=task9_result_hash,
        forecast_season_id=21,
    )
    core_row = SimpleNamespace(
        id=402,
        core_forecast_run_id=401,
        date=target_date,
        forecast_quantile="P50",
        farm_id=11,
        subfarm_id=12,
        variety_id=13,
        destination_factory_id=14,
        task8_forecast_run_id=201,
        task9_harvest_state_run_id=301,
        task9_result_hash=task9_result_hash,
        row_hash="2" * 64,
        marketable_policy_hash="c" * 64,
        model_harvested_marketable_quantity_kg=Decimal("12.5"),
    )
    task9 = SimpleNamespace(
        id=301,
        result_hash=task9_result_hash,
        status="completed",
        is_replay=True,
        forecast_effective_cutoff_at=task9_cutoff,
        replay_executed_at=_CUTOFF,
        replay_code_version="task9-replay-code-v1",
        replay_run_correlation_id="s2-fixture",
        member_row_count=len(members),
    )
    prediction_row = SimpleNamespace(
        arrival_local_date=target_date,
        forecast_horizon_days=7,
        destination_factory_id=14,
        task9_run_id=301,
        task9_result_hash=task9_result_hash,
        prediction_hash="8" * 64,
    )
    task10 = SimpleNamespace(
        prediction_hash="4" * 64,
        prediction_input_signature="7" * 64,
        execution_status="completed",
        model_run_id=701,
        task9_run_id=301,
        task9_result_hash=task9_result_hash,
        input_snapshot={"training_signature": "6" * 64},
        rows=(prediction_row,),
    )
    winner_payload = {
        "source_system": "fixture",
        "external_logical_record_id": "record-1",
        "external_revision_id": "revision-1",
        "revision_number": 1,
        "canonical_record_hash": "1" * 64,
        "record_status": "finalized",
        "effective_status": "eligible",
        "finalized_at_or_null": _CUTOFF,
        "source_recorded_at_or_null": winner_recorded_at,
        "source_recorded_at_authority_status": "AUTHORITATIVE",
        "harvest_business_date": label_target_date,
        "actual_harvest_quantity_kg": Decimal("12.5"),
        "commit_manifest_hash": "9" * 64,
        "season_business_key": "season:2026",
        "farm_business_key": label_farm_business_key,
        "subfarm_business_key": "subfarm:alpha-1",
        "variety_business_key": "variety:legacy",
        "mapping_registry_version": "registry-v1",
        "mapping_policy_version": "mapping-v1",
        "season_resolver_version": "master-v1",
        "mapping_registry_entry_hash": None,
        "resolved_master_business_key": "variety:legacy",
        "resolved_master_parent_business_key": "subfarm:alpha-1",
        "resolved_master_record_hash": "2" * 64,
        "mapping_snapshot_hash": "3" * 64,
        "resolved_identity_snapshot_hash": "a" * 64,
        "registry_content_hash": "4" * 64,
    }
    winner_hash = winner_row_hash_for(winner_payload)
    winner = SimpleNamespace(
        id=503,
        snapshot_id=501,
        season_id=21,
        farm_id=11,
        subfarm_id=12,
        variety_id=13,
        winner_row_hash=winner_hash,
        **winner_payload,
    )
    label_payload = {
        "season_business_key": winner.season_business_key,
        "farm_business_key": winner.farm_business_key,
        "subfarm_business_key": winner.subfarm_business_key,
        "variety_business_key": winner.variety_business_key,
        "harvest_business_date": label_target_date,
        "exact_decimal_quantity_sum_kg": Decimal("12.5"),
        "contributing_winner_hashes": (winner_hash,),
    }
    label = SimpleNamespace(
        **{
            "id": 502,
            "snapshot_id": 501,
            **label_payload,
            "contributing_winner_count": 1,
            "contributing_winner_hashes": json.dumps([winner_hash]),
            "label_row_hash": label_row_hash_for(label_payload),
        }
    )
    source_manifest_set_hash = "f" * 64
    snapshot_request_hash = compute_snapshot_request_identity_hash(
        snapshot_idempotency_key="s2-fixture",
        source_system="fixture",
        visibility_mode="AS_OF_EVALUATION",
        label_observation_cutoff_at_or_null=_LABEL_CUTOFF,
        harvest_date_start=label_target_date,
        harvest_date_end=label_target_date,
        season_business_keys=("season:2026",),
        farm_business_keys_or_empty_for_all=(label_farm_business_key,),
        variety_business_keys_or_empty_for_all=("variety:legacy",),
        snapshot_policy_version=SNAPSHOT_POLICY_VERSION,
        winner_policy_version=WINNER_POLICY_VERSION,
        aggregation_policy_version=AGGREGATION_POLICY_VERSION,
    )
    snapshot_instance_hash = compute_snapshot_instance_identity_hash(
        request_identity_hash=snapshot_request_hash,
        source_commit_manifest_set_hash=source_manifest_set_hash,
    )
    winner_manifest_hash = compute_winner_manifest_hash(
        (winner_payload | {"winner_row_hash": winner_hash},)
    )
    label_row_set_hash = compute_label_row_set_hash(
        (
            label_payload
            | {
                "contributing_winner_count": 1,
                "label_row_hash": label.label_row_hash,
            },
        )
    )
    exclusion_manifest_hash = compute_exclusion_manifest_hash(())
    snapshot_hash = compute_label_snapshot_hash(
        instance_identity_hash=snapshot_instance_hash,
        winner_manifest_hash=winner_manifest_hash,
        label_row_set_hash=label_row_set_hash,
        exclusion_manifest_hash=exclusion_manifest_hash,
        winner_count=1,
        label_row_count=1,
        exclusion_row_count=0,
        snapshot_policy_version=SNAPSHOT_POLICY_VERSION,
        winner_policy_version=WINNER_POLICY_VERSION,
        aggregation_policy_version=AGGREGATION_POLICY_VERSION,
    )
    snapshot = SimpleNamespace(
        id=501,
        snapshot_idempotency_key="s2-fixture",
        source_system="fixture",
        visibility_mode="AS_OF_EVALUATION",
        label_observation_cutoff_at_or_null=_LABEL_CUTOFF,
        harvest_date_start=label_target_date,
        harvest_date_end=label_target_date,
        season_business_keys=json.dumps(["season:2026"]),
        farm_business_keys_or_empty_for_all=json.dumps([label_farm_business_key]),
        variety_business_keys_or_empty_for_all=json.dumps(["variety:legacy"]),
        snapshot_policy_version=SNAPSHOT_POLICY_VERSION,
        winner_policy_version=WINNER_POLICY_VERSION,
        aggregation_policy_version=AGGREGATION_POLICY_VERSION,
        snapshot_request_identity_hash=snapshot_request_hash,
        snapshot_instance_identity_hash=snapshot_instance_hash,
        source_commit_manifest_set_hash=source_manifest_set_hash,
        winner_manifest_hash=winner_manifest_hash,
        label_row_set_hash=label_row_set_hash,
        exclusion_manifest_hash=exclusion_manifest_hash,
        label_snapshot_hash=snapshot_hash,
        source_manifest_count=1,
        winner_count=1,
        label_row_count=1,
        exclusion_row_count=0,
        snapshot_executed_at=_LABEL_CUTOFF,
        created_by_identity="s2-fixture",
    )
    rows = {
        ("CoreForecastRunModel", 401): None if missing_core_run else core_run,
        ("CoreForecastDailyRowModel", 402): core_row,
        ("HarvestStateRun", 301): task9,
        (
            "ResidualModelTrainingRun",
            701,
        ): SimpleNamespace(
            id=701,
            training_signature="6" * 64,
            execution_status="completed",
            eligibility_status="eligible",
            finished_at=training_finished_at,
        ),
        ("ActualHarvestLabelSnapshotModel", 501): snapshot,
        ("ActualHarvestLabelSnapshotLabelModel", 502): label,
        ("ActualHarvestLabelSnapshotWinnerModel", 503): winner,
    }

    class _Session:
        async def get(self, model: type[object], identity: int) -> object | None:
            return rows.get((model.__name__, identity))

    class _Repository:
        def __init__(self, _session: object) -> None:
            pass

        async def load_task9_authority(self, run_id: int) -> Task9AuthoritySource | None:
            return task9_authority if run_id == 301 else None

    class _CorePersistence:
        def __init__(self, _session: object) -> None:
            pass

        async def load_complete_run(self, run_id: int) -> object | None:
            if run_id != 401:
                return None
            return SimpleNamespace(
                run=SimpleNamespace(run_id=401, result_hash=core_run.result_hash),
                daily_curve=SimpleNamespace(rows=(SimpleNamespace(row_hash=core_row.row_hash),)),
            )

    async def _load_task9(_session: object, *, run_id: int) -> object | None:
        return (
            SimpleNamespace(
                result_hash=task9_result_hash,
                status="completed",
                daily_member_state_rows=(task9_member,),
            )
            if run_id == 301
            else None
        )

    async def _load_task10(_session: object, *, run_id: int) -> object | None:
        return task10 if run_id == 601 else None

    async def _load_task10_training(_session: object, *, run_id: int) -> object | None:
        return SimpleNamespace(training_signature="6" * 64) if run_id == 701 else None

    async def _load_labels(_session: object, snapshot_id: int) -> list[object]:
        return [label] if snapshot_id == 501 else []

    async def _load_winners(_session: object, snapshot_id: int) -> list[object]:
        return [winner] if snapshot_id == 501 else []

    async def _load_exclusions(_session: object, snapshot_id: int) -> list[object]:
        return []

    async def _build_task9_binding(_session: object, *, replay_outcome: object) -> object:
        return SimpleNamespace(
            task9_run_id=301,
            task9_result_hash=task9_result_hash,
            replay_outcome=replay_outcome,
        )

    async def _evaluate_task10(
        _session: object,
        *,
        binding_context: object,
        prediction_input: object,
        requested_policy: object,
    ) -> object:
        return SimpleNamespace(
            prediction_run_id=601,
            binding_context=binding_context,
            prediction_input=prediction_input,
            requested_policy=requested_policy,
        )

    monkeypatch.setattr(
        "backend.app.core_forecast.repository.SqlAlchemyCoreForecastRepository",
        _Repository,
    )
    monkeypatch.setattr(
        "backend.app.core_forecast.persistence.CoreForecastRunRepository",
        _CorePersistence,
    )
    monkeypatch.setattr(
        "backend.app.harvest_state.persistence.load_harvest_state_output_by_id",
        _load_task9,
    )
    monkeypatch.setattr(
        "backend.app.residual_model.persistence.load_residual_prediction_run_by_id",
        _load_task10,
    )
    monkeypatch.setattr(
        "backend.app.residual_model.persistence.load_residual_training_run_by_id",
        _load_task10_training,
    )
    monkeypatch.setattr(
        "backend.app.actual_harvest_labels.persistence.load_label_rows_for_snapshot",
        _load_labels,
    )
    monkeypatch.setattr(
        "backend.app.actual_harvest_labels.persistence.load_winners_for_snapshot",
        _load_winners,
    )
    monkeypatch.setattr(
        "backend.app.actual_harvest_labels.persistence.load_exclusion_rows_for_snapshot",
        _load_exclusions,
    )
    monkeypatch.setattr(
        "backend.app.rolling_backtest.replay_task10_binding.build_replay_task9_binding_context",
        _build_task9_binding,
    )
    monkeypatch.setattr(
        "backend.app.rolling_backtest.replay_task10_binding.evaluate_replay_task10_binding",
        _evaluate_task10,
    )

    request = _request(requested_horizons_days=[7])
    business_grain_hash = s2_business_grain_hash(
        season_business_key=winner.season_business_key,
        farm_business_key=winner.farm_business_key,
        subfarm_business_key=winner.subfarm_business_key,
        variety_business_key=winner.variety_business_key,
        target_date=label_target_date,
    )
    winner_set_hash = sha256_payload(canonical_json_value({"winner_row_hashes": (winner_hash,)}))
    actual_source_hash = sha256_payload(
        canonical_json_value(
            {
                "source_commit_manifest_set_hash": snapshot.source_commit_manifest_set_hash,
                "winner_commit_manifest_hashes": (winner.commit_manifest_hash,),
            }
        )
    )
    candidate = S2HistoricalBindingCandidate(
        horizon_days=7,
        target_date=target_date,
        forecast_cutoff_at=_CUTOFF,
        forecast_value_kg=Decimal("12.5"),
        forecast_authority=S2ForecastAuthorityBundle(
            forecast_run_identity_hash=core_run.result_hash,
            daily_row_identity_hash=core_row.row_hash,
            task9_authority_identity_hash=task9_result_hash,
            task9_member_identity_hash=_task9_member_identity_hash(task9_member),
            task10_authority_identity_hash=task10.prediction_hash,
            task10_model_identity_hash=task10.input_snapshot["training_signature"],
            task10_replay_identity_hash=task10.prediction_input_signature,
            task10_prediction_row_identity_hash=prediction_row.prediction_hash,
            forecast_code_identity=core_run.run_schema_version,
            historical_code_identity=task9.replay_code_version,
            model_identity=core_run.task8_artifact_hash,
            parameter_identity=core_row.marketable_policy_hash,
            data_identity=core_run.forecast_input_hash,
            available_at=task9_cutoff,
            task10_model_available_at=training_finished_at,
        ),
        actual_label=S2ActualLabelAuthority(
            label_snapshot_identity_hash=snapshot.label_snapshot_hash,
            label_row_identity_hash=label.label_row_hash,
            label_winner_identity_hash=winner.winner_row_hash,
            label_winner_set_identity_hash=winner_set_hash,
            source_identity_hash=snapshot.source_commit_manifest_set_hash,
            actual_source_identity_hash=actual_source_hash,
            target_date=label_target_date,
            season_business_key=winner.season_business_key,
            farm_business_key=winner.farm_business_key,
            subfarm_business_key=winner.subfarm_business_key,
            variety_business_key=winner.variety_business_key,
            business_grain_hash=business_grain_hash,
            revision_or_winner_evidence={"fixture": True},
            observed_weight_kg=Decimal("12.5"),
            visibility_timestamp=snapshot.snapshot_executed_at,
            physical_alignment_status="VERIFIED",
        ),
        persisted_authority_references=S2PersistedAuthorityReferences(
            core_forecast_run_id=401,
            core_forecast_daily_row_id=402,
            task9_run_id=301,
            task10_prediction_run_id=601,
            label_snapshot_id=501,
            label_row_id=502,
            label_winner_id=503,
        ),
        authority_verification="PERSISTED",
    )
    return _Session(), request, candidate


def test_exact_persisted_forecast_task9_task10_and_i7_authority_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(monkeypatch)
    resolved = asyncio.run(
        resolve_s2_persisted_authorities(
            session,
            request=request,
            candidates=(candidate,),
        )
    )
    assert len(resolved) == 1
    assert resolved[0].authority_verification == "PERSISTED"
    assert resolved[0].forecast_authority == candidate.forecast_authority
    assert resolved[0].actual_label is not None
    assert (
        resolved[0].actual_label.label_row_identity_hash
        == candidate.actual_label.label_row_identity_hash  # type: ignore[union-attr]
    )


def test_missing_persisted_authority_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(
        monkeypatch,
        missing_core_run=True,
    )
    with pytest.raises(ValueError, match="missing"):
        asyncio.run(
            resolve_s2_persisted_authorities(
                session,
                request=request,
                candidates=(candidate,),
            )
        )


def test_ambiguous_persisted_authority_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(
        monkeypatch,
        duplicate_task9_member=True,
    )
    with pytest.raises(ValueError, match="ambiguous"):
        asyncio.run(
            resolve_s2_persisted_authorities(
                session,
                request=request,
                candidates=(candidate,),
            )
        )


def test_latest_fallback_lookup_mode_is_rejected() -> None:
    with pytest.raises(ValidationError):
        S2PersistedAuthorityReferences.model_validate(
            {
                "lookup_mode": "LATEST",
                "core_forecast_run_id": 1,
                "core_forecast_daily_row_id": 2,
                "task9_run_id": 3,
                "task10_prediction_run_id": 4,
                "label_snapshot_id": 5,
                "label_row_id": 6,
                "label_winner_id": 7,
            }
        )


def test_future_persisted_forecast_authority_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(
        monkeypatch,
        task9_cutoff=_CUTOFF + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="cutoff"):
        asyncio.run(
            resolve_s2_persisted_authorities(
                session,
                request=request,
                candidates=(candidate,),
            )
        )


def test_future_task10_model_authority_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(
        monkeypatch,
        training_finished_at=_CUTOFF + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="Task 10 model authority.*forecast cutoff"):
        asyncio.run(
            resolve_s2_persisted_authorities(
                session,
                request=request,
                candidates=(candidate,),
            )
        )


def test_future_i7_revision_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(
        monkeypatch,
        winner_recorded_at=_LABEL_CUTOFF + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="future I7 winner revision"):
        asyncio.run(
            resolve_s2_persisted_authorities(
                session,
                request=request,
                candidates=(candidate,),
            )
        )


def test_persisted_i7_label_target_date_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(
        monkeypatch,
        label_day_offset=1,
    )
    with pytest.raises(ValueError, match="requested snapshot/visibility mode"):
        asyncio.run(
            resolve_s2_persisted_authorities(
                session,
                request=request,
                candidates=(candidate,),
            )
        )


def test_persisted_i7_business_grain_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(
        monkeypatch,
        label_farm_business_key="farm:outside-request",
    )
    with pytest.raises(ValueError, match="snapshot scope|business grain"):
        asyncio.run(
            resolve_s2_persisted_authorities(
                session,
                request=request,
                candidates=(candidate,),
            )
        )


def test_persisted_snapshot_hash_cannot_substitute_for_label_row_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, request, candidate = _install_persisted_authority_fixture(monkeypatch)
    assert candidate.actual_label is not None
    drifted = candidate.model_copy(
        update={
            "actual_label": candidate.actual_label.model_copy(
                update={
                    "label_row_identity_hash": (candidate.actual_label.label_snapshot_identity_hash)
                }
            )
        }
    )
    with pytest.raises(ValueError, match="persisted I7 identity"):
        asyncio.run(
            resolve_s2_persisted_authorities(
                session,
                request=request,
                candidates=(drifted,),
            )
        )
