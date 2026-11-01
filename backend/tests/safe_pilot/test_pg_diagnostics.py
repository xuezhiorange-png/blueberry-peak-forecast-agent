"""Only synthetic error text; public diagnostics must never echo subprocess data."""

import json
import subprocess

import pytest

from backend.tests.safe_pilot.pg_diagnostics import failure, version_number

pytestmark = [pytest.mark.unit, pytest.mark.contract]

FIELDS = {
    "operation",
    "phase",
    "exit_code",
    "client_pg_dump_version",
    "client_pg_restore_version",
    "server_version_num",
    "archive_format",
    "archive_validation_status",
    "error_class",
    "sqlstate_if_reliably_available",
    "diagnostic_evidence_status",
}


@pytest.mark.parametrize(
    ("stderr", "category"),
    [
        (
            b'pg_restore: error: could not execute query: ERROR:  relation "x" already exists',
            "OBJECT_ALREADY_EXISTS",
        ),
        (
            b'pg_restore: error: could not execute query: ERROR:  relation "x" does not exist',
            "OBJECT_MISSING",
        ),
        (
            b"pg_restore: error: could not execute query: ERROR:  permission denied for schema x",
            "PERMISSION_DENIED",
        ),
        (b"pg_dump: error: aborting because of server version mismatch", "VERSION_INCOMPATIBILITY"),
        (
            b"pg_restore: error: could not execute query: ERROR:  "
            b'unrecognized configuration parameter "transaction_timeout"',
            "VERSION_INCOMPATIBILITY",
        ),
        (
            b'pg_restore: error: could not execute query: ERROR:  extension "x" is not available',
            "EXTENSION_OR_SCHEMA_CONFLICT",
        ),
        (
            b"pg_restore: error: could not execute query: ERROR:  "
            b'encoding "UTF8" does not match locale',
            "ENCODING_OR_COLLATION_CONFLICT",
        ),
        (
            b"pg_restore: error: connection to server failed: Connection refused",
            "CONNECTION_FAILURE",
        ),
        (b"pg_restore: error: input file is too short", "INVALID_ARCHIVE"),
        (b"unknown diagnostic with no PostgreSQL error evidence", "UNKNOWN_UNCLASSIFIED"),
    ],
)
def test_only_explicit_postgres_errors_are_classified(stderr, category):
    completed = subprocess.CompletedProcess(["pg_restore"], 7, b"", stderr)
    error = failure(completed, "PG_RESTORE", "18.1", "18.1", 160015, "PASS")
    assert isinstance(error, RuntimeError)
    assert str(error).startswith("SYNTHETIC_POSTGRES_OPERATION_FAILED")
    assert set(error.diagnostic) == FIELDS
    assert error.diagnostic["exit_code"] == 7
    assert error.diagnostic["error_class"] == category
    assert error.diagnostic["sqlstate_if_reliably_available"] is None


@pytest.mark.parametrize("operation", ["PG_DUMP", "PG_RESTORE"])
def test_failure_never_exports_password_sql_paths_or_business_literals(operation):
    secrets = [
        "SYNTHETIC-password-secret",
        "postgresql://SYNTHETIC-user:SYNTHETIC-password-secret@localhost:60000/private",
        "/Users/SYNTHETIC-private-directory/archive.dump",
        "SYNTHETIC-BUSINESS-LITERAL-123456",
        "Cookie=SYNTHETIC-cookie; Token=SYNTHETIC-token",
        "SELECT * FROM SYNTHETIC_private_table",
    ]
    raw = ("pg_restore: error: " + "\n".join(secrets)).encode()
    completed = subprocess.CompletedProcess(secrets, 23, raw, raw)
    error = failure(completed, operation, "16.15", "16.15", 160015, "NOT_PROVEN")
    exported = str(error) + repr(error) + json.dumps(error.diagnostic) + repr(completed)
    assert error.diagnostic["error_class"] == "UNKNOWN_UNCLASSIFIED"
    assert error.diagnostic["exit_code"] == 23
    assert completed.stdout == completed.stderr == b""
    for secret in secrets:
        assert secret not in exported


def test_untrusted_version_or_archive_status_cannot_become_public_text():
    raw = "SYNTHETIC-secret /private/dump postgresql://private"
    completed = subprocess.CompletedProcess(["pg_restore", raw], 1, b"", b"unknown")
    error = failure(completed, "PG_RESTORE", raw, raw, raw, raw)
    assert raw not in str(error)
    assert error.diagnostic["client_pg_dump_version"] is None
    assert error.diagnostic["client_pg_restore_version"] is None
    assert error.diagnostic["server_version_num"] is None
    assert error.diagnostic["archive_validation_status"] == "NOT_PROVEN"


def test_version_parser_accepts_only_exact_postgres_banner():
    assert version_number(b"pg_dump (PostgreSQL) 16.15 (Homebrew)\n", "pg_dump") == "16.15"
    assert version_number(b"pg_restore (PostgreSQL) 18.1\n", "pg_restore") == "18.1"
    assert version_number(b"secret 18.1", "pg_restore") is None
    assert version_number(b"pg_dump (PostgreSQL) 18.1", "pg_restore") is None


