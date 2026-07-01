from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from backend.app.rolling_backtest.availability import (
    build_availability_authority_registry,
    evaluate_authority_visibility,
    get_availability_authority_spec,
)
from backend.app.rolling_backtest.enums import (
    AvailabilityRuleKind,
    AvailabilitySourceType,
    ExecutionMode,
)
from backend.app.rolling_backtest.schemas import (
    AvailabilityAuthorityEvaluationResult,
    AvailabilitySnapshot,
    ParentAuthorityIdentity,
    PersistentUpstreamReference,
    Task3AnalyticsBuildAvailabilitySnapshot,
    Task3SourceVisibilityIdentity,
    Task6PlanVersionAvailabilitySnapshot,
    Task7WeatherObservationAvailabilitySnapshot,
    Task8DailyPredictionAvailabilitySnapshot,
    Task8ModelArtifactAvailabilitySnapshot,
    Task8ModelRunAvailabilitySnapshot,
    Task9HarvestStateRunAvailabilitySnapshot,
    Task10ModelArtifactAvailabilitySnapshot,
    Task10PredictionRunAvailabilitySnapshot,
)


def _golden_path(name: str) -> Path:
    return Path(__file__).parent / "golden" / name


def _evaluate(
    snapshot: AvailabilitySnapshot, *, mode: ExecutionMode
) -> AvailabilityAuthorityEvaluationResult:
    return evaluate_authority_visibility(
        snapshot=snapshot,
        execution_mode=mode,
        forecast_cutoff_at=datetime(2026, 2, 28, 15, 59, 59, tzinfo=UTC),
        as_of_local_date=date(2026, 2, 28),
        business_timezone="Asia/Shanghai",
    )


def _task3_visibility(
    *,
    visible_through_at: datetime = datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
) -> Task3SourceVisibilityIdentity:
    return Task3SourceVisibilityIdentity(
        visibility_policy_version="task11-task3-source-visibility-v1",
        source_max_raw_id=123,
        aggregation_version="task3-v1",
        config_hash="1" * 64,
        visibility_manifest_hash="2" * 64,
        visible_through_at=visible_through_at,
    )


def _parent_run(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK8_MODEL_RUN,
    timestamp: datetime = datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
    status: str = "completed",
    semantic_hash: str | None = "a" * 64,
    persistent_ref: PersistentUpstreamReference | None = None,
) -> ParentAuthorityIdentity:
    return ParentAuthorityIdentity(
        source_type=source_type,
        authority_schema_version="task11-parent-auth-v1",
        authority_policy_version="task11-parent-auth-policy-v1",
        authority_timestamp=timestamp,
        authority_status=status,
        canonical_payload_hash=semantic_hash,
        persistent_reference=persistent_ref,
    )


def test_availability_registry_matches_golden() -> None:
    payload = json.loads(_golden_path("availability_registry.json").read_text(encoding="utf-8"))
    registry = build_availability_authority_registry()
    assert [item.model_dump(mode="json") for item in registry] == payload


def test_authority_registry_is_complete_and_unique() -> None:
    registry = build_availability_authority_registry()
    assert {item.source_type for item in registry} == set(AvailabilitySourceType)
    assert len(registry) == len(set(item.source_type for item in registry))


# ═══════════════════════════════════════════════════════════════════════════════
# Task 3 tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_task3_historical_observed_requires_finished_at() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_task3_historical_requires_source_visibility() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_VISIBILITY_MISSING"


