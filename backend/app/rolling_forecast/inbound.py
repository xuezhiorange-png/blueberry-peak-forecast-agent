"""Bounded read-only recorded-inbound snapshots, NOT an ERP/Excel importer.

The index contains identity/completeness only, never quantities. Date admission
precedes opening day payloads. Explicit immutable winner sets are supplied by a
source custodian; this adapter neither guesses mappings nor resolves revisions.
"""

import hashlib
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


def require_target(source: InboundSnapshot, pair: PreparedPair) -> None:
    """An enum name alone is not source-to-training-target equivalence evidence."""
    if (
        getattr(pair, "model_training_target_quantity_basis", None) != source.quantity_basis
        or source.target_binding is None
        or source.target_binding.fit_sha256 != pair.fit_sha256
    ):
        raise ValueError("SOURCE_BASIS_UNVERIFIED")
    if (
        getattr(pair, "model_provenance", None) == "SYNTHETIC_TEST_FIXTURE"
        and source.provenance != "SYNTHETIC_TEST_FIXTURE"
    ):
        raise ValueError("SOURCE_PROVENANCE_MISMATCH")


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


def load(
    context: Context,
    source: InboundSnapshot,
    origin: date,
    cutoff: datetime,
    start: date | None = None,
) -> list[Observation]:
    if context.calendar.season == "2026-2027" and source.provenance != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("CURRENT_SEASON_REAL_READ_NOT_AUTHORIZED")
    if (
        source.provenance == "SYNTHETIC_TEST_FIXTURE"
        and not source.source_system.upper().startswith("SYNTHETIC")
    ):
        raise ValueError("SOURCE_PROVENANCE_MISMATCH")
    path = Path(source.manifest_path)
    index = Index.model_validate_json(read(path, source.manifest_sha256, 2 * 1024 * 1024))
    if digest(index.model_dump(mode="json")) != source.snapshot_hash or (
        index.base_id,
        index.season,
        index.source_system,
    ) != (context.area.base_id, context.calendar.season, source.source_system):
        raise ValueError("OBSERVATION_SNAPSHOT_IDENTITY_MISMATCH")
    if (
        digest(index.physical_definition.model_dump(mode="json")) != source.physical_definition_hash
        or not index.physical_definition.verified()
    ):
        raise ValueError("SOURCE_BASIS_UNVERIFIED")
    first = context.calendar.start if start is None else start
    if not context.calendar.start <= first < origin <= context.calendar.end + timedelta(days=1):
        raise ValueError("SOURCE_DATE_SCOPE_MISMATCH")
    members = {digest(m.model_dump(mode="json")) for m in source.members}
    days = {d.business_date: d for d in index.days}
    result: list[Observation] = []
    logical_ids: set[str] = set()
    revision_ids: set[str] = set()
    for n in range((origin - first).days):
        target = first + timedelta(days=n)
        item = days.get(target)
        rows: tuple[Record, ...] = ()
        complete = False
        known_at = None
        coverage: tuple[Member, ...] = ()
        if item is not None:
            coverage = item.member_coverage
            covered = [digest(m.model_dump(mode="json")) for m in coverage]
            if len(set(covered)) != len(covered) or not set(covered) <= members:
                raise ValueError("SOURCE_MEMBER_COVERAGE_CONFLICT")
            # Crucially, no payload outside [first, origin) is opened.
            payload = Day.model_validate_json(
                read(path.parent / item.file, item.sha256, 16 * 1024 * 1024)
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
        total = Decimal(0)
        timestamps: list[datetime] = []
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            for record in rows:
                if record.logical_id in logical_ids or record.revision_id in revision_ids:
                    raise ValueError("DUPLICATE_SOURCE_RECORD")
                logical_ids.add(record.logical_id)
                revision_ids.add(record.revision_id)
                if digest(record.member.model_dump(mode="json")) not in members:
                    raise ValueError("SOURCE_MEMBER_MISMATCH")
                if record.grade not in (*index.accepted_grades, *index.excluded_grades):
                    raise ValueError("SOURCE_GRADE_UNVERIFIED")
                times = (record.source_recorded_at, record.server_ingested_at)
                if record.available_at_authority != "TRUSTED_SOURCE_TIMESTAMP" or any(
                    t is None or t > cutoff for t in times
                ):
                    complete = False
                timestamps.extend(t for t in times if t is not None)
                if record.grade in index.accepted_grades:
                    total += record.quantity_kg
        zero = target in source.confirmed_zero_dates
        if zero and total != 0:
            raise ValueError("AUTHORIZED_ZERO_CONFLICT")
        complete = complete and (bool(rows) or zero)
        latest = max([*timestamps, known_at] if known_at else timestamps, default=None)
        result.append(
            InboundObservation(
                base_id=context.area.base_id,
                season=context.calendar.season,
                business_date=target,
                quantity_kg=total if complete else None,
                record_state=("CONFIRMED_ZERO" if zero else "VALID_OBSERVED")
                if complete
                else "UNKNOWN",
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
        )
    return result
