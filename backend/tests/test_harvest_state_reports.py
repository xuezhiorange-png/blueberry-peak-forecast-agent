from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from backend.app.harvest_state.reports import (
    CSV_REPORT_SCHEMA_VERSION,
    JSON_REPORT_SCHEMA_VERSION,
    _csv_bytes,
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


def test_csv_nested_list_uses_canonical_json(completed_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    report = render_harvest_state_csv_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )

    with zipfile.ZipFile(io.BytesIO(report)) as archive:
        csv_text = archive.read("daily_pool_state_rows.csv").decode("utf-8")
    assert '["' in csv_text


def test_csv_does_not_use_python_repr(completed_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    report = render_harvest_state_csv_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )

    with zipfile.ZipFile(io.BytesIO(report)) as archive:
        csv_text = archive.read("daily_pool_state_rows.csv").decode("utf-8")
    assert "['" not in csv_text
    assert "{'" not in csv_text


def test_csv_nested_dict_uses_canonical_json() -> None:
    payload = _csv_bytes(["meta"], [{"meta": {"key": "value", "items": ["a", "b"]}}])
    assert payload.decode("utf-8") == 'meta\n"{""items"":[""a"",""b""],""key"":""value""}"\n'


def test_csv_decimal_format_is_canonical(completed_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    report = render_harvest_state_csv_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )

    with zipfile.ZipFile(io.BytesIO(report)) as archive:
        csv_text = archive.read("daily_pool_state_rows.csv").decode("utf-8")
    assert "48.000" in csv_text
    assert "1.000000" in csv_text


def test_csv_datetime_preserves_timezone_offset(completed_harvest_state_output: object) -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    report = render_harvest_state_csv_report(
        run_id=1,
        created_at=created_at,
        output=completed_harvest_state_output,
    )

    with zipfile.ZipFile(io.BytesIO(report)) as archive:
        csv_text = archive.read("cohort_transition_rows.csv").decode("utf-8")
    assert "+09:00" in csv_text


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
