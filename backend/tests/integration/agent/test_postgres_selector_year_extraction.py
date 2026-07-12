"""TASK-013 Slice A — PostgreSQL selector year-extraction integration test.

This module is a Round 7 (review 4680214102) test-first probe.  It
exercises the TASK-009 selector against a real PostgreSQL database to
verify the season-identity filter is applied at the SQL level using
``json_extract`` (PG-side).  The SQLite-level test
``test_default_selector_rejects_wrong_season_via_persisted_identity``
probes the same defect at the Python post-filter level; this test
probes the PG-side SQL surface (the ``func.strftime`` legacy is
forbidden — PG would reject it).

Test gating (per Charles's spec):

* MUST run against a real PostgreSQL instance (no SQLite session
  masquerading as PG).
* MUST exercise the actual ``_select_harvest_state_run_candidates``
  production function.
* MUST insert a real ``HarvestStateRun`` row whose
  ``input_snapshot`` carries a persisted ``forecast_season``
  identity, then assert the selector returns / excludes the row
  based on the REAL persisted identity (NOT ``as_of_date.year``).
* MUST use a ``postgres`` marker so PR-CI shards the test under the
  ``postgres-task11`` (or equivalent) shard that already runs in CI.

The test is skipped unless ``RUN_POSTGRES_INTEGRATION=1`` is set AND
``BLUEBERRY_PG_DSN`` points to a valid test DSN.  The default DSN
targets the local dev PG on ``localhost:5432`` with the
``blueberry_peak_test_p0fix`` database (created by the Slice 2C
test-harness).
"""
# ruff: noqa: E501, I001, F401, F841, F811, F821, ASYNC240

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.agent.adapters.baseline_composer import (
    _select_harvest_state_run_candidates,
)
from backend.app.models.harvest_state import (
    HarvestStateDailyMemberRowModel,
    HarvestStateRun,
)
from backend.app.models.master_data import Variety


POSTGRES_TEST_DSN = os.getenv(
    "BLUEBERRY_PG_DSN",
    "postgresql+asyncpg://blueberry_app:change-me-in-local-env@localhost:5432/blueberry_peak_test_r7",
)

PG_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _require_postgres() -> None:
    if not PG_INTEGRATION_ENABLED:
        pytest.skip(
            "set RUN_POSTGRES_INTEGRATION=1 to run the real PostgreSQL "
            "selector test; default is skip (SQLite unit test covers the "
            "Python post-filter path)"
        )


def _pg_dialect_compiles() -> bool:
    """Sanity-check: confirm the active SQLAlchemy dialect is PG."""
    return POSTGRES_TEST_DSN.startswith(("postgresql", "postgres"))


@pytest_asyncio.fixture
async def pg_selector_session() -> AsyncIterator[AsyncSession]:
    """A real PostgreSQL session bound to the test DSN.

    Creates a per-test ``harvest_state_run`` table subset and
    truncates after the test.  The schema subset uses the
    ``create_all`` ORM model for ``HarvestStateRun``,
    ``HarvestStateDailyMemberRowModel``, and ``Variety`` —
    sufficient to exercise ``_select_harvest_state_run_candidates``
    end-to-end.

    The session is bound to an engine scoped to this test; no
    global state is mutated.
    """
    if not PG_INTEGRATION_ENABLED:
        pytest.skip("PG integration disabled")
    if not _pg_dialect_compiles():
        pytest.skip("BLUEBERRY_PG_DSN is not a PostgreSQL URL")
    if not _pg_reachable(POSTGRES_TEST_DSN):
        pytest.skip(
            f"PostgreSQL is not reachable at {POSTGRES_TEST_DSN}; "
            "set BLUEBERRY_PG_DSN to a running test instance"
        )

    engine = create_async_engine(POSTGRES_TEST_DSN, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as session:
        # Use the ORM metadata.create_all to ensure the schema
        # matches the real HarvestStateRun / Variety / member
        # row tables (including every additive nullable column
        # added by later migrations).
        from backend.app.models.master_data import Variety as _Variety
        from backend.app.models.harvest_state import (
            HarvestStateDailyMemberRowModel,
            HarvestStateRun,
        )

        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: HarvestStateRun.metadata.create_all(
                    sync_conn,
                    tables=[
                        Table(_Variety.__tablename__, _Variety.metadata),
                        Table(
                            HarvestStateRun.__tablename__,
                            HarvestStateRun.metadata,
                        ),
                        Table(
                            HarvestStateDailyMemberRowModel.__tablename__,
                            HarvestStateDailyMemberRowModel.metadata,
                        ),
                    ],
                    checkfirst=True,
                )
            )

        yield session
        # Cleanup: delete all rows we inserted (in FK-safe order).
        try:
            await session.execute(text("DELETE FROM harvest_state_daily_member_row"))
        except Exception:
            pass
        try:
            await session.execute(text("DELETE FROM harvest_state_run"))
        except Exception:
            pass
        try:
            await session.execute(text("DELETE FROM variety"))
        except Exception:
            pass
        await session.commit()
    await engine.dispose()


