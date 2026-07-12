"""TASK-013 Slice A — ``resolve_location`` deterministic adapter.

The adapter wraps the existing ``backend.app.planning.location.resolve_location_input``
function.  It enforces the §13 hard rules:

* read-only (no DB writes);
* consumes :class:`~backend.app.agent.schemas.NormalizedAgentRequest`;
* uses ``effective_as_of_date`` from the request;
* emits the location catalog identity;
* deterministic tie-break (deterministic ordered by ``(score desc, location_reference_id asc)``);
* never auto-selects an equal-score ambiguous location (returns
  :attr:`~backend.app.agent.enums.BlockerCode.LOCATION_AMBIGUOUS` with the
  top-N candidates);
* returns :attr:`~backend.app.agent.enums.BlockerCode.LOCATION_UNRESOLVED`
  when no match exists;
* returns :attr:`~backend.app.agent.enums.BlockerCode.LOCATION_CATALOG_STALE`
  when visibility fails.

No fuzzy matching algorithm is invented here: the existing location service
behavior is reused unchanged.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import (
    Blocker,
    ResolveLocationCandidate,
    ResolveLocationInput,
    ResolveLocationOutput,
    ResolvedLocation,
)
from backend.app.agent.ports import LocationResolverPort

# Reuse the production location service directly.  Per the design, no fuzzy
# matching may be invented in Agent code; we delegate to the existing callable.
from backend.app.planning.location import resolve_location_input as _upstream_resolve
from backend.app.planning.config import ParameterInferenceRules


# --- Location catalog identity --------------------------------------------
# Slice A picks a frozen catalog-version identifier; later rounds may move
# this to a registry-driven lookup.  The string is opaque and stable.
LOCATION_CATALOG_VERSION = "task13-location-catalog/v1"


class DefaultLocationAdapter:
    """Default ``resolve_location`` adapter.

    When ``resolver`` is supplied, the adapter uses the port directly and
    bypasses the upstream location service.  When ``resolver`` is ``None``
    the adapter falls back to the production ``resolve_location_input``
    callable; in that mode ``rules`` MUST also be supplied.
    """

    def __init__(
        self,
        *,
        resolver: LocationResolverPort | None = None,
        rules: ParameterInferenceRules | None = None,
        ambiguous_top_n: int = 5,
    ) -> None:
        self._resolver = resolver
        self._rules = rules
        self._ambiguous_top_n = ambiguous_top_n

    async def execute(self, session: AsyncSession, *, input: ResolveLocationInput) -> ResolveLocationOutput:
        nr = input.normalized_request
        if self._resolver is None:
            if self._rules is None:
                raise RuntimeError(
                    "DefaultLocationAdapter requires either a resolver port "
                    "or an explicit ParameterInferenceRules instance."
                )
            upstream_location = _to_upstream_location(nr.normalized_location)
            upstream = await _upstream_resolve(
                session,
                location=upstream_location,
                as_of_date=nr.effective_as_of_date,
                rules=self._rules,
            )
            resolved = _to_agent_resolved_location(upstream, nr.effective_as_of_date)
        else:
            upstream_resolved = await self._resolver.resolve(
                session=session,
                location=_to_upstream_location(nr.normalized_location),
                as_of_date=nr.effective_as_of_date,
            )
            resolved = _to_agent_resolved_location(upstream_resolved, nr.effective_as_of_date)

        blockers: list[Blocker] = []
        candidates: list[ResolveLocationCandidate] = []

        if resolved.status == "ambiguous":
            blockers.append(
                Blocker(
                    code=BlockerCode.LOCATION_AMBIGUOUS,
                    message="Multiple locations matched with identical score; caller must disambiguate.",
                    details={
                        "top_n": self._ambiguous_top_n,
                        "effective_as_of_date": str(nr.effective_as_of_date),
                    },
                    retry_hint="FIX_INPUT",
                )
            )
            for c in (resolved.candidates or [])[: self._ambiguous_top_n]:
                candidates.append(_to_resolve_location_candidate(c))
        elif resolved.status == "unresolved":
            blockers.append(
                Blocker(
                    code=BlockerCode.LOCATION_UNRESOLVED,
                    message="Location could not be resolved to any zone.",
                    details={"effective_as_of_date": str(nr.effective_as_of_date)},
                    retry_hint="FIX_INPUT",
                )
            )

        if resolved.warning == "location_catalog_stale":
            blockers.append(
                Blocker(
                    code=BlockerCode.LOCATION_CATALOG_STALE,
                    message="Location catalog is stale relative to effective_as_of_date.",
                    details={"effective_as_of_date": str(nr.effective_as_of_date)},
                    retry_hint="WAIT_FOR_DATA",
                )
            )

        return ResolveLocationOutput(
            resolved_location=resolved,
            location_catalog_version=LOCATION_CATALOG_VERSION,
            candidates=candidates,
            blockers=blockers,
        )


# --- helpers ---------------------------------------------------------------


def _to_upstream_location(resolved_placeholder: ResolvedLocation) -> dict[str, Any]:
    """Translate a stage-1 location payload to the upstream service shape.

    The upstream service accepts a dict with keys: ``address``, ``latitude``,
    ``longitude``, ``altitude_m``, ``location_reference_id``.  Slice A passes
    the placeholders already collected by the upstream layer (they originate
    from ``MinimalInputRequest.location``).  We carry them through unchanged
    when present in ``resolved_placeholder`` metadata.

    Because :class:`ResolvedLocation` is the *post-resolution* object, we
    pass-through its canonical identifiers when available.  The upstream
    resolver will use ``location_reference_id`` if set; otherwise it will
    fall back to address/coordinate resolution.
    """

    out: dict[str, Any] = {}
    if resolved_placeholder.location_reference_id is not None:
        out["location_reference_id"] = int(resolved_placeholder.location_reference_id)
    if resolved_placeholder.address_normalized is not None:
        out["address"] = resolved_placeholder.address_normalized
    if resolved_placeholder.address_raw is not None:
        out["address"] = resolved_placeholder.address_raw
    # Latitude/longitude/altitude are not stored on the placeholder; the
    # upstream resolver does not have access to them once the placeholder has
    # been promoted to a ResolvedLocation.  When the call originated from a
    # raw coordinate, the upstream resolver has already consumed those
    # values and the resulting ResolvedLocation carries them in
    # ``distance_km`` / ``score`` / etc.  We forward nothing here because
    # we cannot reconstruct the raw inputs.
    return out


def _to_agent_resolved_location(upstream: Any, effective_as_of_date: Any) -> ResolvedLocation:
    """Translate the upstream ``ResolvedLocation`` (a Pydantic model in
    ``backend.app.planning.schemas``) to the TASK-013 agent ``ResolvedLocation``.

    The upstream model exposes a similar surface; we map field-by-field and
    preserve the ``status`` discriminator.
    """

    # Upstream fields used in the agent projection:
    status_value = getattr(upstream, "status", "unresolved")
    candidates = getattr(upstream, "candidates", None) or []
    # Extract identification fields.
    location_ref_id = getattr(upstream, "location_reference_id", None)
    address_norm = getattr(upstream, "address_normalized", None)
    address_raw = getattr(upstream, "address_raw", None)
    farm_name = getattr(upstream, "farm_name", None)
    subfarm_name = getattr(upstream, "subfarm_name", None)
    province = getattr(upstream, "province", None)
    prefecture = getattr(upstream, "prefecture", None)
    county = getattr(upstream, "county", None)
    township = getattr(upstream, "township", None)
    village = getattr(upstream, "village", None)
    mapping_method = getattr(upstream, "matched_location_method", None) or "ADMIN_MATCH"
    climate_zone_id = getattr(upstream, "climate_zone_id", None)
    climate_zone_code = getattr(upstream, "climate_zone_code", None)
    climate_zone_version = getattr(upstream, "climate_zone_version", None)
    mapping_confidence = getattr(upstream, "mapping_confidence", None)
    distance_km = getattr(upstream, "distance_km", None)
    altitude_diff_m = getattr(upstream, "altitude_difference_m", None)
    score = getattr(upstream, "score", None)
    warning = getattr(upstream, "warning", None)

    # Convert Decimal values to canonical decimal strings.
    def _d(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        from decimal import Decimal

        return format(Decimal(value), "f")

    return ResolvedLocation(
        status=status_value,
        location_reference_id=int(location_ref_id) if location_ref_id is not None else None,
        address_normalized=address_norm,
        address_raw=address_raw,
        farm_name=farm_name,
        subfarm_name=subfarm_name,
        province=province,
        prefecture=prefecture,
        county=county,
        township=township,
        village=village,
        matched_location_method=_match_method(mapping_method),
        climate_zone_id=int(climate_zone_id) if climate_zone_id is not None else None,
        climate_zone_code=climate_zone_code,
        climate_zone_version=climate_zone_version,
        mapping_confidence=_d(mapping_confidence),
        distance_km=_d(distance_km),
        altitude_difference_m=_d(altitude_diff_m),
        score=_d(score),
        candidates=[_candidate_to_dict(c) for c in candidates],
        warning=warning,
    )


def _match_method(method: Any) -> str:
    """Map the upstream method enum/string to the TASK-013 enum."""

    if method is None:
        return "ADMIN_MATCH"
    s = str(method)
    if "TEXT" in s.upper():
        return "TEXT"
    if "COORD" in s.upper():
        return "COORDINATE"
    if "REFERENCE" in s.upper():
        return "REFERENCE_ID"
    return "ADMIN_MATCH"


def _candidate_to_dict(candidate: Any) -> dict[str, Any]:
    """Project an upstream candidate (ORM or dict) to a free-form dict."""

    out: dict[str, Any] = {}
    items_list: list[tuple[str, Any]] = (
        list(candidate.items())
        if isinstance(candidate, dict)
        else [
            (k, getattr(candidate, k, None))
            for k in (
                "location_reference_id",
                "address_normalized",
                "farm_name",
                "subfarm_name",
                "score",
                "distance_km",
                "id",
            )
        ]
    )
    for k, v in items_list:
        if v is None:
            continue
        if k in ("score", "distance_km"):
            from decimal import Decimal

            out[k] = format(Decimal(v), "f")
        elif k == "id":
            out.setdefault("location_reference_id", int(v))
        else:
            out[k] = v
    if "location_reference_id" not in out:
        for k, v in items_list:
            if k == "id" and v is not None:
                out["location_reference_id"] = int(v)
                break
    return out


def _to_resolve_location_candidate(candidate_dict: dict[str, Any]) -> ResolveLocationCandidate:
    """Project the free-form candidate dict to the strict agent candidate model."""

    score = candidate_dict.get("score")
    distance = candidate_dict.get("distance_km")
    return ResolveLocationCandidate(
        location_reference_id=int(candidate_dict["location_reference_id"]),
        address_normalized=candidate_dict.get("address_normalized"),
        farm_name=candidate_dict.get("farm_name"),
        subfarm_name=candidate_dict.get("subfarm_name"),
        score=str(score) if score is not None else None,
        distance_km=str(distance) if distance is not None else None,
    )


__all__ = [
    "DefaultLocationAdapter",
    "LOCATION_CATALOG_VERSION",
]
