"""S3-A2 incumbent forecast V0.2 postgres obtain tests."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.registry import (
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled

LIVE_ENVELOPE_KIND = CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF


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


def test_default_obtain_returns_empty_tuple() -> None:
    assert IncumbentForecastReplaySource().obtain() == ()


def test_default_catalog_produce_remains_no_versioned() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_harvest_cutoff_skips_postgres_seam_even_when_injected() -> None:
    source = IncumbentForecastReplaySource(
        uses_harvest_date_as_forecast_cutoff=True,
        v0_2_postgres_obtain=lambda: (_replay_entry(model_id="postgres-model"),),
    )

    assert source.obtain() == ()


def test_explicit_replay_rows_win_over_postgres_seam() -> None:
    source = IncumbentForecastReplaySource(
        replay_rows=(_replay_entry(model_id="explicit-model"),),
        v0_2_postgres_obtain=lambda: (_replay_entry(model_id="postgres-model"),),
    )

    rows = source.obtain()

    assert rows == (_replay_entry(model_id="explicit-model"),)


def test_empty_replay_rows_with_default_postgres_seam_returns_empty() -> None:
    assert IncumbentForecastReplaySource(replay_rows=()).obtain() == ()


def test_injected_postgres_rows_project_to_non_empty_without_live_kind() -> None:
    rows = IncumbentForecastReplaySource(
        v0_2_postgres_obtain=lambda: (_replay_entry(model_id="postgres-model"),),
    ).obtain()

    assert rows == (_replay_entry(model_id="postgres-model"),)

    artifact = IncumbentForecastArtifactContentProducer(
        replay_source=IncumbentForecastReplaySource(
            v0_2_postgres_obtain=lambda: (_replay_entry(model_id="postgres-model"),),
        ),
    ).produce()

    assert artifact is not None
    assert artifact.catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE
    assert artifact.catalog_source_kind != LIVE_ENVELOPE_KIND
    assert artifact.content_identity_sha256 != HORIZON_H7_SUCCESS_FIXTURE_HASH

    catalog = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()
    assert catalog.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT


def test_postgres_test_intersecting_rows_exclude_to_empty() -> None:
    rows = IncumbentForecastReplaySource(
        v0_2_postgres_obtain=lambda: (
            _replay_entry(cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC)),
        ),
    ).obtain()

    assert rows == ()


def test_postgres_non_in_season_rows_exclude_to_empty() -> None:
    rows = IncumbentForecastReplaySource(
        v0_2_postgres_obtain=lambda: (
            _replay_entry(cutoff=datetime(2026, 5, 1, 16, 0, tzinfo=UTC)),
        ),
    ).obtain()

    assert rows == ()


def test_module_has_no_sql_table_names_or_forbidden_imports() -> None:
    module_path = Path("backend/app/s3_daily_rowset/incumbent_forecast_replay_source.py")
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

    lowered = source.lower()
    assert "incumbent_forecast_v0_2_live_postgres_read" in lowered
    assert "create table" not in lowered
    assert "postgresql://" not in lowered
    assert "dsn" not in lowered
    assert "core_forecast_daily_row" not in lowered
    assert "rolling_backtest_binding_row" not in lowered


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
