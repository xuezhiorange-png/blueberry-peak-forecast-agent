"""Live PG assertion for the Slice 3 isolated database profile.

This module is the *live* companion to
:mod:`backend.tests.test_alembic_round_trip_isolated`. Where that file
asserts the *helper contract* (the pure name resolver / guard), this
file asserts what actually happened on the wire once the
``postgres-migration`` GitHub Actions job finished its
``alembic upgrade head`` / ``downgrade 0010_harvest_state_persistence`` /
``upgrade head`` round-trip.

CI ownership (Slice 3 contract):

* This file is marked ``pytest.mark.postgres`` (see ``pytestmark``).
  The ``unit-contract-golden`` job's
  ``-m "not integration and not postgres and not postgres_concurrency"``
  selector therefore **excludes** it. Running it on the
  unit-contract shard would be a mistake, not a feature: there is no
  live PostgreSQL in that job.
* This file is **owned** by the ``postgres-migration`` job, which
  lists it explicitly in its ``pytest`` invocation in
  ``.github/workflows/ci.yml`` (the ``-m`` selector does not apply to
  hand-listed files). It is the only CI job that runs these tests.
* This file is intentionally **not** placed under
  ``backend/tests/integration/`` to avoid being collected by any
  future integration-shard wiring.

Local-development contract:

* On hosts without a live PostgreSQL reachable through the
  ``POSTGRES_HOST`` / ``POSTGRES_PORT`` / ``POSTGRES_USER`` /
  ``POSTGRES_PASSWORD`` / ``ISOLATED_DB_NAME`` env vars, every test
  in this file ``pytest.skip``s. We do **not** fall back to the dev
  database; the dev-DB safeguard
  (:mod:`backend.tests.postgres_test_support`) is the only authority
  on which databases may be contacted from tests, and a missing
  ``ISOLATED_DB_NAME`` is treated as a contract violation, not a
  license to improvise.
* Connection parameters come from environment variables only; no
  password / token / ``DATABASE_URL`` value is ever printed or
  formatted into an error message.

Async / event-loop contract:

* The asyncpg connection and its query are executed inside the
  *same* async function and the *same* event loop. We do **not**
  open the connection in one helper, hand the (still-pending)
  coroutine to the test, and ``await`` it from a separate event
  loop — asyncpg connections are bound to the loop that opened
  them, and the previous attempt at that pattern raised
  ``AttributeError: 'coroutine' object has no attribute 'fetchval'``
  in CI. Each test creates a fresh connection, runs exactly one
  query, and closes the connection in the same async function
  before ``asyncio.run`` returns.

Head revision discovery:

* The expected head revision is **not** hard-coded. It is resolved at
  collection time via Alembic's own
  :class:`alembic.script.ScriptDirectory`, using the same
  ``backend/alembic.ini`` that the CI round-trip step uses. This keeps
  the test in sync with whatever head the migration chain is at.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Mapping
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.app.harvest_state.canonical import canonical_json_dumps, sha256_hex

# ---------------------------------------------------------------------------
# Marker / module-level guard
# ---------------------------------------------------------------------------

# Mark this file ``postgres`` so ``unit-contract-golden`` excludes it.
# The ``postgres-migration`` job lists the file explicitly in its
# ``pytest`` invocation, so the marker is not a no-op for that job.
# Slice 1 Batch 4 marker annotation: add ``migration`` (canonical
# Issue #52 taxonomy) additively. Ownership remains ``postgres-migration``
# per ci-shard-manifest.yml.
pytestmark = [pytest.mark.postgres, pytest.mark.migration]

_TASK9_V1_RUN_ID = 9_098_001
_TASK9_V1_RESULT_HASH = "4578d5244657f82eacdc8052388aa076cee3dbffa362b1d0b10edd036d6fcb21"
_TASK9_V1_GOLDEN = Path("backend/tests/harvest_state/golden/task9a_completed_v1_canonical.json")
_REVISION_0015 = "0015_task11_phase3_schema_gap"
_REVISION_0016 = "0016_task9_forecast_season_identity"
_CHILD_TABLES = {
    "pool": "harvest_state_daily_pool_row",
    "member": "harvest_state_daily_member_row",
    "cohort": "harvest_state_cohort_transition_row",
    "future_arrival": "harvest_state_future_arrival_row",
}


# ---------------------------------------------------------------------------
# Live-env introspection
# ---------------------------------------------------------------------------


def _required_live_env() -> dict[str, str]:
    """Return the live PG env this test file requires, or skip if absent.

    Every key must be present and non-empty. We never synthesise a
    ``localhost`` default for any of them — that would silently route
    a test command at a dev / cluster-default database, which the
    slice-1 safeguard forbids.
    """

    required = (
        "ISOLATED_DB_NAME",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )
    env = {key: os.environ.get(key, "") for key in required}
    missing = [key for key, value in env.items() if not value]
    if missing:
        pytest.skip(
            f"Slice 3 live PG test requires env vars {missing!r}; "
            "this host is not running the postgres-migration job"
        )
    return env


def _expected_head_revision() -> str:
    """Return the current head revision of the project, resolved via Alembic.

    Resolved from ``backend/alembic.ini`` so the value tracks the
    migration chain automatically. No hard-coded revision string
    appears in this file.
    """

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini_path = os.path.join("backend", "alembic.ini")
    if not os.path.isfile(ini_path):
        pytest.skip(f"Alembic config not found at {ini_path!r}")
    cfg = Config(ini_path)
    try:
        script_dir = ScriptDirectory.from_config(cfg)
    except Exception as exc:  # pragma: no cover - defensive
        pytest.skip(f"Could not load Alembic script directory: {exc!r}")
    head = script_dir.get_current_head()
    if not head:
        pytest.skip("Alembic script directory reports no current head")
    return head


# ---------------------------------------------------------------------------
# Async helpers — connect, query, close, all in the same coroutine.
# ---------------------------------------------------------------------------


async def _fetch_current_database(asyncpg, env: dict[str, str], database: str) -> str:
    """Open a connection, run ``SELECT current_database()``, and close.

    The connection and the query live in the *same* event loop and
    the *same* coroutine. This is the asyncpg-correct pattern: an
    asyncpg connection is bound to the loop that opened it, and the
    connection object only exposes ``fetchval`` / ``execute`` / etc.
    *after* the ``await asyncpg.connect(...)`` call has actually
    resolved.
    """

    port = int(env["POSTGRES_PORT"])
    conn = await asyncpg.connect(
        host=env["POSTGRES_HOST"],
        port=port,
        database=database,
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        return await conn.fetchval("SELECT current_database()")
    finally:
        await conn.close()


async def _fetch_alembic_version(asyncpg, env: dict[str, str], database: str) -> str | None:
    """Open a connection, query ``alembic_version``, and close.

    Same single-coroutine pattern as :func:`_fetch_current_database`.
    Returns the ``version_num`` column, or ``None`` if the
    ``alembic_version`` table is present but empty (treated as a
    contract violation by the caller).
    """

    port = int(env["POSTGRES_PORT"])
    conn = await asyncpg.connect(
        host=env["POSTGRES_HOST"],
        port=port,
        database=database,
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        return await conn.fetchval("SELECT version_num FROM alembic_version")
    finally:
        await conn.close()


def _alembic_config():
    from alembic.config import Config

    return Config(os.path.join("backend", "alembic.ini"))


def _load_task9_v1_golden() -> dict[str, Any]:
    payload = json.loads(_TASK9_V1_GOLDEN.read_text())
    assert payload["status"] == "completed"
    assert payload["output_schema_version"] == "task9a-output-v1"
    assert payload["result_hash"] == _TASK9_V1_RESULT_HASH
    assert "forecast_season_id" not in payload
    assert "forecast_season_identity" not in payload["input_snapshot"]
    return payload


def _subfarm_identity_key(subfarm_id: int | None) -> str:
    return "NONE" if subfarm_id is None else str(subfarm_id)


def _task8_identity(golden: Mapping[str, Any]) -> dict[str, Any]:
    prediction = golden["input_snapshot"]["task8_daily_predictions"][0]
    verification = prediction["verification_snapshot"]
    return {
        "maturity_model_run_id": verification["maturity_model_run_id"],
        "maturity_model_version": verification["maturity_model_version"],
        "maturity_model_config_hash": verification["maturity_model_config_hash"],
        "maturity_model_source_signature": verification["maturity_model_source_signature"],
        "maturity_model_artifact_id": verification["maturity_model_artifact_id"],
        "maturity_model_artifact_hash": verification["maturity_model_artifact_hash"],
        "maturity_forecast_run_id": verification["maturity_forecast_run_id"],
        "maturity_forecast_source_signature": verification["maturity_forecast_source_signature"],
    }


def _task9_v1_rows(golden: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    source_refs = {
        entry["source_ref_hash"]: entry["source_ref_payload"]
        for entry in golden["source_ref_catalog"]
    }
    pool_memberships = {
        (row["state_date"], row["capacity_pool_id"], row["forecast_quantile"]): row[
            "capacity_pool_membership_hash"
        ]
        for row in golden["daily_pool_state_rows"]
    }
    run_parameters = golden["resolved_parameter_snapshot"]["run_parameters"]

    member_rows = []
    for row in golden["daily_member_state_rows"]:
        member_rows.append(
            {
                **row,
                "harvest_state_run_id": _TASK9_V1_RUN_ID,
                "subfarm_identity_key": _subfarm_identity_key(row["subfarm_id"]),
            }
        )

    cohort_rows = []
    for row in golden["cohort_transition_rows"]:
        cohort_rows.append(
            {
                **row,
                "harvest_state_run_id": _TASK9_V1_RUN_ID,
                "source_ref": source_refs[row["source_ref_hash"]],
                "capacity_pool_membership_hash": pool_memberships[
                    (row["state_date"], row["capacity_pool_id"], row["forecast_quantile"])
                ],
            }
        )

    future_rows = []
    for row in golden["future_arrival_schedule"]:
        future_rows.append(
            {
                **row,
                "harvest_state_run_id": _TASK9_V1_RUN_ID,
                "subfarm_identity_key": _subfarm_identity_key(row["subfarm_id"]),
                "harvest_to_arrival_lag_days": run_parameters["harvest_to_arrival_lag_days"],
                "farm_timezone": run_parameters["farm_timezone"],
                "destination_factory_timezone": run_parameters["destination_factory_timezone"],
            }
        )

    return {
        "pool": [
            {**row, "harvest_state_run_id": _TASK9_V1_RUN_ID}
            for row in golden["daily_pool_state_rows"]
        ],
        "member": member_rows,
        "cohort": cohort_rows,
        "future_arrival": future_rows,
    }


def _task9_v1_run(golden: dict[str, Any]) -> dict[str, Any]:
    input_snapshot = golden["input_snapshot"]
    resolved = golden["resolved_parameter_snapshot"]
    run_parameters = resolved["run_parameters"]
    rows = _task9_v1_rows(golden)
    return {
        "id": _TASK9_V1_RUN_ID,
        "status": golden["status"],
        "output_schema_version": golden["output_schema_version"],
        "result_hash_schema_version": "task9a-result-hash-v1",
        "resolved_parameter_snapshot_schema_version": resolved["schema_version"],
        "source_ref_schema_version": run_parameters["source_ref_schema_version"],
        "stable_cohort_key_schema_version": run_parameters["stable_cohort_key_schema_version"],
        "input_snapshot": input_snapshot,
        "resolved_parameter_snapshot": resolved,
        "source_ref_catalog": golden["source_ref_catalog"],
        "warnings": golden["warnings"],
        "blockers": golden["blockers"],
        "mass_balance_result": golden["mass_balance_result"],
        "continuity_result": golden["continuity_result"],
        "canonical_output": golden,
        "config_hash": golden["config_hash"],
        "result_hash": golden["result_hash"],
        "canonical_payload_hash": sha256_hex(golden),
        "forecast_start_date": input_snapshot["forecast_start_date"],
        "forecast_end_date": input_snapshot["forecast_end_date"],
        "as_of_date": input_snapshot["as_of_date"],
        "destination_factory_id": input_snapshot["destination_factory_id"],
        "pool_row_count": len(rows["pool"]),
        "member_row_count": len(rows["member"]),
        "cohort_row_count": len(rows["cohort"]),
        "future_arrival_row_count": len(rows["future_arrival"]),
        **_task8_identity(golden),
    }


async def _table_columns(conn: Any, table_name: str) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT column_name, data_type, udt_name, is_nullable, column_default, is_identity
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = $1
        ORDER BY ordinal_position
        """,
        table_name,
    )
    return [dict(row) for row in rows]


