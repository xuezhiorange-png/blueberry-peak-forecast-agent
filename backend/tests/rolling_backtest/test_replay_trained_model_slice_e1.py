"""TASK-012 Slice E1 — API / CLI exposure contract-test scaffold.

Authority:
- ``docs/task-012-slice-e-api-cli-amendment.md`` §3.1, §10, §11;
- frozen on ``main`` at merge commit
  ``2e03bfad43c9ea624bcea1df29447561b80d1f3c``.

This file activates the Slice E2 application-service and CLI obligations.
The E3 HTTP obligations remain explicit skips until their separately
authorized implementation slice.

The 20 §10 obligations are classified explicitly:

- ``ACTIVE_SLICE_E1`` exercises behavior already supplied by TASK-012
  Slices A-D and therefore must pass in this PR.
- ``ACTIVE_SLICE_E2`` exercises the service/CLI behavior implemented by the
  authorized Slice E2 PR.
- ``OBLIGATION_SLICE_E3`` records HTTP acceptance obligations that cannot
  be made to pass until the separately authorized Slice E3 PR.

Placeholders are visible pytest skips. They are not successful business
executions and must not be interpreted as fulfilled acceptance criteria.
"""

from __future__ import annotations

import inspect
import json
from collections import Counter
from dataclasses import replace
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Final

import pytest

from backend.app.residual_model.schemas import ResidualTrainingSampleSpec
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.rolling_backtest.enums import Task10ModelPolicy
from backend.app.rolling_backtest.node_orchestration import (
    Task10ReplayBindingInvalidError,
)
from backend.app.rolling_backtest.orchestration import OrchestrationBlocker
from backend.app.rolling_backtest.replay_task10_binding import (
    validate_replay_task10_model_policy,
)
from backend.app.rolling_backtest.replay_trained_filtering import (
    FilteredLabelRow,
    FilteredTrainingRow,
    TrainingRowsEmptyError,
    filter_labels_by_availability_cutoff,
    filter_training_rows_by_cutoff,
    require_non_empty_training_rows,
)
from backend.app.rolling_backtest.replay_trained_identity import (
    ModelConfigPayload,
    ReplayTrainedIdentityProjection,
    TrainingManifestPayload,
    project_replay_trained_identity,
)
from backend.app.rolling_backtest.replay_trained_prediction import (
    ArtifactIdentityPair,
    ComparisonRunIdentity,
    ReplayTrainedArtifactIdentityMismatchError,
    ReplayTrainedBindingInput,
    ReplayTrainedPredictionBindingMismatchError,
    bind_replay_trained_prediction,
    verify_comparison_run_separation,
    verify_replay_trained_artifact_identity,
)
from backend.app.rolling_backtest.replay_trained_service import (
    ReplayTrainedExecutionRequest,
    ReplayTrainedServiceBlockerError,
    ReplayTrainedServiceConflictError,
    ReplayTrainedServiceInputError,
    _validate_request,
    execute_replay_trained_prediction,
)


class SliceEClassification(str, Enum):  # noqa: UP042 - explicit string values aid reports
    """Activation state for each frozen Slice E §10 obligation."""

    ACTIVE_SLICE_E1 = "active_slice_e1"
    ACTIVE_SLICE_E2 = "active_slice_e2"
    ACTIVE_SLICE_E3 = "active_slice_e3"


_SECTION_10_REGISTRY: Final[tuple[dict[str, str], ...]] = (
    {
        "name": "test_pre_slice_e_call_paths_still_reject_replay_trained_model",
        "section": "§10 #1",
        "classification": SliceEClassification.ACTIVE_SLICE_E1.value,
    },
    {
        "name": "test_explicit_slice_e_service_accepts_only_replay_trained_model",
        "section": "§10 #2",
        "classification": SliceEClassification.ACTIVE_SLICE_E2.value,
    },
    {
        "name": "test_missing_or_implicit_policy_is_rejected",
        "section": "§10 #3",
        "classification": SliceEClassification.ACTIVE_SLICE_E2.value,
    },
    {
        "name": "test_post_cutoff_features_and_labels_are_excluded",
        "section": "§10 #4",
        "classification": SliceEClassification.ACTIVE_SLICE_E1.value,
    },
    {
        "name": "test_empty_filtered_training_data_returns_canonical_blocker",
        "section": "§10 #5",
        "classification": SliceEClassification.ACTIVE_SLICE_E1.value,
    },
    {
        "name": "test_exact_task9_run_id_and_result_hash_are_required",
        "section": "§10 #6",
        "classification": SliceEClassification.ACTIVE_SLICE_E1.value,
    },
    {
        "name": "test_cross_attempt_cross_node_and_cross_run_substitutions_are_rejected",
        "section": "§10 #7",
        "classification": SliceEClassification.ACTIVE_SLICE_E2.value,
    },
    {
        "name": "test_json_manifest_artifact_mismatch_is_rejected",
        "section": "§10 #8",
        "classification": SliceEClassification.ACTIVE_SLICE_E1.value,
    },
    {
        "name": "test_identical_requests_produce_same_canonical_identities",
        "section": "§10 #9",
        "classification": SliceEClassification.ACTIVE_SLICE_E1.value,
    },
    {
        "name": "test_idempotent_reexecution_returns_same_semantic_result",
        "section": "§10 #10",
        "classification": SliceEClassification.ACTIVE_SLICE_E2.value,
    },
    {
        "name": "test_same_idempotency_key_with_different_payload_conflicts",
        "section": "§10 #11",
        "classification": SliceEClassification.ACTIVE_SLICE_E2.value,
    },
    {
        "name": "test_replay_trained_output_carries_model_policy",
        "section": "§10 #12",
        "classification": SliceEClassification.ACTIVE_SLICE_E1.value,
    },
    {
        "name": "test_historical_and_replay_trained_outputs_remain_separate",
        "section": "§10 #13",
        "classification": SliceEClassification.ACTIVE_SLICE_E1.value,
    },
    {
        "name": "test_cli_rejects_relative_request_and_output_paths",
        "section": "§10 #14",
        "classification": SliceEClassification.ACTIVE_SLICE_E2.value,
    },
    {
        "name": "test_cli_output_is_byte_identical_for_identical_requests",
        "section": "§10 #15",
        "classification": SliceEClassification.ACTIVE_SLICE_E2.value,
    },
    {
        "name": "test_api_first_execution_is_201_and_exact_replay_is_200",
        "section": "§10 #16",
        "classification": SliceEClassification.ACTIVE_SLICE_E3.value,
    },
    {
        "name": "test_api_error_envelopes_are_stable_and_non_leaking",
        "section": "§10 #17",
        "classification": SliceEClassification.ACTIVE_SLICE_E3.value,
    },
    {
        "name": "test_get_requires_exact_prediction_run_id",
        "section": "§10 #18",
        "classification": SliceEClassification.ACTIVE_SLICE_E3.value,
    },
    {
        "name": "test_api_and_cli_do_not_use_implicit_latest_selection",
        "section": "§10 #19",
        "classification": SliceEClassification.ACTIVE_SLICE_E2.value,
    },
    {
        "name": "test_historically_available_replay_gate_remains_unchanged",
        "section": "§10 #20",
        "classification": SliceEClassification.ACTIVE_SLICE_E1.value,
    },
)


