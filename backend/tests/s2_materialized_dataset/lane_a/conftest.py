from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    S2RawImportBatchModel,
    S2RawSourceArtifactModel,
    S2SourceRowLineageModel,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_LANE_A_MIGRATION_PATH = (
    _BACKEND_ROOT / "alembic" / "versions" / "0029_s2_lane_a_raw_ingestion_lineage.py"
)


def _lane_a_migration_module():
    spec = importlib.util.spec_from_file_location(
        "lane_a_migration_0029",
        _LANE_A_MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def lane_a_session() -> Iterator[Session]:
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            S2RawSourceArtifactModel.__table__,
            S2RawImportBatchModel.__table__,
            S2SourceRowLineageModel.__table__,
        ],
    )
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    session = maker()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def lane_a_migrated_session() -> Iterator[Session]:
    module = _lane_a_migration_module()
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
def synthetic_artifact_bytes() -> bytes:
    return b"synthetic-lane-a-artifact-bytes-v1"


@pytest.fixture
def synthetic_second_artifact_bytes() -> bytes:
    return b"synthetic-lane-a-artifact-bytes-v2"
