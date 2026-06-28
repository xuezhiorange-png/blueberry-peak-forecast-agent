from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from backend.app.harvest_state.canonical import canonical_decimal_string, canonical_json_dumps
from backend.app.residual_model.schemas import (
    PersistableResidualArtifact,
    ResidualPredictionExecutionResult,
    ResidualPredictionRow,
    ResidualTrainingExecutionResult,
)

TRAINING_JSON_REPORT_SCHEMA_VERSION = "task10-residual-training-report-v1"
TRAINING_CSV_REPORT_SCHEMA_VERSION = "task10-residual-training-csv-report-v1"
PREDICTION_JSON_REPORT_SCHEMA_VERSION = "task10-residual-prediction-report-v1"
PREDICTION_CSV_REPORT_SCHEMA_VERSION = "task10-residual-prediction-csv-report-v1"
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


def _warnings_csv_bytes(values: Sequence[str]) -> bytes:
    return _csv_bytes(["warning"], [{"warning": item} for item in values])


def _blockers_csv_bytes(values: Sequence[str]) -> bytes:
    return _csv_bytes(["blocker"], [{"blocker": item} for item in values])


def _zip_bytes(entries: Sequence[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in entries:
            info = zipfile.ZipInfo(filename=name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload)
    return buffer.getvalue()


def render_residual_training_json_report(
    *,
    run_id: int,
    created_at: datetime,
    output: ResidualTrainingExecutionResult,
    manifest_snapshot: Mapping[str, Any],
) -> bytes:
    output_payload = output.model_dump(mode="python", exclude={"artifacts"})
    output_payload["artifacts"] = [
        {
            "quantile_label": artifact.quantile_label,
            "metadata": artifact.metadata.model_dump(mode="json"),
        }
        for artifact in output.artifacts
    ]
    payload = {
        "report_schema_version": TRAINING_JSON_REPORT_SCHEMA_VERSION,
        "run": {
            "run_id": run_id,
            "execution_status": output.execution_status,
            "eligibility_status": output.eligibility_status,
            "training_signature": output.training_signature,
            "config_hash": output.config_hash,
            "manifest_hash": output.manifest_hash,
            "created_at": created_at.isoformat(),
        },
        "manifest_snapshot": manifest_snapshot,
        "output": output_payload,
    }
    return f"{canonical_json_dumps(payload)}\n".encode()


def render_residual_training_csv_report(
    *,
    run_id: int,
    created_at: datetime,
    output: ResidualTrainingExecutionResult,
    manifest_snapshot: Mapping[str, Any],
    artifacts: Sequence[PersistableResidualArtifact],
) -> bytes:
    manifest_rows = list(manifest_snapshot.get("rows", []))
    entries: list[tuple[str, bytes]] = []
    if manifest_rows:
        fieldnames = list(manifest_rows[0].keys())
        entries.append(("manifest_rows.csv", _csv_bytes(fieldnames, manifest_rows)))
    artifact_rows = [
        {
            "quantile_label": artifact.quantile_label,
            "artifact_sha256": artifact.metadata.binary_sha256,
            "model_family": artifact.metadata.model_family,
            "model_version": artifact.metadata.model_version,
            "feature_schema_version": artifact.metadata.feature_schema_version,
            "config_hash": artifact.metadata.config_hash,
            "training_signature": artifact.metadata.training_signature,
            "manifest_hash": artifact.metadata.manifest_hash,
        }
        for artifact in artifacts
    ]
    entries.extend(
        [
            (
                "run.csv",
                _csv_bytes(
                    [
                        "run_id",
                        "execution_status",
                        "eligibility_status",
                        "training_signature",
                        "config_hash",
                        "manifest_hash",
                        "created_at",
                    ],
                    [
                        {
                            "run_id": run_id,
                            "execution_status": output.execution_status,
                            "eligibility_status": output.eligibility_status,
                            "training_signature": output.training_signature,
                            "config_hash": output.config_hash,
                            "manifest_hash": output.manifest_hash,
                            "created_at": created_at.isoformat(),
                        }
                    ],
                ),
            ),
            (
                "artifacts.csv",
                _csv_bytes(
                    [
                        "quantile_label",
                        "artifact_sha256",
                        "model_family",
                        "model_version",
                        "feature_schema_version",
                        "config_hash",
                        "training_signature",
                        "manifest_hash",
                    ],
                    artifact_rows,
                ),
            ),
            (
                "metrics.json",
                (canonical_json_dumps(output.metrics) + "\n").encode("utf-8"),
            ),
            ("warnings.csv", _warnings_csv_bytes(output.warnings)),
            ("blockers.csv", _blockers_csv_bytes(output.blockers)),
        ]
    )
    files = ["manifest.json", *[name for name, _ in entries]]
    manifest = (
        canonical_json_dumps(
            {
                "report_schema_version": TRAINING_CSV_REPORT_SCHEMA_VERSION,
                "run_id": run_id,
                "training_signature": output.training_signature,
                "config_hash": output.config_hash,
                "manifest_hash": output.manifest_hash,
                "created_at": created_at.isoformat(),
                "files": files,
            }
        )
        + "\n"
    ).encode("utf-8")
    return _zip_bytes([("manifest.json", manifest), *entries])


def render_residual_prediction_json_report(
    *,
    run_id: int,
    created_at: datetime,
    output: ResidualPredictionExecutionResult,
) -> bytes:
    payload = {
        "report_schema_version": PREDICTION_JSON_REPORT_SCHEMA_VERSION,
        "run": {
            "run_id": run_id,
            "execution_status": output.execution_status,
            "mode": output.mode,
            "prediction_hash": output.prediction_hash,
            "config_hash": output.config_hash,
            "created_at": created_at.isoformat(),
        },
        "output": output.model_dump(mode="json"),
    }
    return f"{canonical_json_dumps(payload)}\n".encode()


def render_residual_prediction_csv_report(
    *,
    run_id: int,
    created_at: datetime,
    output: ResidualPredictionExecutionResult,
) -> bytes:
    row_payloads = [row.model_dump(mode="json") for row in output.rows]
    entries: list[tuple[str, bytes]] = [
        (
            "run.csv",
            _csv_bytes(
                [
                    "run_id",
                    "execution_status",
                    "mode",
                    "prediction_hash",
                    "config_hash",
                    "created_at",
                ],
                [
                    {
                        "run_id": run_id,
                        "execution_status": output.execution_status,
                        "mode": output.mode,
                        "prediction_hash": output.prediction_hash,
                        "config_hash": output.config_hash,
                        "created_at": created_at.isoformat(),
                    }
                ],
            ),
        ),
        (
            "prediction_rows.csv",
            _csv_bytes(list(ResidualPredictionRow.model_fields.keys()), row_payloads),
        ),
        ("warnings.csv", _warnings_csv_bytes(output.warnings)),
        ("blockers.csv", _blockers_csv_bytes(output.blockers)),
    ]
    files = ["manifest.json", *[name for name, _ in entries]]
    manifest = (
        canonical_json_dumps(
            {
                "report_schema_version": PREDICTION_CSV_REPORT_SCHEMA_VERSION,
                "run_id": run_id,
                "prediction_hash": output.prediction_hash,
                "config_hash": output.config_hash,
                "created_at": created_at.isoformat(),
                "files": files,
            }
        )
        + "\n"
    ).encode("utf-8")
    return _zip_bytes([("manifest.json", manifest), *entries])
