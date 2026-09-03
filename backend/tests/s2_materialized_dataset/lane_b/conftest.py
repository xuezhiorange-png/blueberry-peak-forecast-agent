"""Shared fixtures for Lane B contract tests."""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.s2_materialized_dataset.lane_b.hashes import (
    CLEANED_SCHEMA_VERSION,
    CLEANING_POLICY_VERSION,
    CLEANING_PROJECTION_VERSION,
    CORRECTION_POLICY_VERSION,
    CORRECTION_SCHEMA_VERSION,
    EXCLUSION_POLICY_VERSION,
    EXCLUSION_SCHEMA_VERSION,
    QUALITY_POLICY_VERSION,
    QUALITY_SCHEMA_VERSION,
    compute_synthetic_raw_import_batch_identity_hash,
    compute_synthetic_raw_source_artifact_identity_hash,
    compute_synthetic_source_row_identity_hash,
    digest,
)
from backend.app.s2_materialized_dataset.lane_b.persistence import (
    S2CleanedDatasetVersionModel,
    S2CleanedRowModel,
    S2CorrectionLedgerEntryModel,
    S2ExclusionLedgerEntryModel,
    S2QualityFindingModel,
)
from backend.app.s2_materialized_dataset.lane_b.schemas import (
    SOURCE_COHORT_ID,
    CleaningBuildRequest,
    SyntheticRawImportBatchIdentity,
    SyntheticRawSourceArtifactIdentity,
    SyntheticSourceRowIdentity,
    SyntheticSourceRowInput,
)

MAPPING_REGISTRY_HASH = digest({"registry": "synthetic-lane-b-mapping-v1"})
ARTIFACT_HASH = "a" * 64
BATCH_PAYLOAD_HASH = "b" * 64
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
LANE_B_MIGRATION_PATH = (
    _BACKEND_ROOT / "alembic" / "versions" / "2af278a20e2a_s2_lane_b_cleaning_quality_correction.py"
)
LANE_B_MIGRATION_REVISION = "2af278a20e2a"
LANE_B_MIGRATION_DOWN_REVISION = "0029_s2_lane_a_raw_ingestion_lineage"
ALEMBIC_SINGLE_HEAD = "f3a9b2c8d1e4"