@pytest.mark.parametrize("dump_version", ["16.15", "18.1", None])
def test_restore_client_can_emit_unsupported_setting_independently_of_dump_version(dump_version):
    stderr = (
        b'pg_restore: error: ERROR:  unrecognized configuration parameter "transaction_timeout"'
    )
    error = failure(
        subprocess.CompletedProcess(["pg_restore"], 1, b"", stderr),
        "PG_RESTORE",
        dump_version,
        "18.1",
        160015,
        "PASS",
    )
    assert error.diagnostic["error_class"] == "VERSION_INCOMPATIBILITY"
    unproven = failure(
        subprocess.CompletedProcess(["pg_restore"], 1, b"", stderr),
        "PG_RESTORE",
        dump_version,
        None,
        160015,
        "PASS",
    )
    assert unproven.diagnostic["error_class"] == "UNKNOWN_UNCLASSIFIED"


def test_tool_selection_rejects_wrong_major_and_never_executes_it(monkeypatch, tmp_path):
    from backend.tests.safe_pilot.pg_tools import client_for_server

    newer, matching = tmp_path / "newer", tmp_path / "matching"
    newer.mkdir()
    matching.mkdir()
    wrong, right = newer / "pg_restore", matching / "pg_restore"
    for path in (wrong, right):
        path.touch()
    monkeypatch.setattr("shutil.which", lambda name, **_: str(newer / name))
    calls = []

    def version(arguments, **kwargs):
        assert arguments[1:] == ["--version"]
        calls.append(arguments)
        major = "16.15" if arguments[0] == str(right) else "18.1"
        return subprocess.CompletedProcess(
            arguments, 0, f"pg_restore (PostgreSQL) {major}".encode(), b""
        )

    monkeypatch.setattr(subprocess, "run", version)
    selected, version_value = client_for_server("pg_restore", 160015, {}, (right,))
    assert selected == str(right) and version_value == "16.15"
    assert calls == [[str(wrong), "--version"], [str(right), "--version"]]


def test_missing_matching_client_is_fail_closed(monkeypatch, tmp_path):
    from backend.tests.safe_pilot.pg_tools import client_for_server

    wrong = tmp_path / "pg_dump"
    wrong.touch()
    monkeypatch.setattr("shutil.which", lambda name, **_: str(wrong))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda arguments, **_: subprocess.CompletedProcess(
            arguments, 0, b"pg_dump (PostgreSQL) 18.1", b""
        ),
    )
    with pytest.raises(RuntimeError, match="SYNTHETIC_POSTGRES_MATCHING_CLIENT_REQUIRED"):
        client_for_server("pg_dump", 160015, {}, ())


def test_only_client_message_locale_is_fixed(monkeypatch):
    from backend.tests.safe_pilot.operations import isolated_environment

    for key, value in {
        "APP_ENV": "test",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "60000",
        "POSTGRES_USER": "SYNTHETIC-test",
        "POSTGRES_PASSWORD": "SYNTHETIC-not-published",
    }.items():
        monkeypatch.setenv(key, value)
    environment = isolated_environment("blueberry_test_auth_" + "a" * 32)
    assert environment["LC_MESSAGES"] == "C"
    assert "LC_ALL" not in environment
    assert "PGCLIENTENCODING" not in environment
    assert "PGOPTIONS" not in environment


def test_matching_client_failure_frame_contains_no_environment_or_private_paths(
    monkeypatch, tmp_path
):
    from backend.tests.safe_pilot.pg_tools import client_for_server

    secret = "SYNTHETIC-password-and-private-path"
    tool = tmp_path / secret / "pg_dump"
    tool.parent.mkdir()
    tool.touch()
    monkeypatch.setattr("shutil.which", lambda name, **_: str(tool))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [str(tool)], 0, b"pg_dump (PostgreSQL) 18.1\n" + secret.encode(), secret.encode()
        ),
    )
    with pytest.raises(RuntimeError, match="SYNTHETIC_POSTGRES_MATCHING_CLIENT_REQUIRED") as caught:
        client_for_server("pg_dump", 160015, {"PGPASSWORD": secret}, ())
    trace = caught.value.__traceback__
    while trace and trace.tb_frame.f_code.co_name != "client_for_server":
        trace = trace.tb_next
    assert trace is not None
    assert secret not in repr(trace.tb_frame.f_locals)
    assert str(tool) not in repr(trace.tb_frame.f_locals)


async def test_pg_command_matching_client_preflight_exposes_no_credentials(monkeypatch, tmp_path):
    from backend.tests.safe_pilot import operations, pg_tools

    secret = "SYNTHETIC-preflight-private-value"
    for key, value in {
        "APP_ENV": "test",
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "60000",
        "POSTGRES_USER": "SYNTHETIC-test",
        "POSTGRES_PASSWORD": secret,
    }.items():
        monkeypatch.setenv(key, value)
    closed = []

    class Probe:
        async def fetchval(self, statement):
            return 160015

        async def close(self):
            closed.append(True)

    async def connection(database):
        return Probe()

    def unavailable(server, environment):
        assert set(environment) == {"PATH", "LC_MESSAGES"}
        assert secret not in repr(environment)
        raise pg_tools.PostgresClientUnavailable()

    monkeypatch.setattr(operations, "connection", connection)
    monkeypatch.setattr(pg_tools, "toolchain", unavailable)
    with pytest.raises(pg_tools.PostgresClientUnavailable) as caught:
        await operations.pg_command(
            ["pg_restore", "--dbname", "SYNTHETIC", str(tmp_path / secret)],
            "blueberry_test_auth_" + "a" * 32,
        )
    assert closed == [True]
    trace = caught.value.__traceback__
    while trace and trace.tb_frame.f_code.co_name != "pg_command":
        trace = trace.tb_next
    assert trace is not None and trace.tb_next is None
    assert secret not in repr(trace.tb_frame.f_locals)
    assert trace.tb_frame.f_locals["environment"] == {}