def _utc(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 3, day, hour, 0, 0, tzinfo=UTC)


def _projection() -> ReplayTrainedIdentityProjection:
    manifest = TrainingManifestPayload(
        replay_attempt_id="attempt-e1",
        replay_node_id="node-e1",
        scenario_id="scenario-e1",
        forecast_cutoff_at=_utc(15),
        training_cutoff_at=_utc(14),
        allowed_training_season_ids=(2025,),
        feature_visibility_policy_version="task12-e1-feature-v1",
        label_visibility_policy_version="task12-e1-label-v1",
        artifact_visibility_policy_version="task12-e1-artifact-v1",
        validation_policy_version="task12-e1-validation-v1",
        training_dataset_hash="1" * 64,
        task8_curve_identity="task8-curve-e1",
        task9_replay_binding_identity="task9-binding-e1",
        row_count=2,
        excluded_row_count=1,
    )
    config = ModelConfigPayload(
        algorithm_family="task12-e1-contract",
        hyperparameters={"max_depth": 3, "shuffle": False},
        random_seed=20260710,
        deterministic_serialization_version="task12-e1-json-v1",
    )
    return project_replay_trained_identity(
        manifest=manifest,
        config=config,
        model_code_version="task10-code-e1",
        task12_policy_version="task12-policy-e1",
    )


def _artifact_identity_payload(
    projection: ReplayTrainedIdentityProjection,
) -> dict[str, object]:
    return {
        "model_policy": Task10ModelPolicy.REPLAY_TRAINED_MODEL.value,
        "task12_policy_version": projection.task12_policy_version,
        "replay_attempt_id": projection.manifest.replay_attempt_id,
        "replay_node_id": projection.manifest.replay_node_id,
        "forecast_cutoff_at": projection.manifest.forecast_cutoff_at,
        "training_cutoff_at": projection.manifest.training_cutoff_at,
        "training_manifest_hash": projection.training_manifest_hash,
        "training_dataset_hash": projection.manifest.training_dataset_hash,
        "model_config_hash": projection.model_config_hash,
        "model_artifact_hash": projection.model_artifact_hash,
        "model_code_version": projection.model_code_version,
    }


def _binding_input(
    *,
    task9_run_id: int = 91,
    task9_result_hash: str = "9" * 64,
    replay_attempt_id: str = "attempt-e1",
    replay_node_id: str = "node-e1",
) -> ReplayTrainedBindingInput:
    return ReplayTrainedBindingInput(
        prediction_run_id=1201,
        projection=_projection(),
        task9_run_id=task9_run_id,
        task9_result_hash=task9_result_hash,
        replay_code_version="task11-replay-e1",
        is_replay=True,
        replay_attempt_id=replay_attempt_id,
        replay_node_id=replay_node_id,
    )


def _task10_config_snapshot() -> dict[str, object]:
    from backend.app.residual_model.config import load_residual_model_config

    config = load_residual_model_config(Path("configs/residual_model.yaml"))
    snapshot = dict(config.snapshot)
    snapshot["eligibility"] = {
        **dict(snapshot["eligibility"]),
        "min_training_rows": 0,
        "min_seasons": 0,
        "min_factories": 0,
        "max_validation_wmape": 10.0,
        "require_improvement_over_structural": False,
        "max_fallback_rate": 1.0,
    }
    return snapshot