def test_task3_historical_visibility_after_cutoff_is_blocked() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(
            visible_through_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF"


def test_task3_historical_visibility_policy_mismatch_is_blocked() -> None:
    visibility = _task3_visibility()
    visibility.visibility_policy_version = "wrong-version"
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
        task3_source_visibility=visibility,
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_VISIBILITY_POLICY_MISMATCH"


def test_task3_evaluator_uses_registry_policy_version() -> None:
    """Prove the evaluator reads policy version from the registry spec, not a constant."""
    spec = get_availability_authority_spec(AvailabilitySourceType.TASK3_ANALYTICS_BUILD)
    assert spec.source_visibility_policy_version == "task11-task3-source-visibility-v1"

    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_replay_execution_after_cutoff_is_allowed_with_typed_task3_visibility() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is True
    assert result.blocker_code is None


def test_task3_replay_missing_visibility_is_blocked() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_VISIBILITY_MISSING"


def test_task3_replay_visibility_after_cutoff_is_blocked() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(
            visible_through_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_CUTOFF_AFTER_FORECAST_CUTOFF"


def test_task3_replay_visibility_policy_mismatch_is_blocked() -> None:
    visibility = _task3_visibility()
    visibility.visibility_policy_version = "wrong-version"
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        task3_source_visibility=visibility,
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "SOURCE_VISIBILITY_POLICY_MISMATCH"


def test_task3_replay_execution_after_cutoff_is_allowed_when_source_visible() -> None:
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 8, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(
            visible_through_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is True


# ═══════════════════════════════════════════════════════════════════════════════
# P0: Parent authority semantic binding tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_parent_status_and_timestamp_without_semantic_hash_is_rejected() -> None:
    """Status + timestamp alone without a stable semantic hash is rejected at schema level."""
    import pytest

    with pytest.raises(
        ValueError, match="parent authority identity must include at least one stable hash"
    ):
        ParentAuthorityIdentity(
            source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
            authority_schema_version="v1",
            authority_policy_version="p1",
            authority_timestamp=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
            authority_status="completed",
        )


def test_task8_artifact_requires_model_run_semantic_identity() -> None:
    """Task 8 artifact must bind to Task 8 model run with stable semantic hash."""
    snapshot = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=_parent_run(
            source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
            semantic_hash="b" * 64,
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_task8_daily_prediction_requires_forecast_run_semantic_identity() -> None:
    """Task 8 daily prediction must bind to forecast run with stable semantic hash."""
    snapshot = Task8DailyPredictionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        prediction_date=date(2026, 2, 28),
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=_parent_run(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            semantic_hash="c" * 64,
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_task10_artifact_requires_training_run_semantic_identity() -> None:
    """Task 10 artifact must bind to training run with stable semantic hash."""
    snapshot = Task10ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=_parent_run(
            source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
            semantic_hash="d" * 64,
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_parent_persistent_reference_does_not_change_authority_audit_hash() -> None:
    """Parent persistent reference changes must not affect the authority audit hash."""
    from backend.app.rolling_backtest.availability import parent_authority_audit_hash

    ref_a = PersistentUpstreamReference(reference_type="database_run_id", reference_value=1)
    ref_b = PersistentUpstreamReference(reference_type="database_run_id", reference_value=2)

    parent_a = _parent_run(persistent_ref=ref_a)
    parent_b = _parent_run(persistent_ref=ref_b)

    assert parent_authority_audit_hash(parent_a) == parent_authority_audit_hash(parent_b)

    # Also verify child audit hash is unaffected
    from backend.app.rolling_backtest.availability import availability_snapshot_audit_hash

    child_a = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent_a,
    )
    child_b = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent_b,
    )
    assert availability_snapshot_audit_hash(child_a) == availability_snapshot_audit_hash(child_b)


def test_wrong_parent_source_type_is_rejected() -> None:
    """Parent source type must match child type expectation at schema validation."""
    import pytest

    with pytest.raises(ValueError, match="Task 8 model artifact parent must be a Task 8 model run"):
        Task8ModelArtifactAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
            created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
            parent_authority=_parent_run(
                source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
                semantic_hash="b" * 64,
            ),
        )


def test_parent_authority_timestamp_after_cutoff_is_blocked() -> None:
    """Parent authority timestamp after forecast cutoff must be blocked."""
    snapshot = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=_parent_run(
            timestamp=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        ),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "PARENT_AUTHORITY_REQUIRED"


# ═══════════════════════════════════════════════════════════════════════════════
# P0: Canonical audit hash regression tests
# ═══════════════════════════════════════════════════════════════════════════════


def _fully_identified_parent(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK8_MODEL_RUN,
    semantic_input_signature: str = "1" * 64,
    result_hash: str = "2" * 64,
    canonical_payload_hash: str = "3" * 64,
    authority_schema_version: str = "task11-parent-auth-v1",
    authority_policy_version: str = "task11-parent-auth-policy-v1",
    authority_timestamp: datetime = datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
    authority_status: str = "completed",
) -> ParentAuthorityIdentity:
    """Construct a parent authority with all three stable hashes populated.

    Each mutation test can call this and override a single field to ensure
    only that field differs between left and right.
    """
    return ParentAuthorityIdentity(
        source_type=source_type,
        authority_schema_version=authority_schema_version,
        authority_policy_version=authority_policy_version,
        authority_timestamp=authority_timestamp,
        authority_status=authority_status,
        semantic_input_signature=semantic_input_signature,
        result_hash=result_hash,
        canonical_payload_hash=canonical_payload_hash,
    )


def test_parent_semantic_input_signature_change_changes_authority_audit_hash() -> None:
    from backend.app.rolling_backtest.availability import (
        parent_authority_audit_hash,
        parent_authority_semantic_payload,
    )

    left = _fully_identified_parent()
    right = _fully_identified_parent(semantic_input_signature="4" * 64)

    left_payload = parent_authority_semantic_payload(left)
    right_payload = parent_authority_semantic_payload(right)
    assert left_payload["semantic_input_signature"] == "1" * 64
    assert right_payload["semantic_input_signature"] == "4" * 64
    assert left_payload["result_hash"] == right_payload["result_hash"] == "2" * 64
    assert (
        left_payload["canonical_payload_hash"]
        == right_payload["canonical_payload_hash"]
        == "3" * 64
    )
    assert parent_authority_audit_hash(left) != parent_authority_audit_hash(right)


def test_parent_result_hash_change_changes_authority_audit_hash() -> None:
    from backend.app.rolling_backtest.availability import (
        parent_authority_audit_hash,
        parent_authority_semantic_payload,
    )

    left = _fully_identified_parent()
    right = _fully_identified_parent(result_hash="5" * 64)

    left_payload = parent_authority_semantic_payload(left)
    right_payload = parent_authority_semantic_payload(right)
    assert left_payload["result_hash"] == "2" * 64
    assert right_payload["result_hash"] == "5" * 64
    assert (
        left_payload["semantic_input_signature"]
        == right_payload["semantic_input_signature"]
        == "1" * 64
    )
    assert (
        left_payload["canonical_payload_hash"]
        == right_payload["canonical_payload_hash"]
        == "3" * 64
    )
    assert parent_authority_audit_hash(left) != parent_authority_audit_hash(right)


def test_parent_canonical_payload_hash_change_changes_authority_audit_hash() -> None:
    from backend.app.rolling_backtest.availability import (
        parent_authority_audit_hash,
        parent_authority_semantic_payload,
    )

    left = _fully_identified_parent()
    right = _fully_identified_parent(canonical_payload_hash="4" * 64)

    left_payload = parent_authority_semantic_payload(left)
    right_payload = parent_authority_semantic_payload(right)
    assert left_payload["canonical_payload_hash"] == "3" * 64
    assert right_payload["canonical_payload_hash"] == "4" * 64
    assert (
        left_payload["semantic_input_signature"]
        == right_payload["semantic_input_signature"]
        == "1" * 64
    )
    assert left_payload["result_hash"] == right_payload["result_hash"] == "2" * 64
    assert parent_authority_audit_hash(left) != parent_authority_audit_hash(right)


def test_parent_policy_version_change_changes_authority_audit_hash() -> None:
    from backend.app.rolling_backtest.availability import (
        parent_authority_audit_hash,
        parent_authority_semantic_payload,
    )

    left = _fully_identified_parent()
    right = _fully_identified_parent(authority_policy_version="task11-parent-auth-policy-v2")

    left_payload = parent_authority_semantic_payload(left)
    right_payload = parent_authority_semantic_payload(right)
    assert left_payload["authority_policy_version"] == "task11-parent-auth-policy-v1"
    assert right_payload["authority_policy_version"] == "task11-parent-auth-policy-v2"
    assert (
        left_payload["semantic_input_signature"]
        == right_payload["semantic_input_signature"]
        == "1" * 64
    )
    assert left_payload["result_hash"] == right_payload["result_hash"] == "2" * 64
    assert (
        left_payload["canonical_payload_hash"]
        == right_payload["canonical_payload_hash"]
        == "3" * 64
    )
    assert parent_authority_audit_hash(left) != parent_authority_audit_hash(right)


def test_parent_schema_version_change_changes_authority_audit_hash() -> None:
    from backend.app.rolling_backtest.availability import (
        parent_authority_audit_hash,
        parent_authority_semantic_payload,
    )

    left = _fully_identified_parent()
    right = _fully_identified_parent(authority_schema_version="task11-parent-auth-v2")

    left_payload = parent_authority_semantic_payload(left)
    right_payload = parent_authority_semantic_payload(right)
    assert left_payload["authority_schema_version"] == "task11-parent-auth-v1"
    assert right_payload["authority_schema_version"] == "task11-parent-auth-v2"
    assert (
        left_payload["semantic_input_signature"]
        == right_payload["semantic_input_signature"]
        == "1" * 64
    )
    assert left_payload["result_hash"] == right_payload["result_hash"] == "2" * 64
    assert (
        left_payload["canonical_payload_hash"]
        == right_payload["canonical_payload_hash"]
        == "3" * 64
    )
    assert parent_authority_audit_hash(left) != parent_authority_audit_hash(right)


def test_child_artifact_audit_hash_binds_parent_semantic_identity() -> None:
    from backend.app.rolling_backtest.availability import (
        availability_snapshot_audit_hash,
        parent_authority_audit_hash,
    )

    parent = _parent_run()
    child = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent,
    )
    child_hash = availability_snapshot_audit_hash(child)

    parent_mutated = _parent_run(semantic_hash="b" * 64)
    child_mutated = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent_mutated,
    )
    child_mutated_hash = availability_snapshot_audit_hash(child_mutated)

    assert parent_authority_audit_hash(parent) != parent_authority_audit_hash(parent_mutated)
    assert child_hash != child_mutated_hash


def test_child_daily_prediction_audit_hash_binds_parent_semantic_identity() -> None:
    from backend.app.rolling_backtest.availability import availability_snapshot_audit_hash

    parent_a = _parent_run(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        semantic_hash="a" * 64,
    )
    child_a = Task8DailyPredictionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        prediction_date=date(2026, 2, 28),
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent_a,
    )

    parent_b = _parent_run(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        semantic_hash="b" * 64,
    )
    child_b = Task8DailyPredictionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        prediction_date=date(2026, 2, 28),
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent_b,
    )

    assert availability_snapshot_audit_hash(child_a) != availability_snapshot_audit_hash(child_b)


