"""S3-A2 incumbent forecast fail-closed obtain→produce→adapter wiring tests."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.forecast_artifact import (
    IncumbentForecastArtifactAdapter,
    VersionedIncumbentForecastArtifact,
)
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.registry import CatalogSourceKind
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

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


def test_default_catalog_produce_remains_no_versioned() -> None:
    result = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()

    assert result.reason_code == CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT


def test_default_producer_and_adapter_do_not_claim_live_kind() -> None:
    producer = IncumbentForecastArtifactContentProducer()
    adapter = IncumbentForecastArtifactAdapter()

    assert producer.produce() is None
    assert producer.declared_catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE
    assert adapter.has_versioned_artifact() is False
    assert adapter.catalog_source_kind() == CatalogSourceKind.UNBOUND
    assert adapter.catalog_source_kind() != LIVE_ENVELOPE_KIND


def test_injected_adapter_artifact_wins_over_producer_replay_rows_and_obtain() -> None:
    injected = VersionedIncumbentForecastArtifact(
        content_identity_sha256="injected-forecast-artifact-hash-for-wiring-tests",
        rows=(_replay_entry(model_id="injected-model"),),
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
    )
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(model_id="producer-model"),),
        replay_source=IncumbentForecastReplaySource(
            replay_rows=(_replay_entry(model_id="obtain-model"),),
        ),
    )
    adapter = IncumbentForecastArtifactAdapter(artifact=injected, producer=producer)

    assert adapter.has_versioned_artifact() is True
    assert adapter.entries()[0].model_id == "injected-model"
    assert adapter.catalog_source_kind() == CatalogSourceKind.BOUND_FIXTURE


def test_adapter_without_injection_uses_producer_replay_rows_with_bound_fixture() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(model_id="producer-model"),),
    )
    adapter = IncumbentForecastArtifactAdapter(producer=producer)

    assert adapter.has_versioned_artifact() is True
    assert adapter.entries()[0].model_id == "producer-model"
    assert adapter.catalog_source_kind() == CatalogSourceKind.BOUND_FIXTURE
    assert adapter.catalog_source_kind() != LIVE_ENVELOPE_KIND


def test_producer_uses_obtain_when_replay_rows_empty() -> None:
    obtain_row = _replay_entry(model_id="obtain-model")
    producer = IncumbentForecastArtifactContentProducer(
        replay_source=IncumbentForecastReplaySource(replay_rows=(obtain_row,)),
    )

    artifact = producer.produce()

    assert artifact is not None
    assert artifact.rows[0].model_id == "obtain-model"
    assert artifact.catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE


def test_producer_explicit_replay_rows_win_over_obtain() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(model_id="explicit-model"),),
        replay_source=IncumbentForecastReplaySource(
            replay_rows=(_replay_entry(model_id="obtain-model"),),
        ),
    )

    artifact = producer.produce()

    assert artifact is not None
    assert artifact.rows[0].model_id == "explicit-model"


def test_empty_obtain_yields_none_produce_and_unbound_adapter() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_source=IncumbentForecastReplaySource(),
    )
    adapter = IncumbentForecastArtifactAdapter(producer=producer)

    assert producer.produce() is None
    assert adapter.has_versioned_artifact() is False
    assert adapter.catalog_source_kind() == CatalogSourceKind.UNBOUND


def test_harvest_as_cutoff_returns_none_without_calling_obtain() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_rows=(_replay_entry(),),
        replay_source=IncumbentForecastReplaySource(
            replay_rows=(_replay_entry(model_id="obtain-model"),),
        ),
        uses_harvest_date_as_forecast_cutoff=True,
    )
    adapter = IncumbentForecastArtifactAdapter(producer=producer)

    assert producer.produce() is None
    assert adapter.has_versioned_artifact() is False
    assert adapter.entries() == ()
    assert adapter.catalog_source_kind() == CatalogSourceKind.UNBOUND


def test_obtain_with_live_declaration_assigns_live_envelope_not_by_default() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_source=IncumbentForecastReplaySource(
            replay_rows=(_replay_entry(),),
        ),
        declared_catalog_source_kind=LIVE_ENVELOPE_KIND,
    )

    artifact = producer.produce()

    assert artifact is not None
    assert artifact.catalog_source_kind == LIVE_ENVELOPE_KIND


def test_default_wiring_does_not_assign_live_envelope_from_obtain() -> None:
    producer = IncumbentForecastArtifactContentProducer(
        replay_source=IncumbentForecastReplaySource(
            replay_rows=(_replay_entry(),),
        ),
    )

    artifact = producer.produce()

    assert artifact is not None
    assert artifact.catalog_source_kind == CatalogSourceKind.BOUND_FIXTURE
    assert artifact.catalog_source_kind != LIVE_ENVELOPE_KIND


def test_content_module_has_no_top_level_replay_source_import() -> None:
    module_path = Path("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "incumbent_forecast_replay_source" not in alias.name
        if isinstance(node, ast.ImportFrom):
            assert node.module is None or "incumbent_forecast_replay_source" not in node.module

    pre_type_checking = source.split("if TYPE_CHECKING:")[0]
    forbidden_import = (
        "from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import"
    )
    forbidden_module_import = (
        "import backend.app.s3_daily_rowset.incumbent_forecast_replay_source"
    )
    assert forbidden_import not in pre_type_checking
    assert forbidden_module_import not in pre_type_checking


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