def _database_value(value: Any, *, data_type: str, udt_name: str) -> Any:
    if value is None:
        return None
    if data_type in {"json", "jsonb"} or udt_name in {"json", "jsonb"}:
        return canonical_json_dumps(value)
    if data_type == "date":
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if "timestamp" in data_type:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if data_type == "numeric":
        return Decimal(str(value))
    return value


async def _insert_reflected(conn: Any, table_name: str, payload: Mapping[str, Any]) -> None:
    columns = await _table_columns(conn, table_name)
    available = {column["column_name"] for column in columns}
    unknown = set(payload) - available
    assert not unknown, f"{table_name} payload contains columns absent at revision 0015: {unknown}"
    missing = {
        column["column_name"]
        for column in columns
        if column["is_nullable"] == "NO"
        and column["column_default"] is None
        and column["is_identity"] == "NO"
        and column["column_name"] not in payload
    }
    assert not missing, f"{table_name} payload omits required revision-0015 columns: {missing}"

    selected = [column for column in columns if column["column_name"] in payload]
    names = [column["column_name"] for column in selected]
    placeholders = ", ".join(f"${index}" for index in range(1, len(names) + 1))
    quoted_names = ", ".join(f'"{name}"' for name in names)
    values = [
        _database_value(
            payload[column["column_name"]],
            data_type=column["data_type"],
            udt_name=column["udt_name"],
        )
        for column in selected
    ]
    await conn.execute(
        f'INSERT INTO "{table_name}" ({quoted_names}) VALUES ({placeholders})',
        *values,
    )


