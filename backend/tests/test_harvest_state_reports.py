from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from backend.app.harvest_state.reports import (
    CSV_REPORT_SCHEMA_VERSION,
    JSON_REPORT_SCHEMA_VERSION,
    render_harvest_state_csv_report,
    render_harvest_state_json_report,
)

GOLDEN_DIR = Path("backend/tests/harvest_state/golden")


def test_json_report_is_byte_deterministic(completed_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    first = render_harvest_state_json_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )
    second = render_harvest_state_json_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )

    assert first == second
    payload = json.loads(first)
    assert payload["report_schema_version"] == JSON_REPORT_SCHEMA_VERSION
    assert payload["run"]["result_hash"] == completed_harvest_state_output.result_hash


def test_csv_report_zip_bytes_are_deterministic(completed_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    first = render_harvest_state_csv_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )
    second = render_harvest_state_csv_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )

    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist()[0] == "manifest.json"
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["report_schema_version"] == CSV_REPORT_SCHEMA_VERSION


def test_json_report_completed_golden(completed_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    actual = render_harvest_state_json_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )
    assert actual == (GOLDEN_DIR / "harvest_state_report_completed.json").read_bytes()


def test_json_report_blocked_golden(blocked_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    actual = render_harvest_state_json_report(
        run_id=2,
        created_at=created_at,
        output=blocked_harvest_state_output,
    )
    assert actual == (GOLDEN_DIR / "harvest_state_report_blocked.json").read_bytes()


def test_csv_report_completed_golden(completed_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    actual = render_harvest_state_csv_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )
    assert actual == (GOLDEN_DIR / "harvest_state_report_completed.zip").read_bytes()


def test_csv_report_blocked_golden(blocked_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    actual = render_harvest_state_csv_report(
        run_id=2,
        created_at=created_at,
        output=blocked_harvest_state_output,
    )
    assert actual == (GOLDEN_DIR / "harvest_state_report_blocked.zip").read_bytes()
