"""S3-A2 incumbent forecast artifact adapter tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.forecast_artifact import (
    ForbiddenForecastArtifactError,
    IncumbentForecastArtifactAdapter,
    VersionedIncumbentForecastArtifact,
)
from backend.app.s3_daily_rowset.registry import (
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY


def _forecast_entry(
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


def _artifact(
    *,
    content_identity_sha256: str = "fixture-forecast-artifact-hash-for-tests-only",
    rows: tuple[IncumbentForecastArtifactEntry, ...] | None = None,
    uses_harvest_date_as_forecast_cutoff: bool = False,
) -> VersionedIncumbentForecastArtifact:
    if rows is None:
        rows = (_forecast_entry(),)
    return VersionedIncumbentForecastArtifact(
        content_identity_sha256=content_identity_sha256,
        rows=rows,
        uses_harvest_date_as_forecast_cutoff=uses_harvest_date_as_forecast_cutoff,
    )


def test_default_adapter_is_fail_closed() -> None:
    adapter = IncumbentForecastArtifactAdapter()

    assert adapter.has_versioned_artifact() is False
    assert adapter.entries() == ()
    assert adapter.catalog_source_kind() == CatalogSourceKind.UNBOUND
    assert adapter.uses_harvest_date_as_forecast_cutoff() is False

    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    assert result.catalog_identity_sha256 is None
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.no_bindable_catalog_in_repository is True


def test_injected_fixture_has_versioned_artifact_but_produce_still_needs_alignment() -> None:
    adapter = IncumbentForecastArtifactAdapter(artifact=_artifact())
    assert adapter.has_versioned_artifact() is True
    assert len(adapter.entries()) == 1

    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=adapter,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    assert result.catalog_identity_sha256 is None
    assert result.evaluation_instance_registry_available is False
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.no_bindable_catalog_in_repository is True


def test_test_intersecting_cutoff_is_not_exposed_in_entries() -> None:
    adapter = IncumbentForecastArtifactAdapter(
        artifact=_artifact(
            rows=(_forecast_entry(cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC)),),
        ),
    )

    assert adapter.has_versioned_artifact() is False
    assert adapter.entries() == ()


def test_test_intersecting_horizon_window_is_not_exposed_in_entries() -> None:
    adapter = IncumbentForecastArtifactAdapter(
        artifact=_artifact(
            rows=(_forecast_entry(cutoff=datetime(2026, 3, 9, 16, 0, tzinfo=UTC)),),
        ),
    )

    assert adapter.entries() == ()


def test_harvest_date_as_forecast_cutoff_is_fail_closed() -> None:
    adapter = IncumbentForecastArtifactAdapter(
        artifact=_artifact(uses_harvest_date_as_forecast_cutoff=True),
    )

    assert adapter.uses_harvest_date_as_forecast_cutoff() is True
    assert adapter.has_versioned_artifact() is True

    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=adapter,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.HARVEST_DATE_AS_CUTOFF_FORBIDDEN
    assert result.catalog_identity_sha256 is None


@pytest.mark.parametrize(
    "forbidden_hash",
    [
        HORIZON_H7_SUCCESS_FIXTURE_HASH,
        "",
        "0" * 64,
    ],
)
def test_forbidden_forecast_artifact_hashes_are_rejected(forbidden_hash: str) -> None:
    with pytest.raises(ForbiddenForecastArtifactError):
        _artifact(content_identity_sha256=forbidden_hash)


def test_forbidden_catalog_source_kind_is_rejected() -> None:
    with pytest.raises(ForbiddenForecastArtifactError):
        VersionedIncumbentForecastArtifact(
            content_identity_sha256="fixture-forecast-artifact-hash-for-tests-only",
            rows=(_forecast_entry(),),
            catalog_source_kind=CatalogSourceKind.S2_HARVEST_GRAIN,
        )
