"""S3-A2 incumbent forecast replay source tests."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    ForbiddenIncumbentForecastArtifactContentError,
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
    source = IncumbentForecastReplaySource()

    assert source.obtain() == ()


def test_default_catalog_produce_is_fail_closed() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_harvest_date_as_forecast_cutoff_returns_empty_tuple() -> None:
    source = IncumbentForecastReplaySource(
        replay_rows=(_replay_entry(),),
        uses_harvest_date_as_forecast_cutoff=True,
    )

    assert source.obtain() == ()


def test_test_intersecting_cutoff_is_excluded() -> None:
    rows = IncumbentForecastReplaySource(
        replay_rows=(
            _replay_entry(cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC)),
            _replay_entry(cutoff=datetime(2026, 2, 15, 16, 0, tzinfo=UTC)),
        ),
    ).obtain()

    assert rows == (_replay_entry(cutoff=datetime(2026, 2, 15, 16, 0, tzinfo=UTC)),)


def test_non_in_season_month_is_excluded() -> None:
    rows = IncumbentForecastReplaySource(
        replay_rows=(
            _replay_entry(cutoff=datetime(2026, 5, 1, 16, 0, tzinfo=UTC)),
            _replay_entry(cutoff=datetime(2026, 2, 10, 16, 0, tzinfo=UTC)),
        ),
    ).obtain()

    assert rows == (_replay_entry(cutoff=datetime(2026, 2, 10, 16, 0, tzinfo=UTC)),)


def test_all_rows_excluded_returns_empty_tuple() -> None:
    source = IncumbentForecastReplaySource(
        replay_rows=(_replay_entry(cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC)),),
    )

    assert source.obtain() == ()


def test_obtain_is_deterministic_sorted_and_deduped() -> None:
    rows = (
        _replay_entry(
            cutoff=datetime(2026, 2, 12, 16, 0, tzinfo=UTC),
            model_id="model-b",
        ),
        _replay_entry(cutoff=datetime(2026, 2, 10, 16, 0, tzinfo=UTC)),
        _replay_entry(cutoff=datetime(2026, 2, 10, 16, 0, tzinfo=UTC)),
    )
    first = IncumbentForecastReplaySource(replay_rows=rows).obtain()
    second = IncumbentForecastReplaySource(replay_rows=tuple(reversed(rows))).obtain()

    assert first == second
    assert first == (
        _replay_entry(cutoff=datetime(2026, 2, 10, 16, 0, tzinfo=UTC)),
        _replay_entry(
            cutoff=datetime(2026, 2, 12, 16, 0, tzinfo=UTC),
            model_id="model-b",
        ),
    )


def test_synthetic_injection_yields_non_empty_rows_without_live_identity_claims() -> None:
    rows = IncumbentForecastReplaySource(
        replay_rows=(_replay_entry(),),
    ).obtain()

    assert rows != ()
    assert HORIZON_H7_SUCCESS_FIXTURE_HASH not in {row.model_id for row in rows}


def test_naive_cutoff_is_rejected() -> None:
    with pytest.raises(ForbiddenIncumbentForecastArtifactContentError):
        IncumbentForecastReplaySource(
            replay_rows=(
                IncumbentForecastArtifactEntry(
                    model_id="incumbent-v0.2",
                    forecast_cutoff_at=datetime(2026, 2, 15, 16, 0),
                    forecast_quantile="P50",
                ),
            ),
        ).obtain()


def test_replay_rows_feed_content_producer_fixture_only_envelope() -> None:
    rows = IncumbentForecastReplaySource(
        replay_rows=(_replay_entry(),),
    ).obtain()
    artifact = IncumbentForecastArtifactContentProducer(replay_rows=rows).produce()

    assert artifact is not None
    assert artifact.catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE
    assert artifact.content_identity_sha256 != HORIZON_H7_SUCCESS_FIXTURE_HASH

    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()
    assert result.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT


def test_module_does_not_scan_repository_or_import_forbidden_modules() -> None:
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

    assert "glob(" not in source
    assert "os.walk" not in source


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
