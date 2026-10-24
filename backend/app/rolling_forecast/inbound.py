"""Bounded read-only recorded-inbound snapshots, NOT an ERP/Excel importer.

The index contains identity/completeness only, never quantities. Date admission
precedes opening day payloads. Explicit immutable winner sets are supplied by a
source custodian; this adapter neither guesses mappings nor resolves revisions.
"""

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from backend.app.rolling_forecast.policy import Context, InboundSnapshot, Member
from backend.app.rolling_forecast.schemas import Contract, Hash, Name, Observation
from backend.research.v019_origin_models import PreparedPair
from backend.research.v019_synthetic_validation import digest


class PhysicalDefinition(Contract):
    event: str
    measure: str
    business_date_rule: str
    unit: str
    tare_or_field_conversion: str
    proof_hash: Hash

    def verified(self) -> bool:
        return (
            self.event,
            self.measure,
            self.business_date_rule,
            self.unit,
            self.tare_or_field_conversion,
        ) == (
            "INBOUND_RECEIPT",
            "RECORDED_WEIGHT_AS_RECORDED",
            "INBOUND_EVENT_LOCAL_DATE",
            "kg",
            "NONE",
        )


class DayReference(Contract):
    business_date: date
    file: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,180}\.json$")
    sha256: Hash
    member_coverage: tuple[Member, ...]
    completeness_status: Literal["COMPLETE", "PARTIAL", "UNKNOWN"]
    known_at: datetime | None


class Index(Contract):
    schema_version: Literal["CONTROLLED_RECORDED_INBOUND_V1"]
    base_id: Name
    season: Name
    source_system: Name
    physical_definition: PhysicalDefinition
    accepted_grades: tuple[Name, ...] = Field(min_length=1)
    excluded_grades: tuple[Name, ...]
    revision_rule: Literal["EXPLICIT_IMMUTABLE_WINNERS"]
    days: tuple[DayReference, ...] = Field(max_length=401)

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({d.business_date for d in self.days}) != len(self.days) or len(
            {d.file for d in self.days}
        ) != len(self.days):
            raise ValueError("DUPLICATE_SOURCE_DAY")
        if set(self.accepted_grades) & set(self.excluded_grades):
            raise ValueError("SOURCE_GRADE_CONFLICT")
        return self


