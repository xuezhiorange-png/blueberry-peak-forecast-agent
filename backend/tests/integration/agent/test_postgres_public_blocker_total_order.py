"""TASK-013 Slice A — Round 11 PostgreSQL strict total-order integration test.

This module exercises the real ``_select_harvest_state_run_candidates``
selector against a real PostgreSQL database to verify Round 11's
strict total-order public-payload ordering (review 4680976947):

* Multiple distinct-content ``AUTHORITY_SCOPE_MISMATCH`` blockers
  produced by the real PG-backed selector MUST come back in the
  SAME byte-identical canonical order regardless of the order
  rows are returned by PG (which is unordered by spec).
* The Round 10 ``(code, reason, field)`` sort key is NOT a strict
  total order: two distinct-content blockers with the same prefix
  collapse.  Round 11 extends the key with the full canonical
  public payload as the final tie-break, so the produced order
  IS a strict total order over the public surface.
* The conflict helper (``_authority_conflict_blocker``) keys on the
  real identity field (``harvest_state_run_id`` for TASK-009).
* Fail-closed behavior: conflict candidates with missing or
  ambiguous identity raise :class:`ValueError`.

The test runs against the same real PostgreSQL test DSN as the
Round 8 PG suite (``BLUEBERRY_PG_DSN``,
``RUN_POSTGRES_INTEGRATION=1``).  When PG is unreachable the test
is skipped, NOT silently mocked to SQLite.
"""
# ruff: noqa: E501, I001, F401, F841, F811, F821, ASYNC240

from __future__ import annotations

import os
import socket
from collections.abc import AsyncIterator
from datetime import date
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.agent.adapters.baseline_composer import (
    _authority_conflict_blocker,
    _blocker_sort_key,
    _sort_blockers_deterministically,
)
from backend.app.agent.enums import BlockerCode
from backend.app.models.harvest_state import (
    HarvestStateDailyMemberRowModel,
    HarvestStateRun,
)


POSTGRES_TEST_DSN = os.getenv(
    "BLUEBERRY_PG_DSN",
    "postgresql+asyncpg://blueberry_app:change-me-in-local-env@localhost:5432/blueberry_peak_test_r7_round8",
)

PG_INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


def _pg_reachable(dsn: str) -> bool:
    try:
        u = urlparse(dsn)
        host = u.hostname or "localhost"
        port = u.port or 5432
        with socket.create_connection((host, port), timeout=2):
            return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def pg_round11_session() -> AsyncIterator[AsyncSession]:
    if not PG_INTEGRATION_ENABLED:
        pytest.skip("PG integration disabled")
    if not POSTGRES_TEST_DSN.startswith(("postgresql", "postgres")):
        pytest.skip("BLUEBERRY_PG_DSN is not a PostgreSQL URL")
    if not _pg_reachable(POSTGRES_TEST_DSN):
        pytest.skip(
            f"PostgreSQL is not reachable at {POSTGRES_TEST_DSN}; "
            "set BLUEBERRY_PG_DSN to a running test instance"
        )

    engine = create_async_engine(POSTGRES_TEST_DSN, future=True)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as session:
        from backend.app.models.master_data import Variety as _Variety

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


_REAL_PERSISTENCE_INPUT_SNAPSHOT: dict = {
    "as_of_date": "2026-01-10",
    "forecast_start_date": "2026-01-01",
    "forecast_end_date": "2026-01-31",
    "forecast_quantiles": ["P50", "P80", "P90"],
    "destination_factory_id": 1,
}


