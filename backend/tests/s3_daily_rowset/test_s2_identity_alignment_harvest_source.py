"""S3-A2 S2 identity alignment harvest source tests."""

from __future__ import annotations

import ast
import subprocess
from datetime import date
from pathlib import Path

from backend.app.s3_daily_rowset.accepted_s2_identity_alignment_evidence import (
    AcceptedS2IdentityAlignmentEvidenceProducer,
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
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY, make_row

CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"


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
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )


def test_default_obtain_returns_empty_tuple() -> None:
    source = S2IdentityAlignmentHarvestSource()

    assert source.obtain() == ()


def test_default_producer_produce_returns_none() -> None:
    producer = AcceptedS2IdentityAlignmentEvidenceProducer(dataset_identity=DATASET_IDENTITY)

    assert producer.produce() is None


def test_default_catalog_produce_first_blocker_is_no_versioned_forecast() -> None:
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_forecast_non_empty_and_default_alignment_empty_is_no_s2_identity_alignment() -> None:
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=IncumbentForecastArtifactAdapter(artifact=_forecast_artifact()),
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT


def test_explicit_harvest_rows_win_over_harvest_source() -> None:
    producer_row = make_row(harvest_business_date=date(2026, 2, 10), quantity="1")
    source_row = make_row(
        farm="farm-b",
        harvest_business_date=date(2026, 2, 11),
        quantity="2",
    )
    producer = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(producer_row,),
        harvest_source=S2IdentityAlignmentHarvestSource(harvest_rows=(source_row,)),
    )

    evidence = producer.produce()

    assert evidence is not None
    assert len(evidence.rows) == 1
    assert evidence.rows[0].farm == producer_row.farm.strip()
    assert evidence.rows[0].harvest_business_date == producer_row.harvest_business_date


def test_harvest_source_obtain_yields_evidence_when_producer_harvest_rows_empty() -> None:
    source_row = make_row(harvest_business_date=date(2026, 2, 10), quantity="1")
    producer = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_source=S2IdentityAlignmentHarvestSource(harvest_rows=(source_row,)),
    )

    evidence = producer.produce()

    assert evidence is not None
    assert evidence.content_identity_sha256 == compute_content_identity_sha256(
        dataset_identity=DATASET_IDENTITY,
        rows=evidence.rows,
    )
    assert evidence.content_identity_sha256 != HORIZON_H7_SUCCESS_FIXTURE_HASH


def test_test_partition_dates_are_excluded_from_obtain() -> None:
    rows = S2IdentityAlignmentHarvestSource(
        harvest_rows=(
            make_row(harvest_business_date=date(2026, 3, 10), quantity="1"),
            make_row(harvest_business_date=date(2026, 2, 10), quantity="2"),
        ),
    ).obtain()

    assert rows == (make_row(harvest_business_date=date(2026, 2, 10), quantity="2"),)


def test_all_test_partition_rows_excluded_returns_empty_tuple() -> None:
    source = S2IdentityAlignmentHarvestSource(
        harvest_rows=(make_row(harvest_business_date=date(2026, 3, 15), quantity="1"),),
    )

    assert source.obtain() == ()


def test_synthetic_injection_does_not_claim_live_repository_facts() -> None:
    evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_source=S2IdentityAlignmentHarvestSource(
            harvest_rows=(make_row(harvest_business_date=date(2026, 2, 10), quantity="1"),),
        ),
    ).produce()

    assert evidence is not None
    assert evidence.content_identity_sha256 != HORIZON_H7_SUCCESS_FIXTURE_HASH

    catalog_result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()
    assert (
        catalog_result.reason_code
        == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    )


def test_catalog_source_kind_comes_from_forecast_not_harvest_source() -> None:
    forecast = _forecast_artifact()
    alignment_evidence = AcceptedS2IdentityAlignmentEvidenceProducer(
        dataset_identity=DATASET_IDENTITY,
        harvest_rows=(make_row(harvest_business_date=date(2026, 2, 10), quantity="1"),),
    ).produce()
    assert alignment_evidence is not None

    from backend.app.s3_daily_rowset.registry import InMemoryEvaluationInstanceCatalog
    from backend.app.s3_daily_rowset.s2_identity_alignment import S2IdentityAlignmentAdapter

    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=IncumbentForecastArtifactAdapter(artifact=forecast),
        alignment_port=S2IdentityAlignmentAdapter(evidence=alignment_evidence),
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.ARTIFACT_PRODUCED
    assert isinstance(result.catalog, InMemoryEvaluationInstanceCatalog)
    assert result.catalog.catalog_source_kind == forecast.catalog_source_kind
    assert result.catalog.catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE


def test_frozen_catalog_artifact_blobs_unchanged() -> None:
    catalog_blob = subprocess.check_output(
        ["git", "hash-object", "backend/app/s3_daily_rowset/catalog_artifact.py"],
        text=True,
    ).strip()
    test_blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()

    assert catalog_blob == CATALOG_ARTIFACT_PY_BLOB
    assert test_blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_module_does_not_scan_repository_or_import_forbidden_modules() -> None:
    module_path = Path("backend/app/s3_daily_rowset/s2_identity_alignment_harvest_source.py")
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

    assert "glob(" not in source
    assert "os.walk" not in source


def test_producer_has_no_top_level_harvest_source_import() -> None:
    module_path = Path("backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "s2_identity_alignment_harvest_source" not in alias.name
        if isinstance(node, ast.ImportFrom):
            assert node.module != "backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source"


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
