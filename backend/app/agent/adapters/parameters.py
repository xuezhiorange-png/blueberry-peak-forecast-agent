"""TASK-013 Slice A — ``infer_parameters`` deterministic adapter.

This adapter walks the **eight** logical parameter schemas defined in
``docs/task-013-minimal-input-deterministic-agent-orchestration-design.md``:

* ``expected_per_mu_yield``
* ``commodity_fruit_rate``
* ``first_harvest_date``
* ``maturity_curve``
* ``spring_festival_harvest_rate``
* ``weather_adjustment``
* ``post_spring_festival_backlog_release_intensity``
* ``historical_anomaly_peak_probability``

For each ``(variety, parameter)`` the adapter asks the
:class:`ParameterPriorPort` for a real ``ParameterPrior`` derived from the
existing TASK-005/006/007/008 ``ParameterObservation`` ORM rows via the
upstream :func:`backend.app.planning.inference.infer_parameter` callable.

**Strict capability-boundary policy (round 5).**

The TASK-013 design freezes 8 logical schemas, but the upstream
``parameter_observation`` ORM table only stores 7 ``parameter_type``
values (see ``PARAMETER_UNITS`` in ``backend.app.planning.service``):

* ``yield_kg_per_mu`` ← ``expected_per_mu_yield``
* ``marketable_rate`` ← ``commodity_fruit_rate``
* ``first_harvest_offset_days`` ← ``first_harvest_date``
* ``maturity_peak_offset_days`` + ``maturity_width_days`` +
  ``maturity_skewness`` ← ``maturity_curve`` (3 components)
* ``harvest_realization_rate`` ← (no design schema in Slice A; reserved)

The remaining 4 design schemas have **no persisted prior source** in
the current upstream:

* ``spring_festival_harvest_rate``
* ``weather_adjustment``
* ``post_spring_festival_backlog_release_intensity``
* ``historical_anomaly_peak_probability``

Per Charles's direction (2026-07-12 round 5): KEEP_EIGHT_LOGICAL_PARAMETER_SCHEMAS /
NO_NEW_MIGRATION_IN_SLICE_A / NO_NEW_UPSTREAM_PERSISTENCE_TABLE /
SUPPORTED_PARAMETERS_USE_REAL_PERSISTED_EVIDENCE /
UNSUPPORTED_PARAMETERS_RETURN_STRUCTURED_BLOCKERS /
NO_FABRICATED_NUMERICAL_PRIORS / STRING_VARIETY_RESOLVED_VIA_CATALOG /
VERSIONED_INFERENCE_CONFIG_LOADED / PERSISTED_RESOLVED_LOCATION_PROPAGATED /
MATURITY_CURVE_3_COMPONENTS_REQUIRED.

Round 5 changes:

1. The string variety identity is resolved through the real
   :class:`Variety` catalog (``Variety.code → Variety.id``).  The
   previous ``_to_int_variety_id`` helper that returned ``0`` for
   non-numeric codes is REMOVED.  Unknown codes return
   :data:`BlockerCode.UNKNOWN_VARIETY` (not
   :data:`BlockerCode.INSUFFICIENT_HISTORY`).
2. The default port loads the real versioned parameter inference
   config from :func:`backend.app.planning.config.load_parameter_inference_config`
   (path = ``configs/parameter_inference.yaml``).  When the config
   is missing, malformed, or its hash is not a 64-char lowercase hex
   string, the port surfaces
   :data:`BlockerCode.INFERENCE_CONFIG_MISSING` /
   :data:`BlockerCode.INFERENCE_CONFIG_HASH_MALFORMED` and
   ``infer_parameter`` is NOT called.  No in-code default ruleset
   fallback is permitted on the production path.
3. The default port constructs a real
   :class:`backend.app.planning.schemas.ResolvedLocation` from the
   persisted :class:`LocationReference` row linked by
   ``resolved_location.location_reference_id`` and passes that to
   :func:`infer_parameter` (no more ``resolved_location=None``).
4. ``maturity_curve`` is computed as a 3-component vector (peak
   offset / width / skewness).  All three components must have
   visible observations; if any component is missing the entire
   ``maturity_curve`` returns
   :data:`BlockerCode.INSUFFICIENT_HISTORY` with details listing
   the missing component(s).  No fabrication of width/skewness
   from the peak scalar.
5. Concretely:

   * 4 supported logical parameters (``expected_per_mu_yield``,
     ``commodity_fruit_rate``, ``first_harvest_date``,
     ``maturity_curve``) execute real inference.
   * 4 unsupported parameters return
     :data:`BlockerCode.NO_PERSISTED_PRIOR_SOURCE` (per-variety,
     per-parameter).
6. The :class:`ParameterEstimate` list only contains successfully
   inferred parameters.  Missing parameter categories DO NOT appear
   as zeros, ones, schema defaults, or copies of other categories.
7. :func:`parameters_hash` is sensitive to the exact set of
   successfully inferred parameter identities — different
   blocked-parameter sets yield different hashes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.canonical import parameters_hash as _parameters_hash_fn
from backend.app.agent.enums import BlockerCode, Confidence
from backend.app.agent.ports import ParameterPriorPort, VarietyCatalogPort
from backend.app.agent.schemas import (
    Blocker,
    Citation,
    InferParametersInput,
    InferParametersOutput,
    ParameterEstimate,
    ResolvedLocation,
    UncertaintyWideningPolicy,
)


class SourceCapabilityGapError(RuntimeError):
    """Raised when a required upstream source is missing.

    Per the design, Slice A MUST NOT invent YAML constants or numeric
    priors.  If a parameter category has no concrete persisted prior source,
    this error is raised and the round is required to STOP and report.
    """


# --- Round 6 typed parameter-failure exceptions (P0-2) --------------------
#
# Each error class maps to exactly ONE :class:`BlockerCode` in the
# adapter layer.  Catching the broad :class:`SourceCapabilityGapError`
# is no longer acceptable — the round-5 review required the agent to
# preserve the typed failure mode so consumers can distinguish:
#
# * missing config (infrastructure gap) — INFERENCE_CONFIG_MISSING
# * malformed config hash (data corruption) — INFERENCE_CONFIG_HASH_MALFORMED
# * missing location reference (infrastructure gap) — LOCATION_SOURCE_CAPABILITY_MISSING
# * unknown variety code (input gap) — UNKNOWN_VARIETY
# * insufficient observations (data gap) — INSUFFICIENT_HISTORY
# * upstream read failure (infrastructure failure) — UPSTREAM_READ_FAILURE
# * truly unsupported parameter category (slice-A scope gap) — NO_PERSISTED_PRIOR_SOURCE
#
# All exceptions are subclasses of :class:`SourceCapabilityGapError` so
# legacy call sites that catch the base class still work; new code should
# catch the specific subclass to preserve the typed blocker identity.


class InferenceConfigMissingError(SourceCapabilityGapError):
    """Versioned parameter-inference config file is missing on disk.

    Maps to :data:`BlockerCode.INFERENCE_CONFIG_MISSING`.
    """


class InferenceConfigHashMalformedError(SourceCapabilityGapError):
    """Versioned parameter-inference config hash is malformed.

    Maps to :data:`BlockerCode.INFERENCE_CONFIG_HASH_MALFORMED`.
    """


class LocationSourceCapabilityMissingError(SourceCapabilityGapError):
    """Persisted LocationReference row is absent or missing required
    coordinates (latitude / longitude).

    Maps to :data:`BlockerCode.LOCATION_SOURCE_CAPABILITY_MISSING`.
    """


class UnknownVarietyCapabilityError(SourceCapabilityGapError):
    """Variety code is not present in the catalog.

    Maps to :data:`BlockerCode.UNKNOWN_VARIETY`.  Distinct from
    :class:`UnknownVarietyError` which is a programmatic catalog-level
    exception (re-raised by ports); this one is the parameter-adapter
    typed gap.
    """


class InsufficientHistoryError(SourceCapabilityGapError):
    """No visible prior observations at any priority step.

    Maps to :data:`BlockerCode.INSUFFICIENT_HISTORY`.
    """


class UpstreamReadFailureError(SourceCapabilityGapError):
    """Unrecoverable upstream read failure (config / catalog / observation).

    Maps to :data:`BlockerCode.UPSTREAM_READ_FAILURE`.
    """


class UnknownVarietyError(Exception):
    """Raised when a variety_id is not present in the variety catalog."""


class VarietyCatalogReadFailure(RuntimeError):
    """Raised when the Variety catalog cannot be read from the session.

    Round 5: per Charles's direction, an unexpected read failure on the
    Variety catalog is NOT silently mapped to an empty mapping.  The
    caller must surface the failure as
    :data:`BlockerCode.UPSTREAM_READ_FAILURE`.
    """


class DefaultVarietyCatalogPort(VarietyCatalogPort):
    """Default :class:`VarietyCatalogPort` calling ``planning.plan_repository``.

    Round 5: the catalog lookup returns the persisted :class:`Variety`
    row (carrying both the string ``code`` and the int ``id``).  The
    default prior port uses this to resolve ``Variety.code → Variety.id``
    before querying :class:`ParameterObservation`.  No
    ``_to_int_variety_id`` coercion of arbitrary string codes.
    """

    async def is_known(self, *, session: AsyncSession, variety_id: str) -> bool:
        row = await self.lookup_row(session=session, variety_id=variety_id)
        return row is not None

    async def lookup_row(self, *, session: AsyncSession, variety_id: str) -> Any | None:
        try:
            from backend.app.planning.plan_repository import get_variety_by_code
        except ImportError:
            return None
        try:
            row = await get_variety_by_code(session, variety_code=str(variety_id))
        except Exception as exc:  # noqa: BLE001
            raise VarietyCatalogReadFailure(
                f"Variety catalog read failed: {type(exc).__name__}: {exc}"
            ) from exc
        if row is None:
            raise UnknownVarietyError(f"variety_id is not in the variety catalog: {variety_id}")
        return row


# --- Logical → upstream mapping (frozen) ---------------------------------


# The TASK-013 design exposes 8 logical parameter schemas.  Each one maps
# to EITHER a single upstream ``parameter_type`` string OR a tuple of
# upstream parameter types (when the design exposes one logical schema as
# a composition of upstream scalars), OR is unsupported.
LOGICAL_TO_UPSTREAM: dict[str, tuple[str, ...] | None] = {
    "expected_per_mu_yield": ("yield_kg_per_mu",),
    "commodity_fruit_rate": ("marketable_rate",),
    "first_harvest_date": ("first_harvest_offset_days",),
    "maturity_curve": (
        "maturity_peak_offset_days",
        "maturity_width_days",
        "maturity_skewness",
    ),
    # 4 categories below have no real persisted prior source in
    # ``parameter_observation`` as of Slice A.  Per Charles, the schemas
    # are KEPT but each emits a NO_PERSISTED_PRIOR_SOURCE blocker.
    "spring_festival_harvest_rate": None,
    "weather_adjustment": None,
    "post_spring_festival_backlog_release_intensity": None,
    "historical_anomaly_peak_probability": None,
}

ALL_LOGICAL_PARAMETERS: tuple[str, ...] = (
    "expected_per_mu_yield",
    "commodity_fruit_rate",
    "first_harvest_date",
    "maturity_curve",
    "spring_festival_harvest_rate",
    "weather_adjustment",
    "post_spring_festival_backlog_release_intensity",
    "historical_anomaly_peak_probability",
)

# Visibility predicate (matches ``_load_candidates`` in
# ``backend.app.planning.service``).


def is_visible_prior(
    *,
    effective_from: date | None,
    effective_to: date | None,
    available_at: date | None,
    effective_as_of_date: date,
) -> bool:
    if effective_from is not None and effective_from > effective_as_of_date:
        return False
    if effective_to is not None and effective_to < effective_as_of_date:
        return False
    if available_at is not None and available_at > effective_as_of_date:
        return False
    return True


# --- Step ordering + monotonic widening ----------------------------------

STEP_RANK = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}

_UPSTREAM_SOURCE_LEVEL_STEP = {
    "same_farm_variety": 1,
    "same_township_altitude_variety": 2,
    "same_county_climate_zone_variety": 3,
    "same_province_variety": 4,
    "literature_variety_prior": 5,
}


def widening_factor_for(step: int, policy: UncertaintyWideningPolicy) -> Decimal:
    if step not in STEP_RANK:
        raise ValueError(f"unknown priority step: {step}")
    key = {
        1: "step_1_same_farm_same_variety_high_evidence",
        2: "step_2_same_township_similar_altitude",
        3: "step_3_same_county_same_climate_zone",
        4: "step_4_province_level_same_variety",
        5: "step_5_variety_document_prior_only",
    }[step]
    raw = policy.factors_by_source_level.get(key)
    if raw is None:
        raise SourceCapabilityGapError(f"UncertaintyWideningPolicy is missing factor for {key}")
    return Decimal(raw)


def confidence_for_step(step: int) -> Confidence:
    if step == 1:
        return "HIGH"
    if step in (2, 3):
        return "MEDIUM"
    return "LOW"


def source_level_step(value: Any, *, fallback_step: int) -> int:
    """Map the upstream planning taxonomy to the Agent's stable step rank."""

    if value is None:
        return fallback_step
    if isinstance(value, int) and not isinstance(value, bool) and value in STEP_RANK:
        return value
    if isinstance(value, str) and value in _UPSTREAM_SOURCE_LEVEL_STEP:
        return _UPSTREAM_SOURCE_LEVEL_STEP[value]
    raise SourceCapabilityGapError(f"unknown upstream source_level: {value!r}")