def _service_request(*, idempotency_key: str) -> ReplayTrainedExecutionRequest:
    task9_binding_identity = sha256_payload(
        {
            "task9_run_id": 91,
            "task9_result_hash": "9" * 64,
            "is_replay": True,
            "replay_code_version": "task12-replay-e2",
        }
    )
    manifest = TrainingManifestPayload(
        replay_attempt_id="attempt-e2",
        replay_node_id="node-e2",
        scenario_id="scenario-e2",
        forecast_cutoff_at=_utc(15),
        training_cutoff_at=_utc(14),
        allowed_training_season_ids=(2023, 2024, 2025),
        feature_visibility_policy_version="task12-e2-feature-v1",
        label_visibility_policy_version="task12-e2-label-v1",
        artifact_visibility_policy_version="task12-e2-artifact-v1",
        validation_policy_version="task12-e2-validation-v1",
        training_dataset_hash="1" * 64,
        task8_curve_identity="task8-curve-e2",
        task9_replay_binding_identity=task9_binding_identity,
        row_count=3,
        excluded_row_count=0,
    )
    model_config = ModelConfigPayload(
        algorithm_family="task12-e2-contract",
        hyperparameters={"max_depth": 3, "shuffle": False},
        random_seed=20260710,
        deterministic_serialization_version="task12-e2-json-v1",
    )
    projection = project_replay_trained_identity(
        manifest=manifest,
        config=model_config,
        model_code_version="task10-code-e2",
        task12_policy_version="task12-policy-e2",
    )
    artifact_payload = _artifact_identity_payload(projection)
    return ReplayTrainedExecutionRequest(
        model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        task12_policy_version="task12-policy-e2",
        replay_attempt_id="attempt-e2",
        replay_node_id="node-e2",
        scenario_id="scenario-e2",
        forecast_cutoff_at=_utc(15),
        training_cutoff_at=_utc(14),
        allowed_training_season_ids=(2023, 2024, 2025),
        training_manifest=manifest,
        model_config=model_config,
        model_code_version="task10-code-e2",
        replay_code_version="task12-replay-e2",
        task9_run_id=91,
        task9_result_hash="9" * 64,
        is_replay=True,
        task10_config_snapshot=_task10_config_snapshot(),
        manifest_rows_payload=(
            {"season_id": 2025, "destination_factory_id": 1, "split": "train"},
            {"season_id": 2024, "destination_factory_id": 1, "split": "validation"},
            {"season_id": 2023, "destination_factory_id": 1, "split": "test"},
        ),
        training_rows=(
            {"observation_date": "2026-03-13", "value": 1},
            {"observation_date": "2026-03-14", "value": 2},
            {"observation_date": "2026-03-16", "value": 3},
        ),
        label_rows=(
            {
                "observation_date": "2026-03-13",
                "label_availability_date": "2026-03-14",
                "value": 10,
            },
            {
                "observation_date": "2026-03-14",
                "label_availability_date": "2026-03-16",
                "value": 20,
            },
        ),
        source_run_ids={"task9a_run_id": 91},
        artifact_identity_json=artifact_payload,
        artifact_identity_manifest=dict(artifact_payload),
        feature_actual_snapshot={"source": "explicit-e2-fixture"},
        idempotency_key=idempotency_key,
        caller_identity="test:e2",
        training_samples=(
            ResidualTrainingSampleSpec(
                task9_run_id=91,
                label_analytics_build_run_id=1,
                feature_analytics_build_run_id=2,
                split="train",
            ),
        ),
    )


def _skip_obligation(*, section: str, future_slice: str, requirement: str) -> None:
    pytest.skip(
        f"{section} contract pin awaits separately authorized {future_slice}: "
        f"{requirement}; no successful result may be fabricated in Slice E1"
    )


def test_pre_slice_e_call_paths_still_reject_replay_trained_model() -> None:
    """§10 #1 — the legacy replay gate remains closed."""

    with pytest.raises(Task10ReplayBindingInvalidError):
        validate_replay_task10_model_policy(
            requested_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        )


async def test_explicit_slice_e_service_accepts_only_replay_trained_model() -> None:
    """§10 #2 — service policy acceptance is activated in Slice E2."""

    request = _service_request(idempotency_key="e2-policy")
    _validate_request(request)
    assert request.model_policy is Task10ModelPolicy.REPLAY_TRAINED_MODEL


async def test_missing_or_implicit_policy_is_rejected() -> None:
    """§10 #3 — request-schema policy validation is activated in Slice E2."""

    request = _service_request(idempotency_key="e2-policy-invalid")
    with pytest.raises(ReplayTrainedServiceInputError) as missing:
        _validate_request(replace(request, model_policy=None))
    assert missing.value.code == "TASK012_REPLAY_TRAINED_INPUT_INVALID"

    with pytest.raises(ReplayTrainedServiceInputError) as historical:
        _validate_request(
            replace(
                request,
                model_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
            )
        )
    assert historical.value.code == "TASK012_REPLAY_TRAINED_INPUT_INVALID"


def test_post_cutoff_features_and_labels_are_excluded() -> None:
    """§10 #4 — Slice C cutoff helpers exclude post-cutoff authority."""

    training_rows = (
        FilteredTrainingRow(observation_date=date(2026, 3, 13), value=1.0),
        FilteredTrainingRow(observation_date=date(2026, 3, 14), value=2.0),
        FilteredTrainingRow(observation_date=date(2026, 3, 15), value=3.0),
    )
    kept_training = filter_training_rows_by_cutoff(
        training_rows,
        training_cutoff_at=date(2026, 3, 14),
    )
    assert tuple(row.observation_date for row in kept_training) == (
        date(2026, 3, 13),
        date(2026, 3, 14),
    )

    label_rows = (
        FilteredLabelRow(
            observation_date=date(2026, 3, 12),
            label_availability_date=date(2026, 3, 13),
            value=10.0,
        ),
        FilteredLabelRow(
            observation_date=date(2026, 3, 13),
            label_availability_date=date(2026, 3, 14),
            value=20.0,
        ),
        FilteredLabelRow(
            observation_date=date(2026, 3, 13),
            label_availability_date=date(2026, 3, 15),
            value=30.0,
        ),
    )
    kept_labels = filter_labels_by_availability_cutoff(
        label_rows,
        label_availability_cutoff_at=date(2026, 3, 14),
    )
    assert tuple(row.value for row in kept_labels) == (10.0, 20.0)