def _lane_b_migration_module():
    spec = importlib.util.spec_from_file_location(
        "lane_b_migration_0030",
        LANE_B_MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_lane_b_alembic_head_and_revision_contract() -> None:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, f"alembic heads must be exactly one, got {heads!r}"
    assert heads == [ALEMBIC_SINGLE_HEAD], (
        f"alembic heads must be [{ALEMBIC_SINGLE_HEAD!r}], got {heads!r}"
    )
    module = _lane_b_migration_module()
    assert module.revision == LANE_B_MIGRATION_REVISION
    assert module.down_revision == LANE_B_MIGRATION_DOWN_REVISION


@pytest.fixture
def synthetic_artifact() -> SyntheticRawSourceArtifactIdentity:
    return SyntheticRawSourceArtifactIdentity(
        source_system="farm-system",
        source_dataset="synthetic-daily-marketable-net-kg",
        source_version="synthetic-source-v1",
        source_snapshot_reference="synthetic-snapshot-ref-v1",
        source_object_identity="synthetic-object-v1",
        source_artifact_sequence=1,
        schema_version="synthetic-schema-v1",
        mapping_policy_version="mapping-v1",
        source_artifact_identity_version="synthetic-artifact-identity-v1",
    )


@pytest.fixture
def synthetic_batch(
    synthetic_artifact: SyntheticRawSourceArtifactIdentity,
) -> SyntheticRawImportBatchIdentity:
    artifact_hash = compute_synthetic_raw_source_artifact_identity_hash(
        synthetic_artifact.model_dump(mode="python")
    )
    return SyntheticRawImportBatchIdentity(
        raw_source_artifact_identity_hash=artifact_hash,
        external_batch_id="synthetic-batch-1",
        source_system=synthetic_artifact.source_system,
        source_dataset=synthetic_artifact.source_dataset,
        raw_payload_hash=BATCH_PAYLOAD_HASH,
        import_policy_version="synthetic-import-policy-v1",
        schema_version=synthetic_artifact.schema_version,
        mapping_policy_version=synthetic_artifact.mapping_policy_version,
        validation_policy_version="validation-v1",
        source_cohort_id=SOURCE_COHORT_ID,
    )


def make_source_row(
    *,
    batch: SyntheticRawImportBatchIdentity,
    artifact: SyntheticRawSourceArtifactIdentity,
    logical_id: str = "logical-1",
    revision_id: str = "revision-1",
    quantity: Decimal | None = Decimal("12.500000"),
    harvest_date: date = date(2026, 2, 10),
) -> SyntheticSourceRowInput:
    batch_hash = compute_synthetic_raw_import_batch_identity_hash(batch.model_dump(mode="python"))
    identity = SyntheticSourceRowIdentity(
        raw_source_artifact_identity_hash=batch.raw_source_artifact_identity_hash,
        raw_import_batch_identity_hash=batch_hash,
        external_logical_record_id=logical_id,
        external_revision_id=revision_id,
        revision_number=1,
        source_system=artifact.source_system,
        source_row_identity_version="synthetic-source-row-identity-v1",
        schema_version=artifact.schema_version,
        source_version=artifact.source_version,
    )
    return SyntheticSourceRowInput(
        identity=identity,
        season_business_key="2026",
        farm_business_key="farm-master",
        subfarm_business_key="subfarm-master",
        variety_business_key="variety-master",
        harvest_business_date=harvest_date,
        actual_harvest_quantity_kg=quantity,
    )


def make_source_row_identity_hash(row: SyntheticSourceRowInput) -> str:
    return compute_synthetic_source_row_identity_hash(row.identity.model_dump(mode="python"))


@pytest.fixture
def known_quantity_row(
    synthetic_batch: SyntheticRawImportBatchIdentity,
    synthetic_artifact: SyntheticRawSourceArtifactIdentity,
) -> SyntheticSourceRowInput:
    return make_source_row(batch=synthetic_batch, artifact=synthetic_artifact)


@pytest.fixture
def missing_quantity_row(
    synthetic_batch: SyntheticRawImportBatchIdentity,
    synthetic_artifact: SyntheticRawSourceArtifactIdentity,
) -> SyntheticSourceRowInput:
    return make_source_row(
        batch=synthetic_batch,
        artifact=synthetic_artifact,
        logical_id="logical-missing",
        revision_id="revision-missing",
        quantity=None,
    )


@pytest.fixture
def cleaning_build_request(
    synthetic_artifact: SyntheticRawSourceArtifactIdentity,
    synthetic_batch: SyntheticRawImportBatchIdentity,
    known_quantity_row: SyntheticSourceRowInput,
) -> CleaningBuildRequest:
    return CleaningBuildRequest(
        raw_source_artifacts=(synthetic_artifact,),
        raw_import_batches=(synthetic_batch,),
        source_rows=(known_quantity_row,),
        mapping_registry_hash=MAPPING_REGISTRY_HASH,
        cleaning_policy_version=CLEANING_POLICY_VERSION,
        quality_policy_version=QUALITY_POLICY_VERSION,
        correction_policy_version=CORRECTION_POLICY_VERSION,
        exclusion_policy_version=EXCLUSION_POLICY_VERSION,
        cleaned_schema_version=CLEANED_SCHEMA_VERSION,
        cleaning_projection_version=CLEANING_PROJECTION_VERSION,
        quality_schema_version=QUALITY_SCHEMA_VERSION,
        correction_schema_version=CORRECTION_SCHEMA_VERSION,
        exclusion_schema_version=EXCLUSION_SCHEMA_VERSION,
        quality_rule_version="v0-3-s2-quality-rule-v1",
    )


@pytest.fixture
def lane_b_migrated_session() -> Iterator[Session]:
    module = _lane_b_migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    session = maker()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sqlite_session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    tables = [
        S2CleanedDatasetVersionModel.__table__,
        S2CleanedRowModel.__table__,
        S2QualityFindingModel.__table__,
        S2CorrectionLedgerEntryModel.__table__,
        S2ExclusionLedgerEntryModel.__table__,
    ]
    S2CleanedDatasetVersionModel.metadata.create_all(engine, tables=tables)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    session = maker()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
