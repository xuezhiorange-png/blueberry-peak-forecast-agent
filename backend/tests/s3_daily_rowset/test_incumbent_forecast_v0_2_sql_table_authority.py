"""S3-A2 incumbent forecast V0.2/S3 SQL table-name authority tests."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.forecast_artifact import (
    IncumbentForecastArtifactAdapter,
    VersionedIncumbentForecastArtifact,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_sql_table_authority import (
    AUDIT_TABLE_COUNT,
    MATCH_TABLE_COUNT,
    MATCH_TABLE_NAMES,
    NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY,
    bindable_table_names,
    is_bindable,
)
from backend.app.s3_daily_rowset.registry import (
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"


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


def test_bindable_table_set_is_empty() -> None:
    assert MATCH_TABLE_NAMES == ()
    assert MATCH_TABLE_COUNT == 0
    assert AUDIT_TABLE_COUNT == 106
    assert NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY is False
    assert bindable_table_names() == ("s3_incumbent_forecast_replay_identity",)


def test_is_bindable_rejects_audit_not_match_names() -> None:
    assert is_bindable("core_forecast_daily_row") is False
    assert is_bindable("rolling_backtest_binding_row") is False
    assert is_bindable("any_other_table_name") is False


def test_default_replay_source_obtain_returns_empty_tuple() -> None:
    assert IncumbentForecastReplaySource().obtain() == ()


def test_default_catalog_produce_first_blocker_is_no_versioned_forecast() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_default_obtain_consults_authority_without_io() -> None:
    consulted = False

    def _consulted_bindable() -> tuple[str, ...]:
        nonlocal consulted
        consulted = True
        return ()

    with patch(
        "backend.app.s3_daily_rowset.incumbent_forecast_v0_2_sql_table_authority.bindable_table_names",
        _consulted_bindable,
    ):
        assert IncumbentForecastReplaySource().obtain() == ()
        assert consulted is True


def test_explicit_replay_rows_win_over_default_postgres_seam() -> None:
    source = IncumbentForecastReplaySource(
        replay_rows=(_replay_entry(model_id="explicit-model"),),
        v0_2_postgres_obtain=lambda: (_replay_entry(model_id="postgres-model"),),
    )

    rows = source.obtain()

    assert rows == (_replay_entry(model_id="explicit-model"),)


def test_explicit_forecast_injection_does_not_claim_live_repository_facts() -> None:
    forecast = VersionedIncumbentForecastArtifact(
        content_identity_sha256="fixture-forecast-artifact-hash-for-tests-only",
        rows=(_replay_entry(),),
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    assert forecast.content_identity_sha256 != HORIZON_H7_SUCCESS_FIXTURE_HASH

    catalog_result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=IncumbentForecastArtifactAdapter(artifact=forecast),
    ).produce()
    assert catalog_result.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT


def test_frozen_test_catalog_artifact_blob_unchanged() -> None:
    blob = subprocess.check_output(
        ["git", "hash-object", "backend/tests/s3_daily_rowset/test_catalog_artifact.py"],
        text=True,
    ).strip()
    assert blob == TEST_CATALOG_ARTIFACT_PY_BLOB


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