def test_empty_filtered_training_data_returns_canonical_blocker() -> None:
    """§10 #5 — empty training data carries the frozen blocker and payload."""

    with pytest.raises(TrainingRowsEmptyError) as first:
        require_non_empty_training_rows(
            (),
            training_cutoff_at=date(2026, 3, 14),
            candidate_row_count=3,
        )
    with pytest.raises(TrainingRowsEmptyError) as second:
        require_non_empty_training_rows(
            (),
            training_cutoff_at=date(2026, 3, 14),
            candidate_row_count=3,
        )

    assert first.value.blocker_code == OrchestrationBlocker.TASK12_TRAINING_ROWS_EMPTY.value
    assert first.value.payload == second.value.payload
    assert '"candidate_row_count":3' in first.value.payload
    assert '"kept_row_count":0' in first.value.payload


def test_exact_task9_run_id_and_result_hash_are_required() -> None:
    """§10 #6 — missing Task 9 identity is rejected before binding."""

    with pytest.raises(ReplayTrainedPredictionBindingMismatchError) as bad_run:
        bind_replay_trained_prediction(_binding_input(task9_run_id=0))
    assert "task9_run_id_must_be_positive" in bad_run.value.mismatched_fields

    with pytest.raises(ReplayTrainedPredictionBindingMismatchError) as bad_hash:
        bind_replay_trained_prediction(_binding_input(task9_result_hash=""))
    assert "task9_result_hash_must_be_64_hex" in bad_hash.value.mismatched_fields


async def test_cross_attempt_cross_node_and_cross_run_substitutions_are_rejected() -> None:
    """§10 #7 — full service-context substitution checks activate in E2."""

    request = _service_request(idempotency_key="e2-binding")
    with pytest.raises(ReplayTrainedServiceBlockerError) as exc_info:
        _validate_request(replace(request, replay_attempt_id="other-attempt"))
    assert exc_info.value.blocker_code == OrchestrationBlocker.TASK12_CROSS_RUN_SUBSTITUTION.value
    assert '"blocker":"task12_cross_run_substitution"' in exc_info.value.payload


def test_json_manifest_artifact_mismatch_is_rejected() -> None:
    """§10 #8 — Slice D rejects field-level artifact identity drift."""

    projection = _projection()
    json_side = _artifact_identity_payload(projection)
    manifest_side = dict(json_side)
    manifest_side["model_artifact_hash"] = "f" * 64

    with pytest.raises(ReplayTrainedArtifactIdentityMismatchError) as exc_info:
        verify_replay_trained_artifact_identity(
            ArtifactIdentityPair(
                json_side=json_side,
                manifest_side=manifest_side,
            ),
            projection=projection,
        )

    assert exc_info.value.mismatched_fields == ("model_artifact_hash",)
    assert (
        exc_info.value.blocker_code == OrchestrationBlocker.TASK12_ARTIFACT_IDENTITY_MISMATCH.value
    )


def test_identical_requests_produce_same_canonical_identities() -> None:
    """§10 #9 — identical explicit identity inputs hash identically."""

    first = _projection()
    second = _projection()

    assert first.training_manifest_hash == second.training_manifest_hash
    assert first.model_config_hash == second.model_config_hash
    assert first.model_artifact_hash == second.model_artifact_hash
    assert _artifact_identity_payload(first) == _artifact_identity_payload(second)


def test_idempotent_reexecution_returns_same_semantic_result() -> None:
    """§10 #10 — service idempotency activates in Slice E2."""

    request = _service_request(idempotency_key="e2-idempotent")
    assert request.canonical_identity_payload(
        task10_config_hash="a" * 64
    ) == request.canonical_identity_payload(task10_config_hash="a" * 64)


def test_same_idempotency_key_with_different_payload_conflicts() -> None:
    """§10 #11 — service conflict semantics activate in Slice E2."""

    source = inspect.getsource(execute_replay_trained_prediction)
    assert "_IDEMPOTENCY_RESULTS" not in source
    assert "input_snapshot" in source
    conflict = ReplayTrainedServiceConflictError(
        "idempotency key conflict",
        mismatched_fields=("idempotency_key_payload_mismatch",),
    )
    assert conflict.code == "TASK012_REPLAY_TRAINED_CONFLICT"
    assert "idempotency_key_payload_mismatch" in conflict.mismatched_fields


def test_replay_trained_output_carries_model_policy() -> None:
    """§10 #12 — Slice D binding emits replay_trained_model explicitly."""

    binding = bind_replay_trained_prediction(_binding_input())

    assert binding.model_policy is Task10ModelPolicy.REPLAY_TRAINED_MODEL
    assert binding.model_policy.value == "replay_trained_model"
    assert binding.is_replay is True


