from __future__ import annotations

import io
import json
import zipfile
from csv import DictReader
from dataclasses import replace
from datetime import UTC, date, datetime

from backend.app.residual_model.config import load_residual_model_config
from backend.app.residual_model.manifest import manifest_row_payload
from backend.app.residual_model.reporting import (
    PREDICTION_CSV_REPORT_SCHEMA_VERSION,
    PREDICTION_JSON_REPORT_SCHEMA_VERSION,
    TRAINING_CSV_REPORT_SCHEMA_VERSION,
    TRAINING_JSON_REPORT_SCHEMA_VERSION,
    render_residual_prediction_csv_report,
    render_residual_prediction_json_report,
    render_residual_training_csv_report,
    render_residual_training_json_report,
)
from backend.app.residual_model.service import (
    structural_only_prediction,
    train_residual_model_from_manifest,
)
from backend.tests.residual_model.support import residual_model_config_path
from backend.tests.residual_model.test_persistence import _training_row

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_ZIP_EXTERNAL_ATTR = 0o600 << 16
_TRAINING_RUN_HEADER = (
    "run_id,execution_status,eligibility_status,training_signature,"
    "config_hash,manifest_hash,created_at"
)
_ARTIFACTS_HEADER = (
    "quantile_label,artifact_sha256,model_family,model_version,"
    "feature_schema_version,config_hash,training_signature,manifest_hash"
)
_PREDICTION_RUN_HEADER = "run_id,execution_status,mode,prediction_hash,config_hash,created_at"
_PREDICTION_ROWS_HEADER = (
    "model_run_id,prediction_run_id,task9_run_id,task9_result_hash,"
    "destination_factory_id,arrival_local_date,forecast_horizon_days,"
    "structural_p50_kg,structural_p80_kg,structural_p90_kg,"
    "raw_residual_p50_kg,raw_residual_p80_kg,raw_residual_p90_kg,"
    "corrected_raw_p50_kg,corrected_raw_p80_kg,corrected_raw_p90_kg,"
    "corrected_p50_kg,corrected_p80_kg,corrected_p90_kg,"
    "nonnegative_projection_applied,quantile_projection_applied,projection_reasons,"
    "feature_vector_hash,feature_audit_hash,prediction_hash,mode,fallback_reason"
)


def _config():
    return load_residual_model_config(residual_model_config_path())


def _relaxed_config():
    config = _config()
    eligibility = replace(
        config.rules.eligibility,
        min_training_rows=1,
        min_seasons=1,
        min_factories=1,
        max_validation_wmape=1.0,
        require_improvement_over_structural=False,
        max_fallback_rate=1.0,
    )
    return replace(config, rules=replace(config.rules, eligibility=eligibility))


def _eligible_training():
    rows = [
        _training_row(
            index,
            season_id=(index % 2) + 1 if index < 20 else 3,
            split="train" if index < 20 else "validation",
        )
        for index in range(30)
    ]
    result = train_residual_model_from_manifest(rows=rows, config=_relaxed_config())
    assert result.execution_status == "completed"
    assert result.eligibility_status == "eligible"
    manifest_snapshot = {
        "rows": [manifest_row_payload(row) for row in rows],
        "summary": result.input_snapshot["manifest_summary"],
    }
    return result, manifest_snapshot


def _csv_records(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    payload = archive.read(name).decode("utf-8")
    return list(DictReader(io.StringIO(payload)))


def _csv_header(archive: zipfile.ZipFile, name: str) -> str:
    return archive.read(name).decode("utf-8").splitlines()[0]


def _assert_zip_metadata(archive: zipfile.ZipFile, names: list[str]) -> None:
    for name in names:
        info = archive.getinfo(name)
        assert info.date_time == _ZIP_TIMESTAMP
        assert info.compress_type == zipfile.ZIP_STORED
        assert info.create_system == 3
        assert info.external_attr == _ZIP_EXTERNAL_ATTR


def test_training_json_report_is_deterministic() -> None:
    result, manifest_snapshot = _eligible_training()
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)

    first = render_residual_training_json_report(
        run_id=1,
        created_at=created_at,
        output=result,
        manifest_snapshot=manifest_snapshot,
    )
    second = render_residual_training_json_report(
        run_id=1,
        created_at=created_at,
        output=result,
        manifest_snapshot=manifest_snapshot,
    )

    assert first == second
    assert first.endswith(b"\n")
    assert first.startswith(b'{"manifest_snapshot":')
    assert b'"report_schema_version":"task10-residual-training-report-v1"' in first
    payload = json.loads(first)
    assert payload["report_schema_version"] == TRAINING_JSON_REPORT_SCHEMA_VERSION
    assert payload["run"]["training_signature"] == result.training_signature
    assert "artifact_bytes" not in payload["output"]["artifacts"][0]