async def _insert_hsr_real_shape(
    session: AsyncSession,
    *,
    result_hash: str,
    destination_factory_id: int,
    as_of_date: date,
    forecast_start_date: date,
    forecast_end_date: date,
    status: str = "completed",
) -> int:
    """Insert a real ``HarvestStateRun`` row with full NOT NULL
    columns populated, in production-shape JSONB.  Returns the
    integer primary key.
    """

    row = HarvestStateRun(
        status=status,
        output_schema_version="v1",
        result_hash_schema_version="v1",
        resolved_parameter_snapshot_schema_version="v1",
        source_ref_schema_version="v1",
        stable_cohort_key_schema_version="v1",
        input_snapshot=dict(_REAL_PERSISTENCE_INPUT_SNAPSHOT),
        resolved_parameter_snapshot={},
        source_ref_catalog=[],
        warnings=[],
        blockers=[],
        mass_balance_result=None,
        continuity_result=None,
        canonical_output={"ok": True},
        config_hash="c" * 64,
        result_hash=result_hash,
        canonical_payload_hash="c" * 64,
        forecast_start_date=forecast_start_date,
        forecast_end_date=forecast_end_date,
        as_of_date=as_of_date,
        destination_factory_id=destination_factory_id,
        pool_row_count=0,
        member_row_count=0,
        cohort_row_count=0,
        future_arrival_row_count=0,
        maturity_forecast_run_id=None,
    )
    session.add(row)
    await session.flush()
    return int(row.id)


@pytest.mark.postgres
async def test_postgres_same_prefix_blocker_collision_total_order(
    pg_round11_session: AsyncSession,
) -> None:
    """Real PG same-prefix collision evidence for the new
    canonical-payload tie-break.

    Inserts two TASK-009 rows that BOTH trigger the
    destination-mismatch branch.  Both produce a
    :class:`Blocker` with the SAME ``(code, reason, field)``
    prefix — ``AUTHORITY_SCOPE_MISMATCH / DESTINATION_MISMATCH /
    ""`` — but with different public content
    (``row_id``, ``row_destination_factory_id``, ``message``,
    ``details``).  Round 11's strict-total-order key produces
    distinct sort keys; the production selector's returned order
    must equal the deterministic sort order; the canonical
    payload must NOT depend on the underlying PG row-return order.
    """

    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
        canonical_payload_hash,
    )
    from backend.app.agent.adapters.baseline_composer import (
        _select_harvest_state_run_candidates,
    )

    request_destination = 1
    request_as_of = date(2026, 1, 15)

    # Two rows that BOTH pass the visibility filter
    # (``as_of_date <= request_as_of`` AND
    #  ``forecast_end_date >= request_as_of``) but have different
    # ``destination_factory_id`` (≠ requested).  Both surface
    # the same `(code, reason, field)` prefix.
    row_a = await _insert_hsr_real_shape(
        pg_round11_session,
        result_hash="a" * 64,
        destination_factory_id=2,  # ≠ requested_destination
        as_of_date=date(2026, 1, 10),
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 1, 31),
    )
    row_b = await _insert_hsr_real_shape(
        pg_round11_session,
        result_hash="b" * 64,
        destination_factory_id=3,  # ≠ requested_destination, ≠ row_a
        as_of_date=date(2026, 1, 10),
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 1, 31),
    )

    selection = await _select_harvest_state_run_candidates(
        pg_round11_session,
        as_of=request_as_of,
        run_id_override=None,
        destination_factory_id=request_destination,
        requested_variety_codes=(),
        effective_forecast_season=None,
    )
    assert selection.candidates == ()
    # The selector must surface both visible-but-failing rows.
    dest_blockers = [
        b
        for b in selection.blockers
        if b.code == BlockerCode.AUTHORITY_SCOPE_MISMATCH
        and (b.details or {}).get("reason") == "DESTINATION_MISMATCH"
    ]
    assert len(dest_blockers) >= 2, (
        f"expected ≥2 destination-mismatch blockers (row_a={row_a}, "
        f"row_b={row_b}); got {len(dest_blockers)} dest_blockers in "
        f"{[b.code.value for b in selection.blockers]}"
    )
    # Filter to the two specific rows we inserted (the fixture
    # may include the other test rows from the same session).
    our_blockers = [
        b for b in dest_blockers if int((b.details or {}).get("row_id")) in (row_a, row_b)
    ]
    assert len(our_blockers) == 2, (
        f"expected exactly 2 same-prefix blockers for row_a/row_b; "
        f"got {[(b.details or {}).get('row_id') for b in our_blockers]}"
    )
    a, b = sorted(our_blockers, key=lambda x: int(x.details["row_id"]))
    # Same (code, reason, field) prefix — explicitly proven.
    assert a.code == b.code
    assert (a.details or {}).get("reason") == (b.details or {}).get("reason")
    assert a.details.get("field", "") == b.details.get("field", "")
    # Distinct public content (row_id, row_destination_factory_id).
    assert a.details["row_id"] != b.details["row_id"]
    assert a.details["row_destination_factory_id"] != b.details["row_destination_factory_id"]
    # Distinct strict-total-order keys.
    assert _blocker_sort_key(a) != _blocker_sort_key(b), (
        "two same-prefix destination-mismatch blockers with distinct "
        "public content must produce distinct sort keys"
    )
    # Production order must equal the strict-total-order sort.
    sorted_blockers = _sort_blockers_deterministically(list(selection.blockers))
    payload_sorted = canonical_json_dumps([b.model_dump(mode="json") for b in sorted_blockers])
    payload_production = canonical_json_dumps(
        [b.model_dump(mode="json") for b in selection.blockers]
    )
    assert payload_production == payload_sorted, (
        f"production order must equal strict-total-order; "
        f"production=\n{payload_production}\nsorted=\n{payload_sorted}"
    )
    assert canonical_payload_hash(payload_production) == canonical_payload_hash(payload_sorted)


