"""S3-A2 S2 identity alignment adapter tests."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    S2AlignedIdentity,
    S2IdentityAlignmentPort,
)
from backend.app.s3_daily_rowset.registry import (
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.app.s3_daily_rowset.s2_identity_alignment import (
    AcceptedS2IdentityEvidenceRow,
    ForbiddenS2IdentityAlignmentError,
    S2IdentityAlignmentAdapter,
    VersionedAcceptedS2IdentityAlignmentEvidence,
)
from backend.app.s3_daily_rowset.schemas import DatasetIdentity
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled


def _evidence_row(
    *,
    season: str = "2025~2026",
    farm: str = "farm-a",
    subfarm: str = "subfarm-1",
    variety: str = "variety-x",
    harvest_business_date: date | None = None,
) -> AcceptedS2IdentityEvidenceRow:
    if harvest_business_date is None:
        harvest_business_date = date(2026, 2, 15)
    return AcceptedS2IdentityEvidenceRow(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        harvest_business_date=harvest_business_date,
    )


def _evidence(
    *,
    content_identity_sha256: str = "fixture-s2-alignment-evidence-hash-for-tests-only",
    rows: tuple[AcceptedS2IdentityEvidenceRow, ...] | None = None,
    dataset_identity: DatasetIdentity = DATASET_IDENTITY,
) -> VersionedAcceptedS2IdentityAlignmentEvidence:
    if rows is None:
        rows = (_evidence_row(),)
    return VersionedAcceptedS2IdentityAlignmentEvidence(
        content_identity_sha256=content_identity_sha256,
        dataset_id=dataset_identity.dataset_id,
        dataset_version=dataset_identity.dataset_version,
        materialized_dataset_identity_sha256=dataset_identity.materialized_dataset_identity_sha256,
        rows=rows,
    )


def test_default_adapter_is_fail_closed() -> None:
    adapter = S2IdentityAlignmentAdapter()

    assert adapter.alignment_source_kind() == CatalogSourceKind.UNBOUND
    assert adapter.aligned_identities() == ()

    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_injected_live_evidence_projects_deduped_sorted_identities() -> None:
    adapter = S2IdentityAlignmentAdapter(
        evidence=_evidence(
            rows=(
                _evidence_row(
                    farm="farm-b",
                    harvest_business_date=date(2026, 3, 1),
                ),
                _evidence_row(
                    farm="farm-a",
                    harvest_business_date=date(2026, 2, 10),
                ),
                _evidence_row(
                    farm="farm-a",
                    harvest_business_date=date(2026, 2, 20),
                ),
            ),
        ),
    )

    assert adapter.alignment_source_kind() == (
        CatalogSourceKind.SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT
    )
    identities = adapter.aligned_identities()
    assert identities == (
        S2AlignedIdentity(
            season="2025~2026",
            farm="farm-a",
            subfarm="subfarm-1",
            variety="variety-x",
            partition="VALIDATION",
        ),
        S2AlignedIdentity(
            season="2025~2026",
            farm="farm-b",
            subfarm="subfarm-1",
            variety="variety-x",
            partition="VALIDATION",
        ),
    )


def test_august_train_row_is_excluded_by_month_scope() -> None:
    adapter = S2IdentityAlignmentAdapter(
        evidence=_evidence(
            rows=(
                _evidence_row(harvest_business_date=date(2025, 8, 15)),
                _evidence_row(harvest_business_date=date(2026, 2, 15)),
            ),
        ),
    )

    identities = adapter.aligned_identities()
    assert len(identities) == 1
    assert identities[0].partition == "VALIDATION"


def test_test_partition_source_row_is_excluded() -> None:
    adapter = S2IdentityAlignmentAdapter(
        evidence=_evidence(
            rows=(
                _evidence_row(harvest_business_date=date(2026, 3, 15)),
                _evidence_row(harvest_business_date=date(2026, 2, 15)),
            ),
        ),
    )

    identities = adapter.aligned_identities()
    assert len(identities) == 1
    assert identities[0].partition == "VALIDATION"


@pytest.mark.parametrize("variety", ["普鲜", "普青", "普冻", "废果"])
def test_forbidden_varieties_are_excluded(variety: str) -> None:
    adapter = S2IdentityAlignmentAdapter(
        evidence=_evidence(rows=(_evidence_row(variety=variety),)),
    )

    assert adapter.aligned_identities() == ()
    assert adapter.alignment_source_kind() == CatalogSourceKind.UNBOUND


def test_bason_factory_is_excluded() -> None:
    adapter = S2IdentityAlignmentAdapter(
        evidence=_evidence(rows=(_evidence_row(farm="巴松加工厂"),)),
    )

    assert adapter.aligned_identities() == ()
    assert adapter.alignment_source_kind() == CatalogSourceKind.UNBOUND


@pytest.mark.parametrize("field_name", ["season", "farm", "subfarm", "variety"])
def test_blank_fields_after_trim_are_rejected(field_name: str) -> None:
    kwargs = {field_name: "   "}
    adapter = S2IdentityAlignmentAdapter(
        evidence=_evidence(rows=(_evidence_row(**kwargs),)),
    )
    with pytest.raises(ForbiddenS2IdentityAlignmentError):
        adapter.aligned_identities()


def test_dataset_identity_mismatch_is_rejected() -> None:
    bad_identity = DatasetIdentity(
        dataset_id="source-002",
        dataset_version="e5-live-v1",
        materialized_dataset_identity_sha256="0" * 64,
    )
    with pytest.raises(ForbiddenS2IdentityAlignmentError):
        _evidence(dataset_identity=bad_identity)


@pytest.mark.parametrize(
    "forbidden_hash",
    [
        HORIZON_H7_SUCCESS_FIXTURE_HASH,
        "",
        "0" * 64,
    ],
)
def test_forbidden_alignment_evidence_hashes_are_rejected(forbidden_hash: str) -> None:
    with pytest.raises(ForbiddenS2IdentityAlignmentError):
        _evidence(content_identity_sha256=forbidden_hash)


@dataclass(frozen=True, slots=True)
class _UnboundWithIdentitiesPort(S2IdentityAlignmentPort):
    identities: tuple[S2AlignedIdentity, ...]

    def alignment_source_kind(self) -> CatalogSourceKind:
        return CatalogSourceKind.UNBOUND

    def aligned_identities(self) -> tuple[S2AlignedIdentity, ...]:
        return self.identities


def test_non_empty_identities_with_unbound_source_fail_closed_in_producer() -> None:
    from datetime import UTC, datetime

    from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
    from backend.app.s3_daily_rowset.forecast_artifact import (
        IncumbentForecastArtifactAdapter,
        VersionedIncumbentForecastArtifact,
    )

    forecast_adapter = IncumbentForecastArtifactAdapter(
        artifact=VersionedIncumbentForecastArtifact(
            content_identity_sha256="fixture-forecast-artifact-hash-for-tests-only",
            rows=(
                IncumbentForecastArtifactEntry(
                    model_id="incumbent-v0.2",
                    forecast_cutoff_at=datetime(2026, 2, 15, 16, 0, tzinfo=UTC),
                    forecast_quantile="P50",
                ),
            ),
        ),
    )
    alignment_port = _UnboundWithIdentitiesPort(
        identities=(
            S2AlignedIdentity(
                season="2025~2026",
                farm="farm-a",
                subfarm="subfarm-1",
                variety="variety-x",
                partition="TRAIN",
            ),
        ),
    )

    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=forecast_adapter,
        alignment_port=alignment_port,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.FORBIDDEN_CATALOG_SOURCE


def test_alignment_module_does_not_scan_repository_or_read_source_002() -> None:
    module_path = Path("backend/app/s3_daily_rowset/s2_identity_alignment.py")
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_calls = {"walk", "glob", "rglob", "read_text", "open", "listdir", "scandir"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in {"os", "glob", "pathlib"}
        if isinstance(node, ast.ImportFrom):
            assert node.module not in {"os", "glob", "pathlib", "sqlalchemy"}
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in forbidden_calls:
                raise AssertionError(f"forbidden call detected: {func.attr}")

    assert "MaterializableRow" not in source
    assert "glob(" not in source
    assert "os.walk" not in source
