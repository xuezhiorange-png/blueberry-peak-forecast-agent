from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingBacktestConfig,
    RollingNodeDefinition,
    UpstreamSemanticIdentityPayload,
)
from backend.app.rolling_backtest.signatures import (
    node_signature_hash,
    node_signature_payload,
    run_signature_hash,
    run_signature_payload,
)


def _golden_path(name: str) -> Path:
    return Path(__file__).parent / "golden" / name


def _identity(
    *,
    source_type: AvailabilitySourceType,
    source_role: str,
    display_label: str,
    semantic_payload_hash: str,
    persistent_reference: PersistentUpstreamReference | None = None,
    role_qualifier: str | None = None,
    result_hash: str | None = None,
) -> ResolvedUpstreamSemanticIdentity:
    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        role_qualifier=role_qualifier,
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-upstream-identity-v1",
            display_label=display_label,
            semantic_payload_hash=semantic_payload_hash,
            result_hash=result_hash or semantic_payload_hash,
            canonical_payload_hash=semantic_payload_hash,
        ),
        persistent_reference=persistent_reference,
    )


def _node(
    *,
    season_id: int = 2026,
    node_key: str = "march_15",
    as_of_local_date: date = date(2026, 3, 15),
    forecast_start_local_date: date = date(2026, 3, 16),
    forecast_end_local_date: date = date(2026, 3, 31),
    forecast_cutoff_at: datetime = datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
    identities: tuple[ResolvedUpstreamSemanticIdentity, ...] = (),
    task10_model_policy: dict[str, object] | None = None,
) -> RollingNodeDefinition:
    policy = task10_model_policy or {
        "policy": "historically_available_model",
        "training_run_semantic_identity": "a" * 64,
        "artifact_semantic_identities": ["b" * 64, "c" * 64, "d" * 64],
        "authority_visibility_identity": "e" * 64,
    }
    return RollingNodeDefinition(
        season_id=season_id,
        node_key=node_key,
        as_of_local_date=as_of_local_date,
        forecast_cutoff_at=forecast_cutoff_at,
        forecast_start_local_date=forecast_start_local_date,
        forecast_end_local_date=forecast_end_local_date,
        scope={
            "destination_factory_ids": {"mode": "include_ids", "ids": [202, 101]},
            "farm_ids": {"mode": "all", "ids": []},
            "subfarm_ids": {"mode": "all", "ids": []},
            "variety_ids": {"mode": "all", "ids": []},
        },
        upstream_selection_mode=UpstreamSelectionMode.HISTORICAL_RESOLUTION,
        forecast_horizon_policy_version="task11-horizon-v1",
        timezone="Asia/Shanghai",
        task10_model_policy=policy,
        resolved_upstream_semantic_identities=identities,
    )


def _config(
    nodes: tuple[RollingNodeDefinition, ...],
    *,
    execution_mode: ExecutionMode = ExecutionMode.HISTORICAL_OBSERVED,
    cutoff_local_time: str = "12:00:00",
    cutoff_timezone: str = "Asia/Shanghai",
) -> RollingBacktestConfig:
    return RollingBacktestConfig.model_validate(
        {
            "rolling_schema_version": "task11-rolling-v1",
            "canonical_serialization_version": "task11-canonical-v1",
            "availability_registry_version": "task11-availability-v1",
            "node_calendar_version": "task11-calendar-v1",
            "forecast_horizon_policy_version": "task11-horizon-v1",
            "upstream_selection_policy_version": "task11-selection-v1",
            "metric_policy_version": "task11-metrics-v1",
            "execution_mode": execution_mode.value,
            "calendar_phase_policy_version": "task11-calendar-phase-v1",
            "cutoff_policy_version": "task11-cutoff-v1",
            "cutoff_timezone": cutoff_timezone,
            "cutoff_local_time": cutoff_local_time,
            "nodes": [node.model_dump(mode="json") for node in nodes],
        }
    )


