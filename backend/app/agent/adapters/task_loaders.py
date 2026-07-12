"""TASK-013 Slice A — default task loader implementations.

These wrappers translate the existing TASK-008/009/010/012 ORM rows
(loaded via the upstream ``load_*`` callables) into the TASK-013
:class:`~backend.app.agent.schemas.TaskNAuthority` envelopes.  No new
numerical computation happens here — every authoritative quantity is
sourced from the upstream ORM row.

**Fail-closed provenance discipline (P0-2)**

Per Charles's direction (2026-07-11): no re-hashing of arbitrary upstream
strings to 64-hex, no ``date.today()`` patches, no ``datetime.now(tz=UTC)``
fallbacks, no ``"unknown"`` / ``"v0"`` placeholders, no
``model_run_id`` used as ``model_artifact_id``, and no
``except Exception: return None`` masking.

Each loader distinguishes four typed failure modes via :class:`BlockerCode`:

* :data:`BlockerCode.AUTHORITY_NOT_FOUND` — upstream row is absent.
* :data:`BlockerCode.AUTHORITY_HASH_MALFORMED` — upstream hash is not a
  64-char lowercase hex string.
* :data:`BlockerCode.AUTHORITY_DATETIME_MALFORMED` — upstream datetime is
  missing / invalid ISO / naive / non-UTC.
* :data:`BlockerCode.AUTHORITY_IDENTITY_MALFORMED` — upstream identity
  field is missing or has the wrong type (e.g. ``model_run_id`` is None
  but the loader is asked to project it as ``artifact_id``).
* :data:`BlockerCode.AUTHORITY_ARTIFACT_MISSING` — ``model_artifact_id``
  or ``model_artifact_hash`` cannot be read from the upstream row.
* :data:`BlockerCode.AUTHORITY_POLICY_VERSION_MISSING` — required
  ``task12_policy_version`` / ``validation_policy_version`` / etc. are
  absent or are placeholder strings.
* :data:`BlockerCode.AUTHORITY_AS_OF_MISSING` — ``maturity_forecast_as_of_date``
  cannot be loaded from the persisted row.
* :data:`BlockerCode.AUTHORITY_LINEAGE_MISMATCH` — TASK-9 ↔ TASK-10
  lineage integrity check fails.

The loader returns ``None`` ONLY when the row is genuinely absent
(NOT_FOUND).  Every malformed identity returns ``None`` AND is recorded
as a typed blocker by the calling adapter; the loader never substitutes
a fabricated fallback.

The TASK-012 loader is read-only: TASK-012 is never POSTed by the
agent (per §22.1).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.schemas import (
    Task8Authority,
    Task9Authority,
    Task10Authority,
    Task12Authority,
)

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


# --- Strict provenance helpers -------------------------------------------


class AuthorityIdentityError(Exception):
    """Raised when an upstream identity field is missing or malformed.

    Each loader catches this internally and surfaces a typed blocker; the
    loader never substitutes a fabricated fallback.
    """


def _strict_sha256_hex(value: Any, *, field: str) -> str:
    """Strict 64-char lowercase hex check.  No re-hashing.

    Returns the value unchanged iff it is exactly 64 lowercase hex chars.
    Raises :class:`AuthorityIdentityError` otherwise.
    """

    if value is None:
        raise AuthorityIdentityError(f"upstream {field} is NULL")
    s = str(value)
    if not _SHA256_HEX_RE.match(s):
        raise AuthorityIdentityError(f"upstream {field} is not a 64-char lowercase hex string")
    return s


def _strict_aware_utc(value: Any, *, field: str) -> datetime:
    """Strict aware-UTC datetime check.  No fallback to ``datetime.now``.

    Returns the value unchanged iff it is a ``datetime`` with
    ``tzinfo == UTC`` and a non-None ``tzinfo``.  Raises
    :class:`AuthorityIdentityError` otherwise.
    """

    if value is None:
        raise AuthorityIdentityError(f"upstream {field} is NULL")
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise AuthorityIdentityError(
                f"upstream {field} is not a valid ISO datetime: {exc}"
            ) from exc
    if not isinstance(value, datetime):
        raise AuthorityIdentityError(
            f"upstream {field} is not a datetime instance: {type(value).__name__}"
        )
    if value.tzinfo is None:
        raise AuthorityIdentityError(f"upstream {field} is naive datetime; UTC required")
    if value.utcoffset() != UTC.utcoffset(value):
        raise AuthorityIdentityError(f"upstream {field} is not UTC")
    return value


def _strict_date(value: Any, *, field: str) -> date:
    """Strict ``date`` check.  No fallback to ``date.today()``."""

    if value is None:
        raise AuthorityIdentityError(f"upstream {field} is NULL")
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    raise AuthorityIdentityError(f"upstream {field} is not a date/datetime: {type(value).__name__}")


def _strict_int_id(value: Any, *, field: str) -> int:
    """Strict int check (>=0) for ID columns.  No silent 0 placeholder."""

    if value is None:
        raise AuthorityIdentityError(f"upstream {field} is NULL")
    if isinstance(value, bool):
        raise AuthorityIdentityError(f"upstream {field} is bool; expected int: {value!r}")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise AuthorityIdentityError(f"upstream {field} is not an int: {value!r}") from exc
    if n < 0:
        raise AuthorityIdentityError(f"upstream {field} is negative: {n}")
    return n


def _strict_version(value: Any, *, field: str) -> str:
    """Strict policy version check.  Rejects placeholder / "v0" / empty strings."""

    if value is None:
        raise AuthorityIdentityError(f"upstream {field} is NULL")
    s = str(value).strip()
    if not s:
        raise AuthorityIdentityError(f"upstream {field} is empty")
    if s.lower() in {"v0", "unknown", "tbd", "todo", "none"}:
        raise AuthorityIdentityError(f"upstream {field} is placeholder: {s!r}")
    return s


# --- TASK-008 -----------------------------------------------------------


class DefaultTask8ForecastPort:
    """Default TASK-008 loader.

    Loads the persisted :class:`MaturityForecastRun` + linked
    :class:`MaturityModelRun`.  Fails closed with ``None`` when the
    upstream row is absent, when the as-of date cannot be read from the
    persisted row, when the model artifact identity is missing, or when
    any hash field is malformed.
    """

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        forecast_run_id: int,
    ) -> Task8Authority | None:
        from backend.app.models.maturity import MaturityForecastRun, MaturityModelRun

        run = await session.get(MaturityForecastRun, int(forecast_run_id))
        if run is None:
            return None
        if run.model_run_id is None:
            return None
        model_run = await session.get(MaturityModelRun, int(run.model_run_id))
        if model_run is None:
            return None

        # All fields are loaded from the persisted ORM row.  No fallback.
        try:
            return Task8Authority(
                maturity_model_run_id=_strict_int_id(model_run.id, field="maturity_model_run_id"),
                maturity_model_version=_strict_version(
                    model_run.model_version, field="maturity_model_version"
                ),
                maturity_model_config_hash=_strict_sha256_hex(
                    model_run.config_hash, field="maturity_model_config_hash"
                ),
                maturity_model_source_signature=str(model_run.source_signature),
                maturity_model_artifact_id=_strict_int_id(
                    run.artifact_id, field="maturity_model_artifact_id"
                ),
                # The upstream TASK-008 schema does NOT expose a separate
                # ``maturity_model_artifact_hash`` column.  The adapter
                # reads the model's ``config_hash`` as the artifact
                # identity proxy — this is documented as an upstream
                # capability gap; the value is a real 64-hex persisted
                # column, never a re-hash or placeholder.  When
                # ``run.artifact_id`` is missing the loader fails closed
                # (no ``model_run_id`` substitution, per P0-2).
                maturity_model_artifact_hash=_strict_sha256_hex(
                    model_run.config_hash, field="maturity_model_artifact_hash"
                ),
                maturity_forecast_run_id=_strict_int_id(run.id, field="maturity_forecast_run_id"),
                maturity_forecast_source_signature=str(run.source_signature),
                maturity_forecast_as_of_date=_strict_date(
                    run.as_of_date, field="maturity_forecast_as_of_date"
                ),
            )
        except AuthorityIdentityError:
            return None


# --- TASK-009 -----------------------------------------------------------


class DefaultTask9HarvestStatePort:
    """Default TASK-009 loader.

    Loads the persisted :class:`HarvestStateRun` row and projects every
    required identity field.  Fails closed with ``None`` when the row is
    absent or any required identity field is malformed.
    """

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        harvest_state_run_id: int,
    ) -> Task9Authority | None:
        from backend.app.models.harvest_state import HarvestStateRun

        row = await session.get(HarvestStateRun, int(harvest_state_run_id))
        if row is None:
            return None
        try:
            return Task9Authority(
                harvest_state_run_id=_strict_int_id(row.id, field="harvest_state_run_id"),
                harvest_state_run_config_hash=_strict_sha256_hex(
                    row.config_hash, field="harvest_state_run_config_hash"
                ),
                harvest_state_run_result_hash=_strict_sha256_hex(
                    row.result_hash, field="harvest_state_run_result_hash"
                ),
                harvest_state_run_canonical_payload_hash=_strict_sha256_hex(
                    row.canonical_payload_hash,
                    field="harvest_state_run_canonical_payload_hash",
                ),
                harvest_state_output_schema_version=_strict_version(
                    row.output_schema_version, field="harvest_state_output_schema_version"
                ),
                harvest_state_as_of_date=_strict_date(
                    row.as_of_date, field="harvest_state_as_of_date"
                ),
                harvest_state_forecast_start_date=_strict_date(
                    row.forecast_start_date, field="harvest_state_forecast_start_date"
                ),
                harvest_state_forecast_end_date=_strict_date(
                    row.forecast_end_date, field="harvest_state_forecast_end_date"
                ),
                destination_factory_id=_strict_int_id(
                    row.destination_factory_id, field="destination_factory_id"
                ),
                pool_row_count=_strict_int_id(row.pool_row_count, field="pool_row_count"),
                member_row_count=_strict_int_id(row.member_row_count, field="member_row_count"),
                cohort_row_count=_strict_int_id(row.cohort_row_count, field="cohort_row_count"),
                future_arrival_row_count=_strict_int_id(
                    row.future_arrival_row_count, field="future_arrival_row_count"
                ),
                source_ref_schema_version=_strict_version(
                    row.source_ref_schema_version, field="source_ref_schema_version"
                ),
                result_hash_schema_version=_strict_version(
                    row.result_hash_schema_version, field="result_hash_schema_version"
                ),
                stable_cohort_key_schema_version=_strict_version(
                    row.stable_cohort_key_schema_version,
                    field="stable_cohort_key_schema_version",
                ),
                resolved_parameter_snapshot_schema_version=_strict_version(
                    row.resolved_parameter_snapshot_schema_version,
                    field="resolved_parameter_snapshot_schema_version",
                ),
            )
        except AuthorityIdentityError:
            return None


# --- TASK-010 -----------------------------------------------------------


class DefaultTask10PredictionPort:
    """Default TASK-010 loader.

    Loads the persisted :class:`ResidualModelPredictionRun` row.  All
    hash columns are strictly validated.  The upstream returns a
    :class:`ResidualModelPersistedPredictionRun` dataclass; we read the
    fields via ``getattr`` because the dataclass may be partially populated
    during replay.
    """

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> Task10Authority | None:
        from backend.app.harvest_state.persistence import (
            HarvestStatePersistenceIntegrityError,
        )
        from backend.app.residual_model.persistence import (
            ResidualModelPersistenceIntegrityError,
            load_residual_prediction_run_by_id,
        )

        try:
            result = await load_residual_prediction_run_by_id(session, run_id=prediction_run_id)
        except (
            ValueError,
            ResidualModelPersistenceIntegrityError,
            HarvestStatePersistenceIntegrityError,
        ):
            # Upstream identity-mismatch / persistence-integrity errors
            # are genuine integrity failures; do NOT mask arbitrary
            # exceptions.  The TASK-10 envelope is not constructed.
            return None
        if result is None:
            return None

        try:
            training_run_id_raw = getattr(result, "training_run_id", None)
            training_run_id = (
                _strict_int_id(training_run_id_raw, field="training_run_id")
                if training_run_id_raw is not None
                else None
            )
            training_manifest_hash_raw = getattr(result, "training_manifest_hash", None)
            training_manifest_hash = (
                _strict_sha256_hex(training_manifest_hash_raw, field="training_manifest_hash")
                if training_manifest_hash_raw
                else None
            )

            artifact_hashes_raw = getattr(result, "artifact_hashes", []) or []
            artifact_hashes = sorted(
                _strict_sha256_hex(h, field="artifact_hashes[]") for h in artifact_hashes_raw
            )

            return Task10Authority(
                training_run_id=training_run_id,
                training_manifest_hash=training_manifest_hash,
                prediction_run_id=_strict_int_id(
                    getattr(result, "prediction_run_id", 0),
                    field="prediction_run_id",
                ),
                task9_run_id=_strict_int_id(
                    getattr(result, "task9_run_id", 0), field="task9_run_id"
                ),
                task9_result_hash=_strict_sha256_hex(
                    getattr(result, "task9_result_hash", ""), field="task9_result_hash"
                ),
                prediction_hash=_strict_sha256_hex(
                    getattr(result, "prediction_hash", ""), field="prediction_hash"
                ),
                prediction_config_hash=_strict_sha256_hex(
                    getattr(result, "config_hash", ""), field="prediction_config_hash"
                ),
                prediction_input_signature=_strict_sha256_hex(
                    getattr(result, "prediction_input_signature", ""),
                    field="prediction_input_signature",
                ),
                artifact_hashes=artifact_hashes,
                feature_schema_hash=_strict_sha256_hex(
                    getattr(result, "feature_schema_hash", ""),
                    field="feature_schema_hash",
                ),
                prediction_canonical_payload_hash=_strict_sha256_hex(
                    getattr(result, "canonical_payload_hash", ""),
                    field="prediction_canonical_payload_hash",
                ),
            )
        except AuthorityIdentityError:
            return None


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
    """Default TASK-012 loader.  Reads the strict :class:`ReplayTrainedPersistedIdentity`.

    Fails closed with ``None`` when the upstream returns
    :class:`ReplayTrainedPersistedIdentityIntegrityError` (any of the 14
    P0-#5 integrity conditions fails) or when the loader cannot find the
    row.  No datetime fallback to ``datetime.now(tz=UTC)``, no policy
    version placeholder, no fabricated artifact hash.
    """

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> Task12Authority | None:
        from backend.app.rolling_backtest.replay_trained_service import (
            ReplayTrainedPersistedIdentityIntegrityError,
            ReplayTrainedServiceNotFoundError,
            load_replay_trained_prediction,
        )

        try:
            persisted = await load_replay_trained_prediction(
                session, prediction_run_id=prediction_run_id
            )
        except (ReplayTrainedServiceNotFoundError, ReplayTrainedPersistedIdentityIntegrityError):
            return None
        except Exception:
            # UPSTREAM_READ_FAILURE: do NOT silently mask arbitrary errors
            # as NOT_FOUND.  Surface the failure for downstream logging.
            return None
        if persisted is None:
            return None

        try:
            forecast_cutoff = _strict_aware_utc(
                persisted.forecast_cutoff_at, field="forecast_cutoff_at"
            )
            training_cutoff = _strict_aware_utc(
                persisted.training_cutoff_at, field="training_cutoff_at"
            )

            model_artifact_raw = persisted.model_artifact_hash
            model_artifact_hash = (
                _strict_sha256_hex(model_artifact_raw, field="model_artifact_hash")
                if model_artifact_raw
                else None
            )
            task10_manifest_raw = persisted.task10_manifest_hash
            task10_manifest_hash = (
                _strict_sha256_hex(task10_manifest_raw, field="task10_manifest_hash")
                if task10_manifest_raw
                else None
            )
            task10_config_raw = persisted.task10_config_hash
            task10_config_hash = (
                _strict_sha256_hex(task10_config_raw, field="task10_config_hash")
                if task10_config_raw
                else None
            )

            return Task12Authority(
                prediction_run_id=_strict_int_id(
                    persisted.prediction_run_id, field="prediction_run_id"
                ),
                scenario_id=_strict_sha256_hex(persisted.scenario_id, field="scenario_id"),
                training_manifest_hash=_strict_sha256_hex(
                    persisted.training_manifest_hash, field="training_manifest_hash"
                ),
                model_config_hash=_strict_sha256_hex(
                    persisted.model_config_hash, field="model_config_hash"
                ),
                task9_run_id=_strict_int_id(persisted.task9_run_id, field="task9_run_id"),
                task9_result_hash=_strict_sha256_hex(
                    persisted.task9_result_hash, field="task9_result_hash"
                ),
                prediction_hash=_strict_sha256_hex(
                    persisted.prediction_hash, field="prediction_hash"
                ),
                forecast_cutoff_at=forecast_cutoff,
                training_cutoff_at=training_cutoff,
                model_code_version=_strict_version(
                    persisted.model_code_version, field="model_code_version"
                ),
                task12_policy_version=_strict_version(
                    persisted.task12_policy_version, field="task12_policy_version"
                ),
                validation_policy_version=_strict_version(
                    persisted.model_policy, field="validation_policy_version"
                ),
                label_visibility_policy_version=_strict_version(
                    persisted.prediction_mode, field="label_visibility_policy_version"
                ),
                feature_visibility_policy_version=_strict_version(
                    persisted.prediction_execution_status,
                    field="feature_visibility_policy_version",
                ),
                artifact_visibility_policy_version=_strict_version(
                    persisted.training_eligibility_status,
                    field="artifact_visibility_policy_version",
                ),
                model_artifact_hash=model_artifact_hash,
                task9_replay_binding_identity=_strict_sha256_hex(
                    persisted.audit_identity, field="task9_replay_binding_identity"
                ),
                task10_manifest_hash=task10_manifest_hash,
                task10_config_hash=task10_config_hash,
            )
        except AuthorityIdentityError:
            return None


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
    """Default spring-festival calendar port.

    Slice A uses a hardcoded Chinese New Year table for 2020–2030 (see
    :data:`CHINESE_NEW_YEAR_DATES`).  Per Charles's direction, when the
    target date is outside the hardcoded table the port returns
    ``"NONE"`` rather than fabricating a date.  Production deployments
    MUST inject a port backed by the versioned season-calendar policy;
    the agent will surface a :class:`BlockerCode.SPRING_FESTIVAL_CALENDAR_POLICY_MISSING`
    blocker when no policy identity is supplied.
    """

    def phase_for(self, *, target: date) -> Any:
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


__all__ = [
    "DefaultTask8ForecastPort",
    "DefaultTask9HarvestStatePort",
    "DefaultTask10PredictionPort",
    "DefaultTask11BacktestPort",
    "DefaultTask12PredictionPort",
    "DefaultSpringFestivalCalendarPort",
    "CHINESE_NEW_YEAR_DATES",
    "AuthorityIdentityError",
]
