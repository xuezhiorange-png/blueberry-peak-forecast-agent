"""V0_21 S1 synthetic production-cycle preparation. No source discovery or model.

Pure ``prepare`` consumes a normalized V020 package and explicit synthetic
relationships/clock witnesses. Full audit identity and as-of feature identity
are deliberately separate: future source changes alter audit identity, never
past feature values. No witness establishes real authority or strict PIT.
"""

from __future__ import annotations

import argparse
import calendar
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field

from backend.app.pit.visibility import as_utc, record_visible_at

VOCABULARY_SHA256 = "7a262081df5710b64c29cfbce63cd84a9dc67d5223726fbaa74007fc314c6d7d"
SCOPE_KEYS = ("base", "farm", "subfarm", "plot", "variety", "season", "production_system")
UNKNOWN = {"", "UNKNOWN", "UNMAPPED", "UNBOUND", "N/A", "NULL", "NONE", "-", "未知", "未映射"}
SYSTEMS = {"DECIDUOUS_NATURAL", "DECIDUOUS_FORCING", "EVERGREEN"}
METHOD_UNKNOWN = UNKNOWN | {"UNSPECIFIED", "NA", "不明", "不详", "未提供", "待确认"}
ENVELOPE = {"package_id", "preparation_sha256", "artifact_sha256"}
MAX_BYTES = 16 * 1024 * 1024