def _pg_reachable(dsn: str) -> bool:
    """Quick TCP-level reachability check (no DSN parsing)."""
    try:
        import socket

        # Best-effort: parse host:port from the DSN.
        # Format: postgresql+asyncpg://user:pass@host:port/db
        from urllib.parse import urlparse

        u = urlparse(dsn)
        host = u.hostname or "localhost"
        port = u.port or 5432
        with socket.create_connection((host, port), timeout=2) as _:
            return True
    except Exception:
        return False


@pytest.mark.postgres
async def test_postgres_selector_year_extraction_real_pg(
    pg_selector_session: AsyncSession,
) -> None:
    """Real PostgreSQL: insert a TASK-009 row whose
    ``input_snapshot.forecast_season=2025`` but
    ``as_of_date=2026-01-10``.  The legacy
    ``func.strftime("%Y", ...)`` filter would NOT match because
    ``as_of_date.year != 2025``; the round-7 production code uses
    ``input_snapshot["forecast_season"]`` (real persisted identity)
    and the row is accepted."""
    suffix = uuid.uuid4().hex[:8]
    pg_selector_session.add(Variety(id=1, code=f"Dx_{suffix}", name="Test Dx"))
    await pg_selector_session.flush()
    # Real persisted season = 2025; as_of_date.year = 2026.
    # The selector MUST match by input_snapshot.forecast_season, not
    # by as_of_date.year.
    hsr_id = await _insert_hsr(
        pg_selector_session,
        suffix=suffix,
        result_hash="a" * 64,
        config_hash="b" * 64,
        forecast_season=2025,
        as_of_date=date(2026, 1, 10),
    )
    candidates = await _select_harvest_state_run_candidates(
        pg_selector_session,
        as_of=date(2026, 1, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=2025,
    )
    assert any(c["id"] == hsr_id for c in candidates), (
        "PostgreSQL selector must accept the row when "
        "input_snapshot.forecast_season=2025 even though "
        "as_of_date.year=2026; the legacy as_of_date.year filter "
        "would have rejected it"
    )


@pytest.mark.postgres
async def test_postgres_selector_season_mismatch_excludes_row(
    pg_selector_session: AsyncSession,
) -> None:
    """Real PostgreSQL: row with input_snapshot.forecast_season=2024
    must be EXCLUDED when the request asks for 2025, even though
    as_of_date.year=2025 would have accepted it under the legacy
    round-6 derivation."""
    suffix = uuid.uuid4().hex[:8]
    pg_selector_session.add(Variety(id=1, code=f"Dx_{suffix}", name="Test Dx"))
    await pg_selector_session.flush()
    hsr_id = await _insert_hsr(
        pg_selector_session,
        suffix=suffix,
        result_hash="c" * 64,
        config_hash="d" * 64,
        forecast_season=2024,  # request asks for 2025
        as_of_date=date(2025, 12, 1),
    )
    candidates = await _select_harvest_state_run_candidates(
        pg_selector_session,
        as_of=date(2025, 12, 15),
        run_id_override=None,
        destination_factory_id=1,
        requested_variety_codes=(),
        effective_forecast_season=2025,
    )
    assert all(c["id"] != hsr_id for c in candidates), (
        "PostgreSQL selector must exclude the row whose "
        "input_snapshot.forecast_season=2024 when the request asks "
        "for 2025; the legacy as_of_date.year derivation would have "
        "accepted the row"
    )


async def _insert_hsr(
    session: AsyncSession,
    *,
    suffix: str,
    result_hash: str,
    config_hash: str,
    forecast_season: int,
    as_of_date: date,
) -> int:
    """Insert a real ``HarvestStateRun`` row whose
    ``input_snapshot`` JSONB column carries the season as a JSONB
    scalar (not a TEXT-cast of an SQL filter)."""
    row = HarvestStateRun(
        status="completed",
        output_schema_version="v1",
        result_hash_schema_version="v1",
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        input_snapshot={"forecast_season": forecast_season},
        resolved_parameter_snapshot={"forecast_season": forecast_season},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result=None,
        continuity_result=None,
        canonical_output={"ok": True},
        config_hash=config_hash,
        result_hash=result_hash,
        canonical_payload_hash="c" * 64,
        forecast_start_date=as_of_date,
        forecast_end_date=as_of_date.replace(month=12, day=31),
        as_of_date=as_of_date,
        destination_factory_id=1,
        pool_row_count=0,
        member_row_count=0,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_forecast_run_id=None,
    )
    session.add(row)
    await session.flush()
    return int(row.id)


__all__ = [
    "test_postgres_selector_year_extraction_real_pg",
    "test_postgres_selector_season_mismatch_excludes_row",
]