def test_signature_payloads_match_golden() -> None:
    payload = json.loads(_golden_path("signature_payloads.json").read_text(encoding="utf-8"))
    node = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="task9_result",
                semantic_payload_hash="1" * 64,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=77,
                ),
            ),
            _identity(
                source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
                source_role="task10_residual_artifact",
                role_qualifier="p50",
                display_label="task10_artifact_p50",
                semantic_payload_hash="2" * 64,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_artifact_id",
                    reference_value=11,
                ),
            ),
        )
    )
    config = _config((node,))

    assert node_signature_payload(config, node) == payload["historical_node_payload"]
    assert run_signature_payload(config) == payload["historical_run_payload"]
    assert node_signature_hash(config, node) == payload["historical_node_hash"]
    assert run_signature_hash(config) == payload["historical_run_hash"]


def test_run_signature_is_deterministic_for_reordered_nodes() -> None:
    left = _config(
        (
            _node(),
            _node(
                season_id=2027,
                as_of_local_date=date(2027, 3, 15),
                forecast_start_local_date=date(2027, 3, 16),
                forecast_end_local_date=date(2027, 3, 31),
                forecast_cutoff_at=datetime(2027, 3, 15, 4, 0, tzinfo=UTC),
            ),
        )
    )
    right = _config(tuple(reversed(left.nodes)))
    assert run_signature_hash(left) == run_signature_hash(right)


def test_historical_and_replay_signatures_differ() -> None:
    node = _node()
    historical = _config((node,), execution_mode=ExecutionMode.HISTORICAL_OBSERVED)
    replay = _config((node,), execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert node_signature_hash(historical, historical.nodes[0]) != node_signature_hash(
        replay, replay.nodes[0]
    )
    assert run_signature_hash(historical) != run_signature_hash(replay)


def test_database_ids_do_not_enter_node_signature() -> None:
    left = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="same",
                semantic_payload_hash="a" * 64,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=77,
                ),
            ),
        )
    )
    right = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="same",
                semantic_payload_hash="a" * 64,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=99,
                ),
            ),
        )
    )
    config = _config((left,))
    other = _config((right,))
    assert node_signature_hash(config, config.nodes[0]) == node_signature_hash(
        other, other.nodes[0]
    )


def test_persistent_reference_changes_do_not_change_semantic_signature() -> None:
    base = _config(
        (
            _node(
                identities=(
                    _identity(
                        source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
                        source_role="task10_residual_artifact",
                        role_qualifier="p80",
                        display_label="artifact",
                        semantic_payload_hash="b" * 64,
                        persistent_reference=PersistentUpstreamReference(
                            reference_type="database_artifact_id",
                            reference_value=1,
                        ),
                    ),
                )
            ),
        )
    )
    changed = _config(
        (
            _node(
                identities=(
                    _identity(
                        source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
                        source_role="task10_residual_artifact",
                        role_qualifier="p80",
                        display_label="artifact",
                        semantic_payload_hash="b" * 64,
                        persistent_reference=PersistentUpstreamReference(
                            reference_type="database_artifact_id",
                            reference_value=2,
                        ),
                    ),
                )
            ),
        )
    )
    assert run_signature_hash(base) == run_signature_hash(changed)


def test_semantic_payload_hash_change_changes_signature() -> None:
    left = _config(
        (
            _node(
                identities=(
                    _identity(
                        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                        source_role="task9_structural_forecast",
                        display_label="task9_result",
                        semantic_payload_hash="a" * 64,
                    ),
                )
            ),
        )
    )
    right = _config(
        (
            _node(
                identities=(
                    _identity(
                        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                        source_role="task9_structural_forecast",
                        display_label="task9_result",
                        semantic_payload_hash="b" * 64,
                    ),
                )
            ),
        )
    )
    assert node_signature_hash(left, left.nodes[0]) != node_signature_hash(right, right.nodes[0])


def test_duplicate_source_role_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate source role"):
        _node(
            identities=(
                _identity(
                    source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                    source_role="task9_structural_forecast",
                    display_label="first",
                    semantic_payload_hash="a" * 64,
                ),
                _identity(
                    source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
                    source_role="task9_structural_forecast",
                    display_label="second",
                    semantic_payload_hash="b" * 64,
                ),
            )
        )