def test_child_created_at_change_changes_availability_audit_hash() -> None:
    from backend.app.rolling_backtest.availability import availability_snapshot_audit_hash

    parent = _parent_run()
    child_a = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent,
    )
    child_b = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 11, 0, tzinfo=UTC),
        parent_authority=parent,
    )
    assert availability_snapshot_audit_hash(child_a) != availability_snapshot_audit_hash(child_b)


def test_child_prediction_date_change_changes_availability_audit_hash() -> None:
    from backend.app.rolling_backtest.availability import availability_snapshot_audit_hash

    parent = _parent_run(source_type=AvailabilitySourceType.TASK8_FORECAST_RUN)
    child_a = Task8DailyPredictionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        prediction_date=date(2026, 2, 28),
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent,
    )
    child_b = Task8DailyPredictionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        prediction_date=date(2026, 2, 27),
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent,
    )
    assert availability_snapshot_audit_hash(child_a) != availability_snapshot_audit_hash(child_b)


def test_parent_authority_payload_excludes_persistent_reference() -> None:
    from backend.app.rolling_backtest.availability import parent_authority_semantic_payload

    ref = PersistentUpstreamReference(reference_type="database_run_id", reference_value=77)
    parent = _parent_run(persistent_ref=ref)
    payload = parent_authority_semantic_payload(parent)
    assert "persistent_reference" not in payload
    assert "database_run_id" not in str(payload)
    assert "77" not in str(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# Golden audit hash tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_parent_authority_audit_golden() -> None:
    from backend.app.rolling_backtest.availability import (
        parent_authority_audit_hash,
        parent_authority_semantic_payload,
    )
    from backend.app.rolling_backtest.canonical import canonical_json_dumps

    parent = _parent_run(
        source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
        timestamp=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        semantic_hash="a" * 64,
    )
    payload = json.loads(canonical_json_dumps(parent_authority_semantic_payload(parent)))
    golden = json.loads(_golden_path("authority_audit.json").read_text(encoding="utf-8"))
    assert payload == golden["parent_authority_semantic_payload"]
    assert parent_authority_audit_hash(parent) == golden["parent_authority_audit_hash"]


def test_availability_snapshot_audit_golden() -> None:
    from backend.app.rolling_backtest.availability import (
        availability_snapshot_audit_hash,
        availability_snapshot_audit_payload,
    )
    from backend.app.rolling_backtest.canonical import canonical_json_dumps

    parent = _parent_run(
        source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
        semantic_hash="b" * 64,
    )
    artifact = Task8ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent,
    )
    payload = json.loads(canonical_json_dumps(availability_snapshot_audit_payload(artifact)))
    golden = json.loads(_golden_path("authority_audit.json").read_text(encoding="utf-8"))
    assert payload == golden["artifact_audit_payload"]
    assert availability_snapshot_audit_hash(artifact) == golden["artifact_audit_hash"]


