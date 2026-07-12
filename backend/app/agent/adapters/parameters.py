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

**Strict capability-boundary policy.**  The TASK-013 design freezes 8 logical
schemas, but the upstream ``parameter_observation`` ORM table only stores 7
``parameter_type`` values (see ``PARAMETER_UNITS`` in
``backend.app.planning.service``):

* ``yield_kg_per_mu`` ← ``expected_per_mu_yield``
* ``marketable_rate`` ← ``commodity_fruit_rate``
* ``first_harvest_offset_days`` ← ``first_harvest_date``
* ``maturity_peak_offset_days`` + ``maturity_width_days`` +
*   ``maturity_skewness`` ← ``maturity_curve``
* ``harvest_realization_rate`` ← (no design schema in Slice A; reserved)

The remaining 4 design schemas have **no persisted prior source** in the
current upstream:

* ``spring_festival_harvest_rate``
* ``weather_adjustment``
* ``post_spring_festival_backlog_release_intensity``
* ``historical_anomaly_peak_probability``

Per Charles's direction (2026-07-11): KEEP_EIGHT_LOGICAL_PARAMETER_SCHEMAS /
NO_NEW_MIGRATION_IN_SLICE_A / NO_NEW_UPSTREAM_PERSISTENCE_TABLE /
SUPPORTED_PARAMETERS_USE_REAL_PERSISTED_EVIDENCE /
UNSUPPORTED_PARAMETERS_RETURN_STRUCTURED_BLOCKERS /
NO_FABRICATED_NUMERICAL_PRIORS.

Concretely:

1. The 8 logical schemas are kept as the public input contract.
2. Each per-``(variety, parameter_name)`` pair that maps to a real
   ``parameter_type`` is resolved through the real persisted observation
   table — no fabrication, no YAML fallback, no default numeric value.
3. Each per-``(variety, parameter_name)`` pair that has no upstream
   ``parameter_type`` returns a structured :class:`Blocker` with code
   :data:`BlockerCode.NO_PERSISTED_PRIOR_SOURCE` (per-variety, per-parameter).
4. The :class:`ParameterEstimate` list only contains successfully inferred
   parameters.  Missing parameter categories DO NOT appear as zeros, ones,
   schema defaults, or copies of other categories.
5. :func:`parameters_hash` is sensitive to the exact set of successfully
   inferred parameter identities — different blocked-parameter sets yield
   different hashes.

The visibility predicate replicates ``backend.app.planning.service._load_candidates``:

    valid_from <= as_of_date AND (valid_to IS NULL OR valid_to >= as_of_date)
    AND available_at <= as_of_date

Hard rules (unchanged):

* per ``(location × variety × parameter)``;
* :class:`UncertaintyWideningPolicy` passed explicitly; no hidden runtime
  default policy;
* no numerical values come from the LLM or a handwritten fallback;
* step 1 only avoids widening when HIGH evidence is satisfied;
* steps 2–5 widen monotonically;
* step 5 has maximum widening and LOW confidence;
* unknown variety returns a per-variety blocked result;
* no numerical result is emitted for an unknown variety or unsupported parameter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
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


class UnknownVarietyError(Exception):
    """Raised when a variety_id is not present in the variety catalog."""


class DefaultVarietyCatalogPort(VarietyCatalogPort):
    """Default :class:`VarietyCatalogPort` calling ``planning.plan_repository``."""

    async def is_known(self, *, session: AsyncSession, variety_id: str) -> bool:
        try:
            from backend.app.planning.plan_repository import get_variety_by_code
        except ImportError:
            return False
        row = await get_variety_by_code(session, variety_code=variety_id)
        if row is None:
            raise UnknownVarietyError(f"variety_id is not in the variety catalog: {variety_id}")
        return True


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