def _canonical_database_value(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("{") or value.startswith("["):
            try:
                return _canonical_database_value(json.loads(value))
            except json.JSONDecodeError:
                return value
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _canonical_database_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_database_value(item) for item in value]
    return value


async def _seed_task9_v1_and_read_evidence(
    asyncpg: Any,
    env: dict[str, str],
    database: str,
    golden: dict[str, Any],
) -> dict[str, Any]:
    conn = await asyncpg.connect(
        host=env["POSTGRES_HOST"],
        port=int(env["POSTGRES_PORT"]),
        database=database,
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        assert await conn.fetchval("SELECT current_database()") == database
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM harvest_state_run WHERE id = $1", _TASK9_V1_RUN_ID
            )
            == 0
        )
        async with conn.transaction():
            await _insert_reflected(conn, "harvest_state_run", _task9_v1_run(golden))
            for family, table_name in _CHILD_TABLES.items():
                for row in _task9_v1_rows(golden)[family]:
                    await _insert_reflected(conn, table_name, row)
        return await _read_task9_v1_evidence(conn)
    finally:
        await conn.close()


_RUN_BUSINESS_FIELDS = (
    "status",
    "output_schema_version",
    "destination_factory_id",
    "as_of_date",
    "forecast_start_date",
    "forecast_end_date",
    "config_hash",
    "result_hash_schema_version",
    "resolved_parameter_snapshot_schema_version",
    "source_ref_schema_version",
    "stable_cohort_key_schema_version",
    "pool_row_count",
    "member_row_count",
    "cohort_row_count",
    "future_arrival_row_count",
    "maturity_model_run_id",
    "maturity_model_version",
    "maturity_model_config_hash",
    "maturity_model_source_signature",
    "maturity_model_artifact_id",
    "maturity_model_artifact_hash",
    "maturity_forecast_run_id",
    "maturity_forecast_source_signature",
)


