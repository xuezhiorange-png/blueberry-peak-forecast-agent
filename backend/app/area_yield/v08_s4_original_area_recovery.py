"""Fail-closed rules for recovering original historical area evidence.

This module is an audit utility only. It does not write or mutate any product
area, identity, or quantity authority.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite

TRUSTED_SOURCE_CLASSES = frozenset(
    {
        "USER_ORIGINAL_STRUCTURED_INPUT",
        "USER_CONFIRMED_BUSINESS_RECORD",
        "BUSINESS_CONFIRMED_SOURCE",
    }
)

_SAFE_ADDITION_FORMULA = re.compile(r"^=\s*(\d+(?:\.\d+)?)\s*\+\s*(\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True, slots=True)
class AreaSourceEvidence:
    source_id: str
    source_class: str
    area_semantics: str
    season: str | None
    grain: str
    base_id: str | None
    member_id: str | None
    area_mu: Decimal | None
    source_sha256: str | None
    identity_resolved: bool
    source_conflict: bool = False
    disjoint_scope_proven: bool = False
    supersedes_source_id: str | None = None


@dataclass(frozen=True, slots=True)
class AreaAggregateResult:
    status: str
    area_mu: Decimal | None
    source_ids: tuple[str, ...]


def historical_candidate_status(evidence: AreaSourceEvidence) -> str:
    """Classify a source as a candidate without promoting formal authority."""
    if evidence.source_class not in TRUSTED_SOURCE_CLASSES:
        return "SOURCE_NOT_ORIGINAL_OR_BUSINESS_CONFIRMED"
    if evidence.season is None:
        return "SEASON_UNRESOLVED"
    if evidence.area_semantics != "HISTORICAL_ACTUAL":
        return "AREA_SEMANTICS_NOT_HISTORICAL_ACTUAL"
    if not evidence.identity_resolved or not evidence.base_id:
        return "IDENTITY_UNRESOLVED"
    if evidence.source_conflict:
        return "CONFLICTING_ORIGINAL_AREA_EVIDENCE"
    if evidence.area_mu is None or evidence.area_mu < 0:
        return "AREA_VALUE_INVALID_OR_MISSING"
    if not evidence.source_sha256:
        return "SOURCE_PROVENANCE_MISSING"
    if evidence.grain == "MEMBER":
        if not evidence.member_id:
            return "MEMBER_IDENTITY_UNRESOLVED"
        return "MEMBER_LEVEL_HISTORICAL_ACTUAL_CANDIDATE"
    if evidence.grain == "BASE":
        return "BASE_SEASON_HISTORICAL_ACTUAL_CANDIDATE"
    return "AREA_GRAIN_UNRESOLVED"


def evidence_identity_key(evidence: AreaSourceEvidence) -> tuple[str, str, str, str]:
    """Keep season and source grain in identity; never collapse cross-season values."""
    return (
        evidence.base_id or "UNBOUND_BASE",
        evidence.season or "SEASON_UNRESOLVED",
        evidence.grain,
        evidence.member_id or "BASE_SCOPE",
    )


def conflicting_source_groups(
    evidence_rows: Iterable[AreaSourceEvidence],
) -> tuple[tuple[str, ...], ...]:
    """Return same-key groups with different exact Decimal values."""
    groups: dict[tuple[str, str, str, str], list[AreaSourceEvidence]] = defaultdict(list)
    for evidence in evidence_rows:
        groups[evidence_identity_key(evidence)].append(evidence)

    conflicts: list[tuple[str, ...]] = []
    for rows in groups.values():
        values = {row.area_mu for row in rows if row.area_mu is not None}
        if len(values) > 1:
            conflicts.append(tuple(sorted(row.source_id for row in rows)))
    return tuple(sorted(conflicts))


def resolve_explicit_supersession(
    evidence_rows: Sequence[AreaSourceEvidence],
) -> AreaSourceEvidence | None:
    """Resolve only a complete, explicit supersession chain; otherwise fail closed."""
    if not evidence_rows:
        return None
    by_id = {row.source_id: row for row in evidence_rows}
    if len(by_id) != len(evidence_rows):
        return None

    superseded = {row.supersedes_source_id for row in evidence_rows if row.supersedes_source_id}
    if not superseded:
        if len({row.area_mu for row in evidence_rows}) == 1:
            return evidence_rows[0]
        return None
    if not superseded.issubset(by_id):
        return None

    current = [row for row in evidence_rows if row.source_id not in superseded]
    if len(current) != 1:
        return None
    current_row = current[0]

    visited: set[str] = set()
    cursor = current_row
    while cursor.supersedes_source_id is not None:
        if cursor.source_id in visited:
            return None
        visited.add(cursor.source_id)
        prior = by_id.get(cursor.supersedes_source_id)
        if prior is None:
            return None
        cursor = prior
    if len(visited) != len(evidence_rows) - 1:
        return None
    return current_row


def aggregate_complete_members(
    member_rows: Sequence[AreaSourceEvidence],
    accepted_member_ids: Sequence[str],
) -> AreaAggregateResult:
    """Aggregate only a complete, same-Base/season, explicitly disjoint member set."""
    if not accepted_member_ids or len(set(accepted_member_ids)) != len(accepted_member_ids):
        return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_AUTHORITY_INVALID", None, ())
    if not member_rows:
        return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_AREA_MISSING", None, ())

    keys = {(row.base_id, row.season) for row in member_rows}
    if len(keys) != 1 or None in {key[0] for key in keys} or None in {key[1] for key in keys}:
        return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_SCOPE_MISMATCH", None, ())
    if any(row.grain != "MEMBER" or row.member_id is None for row in member_rows):
        return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_GRAIN_INVALID", None, ())
    if any(row.source_class not in TRUSTED_SOURCE_CLASSES for row in member_rows):
        return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_SOURCE_UNQUALIFIED", None, ())
    if any(not row.identity_resolved or row.source_conflict for row in member_rows):
        return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_IDENTITY_OR_CONFLICT", None, ())
    if any(row.area_mu is None or row.area_mu < 0 for row in member_rows):
        return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_AREA_INVALID", None, ())
    if any(not row.disjoint_scope_proven for row in member_rows):
        return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_OVERLAP_NOT_EXCLUDED", None, ())

    by_member: dict[str, list[AreaSourceEvidence]] = defaultdict(list)
    for row in member_rows:
        assert row.member_id is not None
        by_member[row.member_id].append(row)
    if set(by_member) != set(accepted_member_ids):
        return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_COVERAGE_INCOMPLETE", None, ())

    selected: list[AreaSourceEvidence] = []
    for member_id in accepted_member_ids:
        resolved = resolve_explicit_supersession(by_member[member_id])
        if resolved is None or not resolved.source_sha256:
            return AreaAggregateResult("NOT_COMPUTABLE_MEMBER_SOURCE_CONFLICT", None, ())
        selected.append(resolved)

    total = sum((row.area_mu for row in selected if row.area_mu is not None), Decimal(0))
    return AreaAggregateResult(
        "BASE_AGGREGATE_CANDIDATE_COMPLETE_MEMBERS",
        total,
        tuple(sorted(row.source_id for row in selected)),
    )


def reference_total_matches(area_values: Iterable[Decimal], expected_total: Decimal) -> bool:
    """Use exact Decimal addition; no rounding or tolerance is allowed."""
    return sum(area_values, Decimal(0)) == expected_total


def source_provenance_status(source_id: str | None, source_sha256: str | None) -> str:
    if not source_id or not source_sha256:
        return "DERIVED_AREA_WITHOUT_ORIGINAL_PROVENANCE"
    return "SOURCE_RECORD_AND_HASH_BOUND"


def harvest_workbook_area_source_status(area_like_text_cell_count: int) -> str:
    """Do not treat a harvest workbook as area provenance without an area field."""
    if area_like_text_cell_count < 0:
        raise ValueError("AREA_FIELD_SCAN_COUNT_INVALID")
    if area_like_text_cell_count == 0:
        return "HARVEST_QUANTITY_ONLY_NO_AREA_FIELD"
    return "AREA_LIKE_FIELD_PRESENT_REQUIRES_SOURCE_REVIEW"


def parse_area_mu_cell(value: object) -> Decimal | None:
    """Read a numeric area cell, evaluating only a literal two-term addition formula."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("AREA_VALUE_INVALID")
    if isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("AREA_VALUE_INVALID")
        area = Decimal(str(value))
    elif isinstance(value, str):
        formula = _SAFE_ADDITION_FORMULA.fullmatch(value.strip())
        if formula:
            area = Decimal(formula.group(1)) + Decimal(formula.group(2))
        else:
            try:
                area = Decimal(value.strip())
            except Exception as exc:
                raise ValueError("AREA_VALUE_INVALID") from exc
    else:
        raise ValueError("AREA_VALUE_INVALID")
    if not area.is_finite() or area < 0:
        raise ValueError("AREA_VALUE_INVALID")
    return area