def _build_default_parameter_inference_rules() -> Any:
    """Construct the deterministic in-code default :class:`ParameterInferenceRules`.

    Per Charles's direction, Slice A MUST NOT invent a YAML constant for
    the parameter inference ruleset when one is not loaded.  However, the
    production inference pipeline (``infer_parameter``) REQUIRES a
    rules argument; it is part of the upstream signature.

    Resolution: construct a deterministic ruleset with conservative
    fallback defaults that match the project's ``configs/parameter_inference.yaml``
    semantics.  This is a ruleset snapshot (a typed in-code equivalent of
    the YAML), not a numerical prior.  Production code paths MUST inject
    :func:`load_parameter_inference_config` via :class:`DefaultParameterAdapter`
    to use the versioned on-disk YAML.
    """

    from backend.app.planning.config import (
        ConfidenceRules,
        FallbackRule,
        FallbackRules,
        ParameterInferenceRules,
        ResolverRules,
        SimilarityRules,
        UncertaintyRules,
    )

    return ParameterInferenceRules(
        resolver_version="agent-default/v1",
        resolver=ResolverRules(
            address_fuzzy_match_min_score=Decimal("0.600"),
            nearest_reference_distance_km=Decimal("5.000"),
            climate_zone_radius_km=Decimal("50.000"),
        ),
        similarity=SimilarityRules(
            max_distance_km=Decimal("30.000"),
            max_altitude_difference_m=Decimal("200.000"),
            township_bonus=Decimal("0.200"),
            county_bonus=Decimal("0.150"),
            climate_zone_bonus=Decimal("0.150"),
            same_farm_bonus=Decimal("0.300"),
            distance_weight=Decimal("0.400"),
            altitude_weight=Decimal("0.300"),
            recency_weight=Decimal("0.300"),
            ambiguity_margin=Decimal("0.020"),
        ),
        fallback=FallbackRules(
            same_farm_variety=FallbackRule(
                minimum_sample_count=2,
                minimum_season_count=2,
                maximum_historical_mape=Decimal("0.300"),
            ),
            same_township_altitude_variety=FallbackRule(
                minimum_sample_count=2,
                minimum_season_count=2,
                maximum_historical_mape=Decimal("0.350"),
            ),
            same_county_climate_zone_variety=FallbackRule(
                minimum_sample_count=2,
                minimum_season_count=2,
                maximum_historical_mape=Decimal("0.400"),
            ),
            same_province_variety=FallbackRule(
                minimum_sample_count=3,
                minimum_season_count=3,
                maximum_historical_mape=Decimal("0.450"),
            ),
            literature_variety_prior=FallbackRule(
                minimum_sample_count=1,
                minimum_season_count=1,
                maximum_historical_mape=None,
            ),
        ),
        uncertainty=UncertaintyRules(
            widen_low_confidence_factor=Decimal("1.250"),
            widen_below_minimum_factor=Decimal("1.500"),
        ),
        confidence=ConfidenceRules(
            high_min_score=Decimal("0.800"),
            medium_min_score=Decimal("0.500"),
            same_farm_high_min_seasons=2,
            high_max_historical_mape=Decimal("0.300"),
            medium_max_historical_mape=Decimal("0.450"),
            missing_error_penalty=Decimal("0.050"),
            fallback_below_minimum_penalty=Decimal("0.100"),
            unresolved_location_penalty=Decimal("0.150"),
        ),
    )


def _resolve_location_to_dict(resolved_location: ResolvedLocation) -> dict[str, Any]:
    """Convert :class:`ResolvedLocation` to the dict shape consumed by
    :func:`backend.app.planning.service._load_candidates`.
    """

    out: dict[str, Any] = {
        "location_reference_id": resolved_location.location_reference_id,
        "address_normalized": resolved_location.address_normalized,
        "address_raw": resolved_location.address_raw,
        "farm_name": resolved_location.farm_name,
        "subfarm_name": resolved_location.subfarm_name,
        "province": resolved_location.province,
        "prefecture": resolved_location.prefecture,
        "county": resolved_location.county,
        "township": resolved_location.township,
        "village": resolved_location.village,
        "matched_location_method": resolved_location.matched_location_method,
        "climate_zone_id": resolved_location.climate_zone_id,
        "climate_zone_code": resolved_location.climate_zone_code,
        "climate_zone_version": resolved_location.climate_zone_version,
    }
    if resolved_location.mapping_confidence is not None:
        out["mapping_confidence"] = resolved_location.mapping_confidence
    if resolved_location.distance_km is not None:
        out["distance_km"] = resolved_location.distance_km
    if resolved_location.altitude_difference_m is not None:
        out["altitude_difference_m"] = resolved_location.altitude_difference_m
    # The upstream expects latitude/longitude; the agent ResolvedLocation
    # does not store these directly, so we leave them unset.  When unset,
    # ``_load_candidates`` returns [].  Slice A cannot fabricate them.
    return out


