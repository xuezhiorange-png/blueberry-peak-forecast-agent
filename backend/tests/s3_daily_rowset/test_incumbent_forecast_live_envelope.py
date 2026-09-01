"""S3-A2 incumbent forecast live envelope assignment tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.forecast_artifact import IncumbentForecastArtifactAdapter
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    ForbiddenIncumbentForecastArtifactContentError,
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.registry import (
    FORBIDDEN_CATALOG_SOURCE_KINDS,
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


def test_default_produce_returns_none_with_default_declared_kind() -> None:
    producer = IncumbentForecastArtifactContentProducer()

    assert producer.declared_catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE
    assert producer.produce() is None


def test_injected_rows_without_live_declaration_remain_bound_fixture() -> None:
    artifact = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(),),
    ).produce()

    assert artifact is not None
    assert artifact.catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE
    assert artifact.catalog_source_kind != LIVE_ENVELOPE_KIND


def test_declared_live_with_non_empty_validation_window_rows_assigns_live_envelope() -> None:
    artifact = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(cutoff=datetime(2026, 2, 15, 16, 0, tzinfo=UTC)),),
        declared_catalog_source_kind=LIVE_ENVELOPE_KIND,
    ).produce()

    assert artifact is not None
    assert artifact.catalog_source_kind == LIVE_ENVELOPE_KIND


def test_declared_live_with_empty_replay_rows_returns_none() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        declared_catalog_source_kind=LIVE_ENVELOPE_KIND,
    )

    assert producer.produce() is None


def test_declared_live_with_all_test_intersecting_rows_excluded_returns_none() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC)),),
        declared_catalog_source_kind=LIVE_ENVELOPE_KIND,
    )

    assert producer.produce() is None


def test_harvest_date_as_cutoff_returns_none_even_when_declared_live() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(),),
        declared_catalog_source_kind=LIVE_ENVELOPE_KIND,
        uses_harvest_date_as_forecast_cutoff=True,
    )

    assert producer.produce() is None


@pytest.mark.parametrize(
    "declared_kind",
    [
        CatalogSourceKind.UNBOUND,
        CatalogSourceKind.SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT,
        *FORBIDDEN_CATALOG_SOURCE_KINDS,
    ],
)
def test_forbidden_declared_kind_with_non_empty_rows_raises(
    declared_kind: CatalogSourceKind,
) -> None:
    with pytest.raises(ForbiddenIncumbentForecastArtifactContentError):
        IncumbentForecastArtifactContentProducer(
            replay_rows=(_replay_entry(),),
            declared_catalog_source_kind=declared_kind,
        ).produce()


def test_live_artifact_injected_into_adapter_exposes_live_catalog_source_kind() -> None:
    artifact = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(),),
        declared_catalog_source_kind=LIVE_ENVELOPE_KIND,
    ).produce()
    assert artifact is not None

    adapter = IncumbentForecastArtifactAdapter(artifact=artifact)

    assert adapter.catalog_source_kind() == LIVE_ENVELOPE_KIND


def test_default_catalog_produce_is_fail_closed() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_content_identity_is_not_h7_fixture_and_produce_is_deterministic() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(),),
        declared_catalog_source_kind=LIVE_ENVELOPE_KIND,
    )
    first = producer.produce()
    second = producer.produce()

    assert first is not None
    assert second is not None
    assert first == second
    assert first.content_identity_sha256 != HORIZON_H7_SUCCESS_FIXTURE_HASH
    assert first.content_identity_sha256 not in {"", "0" * 64}


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
