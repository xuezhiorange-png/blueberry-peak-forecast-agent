"""V0_21 S2 synthetic structural descriptions, never yield or peak adjustments.

Historical descriptions and origin-visible snapshots are separate outputs.
The original S1 result is independently reproduced, not trusted as a bag of
origin-eligible facts. All source rows remain unchanged in the input/ledger.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field

from backend.research import v021_cycle_features as cycle

BASES = ("PLANTED", "PRODUCTIVE", "EFFECTIVE")
STATE = Literal["OBSERVED", "PLANNED", "UNKNOWN"]
Record = dict[str, Any]


class Source(cycle.Contract):
    reference: str
    version: str
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    clocks: cycle.ClockEvidence | None = None


class Link(cycle.Contract):
    link_id: str = Field(min_length=1)
    previous_member_id: str | None
    next_member_id: str | None
    previous_entity_id: str | None
    next_entity_id: str | None
    previous_as_of: date | None
    next_as_of: date | None
    kind: Literal["CONTINUING_MEMBER", "VARIETY_REPLACEMENT", "ENTRY", "EXIT", "UNKNOWN", "BROKEN"]
    source: Source


class Supplement(cycle.Contract):
    record_id: str = Field(min_length=1)
    logical_id: str | None
    revision_id: str | None
    supersedes_revision: str | None
    observed_or_planned: STATE
    source: Source


class Density(Supplement):
    member_id: str
    cohort_id: str | None
    plant_count: str | None
    measured_area: str | None
    area_unit: str
    area_basis: str
    method: str | None
    effective_date: cycle.DateToken


class Replant(Supplement):
    previous_member_id: str
    next_member_id: str
    old_cohort_id: str | None
    new_cohort_id: str | None
    business_date: cycle.DateToken


class Scenario(cycle.Contract):
    scenario_id: str = Field(min_length=1)
    link_ids: list[str]


class Declarations(cycle.Contract):
    schema_version: Literal["V0_21_S2_DECLARATIONS_R1"]
    data_class: Literal["SYNTHETIC_TEST_FIXTURE"]
    business_timezone: str
    s1_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    links: list[Link]
    densities: list[Density]
    replants: list[Replant]
    scenarios: list[Scenario]


def _known(value: str | None) -> bool:
    return isinstance(value, str) and value.strip().upper() not in cycle.METHOD_UNKNOWN


def _number(value: Any) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d{1,6})?", value):
        raise ValueError("DECIMAL_VALUE_INVALID")
    if len(value) > 30:
        raise ValueError("DECIMAL_VALUE_INVALID")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("DECIMAL_VALUE_INVALID") from exc


def _six(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _ratio(change: Decimal, previous: Decimal) -> str | None:
    if previous == 0:
        return None
    value = format(change / previous, "f")
    return value.rstrip("0").rstrip(".") if "." in value else value


def _status(reasons: list[str]) -> str:
    hard = ("CONFLICT", "CHANGED", "BROKEN", "INVALID", "NOT_MU", "REPLACEMENT", "NOT_CROSS_SEASON")
    return "NOT_COMPARABLE" if any(any(k in r for k in hard) for r in reasons) else "NOT_PROVEN"


def _source_reason(
    source: Source,
    origin: cycle.Origin | None,
    *,
    business: tuple[date, date] | None = None,
    planned: bool = False,
) -> str | None:
    if not all(_known(v) for v in (source.reference, source.version, source.sha256)):
        return "SOURCE_IDENTITY_NOT_PROVEN"
    if origin is not None:
        return cycle._clock_reason(source.clocks, origin, business=business, planned=planned)
    return None


def _relation_reason(
    link: Link,
    members: dict[str, cycle.Member],
    mapping: dict[str, str | None],
    origin: cycle.Origin | None,
) -> str | None:
    if link.kind == "UNKNOWN":
        return "CONTINUITY_NOT_PROVEN"
    if link.kind == "BROKEN":
        return "ENTITY_CONTINUITY_BROKEN"
    a, b = members.get(link.previous_member_id or ""), members.get(link.next_member_id or "")
    endpoints = [m for m in (a, b) if m is not None]
    if link.kind == "ENTRY":
        shape = (
            a is None
            and link.previous_member_id is None
            and b is not None
            and _known(link.next_entity_id)
        )
    elif link.kind == "EXIT":
        shape = (
            b is None
            and link.next_member_id is None
            and a is not None
            and _known(link.previous_entity_id)
        )
    else:
        shape = a is not None and b is not None
    if not shape:
        return "CONTINUITY_ENDPOINT_NOT_PROVEN"
    if any(
        mapping.get(m.member_id) or not cycle._complete(tuple(m.scope.model_dump().values()))
        for m in endpoints
    ):
        return "UNMAPPED_MEMBER"
    if a and b:
        for key in ("base", "farm", "subfarm", "plot", "production_system"):
            if getattr(a.scope, key) != getattr(b.scope, key):
                return key.upper() + "_CHANGED"
        if not _known(link.previous_entity_id) or not _known(link.next_entity_id):
            return "ENTITY_CONTINUITY_NOT_PROVEN"
        if link.previous_entity_id != link.next_entity_id:
            return "ENTITY_CONTINUITY_BROKEN"
        if b.scope.season <= a.scope.season:
            return "SEASON_ORDER_INVALID"
        if link.previous_as_of is None or link.next_as_of is None:
            return "ASSESSMENT_DATE_NOT_PROVEN"
        if link.previous_as_of >= link.next_as_of:
            return "ASSESSMENT_DATE_ORDER_INVALID"
        changed = a.scope.variety != b.scope.variety
        if changed and link.kind != "VARIETY_REPLACEMENT":
            return "VARIETY_CHANGED"
        if not changed and link.kind == "VARIETY_REPLACEMENT":
            return "VARIETY_REPLACEMENT_IDENTITY_INVALID"
    for m in endpoints:
        if mapping.get(m.member_id) or not cycle._complete(tuple(m.scope.model_dump().values())):
            return "UNMAPPED_MEMBER"
        if origin is not None:
            if not _known(m.evidence_reference):
                return "MEMBER_SOURCE_NOT_PROVEN"
            try:
                if cycle._aware(m.known_at) > origin.cutoff:
                    return "MEMBER_RELATION_NOT_VISIBLE"
            except ValueError:
                return "MEMBER_RELATION_TIME_NOT_PROVEN"
    return _source_reason(link.source, origin)


def _bounds(token: Record, origin: cycle.Origin | None, timezone: str) -> tuple[date, date]:
    return cycle._bounds(
        cycle.DateToken.model_validate(token), ZoneInfo(origin.timezone if origin else timezone)
    )


def _area_visible(
    record: Record,
    clocks: dict[str, cycle.RecordClock],
    origin: cycle.Origin | None,
) -> str | None:
    if origin is None:
        return None
    proof = clocks.get(record["record_id"])
    # A known late revision is excluded before inspecting its changed payload.
    reason = cycle._clock_reason(
        proof, origin, raw=record, planned=record["observed_or_planned"] == "PLANNED"
    )
    if reason == "NOT_VISIBLE_AT_CUTOFF":
        return reason
    try:
        lo, hi = _bounds(record["business_date"], origin, origin.timezone)
    except ValueError:
        return "AREA_BUSINESS_DATE_NOT_PROVEN"
    if hi >= origin.origin_date:
        return "FUTURE_OR_ORIGIN_DAY_FACT"
    if reason:
        return reason
    return cycle._clock_reason(proof, origin, raw=record, business=(lo, hi))


def _revision_head(records: list[Record]) -> tuple[Record | None, str | None]:
    if any(not _known(r.get(k)) for r in records for k in ("logical_id", "revision_id")):
        return None, "REVISION_IDENTITY_NOT_PROVEN"
    if any(
        r.get("supersedes_revision") is not None and not _known(r["supersedes_revision"])
        for r in records
    ):
        return None, "REVISION_IDENTITY_NOT_PROVEN"
    return cycle._heads(records)


def _area_at(
    member: cycle.Member | None,
    point: date | None,
    records: list[Record],
    clocks: dict[str, cycle.RecordClock],
    origin: cycle.Origin | None,
    timezone: str,
) -> dict[str, Record]:
    errors: dict[str, list[str]] = {b: [] for b in BASES}
    selected: dict[str, list[dict[str, Any]]] = {b: [] for b in BASES}
    considered: dict[str, list[str]] = {b: [] for b in BASES}
    rows = [
        r
        for r in records
        if member and cycle._scope(r) == tuple(member.scope.model_dump().values())
    ]
    if member is None or point is None:
        errors = {b: ["ASSESSMENT_DATE_NOT_PROVEN"] for b in BASES}
    elif origin is not None and point >= origin.origin_date:
        errors = {b: ["ASSESSMENT_DATE_NOT_PRIOR"] for b in BASES}
    elif len(rows) > 256:
        errors = {b: ["AREA_MEMBER_SIZE_LIMIT"] for b in BASES}
    else:
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            basis = (r.get("area") or {}).get("basis")
            relevant = [basis] if basis in BASES else list(BASES)
            visibility = _area_visible(r, clocks, origin)
            if visibility in {"NOT_VISIBLE_AT_CUTOFF", "FUTURE_OR_ORIGIN_DAY_FACT"}:
                continue
            for b in relevant:
                considered[b].append(r["record_id"])
            reasons = [visibility] if visibility else []
            if r["observed_or_planned"] != "OBSERVED":
                reasons.append(
                    "PLANNED_NOT_OBSERVED"
                    if r["observed_or_planned"] == "PLANNED"
                    else "AREA_STATE_UNKNOWN"
                )
            if basis not in BASES:
                reasons.append("AREA_BASIS_NOT_PROVEN")
            if not _known(r.get("source_reference")) or not _known(r.get("source_version")):
                reasons.append("SOURCE_IDENTITY_NOT_PROVEN")
            reasons.extend(i["code"] for i in r["issues"] if i["severity"] == "ERROR")
            if "CONFLICT" in r["states"] and not reasons:
                reasons.append("UPSTREAM_CONFLICT")
            if reasons:
                for b in relevant:
                    errors[b].extend(reasons)
                continue
            groups[(str(basis), r["source_reference"], str(r.get("logical_id") or ""))].append(r)
        heads = []
        for (basis, _, _), group in groups.items():
            head, reason = _revision_head(group)
            if reason:
                errors[basis].append(reason)
            elif head:
                heads.append(head)
        intervals = []
        for r in heads:
            a, basis = r["area"], r["area"]["basis"]
            try:
                start, end = (
                    _bounds(a["effective_from"], origin, timezone),
                    _bounds(a["effective_to"], origin, timezone),
                )
                if start[1] > end[0]:
                    raise ValueError("AREA_EFFECTIVE_INTERVAL_NOT_PROVEN")
                if a["unit"] != "mu":
                    raise ValueError("AREA_UNIT_NOT_MU")
                if a["value"] is None:
                    raise ValueError("AREA_VALUE_MISSING")
                amount = _number(a["value"])
                intervals.append((r, start, end, amount))
                if start[0] <= point <= end[1]:
                    if start[1] <= point <= end[0]:
                        selected[basis].append(dict(value=amount, record_id=r["record_id"]))
                    else:
                        errors[basis].append("AREA_EFFECTIVE_DATE_AMBIGUOUS")
            except ValueError as exc:
                errors[basis].append(str(exc))
        for i, (a, astart, aend, av) in enumerate(intervals):
            for b, bstart, bend, bv in intervals[i + 1 :]:
                if astart[0] > bend[1] or bstart[0] > aend[1]:
                    continue
                ab, bb = a["area"]["basis"], b["area"]["basis"]
                if ab == bb:
                    errors[ab].append("AREA_INTERVAL_CONFLICT")
                    if a["source_reference"] != b["source_reference"]:
                        errors[ab].append("AREA_SOURCE_CONFLICT")
                elif (ab == "PLANTED" and bv > av) or (bb == "PLANTED" and av > bv):
                    errors[ab].append("AREA_BASIS_CONFLICT")
                    errors[bb].append("AREA_BASIS_CONFLICT")
    result = {}
    for basis in BASES:
        reasons = sorted(set(errors[basis]))
        values = selected[basis]
        if not reasons and len(values) != 1:
            reasons = ["AREA_RECORD_MISSING" if not values else "AREA_INTERVAL_CONFLICT"]
        result[basis] = dict(
            status=_status(reasons) if reasons else "PREPARED",
            reasons=reasons,
            value_mu=None if reasons else _six(values[0]["value"]),
            record_ids=[v["record_id"] for v in values],
            considered_record_ids=sorted(considered[basis]),
        )
    return result


def _area_change(a: Record, b: Record, reason: str | None = None) -> Record:
    reasons = sorted(set(([reason] if reason else []) + a["reasons"] + b["reasons"]))
    before, after = a["value_mu"], b["value_mu"]
    value = dict(
        status=_status(reasons) if reasons else "COMPARABLE",
        reasons=reasons,
        previous_mu=before,
        next_mu=after,
        previous_record_ids=a.get("considered_record_ids", a["record_ids"]),
        next_record_ids=b.get("considered_record_ids", b["record_ids"]),
        unit="mu",
        delta_mu=None,
        relative_change_ratio=None,
        relative_change_reason=None,
    )
    if not reasons:
        previous, following = Decimal(before), Decimal(after)
        value.update(
            delta_mu=_six(following - previous),
            relative_change_ratio=_ratio(following - previous, previous),
            relative_change_reason="ZERO_PREVIOUS_AREA" if previous == 0 else None,
        )
    return value


def _supplement_head(rows: list[Record]) -> tuple[list[Record], list[str]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["source"]["reference"], row.get("logical_id") or "")].append(row)
    heads, reasons = [], []
    for group in groups.values():
        head, reason = _revision_head(group)
        if reason:
            reasons.append(reason)
        elif head:
            heads.append(head)
    return heads, reasons


def _density_at(
    member: cycle.Member | None,
    point: date | None,
    rows: list[Density],
    origin: cycle.Origin | None,
    timezone: str,
) -> Record:
    values, reasons = [], []
    for r in rows:
        if member is None or r.member_id != member.member_id:
            continue
        visibility = _source_reason(r.source, origin, planned=r.observed_or_planned == "PLANNED")
        if visibility == "NOT_VISIBLE_AT_CUTOFF":
            continue
        try:
            bounds = _bounds(r.effective_date.model_dump(), origin, timezone)
            if point is None:
                raise ValueError("ASSESSMENT_DATE_NOT_PROVEN")
            if origin is not None and bounds[1] >= origin.origin_date:
                continue
            if bounds[0] > point:
                continue
            if bounds[1] > point:
                raise ValueError("DENSITY_EFFECTIVE_DATE_AMBIGUOUS")
            if visibility:
                raise ValueError(visibility)
            if origin is not None:
                reason = _source_reason(
                    r.source, origin, business=bounds, planned=r.observed_or_planned == "PLANNED"
                )
                if reason:
                    raise ValueError(reason)
            values.append(r.model_dump(mode="json"))
        except ValueError as exc:
            reasons.append(str(exc))
    heads, graph_reasons = _supplement_head(values)
    reasons.extend(graph_reasons)
    if not reasons and len(heads) != 1:
        reasons.append("DENSITY_INFORMATION_MISSING" if not heads else "DENSITY_SOURCE_CONFLICT")
    value, calculation_value, cohort, method, basis = None, None, None, None, None
    if not reasons:
        h = heads[0]
        try:
            if h["observed_or_planned"] != "OBSERVED":
                raise ValueError(
                    "PLANNED_NOT_OBSERVED"
                    if h["observed_or_planned"] == "PLANNED"
                    else "DENSITY_STATE_UNKNOWN"
                )
            if not _known(h["cohort_id"]):
                raise ValueError("COHORT_IDENTITY_NOT_PROVEN")
            if h["plant_count"] is None or not re.fullmatch(r"\d+", h["plant_count"]):
                raise ValueError("PLANT_COUNT_MISSING_OR_INVALID")
            if h["area_unit"] != "mu":
                raise ValueError("DENSITY_UNIT_NOT_MU")
            if h["area_basis"] not in BASES:
                raise ValueError("DENSITY_AREA_BASIS_NOT_PROVEN")
            if not _known(h["method"]):
                raise ValueError("DENSITY_METHOD_NOT_PROVEN")
            area = _number(h["measured_area"])
            if area == 0:
                raise ValueError("DENSITY_DENOMINATOR_NOT_POSITIVE")
            amount = _number(h["plant_count"]) / area
            value, calculation_value = _six(amount), str(amount)
            cohort, method, basis = h["cohort_id"], h["method"], h["area_basis"]
        except ValueError as exc:
            reasons.append(str(exc))
    return dict(
        value=value,
        calculation_value=calculation_value,
        reasons=sorted(set(reasons)),
        cohort_id=cohort,
        method=method,
        area_basis=basis,
    )


def _density_change(a: Record, b: Record, reason: str | None = None) -> Record:
    reasons = sorted(set(([reason] if reason else []) + a["reasons"] + b["reasons"]))
    if not reasons:
        for key in ("cohort_id", "method", "area_basis"):
            if a[key] != b[key]:
                reasons.append("DENSITY_" + key.upper() + "_CHANGED")
    result = dict(
        status=_status(reasons) if reasons else "COMPARABLE",
        reasons=reasons,
        previous_plants_per_mu=a["value"],
        next_plants_per_mu=b["value"],
        delta_plants_per_mu=None,
        relative_change_ratio=None,
        relative_change_reason=None,
    )
    if not reasons:
        before, after = Decimal(a["calculation_value"]), Decimal(b["calculation_value"])
        result.update(
            delta_plants_per_mu=_six(after - before),
            relative_change_ratio=_ratio(after - before, before),
            relative_change_reason="ZERO_PREVIOUS_DENSITY" if before == 0 else None,
        )
    return result


def _replant(link: Link, rows: list[Replant], origin: cycle.Origin | None, timezone: str) -> Record:
    candidates, failures, planned = [], [], []
    for r in rows:
        if (r.previous_member_id, r.next_member_id) != (
            link.previous_member_id,
            link.next_member_id,
        ):
            continue
        reason = _source_reason(r.source, origin, planned=r.observed_or_planned == "PLANNED")
        if reason == "NOT_VISIBLE_AT_CUTOFF":
            continue
        try:
            bounds = _bounds(r.business_date.model_dump(), origin, timezone)
            if origin is not None and bounds[1] >= origin.origin_date:
                continue
            if reason:
                raise ValueError(reason)
            if link.next_as_of is None or bounds[1] > link.next_as_of:
                raise ValueError("REPLANT_DATE_AFTER_ASSESSMENT")
            if origin is not None:
                reason = _source_reason(
                    r.source, origin, business=bounds, planned=r.observed_or_planned == "PLANNED"
                )
                if reason:
                    raise ValueError(reason)
            candidates.append(r.model_dump(mode="json"))
        except ValueError as exc:
            failures.append(str(exc))
    heads, errors = _supplement_head(candidates)
    failures.extend(errors)
    events = []
    for h in sorted(heads, key=lambda h: h["record_id"]):
        if h["observed_or_planned"] != "OBSERVED":
            planned.append(h)
            failures.append(
                "PLANNED_NOT_OBSERVED"
                if h["observed_or_planned"] == "PLANNED"
                else "REPLANT_STATE_UNKNOWN"
            )
        elif not _known(h["old_cohort_id"]) or not _known(h["new_cohort_id"]):
            failures.append("REPLANT_COHORT_NOT_PROVEN")
        elif h["old_cohort_id"] == h["new_cohort_id"]:
            failures.append("REPLANT_COHORT_CONFLICT")
        else:
            events.append(h)
    if not events and not failures:
        failures = ["REPLANT_INFORMATION_MISSING"]
    return dict(
        status=_status(failures) if failures else "COMPARABLE",
        reason=sorted(set(failures))[0] if failures else None,
        reasons=sorted(set(failures)),
        events=events,
        planned_or_unknown=planned,
    )


def _compare(
    link: Link,
    members: dict[str, cycle.Member],
    mapping: dict[str, str | None],
    records: list[Record],
    clocks: dict[str, cycle.RecordClock],
    request: Declarations,
    origin: cycle.Origin | None = None,
) -> Record:
    a, b = members.get(link.previous_member_id or ""), members.get(link.next_member_id or "")
    reason = _relation_reason(link, members, mapping, origin)
    if reason:
        empty = {
            basis: dict(status=_status([reason]), reasons=[reason], value_mu=None, record_ids=[])
            for basis in BASES
        }
        before = after = empty
    else:
        before = _area_at(
            a, link.previous_as_of, records, clocks, origin, request.business_timezone
        )
        after = _area_at(b, link.next_as_of, records, clocks, origin, request.business_timezone)
    varieties = []
    if reason is None and link.kind in {"VARIETY_REPLACEMENT", "ENTRY", "EXIT"}:
        for kind, member, areas in (("EXIT", a, before), ("ENTRY", b, after)):
            if member is not None:
                varieties.append(
                    dict(
                        kind=kind,
                        member_id=member.member_id,
                        variety=member.scope.variety,
                        areas=areas,
                    )
                )
        reason = (
            "VARIETY_REPLACEMENT_NOT_SAME_TREND"
            if link.kind == "VARIETY_REPLACEMENT"
            else "ENTRY_OR_EXIT_NOT_CROSS_SEASON_TREND"
        )
    changes = {basis: _area_change(before[basis], after[basis], reason) for basis in BASES}
    reasons = sorted({v for change in changes.values() for v in change["reasons"]})
    missing_density = dict(
        value=None, reasons=[reason], cohort_id=None, method=None, area_basis=None
    )
    densities = (
        (missing_density, missing_density)
        if reason
        else (
            _density_at(
                a, link.previous_as_of, request.densities, origin, request.business_timezone
            ),
            _density_at(b, link.next_as_of, request.densities, origin, request.business_timezone),
        )
    )
    replant = (
        _replant(link, request.replants, origin, request.business_timezone)
        if reason is None
        else dict(
            status=_status([reason]),
            reason=reason,
            reasons=[reason],
            events=[],
            planned_or_unknown=[],
        )
    )
    return dict(
        link_id=link.link_id,
        kind=link.kind,
        status_scope="AREA_COMPARISON_AND_MEMBER_CONTINUITY_ONLY",
        status=_status(reasons) if reasons else "COMPARABLE",
        reasons=reasons,
        previous_member_id=link.previous_member_id,
        next_member_id=link.next_member_id,
        previous_as_of=str(link.previous_as_of) if link.previous_as_of else None,
        next_as_of=str(link.next_as_of) if link.next_as_of else None,
        previous_scope=a.scope.model_dump() if a else None,
        next_scope=b.scope.model_dump() if b else None,
        area_changes=changes,
        variety_changes=varieties,
        density_change=_density_change(densities[0], densities[1], reason=reason),
        replant=replant,
    )


def prepare(s1_result: dict[str, Any], declarations: dict[str, Any]) -> dict[str, Any]:
    """Pure S2 preparation. All authority/real-data/model gates remain closed."""
    if (
        declarations.get("data_class") != "SYNTHETIC_TEST_FIXTURE"
        or s1_result.get("data_class") != "SYNTHETIC_TEST_FIXTURE"
    ):
        raise ValueError("SYNTHETIC_ONLY")
    request = Declarations.model_validate(declarations)
    if (
        len(cycle.canonical(declarations)) > cycle.MAX_BYTES
        or len(request.links) > 4096
        or len(request.densities) + len(request.replants) > 20000
    ):
        raise ValueError("S2_INPUT_SIZE_LIMIT")
    if request.s1_result_sha256 != s1_result.get("result_sha256"):
        raise ValueError("S1_RESULT_HASH_MISMATCH")
    package, original = s1_result["original_package"], s1_result["original_declarations"]
    if cycle.prepare(package, original) != s1_result:
        raise ValueError("S1_RESULT_RECOMPUTATION_MISMATCH")
    upstream = cycle.Declarations.model_validate(original)
    try:
        ZoneInfo(request.business_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("STRUCTURE_TIMEZONE_NOT_PROVEN") from exc
    if any(origin.timezone != request.business_timezone for origin in upstream.origins):
        raise ValueError("STRUCTURE_TIMEZONE_MISMATCH")
    for objects, key in (
        (request.links, "link_id"),
        (request.densities, "record_id"),
        (request.replants, "record_id"),
        (request.scenarios, "scenario_id"),
    ):
        ids = [getattr(obj, key) for obj in objects]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_S2_DECLARATION_ID")
    link_ids = {link.link_id for link in request.links}
    supplement_ids = [r.record_id for r in [*request.densities, *request.replants]]
    if len(supplement_ids) != len(set(supplement_ids)):
        raise ValueError("DUPLICATE_S2_DECLARATION_ID")
    if set(supplement_ids) & {r["record_id"] for r in package["records"]}:
        raise ValueError("SUPPLEMENT_RECORD_ID_COLLISION")
    if any(
        len(s.link_ids) != len(set(s.link_ids)) or not set(s.link_ids) <= link_ids
        for s in request.scenarios
    ):
        raise ValueError("SCENARIO_MEMBERSHIP_INVALID")
    members = {m.member_id: m for m in upstream.members}
    mapping = {m["member_id"]: m["reason"] for m in s1_result["association_ledger"]}
    records = [r for r in package["records"] if r["kind"] == "AREA"]
    ordered = sorted(request.links, key=lambda link: link.link_id)
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        comparisons = [
            _compare(link, members, mapping, records, upstream.record_clocks, request)
            for link in ordered
        ]
        snapshots = []
        visibility_ledger = {}
        for link in ordered:
            endpoint = members.get(link.next_member_id or link.previous_member_id or "")
            for origin in sorted(upstream.origins, key=lambda o: o.origin_id):
                if endpoint is None or (origin.base, origin.season) != (
                    endpoint.scope.base,
                    endpoint.scope.season,
                ):
                    continue
                value = dict(
                    link_id=link.link_id,
                    origin_id=origin.origin_id,
                    origin_date=str(origin.origin_date),
                    timezone=origin.timezone,
                    cutoff=origin.cutoff.astimezone(UTC).isoformat(),
                    temporal_use="SYNTHETIC_AS_OF_ONLY",
                    comparison=_compare(
                        link, members, mapping, records, upstream.record_clocks, request, origin
                    ),
                )
                snapshots.append({**value, "feature_sha256": cycle.digest(value)})
                for member_id in (link.previous_member_id, link.next_member_id):
                    member = members.get(member_id or "")
                    if member is None:
                        continue
                    for r in records:
                        if cycle._scope(r) != tuple(member.scope.model_dump().values()):
                            continue
                        visibility = _area_visible(r, upstream.record_clocks, origin)
                        visibility_ledger[(origin.origin_id, r["record_id"])] = dict(
                            origin_id=origin.origin_id,
                            member_id=member.member_id,
                            record_id=r["record_id"],
                            record_sha256=cycle.digest(r),
                            reason=visibility,
                            status="EXCLUDED_AT_ORIGIN"
                            if visibility in {"NOT_VISIBLE_AT_CUTOFF", "FUTURE_OR_ORIGIN_DAY_FACT"}
                            else "NOT_PROVEN"
                            if visibility
                            else "SYNTHETIC_TIME_CHECK_PASSED",
                        )
    used = {
        mid for link in ordered for mid in (link.previous_member_id, link.next_member_id) if mid
    }
    by_link = {c["link_id"]: c for c in comparisons}
    s1_ledger = {r["record_id"]: r for r in s1_result["record_ledger"]}
    endpoint_pairs = {(link.previous_member_id, link.next_member_id) for link in ordered}
    body = dict(
        schema_version="V0_21_S2_STRUCTURE_SCENARIOS_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        strict_pit_validated=False,
        real_source_authority_proven=False,
        model_use_authorized=False,
        s3_s4_implemented=False,
        temporal_use="RETROSPECTIVE_DESCRIPTION_ONLY",
        business_timezone=request.business_timezone,
        numerical_policy=dict(
            decimal_precision=50,
            display_scale=6,
            rounding="ROUND_HALF_EVEN",
            density_differences_before_display_rounding=True,
        ),
        input_identity=dict(
            s1_result_sha256=request.s1_result_sha256,
            structure_declarations_sha256=cycle.digest(declarations),
            **s1_result["input_identity"],
        ),
        original_declarations=copy.deepcopy(declarations),
        original_cycle_associations=copy.deepcopy(s1_result["cycle_associations"]),
        area_ledger=[
            dict(
                record_id=r["record_id"],
                record_sha256=cycle.digest(r),
                raw_record=copy.deepcopy(r),
                member_ids=s1_ledger[r["record_id"]]["member_ids"],
                reason=s1_ledger[r["record_id"]]["reason"],
                synthetic_clock_evidence=upstream.record_clocks[r["record_id"]].model_dump(
                    mode="json"
                )
                if r["record_id"] in upstream.record_clocks
                else None,
            )
            for r in sorted(records, key=lambda r: r["record_id"])
        ],
        supplement_ledger=[
            dict(
                record_id=r.record_id,
                record_sha256=cycle.digest(r.model_dump(mode="json")),
                raw_record=r.model_dump(mode="json"),
                reason=None
                if (
                    (isinstance(r, Density) and r.member_id in members and r.member_id in used)
                    or (
                        isinstance(r, Replant)
                        and r.previous_member_id in members
                        and r.next_member_id in members
                        and (r.previous_member_id, r.next_member_id) in endpoint_pairs
                    )
                )
                else "UNKNOWN_SUPPLEMENT_MEMBER",
            )
            for r in sorted([*request.densities, *request.replants], key=lambda r: r.record_id)
        ],
        unlinked_members=[
            dict(member_id=m, status="NOT_PROVEN", reason="CONTINUITY_NOT_DECLARED")
            for m in sorted(members.keys() - used)
        ],
        continuity_ledger=[
            dict(
                raw_declaration=link.model_dump(mode="json"),
                status=by_link[link.link_id]["status"],
                reasons=by_link[link.link_id]["reasons"],
            )
            for link in ordered
        ],
        comparisons=comparisons,
        origin_snapshots=snapshots,
        visibility_ledger=[visibility_ledger[k] for k in sorted(visibility_ledger)],
        scenario_results=[
            dict(
                scenario_id=s.scenario_id,
                link_ids=sorted(s.link_ids),
                component_status_counts=_component_counts([by_link[k] for k in s.link_ids]),
            )
            for s in sorted(request.scenarios, key=lambda s: s.scenario_id)
        ],
    )
    return {**body, "result_sha256": cycle.digest(body)}


def _component_counts(rows: list[Record]) -> Record:
    return {
        "area_and_continuity": dict(sorted(Counter(r["status"] for r in rows).items())),
        "density": dict(sorted(Counter(r["density_change"]["status"] for r in rows).items())),
        "replant": dict(sorted(Counter(r["replant"]["status"] for r in rows).items())),
    }


def _csv(result: Record) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "link_id",
            "basis",
            "previous_mu",
            "next_mu",
            "delta_mu",
            "relative_change_ratio",
            "status",
            "reasons",
        ]
    )
    for row in result["comparisons"]:
        for basis, area in row["area_changes"].items():
            values = [
                row["link_id"],
                basis,
                area["previous_mu"],
                area["next_mu"],
                area["delta_mu"],
                area["relative_change_ratio"],
                area["status"],
                ";".join(area["reasons"]),
            ]
            writer.writerow(
                [
                    "'" + v
                    if index in {0, 1, 6, 7}
                    and isinstance(v, str)
                    and v.lstrip().startswith(("=", "+", "-", "@"))
                    else v
                    for index, v in enumerate(values)
                ]
            )
    return buf.getvalue().encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s1", type=Path, required=True)
    parser.add_argument("--declarations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    declarations = cycle._read(args.declarations)
    if declarations.get("data_class") != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("SYNTHETIC_ONLY")
    s1 = cycle._read(args.s1)
    result = prepare(s1, declarations)
    args.output.mkdir(mode=0o700)
    manifest = dict(
        schema_version="V0_21_S2_RUN_MANIFEST_R1",
        executed_at_utc=datetime.now(UTC).isoformat(),
        module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        s1_module_sha256=hashlib.sha256(Path(cycle.__file__).read_bytes()).hexdigest(),
        s1_file_sha256=hashlib.sha256(args.s1.read_bytes()).hexdigest(),
        declarations_file_sha256=hashlib.sha256(args.declarations.read_bytes()).hexdigest(),
        result_sha256=result["result_sha256"],
        synthetic_only=True,
        strict_pit_validated=False,
    )
    for name, payload in (
        ("structure-scenarios.json", cycle.canonical(result) + b"\n"),
        ("area-changes.csv", _csv(result)),
        ("manifest.json", cycle.canonical(manifest) + b"\n"),
    ):
        target = args.output / name
        with target.open("xb") as handle:
            handle.write(payload)
        target.chmod(0o600)
    print(
        cycle.canonical(
            dict(
                result_sha256=result["result_sha256"],
                comparisons=len(result["comparisons"]),
                component_status_counts=_component_counts(result["comparisons"]),
                synthetic_only=True,
            )
        ).decode()
    )


if __name__ == "__main__":
    main()