# --- Default port (delegates to upstream planning inference) ------------


@dataclass(frozen=True)
class ParameterPrior:
    parameter_name: str
    variety_id: str
    p50: Decimal | None
    p80_lower: Decimal | None
    p80_upper: Decimal | None
    source_level: int
    confidence: Confidence
    sample_count: int
    season_count: int
    farm_count: int
    source_observation_ids: tuple[int, ...]
    missing_evidence: tuple[str, ...]
    visibility_effective_from: date | None = None
    visibility_effective_to: date | None = None
    visibility_available_at: date | None = None
    # maturity_curve-only fields (None for all other parameters)
    maturity_peak_offset_days: Decimal | None = None
    maturity_width_days: Decimal | None = None
    maturity_skewness: Decimal | None = None


def _default_inference_config_path() -> Path:
    """Return the canonical on-disk path of the parameter inference config.

    Mirrors the path used by the upstream :func:`load_parameter_inference_config`
    adapter (``configs/parameter_inference.yaml``).  Tests can override
    the path by setting the ``AGENT_PARAMETER_INFERENCE_CONFIG_PATH``
    environment variable.
    """

    import os

    override = os.environ.get("AGENT_PARAMETER_INFERENCE_CONFIG_PATH")
    if override:
        return Path(override)
    return Path("configs/parameter_inference.yaml")


