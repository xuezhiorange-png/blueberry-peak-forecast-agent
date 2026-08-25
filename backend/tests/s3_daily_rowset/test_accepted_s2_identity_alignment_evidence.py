"""S3-A2 accepted S2 identity alignment evidence producer tests."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from backend.app.s3_daily_rowset.accepted_s2_identity_alignment_evidence import (
    AcceptedS2IdentityAlignmentEvidenceProducer,
    ForbiddenAcceptedS2IdentityAlignmentEvidenceError,
    compute_content_identity_sha256,
)
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.forecast_artifact import (
    IncumbentForecastArtifactAdapter,
    VersionedIncumbentForecastArtifact,
)
from backend.app.s3_daily_rowset.registry import (
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.app.s3_daily_rowset.s2_identity_alignment import (
    AcceptedS2IdentityEvidenceRow,
    S2IdentityAlignmentAdapter,
)
from backend.app.s3_daily_rowset.schemas import DatasetIdentity
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY, make_row


def _forecast_artifact() -> VersionedIncumbentForecastArtifact:
    from datetime import UTC, datetime

    from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry

    return VersionedIncumbentForecastArtifact(
        content_identity_sha256="fixture-forecast-artifact-hash-for-tests-only",
        rows=(
            IncumbentForecastArtifactEntry(
                model_id="incumbent-v0.2",
                forecast_cutoff_at=datetime(2026, 2, 15, 16, 0, tzinfo=UTC),
                forecast_quantile="P50",
            ),
        ),
    )


def test_default_produce_returns_none() -> None:
    producer = AcceptedS2IdentityAlignmentEvidenceProducer(dataset_identity=DATASET_IDENTITY)

    assert producer.produce() is None


def test_default_catalog_produce_without_forecast_is_fail_closed() -> None:
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_catalog_produce_with_forecast_only_still_needs_alignment() -> None:
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=IncumbentForecastArtifactAdapter(artifact=_forecast_artifact()),
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT


def test_synthetic_train_validation_rows_produce_versioned_evidence() -> None:
    producer = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(
            make_row(harvest_business_date=date(2026, 2, 10), quantity="1"),
            make_row(
                farm="farm-b",
                harvest_business_date=date(2026, 3, 1),
                quantity="2",
            ),
        ),
    )

    evidence = producer.produce()
    assert evidence is not None
    assert evidence.dataset_id == DATASET_IDENTITY.dataset_id
    assert evidence.dataset_version == DATASET_IDENTITY.dataset_version
    assert (
        evidence.materialized_dataset_identity_sha256
        == DATASET_IDENTITY.materialized_dataset_identity_sha256
    )
    assert evidence.content_identity_sha256 == compute_content_identity_sha256(
        dataset_identity=DATASET_IDENTITY,
        rows=evidence.rows,
    )
    assert evidence.content_identity_sha256 not in {"", "0" * 64, HORIZON_H7_SUCCESS_FIXTURE_HASH}


def test_producer_output_is_deterministic_and_sorted() -> None:
    rows = (
        make_row(farm="farm-b", harvest_business_date=date(2026, 3, 1), quantity="1"),
        make_row(harvest_business_date=date(2026, 2, 10), quantity="2"),
        make_row(harvest_business_date=date(2026, 2, 10), quantity="3"),
    )
    first = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=rows,
    ).produce()
    second = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=tuple(reversed(rows)),
    ).produce()

    assert first is not None
    assert second is not None
    assert first == second
    assert first.rows == (
        AcceptedS2IdentityEvidenceRow(
            season="2025~2026",
            farm="farm-a",
            subfarm="subfarm-1",
            variety="variety-x",
            harvest_business_date=date(2026, 2, 10),
        ),
        AcceptedS2IdentityEvidenceRow(
            season="2025~2026",
            farm="farm-b",
            subfarm="subfarm-1",
            variety="variety-x",
            harvest_business_date=date(2026, 3, 1),
        ),
    )


def test_materializable_row_kg_and_lineage_are_not_carried() -> None:
    row = make_row(harvest_business_date=date(2026, 2, 10), quantity="999")
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(row,),
    ).produce()

    assert evidence is not None
    produced = evidence.rows[0]
    assert isinstance(produced, AcceptedS2IdentityEvidenceRow)
    assert not hasattr(produced, "actual_harvest_quantity_kg")
    assert not hasattr(produced, "source_row_identity")


def test_forbidden_variety_is_excluded() -> None:
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(
            make_row(variety="普鲜", harvest_business_date=date(2026, 2, 10), quantity="1"),
            make_row(harvest_business_date=date(2026, 2, 11), quantity="2"),
        ),
    ).produce()

    assert evidence is not None
    assert len(evidence.rows) == 1
    assert evidence.rows[0].variety == "variety-x"


def test_bason_factory_is_excluded() -> None:
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(
            make_row(farm="巴松加工厂", harvest_business_date=date(2026, 2, 10), quantity="1"),
            make_row(harvest_business_date=date(2026, 2, 11), quantity="2"),
        ),
    ).produce()

    assert evidence is not None
    assert len(evidence.rows) == 1
    assert evidence.rows[0].farm == "farm-a"


def test_non_in_season_month_is_excluded() -> None:
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(
            make_row(harvest_business_date=date(2026, 5, 1), quantity="1"),
            make_row(harvest_business_date=date(2026, 2, 10), quantity="2"),
        ),
    ).produce()

    assert evidence is not None
    assert len(evidence.rows) == 1
    assert evidence.rows[0].harvest_business_date == date(2026, 2, 10)


def test_test_partition_rows_are_rejected() -> None:
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(
            make_row(harvest_business_date=date(2026, 3, 10), quantity="1"),
            make_row(harvest_business_date=date(2026, 2, 10), quantity="2"),
        ),
    ).produce()

    assert evidence is not None
    assert len(evidence.rows) == 1
    assert evidence.rows[0].harvest_business_date == date(2026, 2, 10)


def test_all_rows_excluded_returns_none() -> None:
    producer = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(
            make_row(variety="废果", harvest_business_date=date(2026, 2, 10), quantity="1"),
            make_row(harvest_business_date=date(2026, 3, 10), quantity="2"),
        ),
    )

    assert producer.produce() is None


def test_dataset_identity_mismatch_is_rejected() -> None:
    bad_identity = DatasetIdentity(
        dataset_id="source-002",
        dataset_version="e5-live-v1",
        materialized_dataset_identity_sha256="0" * 64,
    )
    producer = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=bad_identity,
        harvest_rows=(make_row(harvest_business_date=date(2026, 2, 10), quantity="1"),),
    )

    with pytest.raises(ForbiddenAcceptedS2IdentityAlignmentEvidenceError):
        producer.produce()


def test_producer_evidence_injected_into_adapter_yields_live_alignment_kind() -> None:
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(make_row(harvest_business_date=date(2026, 2, 10), quantity="1"),),
    ).produce()
    assert evidence is not None

    adapter = S2IdentityAlignmentAdapter(evidence=evidence)
    assert adapter.alignment_source_kind() == (
        CatalogSourceKind.SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT
    )
    assert adapter.aligned_identities() != ()


def test_none_or_empty_evidence_adapter_remains_unbound() -> None:
    assert S2IdentityAlignmentAdapter().alignment_source_kind() == CatalogSourceKind.UNBOUND
    assert (
        S2IdentityAlignmentAdapter(evidence=None).alignment_source_kind()
        == CatalogSourceKind.UNBOUND
    )


def test_producer_module_does_not_scan_repository_or_read_source_002() -> None:
    module_path = Path("backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py")
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

    assert "forecast_cutoff" not in source
    assert "glob(" not in source
    assert "os.walk" not in source