class Record(Contract):
    logical_id: Name
    revision_id: Name
    member: Member
    grade: Name
    quantity_kg: Decimal = Field(ge=0, allow_inf_nan=False, decimal_places=6, max_digits=24)
    source_recorded_at: datetime | None
    server_ingested_at: datetime | None
    available_at_authority: Literal[
        "TRUSTED_SOURCE_TIMESTAMP", "MISSING", "USER_ASSERTED_UNVERIFIED", "CONFLICTING"
    ]

    @field_validator("quantity_kg", mode="before")
    @classmethod
    def decimal_string(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("KG_DECIMAL_STRING_REQUIRED")
        return value


class Day(Contract):
    base_id: Name
    season: Name
    business_date: date
    source_system: Name
    records: tuple[Record, ...] = Field(max_length=100000)


class InboundObservation(Observation):
    source_snapshot_hash: Hash
    member_coverage: tuple[Member, ...]
    completeness_status: Literal["COMPLETE", "INCOMPLETE"]
    known_at_or_available_at: datetime | None
    cutoff: datetime


def require_target_metadata(
    source: InboundSnapshot, target: str | None, fit_hash: str, provenance: str | None
) -> None:
    """Metadata admission only. Does not load/verify a model file or grant access."""
    if (
        target != source.quantity_basis
        or source.target_binding is None
        or source.target_binding.fit_sha256 != fit_hash
    ):
        raise ValueError("SOURCE_BASIS_UNVERIFIED")
    if provenance == "SYNTHETIC_TEST_FIXTURE" and source.provenance != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("SOURCE_PROVENANCE_MISMATCH")


def require_target(source: InboundSnapshot, pair: PreparedPair) -> None:
    """An enum name alone is not source-to-training-target equivalence evidence."""
    require_target_metadata(
        source,
        getattr(pair, "model_training_target_quantity_basis", None),
        pair.fit_sha256,
        getattr(pair, "model_provenance", None),
    )


def member_coverage(source: InboundSnapshot, item: DayReference) -> tuple[set[str], set[str]]:
    expected = {digest(m.model_dump(mode="json")) for m in source.members}
    covered = [digest(m.model_dump(mode="json")) for m in item.member_coverage]
    if len(set(covered)) != len(covered) or not set(covered) <= expected:
        raise ValueError("SOURCE_MEMBER_COVERAGE_CONFLICT")
    return expected, set(covered)


def read(path: Path, sha: str, limit: int) -> bytes:
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("SOURCE_PATH_UNSAFE")
    try:
        if not path.is_file() or path.stat().st_size > limit or path.stat().st_mode & 0o022:
            raise ValueError("SOURCE_PATH_UNSAFE")
        raw = path.read_bytes()
    except OSError:
        raise ValueError("SOURCE_OBJECT_UNAVAILABLE") from None
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError("SOURCE_SNAPSHOT_HASH_MISMATCH")
    return raw


def _guard_source(context: Context, source: InboundSnapshot) -> None:
    if context.calendar.season == "2026-2027" and source.provenance != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("CURRENT_SEASON_REAL_READ_NOT_AUTHORIZED")
    if (
        source.provenance == "SYNTHETIC_TEST_FIXTURE"
        and not source.source_system.upper().startswith("SYNTHETIC")
    ):
        raise ValueError("SOURCE_PROVENANCE_MISMATCH")


def read_index(context: Context, source: InboundSnapshot) -> Index:
    """Quantity-free identity validation, also usable for offline metadata review."""
    path = Path(source.manifest_path)
    index = Index.model_validate_json(read(path, source.manifest_sha256, 2 * 1024 * 1024))
    if digest(index.model_dump(mode="json")) != source.snapshot_hash or (
        index.base_id,
        index.season,
        index.source_system,
    ) != (context.area.base_id, context.calendar.season, source.source_system):
        raise ValueError("OBSERVATION_SNAPSHOT_IDENTITY_MISMATCH")
    if digest(index.physical_definition.model_dump(mode="json")) != source.physical_definition_hash:
        raise ValueError("SOURCE_BASIS_UNVERIFIED")
    return index


class DuplicateSourceRecord(ValueError):
    def __init__(self, days: tuple[date, ...]):
        super().__init__("DUPLICATE_SOURCE_RECORD")
        self.days = days


@dataclass(frozen=True)
class DayInspection:
    """Internal diagnostic: quantities/exceptions are never serialized into S9 reports."""

    business_date: date
    observation: Observation | None
    reasons: tuple[str, ...]
    record_count: int | None
    excluded_record_count: int | None
    error: ValueError | OSError | None = None
    conflict_dates: tuple[date, ...] = ()
    payload_read: bool = False


def _one_day(
    context: Context,
    source: InboundSnapshot,
    index: Index,
    item: DayReference | None,
    target: date,
    cutoff: datetime,
    logical_ids: dict[str, date],
    revision_ids: dict[str, date],
) -> DayInspection:
    members = {digest(m.model_dump(mode="json")) for m in source.members}
    rows: tuple[Record, ...] = ()
    complete = False
    known_at = None
    coverage: tuple[Member, ...] = ()
    reasons: set[str] = set()
    if item is not None:
        coverage = item.member_coverage
        _, covered = member_coverage(source, item)
        payload = Day.model_validate_json(
            read(Path(source.manifest_path).parent / item.file, item.sha256, 16 * 1024 * 1024)
        )
        if (payload.base_id, payload.season, payload.business_date, payload.source_system) != (
            context.area.base_id,
            context.calendar.season,
            target,
            source.source_system,
        ):
            raise ValueError("SOURCE_DAY_IDENTITY_MISMATCH")
        rows = payload.records
        known_at = item.known_at
        complete = (
            item.completeness_status == "COMPLETE"
            and set(covered) == members
            and target in source.complete_dates
            and known_at is not None
            and known_at <= cutoff
            and source.completeness_known_at <= cutoff
        )
        if set(covered) != members:
            reasons.add("PARTIAL_MEMBER_COVERAGE")
        if item.completeness_status != "COMPLETE":
            reasons.add("SOURCE_COMPLETENESS_" + item.completeness_status)
        if target not in source.complete_dates:
            reasons.add("NO_COMPLETENESS_AUTHORITY_FOR_DAY")
        if known_at is None:
            reasons.add("DAY_TIME_AUTHORITY_MISSING")
        elif known_at > cutoff:
            reasons.add("LATE_COMPLETENESS_AUTHORITY")
    else:
        reasons.add("MISSING_DAY_INDEX")
    if source.completeness_known_at > cutoff:
        reasons.add("SOURCE_COMPLETENESS_AFTER_CUTOFF")
    total = Decimal(0)
    timestamps: list[datetime] = []
    excluded = 0
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        for record in rows:
            if record.logical_id in logical_ids or record.revision_id in revision_ids:
                other = logical_ids.get(
                    record.logical_id, revision_ids.get(record.revision_id, target)
                )
                raise DuplicateSourceRecord(tuple(sorted({other, target})))
            logical_ids[record.logical_id] = target
            revision_ids[record.revision_id] = target
            if digest(record.member.model_dump(mode="json")) not in members:
                raise ValueError("SOURCE_MEMBER_MISMATCH")
            if record.grade not in (*index.accepted_grades, *index.excluded_grades):
                raise ValueError("SOURCE_GRADE_UNVERIFIED")
            times = (record.source_recorded_at, record.server_ingested_at)
            if record.available_at_authority != "TRUSTED_SOURCE_TIMESTAMP":
                reasons.add("SOURCE_TIME_UNVERIFIED")
            if any(t is None for t in times):
                reasons.add("SOURCE_TIMESTAMP_MISSING")
            if any(t is not None and t > cutoff for t in times):
                reasons.add("LATE_SOURCE_RECORD")
            if record.available_at_authority != "TRUSTED_SOURCE_TIMESTAMP" or any(
                t is None or t > cutoff for t in times
            ):
                complete = False
            timestamps.extend(t for t in times if t is not None)
            if record.grade in index.accepted_grades:
                total += record.quantity_kg
            else:
                excluded += 1
    zero = target in source.confirmed_zero_dates
    if zero and total != 0:
        raise ValueError("AUTHORIZED_ZERO_CONFLICT")
    if not rows and not zero:
        reasons.add("NO_RECORD_WITHOUT_ZERO_AUTHORITY")
    complete = complete and (bool(rows) or zero)
    latest = max([*timestamps, known_at] if known_at else timestamps, default=None)
    observation = InboundObservation(
        base_id=context.area.base_id,
        season=context.calendar.season,
        business_date=target,
        quantity_kg=total if complete else None,
        record_state=("CONFIRMED_ZERO" if zero else "VALID_OBSERVED") if complete else "UNKNOWN",
        quantity_basis=source.quantity_basis,
        source_system=source.source_system,
        source_identity=f"{source.reference}:{target}",
        source_hash=item.sha256 if item else source.snapshot_hash,
        source_recorded_at=latest,
        server_ingested_at=latest,
        available_at_authority="TRUSTED_SOURCE_TIMESTAMP" if complete else "MISSING",
        observation_completeness="COMPLETE" if complete else "INCOMPLETE",
        source_snapshot_hash=source.snapshot_hash,
        member_coverage=coverage,
        completeness_status="COMPLETE" if complete else "INCOMPLETE",
        known_at_or_available_at=latest,
        cutoff=cutoff,
    )
    return DayInspection(
        target,
        observation,
        tuple(sorted(reasons)),
        len(rows),
        excluded,
        payload_read=item is not None,
    )


def inspect_days(
    context: Context,
    source: InboundSnapshot,
    origin: date,
    cutoff: datetime,
    start: date | None = None,
) -> Iterator[DayInspection]:
    """One shared parser. Runtime fails fast; offline S9 can retain all bad dates."""
    _guard_source(context, source)
    index = read_index(context, source)
    if not index.physical_definition.verified():
        raise ValueError("SOURCE_BASIS_UNVERIFIED")
    first = context.calendar.start if start is None else start
    if not context.calendar.start <= first < origin <= context.calendar.end + timedelta(days=1):
        raise ValueError("SOURCE_DATE_SCOPE_MISMATCH")
    days = {d.business_date: d for d in index.days}
    logical_ids: dict[str, date] = {}
    revision_ids: dict[str, date] = {}
    for n in range((origin - first).days):
        target = first + timedelta(days=n)
        item = days.get(target)
        try:
            yield _one_day(context, source, index, item, target, cutoff, logical_ids, revision_ids)
        except (ValueError, OSError) as exc:
            text = str(exc)
            code = (
                text
                if re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", text)
                else "SOURCE_RECORD_SCHEMA_INVALID"
            )
            yield DayInspection(
                target,
                None,
                (code,),
                None,
                None,
                error=exc,
                conflict_dates=getattr(exc, "days", (target,)),
                payload_read=item is not None
                and code
                not in {
                    "SOURCE_PATH_UNSAFE",
                    "SOURCE_OBJECT_UNAVAILABLE",
                    "SOURCE_MEMBER_COVERAGE_CONFLICT",
                },
            )


def load(
    context: Context,
    source: InboundSnapshot,
    origin: date,
    cutoff: datetime,
    start: date | None = None,
) -> list[Observation]:
    result: list[Observation] = []
    for checked in inspect_days(context, source, origin, cutoff, start):
        if checked.error is not None:
            raise checked.error
        assert checked.observation is not None
        result.append(checked.observation)
    return result