def test_historical_and_replay_trained_outputs_remain_separate() -> None:
    """§10 #13 — comparison identities cannot be shared across policies."""

    separated = ComparisonRunIdentity(
        historical_prediction_run_id=100,
        historical_prediction_hash="a" * 64,
        historical_model_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        historical_artifact_identity="historical-artifact",
        replay_trained_prediction_run_id=101,
        replay_trained_prediction_hash="b" * 64,
        replay_trained_model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        replay_trained_artifact_identity="replay-artifact",
        audit_identity="audit-e1",
    )
    verify_comparison_run_separation(separated)

    shared = ComparisonRunIdentity(
        historical_prediction_run_id=100,
        historical_prediction_hash="a" * 64,
        historical_model_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
        historical_artifact_identity="historical-artifact",
        replay_trained_prediction_run_id=100,
        replay_trained_prediction_hash="b" * 64,
        replay_trained_model_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        replay_trained_artifact_identity="replay-artifact",
        audit_identity="audit-e1",
    )
    with pytest.raises(ReplayTrainedPredictionBindingMismatchError) as exc_info:
        verify_comparison_run_separation(shared)
    assert "prediction_run_id_must_be_distinct" in exc_info.value.mismatched_fields


def test_cli_rejects_relative_request_and_output_paths() -> None:
    """§10 #14 — CLI path grammar activates in Slice E2."""

    from backend.app.rolling_backtest.cli import EXIT_USAGE_ERROR, main

    assert (
        main(
            [
                "replay-trained-predict",
                "--request-json",
                "relative-request.json",
                "--output-json",
                str(Path.cwd() / "e2-output.json"),
            ]
        )
        == EXIT_USAGE_ERROR
    )
    assert (
        main(
            [
                "replay-trained-predict",
                "--request-json",
                str(Path.cwd() / "e2-request.json"),
                "--output-json",
                "relative-output.json",
            ]
        )
        == EXIT_USAGE_ERROR
    )


def test_cli_output_is_byte_identical_for_identical_requests(
    tmp_path: Path,
) -> None:
    """§10 #15 — CLI deterministic serialization activates in Slice E2."""

    output_path = tmp_path / "output.json"
    from backend.app.rolling_backtest.cli import _write_replay_result

    payload = b'{"prediction_hash":"abc"}'
    assert _write_replay_result(output_path, payload, overwrite="always") is False
    first = output_path.read_bytes()
    assert _write_replay_result(output_path, payload, overwrite="missing") is True
    assert output_path.read_bytes() == first