def test_task8_daily_prediction_audit_golden() -> None:
    from backend.app.rolling_backtest.availability import (
        availability_snapshot_audit_hash,
        availability_snapshot_audit_payload,
    )
    from backend.app.rolling_backtest.canonical import canonical_json_dumps

    parent = ParentAuthorityIdentity(
        source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
        authority_schema_version="task11-parent-auth-v1",
        authority_policy_version="task11-parent-auth-policy-v1",
        authority_timestamp=datetime(2026, 2, 28, 9, 0, tzinfo=UTC),
        authority_status="completed",
        semantic_input_signature="1" * 64,
        result_hash="2" * 64,
        canonical_payload_hash="3" * 64,
    )
    snapshot = Task8DailyPredictionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
        prediction_date=date(2026, 3, 1),
        created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
        parent_authority=parent,
    )
    payload = json.loads(canonical_json_dumps(availability_snapshot_audit_payload(snapshot)))
    golden = json.loads(_golden_path("authority_audit.json").read_text(encoding="utf-8"))
    assert payload == golden["daily_prediction_audit_payload"]
    assert availability_snapshot_audit_hash(snapshot) == golden["daily_prediction_audit_hash"]


def test_task10_model_artifact_audit_golden() -> None:
    from backend.app.rolling_backtest.availability import (
        availability_snapshot_audit_hash,
        availability_snapshot_audit_payload,
    )
    from backend.app.rolling_backtest.canonical import canonical_json_dumps

    parent = ParentAuthorityIdentity(
        source_type=AvailabilitySourceType.TASK10_TRAINING_RUN,
        authority_schema_version="task11-parent-auth-v1",
        authority_policy_version="task11-parent-auth-policy-v1",
        authority_timestamp=datetime(2026, 2, 28, 8, 0, tzinfo=UTC),
        authority_status="completed",
        semantic_input_signature="4" * 64,
        result_hash="5" * 64,
        canonical_payload_hash="6" * 64,
    )
    snapshot = Task10ModelArtifactAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK10_MODEL_ARTIFACT,
        created_at=datetime(2026, 2, 28, 11, 0, tzinfo=UTC),
        parent_authority=parent,
    )
    payload = json.loads(canonical_json_dumps(availability_snapshot_audit_payload(snapshot)))
    golden = json.loads(_golden_path("authority_audit.json").read_text(encoding="utf-8"))
    assert payload == golden["task10_artifact_audit_payload"]
    assert availability_snapshot_audit_hash(snapshot) == golden["task10_artifact_audit_hash"]


