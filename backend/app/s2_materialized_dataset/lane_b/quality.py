"""Lane B quality finding rules (contract §4.6)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.app.s2_materialized_dataset.lane_b.exclusion_ledger import is_row_excluded
from backend.app.s2_materialized_dataset.lane_b.hashes import (
    QUALITY_RULE_VERSION,
    compute_quality_finding_identity_hash,
    digest,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    ExclusionLedgerEntryRecord,
    QualityFindingCode,
    QualityFindingRecord,
    QualityFindingSeverity,
    QuantityPresenceStatus,
    SyntheticSourceRowInput,
)

MISSING_QUANTITY_RULE_ID = "lane-b-missing-quantity-unknown-not-zero-v1"
DUPLICATE_GRAIN_RULE_ID = "lane-b-duplicate-canonical-grain-v1"
VALIDATION_RUN_IDENTITY = "synthetic-lane-b-validation-run-v1"


@dataclass(frozen=True)
class PreparedCleaningRow:
    source_row_identity_hash: str
    canonical_grain_key_payload: dict[str, object]
    source_row: SyntheticSourceRowInput
    quantity_presence_status: QuantityPresenceStatus


def _rule_definition_hash(rule_id: str) -> str:
    return digest({"quality_rule_id": rule_id, "quality_rule_version": QUALITY_RULE_VERSION})


def _normalized_observed_value_identity(*, field_name: str, value: Decimal | None) -> str:
    if value is None:
        return f"{field_name}:UNKNOWN_NOT_ZERO"
    return f"{field_name}:{value}"


def evaluate_quality_findings(
    *,
    cleaned_dataset_version_identity_hash: str,
    quality_policy_version: str,
    quality_schema_version: str,
    prepared_rows: tuple[PreparedCleaningRow, ...],
    cleaned_row_identity_by_source: dict[str, str],
    duplicate_groups: dict[str, tuple[str, ...]],
    exclusion_entries: tuple[ExclusionLedgerEntryRecord, ...],
) -> tuple[QualityFindingRecord, ...]:
    findings: list[QualityFindingRecord] = []

    for prepared in prepared_rows:
        if prepared.quantity_presence_status == QuantityPresenceStatus.UNKNOWN_NOT_ZERO:
            normalized = _normalized_observed_value_identity(
                field_name="actual_harvest_quantity_kg",
                value=None,
            )
            identity_hash = compute_quality_finding_identity_hash(
                cleaned_dataset_version_identity_hash=cleaned_dataset_version_identity_hash,
                source_row_identity_hash=prepared.source_row_identity_hash,
                quality_rule_id=MISSING_QUANTITY_RULE_ID,
                observed_field="actual_harvest_quantity_kg",
                finding_code=QualityFindingCode.MISSING_QUANTITY_UNKNOWN_NOT_ZERO.value,
                quality_policy_version=quality_policy_version,
                quality_rule_version=QUALITY_RULE_VERSION,
                quality_schema_version=quality_schema_version,
                normalized_observed_value_identity=normalized,
                severity=QualityFindingSeverity.WARNING.value,
                rule_definition_hash=_rule_definition_hash(MISSING_QUANTITY_RULE_ID),
            )
            findings.append(
                QualityFindingRecord(
                    quality_finding_identity_hash=identity_hash,
                    cleaned_dataset_version_identity_hash=cleaned_dataset_version_identity_hash,
                    source_row_identity_hash=prepared.source_row_identity_hash,
                    cleaned_row_identity_hash=cleaned_row_identity_by_source.get(
                        prepared.source_row_identity_hash
                    ),
                    quality_rule_id=MISSING_QUANTITY_RULE_ID,
                    quality_rule_version=QUALITY_RULE_VERSION,
                    observed_field="actual_harvest_quantity_kg",
                    finding_code=QualityFindingCode.MISSING_QUANTITY_UNKNOWN_NOT_ZERO,
                    severity=QualityFindingSeverity.WARNING,
                    normalized_observed_value_identity=normalized,
                    rule_definition_hash=_rule_definition_hash(MISSING_QUANTITY_RULE_ID),
                    validation_run_identity=VALIDATION_RUN_IDENTITY,
                )
            )

    prepared_by_source = {row.source_row_identity_hash: row for row in prepared_rows}
    for grain_key, source_row_hashes in sorted(duplicate_groups.items()):
        for source_row_identity_hash in sorted(source_row_hashes):
            if not is_row_excluded(
                source_row_identity_hash=source_row_identity_hash,
                entries=exclusion_entries,
            ):
                continue
            prepared = prepared_by_source[source_row_identity_hash]
            normalized = f"duplicate_canonical_grain:{grain_key}"
            identity_hash = compute_quality_finding_identity_hash(
                cleaned_dataset_version_identity_hash=cleaned_dataset_version_identity_hash,
                source_row_identity_hash=source_row_identity_hash,
                quality_rule_id=DUPLICATE_GRAIN_RULE_ID,
                observed_field="canonical_grain_key",
                finding_code=QualityFindingCode.DUPLICATE_CANONICAL_GRAIN.value,
                quality_policy_version=quality_policy_version,
                quality_rule_version=QUALITY_RULE_VERSION,
                quality_schema_version=quality_schema_version,
                normalized_observed_value_identity=normalized,
                severity=QualityFindingSeverity.ERROR.value,
                rule_definition_hash=_rule_definition_hash(DUPLICATE_GRAIN_RULE_ID),
            )
            findings.append(
                QualityFindingRecord(
                    quality_finding_identity_hash=identity_hash,
                    cleaned_dataset_version_identity_hash=cleaned_dataset_version_identity_hash,
                    source_row_identity_hash=source_row_identity_hash,
                    cleaned_row_identity_hash=cleaned_row_identity_by_source.get(
                        source_row_identity_hash
                    ),
                    quality_rule_id=DUPLICATE_GRAIN_RULE_ID,
                    quality_rule_version=QUALITY_RULE_VERSION,
                    observed_field="canonical_grain_key",
                    finding_code=QualityFindingCode.DUPLICATE_CANONICAL_GRAIN,
                    severity=QualityFindingSeverity.ERROR,
                    normalized_observed_value_identity=normalized,
                    rule_definition_hash=_rule_definition_hash(DUPLICATE_GRAIN_RULE_ID),
                    validation_run_identity=VALIDATION_RUN_IDENTITY,
                )
            )

    return tuple(sorted(findings, key=lambda item: item.quality_finding_identity_hash))


def findings_for_source_row(
    findings: tuple[QualityFindingRecord, ...],
    *,
    source_row_identity_hash: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            finding.quality_finding_identity_hash
            for finding in findings
            if finding.source_row_identity_hash == source_row_identity_hash
        )
    )