def test_cli_maps_replay_trained_service_conflict_to_exit_code_five(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Service-level conflict surfaces as EXIT_HASH_COLLISION (5).

    The frozen contract distinguishes three rejection shapes at the
    CLI:

    - request / policy input error  → EXIT_SERVICE_CONTRACT_ERROR (2)
    - structured blocker            → EXIT_METRIC_BLOCKER (3)
    - idempotency / hash / path
      conflict                       → EXIT_HASH_COLLISION (5)

    ``ReplayTrainedServiceConflictError`` carries the stable code
    ``TASK012_REPLAY_TRAINED_CONFLICT`` and a ``None`` blocker_code. The
    CLI must route it to exit code 5 (not 2), emit the JSON envelope
    on stdout, and emit a single-line deterministic diagnostic on
    stderr. This test exercises ``main(...)`` end-to-end with
    ``_execute_replay_trained_request`` monkeypatched so no database or
    service-side persistence is required.
    """
    from backend.app.rolling_backtest import cli as rolling_cli
    from backend.app.rolling_backtest.cli import (
        EXIT_HASH_COLLISION,
        EXIT_METRIC_BLOCKER,
        EXIT_SERVICE_CONTRACT_ERROR,
        main,
    )
    from backend.app.rolling_backtest.replay_trained_service import (
        ReplayTrainedServiceBlockerError,
        ReplayTrainedServiceConflictError,
        ReplayTrainedServiceInputError,
    )

    # Build a valid request and write it to disk so the CLI's path
    # grammar + JSON loader succeed and execution reaches the service
    # call.
    request = _service_request(idempotency_key="e2-conflict-cli")
    request_payload = json.loads(json.dumps(request.to_payload()))
    request_path = tmp_path / "e2-conflict-request.json"
    request_path.write_text(
        json.dumps(request_payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    output_path = tmp_path / "e2-conflict-output.json"

    def _raise_conflict(_request: ReplayTrainedExecutionRequest) -> object:
        raise ReplayTrainedServiceConflictError(
            "idempotency key conflict",
            mismatched_fields=("idempotency_key_payload_mismatch",),
        )

    monkeypatch.setattr(rolling_cli, "_execute_replay_trained_request", _raise_conflict)

    # 1. Conflict → exit 5, with stable envelope + stderr.
    rc = main(
        [
            "replay-trained-predict",
            "--request-json",
            str(request_path),
            "--output-json",
            str(output_path),
        ]
    )
    assert rc == EXIT_HASH_COLLISION
    assert rc == 5
    captured = capsys.readouterr()
    envelope = json.loads(captured.out.strip())
    # The CLI emits a stable JSON envelope on stdout. The exact field
    # set is the frozen contract from §4.5; this assertion pins the
    # machine-readable surface and the human-readable stderr line.
    assert envelope["error"]["code"] == "TASK012_REPLAY_TRAINED_CONFLICT"
    assert envelope["error"]["blocker"] is None
    assert envelope["error"]["identity"]["mismatched_fields"] == [
        "idempotency_key_payload_mismatch"
    ]
    assert "idempotency key conflict" in envelope["error"]["message"]
    assert "error: TASK012_REPLAY_TRAINED_CONFLICT" in captured.err.splitlines()
    assert not output_path.exists(), "conflict must not produce an output file"

    # 2. Input / policy error → exit 2 (regression for non-conflict
    # service error path).
    def _raise_input(_request: ReplayTrainedExecutionRequest) -> object:
        raise ReplayTrainedServiceInputError(
            "policy invalid",
            mismatched_fields=("model_policy_required",),
        )

    monkeypatch.setattr(rolling_cli, "_execute_replay_trained_request", _raise_input)
    rc_input = main(
        [
            "replay-trained-predict",
            "--request-json",
            str(request_path),
            "--output-json",
            str(output_path),
        ]
    )
    assert rc_input == EXIT_SERVICE_CONTRACT_ERROR
    assert rc_input == 2

    # 3. Blocker → exit 3 (regression for structured blocker path).
    def _raise_blocker(_request: ReplayTrainedExecutionRequest) -> object:
        raise ReplayTrainedServiceBlockerError(
            "training rows empty",
            blocker_code="task12_training_rows_empty",
            mismatched_fields=("training_rows_empty",),
        )

    monkeypatch.setattr(rolling_cli, "_execute_replay_trained_request", _raise_blocker)
    rc_blocker = main(
        [
            "replay-trained-predict",
            "--request-json",
            str(request_path),
            "--output-json",
            str(output_path),
        ]
    )
    assert rc_blocker == EXIT_METRIC_BLOCKER
    assert rc_blocker == 3


async def test_api_first_execution_is_201_and_exact_replay_is_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§10 #16 — HTTP status semantics activate in Slice E3.

    The test exercises the POST endpoint through a real ASGI transport.
    First execution returns 201 Created; an exact idempotent replay
    (same canonical request) returns 200 OK. The HTTP layer delegates
    to the Slice E2 service; the test patches the service boundary
    so the service returns ``created=True`` on the first call and
    ``created=False`` on the second call. The HTTP layer reads the
    disposition from the service result and MUST NOT recompute it.
    """
    import httpx
    from httpx import ASGITransport

    from backend.app.api import rolling_backtest_replay_trained
    from backend.app.main import create_app
    from backend.tests.rolling_backtest.test_replay_trained_model_slice_e1 import (
        _service_request,
    )

    recorded: list[tuple[str, bool]] = []

    class _StubResult:
        def __init__(self, created: bool) -> None:
            self.created = created
            self.prediction_run_id = 4242
            self.prediction_hash = "p" * 64
            self.request_payload_hash = "h" * 64
            self.training_manifest_hash = "m" * 64
            self.model_config_hash = "c" * 64
            self.model_artifact_hash = "a" * 64
            self.task9_run_id = 91
            self.task9_result_hash = "9" * 64
            self.filtered_training_row_count = 3
            self.filtered_label_row_count = 2
            self.training_execution_status = "completed"
            self.training_eligibility_status = "eligible"
            self.prediction_execution_status = "completed"
            self.prediction_mode = "residual_corrected"
            self.audit_identity = "audit-" + "x" * 56

        def to_payload(self) -> dict[str, object]:
            return {
                "service_version": "task12-slice-e3-test",
                "model_policy": "replay_trained_model",
                "task12_policy_version": "task12-policy-e3",
                "replay_attempt_id": "attempt-e3",
                "replay_node_id": "node-e3",
                "scenario_id": "scenario-e3",
                "training_manifest_hash": "m" * 64,
                "training_dataset_hash": "d" * 64,
                "model_config_hash": "c" * 64,
                "model_artifact_hash": "a" * 64,
                "model_code_version": "task10-code-e3",
                "forecast_cutoff_at": "2026-03-15T12:00:00Z",
                "training_cutoff_at": "2026-03-14T12:00:00Z",
                "task9_run_id": 91,
                "task9_result_hash": "9" * 64,
                "prediction_run_id": 4242,
                "prediction_hash": "p" * 64,
                "request_payload_hash": "h" * 64,
                "filtered_training_row_count": 3,
                "filtered_label_row_count": 2,
                "training_execution_status": "completed",
                "training_eligibility_status": "eligible",
                "prediction_execution_status": "completed",
                "prediction_mode": "residual_corrected",
                "task10_training_run_id": 7,
                "task10_training_signature": "s" * 64,
                "task10_manifest_hash": "mh" * 32,
                "task10_config_hash": "ch" * 32,
                "task10_artifact_hashes": ["ah" * 32],
                "idempotency_key": "idem-e3-16",
                "caller_identity": "test:e3-16",
                "no_implicit_selection": True,
                "no_cross_run_substitution": True,
            }

    async def _fake_execute(session: object, *, request: object) -> _StubResult:
        is_replay = bool(recorded)
        recorded.append((getattr(request, "idempotency_key", ""), is_replay))  # type: ignore[arg-type]
        return _StubResult(created=not is_replay)

    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _fake_execute,
    )

    request = _service_request(idempotency_key="idem-e3-16")
    body = request.to_payload()
    body["idempotency_key"] = "idem-e3-16"

    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
        assert first.status_code == 201, first.text
        first_payload = first.json()
        assert first_payload["disposition"] == "created"
        assert first_payload["prediction_run_id"] == 4242
        assert first_payload["audit_identity"].startswith("audit-")

        second = await client.post("/api/v1/rolling-backtest/replay-trained-predictions", json=body)
        assert second.status_code == 200, second.text
        second_payload = second.json()
        assert second_payload["disposition"] == "idempotent_replay"
        # All canonical identity fields must match; only ``disposition`` may differ
        for key, value in first_payload.items():
            if key == "disposition":
                continue
            assert second_payload.get(key) == value, (key, value, second_payload.get(key))


