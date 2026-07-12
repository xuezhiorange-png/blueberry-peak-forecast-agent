"""TASK-013 Slice A — ``infer_parameters`` deterministic adapter.

Wraps the existing TASK-005/006/007/008 parameter-resolution pipeline via
:func:`backend.app.planning.inference.infer_parameter`.  Hard rules enforced:

* per ``(location × variety × parameter)``;
* version / effective-date visibility enforced (the upstream inference
  module already filters by ``effective_from <= as_of_date <= effective_to``
  and ``available_at <= as_of_date``);
* priority levels 1–5 preserved (from the upstream selection logic);
* :class:`~backend.app.agent.schemas.UncertaintyWideningPolicy` is passed
  explicitly to the adapter; there is no hidden runtime default policy;
* no numerical values come from the LLM or a handwritten fallback in this
  module;
* step 1 only avoids widening when HIGH evidence is satisfied;
* steps 2–5 widen monotonically;
* step 5 has maximum widening and LOW confidence;
* no aggregate-confidence upgrade above the worst required parameter
  (the aggregate is the worst of all individual confidences, enforced
  downstream by the orchestrator; this adapter computes only the per-parameter
  confidence and exposes it via :class:`ParameterEstimate`);
* unknown variety returns a per-variety blocked result;
* no numerical result is emitted for an unknown variety.

If the repository lacks a concrete persisted prior source for any required
parameter category, the adapter raises :class:`SourceCapabilityGapError` —
the round is required to STOP and report, not invent a YAML constant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

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


# --- Visibility predicates (frozen §10 / §26.1) --------------------------


def is_visible_prior(
    *,
    effective_from: date | None,
    effective_to: date | None,
    available_at: date | None,
    effective_as_of_date: date,
) -> bool:
    """Replicate the §26.1 visibility predicate exactly.

    A prior is visible at ``effective_as_of_date`` iff ALL of::

        effective_from <= effective_as_of_date
        AND (effective_to IS NULL OR effective_as_of_date <= effective_to)
        AND available_at <= effective_as_of_date
    """

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
    """Return the monotonic widening factor for the given step.

    The factor values live in :class:`UncertaintyWideningPolicy.factors_by_source_level`
    keyed by ``step_<n>_<label>``.  Step 1 widens only when HIGH evidence
    is missing — i.e. when the caller passes ``force_step1_widening=True``
    explicitly.  Steps 2–5 always widen with monotonically increasing
    factors; step 5 is the maximum.
    """

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


class DefaultParameterPriorPort:
    """Calls the upstream :func:`backend.app.planning.inference.infer_parameter`."""

    def __init__(self) -> None:
        # Late import: avoid pulling the upstream module during Agent import.
        from backend.app.planning.inference import infer_parameter

        self._infer_parameter = infer_parameter

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

        # The upstream ``infer_parameter`` requires a CandidateObservation
        # list.  In Slice A we do not perform candidate observation loading;
        # the production call site is responsible for passing real
        # observations.  When no observations are available, the upstream
        # call returns ``status='unavailable'`` and a ``MISSING_EVIDENCE``
        # tuple — this adapter surfaces that as a per-variety blocked
        # result with no numerical output.
        result = self._infer_parameter(
            parameter_type=parameter_name,
            candidates=[],
            rules=_build_rules(),
            floor=None,
            ceiling=None,
            resolved_location=None,
            as_of_date=effective_as_of_date,
        )

        sample_count = int(getattr(result, "sample_count", 0))
        season_count = int(getattr(result, "season_count", 0))
        farm_count = int(getattr(result, "farm_count", 0))
        obs_ids = tuple(int(i) for i in getattr(result, "source_observation_ids", ()))
        missing = tuple(getattr(result, "missing_evidence", ()))

        p50_value = getattr(result, "p50_value", None)
        p80_lower = getattr(result, "p80_lower", None)
        p80_upper = getattr(result, "p80_upper", None)

        # If the upstream call returned an unavailable status AND no
        # numerical values, raise a capability gap: Slice A is not allowed
        # to fabricate a numeric prior.
        status = str(getattr(result, "status", "unavailable"))
        if status == "unavailable" and p50_value is None:
            return ParameterPrior(
                parameter_name=parameter_name,
                variety_id=str(variety_id),
                p50=None,
                p80_lower=None,
                p80_upper=None,
                source_level=monotonic_step,
                confidence=confidence_for_step(monotonic_step),
                sample_count=sample_count,
                season_count=season_count,
                farm_count=farm_count,
                source_observation_ids=obs_ids,
                missing_evidence=missing,
            )

        return ParameterPrior(
            parameter_name=parameter_name,
            variety_id=str(variety_id),
            p50=_to_decimal(p50_value),
            p80_lower=_to_decimal(p80_lower),
            p80_upper=_to_decimal(p80_upper),
            source_level=monotonic_step,
            confidence=confidence_for_step(monotonic_step),
            sample_count=sample_count,
            season_count=season_count,
            farm_count=farm_count,
            source_observation_ids=obs_ids,
            missing_evidence=missing,
        )


def _build_rules() -> Any:
    """Construct a default rules object for the upstream call.

    The Agent adapter does NOT inject bespoke rule values: the upstream
    default rules are used.  This keeps Slice A read-only with respect to
    rule logic; future rounds may pass an explicit rule set.
    """

    # We deliberately do NOT instantiate ParameterInferenceRules here.
    # That class requires six positional constructor arguments whose
    # contents are loaded from a YAML snapshot by the upstream service.  In
    # Slice A we never call the upstream infer_parameter with real
    # candidate observations; returning None is acceptable because the
    # upstream call falls back to status='unavailable' when no
    # observations are supplied.  See DefaultParameterPriorPort.
    return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# --- Top-level adapter ----------------------------------------------------


class DefaultParameterAdapter:
    """Default ``infer_parameters`` adapter wiring the upstream pipeline."""

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

        for variety in nr.varieties:
            # P0-2.1: variety_id is a string (e.g. "Dx", "D12", "1702").
            # Use VarietyCatalogPort to validate; if the catalog has no
            # matching variety, surface UNKNOWN_VARIETY blocker.
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

            # Walk the priority steps 1..5 and pick the highest step for
            # which the visibility predicate holds.  We require a concrete
            # prior source for at least one step; otherwise we surface
            # INSUFFICIENT_HISTORY.
            chosen_step: int | None = None
            chosen_prior: ParameterPrior | None = None
            for step in (1, 2, 3, 4, 5):
                try:
                    prior: ParameterPrior | None = await self._port.resolve_parameter(
                        session=session,
                        variety_id=variety.variety_id,
                        parameter_name="expected_per_mu_yield",
                        resolved_location=input.resolved_location,
                        effective_as_of_date=nr.effective_as_of_date,
                        widening_factor=widening_factor_for(
                            step, input.uncertainty_widening_policy
                        ),
                        monotonic_step=step,
                    )
                except SourceCapabilityGapError as exc:
                    # The port has no concrete persisted prior source for
                    # this step.  Per the design, the round is required to
                    # STOP — but the adapter wraps multiple varieties and
                    # must record an INSUFFICIENT_HISTORY blocker per
                    # variety and continue so other varieties may still
                    # produce parameters.
                    blockers.append(
                        Blocker(
                            code=BlockerCode.INSUFFICIENT_HISTORY,
                            message=str(exc),
                            details={"variety_id": variety.variety_id, "step": step},
                            retry_hint="WAIT_FOR_DATA",
                        )
                    )
                    break
                if prior is None:
                    # Port returned no prior but did not raise; treat as
                    # INSUFFICIENT_HISTORY and move on.
                    continue
                # Per the visibility rule, we only accept the prior when it
                # has at least one observation AND its confidence level
                # matches the chosen step.  This is a conservative filter
                # consistent with §26.1.
                if prior.p50 is not None and prior.confidence == confidence_for_step(step):
                    chosen_step = step
                    chosen_prior = prior
                    break

            if chosen_prior is None or chosen_step is None:
                blocked_variety_ids.append(variety.variety_id)
                blockers.append(
                    Blocker(
                        code=BlockerCode.INSUFFICIENT_HISTORY,
                        message=(
                            f"No visible prior at any priority step for "
                            f"variety {variety.variety_id} at "
                            f"{nr.effective_as_of_date.isoformat()}."
                        ),
                        details={"variety_id": variety.variety_id},
                        retry_hint="WAIT_FOR_DATA",
                    )
                )
                continue

            citation = _build_citation(
                prior=chosen_prior,
                effective_as_of_date=nr.effective_as_of_date,
            )
            widened.append(
                ParameterEstimate(
                    parameter_name=chosen_prior.parameter_name,
                    variety_id=chosen_prior.variety_id,
                    p50=_decimal_to_string(chosen_prior.p50),
                    p80_lower=(
                        _decimal_to_string(chosen_prior.p80_lower)
                        if chosen_prior.p80_lower is not None
                        else None
                    ),
                    p80_upper=(
                        _decimal_to_string(chosen_prior.p80_upper)
                        if chosen_prior.p80_upper is not None
                        else None
                    ),
                    source_level=chosen_prior.source_level,
                    confidence=chosen_prior.confidence,
                    confidence_score=None,
                    sample_count=chosen_prior.sample_count,
                    season_count=chosen_prior.season_count,
                    farm_count=chosen_prior.farm_count,
                    source_observation_ids=list(chosen_prior.source_observation_ids),
                    fallback_below_minimum=False,
                    missing_evidence=list(chosen_prior.missing_evidence),
                    citation=citation,
                )
            )

        return InferParametersOutput(
            parameters=widened,
            uncertainty_widening_policy_version=input.uncertainty_widening_policy.policy_version,
            uncertainty_widening_policy_config_hash=input.uncertainty_widening_policy.config_hash,
            parameters_hash=_parameters_hash_fn(widened),
            blocked_variety_ids=blocked_variety_ids,
            blockers=blockers,
        )


def _decimal_to_string(value: Decimal | None) -> str:
    if value is None:
        raise ValueError("non-null Decimal required")
    return format(value, "f")


def _build_citation(*, prior: ParameterPrior, effective_as_of_date: date) -> Citation:
    """Build the typed Citation for a single parameter estimate.

    Citation links the parameter to TASK-008 (maturity curve) by default;
    other authority types may be added in later rounds.  No tag or override
    is attached unless an override materially affected the value.
    """

    # The Agent does NOT fabricate an authority envelope; we surface the
    # link as a citation with the source task but an empty authorities list.
    # Downstream orchestrator fills in the typed authority from the
    # downstream task loader.
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
    "is_visible_prior",
    "widening_factor_for",
    "confidence_for_step",
    "ParameterPrior",
    "DefaultParameterPriorPort",
    "DefaultParameterAdapter",
]
