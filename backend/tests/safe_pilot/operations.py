"""Fail-closed, test-only backup/restore and loopback TLS lifecycle primitives."""

import asyncio
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import uvicorn
from sqlalchemy import event, text

DATABASE = re.compile(r"blueberry_(?:test_auth|test_s5)_[0-9a-f]{32}\Z")
TABLES = (
    "auth_account",
    "auth_resource_grant",
    "operational_peak_forecast_run",
    "operational_peak_forecast_daily",
    "hierarchical_forecast_run",
    "hierarchical_forecast_daily",
)


def guard_business_writes(factory):
    def reject(connection, cursor, statement, parameters, context, many):
        del connection, cursor, parameters, context, many
        sql = statement.lower().lstrip()
        if sql.startswith(("insert", "update", "delete", "truncate", "alter", "drop")) and (
            "operational_peak_forecast" in sql or "hierarchical_forecast" in sql
        ):
            raise AssertionError("SYNTHETIC_READ_PHASE_BUSINESS_WRITE_FORBIDDEN")

    event.listen(factory.kw["bind"].sync_engine, "before_cursor_execute", reject)


def isolated_environment(database):
    if not DATABASE.fullmatch(database):
        raise ValueError("SYNTHETIC_DATABASE_REQUIRED")
    if os.environ.get("POSTGRES_HOST") not in {"127.0.0.1", "localhost"}:
        raise ValueError("LOOPBACK_REQUIRED")
    if os.environ.get("APP_ENV") != "test":
        raise ValueError("TEST_ENVIRONMENT_REQUIRED")
    port = int(os.environ["POSTGRES_PORT"])
    if port in {5432, 5433}:
        raise ValueError("DEDICATED_TEST_PORT_REQUIRED")
    # Never pass passwords on the command line, or inherit a DATABASE_URL/PGSERVICE.
    return {
        "PATH": os.environ["PATH"],
        "PGHOST": os.environ["POSTGRES_HOST"],
        "PGPORT": str(port),
        "PGUSER": os.environ["POSTGRES_USER"],
        "PGPASSWORD": os.environ["POSTGRES_PASSWORD"],
        "PGDATABASE": database,
        "PGCONNECT_TIMEOUT": "5",
    }


async def connection(database):
    env = isolated_environment(database)
    return await asyncpg.connect(
        host=env["PGHOST"],
        port=int(env["PGPORT"]),
        user=env["PGUSER"],
        password=env["PGPASSWORD"],
        database=database,
    )


async def snapshot(factory):
    """All source bytes are hashed, not exposed; row order is deterministic."""
    result = {}
    async with factory() as db:
        for table in TABLES:
            rows = list(
                (await db.scalars(text(f"SELECT row_to_json(t)::text FROM {table} t"))).all()
            )
            result[table] = {
                "count": len(rows),
                "sha256": row_digest(rows),
            }
    return result


def row_digest(rows):
    # Keep PostgreSQL NUMERIC lexemes intact. json.loads defaults to binary float
    # and could collapse two distinct 12-place quantities into the same value.
    canonical = json.dumps(sorted(rows), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def pg_command(arguments, database):
    completed = await asyncio.to_thread(
        subprocess.run,
        arguments,
        env=isolated_environment(database),
        capture_output=True,
        timeout=60,
        check=False,
    )
    # Do not expose SQL, filesystem paths or connection details from tool stderr.
    if completed.returncode:
        raise RuntimeError("SYNTHETIC_POSTGRES_OPERATION_FAILED")
    return completed


async def backup(database, directory):
    if await asyncio.to_thread(Path(directory).is_symlink):
        raise ValueError("PRIVATE_BACKUP_DIRECTORY_REQUIRED")
    directory = await asyncio.to_thread(Path(directory).resolve, strict=True)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError("PRIVATE_BACKUP_DIRECTORY_REQUIRED")
    target = directory / "SYNTHETIC-private.dump"
    # Exclusive reservation; a second run must not overwrite previous evidence.
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    await pg_command(
        ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(target)],
        database,
    )
    target.chmod(0o600)
    return target, hashlib.sha256(target.read_bytes()).hexdigest()


