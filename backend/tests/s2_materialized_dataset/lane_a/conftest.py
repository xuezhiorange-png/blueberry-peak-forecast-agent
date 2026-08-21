from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.base import Base
from backend.app.s2_materialized_dataset.lane_a.persistence import (
    S2RawImportBatchModel,
    S2RawSourceArtifactModel,
    S2SourceRowLineageModel,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def lane_a_session() -> Iterator[Session]:
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///:memory:")
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
def synthetic_artifact_bytes() -> bytes:
    return b"synthetic-lane-a-artifact-bytes-v1"


@pytest.fixture
def synthetic_second_artifact_bytes() -> bytes:
    return b"synthetic-lane-a-artifact-bytes-v2"
