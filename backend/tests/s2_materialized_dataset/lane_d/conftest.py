"""Shared fixtures for Lane D materialized dataset tests."""

from __future__ import annotations

import hashlib
import importlib.util
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.s2_materialized_dataset.shared.contracts import (
    SOURCE_COHORT_ID,
    SOURCE_COHORT_MANIFEST_SHA256,
    MaterializableRow,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
LANE_D_MIGRATION_PATH = (
    _BACKEND_ROOT / "alembic" / "versions" / "d4e8f1a2b3c5_s2_lane_d_materialized_dataset.py"
)
LANE_D_MIGRATION_REVISION = "d4e8f1a2b3c5"
LANE_D_MIGRATION_DOWN_REVISION = "8c6aead9f8e9"
ALEMBIC_SINGLE_HEAD = "f3a9b2c8d1e4"


def _identity_hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class FakeLaneA:
    source_cohort_id: str = SOURCE_COHORT_ID
    source_cohort_manifest_sha256: str = SOURCE_COHORT_MANIFEST_SHA256
    raw_policy_version: str = "v0-3-s2-raw-policy-v1"
    lineage_present: bool = True

    def lineage_identity_present(self) -> bool:
        return self.lineage_present


@dataclass(frozen=True, slots=True)
class FakeLaneB:
    cleaned_dataset_version_identity: str = "cleaned-dataset-v1"
    cleaning_policy_version: str = "v0-3-s2-cleaning-policy-v1"
    correction_policy_version: str = "v0-3-s2-correction-policy-v1"
    exclusion_policy_version: str = "v0-3-s2-exclusion-policy-v1"
    rows: tuple[MaterializableRow, ...] = ()
    lineage_present: bool = True

    def iter_materializable_rows(self) -> tuple[MaterializableRow, ...]:
        return self.rows

    def lineage_identity_present(self) -> bool:
        return self.lineage_present


@dataclass(frozen=True, slots=True)
class FakeLaneC:
    visibility_policy_version: str = "v0-3-s2-visibility-policy-v1"
    revision_winner_policy_version: str = "v0-3-s2-revision-winner-policy-v1"
    lineage_present: bool = True

    def lineage_identity_present(self) -> bool:
        return self.lineage_present


@dataclass(frozen=True, slots=True)
class FakeUpstream:
    lane_a: FakeLaneA
    lane_b: FakeLaneB
    lane_c: FakeLaneC


def _lane_d_migration_module():
    spec = importlib.util.spec_from_file_location(
        "lane_d_migration_0032",
        LANE_D_MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_lane_d_alembic_head_and_revision_contract() -> None:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, f"alembic heads must be exactly one, got {heads!r}"
    assert heads == [ALEMBIC_SINGLE_HEAD], (
        f"alembic heads must be [{ALEMBIC_SINGLE_HEAD!r}], got {heads!r}"
    )
    module = _lane_d_migration_module()
    assert module.revision == LANE_D_MIGRATION_REVISION
    assert module.down_revision == LANE_D_MIGRATION_DOWN_REVISION


def make_row(
    *,
    season: str = "2025-26",
    farm: str = "farm-a",
    subfarm: str = "subfarm-1",
    variety: str = "variety-x",
    harvest_business_date: date = date(2025, 9, 1),
    quantity: str = "100.0",
    source_row_identity: str | None = None,
    cleaned_row_identity: str | None = None,
    pit_visibility_identity: str | None = None,
    revision_winner_identity: str | None = None,
) -> MaterializableRow:
    return MaterializableRow(
        season=season,
        farm=farm,
        subfarm=subfarm,
        variety=variety,
        harvest_business_date=harvest_business_date,
        actual_harvest_quantity_kg=Decimal(quantity),
        source_row_identity=_identity_hash("source-row-1")
        if source_row_identity is None
        else source_row_identity,
        cleaned_row_identity=_identity_hash("cleaned-row-1")
        if cleaned_row_identity is None
        else cleaned_row_identity,
        pit_visibility_identity=_identity_hash("pit-vis-1")
        if pit_visibility_identity is None
        else pit_visibility_identity,
        revision_winner_identity=_identity_hash("rev-win-1")
        if revision_winner_identity is None
        else revision_winner_identity,
    )


def complete_upstream(rows: tuple[MaterializableRow, ...] | None = None) -> FakeUpstream:
    sample_rows = rows or (
        make_row(harvest_business_date=date(2025, 9, 1)),
        make_row(
            harvest_business_date=date(2026, 2, 15),
            source_row_identity=_identity_hash("source-row-2"),
            cleaned_row_identity=_identity_hash("cleaned-row-2"),
            pit_visibility_identity=_identity_hash("pit-vis-2"),
            revision_winner_identity=_identity_hash("rev-win-2"),
        ),
    )
    return FakeUpstream(
        lane_a=FakeLaneA(),
        lane_b=FakeLaneB(rows=sample_rows),
        lane_c=FakeLaneC(),
    )


def build_timestamps() -> datetime:
    return datetime(2026, 4, 1, 0, 0, tzinfo=UTC)


@pytest.fixture
def lane_d_migrated_session() -> Iterator[Session]:
    module = _lane_d_migration_module()
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


class _SyncSessionBridge:
    def __init__(self, sync_session: Session) -> None:
        self._sync_session = sync_session

    async def run_sync(self, fn, *args, **kwargs):
        return fn(self._sync_session, *args, **kwargs)


@pytest.fixture
def lane_d_api_client(lane_d_migrated_session: Session) -> Iterator[AsyncClient]:
    app = create_app()

    async def _override_db_session() -> AsyncIterator[_SyncSessionBridge]:
        yield _SyncSessionBridge(lane_d_migrated_session)

    app.dependency_overrides[get_db_session] = _override_db_session
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def persisted_dataset(lane_d_migrated_session: Session):
    from backend.app.s2_materialized_dataset.lane_d.builder import BuildTimestamps
    from backend.app.s2_materialized_dataset.lane_d.service import persist_materialized_dataset

    upstream = complete_upstream()
    timestamps = BuildTimestamps(
        started_at=build_timestamps(),
        completed_at=build_timestamps(),
    )
    result = persist_materialized_dataset(
        lane_d_migrated_session,
        dataset_id="materialized-ds-1",
        dataset_version="v1",
        upstream=upstream,
        timestamps=timestamps,
    )
    lane_d_migrated_session.commit()
    return result
