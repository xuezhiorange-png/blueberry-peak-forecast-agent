"""Real PostgreSQL: incompatible default clients cannot control synthetic restores."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from backend.tests.safe_pilot import operations
from backend.tests.safe_pilot.pg_diagnostics import PostgresOperationFailure

pytestmark = pytest.mark.postgres


async def test_matching_clients_restore_real_snapshot_despite_newer_path_default(
    pg_auth, tmp_path, monkeypatch
):
    _, factory, _, _, database = pg_auth
    before = await operations.snapshot(factory)
    tools = tmp_path / "SYNTHETIC-incompatible-clients"
    tools.mkdir(mode=0o700)
    for name in ("pg_dump", "pg_restore"):
        script = tools / name
        script.write_text(
            '#!/bin/sh\nif [ "$1" = "--version" ]; then\n'
            f'  echo "{name} (PostgreSQL) 18.1"\n'
            "else\n  exit 97\nfi\n"
        )
        script.chmod(0o700)
    monkeypatch.setenv("PATH", str(tools) + ":" + operations.os.environ["PATH"])
    backup_dir = tmp_path / "SYNTHETIC-backup"
    backup_dir.mkdir(mode=0o700)
    archive, identity = await operations.backup(database, backup_dir)
    original_command = operations.pg_command
    observed = []

    async def observe_restore(arguments, destination):
        probe = await operations.connection(destination)
        try:
            count = await probe.fetchval(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S')"
            )
            assert count == 0
            observed.append("NEW_DATABASE_EMPTY")
        finally:
            await probe.close()
        return await original_command(arguments, destination)

    monkeypatch.setattr(operations, "pg_command", observe_restore)
    async with operations.restored_database(database, archive, identity) as restored:
        probe = await operations.connection(restored)
        try:
            assert (
                await probe.fetchval("SELECT count(*) FROM auth_account")
                == before["auth_account"]["count"]
            )
            for table, expected in before.items():
                rows = await probe.fetch(f"SELECT row_to_json(t)::text AS row FROM {table} t")
                assert operations.row_digest([r["row"] for r in rows]) == expected["sha256"]
        finally:
            await probe.close()
    assert observed == ["NEW_DATABASE_EMPTY"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == identity
    assert await operations.snapshot(factory) == before


async def test_restore_error_keeps_exit_code_redacts_frame_and_drops_only_owned_database(
    pg_auth, tmp_path, monkeypatch
):
    _, factory, _, _, database = pg_auth
    before = await operations.snapshot(factory)
    directory = tmp_path / "SYNTHETIC-backup"
    directory.mkdir(mode=0o700)
    archive, identity = await operations.backup(database, directory)
    original_run = subprocess.run
    targets = []
    secret = "SYNTHETIC-secret-password /Users/SYNTHETIC-private/path postgresql://private"

    def fail_restore(arguments, **options):
        if Path(arguments[0]).name == "pg_restore" and "--dbname" in arguments:
            targets.append(arguments[arguments.index("--dbname") + 1])
            return subprocess.CompletedProcess(
                arguments,
                71,
                secret.encode(),
                b'pg_restore: error: could not execute query: ERROR:  relation "'
                + secret.encode()
                + b'" already exists',
            )
        return original_run(arguments, **options)

    monkeypatch.setattr(subprocess, "run", fail_restore)
    with pytest.raises(PostgresOperationFailure) as caught:
        async with operations.restored_database(database, archive, identity):
            pytest.fail("FAILED_RESTORE_WAS_EXPOSED")
    error = caught.value
    assert error.diagnostic["exit_code"] == 71
    assert error.diagnostic["error_class"] == "OBJECT_ALREADY_EXISTS"
    assert error.diagnostic["archive_validation_status"] == "PASS"
    assert secret not in str(error) + json.dumps(error.diagnostic)
    trace = error.__traceback__
    while trace and trace.tb_frame.f_code.co_name != "pg_command":
        trace = trace.tb_next
    assert trace is not None
    assert secret not in repr(trace.tb_frame.f_locals)
    assert trace.tb_frame.f_locals["environment"] == {}
    probe = await operations.connection(database)
    try:
        assert len(targets) == 1 and targets[0] != database
        assert not await probe.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)", targets[0]
        )
    finally:
        await probe.close()
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == identity
    assert await operations.snapshot(factory) == before


async def test_invalid_archive_stays_fail_closed_even_with_matching_file_hash(pg_auth, tmp_path):
    _, factory, _, _, database = pg_auth
    before = await operations.snapshot(factory)
    archive = tmp_path / "SYNTHETIC-invalid.dump"
    archive.write_bytes(b"SYNTHETIC_NOT_A_POSTGRES_ARCHIVE")
    archive.chmod(0o600)
    identity = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(PostgresOperationFailure) as caught:
        async with operations.restored_database(database, archive, identity):
            pytest.fail("INVALID_ARCHIVE_WAS_EXPOSED")
    assert caught.value.diagnostic["archive_validation_status"] == "FAIL"
    assert caught.value.diagnostic["error_class"] == "INVALID_ARCHIVE"
    assert caught.value.diagnostic["exit_code"] != 0
    assert await operations.snapshot(factory) == before