def test_conflicting_semantic_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="conflicting semantic identity"):
        _node(
            identities=(
                _identity(
                    source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                    source_role="task9_structural_forecast",
                    role_qualifier="default",
                    display_label="task9",
                    semantic_payload_hash="a" * 64,
                ),
                _identity(
                    source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                    source_role="task9_structural_forecast",
                    role_qualifier="default",
                    display_label="task9",
                    semantic_payload_hash="b" * 64,
                    result_hash="c" * 64,
                ),
            )
        )


def test_exact_duplicate_identity_is_rejected() -> None:
    identity = _identity(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        source_role="task9_structural_forecast",
        display_label="task9",
        semantic_payload_hash="a" * 64,
    )
    with pytest.raises(ValueError, match="exact duplicate semantic identity"):
        _node(identities=(identity, identity))


def test_replay_training_identity_changes_node_signature() -> None:
    left = _config(
        (
            _node(
                task10_model_policy={
                    "policy": "replay_trained_model",
                    "training_cutoff_at": "2026-02-28T15:00:00Z",
                    "allowed_training_season_ids": [2024, 2025],
                    "validation_policy_version": "val-v1",
                    "label_visibility_policy_version": "label-v1",
                    "feature_visibility_policy_version": "feature-v1",
                    "artifact_visibility_policy_version": "artifact-v1",
                    "training_manifest_semantic_hash": "a" * 64,
                },
            ),
        ),
        execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY,
    )
    right = _config(
        (
            _node(
                task10_model_policy={
                    "policy": "replay_trained_model",
                    "training_cutoff_at": "2026-02-28T15:00:00Z",
                    "allowed_training_season_ids": [2024, 2025],
                    "validation_policy_version": "val-v2",
                    "label_visibility_policy_version": "label-v1",
                    "feature_visibility_policy_version": "feature-v1",
                    "artifact_visibility_policy_version": "artifact-v1",
                    "training_manifest_semantic_hash": "a" * 64,
                },
            ),
        ),
        execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY,
    )
    assert node_signature_hash(left, left.nodes[0]) != node_signature_hash(right, right.nodes[0])


def test_display_label_does_not_change_signature() -> None:
    """display_label is excluded from semantic payload; changing it must not change signature."""
    left = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="label_one",
                semantic_payload_hash="a" * 64,
            ),
        )
    )
    right = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="label_two",
                semantic_payload_hash="a" * 64,
            ),
        )
    )
    config = _config((left,))
    other = _config((right,))
    assert node_signature_hash(config, config.nodes[0]) == node_signature_hash(
        other, other.nodes[0]
    )
    assert run_signature_hash(config) == run_signature_hash(other)


def test_persistent_reference_does_not_change_signature() -> None:
    """Persistent references (DB IDs) are excluded from semantic payload."""
    left = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="same",
                semantic_payload_hash="a" * 64,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=77
                ),
            ),
        )
    )
    right = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="same",
                semantic_payload_hash="a" * 64,
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=99
                ),
            ),
        )
    )
    config = _config((left,))
    other = _config((right,))
    assert node_signature_hash(config, config.nodes[0]) == node_signature_hash(
        other, other.nodes[0]
    )
    assert run_signature_hash(config) == run_signature_hash(other)


def test_stable_hash_change_changes_node_and_run_signature() -> None:
    """Changing a stable hash (semantic_payload_hash) changes both signatures."""
    left = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="same_label",
                semantic_payload_hash="a" * 64,
            ),
        )
    )
    right = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="same_label",
                semantic_payload_hash="b" * 64,
            ),
        )
    )
    config = _config((left,))
    other = _config((right,))
    assert node_signature_hash(config, config.nodes[0]) != node_signature_hash(
        other, other.nodes[0]
    )
    assert run_signature_hash(config) != run_signature_hash(other)


def test_database_id_cannot_enter_semantic_payload() -> None:
    """A uuid-style display_label does NOT affect the semantic signature."""
    left = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="uuid:abc-123",
                semantic_payload_hash="a" * 64,
            ),
        )
    )
    right = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="task9:run:77",
                semantic_payload_hash="a" * 64,
            ),
        )
    )
    config = _config((left,))
    other = _config((right,))
    assert node_signature_hash(config, config.nodes[0]) == node_signature_hash(
        other, other.nodes[0]
    )
    assert run_signature_hash(config) == run_signature_hash(other)


