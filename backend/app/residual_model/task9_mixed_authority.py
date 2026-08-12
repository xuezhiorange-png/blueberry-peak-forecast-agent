from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.harvest_state.schemas import Task9ACompletedOutput
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.residual_model.canonical import canonical_payload_hash
from backend.app.residual_model.schemas import FeatureValue

TASK9_MIXED_VISIBILITY_POLICY_VERSION = "v0-3-s1-task9-mixed-visibility-v1"
TASK9_EXACT_TIMESTAMP_AUTHORITY = "EXACT_TIMESTAMP_AUTHORITY"
TASK9_LOCAL_DATE_AUTHORITY = "LOCAL_AVAILABLE_DATE_AUTHORITY"
TASK9_FEATURE_NAMES = frozenset(
    {
        "structural_arrival_p50_kg",
        "structural_arrival_p80_kg",
        "structural_arrival_p90_kg",
        "forecast_horizon_days",
        "structural_cumulative_to_as_of_kg",
        "spring_festival_window_flag",
    }
)


class Task9MixedAuthorityError(ValueError):
    """Raised when a completed Task 9 output has an unclassified upstream ref."""


@dataclass(frozen=True)
class Task9MixedAuthorityEvidence:
    policy_version: str
    task9_run_id: int
    task9_result_hash: str
    forecast_cutoff_at: datetime
    as_of_date: date
    evidence_hash: str

    def feature_source_ref_fragment(self) -> dict[str, object]:
        return {
            "task9_mixed_visibility_policy_version": self.policy_version,
            "task9_mixed_authority_validated": True,
            "task9_mixed_authority_evidence_hash": self.evidence_hash,
        }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise Task9MixedAuthorityError(f"{field_name} is not a valid ISO date") from exc
    raise Task9MixedAuthorityError(f"{field_name} is required")


def _datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, str):
        try:
            return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError as exc:
            raise Task9MixedAuthorityError(f"{field_name} is not a valid ISO datetime") from exc
    raise Task9MixedAuthorityError(f"{field_name} is required")


async def validate_task9_mixed_authority(
    session: AsyncSession,
    *,
    task9_run_id: int,
    output: Task9ACompletedOutput,
    forecast_cutoff_at: datetime,
) -> Task9MixedAuthorityEvidence:
    run = await session.get(HarvestStateRun, task9_run_id)
    if run is None:
        raise Task9MixedAuthorityError(f"HarvestStateRun {task9_run_id} was not found")
    as_of_date = _date(output.input_snapshot.get("as_of_date"), field_name="as_of_date")
    if run.as_of_date != as_of_date:
        raise Task9MixedAuthorityError("Task 9 run as_of_date does not match its output snapshot")
    cutoff = _utc(forecast_cutoff_at)
    classified: list[dict[str, object]] = []
    for entry in sorted(output.source_ref_catalog, key=lambda item: item.source_ref_hash):
        source_type = entry.source_ref_type.value
        payload = entry.source_ref_payload
        if source_type == "TASK8_DAILY_PREDICTION":
            authority_class = TASK9_EXACT_TIMESTAMP_AUTHORITY
            raw_available_at = payload.get("maturity_daily_prediction_available_at")
            if raw_available_at is None:
                if run.is_replay is True:
                    raise Task9MixedAuthorityError(
                        "replay Task 9 output is missing Task 8 exact availability timestamp"
                    )
                classified.append(
                    {
                        "source_ref_hash": entry.source_ref_hash,
                        "authority_class": authority_class,
                        "authority_timestamp": None,
                        "legacy_non_replay_compatibility": True,
                    }
                )
                continue
            available_at = _datetime(
                raw_available_at,
                field_name="maturity_daily_prediction_available_at",
            )
            if available_at > cutoff:
                raise Task9MixedAuthorityError(
                    "Task 8 exact availability timestamp is after the forecast cutoff"
                )
            classified.append(
                {
                    "source_ref_hash": entry.source_ref_hash,
                    "authority_class": authority_class,
                    "authority_timestamp": available_at,
                }
            )
        elif source_type in {"PARAMETER_SOURCE", "INITIAL_INVENTORY_SNAPSHOT"}:
            authority_class = TASK9_LOCAL_DATE_AUTHORITY
            local_available_at = _date(payload.get("available_at"), field_name="available_at")
            ref_as_of_date = _date(payload.get("as_of_date"), field_name="as_of_date")
            if ref_as_of_date != as_of_date:
                raise Task9MixedAuthorityError(
                    f"{source_type} authority date does not match the Task 9 as-of date"
                )
            if local_available_at > as_of_date:
                raise Task9MixedAuthorityError(
                    f"{source_type} available_at is after the Task 9 as-of date"
                )
            classified.append(
                {
                    "source_ref_hash": entry.source_ref_hash,
                    "authority_class": authority_class,
                    "available_at": local_available_at,
                    "as_of_date": ref_as_of_date,
                }
            )
        else:
            raise Task9MixedAuthorityError(
                f"unclassified Task 9 upstream source ref type: {source_type}"
            )

    evidence_payload = {
        "policy_version": TASK9_MIXED_VISIBILITY_POLICY_VERSION,
        "task9_run_id": task9_run_id,
        "task9_result_hash": output.result_hash,
        "forecast_cutoff_at": cutoff,
        "as_of_date": as_of_date,
        "source_refs": classified,
    }
    return Task9MixedAuthorityEvidence(
        policy_version=TASK9_MIXED_VISIBILITY_POLICY_VERSION,
        task9_run_id=task9_run_id,
        task9_result_hash=output.result_hash,
        forecast_cutoff_at=cutoff,
        as_of_date=as_of_date,
        evidence_hash=canonical_payload_hash(evidence_payload),
    )


def bind_task9_feature_provenance(
    feature_values: Sequence[FeatureValue],
    *,
    evidence: Task9MixedAuthorityEvidence,
) -> tuple[FeatureValue, ...]:
    fragment = evidence.feature_source_ref_fragment()
    bound: list[FeatureValue] = []
    for feature in feature_values:
        if feature.feature_name not in TASK9_FEATURE_NAMES:
            bound.append(feature)
            continue
        bound.append(feature.model_copy(update={"source_ref": {**feature.source_ref, **fragment}}))
    return tuple(bound)
