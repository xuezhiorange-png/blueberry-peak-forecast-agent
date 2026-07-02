from __future__ import annotations

import io
import json
import zipfile
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.cli import run_cli
from backend.app.harvest_state.canonical import canonical_json_dumps
from backend.tests.residual_model.test_training_manifest import (
    _config,
    _persist_task9_run,
    _seed_build_run,
    _seed_daily_fact,
    _seed_master_data,
    _seed_season,
    _snapshot_as_of_date,
    _supplemental_features,
)

pytest_plugins = ("backend.tests.residual_model.test_training_manifest",)
pytestmark = pytest.mark.asyncio


def _sample_payload(seeded: dict[str, object]) -> dict[str, object]:
    return {
        "task9_run_id": seeded["task9_run_id"],
        "label_analytics_build_run_id": seeded["label_analytics_build_run_id"],
        "feature_analytics_build_run_id": seeded["feature_analytics_build_run_id"],
        "supplemental_feature_values": seeded["supplemental_feature_values"],
    }


def _session_factory(sqlite_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    assert sqlite_session.bind is not None
    return async_sessionmaker(sqlite_session.bind, expire_on_commit=False, class_=AsyncSession)


def _relaxed_config_path(tmp_path: Path) -> Path:
    config = _config()
    eligibility = replace(
        config.rules.eligibility,
        min_training_rows=1,
        min_seasons=1,
        min_factories=1,
        max_validation_wmape=Decimal("10"),
        require_improvement_over_structural=False,
        max_fallback_rate=Decimal("1"),
    )
    rules = replace(config.rules, eligibility=eligibility)
    relaxed = replace(config, rules=rules)
    snapshot = deepcopy(config.snapshot)
    snapshot["eligibility"] = {
        "min_training_rows": relaxed.rules.eligibility.min_training_rows,
        "min_seasons": relaxed.rules.eligibility.min_seasons,
        "min_factories": relaxed.rules.eligibility.min_factories,
        "max_validation_wmape": relaxed.rules.eligibility.max_validation_wmape,
        "require_improvement_over_structural": (
            relaxed.rules.eligibility.require_improvement_over_structural
        ),
        "max_fallback_rate": relaxed.rules.eligibility.max_fallback_rate,
    }
    path = tmp_path / "residual_model.yaml"
    path.write_text(canonical_json_dumps(snapshot), encoding="utf-8")
    return path


@pytest.fixture
async def seeded_residual_inputs(sqlite_session: AsyncSession) -> dict[str, object]:
    season_id, factory_id, variety_id = await _seed_master_data(sqlite_session)
    validation_season_id = 2
    await _seed_season(
        sqlite_session,
        season_id=validation_season_id,
        code="2026-2027",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
    )
    task9_run_id, output = await _persist_task9_run(sqlite_session)
    as_of_date = _snapshot_as_of_date(output)
    label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=1,
        season_id=season_id,
        source_max_raw_id=100,
        config_hash="a" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=2,
        season_id=season_id,
        source_max_raw_id=50,
        config_hash="b" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_label_build = await _seed_build_run(
        sqlite_session,
        build_run_id=101,
        season_id=validation_season_id,
        source_max_raw_id=200,
        config_hash="c" * 64,
        finished_at=datetime(2026, 3, 20, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    validation_feature_build = await _seed_build_run(
        sqlite_session,
        build_run_id=102,
        season_id=validation_season_id,
        source_max_raw_id=150,
        config_hash="d" * 64,
        finished_at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC),
        covered_factory_ids=(factory_id,),
    )
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=100 + index,
            build_run_id=label_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("100") + Decimal(index),
        )
    for offset, weight in ((1, Decimal("11")), (3, Decimal("13")), (7, Decimal("17"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=200 + offset,
            build_run_id=feature_build.id,
            season_id=season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    for index, target_date in enumerate((date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=300 + index,
            build_run_id=validation_label_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=target_date,
            weight_kg=Decimal("120") + Decimal(index),
        )
    for offset, weight in ((1, Decimal("21")), (3, Decimal("23")), (7, Decimal("27"))):
        await _seed_daily_fact(
            sqlite_session,
            fact_id=400 + offset,
            build_run_id=validation_feature_build.id,
            season_id=validation_season_id,
            factory_id=factory_id,
            variety_id=variety_id,
            receipt_date=as_of_date - timedelta(days=offset),
            weight_kg=weight,
        )
    await sqlite_session.commit()
    return {
        "task9_run_id": task9_run_id,
        "label_analytics_build_run_id": label_build.id,
        "feature_analytics_build_run_id": feature_build.id,
        "validation_label_analytics_build_run_id": validation_label_build.id,
        "validation_feature_analytics_build_run_id": validation_feature_build.id,
        "supplemental_feature_values": [
            item.model_dump(mode="json") for item in _supplemental_features(as_of_date=as_of_date)
        ],
    }


async def test_residual_cli_build_manifest(
    sqlite_session: AsyncSession,
    tmp_path: Path,
    seeded_residual_inputs: dict[str, object],
) -> None:
    request_path = tmp_path / "manifest_request.json"
    request_path.write_text(
        json.dumps({"samples": [{**_sample_payload(seeded_residual_inputs), "split": "train"}]}),
        encoding="utf-8",
    )
    stdout = io.StringIO()

    exit_code = run_cli(
        ["residual-model", "build-manifest", "--input", str(request_path)],
        session_factory=_session_factory(sqlite_session),
        stdout=stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(""),
    )

    assert exit_code == 0
    payload = json.loads(stdout.getvalue())
    assert payload
    assert payload[0]["task9_run_id"] == seeded_residual_inputs["task9_run_id"]


async def test_residual_cli_train_and_inspect(
    sqlite_session: AsyncSession,
    tmp_path: Path,
    seeded_residual_inputs: dict[str, object],
) -> None:
    request_path = tmp_path / "train_request.json"
    config_path = _relaxed_config_path(tmp_path)
    samples = [{**_sample_payload(seeded_residual_inputs), "split": "train"} for _ in range(24)] + [
        {
            **_sample_payload(seeded_residual_inputs),
            "label_analytics_build_run_id": seeded_residual_inputs[
                "validation_label_analytics_build_run_id"
            ],
            "feature_analytics_build_run_id": seeded_residual_inputs[
                "validation_feature_analytics_build_run_id"
            ],
            "split": "validation",
        }
        for _ in range(6)
    ]
    request_path.write_text(
        json.dumps({"samples": samples}),
        encoding="utf-8",
    )
    stdout = io.StringIO()

    exit_code = run_cli(
        [
            "residual-model",
            "train",
            "--input",
            str(request_path),
            "--config",
            str(config_path),
        ],
        session_factory=_session_factory(sqlite_session),
        stdout=stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(""),
    )

    assert exit_code == 0
    envelope = json.loads(stdout.getvalue())
    assert envelope["output"]["eligibility_status"] == "eligible"

    inspect_stdout = io.StringIO()
    inspect_code = run_cli(
        ["residual-model", "inspect-training", "--run-id", str(envelope["run_id"])],
        session_factory=_session_factory(sqlite_session),
        stdout=inspect_stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(""),
    )
    assert inspect_code == 0
    assert json.loads(inspect_stdout.getvalue())["run_id"] == envelope["run_id"]


async def test_residual_cli_predict_and_report(
    sqlite_session: AsyncSession,
    tmp_path: Path,
    seeded_residual_inputs: dict[str, object],
) -> None:
    train_request_path = tmp_path / "train_request.json"
    config_path = _relaxed_config_path(tmp_path)
    samples = [{**_sample_payload(seeded_residual_inputs), "split": "train"} for _ in range(24)] + [
        {
            **_sample_payload(seeded_residual_inputs),
            "label_analytics_build_run_id": seeded_residual_inputs[
                "validation_label_analytics_build_run_id"
            ],
            "feature_analytics_build_run_id": seeded_residual_inputs[
                "validation_feature_analytics_build_run_id"
            ],
            "split": "validation",
        }
        for _ in range(6)
    ]
    train_request_path.write_text(
        json.dumps({"samples": samples}),
        encoding="utf-8",
    )
    train_stdout = io.StringIO()
    train_code = run_cli(
        [
            "residual-model",
            "train",
            "--input",
            str(train_request_path),
            "--config",
            str(config_path),
        ],
        session_factory=_session_factory(sqlite_session),
        stdout=train_stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(""),
    )
    assert train_code == 0
    training_envelope = json.loads(train_stdout.getvalue())

    predict_request_path = tmp_path / "predict_request.json"
    predict_request_path.write_text(
        json.dumps(
            {
                "model_run_id": training_envelope["run_id"],
                "task9_run_id": seeded_residual_inputs["task9_run_id"],
                "feature_analytics_build_run_id": seeded_residual_inputs[
                    "feature_analytics_build_run_id"
                ],
                "supplemental_feature_values": seeded_residual_inputs[
                    "supplemental_feature_values"
                ],
            }
        ),
        encoding="utf-8",
    )
    predict_stdout = io.StringIO()
    predict_code = run_cli(
        ["residual-model", "predict", "--input", str(predict_request_path)],
        session_factory=_session_factory(sqlite_session),
        stdout=predict_stdout,
        stderr=io.StringIO(),
        stdin=io.StringIO(""),
    )
    assert predict_code == 0
    prediction_envelope = json.loads(predict_stdout.getvalue())
    assert prediction_envelope["output"]["mode"] == "residual_corrected"

    report_path = tmp_path / "prediction_report.zip"
    report_code = run_cli(
        [
            "residual-model",
            "report",
            "--kind",
            "prediction",
            "--run-id",
            str(prediction_envelope["run_id"]),
            "--format",
            "csv",
            "--output",
            str(report_path),
        ],
        session_factory=_session_factory(sqlite_session),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        stdin=io.StringIO(""),
    )
    assert report_code == 0
    with zipfile.ZipFile(report_path) as archive:
        assert "prediction_rows.csv" in archive.namelist()