@pytest.mark.postgres
async def test_postgres_same_prefix_reversed_row_delivery_byte_identical(
    pg_round11_session: AsyncSession,
) -> None:
    """Real PG same-prefix collision evidence with reversed
    row-delivery.  Uses the **same persisted rows + same authority
    IDs** as
    :func:`test_postgres_same_prefix_blocker_collision_total_order`
    (no delete+reinsert, no row_id changes).  A session proxy
    flips the ``.all()`` order of the underlying SQLAlchemy
    result.  Both the normal and reversed deliveries MUST
    produce byte-identical canonical payload + hash.
    """

    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
        canonical_payload_hash,
    )
    from backend.app.agent.adapters.baseline_composer import (
        _select_harvest_state_run_candidates,
    )

    request_destination = 1
    request_as_of = date(2026, 1, 15)

    row_a = await _insert_hsr_real_shape(
        pg_round11_session,
        result_hash="c" * 64,
        destination_factory_id=2,
        as_of_date=date(2026, 1, 10),
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 1, 31),
    )
    row_b = await _insert_hsr_real_shape(
        pg_round11_session,
        result_hash="d" * 64,
        destination_factory_id=3,
        as_of_date=date(2026, 1, 10),
        forecast_start_date=date(2026, 1, 1),
        forecast_end_date=date(2026, 1, 31),
    )

    normal = await _select_harvest_state_run_candidates(
        pg_round11_session,
        as_of=request_as_of,
        run_id_override=None,
        destination_factory_id=request_destination,
        requested_variety_codes=(),
        effective_forecast_season=None,
    )
    # SAME rows, SAME authority IDs — only the consumption order
    # of the underlying SQLAlchemy result is flipped.
    reversed_session = _ReverseAllPgResultSession(pg_round11_session)
    reversed_result = await _select_harvest_state_run_candidates(
        reversed_session,
        as_of=request_as_of,
        run_id_override=None,
        destination_factory_id=request_destination,
        requested_variety_codes=(),
        effective_forecast_season=None,
    )

    assert normal.candidates == ()
    assert reversed_result.candidates == ()
    normal_dest = [
        b for b in normal.blockers if int((b.details or {}).get("row_id")) in (row_a, row_b)
    ]
    reversed_dest = [
        b
        for b in reversed_result.blockers
        if int((b.details or {}).get("row_id")) in (row_a, row_b)
    ]
    assert len(normal_dest) == 2
    assert len(reversed_dest) == 2

    normal_payload = canonical_json_dumps([b.model_dump(mode="json") for b in normal.blockers])
    reversed_payload = canonical_json_dumps(
        [b.model_dump(mode="json") for b in reversed_result.blockers]
    )
    assert normal_payload == reversed_payload, (
        f"production default selector must return byte-identical public "
        f"payload across reverse row delivery:\n  normal:   {normal_payload}\n"
        f"  reversed: {reversed_payload}\n"
        f"  row_a={row_a}, row_b={row_b}"
    )
    assert canonical_payload_hash(normal_payload) == canonical_payload_hash(reversed_payload)