async def test_api_error_envelopes_are_stable_and_non_leaking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§10 #17 — HTTP error envelopes activate in Slice E3.

    Stable 404 / 409 / 422 / 500 transport envelopes must not leak
    SQL text, traceback text, file paths, or environment variables.
    """
    import httpx
    from httpx import ASGITransport

    from backend.app.api import rolling_backtest_replay_trained
    from backend.app.main import create_app
    from backend.app.rolling_backtest.replay_trained_service import (
        ReplayTrainedServiceInputError,
    )
    from backend.tests.rolling_backtest.test_replay_trained_model_slice_e1 import (
        _service_request,
    )

    async def _raise_input_error(session: object, *, request: object) -> object:
        raise ReplayTrainedServiceInputError(
            "internal-impl-detail: /var/secrets/db/credentials.txt leaked",
            mismatched_fields=("shape",),
        )

    async def _raise_unexpected(session: object, *, request: object) -> object:
        raise RuntimeError(
            "Traceback (most recent call last):\n"
            "  File '/srv/blueberry/replay_trained_service.py', line 9999\n"
            "    raise SQLAlchemyError('DSN=postgres://root:***@host/db')\n"
        )

    app = create_app()
    transport = ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 422 — request shape is not a JSON object
        shape_response = await client.post(
            "/api/v1/rolling-backtest/replay-trained-predictions", json=[1, 2, 3]
        )
        assert shape_response.status_code == 422
        shape_body = shape_response.json()
        assert shape_body["error"]["code"] == "TASK012_REPLAY_TRAINED_INPUT_INVALID"
        assert "credentials.txt" not in shape_response.text
        assert "Traceback" not in shape_response.text
        assert "SQLAlchemy" not in shape_response.text

        # 422 — missing required identity
        missing_body = {
            "idempotency_key": "idem-missing",
            "model_policy": "replay_trained_model",
        }
        missing_response = await client.post(
            "/api/v1/rolling-backtest/replay-trained-predictions", json=missing_body
        )
        assert missing_response.status_code == 422
        assert missing_response.json()["error"]["code"] == ("TASK012_REPLAY_TRAINED_INPUT_INVALID")

        # 500 — internal exception, must not leak traceback / SQL / path / secret
        request = _service_request(idempotency_key="idem-e3-17")
        body = request.to_payload()
        body["idempotency_key"] = "idem-e3-17"
        monkeypatch.setattr(
            rolling_backtest_replay_trained,
            "execute_replay_trained_prediction",
            _raise_unexpected,
        )
        unexpected_response = await client.post(
            "/api/v1/rolling-backtest/replay-trained-predictions", json=body
        )
        assert unexpected_response.status_code == 500
        unexpected_body = unexpected_response.json()
        assert unexpected_body["error"]["code"] == ("TASK012_REPLAY_TRAINED_INTEGRITY")
        leaked_text = unexpected_response.text
        for forbidden in (
            "Traceback",
            "SQLAlchemy",
            "postgres://",
            "hunter2",
            "/srv/blueberry",
            "replay_trained_service.py",
            "DSN=",
        ):
            assert forbidden not in leaked_text, forbidden

        # Reset monkeypatch and test 422 via service InputError
        monkeypatch.setattr(
            rolling_backtest_replay_trained,
            "execute_replay_trained_prediction",
            _raise_input_error,
        )
        leaked_response = await client.post(
            "/api/v1/rolling-backtest/replay-trained-predictions", json=body
        )
        assert leaked_response.status_code == 422
        leaked_body = leaked_response.json()
        assert leaked_body["error"]["code"] == ("TASK012_REPLAY_TRAINED_INPUT_INVALID")
        # The internal-impl-detail string from the InputError MUST NOT
        # be reflected into the stable 422 envelope.
        assert "/var/secrets" not in leaked_response.text


async def test_get_requires_exact_prediction_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§10 #18 — exact retrieval semantics activate in Slice E3.

    The GET endpoint must:
    * return 200 with the persisted TASK-012 identity for the exact
      ``prediction_run_id`` it is asked for;
    * return 404 when the ``prediction_run_id`` is not found;
    * never accept / infer ``latest`` / ``current`` / ``most_recent``
      selectors and must not re-execute training or prediction.
    """
    import httpx
    from httpx import ASGITransport

    from backend.app.api import rolling_backtest_replay_trained
    from backend.app.main import create_app
    from backend.app.rolling_backtest.replay_trained_service import (
        ReplayTrainedPersistedIdentity,
        ReplayTrainedServiceNotFoundError,
    )

    async def _fake_load(
        session: object, *, prediction_run_id: int
    ) -> ReplayTrainedPersistedIdentity:
        if prediction_run_id != 4242:
            raise ReplayTrainedServiceNotFoundError(
                "the requested replay-trained prediction was not found",
                identity={"prediction_run_id": prediction_run_id},
            )
        return ReplayTrainedPersistedIdentity(
            prediction_run_id=prediction_run_id,
            prediction_hash="z" * 64,
            request_payload_hash="h" * 64,
            model_policy="replay_trained_model",
            task12_policy_version="task12-policy-e3",
            replay_attempt_id="attempt-e3",
            replay_node_id="node-e3",
            scenario_id="scenario-e3",
            training_manifest_hash="m" * 64,
            training_dataset_hash="d" * 64,
            model_config_hash="c" * 64,
            model_artifact_hash="a" * 64,
            model_code_version="task10-code-e3",
            forecast_cutoff_at="2026-03-15T12:00:00Z",
            training_cutoff_at="2026-03-14T12:00:00Z",
            task9_run_id=91,
            task9_result_hash="9" * 64,
            task10_training_run_id=7,
            task10_training_signature="s" * 64,
            task10_manifest_hash="mh" * 32,
            task10_config_hash="ch" * 32,
            task10_artifact_hashes=("ah" * 32,),
            filtered_training_row_count=3,
            filtered_label_row_count=2,
            training_execution_status="completed",
            training_eligibility_status="eligible",
            prediction_execution_status="completed",
            prediction_mode="residual_corrected",
            idempotency_key="idem-e3-18",
            caller_identity="test:e3-18",
            audit_identity="audit-" + "y" * 56,
        )

    async def _service_should_not_run(session: object, *, request: object) -> object:
        service_called.append(True)
        raise AssertionError("GET endpoint must not call the Slice E2 service")

    service_called: list[bool] = []
    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "load_replay_trained_prediction",
        _fake_load,
    )
    monkeypatch.setattr(
        rolling_backtest_replay_trained,
        "execute_replay_trained_prediction",
        _service_should_not_run,
    )

    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        exact = await client.get("/api/v1/rolling-backtest/replay-trained-predictions/4242")
        assert exact.status_code == 200
        exact_body = exact.json()
        assert exact_body["prediction_run_id"] == 4242
        assert exact_body["audit_identity"].startswith("audit-")
        assert exact_body["model_policy"] == "replay_trained_model"

        missing = await client.get("/api/v1/rolling-backtest/replay-trained-predictions/9999")
        assert missing.status_code == 404
        missing_body = missing.json()
        assert missing_body["error"]["code"] == "TASK012_REPLAY_TRAINED_NOT_FOUND"
        # The error envelope from ReplayTrainedServiceNotFoundError wraps the
        # identity dict in ``error.details.prediction_run_id`` (not
        # ``error.identity.prediction_run_id``).
        assert missing_body["error"]["details"]["prediction_run_id"] == 9999

    # GET must never re-execute the Slice E2 service
    assert service_called == []


