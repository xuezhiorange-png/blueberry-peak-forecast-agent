"""TASK-013 Slice A — default task loader implementations.

These wrappers translate the existing TASK-008/009/010/012 ORM rows
(loaded via the upstream ``load_*`` callables) into the TASK-013
:class:`~backend.app.agent.schemas.TaskNAuthority` envelopes.  No new
numerical computation happens here — every authoritative quantity is
sourced from the upstream ORM row.

**Fail-closed provenance discipline (P0-2)**

Per Charles's direction (2026-07-11 + 2026-07-12 round 5): no
re-hashing of arbitrary upstream strings to 64-hex, no ``date.today()``
patches, no ``datetime.now(tz=UTC)`` fallbacks, no ``"unknown"`` /
``"v0"`` placeholders, no ``model_run_id`` used as
``model_artifact_id``, no ``config_hash`` used as ``artifact_hash``,
no status/mode fields mapped into policy-version fields, and no
``except Exception: return None`` masking.

Each loader distinguishes EIGHT typed failure modes via
:class:`BlockerCode`:

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
* :data:`BlockerCode.UPSTREAM_READ_FAILURE` — any other unexpected
  upstream read exception.  NEVER folded silently into NOT_FOUND.

The new ``load_typed`` methods return a :class:`AuthorityLoadResult`
envelope carrying both the constructed authority (or ``None``) and the
list of typed blockers.  This allows the calling adapter to
distinguish NOT_FOUND from HASH_MALFORMED, ARTIFACT_MISSING, etc.

The legacy ``load_by_id`` method is preserved (returns ``authority |
None``) for backward compatibility with the
:class:`Task{N}AuthorityPort` Protocol; the default adapters now use
``load_typed`` so that the full blocker provenance is propagated.

The TASK-012 loader is read-only: TASK-012 is never POSTed by the
agent (per §22.1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.enums import BlockerCode, RetryHint
from backend.app.agent.schemas import (
    Blocker,
    Task8Authority,
    Task9Authority,
    Task10Authority,
    Task12Authority,
)

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

_T = TypeVar("_T", Task8Authority, Task9Authority, Task10Authority, Task12Authority)


# --- Typed authority load result ------------------------------------------


@dataclass(frozen=True)
class AuthorityLoadResult(Generic[_T]):  # noqa: UP046 — Generic[_T] is required for dataclass Generic support
    """Result envelope for a single authority load call (P0-2 round 5).

    Either the authority envelope is constructed (and ``blockers`` is
    empty) or the authority is ``None`` and ``blockers`` carries one
    typed blocker explaining the failure.  The previously-coarse
    ``load_by_id`` returning ``None`` is preserved as a thin shim but
    downstream adapters MUST use ``load_typed`` to distinguish:

    * row missing  → AUTHORITY_NOT_FOUND
    * hash malformed → AUTHORITY_HASH_MALFORMED
    * datetime malformed → AUTHORITY_DATETIME_MALFORMED
    * artifact missing → AUTHORITY_ARTIFACT_MISSING
    * policy_version missing → AUTHORITY_POLICY_VERSION_MISSING
    * identity malformed → AUTHORITY_IDENTITY_MALFORMED
    * lineage mismatch → AUTHORITY_LINEAGE_MISMATCH
    * unexpected read exception → UPSTREAM_READ_FAILURE
    """

    authority: _T | None
    blockers: tuple[Blocker, ...] = field(default_factory=tuple)

    @property
    def is_loaded(self) -> bool:
        return self.authority is not None

    @property
    def primary_blocker(self) -> Blocker | None:
        return self.blockers[0] if self.blockers else None


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


def _make_blocker(
    *,
    code: BlockerCode,
    field: str,
    message: str,
    details: dict[str, Any] | None = None,
    retry_hint: RetryHint = "FIX_INPUT",
) -> Blocker:
    """Build a typed :class:`Blocker` for an authority-load failure."""

    payload: dict[str, Any] = {"field": field}
    if details:
        payload.update(details)
    return Blocker(code=code, message=message, details=payload, retry_hint=retry_hint)


def _blocker_for_identity_error(*, field: str, exc: AuthorityIdentityError) -> Blocker:
    """Map an :class:`AuthorityIdentityError` to the most-specific blocker code.

    The original message contains hints like "is NULL", "is not a 64-char
    lowercase hex string", "is not UTC", etc.  The mapping here is
    intentionally narrow (string-match on the exception message) so
    that the typed failure mode is preserved without over-classifying.
    """

    msg = str(exc)
    if "64-char lowercase hex" in msg or "is NULL" in msg and "hash" in field:
        return _make_blocker(code=BlockerCode.AUTHORITY_HASH_MALFORMED, field=field, message=msg)
    if "UTC" in msg or "naive datetime" in msg or "ISO datetime" in msg:
        return _make_blocker(
            code=BlockerCode.AUTHORITY_DATETIME_MALFORMED, field=field, message=msg
        )
    if "policy_version" in field or "placeholder" in msg:
        return _make_blocker(
            code=BlockerCode.AUTHORITY_POLICY_VERSION_MISSING,
            field=field,
            message=msg,
        )
    if "artifact" in field:
        return _make_blocker(code=BlockerCode.AUTHORITY_ARTIFACT_MISSING, field=field, message=msg)
    if "as_of" in field or "as of" in field:
        return _make_blocker(code=BlockerCode.AUTHORITY_AS_OF_MISSING, field=field, message=msg)
    return _make_blocker(code=BlockerCode.AUTHORITY_IDENTITY_MALFORMED, field=field, message=msg)


def _maybe_version(value: Any, *, field: str) -> str | None:
    """Optional version validator.  Returns ``None`` when value is missing.

    When the value IS present, it is strictly validated via
    :func:`_strict_version` (rejects placeholders like ``"v0"`` /
    ``"unknown"`` / empty).  The caller is responsible for surfacing
    :data:`BlockerCode.AUTHORITY_POLICY_VERSION_MISSING` when ``None``
    is returned AND the field is required by the downstream consumer.
    """

    if value is None:
        return None
    return _strict_version(value, field=field)


# --- TASK-008 -----------------------------------------------------------


class DefaultTask8ForecastPort:
    """Default TASK-008 loader.

    Loads the persisted :class:`MaturityForecastRun` + linked
    :class:`MaturityModelRun` + linked :class:`MaturityModelArtifact`.
    Fails closed (typed blocker via :meth:`load_typed`) when:

    * the upstream row is absent;
    * the as-of date cannot be read from the persisted row;
    * the model artifact identity (``artifact_id`` / ``artifact_hash``)
      is missing or malformed;
    * any hash field is malformed.

    P0-2 round 5: ``maturity_model_artifact_hash`` is read from
    :class:`MaturityModelArtifact.artifact_hash` (the real
    ``maturity_model_artifact`` row linked by ``artifact_id``).  The
    previous implementation substituted ``model_run.config_hash`` for
    the artifact hash, which violated the P0-2 provenance discipline;
    that proxy is REMOVED.
    """

    async def load_typed(
        self,
        *,
        session: AsyncSession,
        forecast_run_id: int,
    ) -> AuthorityLoadResult[Task8Authority]:
        from backend.app.models.maturity import (
            MaturityForecastRun,
            MaturityModelArtifact,
            MaturityModelRun,
        )

        run = await session.get(MaturityForecastRun, int(forecast_run_id))
        if run is None:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_NOT_FOUND,
                        field="maturity_forecast_run",
                        message=(f"TASK-008 forecast_run_id={forecast_run_id} not found"),
                    ),
                ),
            )

        if run.model_run_id is None:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_LINEAGE_MISMATCH,
                        field="model_run_id",
                        message=(
                            f"TASK-008 forecast_run_id={forecast_run_id} has no "
                            "model_run_id lineage pointer"
                        ),
                    ),
                ),
            )

        model_run = await session.get(MaturityModelRun, int(run.model_run_id))
        if model_run is None:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_LINEAGE_MISMATCH,
                        field="model_run_id",
                        message=(
                            f"TASK-008 forecast_run_id={forecast_run_id} "
                            f"model_run_id={run.model_run_id} not found"
                        ),
                    ),
                ),
            )

        # Resolve the REAL artifact hash from ``maturity_model_artifact``
        # (the upstream table linked by ``MaturityForecastRun.artifact_id``).
        # Round 5: do NOT use ``model_run.config_hash`` as a proxy.
        artifact_id_raw = getattr(run, "artifact_id", None)
        artifact_hash: str | None = None
        artifact_id_strict: int | None = None
        if artifact_id_raw is None:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_ARTIFACT_MISSING,
                        field="maturity_model_artifact_id",
                        message=(
                            f"TASK-008 forecast_run_id={forecast_run_id} has no "
                            "maturity_model_artifact_id reference"
                        ),
                    ),
                ),
            )
        artifact_id_strict = _strict_int_id(artifact_id_raw, field="maturity_model_artifact_id")
        try:
            artifact = await session.get(MaturityModelArtifact, int(artifact_id_strict))
        except Exception as exc:  # noqa: BLE001
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.UPSTREAM_READ_FAILURE,
                        field="maturity_model_artifact",
                        message=(
                            f"unexpected upstream read error while loading "
                            f"maturity_model_artifact id={artifact_id_strict}: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    ),
                ),
            )
        if artifact is None or not getattr(artifact, "artifact_hash", None):
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_ARTIFACT_MISSING,
                        field="maturity_model_artifact_hash",
                        message=(
                            f"TASK-008 artifact_id={artifact_id_strict} has no "
                            "real artifact_hash on the persisted "
                            "maturity_model_artifact row"
                        ),
                    ),
                ),
            )
        try:
            artifact_hash = _strict_sha256_hex(
                artifact.artifact_hash, field="maturity_model_artifact_hash"
            )
        except AuthorityIdentityError as exc:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _blocker_for_identity_error(field="maturity_model_artifact_hash", exc=exc),
                ),
            )

        # Build the envelope from real persisted fields only.  Any
        # remaining malformed identity is reported with a typed blocker.
        try:
            return AuthorityLoadResult(
                authority=Task8Authority(
                    maturity_model_run_id=_strict_int_id(
                        model_run.id, field="maturity_model_run_id"
                    ),
                    maturity_model_version=_strict_version(
                        model_run.model_version, field="maturity_model_version"
                    ),
                    maturity_model_config_hash=_strict_sha256_hex(
                        model_run.config_hash, field="maturity_model_config_hash"
                    ),
                    maturity_model_source_signature=str(model_run.source_signature),
                    maturity_model_artifact_id=artifact_id_strict,
                    maturity_model_artifact_hash=artifact_hash,
                    maturity_forecast_run_id=_strict_int_id(
                        run.id, field="maturity_forecast_run_id"
                    ),
                    maturity_forecast_source_signature=str(run.source_signature),
                    maturity_forecast_as_of_date=_strict_date(
                        run.as_of_date, field="maturity_forecast_as_of_date"
                    ),
                )
            )
        except AuthorityIdentityError as exc:
            return AuthorityLoadResult(
                authority=None,
                blockers=(_blocker_for_identity_error(field="task8_identity", exc=exc),),
            )

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        forecast_run_id: int,
    ) -> Task8Authority | None:
        result = await self.load_typed(session=session, forecast_run_id=forecast_run_id)
        return result.authority


# --- TASK-009 -----------------------------------------------------------


class DefaultTask9HarvestStatePort:
    """Default TASK-009 loader.

    Loads the persisted :class:`HarvestStateRun` row and projects every
    required identity field.  Fails closed (typed blocker via
    :meth:`load_typed`) when the row is absent or any required identity
    field is malformed.
    """

    async def load_typed(
        self,
        *,
        session: AsyncSession,
        harvest_state_run_id: int,
    ) -> AuthorityLoadResult[Task9Authority]:
        from backend.app.models.harvest_state import HarvestStateRun

        try:
            row = await session.get(HarvestStateRun, int(harvest_state_run_id))
        except Exception as exc:  # noqa: BLE001
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.UPSTREAM_READ_FAILURE,
                        field="harvest_state_run",
                        message=(
                            f"unexpected upstream read error while loading "
                            f"harvest_state_run id={harvest_state_run_id}: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    ),
                ),
            )
        if row is None:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_NOT_FOUND,
                        field="harvest_state_run",
                        message=(f"TASK-009 harvest_state_run_id={harvest_state_run_id} not found"),
                    ),
                ),
            )
        try:
            return AuthorityLoadResult(
                authority=Task9Authority(
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
                        row.output_schema_version,
                        field="harvest_state_output_schema_version",
                    ),
                    harvest_state_as_of_date=_strict_date(
                        row.as_of_date, field="harvest_state_as_of_date"
                    ),
                    harvest_state_forecast_start_date=_strict_date(
                        row.forecast_start_date,
                        field="harvest_state_forecast_start_date",
                    ),
                    harvest_state_forecast_end_date=_strict_date(
                        row.forecast_end_date,
                        field="harvest_state_forecast_end_date",
                    ),
                    destination_factory_id=_strict_int_id(
                        row.destination_factory_id, field="destination_factory_id"
                    ),
                    pool_row_count=_strict_int_id(row.pool_row_count, field="pool_row_count"),
                    member_row_count=_strict_int_id(row.member_row_count, field="member_row_count"),
                    cohort_row_count=_strict_int_id(row.cohort_row_count, field="cohort_row_count"),
                    future_arrival_row_count=_strict_int_id(
                        row.future_arrival_row_count,
                        field="future_arrival_row_count",
                    ),
                    source_ref_schema_version=_strict_version(
                        row.source_ref_schema_version,
                        field="source_ref_schema_version",
                    ),
                    result_hash_schema_version=_strict_version(
                        row.result_hash_schema_version,
                        field="result_hash_schema_version",
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
            )
        except AuthorityIdentityError as exc:
            return AuthorityLoadResult(
                authority=None,
                blockers=(_blocker_for_identity_error(field="task9_identity", exc=exc),),
            )

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        harvest_state_run_id: int,
    ) -> Task9Authority | None:
        result = await self.load_typed(session=session, harvest_state_run_id=harvest_state_run_id)
        return result.authority


# --- TASK-010 -----------------------------------------------------------


class DefaultTask10PredictionPort:
    """Default TASK-010 loader.

    Loads the persisted :class:`ResidualModelPredictionRun` row.  All
    hash columns are strictly validated.  The upstream returns a
    :class:`ResidualModelPersistedPredictionRun` dataclass; we read the
    fields via ``getattr`` because the dataclass may be partially populated
    during replay.
    """

    async def load_typed(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> AuthorityLoadResult[Task10Authority]:
        from backend.app.harvest_state.persistence import (
            HarvestStatePersistenceIntegrityError,
        )
        from backend.app.residual_model.persistence import (
            ResidualModelPersistenceIntegrityError,
            load_residual_prediction_run_by_id,
        )

        try:
            result = await load_residual_prediction_run_by_id(session, run_id=prediction_run_id)
        except (ValueError, KeyError) as exc:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_IDENTITY_MALFORMED,
                        field="residual_prediction_run",
                        message=(
                            f"upstream identity-mismatch loading "
                            f"residual_prediction_run id={prediction_run_id}: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    ),
                ),
            )
        except (
            ResidualModelPersistenceIntegrityError,
            HarvestStatePersistenceIntegrityError,
        ) as exc:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_HASH_MALFORMED,
                        field="residual_prediction_run",
                        message=(
                            f"upstream persistence integrity error loading "
                            f"residual_prediction_run id={prediction_run_id}: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    ),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.UPSTREAM_READ_FAILURE,
                        field="residual_prediction_run",
                        message=(
                            f"unexpected upstream read error while loading "
                            f"residual_prediction_run id={prediction_run_id}: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    ),
                ),
            )
        if result is None:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_NOT_FOUND,
                        field="residual_prediction_run",
                        message=(f"TASK-010 prediction_run_id={prediction_run_id} not found"),
                    ),
                ),
            )

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

            return AuthorityLoadResult(
                authority=Task10Authority(
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
            )
        except AuthorityIdentityError as exc:
            return AuthorityLoadResult(
                authority=None,
                blockers=(_blocker_for_identity_error(field="task10_identity", exc=exc),),
            )

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> Task10Authority | None:
        result = await self.load_typed(session=session, prediction_run_id=prediction_run_id)
        return result.authority


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

    Fails closed (typed blocker via :meth:`load_typed`) when the upstream
    returns :class:`ReplayTrainedPersistedIdentityIntegrityError` (any
    of the 14 P0-#5 integrity conditions fails) or when the loader
    cannot find the row.  No datetime fallback to
    ``datetime.now(tz=UTC)``, no policy version placeholder, no
    fabricated artifact hash.

    Round 5: policy-version fields are read from the matching real
    ``persisted.*_policy_version`` columns.  Status-like fields
    (``model_policy`` / ``prediction_mode`` /
    ``prediction_execution_status`` / ``training_eligibility_status``)
    are NOT used as policy-version substitutions.
    """

    async def load_typed(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> AuthorityLoadResult[Task12Authority]:
        from backend.app.rolling_backtest.replay_trained_service import (
            ReplayTrainedPersistedIdentityIntegrityError,
            ReplayTrainedServiceNotFoundError,
            load_replay_trained_prediction,
        )

        try:
            persisted = await load_replay_trained_prediction(
                session, prediction_run_id=prediction_run_id
            )
        except ReplayTrainedServiceNotFoundError as exc:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_NOT_FOUND,
                        field="replay_trained_prediction",
                        message=(
                            f"TASK-012 prediction_run_id={prediction_run_id} "
                            f"not found: {type(exc).__name__}: {exc}"
                        ),
                    ),
                ),
            )
        except ReplayTrainedPersistedIdentityIntegrityError as exc:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_HASH_MALFORMED,
                        field="replay_trained_prediction",
                        message=(
                            f"TASK-012 identity integrity check failed for "
                            f"prediction_run_id={prediction_run_id}: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    ),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.UPSTREAM_READ_FAILURE,
                        field="replay_trained_prediction",
                        message=(
                            f"unexpected upstream read error while loading "
                            f"replay_trained_prediction id={prediction_run_id}: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                    ),
                ),
            )
        if persisted is None:
            return AuthorityLoadResult(
                authority=None,
                blockers=(
                    _make_blocker(
                        code=BlockerCode.AUTHORITY_NOT_FOUND,
                        field="replay_trained_prediction",
                        message=(f"TASK-012 prediction_run_id={prediction_run_id} not found"),
                    ),
                ),
            )

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

            return AuthorityLoadResult(
                authority=Task12Authority(
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
                    # P0-2 round 5: the four policy-version fields are
                    # read from the matching persisted *policy_version*
                    # columns (or absent on older schema revisions).
                    # Status-like fields (model_policy / prediction_mode
                    # / prediction_execution_status /
                    # training_eligibility_status) are NOT mapped into
                    # policy-version slots.  When the persisted identity
                    # does not expose a real ``*_policy_version``
                    # column, the value stays None and the loader
                    # surfaces AUTHORITY_POLICY_VERSION_MISSING via
                    # the adapter-side result envelope.
                    validation_policy_version=_maybe_version(
                        getattr(persisted, "validation_policy_version", None),
                        field="validation_policy_version",
                    ),
                    label_visibility_policy_version=_maybe_version(
                        getattr(persisted, "label_visibility_policy_version", None),
                        field="label_visibility_policy_version",
                    ),
                    feature_visibility_policy_version=_maybe_version(
                        getattr(persisted, "feature_visibility_policy_version", None),
                        field="feature_visibility_policy_version",
                    ),
                    artifact_visibility_policy_version=_maybe_version(
                        getattr(persisted, "artifact_visibility_policy_version", None),
                        field="artifact_visibility_policy_version",
                    ),
                    model_artifact_hash=model_artifact_hash,
                    task9_replay_binding_identity=_strict_sha256_hex(
                        persisted.audit_identity, field="task9_replay_binding_identity"
                    ),
                    task10_manifest_hash=task10_manifest_hash,
                    task10_config_hash=task10_config_hash,
                )
            )
        except AuthorityIdentityError as exc:
            return AuthorityLoadResult(
                authority=None,
                blockers=(_blocker_for_identity_error(field="task12_identity", exc=exc),),
            )

    async def load_by_id(
        self,
        *,
        session: AsyncSession,
        prediction_run_id: int,
    ) -> Task12Authority | None:
        result = await self.load_typed(session=session, prediction_run_id=prediction_run_id)
        return result.authority