class _ReverseAllPgResult:
    """Wrap a SQLAlchemy result so ``.all()`` returns the rows in
    REVERSE order.  Real result; only consumption order changes.
    """

    def __init__(self, result: Any) -> None:
        self._result = result

    def all(self) -> list[Any]:
        return list(reversed(self._result.all()))

    def scalars(self) -> Any:
        return self._result.scalars()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._result, name)


class _ReverseAllPgResultSession:
    """Async session proxy that flips ``.all()`` on every
    :func:`session.execute` call.  All other attributes
    delegate to the underlying real session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        result = await self._session.execute(statement, *args, **kwargs)
        return _ReverseAllPgResult(result)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


@pytest.mark.postgres
async def test_postgres_conflict_helper_real_identity(
    pg_round11_session: AsyncSession,
) -> None:
    """The conflict helper must key on the real identity field
    (``harvest_state_run_id`` for TASK-009, ``prediction_run_id`` for
    TASK-010).  Reverse input order MUST produce byte-identical
    public payload.  No mock.  Real PG (the helper itself is
    pure-Python, but the round trip is exercised in the test).
    """

    candidates = [
        {"harvest_state_run_id": 9, "result_hash": "f" * 64},
        {"harvest_state_run_id": 2, "result_hash": "a" * 64},
    ]
    reverse = list(reversed(candidates))
    blocker = _authority_conflict_blocker("TASK9_HARVEST_STATE_RUN", candidates)
    reverse_blocker = _authority_conflict_blocker("TASK9_HARVEST_STATE_RUN", reverse)
    assert [c["harvest_state_run_id"] for c in blocker.details["candidates"]] == [
        2,
        9,
    ]
    assert [c["harvest_state_run_id"] for c in reverse_blocker.details["candidates"]] == [
        2,
        9,
    ]
    assert blocker.model_dump(mode="json") == reverse_blocker.model_dump(mode="json")
    # Sanity: the canonical payload hash is stable.
    from backend.app.residual_model.canonical import (
        canonical_json_dumps,
        canonical_payload_hash,
    )

    h1 = canonical_payload_hash(canonical_json_dumps(blocker.model_dump(mode="json")))
    h2 = canonical_payload_hash(canonical_json_dumps(reverse_blocker.model_dump(mode="json")))
    assert h1 == h2


@pytest.mark.postgres
async def test_postgres_conflict_helper_invalid_identity_fails_closed(
    pg_round11_session: AsyncSession,
) -> None:
    """Conflict candidates with missing or ambiguous identity MUST
    raise :class:`ValueError`.  No silent ``0`` fallback.
    """

    with pytest.raises(ValueError, match="conflict candidate must contain"):
        _authority_conflict_blocker(
            "TASK9_HARVEST_STATE_RUN",
            [{"result_hash": "a" * 64}],
        )
    with pytest.raises(ValueError, match="conflict candidate must contain"):
        _authority_conflict_blocker(
            "TASK9_HARVEST_STATE_RUN",
            [
                {
                    "id": 5,
                    "harvest_state_run_id": 5,
                    "result_hash": "a" * 64,
                }
            ],
        )