@asynccontextmanager
async def restored_database(source_database, archive, expected_hash):
    from uuid import uuid4

    contents = await asyncio.to_thread(Path(archive).read_bytes)
    if hashlib.sha256(contents).hexdigest() != expected_hash:
        raise ValueError("BACKUP_HASH_MISMATCH")
    admin = await connection(source_database)
    database = "blueberry_test_s5_" + uuid4().hex
    await admin.execute(f'CREATE DATABASE "{database}"')
    try:
        await pg_command(
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                database,
                str(archive),
            ],
            database,
        )
        yield database
    finally:
        # UUID was generated here, never accepted from a cleanup argument.
        await admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        await admin.close()


async def quarantine(factory):
    """Restored snapshots are NOT current permission authority; revoke everything.

    Do not serve the restored database until this transaction commits. Explicit
    administrator reapproval from the CURRENT trusted catalog is then required.
    Never restore MCP policy/keys from a DB dump.
    """
    async with factory() as db, db.begin():
        isolated_environment(await db.scalar(text("SELECT current_database()")))
        await db.execute(
            text(
                "UPDATE auth_account SET auth_revision=auth_revision+1, "
                "grant_revision=grant_revision+1"
            )
        )
        await db.execute(
            text(
                "UPDATE auth_session SET revoked_at=COALESCE(revoked_at,now()), "
                "revoke_reason='SYNTHETIC_RESTORE_QUARANTINE'"
            )
        )
        await db.execute(
            text("UPDATE auth_resource_grant SET revoked_at=COALESCE(revoked_at,now())")
        )
        from sqlalchemy import select

        from backend.app.local_auth.models import AuthAccount
        from backend.app.local_auth.passwords import hash_password

        # A backup may predate a password reset. Never revive that old credential.
        # Random replacement values are discarded, not published as default logins.
        for account in (await db.scalars(select(AuthAccount))).all():
            account.password_hash = await asyncio.to_thread(
                hash_password, secrets.token_urlsafe(48)
            )
            account.must_change_password = True
        # Preserve the restoration event using the existing audited schema.
        from backend.app.local_auth.models import AuthAuditEvent
        from backend.app.local_auth.sessions import now

        db.add(
            AuthAuditEvent(
                action="SYNTHETIC_RESTORE_QUARANTINE",
                result_code="SUCCESS",
                reason_code="SYNTHETIC_REAPPROVAL_REQUIRED",
                occurred_at=now(),
            )
        )


async def approve_synthetic_recovery_password(factory, account_id, password):
    """Explicit TEST operator recovery, never a production bootstrap/reset path."""
    from backend.app.local_auth.models import AuthAccount, AuthAuditEvent
    from backend.app.local_auth.passwords import hash_password
    from backend.app.local_auth.sessions import now

    async with factory() as db, db.begin():
        database = await db.scalar(text("SELECT current_database()"))
        if not DATABASE.fullmatch(database) or not password.startswith("SYNTHETIC-"):
            raise ValueError("SYNTHETIC_RECOVERY_ONLY")
        account = await db.get(AuthAccount, account_id, with_for_update=True)
        if account is None or not account.username_normalized.startswith("synthetic-"):
            raise ValueError("SYNTHETIC_ACCOUNT_REQUIRED")
        account.password_hash = await asyncio.to_thread(hash_password, password)
        account.must_change_password = False
        account.auth_revision += 1
        db.add(
            AuthAuditEvent(
                action="SYNTHETIC_OPERATOR_RECOVERY",
                result_code="SUCCESS",
                target_account_id=account.account_id,
                reason_code="SYNTHETIC_EXPLICIT_REAPPROVAL",
                occurred_at=now(),
            )
        )


@asynccontextmanager
async def tls_server(app, directory):
    directory = Path(directory)
    key, cert = directory / "SYNTHETIC.key", directory / "SYNTHETIC.crt"
    await asyncio.to_thread(
        subprocess.run,
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=SYNTHETIC_ONLY",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        capture_output=True,
        check=True,
    )
    key.chmod(0o600)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            ssl_keyfile=str(key),
            ssl_certfile=str(cert),
            proxy_headers=False,
            lifespan="off",
            access_log=False,
            log_level="warning",
            timeout_graceful_shutdown=1,
        )
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("SYNTHETIC_TLS_START_FAILED")
                await asyncio.sleep(0)
        yield f"https://127.0.0.1:{port}", cert, server
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 5)
        finally:
            listener.close()
        assert task.done() and listener.fileno() == -1


def assert_redacted(contents, secrets):
    for secret in secrets:
        if secret and secret in contents:
            raise AssertionError("SENSITIVE_LOG_VALUE_FOUND")
