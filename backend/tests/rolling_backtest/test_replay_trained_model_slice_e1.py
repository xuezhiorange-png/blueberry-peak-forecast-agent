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
    OBLIGATION_SLICE_E3 = "obligation_slice_e3"


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
        "classification": SliceEClassification.OBLIGATION_SLICE_E3.value,
        "future_slice": "Slice E3",
    },
    {
        "name": "test_api_error_envelopes_are_stable_and_non_leaking",
        "section": "§10 #17",
        "classification": SliceEClassification.OBLIGATION_SLICE_E3.value,
        "future_slice": "Slice E3",
    },
    {
        "name": "test_get_requires_exact_prediction_run_id",
        "section": "§10 #18",
        "classification": SliceEClassification.OBLIGATION_SLICE_E3.value,
        "future_slice": "Slice E3",
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


def test_api_first_execution_is_201_and_exact_replay_is_200() -> None:
    """§10 #16 — HTTP status semantics activate in Slice E3."""

    _skip_obligation(
        section="§10 #16",
        future_slice="Slice E3",
        requirement="POST first-execution and exact-idempotent-replay status contract",
    )


def test_api_error_envelopes_are_stable_and_non_leaking() -> None:
    """§10 #17 — HTTP error envelopes activate in Slice E3."""

    _skip_obligation(
        section="§10 #17",
        future_slice="Slice E3",
        requirement="stable 404/409/422/500 transport envelopes",
    )


def test_get_requires_exact_prediction_run_id() -> None:
    """§10 #18 — exact retrieval semantics activate in Slice E3."""

    _skip_obligation(
        section="§10 #18",
        future_slice="Slice E3",
        requirement="GET by exact prediction_run_id with no implicit selection",
    )


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
        SliceEClassification.OBLIGATION_SLICE_E3.value: 3,
    }


def test_slice_e1_obligations_name_the_exact_future_slice() -> None:
    """Meta — every placeholder names E2 or E3 and no active test does."""

    for entry in _SECTION_10_REGISTRY:
        classification = entry["classification"]
        future_slice = entry.get("future_slice")
        if classification == SliceEClassification.ACTIVE_SLICE_E1.value:
            assert future_slice is None
        elif classification == SliceEClassification.ACTIVE_SLICE_E2.value:
            assert future_slice is None
        elif classification == SliceEClassification.OBLIGATION_SLICE_E3.value:
            assert future_slice == "Slice E3"
        else:  # pragma: no cover - registry enum guard
            raise AssertionError(f"unknown classification: {classification}")
