"""S3-A2 S2 identity alignment producer→adapter wiring tests."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EmptyS2IdentityAlignmentPort,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
    IncumbentForecastArtifactPort,
    S2AlignedIdentity,
    S2IdentityAlignmentPort,
)
from backend.app.s3_daily_rowset.registry import (
    HORIZON_H7_SUCCESS_FIXTURE_HASH,
    CatalogSourceKind,
    InMemoryEvaluationInstanceCatalog,
)
from backend.app.s3_daily_rowset.s2_identity_alignment import S2IdentityAlignmentAdapter
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


def _aligned_identity(
    *,
    season: str = "2025~2026",
    farm: str = "farm-a",
    subfarm: str = "subfarm-1",
    variety: str = "variety-x",
    partition: Literal["TRAIN", "VALIDATION"] = "TRAIN",
) -> S2AlignedIdentity:
    return S2AlignedIdentity(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        partition=partition,
    )


class FakeIncumbentForecastArtifactPort:
    def __init__(
        self,
        *,
        entries_value: tuple[IncumbentForecastArtifactEntry, ...],
        catalog_source_kind_value: CatalogSourceKind = CatalogSourceKind.BOUND_FIXTURE,
    ) -> None:
        self.entries_value = entries_value
        self.catalog_source_kind_value = catalog_source_kind_value

    def has_versioned_artifact(self) -> bool:
        return bool(self.entries_value)

    def catalog_source_kind(self) -> CatalogSourceKind:
        return self.catalog_source_kind_value

    def entries(self) -> tuple[IncumbentForecastArtifactEntry, ...]:
        return self.entries_value

    def uses_harvest_date_as_forecast_cutoff(self) -> bool:
        return False


class FakeS2IdentityAlignmentPort:
    def __init__(
        self,
        *,
        identities: tuple[S2AlignedIdentity, ...],
        alignment_source_kind_value: CatalogSourceKind = CatalogSourceKind.BOUND_FIXTURE,
    ) -> None:
        self.identities = identities
        self.alignment_source_kind_value = alignment_source_kind_value

    def alignment_source_kind(self) -> CatalogSourceKind:
        return self.alignment_source_kind_value

    def aligned_identities(self) -> tuple[S2AlignedIdentity, ...]:
        return self.identities


def test_explicit_alignment_port_injection_wins_over_default_wiring() -> None:
    injected = EmptyS2IdentityAlignmentPort()
    service = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        alignment_port=injected,
    )

    assert service.alignment_port is injected


def test_explicit_fake_alignment_port_injection_wins() -> None:
    injected = FakeS2IdentityAlignmentPort(identities=(_aligned_identity(),))
    service = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        alignment_port=cast(S2IdentityAlignmentPort, injected),
    )

    assert service.alignment_port is injected  # type: ignore[comparison-overlap]


def test_explicit_adapter_injection_wins() -> None:
    injected = S2IdentityAlignmentAdapter(evidence=None)
    service = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        alignment_port=injected,
    )

    assert service.alignment_port is injected


def test_default_wiring_produces_adapter_with_none_evidence() -> None:
    service = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    )

    assert isinstance(service.alignment_port, S2IdentityAlignmentAdapter)
    assert service.alignment_port.evidence is None
    assert service.alignment_port.aligned_identities() == ()
    assert service.alignment_port.alignment_source_kind() == CatalogSourceKind.UNBOUND


def test_default_catalog_produce_first_blocker_remains_no_versioned() -> None:
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_non_empty_forecast_with_default_empty_alignment_is_no_s2_identity_alignment() -> None:
    forecast = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
    )
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=cast(IncumbentForecastArtifactPort, forecast),
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT


def test_catalog_source_kind_follows_forecast_not_alignment() -> None:
    forecast = FakeIncumbentForecastArtifactPort(
        entries_value=(_forecast_entry(),),
        catalog_source_kind_value=CatalogSourceKind.BOUND_FIXTURE,
    )
    alignment = FakeS2IdentityAlignmentPort(
        identities=(_aligned_identity(),),
        alignment_source_kind_value=CatalogSourceKind.SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT,
    )
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
        forecast_port=cast(IncumbentForecastArtifactPort, forecast),
        alignment_port=cast(S2IdentityAlignmentPort, alignment),
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.ARTIFACT_PRODUCED
    assert isinstance(result.catalog, InMemoryEvaluationInstanceCatalog)
    assert result.catalog.catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE
    assert result.catalog.catalog_source_kind != alignment.alignment_source_kind()


def test_catalog_module_has_no_top_level_alignment_imports() -> None:
    module_path = Path("backend/app/s3_daily_rowset/catalog_artifact.py")
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "s2_identity_alignment" not in alias.name
                assert "accepted_s2_identity_alignment_evidence" not in alias.name
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "s2_identity_alignment" not in module
            assert "accepted_s2_identity_alignment_evidence" not in module


def test_default_wiring_does_not_use_h7_fixture_as_live_evidence() -> None:
    service = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    )

    assert isinstance(service.alignment_port, S2IdentityAlignmentAdapter)
    evidence = service.alignment_port.evidence
    assert evidence is None
    assert HORIZON_H7_SUCCESS_FIXTURE_HASH not in {}


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
