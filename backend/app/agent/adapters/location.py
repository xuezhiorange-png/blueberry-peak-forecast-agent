"""TASK-013 Slice A — ``resolve_location`` deterministic adapter.

P0-3 fix: the adapter now reads the **raw caller-supplied** ``LocationInput``
(NOT the post-resolved :class:`~backend.app.agent.schemas.ResolvedLocation`).
The upstream
:func:`backend.app.planning.location.resolve_location_input` receives a dict
with keys ``address``, ``latitude``, ``longitude``, ``altitude_m``,
``location_reference_id``; we map the ``LocationInput`` fields into that
shape and let the upstream do the actual matching (per the design — no fuzzy
matching in Agent code).

Hard rules enforced:

* read-only (no DB writes);
* consumes :class:`~backend.app.agent.schemas.NormalizedAgentRequest` and the
  raw :class:`~backend.app.agent.schemas.LocationInput`;
* uses ``effective_as_of_date`` from the request;
* emits a **per-resolution** catalog version (sha256 over the effective
  as-of date and the sorted upstream catalog effective dates);
* deterministic tie-break (deterministic ordered by ``(score desc,
  location_reference_id asc)``);
* never auto-selects an equal-score ambiguous location (returns
  :attr:`~backend.app.agent.enums.BlockerCode.LOCATION_AMBIGUOUS` with the
  top-N candidates);
* returns :attr:`~backend.app.agent.enums.BlockerCode.LOCATION_UNRESOLVED`
  when no match exists;
* returns :attr:`~backend.app.agent.enums.BlockerCode.LOCATION_CATALOG_STALE`
  when the catalog is stale at the effective as-of date.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Any, Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.enums import BlockerCode
from backend.app.agent.ports import LocationResolverPort
from backend.app.agent.schemas import (
    Blocker,
    LocationInput,
    ResolvedLocation,
    ResolveLocationCandidate,
    ResolveLocationInput,
    ResolveLocationOutput,
)
from backend.app.planning.config import ParameterInferenceRules

# Reuse the production location service directly.  Per the design, no fuzzy
# matching may be invented in Agent code; we delegate to the existing callable.
from backend.app.planning.location import resolve_location_input as _upstream_resolve

# Historical constant preserved for backward compat with existing tests.
# The actual catalog version is computed per-resolution in
# :func:`_compute_catalog_version`.
LOCATION_CATALOG_VERSION = "task13-location-catalog/v1"


def _compute_catalog_version(
    effective_as_of_date: date,
    catalog_effective_dates: list[date],
) -> str:
    """Deterministic per-resolution catalog version.

    sha256 over the effective as-of date and the sorted catalog effective
    dates.  Two resolutions with the same as-of date and the same upstream
    catalog state always produce the same catalog_version string.
    """
    payload = (
        effective_as_of_date.isoformat()
        + "|"
        + ",".join(sorted(d.isoformat() for d in catalog_effective_dates))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _catalog_effective_dates(session: AsyncSession, *, as_of_date: date) -> list[date]:
    """Best-effort read of upstream catalog effective_from dates."""
    try:
        from sqlalchemy import select

        from backend.app.models.planning import LocationReference

        rows = (
            await session.scalars(
                select(LocationReference.valid_from).where(
                    LocationReference.valid_from <= as_of_date
                )
            )
        ).all()
        return list(rows)
    except Exception:  # noqa: BLE001
        return []


def _to_upstream_dict(location_input: LocationInput) -> dict[str, Any]:
    """Map :class:`LocationInput` to the upstream dict shape.

    Deterministic precedence (highest → lowest):
    1. ``location_reference_id``
    2. ``address``
    3. ``(latitude, longitude)`` coordinates
    4. ``raw_text``
    5. ``map_pick_token``

    ``address`` takes the ``address`` field if set, else falls back to
    ``raw_text`` (the upstream expects a single ``address`` string).
    """
    out: dict[str, Any] = {}
    if location_input.location_reference_id is not None:
        out["location_reference_id"] = int(location_input.location_reference_id)
    if location_input.address is not None:
        out["address"] = location_input.address
    elif location_input.raw_text is not None:
        out["address"] = location_input.raw_text
    if location_input.latitude is not None and location_input.longitude is not None:
        out["latitude"] = str(Decimal(location_input.latitude))
        out["longitude"] = str(Decimal(location_input.longitude))
    if location_input.altitude_m is not None:
        out["altitude_m"] = str(Decimal(location_input.altitude_m))
    return out


def _to_agent_resolved_location(upstream: Any, effective_as_of_date: date) -> ResolvedLocation:
    """Translate the upstream ``ResolvedLocation`` to the agent ``ResolvedLocation``."""

    status_value: Literal["resolved", "ambiguous", "unresolved"] = cast(
        Literal["resolved", "ambiguous", "unresolved"],
        str(getattr(upstream, "status", "unresolved")),
    )
    candidates = getattr(upstream, "candidates", None) or []
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
    # The upstream ``warnings`` tuple may contain ``location_catalog_stale``
    # if the catalog is stale relative to as_of_date.  Mirror that as the
    # ``warning`` field on the agent ResolvedLocation.
    upstream_warnings = getattr(upstream, "warnings", ()) or ()
    warning = "location_catalog_stale" if "location_catalog_stale" in upstream_warnings else None

    def _d(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return format(Decimal(str(value)), "f")

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
        matched_location_method=cast(
            Literal["REFERENCE_ID", "TEXT", "COORDINATE", "ADMIN_MATCH"],
            _match_method(mapping_method),
        ),
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
            out[k] = format(Decimal(str(v)), "f")
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

    async def execute(
        self, session: AsyncSession, *, input: ResolveLocationInput
    ) -> ResolveLocationOutput:
        location_input = input.resolved_location_input
        nr = input.normalized_request
        if self._resolver is None:
            if self._rules is None:
                raise RuntimeError(
                    "DefaultLocationAdapter requires either a resolver port "
                    "or an explicit ParameterInferenceRules instance."
                )
            upstream_location = _to_upstream_dict(location_input)
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
                location=_to_upstream_dict(location_input),
                as_of_date=nr.effective_as_of_date,
            )
            # When the resolver returns an agent ResolvedLocation (test
            # fakes), honor its ``warning`` field directly.  When it
            # returns an upstream ResolvedLocation dataclass (with
            # ``warnings`` tuple), translate via the helper.
            if hasattr(upstream_resolved, "matched_location_method") and not hasattr(
                upstream_resolved, "warnings"
            ):
                resolved = upstream_resolved
            else:
                resolved = _to_agent_resolved_location(upstream_resolved, nr.effective_as_of_date)

        # Per-resolution catalog version: sha256 over (effective_as_of_date,
        # sorted catalog effective_from dates).
        catalog_effective_dates = await _catalog_effective_dates(
            session, as_of_date=nr.effective_as_of_date
        )
        catalog_version = _compute_catalog_version(nr.effective_as_of_date, catalog_effective_dates)

        blockers: list[Blocker] = []
        candidates: list[ResolveLocationCandidate] = []

        if resolved.status == "ambiguous":
            blockers.append(
                Blocker(
                    code=BlockerCode.LOCATION_AMBIGUOUS,
                    message=(
                        "Multiple locations matched with identical score; caller must disambiguate."
                    ),
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
            location_catalog_version=catalog_version,
            candidates=candidates,
            blockers=blockers,
        )


__all__ = ["DefaultLocationAdapter", "LOCATION_CATALOG_VERSION"]