def test_authority_audit_golden_excludes_persistent_references() -> None:
    """Golden file must not contain persistent_reference, database IDs, or UUIDs."""
    raw = _golden_path("authority_audit.json").read_text(encoding="utf-8")
    assert "persistent_reference" not in raw
    assert "database_run_id" not in raw
    assert "database_artifact_id" not in raw
    assert "uuid" not in raw.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# P1: Typed snapshot tests (old P0-2 regressions preserved)
# ═══════════════════════════════════════════════════════════════════════════════


def test_plan_snapshot_rejects_status() -> None:
    """Task 6 plan has no status field — cannot construct one at schema level."""
    snapshot = Task6PlanVersionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
        available_at=date(2026, 2, 28),
        effective_interval_version="plan-interval-v1",
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_weather_snapshot_rejects_status() -> None:
    """Task 7 weather has no status field."""
    snapshot = Task7WeatherObservationAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
        available_at=date(2026, 2, 28),
        observation_date=date(2026, 2, 28),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is True


def test_artifact_snapshot_rejects_run_status_field() -> None:
    """Artifact snapshots cannot have a 'status' field at schema level."""
    import pytest

    with pytest.raises(ValueError):
        Task8ModelArtifactAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_MODEL_ARTIFACT,
            created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
            parent_authority=_parent_run(),
            status="completed",  # type: ignore[call-arg]
        )


