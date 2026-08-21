from __future__ import annotations

import pytest

from backend.app.s2_materialized_dataset.lane_b.cleaning import (
    CleanedRowConflictError,
    build_cleaned_dataset,
)
from backend.app.s2_materialized_dataset.lane_b.hashes import compute_quality_finding_identity_hash
from backend.app.s2_materialized_dataset.lane_b.quality import (
    DUPLICATE_GRAIN_RULE_ID,
    MISSING_QUANTITY_RULE_ID,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    CleaningBuildRequest,
    ExclusionCode,
    ManualExclusionRequest,
    QualityFindingCode,
    QualityFindingSeverity,
    SyntheticSourceRowInput,
)
from backend.tests.s2_materialized_dataset.lane_b.conftest import make_source_row_identity_hash

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_missing_quantity_emits_quality_finding(
    cleaning_build_request: CleaningBuildRequest,
    missing_quantity_row: SyntheticSourceRowInput,
) -> None:
    request = cleaning_build_request.model_copy(update={"source_rows": (missing_quantity_row,)})
    result = build_cleaned_dataset(request)

    assert len(result.quality_findings) == 1
    finding = result.quality_findings[0]
    assert finding.finding_code == QualityFindingCode.MISSING_QUANTITY_UNKNOWN_NOT_ZERO
    assert finding.severity == QualityFindingSeverity.WARNING
    assert finding.observed_field == "actual_harvest_quantity_kg"
    assert finding.quality_rule_id == MISSING_QUANTITY_RULE_ID
    assert finding.normalized_observed_value_identity == (
        "actual_harvest_quantity_kg:UNKNOWN_NOT_ZERO"
    )
    assert finding.cleaned_row_identity_hash == result.cleaned_rows[0].cleaned_row_identity_hash


def test_duplicate_grain_without_disposition_fails_closed(
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row: SyntheticSourceRowInput,
) -> None:
    duplicate = known_quantity_row.model_copy(
        update={
            "identity": known_quantity_row.identity.model_copy(
                update={
                    "external_logical_record_id": "logical-2",
                    "external_revision_id": "revision-2",
                }
            )
        }
    )
    request = cleaning_build_request.model_copy(
        update={"source_rows": (known_quantity_row, duplicate)}
    )

    with pytest.raises(CleanedRowConflictError, match="duplicate canonical grain"):
        build_cleaned_dataset(request)


def test_duplicate_grain_resolved_by_exclusion_publishes_single_row(
    cleaning_build_request: CleaningBuildRequest,
    known_quantity_row: SyntheticSourceRowInput,
) -> None:
    duplicate = known_quantity_row.model_copy(
        update={
            "identity": known_quantity_row.identity.model_copy(
                update={
                    "external_logical_record_id": "logical-2",
                    "external_revision_id": "revision-2",
                }
            )
        }
    )
    duplicate_hash = make_source_row_identity_hash(duplicate)
    request = cleaning_build_request.model_copy(
        update={
            "source_rows": (known_quantity_row, duplicate),
            "manual_exclusions": (
                ManualExclusionRequest(
                    exclusion_event_id="exclude-duplicate",
                    source_row_identity_hash=duplicate_hash,
                    exclusion_code=ExclusionCode.QUALITY_BLOCKED,
                    exclusion_reason_reference="duplicate-grain-disposition",
                    decision_authority_reference="approver-1",
                ),
            ),
        }
    )
    result = build_cleaned_dataset(request)

    assert len(result.cleaned_rows) == 1
    survivor_hash = make_source_row_identity_hash(known_quantity_row)
    assert result.cleaned_rows[0].source_row_identity_hash == survivor_hash

    duplicate_findings = [
        finding
        for finding in result.quality_findings
        if finding.finding_code == QualityFindingCode.DUPLICATE_CANONICAL_GRAIN
    ]
    assert len(duplicate_findings) == 1
    finding = duplicate_findings[0]
    assert finding.source_row_identity_hash == duplicate_hash
    assert finding.quality_rule_id == DUPLICATE_GRAIN_RULE_ID
    assert finding.severity == QualityFindingSeverity.ERROR
    assert finding.cleaned_row_identity_hash is None


def test_same_finding_identity_with_changed_severity_is_conflict(
    cleaning_build_request: CleaningBuildRequest,
    missing_quantity_row: SyntheticSourceRowInput,
) -> None:
    request = cleaning_build_request.model_copy(update={"source_rows": (missing_quantity_row,)})
    result = build_cleaned_dataset(request)
    finding = result.quality_findings[0]

    recomputed = compute_quality_finding_identity_hash(
        cleaned_dataset_version_identity_hash=finding.cleaned_dataset_version_identity_hash,
        source_row_identity_hash=finding.source_row_identity_hash,
        quality_rule_id=finding.quality_rule_id,
        observed_field=finding.observed_field,
        finding_code=finding.finding_code.value,
        quality_policy_version=request.quality_policy_version,
        quality_rule_version=finding.quality_rule_version,
        quality_schema_version=request.quality_schema_version,
        normalized_observed_value_identity=finding.normalized_observed_value_identity,
        severity=QualityFindingSeverity.ERROR.value,
        rule_definition_hash=finding.rule_definition_hash,
    )
    assert recomputed != finding.quality_finding_identity_hash
