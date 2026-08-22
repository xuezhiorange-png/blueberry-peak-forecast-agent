from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.s2_materialized_dataset.lane_a.schemas import (
    SourceRowBusinessContent,
    SourceRowIdentity,
    SourceRowLineageInput,
)
from backend.app.s2_materialized_dataset.lane_b.cleaning import (
    SOURCE_002_JULY_EXCLUSION_DATE,
    build_canonical_grain_collision_exclusions,
    build_cleaned_dataset,
    build_july_cohort_exclusions,
    resolve_source_002_season_business_key,
    source_row_input_from_persisted_lane_a,
)
from backend.app.s2_materialized_dataset.lane_b.hashes import digest
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    SOURCE_002_JULY_COHORT_EXCLUSION_REASON,
    SOURCE_002_MAPPED_SEASON_BUSINESS_KEY,
    SOURCE_002_UNMAPPED_SEASON_BUSINESS_KEY,
    ExclusionCode,
    Source002CleaningBlockedError,
)
from backend.tests.s2_materialized_dataset.lane_b.conftest import (
    make_source_row,
    make_source_row_identity_hash,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _persisted_identity(
    *,
    logical_id: str,
    harvest_date: date,
    quantity: Decimal = Decimal("10.000000"),
) -> tuple[SourceRowLineageInput, SourceRowIdentity]:
    row_input = SourceRowLineageInput(
        external_logical_record_id=logical_id,
        external_revision_id="source-002-idfl-immutable-final-revision-v1",
        revision_number=1,
        source_system="扫码称重系统",
        source_version="scan-weight-export:v0_3_s1:002",
        schema_version="observed-source-schema-v1",
        source_row_identity_version="v0-3-s2-source-row-identity-v1",
        source_sheet_name="Sheet1",
        source_row_number=2,
        source_column_mapping_snapshot_hash="6" * 64,
        business_content=SourceRowBusinessContent(
            harvest_business_date=harvest_date,
            farm_code="farm-a",
            subfarm_or_plot_code="subfarm-a",
            variety_code="variety-a",
            actual_harvest_quantity_kg=quantity,
        ),
    )
    identity = SourceRowIdentity(
        source_row_identity_hash=digest({"logical_id": logical_id, "harvest_date": harvest_date}),
        content_sha256="b" * 64,
        raw_source_artifact_identity_hash="c" * 64,
        raw_import_batch_identity_hash="d" * 64,
        external_logical_record_id=logical_id,
        external_revision_id="source-002-idfl-immutable-final-revision-v1",
        revision_number=1,
        source_system="扫码称重系统",
        source_version="scan-weight-export:v0_3_s1:002",
        schema_version="observed-source-schema-v1",
        source_row_identity_version="v0-3-s2-source-row-identity-v1",
        source_sheet_name="Sheet1",
        source_row_number=2,
        source_column_mapping_snapshot_hash="6" * 64,
        winner_selection_blocked=False,
    )
    return row_input, identity


def test_source_002_season_resolution_maps_mapped_dates() -> None:
    assert resolve_source_002_season_business_key(date(2025, 8, 5)) == (
        SOURCE_002_MAPPED_SEASON_BUSINESS_KEY
    )
    assert resolve_source_002_season_business_key(date(2026, 4, 16)) == (
        SOURCE_002_MAPPED_SEASON_BUSINESS_KEY
    )


def test_source_002_july_date_uses_unmapped_sentinel_not_auto_season() -> None:
    assert resolve_source_002_season_business_key(SOURCE_002_JULY_EXCLUSION_DATE) == (
        SOURCE_002_UNMAPPED_SEASON_BUSINESS_KEY
    )


def test_source_002_out_of_scope_date_fails_closed() -> None:
    with pytest.raises(Source002CleaningBlockedError):
        resolve_source_002_season_business_key(date(2024, 1, 1))


def test_july_cohort_exclusions_reference_option_a_reason() -> None:
    row_input, identity = _persisted_identity(
        logical_id="july-row-1",
        harvest_date=SOURCE_002_JULY_EXCLUSION_DATE,
    )
    source_row = source_row_input_from_persisted_lane_a(
        row_input=row_input,
        persisted_identity=identity,
    )
    exclusions = build_july_cohort_exclusions(source_rows=(source_row,))
    assert len(exclusions) == 1
    assert exclusions[0].exclusion_code == ExclusionCode.BUSINESS_EXCLUSION
    assert exclusions[0].exclusion_reason_reference == SOURCE_002_JULY_COHORT_EXCLUSION_REASON


def test_canonical_grain_collision_excludes_loser_by_min_hash(
    synthetic_batch,
    synthetic_artifact,
) -> None:
    row_a = make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="logical-a",
        harvest_date=date(2026, 2, 10),
    )
    row_b = make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="logical-b",
        harvest_date=date(2026, 2, 10),
    )
    hash_a = make_source_row_identity_hash(row_a)
    hash_b = make_source_row_identity_hash(row_b)
    row_a = row_a.model_copy(update={"persisted_source_row_identity_hash": hash_a})
    row_b = row_b.model_copy(update={"persisted_source_row_identity_hash": hash_b})

    exclusions = build_canonical_grain_collision_exclusions(source_rows=(row_a, row_b))
    assert len(exclusions) == 1
    loser = max(hash_a, hash_b)
    assert exclusions[0].source_row_identity_hash == loser
    assert exclusions[0].exclusion_code == ExclusionCode.QUALITY_BLOCKED


def test_july_rows_remain_in_source_lineage_but_not_canonical_output(
    cleaning_build_request,
    synthetic_batch,
    synthetic_artifact,
) -> None:
    mapped_row = make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="mapped-row",
        harvest_date=date(2026, 2, 10),
    )
    july_row = make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="july-row",
        harvest_date=SOURCE_002_JULY_EXCLUSION_DATE,
    )
    july_row = july_row.model_copy(
        update={
            "season_business_key": SOURCE_002_UNMAPPED_SEASON_BUSINESS_KEY,
            "identity": july_row.identity.model_copy(
                update={"external_logical_record_id": "july-logical"}
            ),
        }
    )
    july_hash = make_source_row_identity_hash(july_row)
    july_exclusions = build_july_cohort_exclusions(source_rows=(july_row,))
    request = cleaning_build_request.model_copy(
        update={
            "source_rows": (mapped_row, july_row),
            "manual_exclusions": july_exclusions,
        }
    )
    result = build_cleaned_dataset(request)

    assert len(result.version.source_row_identity_hashes) == 2
    assert july_hash in result.version.source_row_identity_hashes
    assert sum(1 for row in result.cleaned_rows if not row.is_excluded) == 1
    assert any(
        row.source_row_identity_hash == july_hash and row.is_excluded for row in result.cleaned_rows
    )