def exact_canonical_base_binding(
    source_base_name: str, canonical_bases: Iterable[Mapping[str, str]]
) -> tuple[str, str] | None:
    """Bind a Base-grain label by exact canonical-name equality only."""
    matches = [
        (base["base_id"], base["canonical_base_name"])
        for base in canonical_bases
        if source_base_name == base["canonical_base_name"]
    ]
    if len(matches) > 1:
        raise ValueError("CANONICAL_BASE_NAME_NOT_UNIQUE")
    return matches[0] if matches else None


def classify_source_category(source_type: str, business_confirmation_status: str) -> str:
    """Classify evidence origin without promoting derived artifacts to authority."""
    if source_type == "BASE_REGISTRY_SOURCE_WORKBOOK":
        return "USER_ORIGINAL_STRUCTURED_INPUT"
    if (
        source_type == "AREA_YIELD_AUTHORITY"
        and business_confirmation_status == "BUSINESS_CONFIRMED"
    ):
        return "USER_CONFIRMED_BUSINESS_RECORD"
    if (
        source_type == "CURRENT_AREA_REVIEW_WORKBOOK"
        and business_confirmation_status == "BUSINESS_CONFIRMED_REVIEW_WORKBOOK"
    ):
        return "BUSINESS_CONFIRMED_SOURCE"
    if source_type in {"BASE_REGISTRY_JSON", "BASE_REGISTRY_NORMALIZED"}:
        return "REFERENCE_REGISTRY_DERIVED"
    if source_type in {
        "FARM_TOTAL_AREA_AUTHORITY_PROXY_PACKAGE",
        "R4_FARM_AREA_AUTHORITY_AUDIT",
    }:
        return "PROXY_DERIVED"
    if source_type in {
        "PROCESSING_FACTORY_STATISTICAL_REPORT",
        "PROCESSING_FACTORY_STATISTICAL_AREA",
    }:
        return "REPORT_DERIVED"
    if source_type in {"PRODUCTION_PLAN_OR_LAYOUT", "SEASON_YIELD_FORECAST_DETAIL"}:
        return "PLANNED_AREA"
    if source_type in {"MODEL_INPUT", "MODEL_TRAINING_SAMPLE", "BACKTEST_INPUT"}:
        return "MODEL_INPUT_DERIVED_FROM_USER_DATA"
    return "UNKNOWN_ORIGIN"


def deterministic_csv_bytes(fieldnames: Sequence[str], rows: Iterable[dict[str, str]]) -> bytes:
    """Serialize sorted rows with fixed encoding, field order, and line endings."""
    ordered = sorted(rows, key=lambda row: tuple(row.get(key, "") for key in fieldnames))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(ordered)
    return buffer.getvalue().encode("utf-8")
