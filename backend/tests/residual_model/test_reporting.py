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
    return rows, result, manifest_snapshot


def test_training_json_report_is_deterministic() -> None:
    _rows, result, manifest_snapshot = _eligible_training()
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
    payload = json.loads(first)
    assert payload["report_schema_version"] == TRAINING_JSON_REPORT_SCHEMA_VERSION
    assert payload["run"]["training_signature"] == result.training_signature
    assert "artifact_bytes" not in payload["output"]["artifacts"][0]


def test_training_csv_report_is_deterministic() -> None:
    _rows, result, manifest_snapshot = _eligible_training()
    created_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)

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
        assert archive.namelist() == [
            "manifest.json",
            "manifest_rows.csv",
            "run.csv",
            "artifacts.csv",
            "metrics.json",
            "warnings.csv",
            "blockers.csv",
        ]
        manifest = json.loads(archive.read("manifest.json"))
        manifest_rows = archive.read("manifest_rows.csv").decode("utf-8")
        assert manifest["report_schema_version"] == TRAINING_CSV_REPORT_SCHEMA_VERSION
        parsed_rows = list(DictReader(io.StringIO(manifest_rows)))
        assert parsed_rows[0]["source_refs"] == '["analytics","task9"]'
        assert "['task9', 'analytics']" not in manifest_rows


def test_training_json_payload_does_not_attempt_utf8_decode_artifact_bytes() -> None:
    _rows, result, manifest_snapshot = _eligible_training()
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
    )

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
    assert csv_first == csv_second
    assert json.loads(json_first)["report_schema_version"] == PREDICTION_JSON_REPORT_SCHEMA_VERSION
    with zipfile.ZipFile(io.BytesIO(csv_first)) as archive:
        assert archive.namelist() == [
            "manifest.json",
            "run.csv",
            "prediction_rows.csv",
            "warnings.csv",
            "blockers.csv",
        ]
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["report_schema_version"] == PREDICTION_CSV_REPORT_SCHEMA_VERSION
