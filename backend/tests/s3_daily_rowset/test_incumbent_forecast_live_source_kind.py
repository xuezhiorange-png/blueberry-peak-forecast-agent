"""S3-A2 incumbent forecast live catalog source kind tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

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
    ALLOWED_ALIGNMENT_SOURCE_KINDS,
    FORBIDDEN_CATALOG_SOURCE_KINDS,
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled

LIVE_FORECAST_CATALOG_SOURCE_KIND = CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF


def _is_live_forecast_catalog_source_kind(kind: CatalogSourceKind) -> bool:
    return kind == LIVE_FORECAST_CATALOG_SOURCE_KIND


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


def test_live_catalog_source_kind_enum_member_exists_and_value_equals_name() -> None:
    assert hasattr(CatalogSourceKind, "V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF")
    assert (
        CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
        == "V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF"
    )
    assert (
        CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF.name
        == "V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF"
    )


def test_live_catalog_source_kind_not_in_forbidden_set() -> None:
    assert LIVE_FORECAST_CATALOG_SOURCE_KIND not in FORBIDDEN_CATALOG_SOURCE_KINDS


def test_live_catalog_source_kind_not_in_allowed_alignment_set() -> None:
    assert LIVE_FORECAST_CATALOG_SOURCE_KIND not in ALLOWED_ALIGNMENT_SOURCE_KINDS


@pytest.mark.parametrize(
    "kind",
    [
        CatalogSourceKind.UNBOUND,
        CatalogSourceKind.BOUND_FIXTURE,
        CatalogSourceKind.SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT,
        *FORBIDDEN_CATALOG_SOURCE_KINDS,
    ],
)
def test_non_live_kinds_are_not_live_forecast_catalog_source_kind(
    kind: CatalogSourceKind,
) -> None:
    assert not _is_live_forecast_catalog_source_kind(kind)


def test_only_live_kind_is_live_forecast_catalog_source_kind() -> None:
    assert _is_live_forecast_catalog_source_kind(LIVE_FORECAST_CATALOG_SOURCE_KIND)
    for kind in CatalogSourceKind:
        if kind == LIVE_FORECAST_CATALOG_SOURCE_KIND:
            continue
        assert not _is_live_forecast_catalog_source_kind(kind)


def test_default_catalog_produce_is_fail_closed() -> None:
    with patch_handoff_disabled():
        result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_default_replay_source_obtain_returns_empty_tuple() -> None:
    source = IncumbentForecastReplaySource()

    assert source.obtain() == ()


def test_default_content_producer_produce_returns_none() -> None:
    producer = IncumbentForecastArtifactContentProducer()

    assert producer.produce() is None


def test_injected_test_envelope_remains_bound_fixture_not_live_kind() -> None:
    rows = IncumbentForecastReplaySource(
        replay_rows=(_replay_entry(),),
    ).obtain()
    artifact = IncumbentForecastArtifactContentProducer(replay_rows=rows).produce()

    assert artifact is not None
    assert artifact.catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE
    assert artifact.catalog_source_kind != LIVE_FORECAST_CATALOG_SOURCE_KIND
    assert artifact.content_identity_sha256 != HORIZON_H7_SUCCESS_FIXTURE_HASH


def test_h7_fixture_hash_is_not_live_forecast_catalog_source_kind() -> None:
    assert HORIZON_H7_SUCCESS_FIXTURE_HASH != LIVE_FORECAST_CATALOG_SOURCE_KIND
    assert HORIZON_H7_SUCCESS_FIXTURE_HASH != LIVE_FORECAST_CATALOG_SOURCE_KIND.value


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
