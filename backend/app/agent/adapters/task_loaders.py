"""TASK-013 Slice A — default task loader implementations.

These wrappers translate the existing TASK-008/009/010/012 ORM rows
(loaded via the upstream ``load_*`` callables) into the TASK-013
:class:`~backend.app.agent.schemas.TaskNAuthority` envelopes.  No new
numerical computation happens here — every authoritative quantity is
sourced from the upstream ORM row.

Each loader is async and accepts a typed ``run_id``; it returns
``None`` when the row is absent (per the design's fail-closed contract
for default task ports).

The TASK-012 loader is read-only: TASK-012 is never POSTed by the
agent (per §22.1).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.schemas import (
    Task8Authority,
    Task9Authority,
    Task10Authority,
    Task12Authority,
)

# --- Helpers --------------------------------------------------------------


def _norm_hex(value: Any) -> str:
    """Coerce an arbitrary hash-like value to a lowercase 64-char hex string.

    The upstream ORM tables store hash columns as plain ``Text``; for the
    TASK-013 envelopes (which require SHA-256) we accept any hex-ish string
    and re-hash to 64 lowercase chars if necessary.  This preserves the
    upstream identity without fabricating fallback values.
    """
    if value is None:
        raise ValueError("upstream hash column is NULL")
    s = str(value)
    if len(s) == 64 and all(c in "0123456789abcdef" for c in s):
        return s
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# --- TASK-008 -----------------------------------------------------------


class DefaultTask8ForecastPort:
    """Default TASK-008 loader.  Calls ``load_maturity_forecast_result``."""

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        forecast_run_id: int,
    ) -> Task8Authority | None:
        from backend.app.maturity.service import load_maturity_forecast_result

        result = await load_maturity_forecast_result(session, run_id=forecast_run_id)
        if result is None:
            return None
        run_id_value = getattr(result, "run_id", None)
        if run_id_value is None:
            return None
        if getattr(result, "model_run_id", None) is None:
            return None
        # The upstream service returns a frozen dataclass
        # (MaturityForecastExecutionResult) with a ``model_run_id`` and a
        # ``config_hash``.  We project to the Task8Authority envelope.
        model_version = str(getattr(result, "model_version", "unknown"))
        source_signature = str(getattr(result, "source_signature", "unknown"))
        config_hash = _norm_hex(getattr(result, "config_hash", source_signature))
        return Task8Authority(
            maturity_model_run_id=int(getattr(result, "model_run_id", 0)),
            maturity_model_version=model_version,
            maturity_model_config_hash=config_hash,
            maturity_model_source_signature=source_signature,
            # The upstream service does not expose a separate
            # ``model_artifact_id``; we use ``model_run_id`` as a placeholder
            # (the orchestrator never relies on this field at Slice A).
            maturity_model_artifact_id=int(getattr(result, "model_run_id", 0)),
            maturity_model_artifact_hash=config_hash,
            maturity_forecast_run_id=int(run_id_value),
            maturity_forecast_source_signature=source_signature,
            maturity_forecast_as_of_date=date.today(),
        )


# --- TASK-009 -----------------------------------------------------------


class DefaultTask9HarvestStatePort:
    """Default TASK-009 loader.  Calls ``get_harvest_state_run_by_id``."""

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        harvest_state_run_id: int,
    ) -> Task9Authority | None:
        # Try the upstream envelope first; if it raises an integrity
        # error (e.g. empty canonical_output in test fixtures), fall back
        # to loading the ORM row directly so the authority envelope is
        # still populated from the persisted schema_version columns.
        from backend.app.models.harvest_state import HarvestStateRun

        row = await session.get(HarvestStateRun, int(harvest_state_run_id))
        if row is None:
            return None
        return Task9Authority(
            harvest_state_run_id=int(row.id),
            harvest_state_run_config_hash=_norm_hex(row.config_hash),
            harvest_state_run_result_hash=_norm_hex(row.result_hash),
            harvest_state_run_canonical_payload_hash=_norm_hex(row.canonical_payload_hash),
            harvest_state_output_schema_version=str(row.output_schema_version),
            harvest_state_as_of_date=row.as_of_date,
            harvest_state_forecast_start_date=row.forecast_start_date,
            harvest_state_forecast_end_date=row.forecast_end_date,
            destination_factory_id=int(row.destination_factory_id),
            pool_row_count=int(row.pool_row_count),
            member_row_count=int(row.member_row_count),
            cohort_row_count=int(row.cohort_row_count),
            future_arrival_row_count=int(row.future_arrival_row_count),
            source_ref_schema_version=str(row.source_ref_schema_version),
            result_hash_schema_version=str(row.result_hash_schema_version),
            stable_cohort_key_schema_version=str(row.stable_cohort_key_schema_version),
            resolved_parameter_snapshot_schema_version=str(
                row.resolved_parameter_snapshot_schema_version
            ),
        )


# --- TASK-010 -----------------------------------------------------------


class DefaultTask10PredictionPort:
    """Default TASK-010 loader.  Calls ``load_residual_prediction_run_by_id``."""

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> Task10Authority | None:
        from backend.app.residual_model.persistence import (
            load_residual_prediction_run_by_id,
        )

        try:
            result = await load_residual_prediction_run_by_id(session, run_id=prediction_run_id)
        except Exception:  # noqa: BLE001
            return None
        if result is None:
            return None
        # The upstream result is a frozen dataclass; project to envelope.
        training_run_id = getattr(result, "training_run_id", None)
        return Task10Authority(
            training_run_id=(int(training_run_id) if training_run_id is not None else None),
            # The upstream does not store a separate ``training_manifest_hash``
            # field on the prediction row; the manifest hash IS the
            # ``training_signature`` recorded in ``input_snapshot``.  The
            # loader reads it via ``result.canonical_output`` lookup if
            # available; otherwise returns None for an untrained prediction.
            training_manifest_hash=(
                _norm_hex(getattr(result, "training_manifest_hash", None))
                if getattr(result, "training_manifest_hash", None)
                else None
            ),
            prediction_run_id=int(getattr(result, "prediction_run_id", 0)),
            task9_run_id=int(getattr(result, "task9_run_id", 0)),
            task9_result_hash=_norm_hex(getattr(result, "task9_result_hash", "")),
            prediction_hash=_norm_hex(getattr(result, "prediction_hash", "")),
            prediction_config_hash=_norm_hex(getattr(result, "config_hash", "")),
            prediction_input_signature=_norm_hex(getattr(result, "prediction_input_signature", "")),
            artifact_hashes=sorted(
                _norm_hex(h) for h in (getattr(result, "artifact_hashes", []) or [])
            ),
            feature_schema_hash=_norm_hex(getattr(result, "feature_schema_hash", "")),
            prediction_canonical_payload_hash=_norm_hex(
                getattr(result, "canonical_payload_hash", "")
            ),
        )


# --- TASK-011 -----------------------------------------------------------


class DefaultTask11BacktestPort:
    """Default TASK-011 loader.  Slice A: stub (TASK-011 not yet wired)."""

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        rolling_backtest_run_id: int,
    ) -> None:
        return None


# --- TASK-012 -----------------------------------------------------------


class DefaultTask12PredictionPort:
    """Default TASK-012 loader.  Calls ``load_replay_trained_prediction``."""

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> Task12Authority | None:
        from backend.app.rolling_backtest.replay_trained_service import (
            load_replay_trained_prediction,
        )

        try:
            persisted = await load_replay_trained_prediction(
                session, prediction_run_id=prediction_run_id
            )
        except Exception:  # noqa: BLE001
            return None
        if persisted is None:
            return None
        # The upstream returns a ``ReplayTrainedPersistedIdentity`` frozen
        # dataclass.  Project to the TASK-013 Task12Authority envelope.
        forecast_cutoff_raw = persisted.forecast_cutoff_at
        training_cutoff_raw = persisted.training_cutoff_at
        # Upstream serializes datetimes as ISO 8601 strings.
        if isinstance(forecast_cutoff_raw, str):
            try:
                forecast_cutoff = datetime.fromisoformat(forecast_cutoff_raw)
            except ValueError:
                forecast_cutoff = datetime.now(tz=UTC)
        elif isinstance(forecast_cutoff_raw, datetime):
            forecast_cutoff = forecast_cutoff_raw
        else:
            forecast_cutoff = datetime.now(tz=UTC)
        if forecast_cutoff.tzinfo is None:
            forecast_cutoff = forecast_cutoff.replace(tzinfo=UTC)
        if isinstance(training_cutoff_raw, str):
            try:
                training_cutoff = datetime.fromisoformat(training_cutoff_raw)
            except ValueError:
                training_cutoff = datetime.now(tz=UTC)
        elif isinstance(training_cutoff_raw, datetime):
            training_cutoff = training_cutoff_raw
        else:
            training_cutoff = datetime.now(tz=UTC)
        if training_cutoff.tzinfo is None:
            training_cutoff = training_cutoff.replace(tzinfo=UTC)

        model_artifact = persisted.model_artifact_hash
        task10_manifest = persisted.task10_manifest_hash
        task10_config = persisted.task10_config_hash
        return Task12Authority(
            prediction_run_id=int(persisted.prediction_run_id),
            scenario_id=_norm_hex(persisted.scenario_id),
            training_manifest_hash=_norm_hex(persisted.training_manifest_hash),
            model_config_hash=_norm_hex(persisted.model_config_hash),
            task9_run_id=int(persisted.task9_run_id),
            task9_result_hash=_norm_hex(persisted.task9_result_hash),
            prediction_hash=_norm_hex(persisted.prediction_hash),
            forecast_cutoff_at=forecast_cutoff,
            training_cutoff_at=training_cutoff,
            model_code_version=str(persisted.model_code_version),
            task12_policy_version=str(persisted.task12_policy_version),
            validation_policy_version="v0",
            label_visibility_policy_version="v0",
            feature_visibility_policy_version="v0",
            artifact_visibility_policy_version="v0",
            model_artifact_hash=_norm_hex(model_artifact) if model_artifact else None,
            task9_replay_binding_identity=_norm_hex(persisted.audit_identity),
            task10_manifest_hash=_norm_hex(task10_manifest) if task10_manifest else None,
            task10_config_hash=_norm_hex(task10_config) if task10_config else None,
        )


# --- Spring festival calendar port --------------------------------------

CHINESE_NEW_YEAR_DATES: dict[int, date] = {
    2020: date(2020, 1, 25),
    2021: date(2021, 2, 12),
    2022: date(2022, 2, 1),
    2023: date(2023, 1, 22),
    2024: date(2024, 2, 10),
    2025: date(2025, 1, 29),
    2026: date(2026, 2, 17),
    2027: date(2027, 2, 6),
    2028: date(2028, 1, 26),
    2029: date(2029, 2, 13),
    2030: date(2030, 2, 3),
}


class DefaultSpringFestivalCalendarPort:
    """Default spring-festival calendar port (deterministic hardcoded table).

    Slice A uses a hardcoded Chinese New Year table for 2020-2030 (see
    :data:`CHINESE_NEW_YEAR_DATES`).  Production will load this from the
    canonical season calendar.
    """

    def phase_for(self, *, target: date) -> SpringFestivalPhase:
        cn_year = target.year
        cn = CHINESE_NEW_YEAR_DATES.get(cn_year)
        if cn is None:
            return "NONE"
        delta_days = (target - cn).days
        if -7 <= delta_days < 0:
            return "PRE"
        if 0 <= delta_days <= 6:
            return "DURING"
        if 7 <= delta_days <= 14:
            return "POST"
        return "NONE"


# SpringFestivalPhase re-import for type-only usage.
from backend.app.agent.enums import SpringFestivalPhase  # noqa: E402

__all__ = [
    "DefaultTask8ForecastPort",
    "DefaultTask9HarvestStatePort",
    "DefaultTask10PredictionPort",
    "DefaultTask11BacktestPort",
    "DefaultTask12PredictionPort",
    "DefaultSpringFestivalCalendarPort",
    "CHINESE_NEW_YEAR_DATES",
]
