from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.cli import run_cli
from backend.app.harvest_state.schemas import Task9ARequest
from backend.tests.harvest_state.conftest import make_request


def _session_factory(sqlite_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    assert sqlite_session.bind is not None
    return async_sessionmaker(sqlite_session.bind, expire_on_commit=False, class_=AsyncSession)


def _request_json() -> dict[str, object]:
    return Task9ARequest.model_validate(make_request()).model_dump(mode="json")


@pytest.mark.asyncio
async def test_cli_run_from_file_and_get(sqlite_session: AsyncSession, tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request_json()), encoding="utf-8")
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_cli(
        ["harvest-state", "run", "--input", str(request_path)],
        session_factory=_session_factory(sqlite_session),
        stdout=stdout,
        stderr=stderr,
        stdin=io.StringIO(""),
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    envelope = json.loads(stdout.getvalue())
    get_stdout = io.StringIO()
    get_code = run_cli(
        ["harvest-state", "get", "--run-id", str(envelope["run_id"])],
        session_factory=_session_factory(sqlite_session),
        stdout=get_stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(""),
    )
    assert get_code == 0
    assert json.loads(get_stdout.getvalue()) == envelope


@pytest.mark.asyncio
async def test_cli_run_from_stdin_and_blocked_exit_zero(
    sqlite_session: AsyncSession,
) -> None:
    payload = _request_json()
    payload["farm_timezone"] = "Bad/Timezone"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_cli(
        ["harvest-state", "run", "--input", "-"],
        session_factory=_session_factory(sqlite_session),
        stdout=stdout,
        stderr=stderr,
        stdin=io.StringIO(json.dumps(payload)),
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue())["status"] == "blocked"


@pytest.mark.asyncio
async def test_cli_json_and_csv_report(sqlite_session: AsyncSession, tmp_path: Path) -> None:
    stdout = io.StringIO()
    run_code = run_cli(
        ["harvest-state", "run", "--input", "-"],
        session_factory=_session_factory(sqlite_session),
        stdout=stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(json.dumps(_request_json())),
    )
    assert run_code == 0
    envelope = json.loads(stdout.getvalue())
    run_id = envelope["run_id"]

    json_report_path = tmp_path / "report.json"
    csv_report_path = tmp_path / "report.zip"
    json_code = run_cli(
        [
            "harvest-state",
            "report",
            "--run-id",
            str(run_id),
            "--format",
            "json",
            "--output",
            str(json_report_path),
        ],
        session_factory=_session_factory(sqlite_session),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        stdin=io.StringIO(""),
    )
    csv_code = run_cli(
        [
            "harvest-state",
            "report",
            "--run-id",
            str(run_id),
            "--format",
            "csv",
            "--output",
            str(csv_report_path),
        ],
        session_factory=_session_factory(sqlite_session),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        stdin=io.StringIO(""),
    )

    assert json_code == 0
    assert csv_code == 0
    assert json.loads(json_report_path.read_text(encoding="utf-8"))["run"]["run_id"] == run_id
    with zipfile.ZipFile(csv_report_path) as archive:
        assert "manifest.json" in archive.namelist()


@pytest.mark.asyncio
async def test_cli_missing_run_exit_code(sqlite_session: AsyncSession) -> None:
    stderr = io.StringIO()
    exit_code = run_cli(
        ["harvest-state", "get", "--run-id", "999"],
        session_factory=_session_factory(sqlite_session),
        stdout=io.StringIO(),
        stderr=stderr,
        stdin=io.StringIO(""),
    )
    assert exit_code == 4
    assert "HARVEST_STATE_RUN_NOT_FOUND" in stderr.getvalue()


@pytest.mark.asyncio
async def test_cli_invalid_input_exit_code(sqlite_session: AsyncSession) -> None:
    payload = _request_json()
    del payload["destination_factory_id"]
    stderr = io.StringIO()

    exit_code = run_cli(
        ["harvest-state", "run", "--input", "-"],
        session_factory=_session_factory(sqlite_session),
        stdout=io.StringIO(),
        stderr=stderr,
        stdin=io.StringIO(json.dumps(payload)),
    )

    assert exit_code == 2
    assert "HARVEST_STATE_DELIVERY_INPUT_ERROR" in stderr.getvalue()


@pytest.mark.asyncio
async def test_cli_missing_input_file_returns_exit_2(sqlite_session: AsyncSession) -> None:
    stderr = io.StringIO()

    exit_code = run_cli(
        ["harvest-state", "run", "--input", "/definitely/missing.json"],
        session_factory=_session_factory(sqlite_session),
        stdout=io.StringIO(),
        stderr=stderr,
        stdin=io.StringIO(""),
    )

    assert exit_code == 2
    assert "HARVEST_STATE_DELIVERY_INPUT_ERROR" in stderr.getvalue()
    assert "traceback" not in stderr.getvalue().lower()
    assert "/definitely/missing.json" not in stderr.getvalue()


@pytest.mark.asyncio
async def test_cli_invalid_utf8_input_returns_exit_2(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_bytes(b"\xff\xfe\x00")
    stderr = io.StringIO()

    exit_code = run_cli(
        ["harvest-state", "run", "--input", str(bad_path)],
        session_factory=_session_factory(sqlite_session),
        stdout=io.StringIO(),
        stderr=stderr,
        stdin=io.StringIO(""),
    )

    assert exit_code == 2
    assert "HARVEST_STATE_DELIVERY_INPUT_ERROR" in stderr.getvalue()
    assert "traceback" not in stderr.getvalue().lower()
    assert str(bad_path) not in stderr.getvalue()


@pytest.mark.asyncio
async def test_cli_unreadable_input_returns_stable_error(
    sqlite_session: AsyncSession,
) -> None:
    stderr = io.StringIO()

    with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
        exit_code = run_cli(
            ["harvest-state", "run", "--input", "/tmp/request.json"],
            session_factory=_session_factory(sqlite_session),
            stdout=io.StringIO(),
            stderr=stderr,
            stdin=io.StringIO(""),
        )

    assert exit_code == 2
    assert "HARVEST_STATE_DELIVERY_INPUT_ERROR" in stderr.getvalue()
    assert "permission denied" not in stderr.getvalue().lower()
    assert "/tmp/request.json" not in stderr.getvalue()


@pytest.mark.asyncio
async def test_cli_unwritable_text_output_returns_exit_10(
    sqlite_session: AsyncSession,
    tmp_path: Path,
) -> None:
    stderr = io.StringIO()

    with patch("pathlib.Path.write_text", side_effect=OSError("permission denied")):
        exit_code = run_cli(
            [
                "harvest-state",
                "run",
                "--input",
                "-",
                "--output",
                str(tmp_path / "result.json"),
            ],
            session_factory=_session_factory(sqlite_session),
            stdout=io.StringIO(),
            stderr=stderr,
            stdin=io.StringIO(json.dumps(_request_json())),
        )

    assert exit_code == 10
    assert "HARVEST_STATE_DELIVERY_INTEGRITY_ERROR" in stderr.getvalue()
    assert "permission denied" not in stderr.getvalue().lower()


@pytest.mark.asyncio
async def test_cli_unwritable_binary_output_returns_exit_10(
    sqlite_session: AsyncSession,
) -> None:
    stdout = io.StringIO()
    run_code = run_cli(
        ["harvest-state", "run", "--input", "-"],
        session_factory=_session_factory(sqlite_session),
        stdout=stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(json.dumps(_request_json())),
    )
    assert run_code == 0
    run_id = json.loads(stdout.getvalue())["run_id"]
    stderr = io.StringIO()

    with patch("pathlib.Path.write_bytes", side_effect=OSError("permission denied")):
        exit_code = run_cli(
            [
                "harvest-state",
                "report",
                "--run-id",
                str(run_id),
                "--format",
                "csv",
                "--output",
                "/tmp/report.zip",
            ],
            session_factory=_session_factory(sqlite_session),
            stdout=io.StringIO(),
            stderr=stderr,
            stdin=io.StringIO(""),
        )

    assert exit_code == 10
    assert "HARVEST_STATE_DELIVERY_INTEGRITY_ERROR" in stderr.getvalue()
    assert "permission denied" not in stderr.getvalue().lower()
    assert "/tmp/report.zip" not in stderr.getvalue()