def _load_inference_rules_or_raise(
    config_path: Path,
) -> tuple[Any, str, str]:
    """Load the real versioned parameter inference config (P0-1 #5).

    Returns a tuple ``(rules, config_version, config_hash)``.  Raises
    :class:`InferenceConfigMissingError` when the config file is
    missing, :class:`InferenceConfigHashMalformedError` when the
    config_hash field is malformed, and :class:`UpstreamReadFailureError`
    on any other load failure.  No in-code default ruleset fallback is
    permitted.
    """

    import re

    from backend.app.planning.config import load_parameter_inference_config

    if not config_path.exists():
        raise InferenceConfigMissingError(
            f"parameter inference config not found at {config_path!s} "
            "(required by P0-1 round 5: versioned config must be loaded "
            "from the on-disk YAML)"
        )
    try:
        config = load_parameter_inference_config(config_path)
    except Exception as exc:  # noqa: BLE001
        raise UpstreamReadFailureError(
            f"parameter inference config at {config_path!s} failed to load: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    rules = getattr(config, "rules", None)
    config_version = str(getattr(rules, "resolver_version", "") or "")
    config_hash = str(getattr(config, "config_hash", "") or "")
    if not config_version or config_version in {"v0", "unknown"}:
        raise InferenceConfigHashMalformedError(
            f"parameter inference config at {config_path!s} has invalid "
            f"resolver_version={config_version!r}"
        )
    if not re.fullmatch(r"[0-9a-f]{64}", config_hash or ""):
        raise InferenceConfigHashMalformedError(
            f"parameter inference config at {config_path!s} has invalid "
            f"config_hash={config_hash!r} (expected 64-char lowercase hex)"
        )
    return rules, config_version, config_hash


def _build_upstream_resolved_location(
    *, agent_resolved_location: ResolvedLocation, location_reference: Any
) -> Any:
    """Build the upstream :class:`ResolvedLocation` (P0-1 #6).

    The upstream dataclass requires latitude, longitude, and
    optional altitude.  These are read from the persisted
    :class:`LocationReference` row linked by
    ``agent_resolved_location.location_reference_id``.  When the
    reference is missing, the missing fields surface as
    :data:`BlockerCode.LOCATION_SOURCE_CAPABILITY_MISSING`.
    """

    from backend.app.planning.schemas import ResolvedLocation as UpstreamResolvedLocation

    if location_reference is None:
        return None
    latitude = getattr(location_reference, "latitude", None)
    longitude = getattr(location_reference, "longitude", None)
    if latitude is None or longitude is None:
        return None
    return UpstreamResolvedLocation(
        status="resolved",
        location_reference_id=int(getattr(location_reference, "id", 0) or 0) or None,
        address_raw=agent_resolved_location.address_raw,
        address_normalized=agent_resolved_location.address_normalized or "",
        province=agent_resolved_location.province,
        prefecture=agent_resolved_location.prefecture,
        county=agent_resolved_location.county,
        township=agent_resolved_location.township,
        village=None,
        farm_name=agent_resolved_location.farm_name,
        latitude=Decimal(str(latitude)),
        longitude=Decimal(str(longitude)),
        altitude_m=(
            Decimal(str(getattr(location_reference, "altitude_m", "")))
            if getattr(location_reference, "altitude_m", None) is not None
            else None
        ),
        climate_zone_id=agent_resolved_location.climate_zone_id,
        climate_zone_code=agent_resolved_location.climate_zone_code,
        climate_zone_mapping_method=None,
        climate_zone_confidence=(
            Decimal(str(agent_resolved_location.mapping_confidence))
            if agent_resolved_location.mapping_confidence is not None
            else None
        ),
        candidate_count=len(agent_resolved_location.candidates),
        confidence_score=(
            Decimal(str(agent_resolved_location.score))
            if agent_resolved_location.score is not None
            else None
        ),
        warnings=((agent_resolved_location.warning,) if agent_resolved_location.warning else ()),
        candidates=tuple(agent_resolved_location.candidates),
        reproducibility_snapshot={
            "agent_status": agent_resolved_location.status,
            "agent_matched_location_method": str(agent_resolved_location.matched_location_method),
        },
    )


class DefaultParameterPriorPort:
    """Real persisted observation port (P0-1 round 5).

    Loads :class:`ParameterObservation` rows for the given
    ``(variety_id, parameter_type)``, applies the §26.1 visibility
    predicate, projects the rows to :class:`CandidateObservation`
    objects, and calls :func:`infer_parameter` from the upstream
    pipeline.  The default port:

    * resolves the string variety identity through the real
      :class:`Variety` catalog (no ``int()`` coercion);
    * loads the real versioned :func:`load_parameter_inference_config`
      from the on-disk YAML (no in-code default ruleset fallback);
    * builds a real upstream :class:`ResolvedLocation` from the
      persisted :class:`LocationReference` row (no
      ``resolved_location=None``);
    * handles the 3-component ``maturity_curve`` schema end-to-end.
    """

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        catalog: VarietyCatalogPort | None = None,
    ) -> None:
        self._config_path = config_path or _default_inference_config_path()
        self._catalog = catalog or DefaultVarietyCatalogPort()

    async def resolve_parameter(
        self,
        *,
        session: AsyncSession,
        variety_id: str,
        parameter_name: str,
        resolved_location: ResolvedLocation,
        effective_as_of_date: date,
        widening_factor: Decimal,
        monotonic_step: int,
    ) -> ParameterPrior:
        if monotonic_step not in STEP_RANK:
            raise SourceCapabilityGapError(f"unknown monotonic step: {monotonic_step}")

        if parameter_name not in ALL_LOGICAL_PARAMETERS:
            raise SourceCapabilityGapError(f"unknown logical parameter_name: {parameter_name!r}")

        upstream_types = LOGICAL_TO_UPSTREAM.get(parameter_name)
        if upstream_types is None:
            raise SourceCapabilityGapError(
                f"logical parameter {parameter_name!r} has no persisted upstream parameter_type"
            )

        # Variety code → PK resolution (P0-1 #4): use the catalog.
        try:
            variety_row = await self._catalog.lookup_row(session=session, variety_id=variety_id)
        except UnknownVarietyError:
            raise UnknownVarietyCapabilityError(
                f"variety_id is not in the variety catalog: {variety_id!r}"
            ) from None
        except VarietyCatalogReadFailure as exc:
            # UPSTREAM_READ_FAILURE on the Variety catalog itself must
            # propagate; the adapter surfaces it via
            # :data:`BlockerCode.UPSTREAM_READ_FAILURE`.
            raise UpstreamReadFailureError(str(exc)) from exc
        if variety_row is None:
            raise UnknownVarietyCapabilityError(
                f"variety_id is not in the variety catalog: {variety_id!r}"
            )
        variety_pk = int(variety_row.id)

        # Load the real versioned inference config (P0-1 #5).
        # Raises InferenceConfigMissingError / InferenceConfigHashMalformedError /
        # UpstreamReadFailureError on failure.
        rules, config_version, config_hash = _load_inference_rules_or_raise(self._config_path)

        # Load the real persisted LocationReference (P0-1 #6).
        try:
            location_reference = await _load_location_reference(
                session=session,
                location_reference_id=resolved_location.location_reference_id,
            )
        except LocationSourceCapabilityMissingError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UpstreamReadFailureError(
                f"location_reference read failed: {type(exc).__name__}: {exc}"
            ) from exc
        upstream_resolved_location = _build_upstream_resolved_location(
            agent_resolved_location=resolved_location,
            location_reference=location_reference,
        )
        if upstream_resolved_location is None:
            # P0-1 #6: missing location reference or required
            # coordinates → LOCATION_SOURCE_CAPABILITY_MISSING blocker.
            # We do NOT call ``infer_parameter`` in this case.
            raise LocationSourceCapabilityMissingError(
                f"persisted LocationReference id={resolved_location.location_reference_id} "
                f"is absent or missing required coordinates (latitude / longitude)"
            )

        from backend.app.planning.inference import infer_parameter

        if parameter_name == "maturity_curve":
            # P0-1 #7: 3-component maturity_curve.  All three
            # components must have visible observations; otherwise the
            # entire maturity_curve is blocked (INSUFFICIENT_HISTORY
            # listing the missing component(s)).
            return await _resolve_maturity_curve(
                session=session,
                variety_id=variety_id,
                variety_pk=variety_pk,
                resolved_location=resolved_location,
                upstream_resolved_location=upstream_resolved_location,
                effective_as_of_date=effective_as_of_date,
                rules=rules,
                monotonic_step=monotonic_step,
                config_version=config_version,
                config_hash=config_hash,
            )

        # Single-upstream-type logical parameter
        primary_type = upstream_types[0]
        try:
            candidates = await _load_candidates_from_orm(
                session=session,
                variety_id=variety_pk,
                parameter_type=primary_type,
                effective_as_of_date=effective_as_of_date,
                resolved_location=resolved_location,
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamReadFailureError(
                f"ParameterObservation read failed: {type(exc).__name__}: {exc}"
            ) from exc
        if not candidates:
            raise InsufficientHistoryError(
                f"no visible observations for variety_id={variety_id} "
                f"parameter_type={primary_type} as_of={effective_as_of_date.isoformat()}"
            )

        floor, ceiling = _parameter_bounds(primary_type)
        result = infer_parameter(
            parameter_type=primary_type,
            candidates=candidates,
            rules=rules,
            floor=floor,
            ceiling=ceiling,
            resolved_location=upstream_resolved_location,
            as_of_date=effective_as_of_date,
        )
        return _build_parameter_prior_from_inference_result(
            result=result,
            parameter_name=parameter_name,
            variety_id=variety_id,
            monotonic_step=monotonic_step,
        )


def _unsupported_prior(
    *,
    parameter_name: str,
    variety_id: str,
    monotonic_step: int,
    missing_evidence: tuple[str, ...],
) -> ParameterPrior:
    return ParameterPrior(
        parameter_name=parameter_name,
        variety_id=str(variety_id),
        p50=None,
        p80_lower=None,
        p80_upper=None,
        source_level=monotonic_step,
        confidence=confidence_for_step(monotonic_step),
        sample_count=0,
        season_count=0,
        farm_count=0,
        source_observation_ids=(),
        missing_evidence=missing_evidence,
    )


def _normalize_confidence(value: Any) -> Confidence:
    s = str(value or "").upper()
    if s == "HIGH":
        return "HIGH"
    if s in ("MEDIUM", "MED"):
        return "MEDIUM"
    return "LOW"


def _parameter_bounds(parameter_type: str) -> tuple[Decimal | None, Decimal | None]:
    """Per-upstream-parameter-type numeric floor/ceiling (defensive only)."""

    from backend.app.planning.service import _parameter_bounds as upstream_bounds

    return upstream_bounds(parameter_type)


async def _load_location_reference(
    *, session: AsyncSession, location_reference_id: int | None
) -> Any:
    """Load the persisted :class:`LocationReference` row for the given id.

    Returns ``None`` when no reference is present (the caller
    translates this to LOCATION_SOURCE_CAPABILITY_MISSING).
    """
    if location_reference_id is None:
        raise LocationSourceCapabilityMissingError(
            "resolved location has no location_reference_id (P0-1 #6)"
        )
    try:
        from backend.app.models.planning import LocationReference
    except ImportError as exc:
        raise LocationSourceCapabilityMissingError(
            f"persisted LocationReference ORM not importable: {type(exc).__name__}: {exc}"
        ) from exc
    try:
        return await session.get(LocationReference, int(location_reference_id))
    except Exception as exc:  # noqa: BLE001
        raise UpstreamReadFailureError(
            f"LocationReference read failed: {type(exc).__name__}: {exc}"
        ) from exc


async def _resolve_maturity_curve(
    *,
    session: AsyncSession,
    variety_id: str,
    variety_pk: int,
    resolved_location: ResolvedLocation,
    upstream_resolved_location: Any,
    effective_as_of_date: date,
    rules: Any,
    monotonic_step: int,
    config_version: str,
    config_hash: str,
) -> ParameterPrior:
    """P0-1 #7: 3-component maturity_curve.

    All three components must produce a non-``None`` numeric estimate.
    If any component is missing, the entire ``maturity_curve`` is
    blocked and ``missing_evidence`` lists the missing component
    identifier(s).
    """

    from backend.app.planning.inference import infer_parameter

    component_results: dict[str, Any] = {}
    component_prior_estimates: dict[str, tuple[Decimal | None, int]] = {}
    missing_components: list[str] = []
    all_observation_ids: list[int] = []
    for component_type in ("maturity_peak_offset_days", "maturity_width_days", "maturity_skewness"):
        candidates = await _load_candidates_from_orm(
            session=session,
            variety_id=variety_pk,
            parameter_type=component_type,
            effective_as_of_date=effective_as_of_date,
            resolved_location=resolved_location,
        )
        if not candidates:
            missing_components.append(component_type)
            continue
        floor, ceiling = _parameter_bounds(component_type)
        result = infer_parameter(
            parameter_type=component_type,
            candidates=candidates,
            rules=rules,
            floor=floor,
            ceiling=ceiling,
            resolved_location=upstream_resolved_location,
            as_of_date=effective_as_of_date,
        )
        component_results[component_type] = result
        component_prior_estimates[component_type] = (
            getattr(result, "p50_value", None),
            int(getattr(result, "sample_count", 0) or 0),
        )
        obs_ids = getattr(result, "source_observation_ids", ()) or ()
        all_observation_ids.extend(int(i) for i in obs_ids)
        if getattr(result, "p50_value", None) is None:
            missing_components.append(component_type)

    if missing_components:
        return ParameterPrior(
            parameter_name="maturity_curve",
            variety_id=str(variety_id),
            p50=None,
            p80_lower=None,
            p80_upper=None,
            source_level=monotonic_step,
            confidence=confidence_for_step(monotonic_step),
            sample_count=0,
            season_count=0,
            farm_count=0,
            source_observation_ids=(),
            missing_evidence=tuple(
                f"maturity_curve_component_missing:{c}" for c in missing_components
            ),
        )

    # All three components present — construct a composite
    # ``ParameterPrior`` whose ``p50`` carries the peak offset as the
    # primary scalar (the design's ``maturity_curve`` schema expects a
    # 3-tuple semantic), and the three component decimals are
    # surfaced as dedicated fields.
    peak_result = component_results["maturity_peak_offset_days"]
    return ParameterPrior(
        parameter_name="maturity_curve",
        variety_id=str(variety_id),
        p50=_to_decimal(getattr(peak_result, "p50_value", None)),
        p80_lower=_to_decimal(getattr(peak_result, "p80_lower", None)),
        p80_upper=_to_decimal(getattr(peak_result, "p80_upper", None)),
        source_level=source_level_step(
            getattr(peak_result, "source_level", None), fallback_step=monotonic_step
        ),
        confidence=_normalize_confidence(getattr(peak_result, "confidence_level", None)),
        sample_count=int(getattr(peak_result, "sample_count", 0) or 0),
        season_count=int(getattr(peak_result, "season_count", 0) or 0),
        farm_count=int(getattr(peak_result, "farm_count", 0) or 0),
        source_observation_ids=tuple(all_observation_ids),
        missing_evidence=(),
        maturity_peak_offset_days=_to_decimal(
            component_prior_estimates["maturity_peak_offset_days"][0]
        ),
        maturity_width_days=_to_decimal(component_prior_estimates["maturity_width_days"][0]),
        maturity_skewness=_to_decimal(component_prior_estimates["maturity_skewness"][0]),
    )


def _build_parameter_prior_from_inference_result(
    *,
    result: Any,
    parameter_name: str,
    variety_id: str,
    monotonic_step: int,
) -> ParameterPrior:
    p50_value = getattr(result, "p50_value", None)
    p80_lower = getattr(result, "p80_lower", None)
    p80_upper = getattr(result, "p80_upper", None)
    source_level_value = source_level_step(
        getattr(result, "source_level", None), fallback_step=monotonic_step
    )
    confidence_value = getattr(result, "confidence_level", None) or confidence_for_step(
        monotonic_step
    )

    sample_count = int(getattr(result, "sample_count", 0))
    season_count = int(getattr(result, "season_count", 0))
    farm_count = int(getattr(result, "farm_count", 0))
    obs_ids = tuple(int(i) for i in getattr(result, "source_observation_ids", ()))
    missing = tuple(getattr(result, "missing_evidence", ()))

    return ParameterPrior(
        parameter_name=parameter_name,
        variety_id=str(variety_id),
        p50=_to_decimal(p50_value),
        p80_lower=_to_decimal(p80_lower),
        p80_upper=_to_decimal(p80_upper),
        source_level=source_level_value,
        confidence=_normalize_confidence(confidence_value),
        sample_count=sample_count,
        season_count=season_count,
        farm_count=farm_count,
        source_observation_ids=obs_ids,
        missing_evidence=missing,
    )


async def _load_candidates_from_orm(
    *,
    session: AsyncSession,
    variety_id: int,
    parameter_type: str,
    effective_as_of_date: date,
    resolved_location: ResolvedLocation,
) -> list[Any]:
    """Load and project :class:`ParameterObservation` rows to CandidateObservation.

    Mirrors :func:`backend.app.planning.service._load_candidates` but
    stays agent-local and uses :class:`AsyncSession` directly without
    invoking the upstream private helper.  Returns ``[]`` when the
    table is not part of the agent's session (e.g. SQLite fixture) —
    the caller treats ``[]`` as ``status='unavailable'``.
    """

    try:
        from backend.app.models.master_data import Farm, Season
        from backend.app.models.planning import ParameterObservation
    except ImportError:
        return []

    # Apply visibility predicate using ORM-level filtering.
    visibility_stmt = select(ParameterObservation).where(
        ParameterObservation.variety_id == variety_id,
        ParameterObservation.parameter_type == parameter_type,
        ParameterObservation.valid_from <= effective_as_of_date,
        (ParameterObservation.valid_to.is_(None))
        | (ParameterObservation.valid_to >= effective_as_of_date),
        ParameterObservation.available_at <= effective_as_of_date,
    )
    rows = (await session.scalars(visibility_stmt)).all()
    if not rows:
        return []

    # Build the auxiliary lookups needed by the upstream CandidateObservation.
    farm_lookup: dict[int, str | None] = {
        row.id: row.name
        for row in (await session.scalars(select(Farm).order_by(Farm.id.asc()))).all()
    }
    location_reference_ids = [
        r.location_reference_id for r in rows if r.location_reference_id is not None
    ]
    location_lookup: dict[int, Any] = {}
    if location_reference_ids:
        from backend.app.models.planning import LocationReference

        location_lookup = {
            row.id: row
            for row in (
                await session.scalars(
                    select(LocationReference).where(
                        LocationReference.id.in_(location_reference_ids)
                    )
                )
            ).all()
        }
    season_lookup: dict[int, Any] = {
        row.id: row
        for row in (await session.scalars(select(Season).order_by(Season.id.asc()))).all()
    }

    candidates: list[Any] = []
    for row in rows:
        reference = (
            location_lookup.get(row.location_reference_id)
            if row.location_reference_id is not None
            else None
        )
        farm_name = (
            reference.farm_name
            if reference is not None and reference.farm_name is not None
            else (farm_lookup.get(row.farm_id) if row.farm_id is not None else None)
        )
        candidate_province = (
            reference.province
            if reference is not None and reference.province is not None
            else row.province
        )
        candidate_prefecture = (
            reference.prefecture
            if reference is not None and reference.prefecture is not None
            else row.prefecture
        )
        candidate_county = (
            reference.county
            if reference is not None and reference.county is not None
            else row.county
        )
        candidate_township = (
            reference.township
            if reference is not None and reference.township is not None
            else row.township
        )
        season = season_lookup.get(row.season_id) if row.season_id is not None else None
        from backend.app.planning.schemas import CandidateObservation

        candidates.append(
            CandidateObservation(
                observation_id=int(row.id),
                parameter_type=str(row.parameter_type),
                variety_id=int(row.variety_id),
                scalar_value=Decimal(row.scalar_value),
                sample_weight=Decimal(row.sample_weight),
                source_level=str(row.source_level),
                farm_id=row.farm_id,
                subfarm_id=row.subfarm_id,
                location_reference_id=row.location_reference_id,
                climate_zone_id=row.climate_zone_id,
                province=candidate_province,
                prefecture=candidate_prefecture,
                county=candidate_county,
                township=candidate_township,
                farm_name=farm_name,
                altitude_m=row.altitude_m,
                latitude=(
                    Decimal(str(reference.latitude))
                    if reference is not None and reference.latitude is not None
                    else None
                ),
                longitude=(
                    Decimal(str(reference.longitude))
                    if reference is not None and reference.longitude is not None
                    else None
                ),
                season_id=row.season_id,
                season_code=str(season.code) if season is not None else None,
                season_end_date=season.end_date if season is not None else None,
                historical_mape=row.historical_mape,
                date_mae_days=row.date_mae_days,
                p90_coverage=row.p90_coverage,
                valid_from=row.valid_from,
                valid_to=row.valid_to,
                available_at=row.available_at,
                source_version=row.source_version,
            )
        )
    return candidates


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# --- Top-level adapter ----------------------------------------------------


class DefaultParameterAdapter:
    """Default ``infer_parameters`` adapter wiring the upstream pipeline.

    Walks all 8 logical schemas per (variety, parameter_name).  Each
    (variety, parameter_name) is independently resolved:

    * Variety unknown → :class:`BlockerCode.UNKNOWN_VARIETY`
    * Parameter maps to upstream type, observation visible, inference
      succeeds → :class:`ParameterEstimate`
    * Parameter maps to upstream type but no visible observations →
      :class:`BlockerCode.INSUFFICIENT_HISTORY`
    * Parameter has no persisted upstream source → :class:`BlockerCode.NO_PERSISTED_PRIOR_SOURCE`
    * Location source missing required coordinates →
      :class:`BlockerCode.LOCATION_SOURCE_CAPABILITY_MISSING`
    * Inference config missing / malformed →
      :class:`BlockerCode.INFERENCE_CONFIG_MISSING` /
      :class:`BlockerCode.INFERENCE_CONFIG_HASH_MALFORMED`

    The ``parameters_hash`` is computed over the canonical list of
    :class:`ParameterEstimate` (successful parameters only); the
    ``blocked_parameter_identities`` field records the per-variety set
    of blocked parameter names for downstream observability.
    """

    def __init__(
        self,
        *,
        port: ParameterPriorPort | None = None,
        catalog: VarietyCatalogPort | None = None,
    ) -> None:
        self._port = port or DefaultParameterPriorPort(catalog=catalog)
        self._catalog = catalog or DefaultVarietyCatalogPort()

    async def execute(
        self,
        session: AsyncSession,
        *,
        input: InferParametersInput,
    ) -> InferParametersOutput:
        nr = input.normalized_request
        widened: list[ParameterEstimate] = []
        blocked_variety_ids: list[str] = []
        blockers: list[Blocker] = []
        # Per-variety, per-parameter structured blockers — keyed by
        # (variety_id, parameter_name) for deterministic output.
        blocked_parameter_identities: list[dict[str, Any]] = []

        for variety in nr.varieties:
            # Variety code resolution via the real catalog (P0-1 #4).
            try:
                await self._catalog.is_known(session=session, variety_id=variety.variety_id)
            except UnknownVarietyError:
                blocked_variety_ids.append(variety.variety_id)
                blockers.append(
                    Blocker(
                        code=BlockerCode.UNKNOWN_VARIETY,
                        message=(f"variety_id is not in the variety catalog: {variety.variety_id}"),
                        details={"variety_id": variety.variety_id},
                        retry_hint="FIX_INPUT",
                    )
                )
                continue
            except VarietyCatalogReadFailure as exc:
                blockers.append(
                    Blocker(
                        code=BlockerCode.UPSTREAM_READ_FAILURE,
                        message=str(exc),
                        details={"variety_id": variety.variety_id},
                        retry_hint="WAIT_FOR_DATA",
                    )
                )
                continue

            # Walk all 8 logical parameters; each (variety, parameter_name)
            # pair is independently resolved.
            for parameter_name in ALL_LOGICAL_PARAMETERS:
                blocker, prior = await _resolve_one_parameter(
                    port=self._port,
                    session=session,
                    variety_id=variety.variety_id,
                    parameter_name=parameter_name,
                    resolved_location=input.resolved_location,
                    effective_as_of_date=nr.effective_as_of_date,
                    uncertainty_widening_policy=input.uncertainty_widening_policy,
                )
                if blocker is not None:
                    blockers.append(blocker)
                    blocked_parameter_identities.append(
                        {
                            "variety_id": variety.variety_id,
                            "parameter_name": parameter_name,
                            "blocker_code": blocker.code.value,
                        }
                    )
                    continue
                assert prior is not None
                # P0-3 round 6: the frozen public ``ParameterEstimate``
                # schema only carries p50 / p80_lower / p80_upper
                # scalars; it cannot express the 3-component
                # ``maturity_curve`` (peak_offset / width / skewness).
                # The internal prior HAS the 3 components (see
                # ``_resolve_maturity_curve``), but emitting a
                # ``maturity_curve`` ParameterEstimate whose ``p50``
                # holds only the peak-offset scalar would falsely claim
                # the logical parameter is complete.  Round 6 design
                # contract: exclude ``maturity_curve`` from the public
                # output and surface
                # ``MATURITY_CURVE_OUTPUT_SCHEMA_CAPABILITY_MISSING``.
                if prior.parameter_name == "maturity_curve":
                    blockers.append(
                        Blocker(
                            code=BlockerCode.MATURITY_CURVE_OUTPUT_SCHEMA_CAPABILITY_MISSING,
                            message=(
                                "logical parameter 'maturity_curve' has all "
                                "three components inferred (peak_offset / "
                                "width / skewness) but the frozen public "
                                "ParameterEstimate schema cannot carry a "
                                "composite 3-component value.  Slice A "
                                "output contract is unable to expose the "
                                "complete maturity_curve estimate.  Awaiting "
                                "design amendment to add a composite "
                                "ParameterEstimate variant."
                            ),
                            details={
                                "variety_id": variety.variety_id,
                                "parameter_name": prior.parameter_name,
                                "inferred_components": [
                                    "maturity_peak_offset_days",
                                    "maturity_width_days",
                                    "maturity_skewness",
                                ],
                                "blocked_via": "schema_capability_gap",
                            },
                            retry_hint="WAIT_FOR_DATA",
                        )
                    )
                    blocked_parameter_identities.append(
                        {
                            "variety_id": variety.variety_id,
                            "parameter_name": prior.parameter_name,
                            "blocker_code": (
                                BlockerCode.MATURITY_CURVE_OUTPUT_SCHEMA_CAPABILITY_MISSING.value
                            ),
                        }
                    )
                    continue
                widened.append(
                    ParameterEstimate(
                        parameter_name=prior.parameter_name,
                        variety_id=prior.variety_id,
                        p50=_decimal_to_string(prior.p50),
                        p80_lower=(
                            _decimal_to_string(prior.p80_lower)
                            if prior.p80_lower is not None
                            else None
                        ),
                        p80_upper=(
                            _decimal_to_string(prior.p80_upper)
                            if prior.p80_upper is not None
                            else None
                        ),
                        source_level=prior.source_level,
                        confidence=prior.confidence,
                        confidence_score=None,
                        sample_count=prior.sample_count,
                        season_count=prior.season_count,
                        farm_count=prior.farm_count,
                        source_observation_ids=list(prior.source_observation_ids),
                        fallback_below_minimum=False,
                        missing_evidence=list(prior.missing_evidence),
                        citation=_build_citation(
                            prior=prior,
                            effective_as_of_date=nr.effective_as_of_date,
                        ),
                    )
                )

        # parameters_hash is sensitive to the EXACT set of successful
        # parameters AND to the blocked identities so that two requests
        # with identical successful parameters but different blocked
        # categories produce different hashes.
        hash_payload = {
            "successful_parameters": [p.model_dump(mode="python") for p in widened],
            "blocked_parameter_identities": sorted(
                blocked_parameter_identities, key=lambda x: (x["variety_id"], x["parameter_name"])
            ),
        }
        parameters_hash = _parameters_hash_fn(hash_payload)
        return InferParametersOutput(
            parameters=widened,
            uncertainty_widening_policy_version=input.uncertainty_widening_policy.policy_version,
            uncertainty_widening_policy_config_hash=input.uncertainty_widening_policy.config_hash,
            parameters_hash=parameters_hash,
            blocked_variety_ids=blocked_variety_ids,
            blockers=blockers,
        )


async def _resolve_one_parameter(
    *,
    port: ParameterPriorPort,
    session: AsyncSession,
    variety_id: str,
    parameter_name: str,
    resolved_location: ResolvedLocation,
    effective_as_of_date: date,
    uncertainty_widening_policy: UncertaintyWideningPolicy,
) -> tuple[Blocker | None, ParameterPrior | None]:
    """Resolve a single ``(variety, parameter)`` pair.

    Walks the priority steps 1..5 and picks the highest step for which
    the prior port returns a successful prior (p50 not None).  When the
    port raises one of the typed :class:`SourceCapabilityGapError`
    subclasses, the blocker is the matching typed
    :class:`BlockerCode` (round 6 P0-2: no coarse
    ``NO_PERSISTED_PRIOR_SOURCE`` re-mapping).
    """

    details_base = {
        "variety_id": variety_id,
        "parameter_name": parameter_name,
        "effective_as_of_date": effective_as_of_date.isoformat(),
    }

    for step in (1, 2, 3, 4, 5):
        try:
            prior = await port.resolve_parameter(
                session=session,
                variety_id=variety_id,
                parameter_name=parameter_name,
                resolved_location=resolved_location,
                effective_as_of_date=effective_as_of_date,
                widening_factor=widening_factor_for(step, uncertainty_widening_policy),
                monotonic_step=step,
            )
        except UnknownVarietyCapabilityError as exc:
            return (
                Blocker(
                    code=BlockerCode.UNKNOWN_VARIETY,
                    message=str(exc),
                    details=dict(details_base),
                    retry_hint="FIX_INPUT",
                ),
                None,
            )
        except InferenceConfigMissingError as exc:
            return (
                Blocker(
                    code=BlockerCode.INFERENCE_CONFIG_MISSING,
                    message=str(exc),
                    details=dict(details_base),
                    retry_hint="CONTACT_OPS",
                ),
                None,
            )
        except InferenceConfigHashMalformedError as exc:
            return (
                Blocker(
                    code=BlockerCode.INFERENCE_CONFIG_HASH_MALFORMED,
                    message=str(exc),
                    details=dict(details_base),
                    retry_hint="CONTACT_OPS",
                ),
                None,
            )
        except LocationSourceCapabilityMissingError as exc:
            return (
                Blocker(
                    code=BlockerCode.LOCATION_SOURCE_CAPABILITY_MISSING,
                    message=str(exc),
                    details=dict(details_base),
                    retry_hint="PROVIDE_OVERRIDE",
                ),
                None,
            )
        except UpstreamReadFailureError as exc:
            return (
                Blocker(
                    code=BlockerCode.UPSTREAM_READ_FAILURE,
                    message=str(exc),
                    details=dict(details_base),
                    retry_hint="WAIT_FOR_DATA",
                ),
                None,
            )
        except InsufficientHistoryError as exc:
            return (
                Blocker(
                    code=BlockerCode.INSUFFICIENT_HISTORY,
                    message=str(exc),
                    details=dict(details_base),
                    retry_hint="WAIT_FOR_DATA",
                ),
                None,
            )
        except SourceCapabilityGapError as exc:
            # Truly unsupported parameter category (no persisted
            # upstream source) — slice-A scope gap.
            return (
                Blocker(
                    code=BlockerCode.NO_PERSISTED_PRIOR_SOURCE,
                    message=str(exc),
                    details=dict(details_base),
                    retry_hint="WAIT_FOR_DATA",
                ),
                None,
            )
        if prior is None or prior.p50 is None:
            # Per-step priority walk continues only when the prior has a
            # numerical estimate.  When NO step yields a numeric prior,
            # surface INSUFFICIENT_HISTORY for this (variety, parameter).
            continue
        return None, prior

    return (
        Blocker(
            code=BlockerCode.INSUFFICIENT_HISTORY,
            message=(
                f"No visible prior at any priority step for "
                f"variety {variety_id} parameter {parameter_name} at "
                f"{effective_as_of_date.isoformat()}."
            ),
            details={
                "variety_id": variety_id,
                "parameter_name": parameter_name,
            },
            retry_hint="WAIT_FOR_DATA",
        ),
        None,
    )


def _decimal_to_string(value: Decimal | None) -> str:
    if value is None:
        raise ValueError("non-null Decimal required")
    return format(value, "f")


def _build_citation(*, prior: ParameterPrior, effective_as_of_date: date) -> Citation:
    return Citation(
        source_tasks=["TASK_008"],
        source_tool="INFER_PARAMETERS",
        authorities=[],
        agent_artifact_hash=None,
        field_path=f"parameters[{prior.variety_id}].{prior.parameter_name}",
        effective_as_of_date=effective_as_of_date,
        confidence_evidence={
            "sample_count": prior.sample_count,
            "season_count": prior.season_count,
            "farm_count": prior.farm_count,
        },
        tags=[],
        override_refs=[],
    )


__all__ = [
    "SourceCapabilityGapError",
    "InferenceConfigMissingError",
    "InferenceConfigHashMalformedError",
    "LocationSourceCapabilityMissingError",
    "UnknownVarietyCapabilityError",
    "InsufficientHistoryError",
    "UpstreamReadFailureError",
    "UnknownVarietyError",
    "VarietyCatalogReadFailure",
    "is_visible_prior",
    "widening_factor_for",
    "confidence_for_step",
    "ParameterPrior",
    "DefaultParameterPriorPort",
    "DefaultVarietyCatalogPort",
    "DefaultParameterAdapter",
    "ALL_LOGICAL_PARAMETERS",
    "LOGICAL_TO_UPSTREAM",
]