async def _read_task9_v1_evidence(conn: Any) -> dict[str, Any]:
    run = await conn.fetchrow("SELECT * FROM harvest_state_run WHERE id = $1", _TASK9_V1_RUN_ID)
    assert run is not None
    run_dict = dict(run)
    canonical_output = _canonical_database_value(run_dict["canonical_output"])

    counts = {"runs": 1}
    child_hashes: dict[str, str] = {}
    for family, table_name in _CHILD_TABLES.items():
        records = await conn.fetch(
            f'SELECT * FROM "{table_name}" WHERE harvest_state_run_id = $1',
            _TASK9_V1_RUN_ID,
        )
        rows = []
        for record in records:
            row = dict(record)
            row.pop("id")
            rows.append(_canonical_database_value(row))
        rows.sort(key=canonical_json_dumps)
        counts[f"{family}_rows"] = len(rows)
        child_hashes[family] = sha256_hex(rows)

    return {
        "canonical_output": canonical_json_dumps(canonical_output),
        "canonical_hash": sha256_hex(canonical_output),
        "result_hash": run_dict["result_hash"],
        "canonical_payload_hash": run_dict["canonical_payload_hash"],
        "run_business_fields": {
            field: _canonical_database_value(run_dict[field]) for field in _RUN_BUSINESS_FIELDS
        },
        "counts": counts,
        "child_semantic_hashes": child_hashes,
    }