def test_run_snapshot_rejects_artifact_fields() -> None:
    """Run snapshots cannot have artifact-specific fields at schema level."""
    import pytest

    with pytest.raises(ValueError):
        Task8ModelRunAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK8_MODEL_RUN,
            status="completed",
            authoritative_timestamp=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
            created_at=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),  # type: ignore[call-arg]
        )


def test_source_specific_snapshot_rejects_unrelated_fields() -> None:
    """Plan snapshot cannot have a 'status' field — Pydantic rejects extras."""
    import pytest

    with pytest.raises(ValueError):
        Task6PlanVersionAvailabilitySnapshot(
            source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
            available_at=date(2026, 2, 28),
            effective_interval_version="plan-interval-v1",
            status="completed",  # type: ignore[call-arg]
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 10 / existing behavior tests (typed snapshots)
# ═══════════════════════════════════════════════════════════════════════════════


def test_task10_prediction_completed_at_missing_is_rejected() -> None:
    snapshot = Task10PredictionRunAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK10_PREDICTION_RUN,
        status="completed",
        authoritative_timestamp=datetime(2026, 3, 20, 10, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "AUTHORITATIVE_TIMESTAMP_AFTER_CUTOFF"


def test_plan_available_date_uses_explicit_local_date_policy() -> None:
    spec = get_availability_authority_spec(AvailabilitySourceType.TASK6_PLAN_VERSION)
    assert spec.rule_kind == AvailabilityRuleKind.LOCAL_AVAILABLE_DATE
    assert spec.local_date_policy_version == "task11-local-date-visibility-v1"

    snapshot = Task6PlanVersionAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
        available_at=date(2026, 3, 1),
        effective_interval_version="plan-interval-v1",
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "AVAILABLE_ON_LOCAL_DATE_AFTER_AS_OF"


def test_weather_requires_observation_and_available_date() -> None:
    snapshot = Task7WeatherObservationAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
        available_at=date(2026, 2, 28),
        observation_date=date(2026, 3, 1),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.RETROSPECTIVE_REPLAY)
    assert result.allowed is False
    assert result.blocker_code == "OBSERVATION_DATE_AFTER_CUTOFF"


def test_task9_harvest_state_status_is_checked() -> None:
    snapshot = Task9HarvestStateRunAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
        status="running",
        authoritative_timestamp=datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
    )
    result = _evaluate(snapshot, mode=ExecutionMode.HISTORICAL_OBSERVED)
    assert result.allowed is False
    assert result.blocker_code == "STATUS_NOT_ALLOWED"


# ═══════════════════════════════════════════════════════════════════════════════
# P1: Registry single-authority tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_registry_missing_task3_policy_version_is_rejected() -> None:
    """Evaluator must reject when registry spec is missing Task 3 policy version."""
    import pytest

    from backend.app.rolling_backtest.availability import _evaluate_task3
    from backend.app.rolling_backtest.schemas import AvailabilityAuthoritySpec

    spec = AvailabilityAuthoritySpec(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        rule_kind=AvailabilityRuleKind.TASK3_SOURCE_VISIBILITY,
        required_statuses=("completed",),
        authoritative_timestamp_field="finished_at",
        task3_source_visibility_field="task3_source_visibility",
        parent_authority_required=False,
        source_visibility_policy_version=None,
    )
    snapshot = Task3AnalyticsBuildAvailabilitySnapshot(
        source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
        status="completed",
        authoritative_timestamp=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),
        task3_source_visibility=_task3_visibility(),
    )
    with pytest.raises(ValueError, match="task3 source visibility rule requires policy version"):
        _evaluate_task3(
            snapshot=snapshot,
            spec=spec,
            execution_mode=ExecutionMode.HISTORICAL_OBSERVED,
            forecast_cutoff_at=datetime(2026, 2, 28, 15, 59, 59, tzinfo=UTC),
        )