def test_node_task10_policy_change_changes_node_and_run_signature() -> None:
    """Different Task 10 model policies on nodes produce different signatures."""
    left = _node(
        task10_model_policy={
            "policy": "historically_available_model",
            "training_run_semantic_identity": "a" * 64,
            "artifact_semantic_identities": ["b" * 64, "c" * 64],
            "authority_visibility_identity": "d" * 64,
        },
    )
    right = _node(
        task10_model_policy={
            "policy": "replay_trained_model",
            "training_cutoff_at": "2026-02-28T15:00:00Z",
            "allowed_training_season_ids": [2024, 2025],
            "validation_policy_version": "val-v1",
            "label_visibility_policy_version": "label-v1",
            "feature_visibility_policy_version": "feature-v1",
            "artifact_visibility_policy_version": "artifact-v1",
            "training_manifest_semantic_hash": "a" * 64,
        },
    )
    config = _config((left,), execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    other = _config((right,), execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert node_signature_hash(config, config.nodes[0]) != node_signature_hash(
        other, other.nodes[0]
    )
    assert run_signature_hash(config) != run_signature_hash(other)


def test_task10_policy_is_frozen_per_node() -> None:
    """Each node owns its Task 10 policy independently — and signatures reflect it."""
    node_a = _node(
        season_id=2026,
        node_key="march_15",
        as_of_local_date=date(2026, 3, 15),
        forecast_start_local_date=date(2026, 3, 16),
        forecast_end_local_date=date(2026, 3, 31),
        forecast_cutoff_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
        task10_model_policy={
            "policy": "historically_available_model",
            "training_run_semantic_identity": "a" * 64,
            "artifact_semantic_identities": ["b" * 64],
            "authority_visibility_identity": "c" * 64,
        },
    )
    node_b = _node(
        season_id=2027,
        node_key="march_15",
        as_of_local_date=date(2027, 3, 15),
        forecast_start_local_date=date(2027, 3, 16),
        forecast_end_local_date=date(2027, 3, 31),
        forecast_cutoff_at=datetime(2027, 3, 15, 4, 0, tzinfo=UTC),
        task10_model_policy={
            "policy": "replay_trained_model",
            "training_cutoff_at": "2027-02-28T15:00:00Z",
            "allowed_training_season_ids": [2025, 2026],
            "validation_policy_version": "val-v1",
            "label_visibility_policy_version": "label-v1",
            "feature_visibility_policy_version": "feature-v1",
            "artifact_visibility_policy_version": "artifact-v1",
            "training_manifest_semantic_hash": "d" * 64,
        },
    )
    config = _config((node_a, node_b), execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert node_a.task10_model_policy.policy == "historically_available_model"
    assert node_b.task10_model_policy.policy == "replay_trained_model"
    assert node_signature_hash(config, node_a) != node_signature_hash(config, node_b)
    assert run_signature_hash(config) is not None


def test_historical_observed_rejects_replay_trained_model() -> None:
    """historical_observed mode cannot use replay_trained_model policy."""
    import pytest

    with pytest.raises(
        ValueError, match="historical_observed nodes must use historically_available_model"
    ):
        _config(
            (
                _node(
                    task10_model_policy={
                        "policy": "replay_trained_model",
                        "training_cutoff_at": "2026-02-28T15:00:00Z",
                        "allowed_training_season_ids": [2024, 2025],
                        "validation_policy_version": "val-v1",
                        "label_visibility_policy_version": "label-v1",
                        "feature_visibility_policy_version": "feature-v1",
                        "artifact_visibility_policy_version": "artifact-v1",
                        "training_manifest_semantic_hash": "a" * 64,
                    },
                ),
            ),
            execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
        )


def test_replay_training_cutoff_after_node_cutoff_is_rejected() -> None:
    """Replay training cutoff must not be after the node's forecast cutoff."""
    import pytest

    with pytest.raises(
        ValueError,
        match="replay training_cutoff_at must not be after node forecast_cutoff_at",
    ):
        _node(
            forecast_cutoff_at=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
            task10_model_policy={
                "policy": "replay_trained_model",
                "training_cutoff_at": "2026-03-15T15:00:00Z",
                "allowed_training_season_ids": [2024, 2025],
                "validation_policy_version": "val-v1",
                "label_visibility_policy_version": "label-v1",
                "feature_visibility_policy_version": "feature-v1",
                "artifact_visibility_policy_version": "artifact-v1",
                "training_manifest_semantic_hash": "a" * 64,
            },
        )


def test_multi_node_replay_uses_distinct_training_cutoffs() -> None:
    """Multi-node runs can have distinct training cutoff per node."""
    node_early = _node(
        season_id=2026,
        node_key="february_end",
        as_of_local_date=date(2026, 2, 28),
        forecast_start_local_date=date(2026, 3, 1),
        forecast_end_local_date=date(2026, 3, 31),
        forecast_cutoff_at=datetime(2026, 2, 28, 4, 0, tzinfo=UTC),
        task10_model_policy={
            "policy": "replay_trained_model",
            "training_cutoff_at": "2026-02-15T15:00:00Z",
            "allowed_training_season_ids": [2024, 2025],
            "validation_policy_version": "val-v1",
            "label_visibility_policy_version": "label-v1",
            "feature_visibility_policy_version": "feature-v1",
            "artifact_visibility_policy_version": "artifact-v1",
            "training_manifest_semantic_hash": "a" * 64,
        },
    )
    node_late = _node(
        season_id=2026,
        node_key="march_15",
        as_of_local_date=date(2026, 3, 15),
        forecast_start_local_date=date(2026, 3, 16),
        forecast_end_local_date=date(2026, 3, 31),
        forecast_cutoff_at=datetime(2026, 3, 15, 4, 0, tzinfo=UTC),
        task10_model_policy={
            "policy": "replay_trained_model",
            "training_cutoff_at": "2026-03-01T15:00:00Z",
            "allowed_training_season_ids": [2024, 2025],
            "validation_policy_version": "val-v1",
            "label_visibility_policy_version": "label-v1",
            "feature_visibility_policy_version": "feature-v1",
            "artifact_visibility_policy_version": "artifact-v1",
            "training_manifest_semantic_hash": "b" * 64,
        },
    )
    config = _config((node_early, node_late), execution_mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert node_signature_hash(config, node_early) != node_signature_hash(config, node_late)


def test_semantic_identity_contains_only_typed_stable_fields() -> None:
    """Verify that semantic payload only contains typed stable fields — no display_label."""
    node = _node(
        identities=(
            _identity(
                source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                source_role="task9_structural_forecast",
                display_label="RUN_ID_77",
                semantic_payload_hash="a" * 64,
            ),
        )
    )
    config = _config((node,))
    payload = node_signature_payload(config, node)
    identities = payload["resolved_upstream_semantic_identities"]
    assert len(identities) == 1
    semantic = identities[0]["semantic"]
    # Must contain only typed stable fields
    assert "schema_version" in semantic
    assert "semantic_payload_hash" in semantic
    # Must NOT contain display_label
    assert "display_label" not in semantic
    assert "semantic_identity" not in semantic
    # No DB ID, UUID, or free-form identity strings in semantic payload
    for key in semantic:
        assert isinstance(semantic[key], (str, type(None))), f"unexpected type in {key}"


@pytest.mark.parametrize(
    ("field", "mutated_value"),
    [
        ("cutoff_timezone", "UTC"),
        ("cutoff_local_time", "13:00:00"),
        ("metric_policy_version", "task11-metrics-v2"),
    ],
)
def test_run_signature_changes_when_semantic_config_changes(
    field: str,
    mutated_value: object,
) -> None:
    base = _config((_node(),))
    payload = base.model_dump(mode="json")
    payload[field] = mutated_value
    if field == "cutoff_timezone":
        payload["nodes"][0]["timezone"] = mutated_value
        payload["nodes"][0]["forecast_cutoff_at"] = "2026-03-15T12:00:00Z"
    if field == "cutoff_local_time":
        payload["nodes"][0]["forecast_cutoff_at"] = "2026-03-15T05:00:00Z"
    changed = RollingBacktestConfig.model_validate(payload)
    assert run_signature_hash(base) != run_signature_hash(changed)