async def _read_live_state(
    asyncpg: Any,
    env: dict[str, str],
    database: str,
) -> tuple[str | None, bool, dict[str, Any]]:
    conn = await asyncpg.connect(
        host=env["POSTGRES_HOST"],
        port=int(env["POSTGRES_PORT"]),
        database=database,
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        assert await conn.fetchval("SELECT current_database()") == database
        revision = await conn.fetchval("SELECT version_num FROM alembic_version")
        has_forecast_season = bool(
            await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'harvest_state_run'
                      AND column_name = 'forecast_season_id'
                )
                """
            )
        )
        evidence = await _read_task9_v1_evidence(conn)
        if has_forecast_season:
            assert (
                await conn.fetchval(
                    "SELECT forecast_season_id FROM harvest_state_run WHERE id = $1",
                    _TASK9_V1_RUN_ID,
                )
                is None
            )
        return revision, has_forecast_season, evidence
    finally:
        await conn.close()


async def _cleanup_task9_v1(
    asyncpg: Any,
    env: dict[str, str],
    database: str,
) -> None:
    conn = await asyncpg.connect(
        host=env["POSTGRES_HOST"],
        port=int(env["POSTGRES_PORT"]),
        database=database,
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )
    try:
        assert await conn.fetchval("SELECT current_database()") == database
        async with conn.transaction():
            for table_name in reversed(tuple(_CHILD_TABLES.values())):
                await conn.execute(
                    f'DELETE FROM "{table_name}" WHERE harvest_state_run_id = $1',
                    _TASK9_V1_RUN_ID,
                )
            await conn.execute("DELETE FROM harvest_state_run WHERE id = $1", _TASK9_V1_RUN_ID)
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM harvest_state_run WHERE id = $1", _TASK9_V1_RUN_ID
            )
            == 0
        )
    finally:
        await conn.close()


def _assert_no_v2_or_agent_season_fields(canonical_output: str) -> None:
    payload = json.loads(canonical_output)
    assert "forecast_season_id" not in payload
    assert "forecast_season_identity" not in payload["input_snapshot"]
    serialized = canonical_json_dumps(payload)
    assert "season_resolution_policy_version" not in serialized
    assert "season_resolution_policy_config_hash" not in serialized


# ---------------------------------------------------------------------------
# Live assertions
# ---------------------------------------------------------------------------


def test_live_current_database_matches_isolated_db_name() -> None:
    """``SELECT current_database()`` must equal the resolved isolated name.

    The CI step ``Resolve isolated test database name`` writes the
    name to ``$GITHUB_ENV``. If anything between that step and the
    pytest step silently re-pointed the connection at a different
    database (the dev / production / cluster-default path that
    slice-1 is meant to block), this assertion fails loud.
    """

    env = _required_live_env()
    expected_db = env["ISOLATED_DB_NAME"]

    # Import asyncpg lazily: we don't want a missing optional dep to
    # mask the ``pytest.skip`` path above. The test infra already
    # requires asyncpg (it is in ``backend/app/``'s dependency
    # graph), so the import should succeed in CI; the try/except
    # keeps local dev running if a user has stripped optional deps.
    try:
        import asyncpg  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - optional dep
        pytest.skip("asyncpg is not installed in this environment")

    actual_db = asyncio.run(_fetch_current_database(asyncpg, env, database=expected_db))

    assert actual_db == expected_db, (
        "current_database() did not match ISOLATED_DB_NAME — "
        "the pytest step is bound to a different database than the "
        "CI round-trip step"
    )


def test_live_alembic_version_equals_current_head() -> None:
    """``alembic_version.version_num`` must equal the Alembic head.

    The CI round-trip is the authoritative proof of upgrade; this
    assertion catches the case where the round-trip's
    ``downgrade 0010_harvest_state_persistence`` /
    ``upgrade head`` chain ended in a state that does not match the
    project head (for example because a future downgrade
    accidentally downgraded past head, or because an env var caused
    the second ``upgrade head`` to bind to the wrong database).
    """

    env = _required_live_env()
    expected_head = _expected_head_revision()
    expected_db = env["ISOLATED_DB_NAME"]

    try:
        import asyncpg  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - optional dep
        pytest.skip("asyncpg is not installed in this environment")

    actual_version = asyncio.run(_fetch_alembic_version(asyncpg, env, database=expected_db))

    assert actual_version is not None, (
        "alembic_version table is empty — the CI round-trip did not "
        "leave the isolated database at any revision"
    )
    assert actual_version == expected_head, (
        f"alembic_version.version_num={actual_version!r} does not "
        f"match the project head {expected_head!r}"
    )


def test_live_task9_completed_v1_data_survives_0015_0016_round_trip(
    record_property: Callable[[str, object], None],
) -> None:
    """Preserve Task 9 data across 0015/0016 while restoring current head.

    The compatibility transition is fixed at 0015 -> 0016 -> 0015. The
    project's terminal head is resolved dynamically and may be later than
    0016, so the final upgrade restores that discovered head.
    """

    from alembic import command

    env = _required_live_env()
    database = env["ISOLATED_DB_NAME"]
    expected_head = _expected_head_revision()
    golden = _load_task9_v1_golden()
    expected_counts = {
        "runs": 1,
        "pool_rows": len(golden["daily_pool_state_rows"]),
        "member_rows": len(golden["daily_member_state_rows"]),
        "cohort_rows": len(golden["cohort_transition_rows"]),
        "future_arrival_rows": len(golden["future_arrival_schedule"]),
    }

    try:
        import asyncpg  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - optional dep
        pytest.skip("asyncpg is not installed in this environment")

    config = _alembic_config()
    baseline: dict[str, Any] | None = None
    try:
        assert asyncio.run(_fetch_current_database(asyncpg, env, database=database)) == database
        record_property("isolated_database", database)
        assert asyncio.run(_fetch_alembic_version(asyncpg, env, database=database)) == expected_head
        record_property("starting_alembic_head", expected_head)

        command.downgrade(config, _REVISION_0015)
        assert (
            asyncio.run(_fetch_alembic_version(asyncpg, env, database=database)) == _REVISION_0015
        )
        record_property("seed_revision", _REVISION_0015)
        baseline = asyncio.run(_seed_task9_v1_and_read_evidence(asyncpg, env, database, golden))
        assert baseline["counts"] == expected_counts
        assert baseline["canonical_output"] == canonical_json_dumps(golden)
        assert baseline["canonical_hash"] == sha256_hex(golden)
        assert baseline["result_hash"] == _TASK9_V1_RESULT_HASH
        assert baseline["canonical_payload_hash"] == sha256_hex(golden)
        _assert_no_v2_or_agent_season_fields(baseline["canonical_output"])
        record_property("baseline_canonical_hash", baseline["canonical_hash"])
        record_property("baseline_result_hash", baseline["result_hash"])
        record_property("baseline_canonical_payload_hash", baseline["canonical_payload_hash"])
        for family, count in baseline["counts"].items():
            record_property(f"baseline_count_{family}", count)
        for family, semantic_hash in baseline["child_semantic_hashes"].items():
            record_property(f"baseline_child_hash_{family}", semantic_hash)

        command.upgrade(config, _REVISION_0016)
        revision, has_forecast_season, after_upgrade = asyncio.run(
            _read_live_state(asyncpg, env, database)
        )
        assert revision == _REVISION_0016
        assert has_forecast_season is True
        assert after_upgrade == baseline
        _assert_no_v2_or_agent_season_fields(after_upgrade["canonical_output"])
        record_property("upgrade_revision", revision)
        record_property("legacy_forecast_season_id", "NULL")

        command.downgrade(config, _REVISION_0015)
        revision, has_forecast_season, after_downgrade = asyncio.run(
            _read_live_state(asyncpg, env, database)
        )
        assert revision == _REVISION_0015
        assert has_forecast_season is False
        assert after_downgrade == baseline
        _assert_no_v2_or_agent_season_fields(after_downgrade["canonical_output"])
        record_property("downgrade_revision", revision)
    finally:
        command.upgrade(config, "head")
        final_revision = asyncio.run(_fetch_alembic_version(asyncpg, env, database=database))
        assert final_revision == expected_head
        asyncio.run(_cleanup_task9_v1(asyncpg, env, database))
        assert asyncio.run(_fetch_alembic_version(asyncpg, env, database=database)) == expected_head
        record_property("final_alembic_head", expected_head)
        record_property("test_run_cleaned", True)

    assert baseline is not None


__all__ = [
    "test_live_current_database_matches_isolated_db_name",
    "test_live_alembic_version_equals_current_head",
    "test_live_task9_completed_v1_data_survives_0015_0016_round_trip",
]