def test_training_csv_report_is_deterministic() -> None:
    result, manifest_snapshot = _eligible_training()
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    result = result.model_copy(update={"warnings": ("w1", "w2"), "blockers": ("b1",)})

    first = render_residual_training_csv_report(
        run_id=1,
        created_at=created_at,
        output=result,
        manifest_snapshot=manifest_snapshot,
        artifacts=result.artifacts,
    )
    second = render_residual_training_csv_report(
        run_id=1,
        created_at=created_at,
        output=result,
        manifest_snapshot=manifest_snapshot,
        artifacts=result.artifacts,
    )

    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        names = [
            "manifest.json",
            "manifest_rows.csv",
            "run.csv",
            "artifacts.csv",
            "metrics.json",
            "warnings.csv",
            "blockers.csv",
        ]
        assert archive.namelist() == names
        _assert_zip_metadata(archive, names)
        assert _csv_header(archive, "run.csv") == _TRAINING_RUN_HEADER
        assert _csv_header(archive, "artifacts.csv") == _ARTIFACTS_HEADER
        assert json.loads(archive.read("manifest.json"))["report_schema_version"] == (
            TRAINING_CSV_REPORT_SCHEMA_VERSION
        )
        manifest_rows = archive.read("manifest_rows.csv").decode("utf-8")
        parsed_rows = list(DictReader(io.StringIO(manifest_rows)))
        assert parsed_rows[0]["source_refs"] == '["analytics","task9"]'
        assert "['task9', 'analytics']" not in manifest_rows
        assert _csv_records(archive, "warnings.csv") == [{"warning": "w1"}, {"warning": "w2"}]
        assert _csv_records(archive, "blockers.csv") == [{"blocker": "b1"}]


def test_training_json_payload_does_not_attempt_utf8_decode_artifact_bytes() -> None:
    result, manifest_snapshot = _eligible_training()
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)

    payload = render_residual_training_json_report(
        run_id=1,
        created_at=created_at,
        output=result,
        manifest_snapshot=manifest_snapshot,
    )

    decoded = json.loads(payload)
    assert decoded["output"]["artifacts"][0]["metadata"]["binary_sha256"]
    assert "artifact_bytes" not in json.dumps(decoded, ensure_ascii=False)


def test_prediction_json_and_csv_reports_are_deterministic() -> None:
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    prediction = structural_only_prediction(
        model_run_id=1,
        task9_run_id=10,
        task9_result_hash="a" * 64,
        config_hash="b" * 64,
        structural_rows=[
            {
                "destination_factory_id": 1,
                "arrival_local_date": date(2026, 3, 2),
                "forecast_horizon_days": 1,
                "structural_p50_kg": "100",
                "structural_p80_kg": "110",
                "structural_p90_kg": "120",
            }
        ],
        fallback_reason="model_ineligible",
    ).model_copy(update={"warnings": ("w1",), "blockers": ("b1", "b2")})

    json_first = render_residual_prediction_json_report(
        run_id=2,
        created_at=created_at,
        output=prediction,
    )
    json_second = render_residual_prediction_json_report(
        run_id=2,
        created_at=created_at,
        output=prediction,
    )
    csv_first = render_residual_prediction_csv_report(
        run_id=2,
        created_at=created_at,
        output=prediction,
    )
    csv_second = render_residual_prediction_csv_report(
        run_id=2,
        created_at=created_at,
        output=prediction,
    )

    assert json_first == json_second
    assert json_first.endswith(b"\n")
    assert json_first.startswith(b'{"output":')
    assert b'"report_schema_version":"task10-residual-prediction-report-v1"' in json_first
    assert csv_first == csv_second
    payload = json.loads(json_first)
    assert payload["report_schema_version"] == PREDICTION_JSON_REPORT_SCHEMA_VERSION
    assert payload["output"]["warnings"] == ["w1"]
    assert payload["output"]["blockers"] == ["b1", "b2"]
    with zipfile.ZipFile(io.BytesIO(csv_first)) as archive:
        names = ["manifest.json", "run.csv", "prediction_rows.csv", "warnings.csv", "blockers.csv"]
        assert archive.namelist() == names
        _assert_zip_metadata(archive, names)
        assert _csv_header(archive, "run.csv") == _PREDICTION_RUN_HEADER
        assert _csv_header(archive, "prediction_rows.csv") == _PREDICTION_ROWS_HEADER
        assert json.loads(archive.read("manifest.json"))["report_schema_version"] == (
            PREDICTION_CSV_REPORT_SCHEMA_VERSION
        )
        assert _csv_records(archive, "warnings.csv") == [{"warning": "w1"}]
        assert _csv_records(archive, "blockers.csv") == [{"blocker": "b1"}, {"blocker": "b2"}]