# --- Spring festival calendar port --------------------------------------


# Hardcoded reference table for 2020–2030, kept ONLY for unit-test
# fixtures.  The default production calendar port MUST be replaced
# with a versioned-season-calendar policy implementation.  This
# constant is no longer the default production authority (P0-7
# round 5).
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
    """Default spring-festival calendar port (P0-7 round 5).

    The default port returns ``"NONE"`` for every date and records the
    absence of a versioned season-calendar policy via the
    :data:`BlockerCode.SPRING_FESTIVAL_CALENDAR_POLICY_MISSING` blocker
    contract.  Production deployments MUST inject a port backed by the
    real versioned season-calendar policy (i.e. a policy carrying
    ``policy_version`` + ``config_hash`` + ``effective_range``).

    The hardcoded 2020–2030 table (:data:`CHINESE_NEW_YEAR_DATES`) is
    intentionally NOT consulted by the default port.  It is preserved
    only as a test fixture (see :class:`HardcodedSpringFestivalCalendarPort`).
    """

    policy_version: str = ""
    config_hash: str | None = None

    def phase_for(self, *, target: date) -> str:
        # Fail-closed: with no versioned policy, the phase is always
        # "NONE" and the producer (BaselineCompositionResult) is
        # expected to emit a SPRING_FESTIVAL_CALENDAR_POLICY_MISSING
        # blocker when calendar policy is required.
        return "NONE"

    def is_policy_loaded(self) -> bool:
        return bool(self.policy_version) and self.config_hash is not None


class HardcodedSpringFestivalCalendarPort:
    """Test-fixture port backed by :data:`CHINESE_NEW_YEAR_DATES`.

    NOT a default production source.  This class exists so that
    tests can opt into the 2020–2030 hardcoded table without
    contaminating the default production path.
    """

    policy_version: str = "test-fixture/v1"
    config_hash: str = "f" * 64

    def phase_for(self, *, target: date) -> str:
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

    def is_policy_loaded(self) -> bool:
        return True


__all__ = [
    "DefaultTask8ForecastPort",
    "DefaultTask9HarvestStatePort",
    "DefaultTask10PredictionPort",
    "DefaultTask11BacktestPort",
    "DefaultTask12PredictionPort",
    "DefaultSpringFestivalCalendarPort",
    "HardcodedSpringFestivalCalendarPort",
    "CHINESE_NEW_YEAR_DATES",
    "AuthorityIdentityError",
    "AuthorityLoadResult",
]
