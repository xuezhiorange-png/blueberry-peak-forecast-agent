"""Flush-only persistence for the immutable V0.6-S4 authorities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pit.canonical import hash_payload
from backend.app.pit.prospective_models import (
    ProspectiveValidationRun,
    WeatherIncrementalValueAssessment,
)
from backend.app.pit.prospective_validation import S4AssessmentComputation


class ProspectiveValidationPersistenceError(RuntimeError):
    """Base S4 persistence error."""


class ProspectiveValidationConflictError(ProspectiveValidationPersistenceError):
    """Same authority identity was submitted with different content."""


class ProspectiveValidationIntegrityError(ProspectiveValidationPersistenceError):
    """Stored S4 content failed its canonical reload gate."""


def _json_payload(value: object) -> Any:
    # Keep the shared canonicalizer lazy for the same import boundary as S3.
    from backend.app.rolling_backtest.canonical import canonical_json_value

    return canonical_json_value(value)


def _child_payload(computation: S4AssessmentComputation) -> dict[str, Any]:
    return {
        "validation_run_id": computation.validation_run_id,
        "policy_version": computation.policy_version,
        "model_a_identity": computation.model_a_identity,
        "model_a_hash": computation.model_a_hash,
        "weather_snapshot_authority_hashes": list(computation.weather_snapshot_authority_hashes),
        "sample_scope": computation.sample_scope,
        "coverage_summary": computation.coverage_summary,
        "baseline_metrics": computation.baseline_metrics,
        "weather_quality_metrics": computation.weather_quality_metrics,
        "weather_incremental_metrics": computation.weather_incremental_metrics,
        "evidence_sufficiency": computation.evidence_sufficiency,
        "weather_incremental_value_conclusion": computation.weather_incremental_value_conclusion,
        "v0_7_recommendation": computation.v0_7_recommendation,
        "warnings": list(computation.warnings),
    }


def _child_payload_from_model(
    model: WeatherIncrementalValueAssessment,
) -> dict[str, Any]:
    return {
        "validation_run_id": model.validation_run_id,
        "policy_version": model.policy_version,
        "model_a_identity": model.model_a_identity,
        "model_a_hash": model.model_a_hash,
        "weather_snapshot_authority_hashes": model.weather_snapshot_authority_hashes,
        "sample_scope": model.sample_scope,
        "coverage_summary": model.coverage_summary,
        "baseline_metrics": model.baseline_metrics,
        "weather_quality_metrics": model.weather_quality_metrics,
        "weather_incremental_metrics": model.weather_incremental_metrics,
        "evidence_sufficiency": model.evidence_sufficiency,
        "weather_incremental_value_conclusion": model.weather_incremental_value_conclusion,
        "v0_7_recommendation": model.v0_7_recommendation,
        "warnings": model.warnings,
    }


def _parent_payload(model: ProspectiveValidationRun) -> dict[str, Any]:
    identity = {
        "policy_version": model.policy_version,
        "model_a_identity": model.model_a_identity,
        "model_a_hash": model.model_a_hash,
        "eligible_forecast_run_ids": model.eligible_forecast_run_ids,
        "s3_evaluation_ids": model.s3_evaluation_ids,
        "weather_snapshot_authority_hashes": model.weather_snapshot_authority_hashes,
        "sample_scope": model.sample_scope,
        "evidence_sufficiency": model.evidence_sufficiency,
    }
    result = {
        "eligibility_registry": model.eligibility_registry_json,
        "coverage_summary": model.coverage_summary,
        "baseline_metrics": model.baseline_metrics,
        "weather_quality_metrics": model.weather_quality_metrics,
        "weather_incremental_metrics": model.weather_incremental_metrics,
        "weather_incremental_value_conclusion": model.weather_incremental_value_conclusion,
        "v0_7_recommendation": model.v0_7_recommendation,
        "warnings": model.warnings,
    }
    return {"identity": identity, "result": result}


class ProspectiveValidationRepository:
    """Append-only S4 repository; the caller owns commit and rollback."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, computation: S4AssessmentComputation) -> ProspectiveValidationRun:
        if computation.compute_result_hash() != computation.result_hash:
            raise ProspectiveValidationIntegrityError("S4_RESULT_HASH_MISMATCH")
        if computation.compute_payload_hash() != computation.payload_hash:
            raise ProspectiveValidationIntegrityError("S4_PAYLOAD_HASH_MISMATCH")
        expected_id = f"prospective_validation_{hash_payload(computation.identity_payload())}"
        if computation.validation_run_id != expected_id:
            raise ProspectiveValidationIntegrityError("S4_VALIDATION_RUN_ID_MISMATCH")

        existing = await self.session.get(ProspectiveValidationRun, computation.validation_run_id)
        if existing is not None:
            if (
                existing.payload_hash != computation.payload_hash
                or existing.result_hash != computation.result_hash
            ):
                raise ProspectiveValidationConflictError("PROSPECTIVE_VALIDATION_CONFLICT")
            return await self.get_assessment(computation.validation_run_id)

        model = ProspectiveValidationRun(
            validation_run_id=computation.validation_run_id,
            created_at=computation.created_at,
            policy_version=computation.policy_version,
            model_a_identity=computation.model_a_identity,
            model_a_hash=computation.model_a_hash,
            eligible_forecast_run_ids=sorted(
                item.forecast_run_id
                for item in computation.eligibility
                if item.prospective_eligible
            ),
            s3_evaluation_ids=list(computation.s3_evaluation_ids),
            eligibility_registry_json=[item.payload() for item in computation.eligibility],
            sample_scope=_json_payload(computation.sample_scope),
            coverage_summary=_json_payload(computation.coverage_summary),
            baseline_metrics=_json_payload(computation.baseline_metrics),
            weather_quality_metrics=_json_payload(computation.weather_quality_metrics),
            weather_incremental_metrics=_json_payload(computation.weather_incremental_metrics),
            evidence_sufficiency=_json_payload(computation.evidence_sufficiency),
            weather_snapshot_authority_hashes=list(computation.weather_snapshot_authority_hashes),
            weather_incremental_value_conclusion=computation.weather_incremental_value_conclusion,
            v0_7_recommendation=computation.v0_7_recommendation,
            warnings=list(computation.warnings),
            payload_hash=computation.payload_hash,
            result_hash=computation.result_hash,
        )
        child_payload = _json_payload(_child_payload(computation))
        child = WeatherIncrementalValueAssessment(
            assessment_id=computation.assessment_id,
            validation_run_id=computation.validation_run_id,
            created_at=computation.created_at,
            policy_version=computation.policy_version,
            model_a_identity=computation.model_a_identity,
            model_a_hash=computation.model_a_hash,
            weather_snapshot_authority_hashes=list(computation.weather_snapshot_authority_hashes),
            sample_scope=_json_payload(computation.sample_scope),
            coverage_summary=_json_payload(computation.coverage_summary),
            baseline_metrics=_json_payload(computation.baseline_metrics),
            weather_quality_metrics=_json_payload(computation.weather_quality_metrics),
            weather_incremental_metrics=_json_payload(computation.weather_incremental_metrics),
            evidence_sufficiency=_json_payload(computation.evidence_sufficiency),
            weather_incremental_value_conclusion=computation.weather_incremental_value_conclusion,
            v0_7_recommendation=computation.v0_7_recommendation,
            warnings=list(computation.warnings),
            payload_hash=hash_payload(child_payload),
            result_hash=hash_payload(
                {
                    key: child_payload[key]
                    for key in (
                        "weather_incremental_metrics",
                        "weather_incremental_value_conclusion",
                        "v0_7_recommendation",
                    )
                }
            ),
        )
        self.session.add(model)
        self.session.add(child)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise ProspectiveValidationConflictError("S4_INSERT_CONFLICT") from exc
        except SQLAlchemyError as exc:
            raise ProspectiveValidationIntegrityError("S4_INSERT_FAILED") from exc
        return await self.get_assessment(computation.validation_run_id)

    async def get_assessment(self, validation_run_id: str) -> ProspectiveValidationRun:
        model = await self.session.get(ProspectiveValidationRun, validation_run_id)
        if model is None:
            raise ProspectiveValidationIntegrityError("S4_VALIDATION_RUN_NOT_FOUND")
        payload = _parent_payload(model)
        if hash_payload(_json_payload(payload)) != model.payload_hash:
            raise ProspectiveValidationIntegrityError("S4_PAYLOAD_CORRUPTED")
        result = payload.get("result")
        identity = payload.get("identity")
        if not isinstance(result, Mapping) or not isinstance(identity, Mapping):
            raise ProspectiveValidationIntegrityError("S4_PAYLOAD_INVALID")
        if hash_payload(_json_payload(result)) != model.result_hash:
            raise ProspectiveValidationIntegrityError("S4_RESULT_CORRUPTED")
        child = await self.session.get(
            WeatherIncrementalValueAssessment,
            f"weather_assessment_{validation_run_id.removeprefix('prospective_validation_')}",
        )
        if child is None:
            raise ProspectiveValidationIntegrityError("S4_WEATHER_ASSESSMENT_NOT_FOUND")
        child_payload = _child_payload_from_model(child)
        if hash_payload(_json_payload(child_payload)) != child.payload_hash:
            raise ProspectiveValidationIntegrityError("S4_CHILD_PAYLOAD_CORRUPTED")
        child_result = {
            key: child_payload[key]
            for key in (
                "weather_incremental_metrics",
                "weather_incremental_value_conclusion",
                "v0_7_recommendation",
            )
        }
        if hash_payload(_json_payload(child_result)) != child.result_hash:
            raise ProspectiveValidationIntegrityError("S4_CHILD_RESULT_CORRUPTED")
        return model


__all__ = [
    "ProspectiveValidationConflictError",
    "ProspectiveValidationIntegrityError",
    "ProspectiveValidationPersistenceError",
    "ProspectiveValidationRepository",
]
