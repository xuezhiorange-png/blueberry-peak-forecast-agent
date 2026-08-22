"""SOURCE_ROW_IDENTITY construction and append-only lineage registration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

import xlrd
from sqlalchemy.orm import Session

from backend.app.rolling_backtest.canonical import canonical_json_dumps
from backend.app.s2_materialized_dataset.lane_a.hashes import (
    S2_CANONICAL_SERIALIZATION_PROFILE,
    compute_source_row_content_hash,
    compute_source_row_identity_hash,
)
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    derive_winner_selection_blocked,
    fetch_source_row_by_identity_and_content,
    fetch_source_rows_by_identity_hash,
    insert_source_row_lineage,
)
from backend.app.s2_materialized_dataset.lane_a.schemas import (
    SOURCE_002_DECLARED_ROW_COUNT,
    SOURCE_002_EXPECTED_HEADERS,
    SOURCE_002_IDFL_REVISION_ID,
    SOURCE_002_OBSERVED_SCHEMA_SHA256,
    SOURCE_002_ROW_EVIDENCE_IDENTITY_POLICY_VERSION,
    SOURCE_002_SCHEMA_VERSION,
    SOURCE_002_SNAPSHOT_REFERENCE,
    SOURCE_002_SOURCE_SYSTEM,
    SOURCE_002_SOURCE_VERSION,
    MissingExternalLogicalRecordIdError,
    Source002ParseError,
    SourceRowBusinessContent,
    SourceRowIdentity,
    SourceRowLineageInput,
    SourceRowRegistration,
    SourceRowRegistrationResult,
)


@dataclass(frozen=True, slots=True)
class Source002WorkbookEvidence:
    header_fields: tuple[str, ...]
    row_count: int
    sheet_count: int
    observed_schema_sha256: str


def _normalize_cell_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def compute_source_002_observed_schema_sha256(*, header_fields: tuple[str, ...]) -> str:
    payload = {
        "canonical_serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
        "policy_version": "v0-3-s2-source-002-observed-schema-hash-v1",
        "identity_kind": "OBSERVED_SOURCE_SCHEMA",
        "schema_version": SOURCE_002_SCHEMA_VERSION,
        "header_fields": list(header_fields),
    }
    return sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def _parse_header_row(sheet: xlrd.sheet.Sheet, header_row: int) -> tuple[str, ...]:
    values = tuple(
        _normalize_cell_text(sheet.cell_value(header_row, col_index)) or ""
        for col_index in range(sheet.ncols)
    )
    trimmed = tuple(value for value in values if value)
    if trimmed != SOURCE_002_EXPECTED_HEADERS:
        raise Source002ParseError("SOURCE_002 header row does not match the frozen schema")
    return trimmed


def _count_data_rows(sheet: xlrd.sheet.Sheet, *, header_row: int) -> int:
    count = 0
    for row_index in range(header_row + 1, sheet.nrows):
        if any(
            _normalize_cell_text(sheet.cell_value(row_index, col_index))
            for col_index in range(sheet.ncols)
        ):
            count += 1
    return count


def extract_source_002_workbook_evidence(artifact_bytes: bytes) -> Source002WorkbookEvidence:
    workbook = xlrd.open_workbook(file_contents=artifact_bytes)
    header_fields: tuple[str, ...] | None = None
    row_count = 0
    for sheet in workbook.sheets():
        header_row = 0
        for row_index in range(sheet.nrows):
            values = [
                _normalize_cell_text(sheet.cell_value(row_index, col_index))
                for col_index in range(sheet.ncols)
            ]
            if set(SOURCE_002_EXPECTED_HEADERS).issubset({value for value in values if value}):
                header_row = row_index
                break
        else:
            raise Source002ParseError("SOURCE_002 canonical header row was not found")
        sheet_headers = _parse_header_row(sheet, header_row)
        if header_fields is None:
            header_fields = sheet_headers
        elif header_fields != sheet_headers:
            raise Source002ParseError("SOURCE_002 sheet headers are inconsistent")
        row_count += _count_data_rows(sheet, header_row=header_row)
    if header_fields is None:
        raise Source002ParseError("SOURCE_002 workbook contains no readable sheets")
    return Source002WorkbookEvidence(
        header_fields=header_fields,
        row_count=row_count,
        sheet_count=workbook.nsheets,
        observed_schema_sha256=SOURCE_002_OBSERVED_SCHEMA_SHA256,
    )


def _parse_business_date(value: Any, *, datemode: int) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, float):
        try:
            return xlrd.xldate_as_datetime(value, datemode).date()
        except (ValueError, OverflowError) as exc:
            raise Source002ParseError("SOURCE_002 harvest date is invalid") from exc
    text = _normalize_cell_text(value)
    if text is None:
        raise Source002ParseError("SOURCE_002 harvest date is missing")
    return date.fromisoformat(text)


def _parse_weight_kg(value: Any) -> Decimal:
    if value is None or _normalize_cell_text(value) is None:
        raise Source002ParseError("SOURCE_002 weight is missing and must not be coerced to zero")
    if isinstance(value, Decimal):
        quantity = value
    else:
        text = _normalize_cell_text(value)
        if text is None:
            raise Source002ParseError(
                "SOURCE_002 weight is missing and must not be coerced to zero"
            )
        try:
            quantity = Decimal(text.replace(",", ""))
        except (InvalidOperation, ValueError) as exc:
            raise Source002ParseError("SOURCE_002 weight is not a valid decimal") from exc
    if not quantity.is_finite():
        raise Source002ParseError("SOURCE_002 weight must be finite")
    return quantity


def derive_source_002_external_logical_record_id(
    *,
    harvest_business_date: date,
    chain: str,
    farm: str,
    subfarm: str,
    variety: str,
    fruit_size: str,
) -> str:
    payload = {
        "canonical_serialization_profile": S2_CANONICAL_SERIALIZATION_PROFILE,
        "policy_version": SOURCE_002_ROW_EVIDENCE_IDENTITY_POLICY_VERSION,
        "source_system": SOURCE_002_SOURCE_SYSTEM,
        "source_snapshot_reference": SOURCE_002_SNAPSHOT_REFERENCE,
        "source_row_evidence_fields": {
            "harvest_business_date": harvest_business_date.isoformat(),
            "chain": chain,
            "farm": farm,
            "subfarm": subfarm,
            "variety": variety,
            "fruit_size": fruit_size,
        },
    }
    return sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def iter_source_002_row_inputs(
    artifact_bytes: bytes,
    *,
    source_column_mapping_snapshot_hash: str,
) -> tuple[SourceRowLineageInput, ...]:
    workbook = xlrd.open_workbook(file_contents=artifact_bytes)
    rows: list[SourceRowLineageInput] = []
    for sheet in workbook.sheets():
        header_row = 0
        header_map: dict[str, int] = {}
        for row_index in range(sheet.nrows):
            values = [
                _normalize_cell_text(sheet.cell_value(row_index, col_index))
                for col_index in range(sheet.ncols)
            ]
            if set(SOURCE_002_EXPECTED_HEADERS).issubset({value for value in values if value}):
                header_row = row_index
                header_fields = _parse_header_row(sheet, header_row)
                header_map = {name: header_fields.index(name) for name in header_fields}
                break
        else:
            raise Source002ParseError("SOURCE_002 canonical header row was not found")
        for row_index in range(header_row + 1, sheet.nrows):
            raw_values = [
                sheet.cell_value(row_index, col_index) for col_index in range(sheet.ncols)
            ]
            if not any(_normalize_cell_text(value) for value in raw_values):
                continue
            harvest_business_date = _parse_business_date(
                raw_values[header_map["时间"]],
                datemode=workbook.datemode,
            )
            chain = _normalize_cell_text(raw_values[header_map["链路"]])
            farm = _normalize_cell_text(raw_values[header_map["农场"]])
            subfarm = _normalize_cell_text(raw_values[header_map["分场"]])
            variety = _normalize_cell_text(raw_values[header_map["品种"]])
            fruit_size = _normalize_cell_text(raw_values[header_map["果径"]])
            if not all([chain, farm, subfarm, variety, fruit_size]):
                raise Source002ParseError("SOURCE_002 required source dimension is missing")
            quantity = _parse_weight_kg(raw_values[header_map["入库公斤数"]])
            logical_record_id = derive_source_002_external_logical_record_id(
                harvest_business_date=harvest_business_date,
                chain=chain,
                farm=farm,
                subfarm=subfarm,
                variety=variety,
                fruit_size=fruit_size,
            )
            rows.append(
                SourceRowLineageInput(
                    external_logical_record_id=logical_record_id,
                    external_revision_id=SOURCE_002_IDFL_REVISION_ID,
                    revision_number=1,
                    source_system=SOURCE_002_SOURCE_SYSTEM,
                    source_version=SOURCE_002_SOURCE_VERSION,
                    schema_version=SOURCE_002_SCHEMA_VERSION,
                    source_row_identity_version="v0-3-s2-source-row-identity-v1",
                    source_sheet_name=sheet.name,
                    source_row_number=row_index + 1,
                    source_column_mapping_snapshot_hash=source_column_mapping_snapshot_hash,
                    business_content=SourceRowBusinessContent(
                        harvest_business_date=harvest_business_date,
                        farm_code=farm,
                        subfarm_or_plot_code=subfarm,
                        variety_code=variety,
                        actual_harvest_quantity_kg=quantity,
                    ),
                )
            )
    if len(rows) != SOURCE_002_DECLARED_ROW_COUNT:
        raise Source002ParseError(
            "SOURCE_002 parsed row count does not match the frozen declaration"
        )
    return tuple(rows)


def _require_external_logical_record_id(row_input: SourceRowLineageInput) -> None:
    if not row_input.external_logical_record_id.strip():
        raise MissingExternalLogicalRecordIdError(
            "source row ingestion requires a stable external logical record identity"
        )


def build_source_row_identity(
    *,
    artifact_identity_hash: str,
    batch_identity_hash: str,
    row_input: SourceRowLineageInput,
) -> SourceRowIdentity:
    _require_external_logical_record_id(row_input)
    content_sha256 = compute_source_row_content_hash(business_content=row_input.business_content)
    source_row_identity_hash = compute_source_row_identity_hash(
        artifact_identity_hash=artifact_identity_hash,
        row_input=row_input,
    )
    return SourceRowIdentity(
        source_row_identity_hash=source_row_identity_hash,
        content_sha256=content_sha256,
        raw_source_artifact_identity_hash=artifact_identity_hash,
        raw_import_batch_identity_hash=batch_identity_hash,
        external_logical_record_id=row_input.external_logical_record_id,
        external_revision_id=row_input.external_revision_id,
        revision_number=row_input.revision_number,
        source_system=row_input.source_system,
        source_version=row_input.source_version,
        schema_version=row_input.schema_version,
        source_row_identity_version=row_input.source_row_identity_version,
        source_sheet_name=row_input.source_sheet_name,
        source_row_number=row_input.source_row_number,
        source_column_mapping_snapshot_hash=row_input.source_column_mapping_snapshot_hash,
        winner_selection_blocked=False,
    )


def _with_derived_blocked_state(
    session: Session,
    *,
    identity: SourceRowIdentity,
) -> SourceRowIdentity:
    return identity.model_copy(
        update={
            "winner_selection_blocked": derive_winner_selection_blocked(
                session,
                raw_source_artifact_identity_hash=identity.raw_source_artifact_identity_hash,
                source_system=identity.source_system,
                external_logical_record_id=identity.external_logical_record_id,
                source_row_identity_hash=identity.source_row_identity_hash,
            )
        }
    )


def register_source_row_lineage(
    session: Session,
    *,
    artifact_identity_hash: str,
    batch_identity_hash: str,
    row_input: SourceRowLineageInput,
) -> SourceRowRegistration:
    identity = build_source_row_identity(
        artifact_identity_hash=artifact_identity_hash,
        batch_identity_hash=batch_identity_hash,
        row_input=row_input,
    )

    existing = fetch_source_row_by_identity_and_content(
        session,
        source_row_identity_hash=identity.source_row_identity_hash,
        content_sha256=identity.content_sha256,
    )
    if existing is not None:
        return SourceRowRegistration(
            result=SourceRowRegistrationResult.EXACT_REPLAY,
            identity=_with_derived_blocked_state(session, identity=existing),
        )

    conflicting_rows = fetch_source_rows_by_identity_hash(
        session,
        source_row_identity_hash=identity.source_row_identity_hash,
    )
    if conflicting_rows:
        insert_source_row_lineage(session, identity=identity)
        persisted = fetch_source_row_by_identity_and_content(
            session,
            source_row_identity_hash=identity.source_row_identity_hash,
            content_sha256=identity.content_sha256,
        )
        assert persisted is not None
        return SourceRowRegistration(
            result=SourceRowRegistrationResult.CONTENT_CONFLICT_CANDIDATE,
            identity=_with_derived_blocked_state(session, identity=persisted),
        )

    insert_source_row_lineage(session, identity=identity)
    persisted = fetch_source_row_by_identity_and_content(
        session,
        source_row_identity_hash=identity.source_row_identity_hash,
        content_sha256=identity.content_sha256,
    )
    assert persisted is not None
    return SourceRowRegistration(
        result=SourceRowRegistrationResult.FIRST_SEEN,
        identity=_with_derived_blocked_state(session, identity=persisted),
    )
