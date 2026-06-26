from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from enum import Enum

from backend.app.harvest_state.canonical import canonical_decimal_string, canonical_json_dumps
from backend.app.harvest_state.schemas import (
    CohortTransitionRow,
    DailyMemberStateRow,
    DailyPoolStateRow,
    FutureArrivalScheduleRow,
    Task9ABlockedOutput,
    Task9ACompletedOutput,
)

JSON_REPORT_SCHEMA_VERSION = "task9c-harvest-state-json-report-v1"
CSV_REPORT_SCHEMA_VERSION = "task9c-harvest-state-csv-report-v1"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _scalar_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return canonical_decimal_string(value)
    if isinstance(value, Mapping):
        return canonical_json_dumps(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return canonical_json_dumps(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()  # type: ignore[no-any-return]
        except TypeError:
            pass
    if isinstance(value, Enum):
        return _scalar_text(value.value)
    return str(value)


def _csv_bytes(fieldnames: Sequence[str], rows: Iterable[Mapping[str, object]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _scalar_text(row.get(key)) for key in fieldnames})
    return buffer.getvalue().encode("utf-8")


def _run_csv_bytes(
    *,
    run_id: int,
    created_at: datetime,
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> bytes:
    row: dict[str, object] = {
        "run_id": run_id,
        "status": output.status,
        "config_hash": output.config_hash,
        "result_hash": output.result_hash,
        "created_at": created_at.isoformat(),
        "output_schema_version": output.output_schema_version,
    }
    return _csv_bytes(list(row.keys()), [row])


def _warnings_csv_bytes(values: list[str]) -> bytes:
    return _csv_bytes(["warning"], [{"warning": item} for item in values])


def _blockers_csv_bytes(values: list[str]) -> bytes:
    return _csv_bytes(["blocker"], [{"blocker": item} for item in values])


def _row_csv_bytes(
    fieldnames: Sequence[str],
    rows: Sequence[
        DailyPoolStateRow
        | DailyMemberStateRow
        | CohortTransitionRow
        | FutureArrivalScheduleRow
    ],
) -> bytes:
    return _csv_bytes(fieldnames, [row.model_dump(mode="json") for row in rows])


def render_harvest_state_json_report(
    *,
    run_id: int,
    created_at: datetime,
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> bytes:
    payload = {
        "report_schema_version": JSON_REPORT_SCHEMA_VERSION,
        "run": {
            "run_id": run_id,
            "status": output.status,
            "config_hash": output.config_hash,
            "result_hash": output.result_hash,
            "created_at": created_at.isoformat(),
        },
        "output": output.model_dump(mode="json"),
    }
    return f"{canonical_json_dumps(payload)}\n".encode()


def _manifest_payload(
    *,
    run_id: int,
    created_at: datetime,
    output: Task9ACompletedOutput | Task9ABlockedOutput,
    files: list[str],
) -> dict[str, object]:
    return {
        "report_schema_version": CSV_REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "status": output.status,
        "config_hash": output.config_hash,
        "result_hash": output.result_hash,
        "created_at": created_at.isoformat(),
        "files": files,
    }


def render_harvest_state_csv_report(
    *,
    run_id: int,
    created_at: datetime,
    output: Task9ACompletedOutput | Task9ABlockedOutput,
) -> bytes:
    entries: list[tuple[str, bytes]] = []
    if output.status == "completed":
        completed = output
        entries.extend(
            [
                (
                    "daily_pool_state_rows.csv",
                    _row_csv_bytes(
                        list(DailyPoolStateRow.model_fields.keys()),
                        completed.daily_pool_state_rows,
                    ),
                ),
                (
                    "daily_member_state_rows.csv",
                    _row_csv_bytes(
                        list(DailyMemberStateRow.model_fields.keys()),
                        completed.daily_member_state_rows,
                    ),
                ),
                (
                    "cohort_transition_rows.csv",
                    _row_csv_bytes(
                        list(CohortTransitionRow.model_fields.keys()),
                        completed.cohort_transition_rows,
                    ),
                ),
                (
                    "future_arrival_schedule.csv",
                    _row_csv_bytes(
                        list(FutureArrivalScheduleRow.model_fields.keys()),
                        completed.future_arrival_schedule,
                    ),
                ),
                (
                    "source_ref_catalog.json",
                    (
                        canonical_json_dumps(
                            [
                                entry.model_dump(mode="json")
                                for entry in completed.source_ref_catalog
                            ]
                        )
                        + "\n"
                    ).encode("utf-8"),
                ),
                ("warnings.csv", _warnings_csv_bytes(completed.warnings)),
                ("blockers.csv", _blockers_csv_bytes(completed.blockers)),
            ]
        )
    else:
        blocked = output
        entries.extend(
            [
                ("warnings.csv", _warnings_csv_bytes(blocked.warnings)),
                ("blockers.csv", _blockers_csv_bytes(blocked.blockers)),
            ]
        )

    filenames = ["manifest.json", "run.csv", *[name for name, _ in entries]]
    manifest = (
        canonical_json_dumps(
            _manifest_payload(
                run_id=run_id,
                created_at=created_at,
                output=output,
                files=filenames,
            )
        )
        + "\n"
    ).encode("utf-8")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in [
            ("manifest.json", manifest),
            ("run.csv", _run_csv_bytes(run_id=run_id, created_at=created_at, output=output)),
            *entries,
        ]:
            info = zipfile.ZipInfo(filename=name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload)
    return zip_buffer.getvalue()
