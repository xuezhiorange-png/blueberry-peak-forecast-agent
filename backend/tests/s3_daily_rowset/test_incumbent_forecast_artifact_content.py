"""S3-A2 incumbent forecast artifact content producer tests."""

from __future__ import annotations

import ast
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.forecast_artifact import IncumbentForecastArtifactAdapter
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
    compute_content_identity_sha256,
)
from backend.app.s3_daily_rowset.registry import (
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled


def _replay_entry(
    *,
    cutoff: datetime | None = None,
    model_id: str = "incumbent-v0.2",
    quantile: str = "P50",
) -> IncumbentForecastArtifactEntry:
    if cutoff is None:
        cutoff = datetime(2026, 2, 15, 16, 0, tzinfo=UTC)
    return IncumbentForecastArtifactEntry(
        model_id=model_id,
        forecast_cutoff_at=cutoff,
        forecast_quantile=quantile,
    )


def test_default_produce_returns_none() -> None:
    producer = IncumbentForecastArtifactContentProducer()

    assert producer.produce() is None


def test_default_catalog_produce_is_fail_closed() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_synthetic_validation_cutoff_produces_versioned_artifact() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(
            _replay_entry(),
            _replay_entry(
                cutoff=datetime(2026, 2, 12, 16, 0, tzinfo=UTC),
                quantile="P80",
            ),
        ),
    )

    artifact = producer.produce()
    assert artifact is not None
    assert artifact.content_identity_sha256 == compute_content_identity_sha256(
        rows=artifact.rows,
    )
    assert artifact.content_identity_sha256 not in {"", "0" * 64, HORIZON_H7_SUCCESS_FIXTURE_HASH}
    assert artifact.uses_harvest_date_as_forecast_cutoff is False
    assert artifact.catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE


def test_producer_output_is_deterministic_sorted_and_deduped() -> None:
    rows = (
        _replay_entry(
            cutoff=datetime(2026, 2, 12, 16, 0, tzinfo=UTC),
            model_id="model-b",
        ),
        _replay_entry(cutoff=datetime(2026, 2, 10, 16, 0, tzinfo=UTC)),
        _replay_entry(cutoff=datetime(2026, 2, 10, 16, 0, tzinfo=UTC)),
    )
    first = IncumbentForecastArtifactContentProducer(replay_rows=rows).produce()
    second = IncumbentForecastArtifactContentProducer(replay_rows=tuple(reversed(rows))).produce()

    assert first is not None
    assert second is not None
    assert first == second
    assert first.rows == (
        _replay_entry(cutoff=datetime(2026, 2, 10, 16, 0, tzinfo=UTC)),
        _replay_entry(
            cutoff=datetime(2026, 2, 12, 16, 0, tzinfo=UTC),
            model_id="model-b",
        ),
    )


def test_test_intersecting_cutoff_is_excluded() -> None:
    artifact = IncumbentForecastArtifactContentProducer(
        replay_rows=(
            _replay_entry(cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC)),
            _replay_entry(cutoff=datetime(2026, 2, 15, 16, 0, tzinfo=UTC)),
        ),
    ).produce()

    assert artifact is not None
    assert len(artifact.rows) == 1
    assert artifact.rows[0].forecast_cutoff_at == datetime(2026, 2, 15, 16, 0, tzinfo=UTC)


def test_all_rows_excluded_returns_none() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC)),),
    )

    assert producer.produce() is None


def test_harvest_date_as_forecast_cutoff_input_does_not_produce_artifact() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(),),
        uses_harvest_date_as_forecast_cutoff=True,
    )

    assert producer.produce() is None


def test_produced_rows_only_carry_forecast_entry_fields() -> None:
    artifact = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(),),
    ).produce()

    assert artifact is not None
    row = artifact.rows[0]
    assert {field.name for field in fields(row)} == {
        "model_id",
        "forecast_cutoff_at",
        "forecast_quantile",
    }


def test_producer_artifact_injected_into_adapter_follows_existing_rules() -> None:
    artifact = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(),),
    ).produce()
    assert artifact is not None

    adapter = IncumbentForecastArtifactAdapter(artifact=artifact)
    assert adapter.has_versioned_artifact() is True
    assert len(adapter.entries()) == 1
    assert adapter.catalog_source_kind() == CatalogSourceKind.BOUND_FIXTURE

    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=adapter,
    ).produce()
    assert result.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT


def test_module_does_not_scan_repository_or_import_forbidden_modules() -> None:
    module_path = Path("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
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


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