def canonical(value: Any) -> bytes:
    """V020-compatible JSON: UTF-16 key order, UTF-8 text, finite JSON scalars."""

    def ordered(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: ordered(v[k]) for k in sorted(v, key=lambda s: s.encode("utf-16-be"))}
        if isinstance(v, list):
            return [ordered(x) for x in v]
        if isinstance(v, float):
            raise ValueError("NON_INTEGER_JSON_NUMBER")
        return v

    return json.dumps(
        ordered(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DateToken(Contract):
    raw: str
    precision: Literal["DAY", "MONTH", "YEAR", "TIMESTAMP", "LOCAL_DATETIME", "UNKNOWN"]
    lower_date: str | None
    upper_date: str | None
    instant: str | None


class ClockEvidence(Contract):
    provenance: Literal["SYNTHETIC_EXPLICIT_CLOCKS"]
    observed_at: str | None
    recorded_at: str | None
    known_at: str | None
    evidence_reference: str


class RecordClock(ClockEvidence):
    record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Scope(Contract):
    base: str
    farm: str
    subfarm: str
    plot: str
    variety: str
    season: str
    production_system: str


class IntervalLink(Contract):
    interval_id: str
    start_record_id: str
    end_record_id: str


class Member(Contract):
    member_id: str = Field(min_length=1)
    cycle_id: str
    scope: Scope
    provenance: Literal["SYNTHETIC_EXPLICIT_RELATIONSHIP"]
    known_at: str | None
    evidence_reference: str
    primary_pruning: list[str]
    intervals: list[IntervalLink]


class Cycle(Contract):
    cycle_id: str = Field(min_length=1)
    base: str
    season: str
    start: DateToken
    clocks: ClockEvidence


class Origin(Contract):
    origin_id: str = Field(min_length=1)
    base: str
    season: str
    origin_date: date
    timezone: str
    cutoff: datetime


class Declarations(Contract):
    schema_version: Literal["V0_21_S1_DECLARATIONS_R1"]
    data_class: Literal["SYNTHETIC_TEST_FIXTURE"]
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    members: list[Member]
    cycles: list[Cycle]
    origins: list[Origin]
    record_clocks: dict[str, RecordClock]


def _aware(raw: str | None) -> datetime:
    if not raw:
        raise ValueError("CLOCK_NOT_PROVEN")
    try:
        return as_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError("CLOCK_NOT_PROVEN") from exc


def _bounds(token: DateToken, zone: ZoneInfo) -> tuple[date, date]:
    if token.precision == "UNKNOWN" or not token.lower_date or not token.upper_date:
        raise ValueError("DATE_MISSING")
    lo, hi = date.fromisoformat(token.lower_date), date.fromisoformat(token.upper_date)
    if lo > hi:
        raise ValueError("DATE_INTERVAL_REVERSED")
    if token.precision == "LOCAL_DATETIME":
        raise ValueError("LOCAL_TIMEZONE_NOT_PROVEN")
    if token.precision == "TIMESTAMP":
        day = _aware(token.instant).astimezone(zone).date()
        return day, day
    if token.instant is not None:
        raise ValueError("DATE_PRECISION_CONFLICT")
    if token.precision == "DAY" and lo != hi:
        raise ValueError("DATE_PRECISION_CONFLICT")
    if token.precision == "MONTH" and (
        lo.day != 1 or hi != date(lo.year, lo.month, calendar.monthrange(lo.year, lo.month)[1])
    ):
        raise ValueError("DATE_PRECISION_CONFLICT")
    if token.precision == "YEAR" and (lo != date(lo.year, 1, 1) or hi != date(lo.year, 12, 31)):
        raise ValueError("DATE_PRECISION_CONFLICT")
    return lo, hi


def _empty(reason: str) -> dict[str, Any]:
    return dict(
        status="NOT_COMPUTABLE", value=None, lower_days=None, upper_days=None, reason=reason
    )


def _range(lo: int, hi: int) -> dict[str, Any]:
    return dict(
        status="EXACT" if lo == hi else "INTERVAL",
        value=lo if lo == hi else None,
        lower_days=lo,
        upper_days=hi,
        reason=None,
    )


def _elapsed(bounds: tuple[date, date], origin: date) -> dict[str, Any]:
    return _range((origin - bounds[1]).days, (origin - bounds[0]).days)


def _clock_reason(
    proof: ClockEvidence | None,
    origin: Origin,
    *,
    planned: bool = False,
    raw: dict[str, Any] | None = None,
    business: tuple[date, date] | None = None,
) -> str | None:
    if proof is None or proof.evidence_reference.strip().upper() in METHOD_UNKNOWN:
        return "CLOCK_EVIDENCE_MISSING"
    try:
        recorded, known = _aware(proof.recorded_at), _aware(proof.known_at)
        observed = None if planned else _aware(proof.observed_at)
        if planned and proof.observed_at is not None:
            return "PLANNED_OBSERVED_CONFLICT"
        if recorded > known or (observed is not None and observed > recorded):
            return "CLOCK_ORDER_CONFLICT"
        if any(t > origin.cutoff for t in (recorded, known, observed) if t is not None):
            return "NOT_VISIBLE_AT_CUTOFF"
        zone = ZoneInfo(origin.timezone)
        if (
            observed is not None
            and business is not None
            and observed.astimezone(zone).date() < business[0]
        ):
            return "OBSERVATION_BEFORE_BUSINESS_EVENT"
        # Independent witnesses supplement, never overwrite, the original clocks.
        for key, value in (
            ("observed_at", observed),
            ("recorded_at", recorded),
            ("known_at", known),
        ):
            if raw is None or key not in raw:
                continue
            token = DateToken.model_validate(raw[key])
            if token.precision == "UNKNOWN":
                continue
            if value is None:
                return "CLOCK_SOURCE_CONFLICT"
            if token.precision == "TIMESTAMP":
                if _aware(token.instant) != value:
                    return "CLOCK_SOURCE_CONFLICT"
            else:
                lo, hi = _bounds(token, zone)
                if not lo <= value.astimezone(zone).date() <= hi:
                    return "CLOCK_SOURCE_CONFLICT"
    except ValueError:
        return "CLOCK_NOT_PROVEN"
    if not record_visible_at(SimpleNamespace(known_at=known), origin.cutoff):
        return "NOT_VISIBLE_AT_CUTOFF"
    return None


def _scope(record: dict[str, Any]) -> tuple[str, ...]:
    return tuple(record.get("scope", {}).get(k, "") for k in SCOPE_KEYS)


def _complete(scope: tuple[str, ...]) -> bool:
    return (
        all(isinstance(v, str) and v.strip().upper() not in UNKNOWN for v in scope)
        and scope[-1] in SYSTEMS
        and re.fullmatch(r"\d{4}-\d{4}", scope[5]) is not None
        and int(scope[5][5:]) == int(scope[5][:4]) + 1
    )


def _family(record: dict[str, Any]) -> tuple[str, ...]:
    return (
        *_scope(record),
        record["kind"],
        record.get("source_reference") or "",
        record.get("logical_id") or record["record_id"],
        (record.get("slot") or {}).get("id", ""),
    )


def _semantic(record: dict[str, Any], vocabulary: dict[str, Any]) -> str:
    if record["observed_or_planned"] == "UNKNOWN":
        raise ValueError("EVENT_STATE_UNKNOWN")
    if any(i["severity"] == "ERROR" for i in record["issues"]):
        raise ValueError("UPSTREAM_CONFLICT")
    if record["kind"] == "EVENT":
        event = record["event"]
        codes = {e["code"]: e for e in vocabulary["event_types"]}
        code = event.get("canonical_type")
        if re.search(r"促早|催早|^FORCING$", event["raw_type"], re.I) and (
            str(event.get("method") or "").strip().upper() in METHOD_UNKNOWN
        ):
            raise ValueError("FORCING_METHOD_UNRESOLVED")
        if code not in codes:
            raise ValueError("EVENT_TYPE_UNMAPPED")
        if record["scope"]["production_system"] not in codes[code]["applicable_systems"]:
            raise ValueError("EVENT_SYSTEM_CONFLICT")
        if any(i["code"] == "FORCING_METHOD_UNRESOLVED" for i in record["issues"]):
            raise ValueError("FORCING_METHOD_UNRESOLVED")
        if (
            "促早" in event["raw_type"]
            and str(event.get("method") or "").strip().upper() in UNKNOWN
        ):
            raise ValueError("FORCING_METHOD_UNRESOLVED")
        return "EVENT:" + str(code)
    if record["kind"] == "PHENOLOGY":
        phase = record["phenology"]
        ordinary, percent = phase.get("production_plan_field"), phase.get("canonical_stage")
        if ordinary and percent:
            raise ValueError("PHENOLOGY_CLASSIFICATION_CONFLICT")
        if not all(
            str(phase.get(k) or "").strip().upper() not in METHOD_UNKNOWN
            for k in ("method", "sample_scope", "quality_status")
        ):
            raise ValueError("PHENOLOGY_METHOD_NOT_PROVEN")
        if ordinary in {"flowering_start_date", "flowering_peak_date", "flowering_end_date"}:
            return "GENERIC_BLOOM:" + str(ordinary)
        if percent in {"BLOOM_10", "BLOOM_50", "BLOOM_90"}:
            if phase.get("raw_stage") in {"开花开始", "盛花", "开花结束"}:
                raise ValueError("PHENOLOGY_CLASSIFICATION_CONFLICT")
            return "PERCENT_BLOOM:" + str(percent)
    raise ValueError("OUTSIDE_S1_FEATURE_SCOPE")


def _time_reason(
    record: dict[str, Any], proof: RecordClock | None, origin: Origin
) -> tuple[str | None, tuple[date, date] | None]:
    if record["kind"] not in {"EVENT", "PHENOLOGY"}:
        return "OUTSIDE_S1_FEATURE_SCOPE", None
    state = record["observed_or_planned"]
    if state not in {"OBSERVED", "PLANNED", "UNKNOWN"}:
        return "EVENT_STATE_UNKNOWN", None
    try:
        bounds = _bounds(
            DateToken.model_validate(record["business_date"]), ZoneInfo(origin.timezone)
        )
        end = (record.get("event") or {}).get("end_date")
        upper = bounds[1]
        if end and end["raw"]:
            elo, ehi = _bounds(DateToken.model_validate(end), ZoneInfo(origin.timezone))
            if elo < bounds[1]:
                return "EVENT_INTERVAL_ORDER_UNPROVEN", bounds
            upper = ehi
        if state == "OBSERVED" and upper >= origin.origin_date:
            return "FUTURE_OR_ORIGIN_DAY_FACT", bounds
        if any(
            str(record.get(k) or "").strip().upper() in METHOD_UNKNOWN
            for k in ("source_reference", "source_version")
        ):
            return "SOURCE_IDENTITY_NOT_PROVEN", bounds
        return _clock_reason(
            proof,
            origin,
            planned=state == "PLANNED"
            or (state == "UNKNOWN" and proof is not None and proof.observed_at is None),
            raw=record,
            business=bounds,
        ), bounds
    except ValueError:
        return "DATE_NOT_COMPUTABLE", None


def _heads(records: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    if not all(r.get("logical_id") and r.get("revision_id") for r in records):
        return None, "REVISION_IDENTITY_NOT_PROVEN"
    by_revision = {r["revision_id"]: r for r in records}
    if len(by_revision) != len(records):
        return None, "DUPLICATE_VISIBLE_REVISION"
    parents = {r["supersedes_revision"] for r in records if r["supersedes_revision"]}
    if not parents <= by_revision.keys():
        return None, "REVISION_PREDECESSOR_NOT_VISIBLE"
    for start in by_revision:
        seen: set[str] = set()
        cursor = start
        while cursor:
            if cursor in seen:
                return None, "REVISION_CYCLE"
            seen.add(cursor)
            cursor = by_revision[cursor]["supersedes_revision"]
    heads = [r for key, r in by_revision.items() if key not in parents]
    if len(heads) != 1:
        return None, "REVISION_FORK"
    return heads[0], None


def _validate(package: dict[str, Any], declaration: dict[str, Any]) -> Declarations:
    if (
        package.get("data_class") != "SYNTHETIC_TEST_FIXTURE"
        or declaration.get("data_class") != "SYNTHETIC_TEST_FIXTURE"
    ):
        raise ValueError("SYNTHETIC_ONLY")
    request = Declarations.model_validate(declaration)
    if (
        package.get("schema_version") != "V0_20_AGRONOMIC_PREPARATION_R1"
        or package.get("version") != "0.20.0"
    ):
        raise ValueError("V020_SCHEMA_MISMATCH")
    core = {k: v for k, v in package.items() if k not in ENVELOPE}
    expected_core = {
        "schema_version",
        "version",
        "data_class",
        "source_file_sha256",
        "mapping_sha256",
        "vocabulary_sha256",
        "upstream",
        "plans",
        "source_rows",
        "records",
        "summary",
        "restrictions",
    }
    if core.keys() != expected_core:
        raise ValueError("V020_PACKAGE_SCHEMA_MISMATCH")
    computed = digest(core)
    if (
        request.package_sha256 != computed
        or package.get("preparation_sha256", computed) != computed
        or package.get("package_id", "V0_20-" + computed) != "V0_20-" + computed
    ):
        raise ValueError("PACKAGE_HASH_MISMATCH")
    if (
        digest(package["upstream"]) != VOCABULARY_SHA256
        or package["vocabulary_sha256"] != VOCABULARY_SHA256
    ):
        raise ValueError("FROZEN_VOCABULARY_MISMATCH")
    if digest(package["plans"]) != package["mapping_sha256"]:
        raise ValueError("MAPPING_HASH_MISMATCH")
    if len(package["source_file_sha256"]) != 64 or any(
        v is not False for v in package["restrictions"].values()
    ):
        raise ValueError("UPSTREAM_AUTHORITY_NOT_A_GRANT")
    if re.fullmatch(r"[0-9a-f]{64}", package["source_file_sha256"]) is None:
        raise ValueError("SOURCE_HASH_FORMAT_INVALID")
    records = package["records"]
    required = {
        "record_id",
        "kind",
        "source_row_id",
        "scope",
        "business_date",
        "observed_or_planned",
        "recorded_at",
        "known_at",
        "observed_at",
        "source_reference",
        "source_version",
        "logical_id",
        "revision_id",
        "supersedes_revision",
        "event",
        "phenology",
        "area",
        "issues",
        "states",
        "slot",
    }
    if not all(isinstance(r, dict) and required <= r.keys() for r in records):
        raise ValueError("V020_RECORD_SCHEMA_MISMATCH")
    restrictions = {
        "source_authority_proven",
        "strict_pit_validated",
        "model_use_authorized",
        "prediction_adjustment_authorized",
        "production_database_writes",
        "real_data_verified",
        "formal_version_complete",
    }
    if (
        set(package["restrictions"]) != restrictions
        or package["summary"]["research_admitted_count"] != 0
    ):
        raise ValueError("UPSTREAM_AUTHORITY_NOT_A_GRANT")
    if len(request.members) > 4096 or len(request.origins) > 256:
        raise ValueError("DECLARATION_SIZE_LIMIT")
    if len(records) > 20000 or len(canonical(package)) > MAX_BYTES:
        raise ValueError("PACKAGE_SIZE_LIMIT")
    record_ids = [r["record_id"] for r in records]
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("DUPLICATE_RECORD_ID")
    for key, field in (
        ("member_id", request.members),
        ("cycle_id", request.cycles),
        ("origin_id", request.origins),
    ):
        ids = [getattr(item, key) for item in field]
        if len(set(ids)) != len(ids):
            raise ValueError("DUPLICATE_DECLARATION_ID")
    if not request.record_clocks.keys() <= set(record_ids):
        raise ValueError("UNKNOWN_RECORD_PROOF")
    for record in records:
        proof = request.record_clocks.get(record["record_id"])
        if proof and proof.record_sha256 != digest(record):
            raise ValueError("RECORD_PROOF_HASH_MISMATCH")
    for member in request.members:
        ids = [p.interval_id for p in member.intervals]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_STAGE_INTERVAL_ID")
    for origin in request.origins:
        try:
            zone = ZoneInfo(origin.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("ORIGIN_TIMEZONE_UNKNOWN") from exc
        if (
            origin.cutoff.tzinfo is None
            or origin.cutoff.astimezone(zone).date() != origin.origin_date
        ):
            raise ValueError("ORIGIN_CUTOFF_TIMEZONE_MISMATCH")
    return request


def _snapshot(
    member: Member,
    cycle: Cycle | None,
    origin: Origin,
    records: list[dict[str, Any]],
    request: Declarations,
    package: dict[str, Any],
    mapping_reason: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    def empty(reason: str) -> dict[str, Any]:
        return {
            "days_since_cycle_start": _empty(reason),
            "days_since_primary_pruning": _empty(reason),
            "days_since_eligible_observed_event": [],
            "completed_stage_intervals": [],
        }

    features = empty("NOT_COMPUTABLE")
    planned: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    consumed: list[dict[str, Any]] = []
    if mapping_reason is None:
        try:
            if (
                member.evidence_reference.strip().upper() in METHOD_UNKNOWN
                or _aware(member.known_at) > origin.cutoff
            ):
                mapping_reason = "MEMBER_RELATION_NOT_VISIBLE"
        except ValueError:
            mapping_reason = "MEMBER_RELATION_TIME_NOT_PROVEN"
    if mapping_reason is None and cycle is not None:
        try:
            cycle_business = _bounds(cycle.start, ZoneInfo(origin.timezone))
        except ValueError:
            cycle_business = None
        mapping_reason = _clock_reason(cycle.clocks, origin, business=cycle_business)
    if mapping_reason:
        features = empty(mapping_reason)
    else:
        assert cycle is not None
        try:
            cb = _bounds(cycle.start, ZoneInfo(origin.timezone))
            features["days_since_cycle_start"] = (
                _elapsed(cb, origin.origin_date)
                if cb[1] < origin.origin_date
                else _empty("CYCLE_START_NOT_PRIOR")
            )
        except ValueError:
            features["days_since_cycle_start"] = _empty("CYCLE_START_MISSING_OR_AMBIGUOUS")
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        times, bounds_by_id = {}, {}
        for r in records:
            rid = r["record_id"]
            reason, bounds = _time_reason(r, request.record_clocks.get(rid), origin)
            times[rid], bounds_by_id[rid] = reason, bounds
            decisions.append(
                dict(
                    record_id=rid,
                    origin_id=origin.origin_id,
                    member_id=member.member_id,
                    reason=reason,
                )
            )
            groups[_family(r)].append(r)
        active, failures = {}, {}
        for family, group in groups.items():
            visible = [r for r in group if times[r["record_id"]] is None]
            uncertain = [
                r
                for r in group
                if times[r["record_id"]]
                not in {
                    None,
                    "NOT_VISIBLE_AT_CUTOFF",
                    "FUTURE_OR_ORIGIN_DAY_FACT",
                    "OUTSIDE_S1_FEATURE_SCOPE",
                }
            ]
            if uncertain:
                failures[family] = "REVISION_VISIBILITY_NOT_PROVEN"
                continue
            if not visible:
                failures[family] = "NO_ELIGIBLE_OBSERVED_RECORD"
                continue
            states = {r["observed_or_planned"] for r in visible}
            if len(states) != 1:
                failures[family] = "PLANNED_OBSERVED_REVISION_CONFLICT"
                continue
            head, reason = _heads(visible)
            if reason or head is None:
                failures[family] = reason or "REVISION_NOT_COMPUTABLE"
                continue
            try:
                semantic = _semantic(head, package["upstream"])
            except ValueError as exc:
                failures[family] = str(exc)
                continue
            hb = bounds_by_id[head["record_id"]]
            assert hb is not None
            fact = dict(fact_key=digest(list(family)), semantic_type=semantic)
            if head["observed_or_planned"] == "PLANNED":
                planned.append(
                    {
                        **fact,
                        "business_date": head["business_date"],
                        "status": "PLANNED_NOT_OBSERVED",
                    }
                )
            else:
                active[family] = (head, hb, semantic)
                features["days_since_eligible_observed_event"].append(
                    {**fact, "elapsed": _elapsed(hb, origin.origin_date)}
                )
            consumed.append(
                dict(record=head, clocks=request.record_clocks[head["record_id"]].model_dump())
            )
        by_id = {r["record_id"]: r for r in package["records"]}

        def resolve(rid: str) -> tuple[dict[str, Any], tuple[date, date], str]:
            record = by_id.get(rid)
            if record is None or _scope(record) != tuple(member.scope.model_dump().values()):
                raise ValueError("ANCHOR_MEMBER_SCOPE_MISMATCH")
            family = _family(record)
            if family in failures:
                raise ValueError(failures[family])
            if times.get(rid) is not None:
                raise ValueError("ANCHOR_REFERENCE_NOT_VISIBLE")
            if family not in active:
                raise ValueError("ANCHOR_NOT_OBSERVED")
            return active[family]

        try:
            if not member.primary_pruning:
                raise ValueError("PRIMARY_PRUNING_MISSING")
            if len(member.primary_pruning) != 1:
                raise ValueError("PRIMARY_PRUNING_AMBIGUOUS")
            anchor, rb, code = resolve(member.primary_pruning[0])
            registered = next(
                (e for e in package["upstream"]["event_types"] if "EVENT:" + e["code"] == code),
                None,
            )
            if registered is None or registered["family"] != "PRUNING":
                raise ValueError("PRIMARY_ANCHOR_NOT_PRUNING")
            features["days_since_primary_pruning"] = _elapsed(rb, origin.origin_date)
        except ValueError as exc:
            features["days_since_primary_pruning"] = _empty(str(exc))
        for interval in member.intervals:
            try:
                a, ab, _ = resolve(interval.start_record_id)
                b, bb, _ = resolve(interval.end_record_id)
                if a["record_id"] == b["record_id"]:
                    raise ValueError("SAME_EVENT_IS_NOT_STAGE_INTERVAL")
                lo, hi = (bb[0] - ab[1]).days, (bb[1] - ab[0]).days
                if lo < 0:
                    raise ValueError("STAGE_ORDER_REVERSED" if hi < 0 else "STAGE_ORDER_AMBIGUOUS")
                value = _range(lo, hi)
            except ValueError as exc:
                value = _empty(str(exc))
            features["completed_stage_intervals"].append(
                {"interval_id": interval.interval_id, **value}
            )
        for decision in decisions:
            if decision["reason"] is None:
                r = by_id[decision["record_id"]]
                family = _family(r)
                if family in failures:
                    decision["reason"] = failures[family]
                elif family in active and active[family][0]["record_id"] != r["record_id"]:
                    decision["reason"] = "SUPERSEDED_AS_OF_CUTOFF"
    features["days_since_eligible_observed_event"].sort(key=lambda r: r["fact_key"])
    features["completed_stage_intervals"].sort(key=lambda r: r["interval_id"])
    planned.sort(key=lambda r: r["fact_key"])
    scope = member.scope.model_dump()
    business = dict(
        scope=scope,
        origin_date=str(origin.origin_date),
        timezone=origin.timezone,
        cutoff=origin.cutoff.astimezone(UTC).isoformat(),
        features=features,
        planned_events=planned,
    )
    lineage = dict(
        package_sha256=request.package_sha256,
        member=member.model_dump(mode="json"),
        cycle=cycle.model_dump(mode="json") if cycle else None,
        consumed_records=sorted(consumed, key=lambda x: x["record"]["record_id"]),
    )
    return dict(
        origin_id=origin.origin_id,
        member_id=member.member_id,
        **business,
        status=(
            "UNMAPPED"
            if mapping_reason
            in {
                "UNMAPPED_IDENTITY",
                "AMBIGUOUS_MEMBER_RELATION",
                "CYCLE_MEMBER_SCOPE_MISMATCH",
                "AMBIGUOUS_PRIMARY_CYCLE",
            }
            else "NOT_COMPUTABLE"
        )
        if mapping_reason
        else "PREPARED",
        reason=mapping_reason,
        feature_sha256=digest(business),
        lineage_sha256=digest(lineage),
        lineage=lineage,
    ), decisions


def prepare(package: dict[str, Any], declarations: dict[str, Any]) -> dict[str, Any]:
    """Prepare synthetic cycles. Does not mutate inputs, open files or run models."""
    request = _validate(package, declarations)
    cycle_by_id = {c.cycle_id: c for c in request.cycles}
    cycle_counts = Counter((c.base, c.season) for c in request.cycles)
    member_counts = Counter(tuple(m.scope.model_dump().values()) for m in request.members)
    associations, snapshots, decisions = [], [], []
    mapping: dict[str, str | None] = {}
    members_by_scope: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for member in sorted(request.members, key=lambda m: m.member_id):
        scope = tuple(member.scope.model_dump().values())
        cycle = cycle_by_id.get(member.cycle_id)
        reason = None
        if not _complete(scope):
            reason = "UNMAPPED_IDENTITY"
        elif member_counts[scope] != 1:
            reason = "AMBIGUOUS_MEMBER_RELATION"
        elif cycle is None or (cycle.base, cycle.season) != (
            member.scope.base,
            member.scope.season,
        ):
            reason = "CYCLE_MEMBER_SCOPE_MISMATCH"
        elif cycle_counts[(cycle.base, cycle.season)] != 1:
            reason = "AMBIGUOUS_PRIMARY_CYCLE"
        mapping[member.member_id] = reason
        if reason is None:
            members_by_scope[scope].append(member.member_id)
        for origin in sorted(request.origins, key=lambda o: o.origin_id):
            if (origin.base, origin.season) != (member.scope.base, member.scope.season):
                continue
            records = [r for r in package["records"] if _scope(r) == scope]
            result, detail = _snapshot(member, cycle, origin, records, request, package, reason)
            snapshots.append(result)
            decisions.extend(detail)
    for cycle in sorted(request.cycles, key=lambda c: c.cycle_id):
        associations.append(
            dict(
                cycle=cycle.model_dump(mode="json"),
                status="DECLARED_SYNTHETIC_RELATION"
                if cycle_counts[(cycle.base, cycle.season)] == 1
                else "AMBIGUOUS_PRIMARY_CYCLE",
                members=[
                    dict(
                        member_id=m.member_id,
                        scope=m.scope.model_dump(),
                        reason=mapping[m.member_id],
                    )
                    for m in sorted(request.members, key=lambda m: m.member_id)
                    if m.cycle_id == cycle.cycle_id
                ],
            )
        )
    ledger = [
        dict(
            record_id=r["record_id"],
            raw_record=copy.deepcopy(r),
            member_ids=members_by_scope.get(_scope(r), []),
            reason=None if _scope(r) in members_by_scope else "UNMAPPED_RECORD",
        )
        for r in sorted(package["records"], key=lambda r: r["record_id"])
    ]
    body = dict(
        schema_version="V0_21_S1_CYCLE_FEATURES_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        strict_pit_validated=False,
        real_source_authority_proven=False,
        model_use_authorized=False,
        s2_s4_implemented=False,
        input_identity=dict(
            package_sha256=request.package_sha256,
            declarations_sha256=digest(declarations),
            source_file_sha256=package["source_file_sha256"],
            mapping_sha256=package["mapping_sha256"],
            vocabulary_sha256=package["vocabulary_sha256"],
        ),
        original_package=copy.deepcopy(package),
        original_declarations=copy.deepcopy(declarations),
        association_ledger=[
            dict(member_id=m.member_id, reason=mapping[m.member_id])
            for m in sorted(request.members, key=lambda m: m.member_id)
        ],
        origin_requests=[
            dict(
                origin_id=o.origin_id,
                reason=None
                if any(s["origin_id"] == o.origin_id for s in snapshots)
                else "NO_DECLARED_MEMBER",
            )
            for o in sorted(request.origins, key=lambda o: o.origin_id)
        ],
        cycle_associations=associations,
        origin_snapshots=snapshots,
        record_ledger=ledger,
        origin_decisions=sorted(
            decisions, key=lambda r: (r["origin_id"], r["member_id"], r["record_id"])
        ),
    )
    return {**body, "result_sha256": digest(body)}


def _read(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("EXPLICIT_INPUT_PATH_OR_SIZE_INVALID")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    value = json.loads(path.read_bytes(), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--declarations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    declaration = _read(args.declarations)
    if declaration.get("data_class") != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("SYNTHETIC_ONLY")
    package = _read(args.package)
    result = prepare(package, declaration)
    args.output.mkdir(mode=0o700)
    for name, value in (
        ("cycle-features.json", result),
        (
            "manifest.json",
            dict(
                schema_version="V0_21_S1_RUN_MANIFEST_R1",
                executed_at_utc=datetime.now(UTC).isoformat(),
                module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                package_file_sha256=hashlib.sha256(args.package.read_bytes()).hexdigest(),
                declarations_file_sha256=hashlib.sha256(args.declarations.read_bytes()).hexdigest(),
                result_sha256=result["result_sha256"],
                synthetic_only=True,
                strict_pit_validated=False,
            ),
        ),
    ):
        path = args.output / name
        with path.open("xb") as handle:
            handle.write(canonical(value) + b"\n")
        path.chmod(0o600)
    print(
        json.dumps(
            dict(
                result_sha256=result["result_sha256"],
                cycles=len(result["cycle_associations"]),
                snapshots=len(result["origin_snapshots"]),
                strict_pit_validated=False,
            )
        )
    )


if __name__ == "__main__":
    main()