def test_api_and_cli_do_not_use_implicit_latest_selection() -> None:
    """§10 #19 — adapter source scanning activates with Slice E2/E3 files."""

    from backend.app.rolling_backtest import cli as rolling_cli
    from backend.app.rolling_backtest import replay_trained_service

    source = inspect.getsource(rolling_cli._handle_replay_trained_predict)
    source += inspect.getsource(replay_trained_service.execute_replay_trained_prediction)
    for forbidden in ("latest", "most_recent", "current_data", "now()"):
        assert forbidden not in source


def test_historically_available_replay_gate_remains_unchanged() -> None:
    """§10 #20 — the existing historical replay policy remains accepted."""

    accepted = validate_replay_task10_model_policy(
        requested_policy=Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL,
    )
    assert accepted is Task10ModelPolicy.HISTORICALLY_AVAILABLE_MODEL

    with pytest.raises(Task10ReplayBindingInvalidError):
        validate_replay_task10_model_policy(
            requested_policy=Task10ModelPolicy.REPLAY_TRAINED_MODEL,
        )


def test_slice_e1_registry_has_exact_twenty_item_contract_surface() -> None:
    """Meta — all 20 frozen §10 requirements are present once."""

    assert len(_SECTION_10_REGISTRY) == 20
    assert {entry["section"] for entry in _SECTION_10_REGISTRY} == {
        f"§10 #{index}" for index in range(1, 21)
    }
    names = [entry["name"] for entry in _SECTION_10_REGISTRY]
    assert len(names) == len(set(names))


def test_slice_e1_registry_names_resolve_to_test_functions() -> None:
    """Meta — registry entries cannot drift from collected test names."""

    for entry in _SECTION_10_REGISTRY:
        test_function = globals().get(entry["name"])
        assert callable(test_function), f"missing contract test: {entry['name']}"


def test_slice_e1_classification_counts_are_explicit() -> None:
    """Meta — active and future obligations cannot be reported as one bucket."""

    counts = Counter(entry["classification"] for entry in _SECTION_10_REGISTRY)
    assert counts == {
        SliceEClassification.ACTIVE_SLICE_E1.value: 9,
        SliceEClassification.ACTIVE_SLICE_E2.value: 8,
        SliceEClassification.ACTIVE_SLICE_E3.value: 3,
    }


def test_slice_e1_obligations_name_the_exact_future_slice() -> None:
    """Meta — every obligation classification is recognised; no placeholders remain."""

    for entry in _SECTION_10_REGISTRY:
        classification = entry["classification"]
        future_slice = entry.get("future_slice")
        if classification == SliceEClassification.ACTIVE_SLICE_E1.value:
            assert future_slice is None
        elif classification == SliceEClassification.ACTIVE_SLICE_E2.value:
            assert future_slice is None
        elif classification == SliceEClassification.ACTIVE_SLICE_E3.value:
            assert future_slice is None
        else:  # pragma: no cover - registry enum guard
            raise AssertionError(f"unknown classification: {classification}")