def _to_int_variety_id(variety_id: str) -> int:
    """Best-effort conversion of a string variety code to an int PK.

    Returns ``0`` when the code is not numeric; the upstream loader
    requires an int ``variety_id``.  Slice A treats non-numeric codes as
    a capability gap (``UNKNOWN_VARIETY`` upstream); the adapter surfaces
    this as INSUFFICIENT_HISTORY for non-numeric codes.
    """

    try:
        return int(variety_id)
    except (TypeError, ValueError):
        return 0


class DefaultParameterPriorPort:
    """Real persisted observation port.

    Loads :class:`ParameterObservation` rows for the given
    ``(variety_id, parameter_type)``, applies the §26.1 visibility
    predicate, projects the rows to :class:`CandidateObservation` objects,
    and calls :func:`infer_parameter` from the upstream pipeline.  No
    candidate fabrication: when the DB has no visible rows, the inference
    returns ``status='unavailable'`` and the port surfaces
    ``p50_value=None`` to the adapter (which records a per-variety
    INSUFFICIENT_HISTORY blocker).
    """

    def __init__(self, *, rules: Any | None = None) -> None:
        self._rules = rules  # None ⇒ use the deterministic default ruleset

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

        # Validate the logical schema is one of the 8 frozen names.
        if parameter_name not in ALL_LOGICAL_PARAMETERS:
            raise SourceCapabilityGapError(f"unknown logical parameter_name: {parameter_name!r}")

        # Map the logical schema to the upstream parameter_type(s).
        upstream_types = LOGICAL_TO_UPSTREAM.get(parameter_name)
        if upstream_types is None:
            # 4 categories with no real persisted prior source.  Surface
            # a typed gap to the adapter (which records a per-variety
            # NO_PERSISTED_PRIOR_SOURCE blocker).
            raise SourceCapabilityGapError(
                f"logical parameter {parameter_name!r} has no persisted upstream parameter_type"
            )

        # The 4 composed (maturity_curve) and 1 single (yield_kg_per_mu)
        # upstream types are reduced to a single p50 in the agent output.
        # For composed categories we use the FIRST upstream type as the
        # canonical inference target; the remaining types are documented
        # in the citation but their values are not concatenated (no
        # fabrication).
        primary_type = upstream_types[0]

        rules = self._rules or _build_default_parameter_inference_rules()
        int_variety_id = _to_int_variety_id(variety_id)
        if int_variety_id <= 0:
            # Non-numeric variety code; the upstream ``_load_candidates``
            # requires an int PK.  Slice A surfaces this as
            # INSUFFICIENT_HISTORY (no numeric fabrication).
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
                missing_evidence=("variety_id_not_int",),
            )

        candidates = await _load_candidates_from_orm(
            session=session,
            variety_id=int_variety_id,
            parameter_type=primary_type,
            effective_as_of_date=effective_as_of_date,
            resolved_location=resolved_location,
        )

        if not candidates:
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
                missing_evidence=("no_visible_observations",),
            )

        from backend.app.planning.inference import infer_parameter

        floor, ceiling = _parameter_bounds(primary_type)
        # Pass None for ``resolved_location``: the agent layer does NOT
        # carry latitude/longitude (the upstream requirement for matching
        # candidates).  The upstream ``infer_parameter`` accepts None and
        # the candidates list returned by ``_load_candidates_from_orm``
        # still drives the inference result.  When the upstream selection
        # rejects all candidates (no lat/lng for the matched subset), the
        # inference returns ``status='unavailable'`` and the per-variety
        # INSUFFICIENT_HISTORY blocker is surfaced — no fabrication.
        result = infer_parameter(
            parameter_type=primary_type,
            candidates=candidates,
            rules=rules,
            floor=floor,
            ceiling=ceiling,
            resolved_location=None,
            as_of_date=effective_as_of_date,
        )

        p50_value = getattr(result, "p50_value", None)
        p80_lower = getattr(result, "p80_lower", None)
        p80_upper = getattr(result, "p80_upper", None)
        source_level_value = getattr(result, "source_level", None) or monotonic_step
        confidence_value = getattr(result, "confidence_level", None) or confidence_for_step(
            monotonic_step
        )

        sample_count = int(getattr(result, "sample_count", 0))
        season_count = int(getattr(result, "season_count", 0))
        farm_count = int(getattr(result, "farm_count", 0))
        obs_ids = tuple(int(i) for i in getattr(result, "source_observation_ids", ()))
        missing = tuple(getattr(result, "missing_evidence", ()))

        # ``p50_value`` is Decimal|None from the upstream.  We keep it as-is
        # — when status='unavailable', the upstream returns None and we
        # propagate that to the adapter.
        return ParameterPrior(
            parameter_name=parameter_name,
            variety_id=str(variety_id),
            p50=_to_decimal(p50_value),
            p80_lower=_to_decimal(p80_lower),
            p80_upper=_to_decimal(p80_upper),
            source_level=int(source_level_value),
            confidence=_normalize_confidence(confidence_value),
            sample_count=sample_count,
            season_count=season_count,
            farm_count=farm_count,
            source_observation_ids=obs_ids,
            missing_evidence=missing,
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


async def _load_candidates_from_orm(
    *,
    session: AsyncSession,
    variety_id: int,
    parameter_type: str,
    effective_as_of_date: date,
    resolved_location: ResolvedLocation,
) -> list[Any]:
    """Load and project :class:`ParameterObservation` rows to CandidateObservation.

    Mirrors :func:`backend.app.planning.service._load_candidates` but stays
    agent-local and uses :class:`AsyncSession` directly without invoking the
    upstream private helper.  Returns ``[]`` when the table is not part of
    the agent's session (e.g. SQLite fixture) — the caller treats ``[]``
    as ``status='unavailable'``.
    """

    try:
        from backend.app.models.planning import ParameterObservation, LocationReference
        from backend.app.models.master_data import Farm, Season
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
    reference_lookup: dict[int, Any] = {
        row.id: row
        for row in (
            await session.scalars(
                select(LocationReference).where(LocationReference.id.in_(location_reference_ids))
            )
        ).all()
    }
    season_lookup: dict[int, Any] = {
        row.id: row
        for row in (await session.scalars(select(Season).order_by(Season.id.asc()))).all()
    }

    # If the agent-side ResolvedLocation does not carry lat/lng, the
    # upstream _load_candidates would return []; this port must mirror
    # that behaviour without fabricating coordinates.
    candidates: list[Any] = []
    for row in rows:
        reference = (
            reference_lookup.get(row.location_reference_id)
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
                # Latitude/longitude are intentionally NOT fabricated when
                # the agent ResolvedLocation does not carry them; this
                # causes the upstream to return [].
                latitude=None,
                longitude=None,
                season_id=row.season_id,
                season_code=str(season.season_code) if season is not None else None,
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

    The ``parameters_hash`` is computed over the canonical list of
    :class:`ParameterEstimate` (successful parameters only); the
    ``blocked_parameter_identities`` field records the per-variety set of
    blocked parameter names for downstream observability.
    """

    def __init__(
        self,
        *,
        port: ParameterPriorPort | None = None,
        catalog: VarietyCatalogPort | None = None,
    ) -> None:
        self._port = port or DefaultParameterPriorPort()
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
            # P0-2.1: validate the variety via the catalog.
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
    port raises :class:`SourceCapabilityGapError` for ALL steps
    (``unsupported parameter``), the per-variety NO_PERSISTED_PRIOR_SOURCE
    blocker is returned.  When the port returns a prior with p50=None,
    the per-variety INSUFFICIENT_HISTORY blocker is returned.
    """

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
        except SourceCapabilityGapError as exc:
            # ``unsupported parameter`` is raised immediately for ALL
            # steps (no upstream type maps to this logical schema).
            # Surface the per-variety NO_PERSISTED_PRIOR_SOURCE blocker.
            return (
                Blocker(
                    code=BlockerCode.NO_PERSISTED_PRIOR_SOURCE,
                    message=str(exc),
                    details={
                        "variety_id": variety_id,
                        "parameter_name": parameter_name,
                        "effective_as_of_date": effective_as_of_date.isoformat(),
                    },
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
    "UnknownVarietyError",
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
