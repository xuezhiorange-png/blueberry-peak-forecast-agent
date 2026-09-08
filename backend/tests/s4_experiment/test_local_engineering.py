from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.maturity.config import load_maturity_curve_config
from backend.app.s4_candidate_execution import (
    CANDIDATE_01_PARAMETER_MANIFEST_HASH_BOUND,
    build_candidate_01_manifest,
    build_derived_candidate_config,
    validate_candidate_01_manifest,
)
from backend.app.s4_local_engineering import (
    LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS,
    load_frozen_engineering_dataset,
    run_local_replay,
    verify_frozen_source_object,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def dataset():
    return load_frozen_engineering_dataset(REPO_ROOT)


@pytest.fixture(scope="module")
def incumbent_config():
    return load_maturity_curve_config(REPO_ROOT / "configs/maturity_curve.yaml")


def test_frozen_source_and_partition_identity(dataset) -> None:
    source = verify_frozen_source_object(Path("/tmp/source-002-original.xls"))

    assert source.byte_count == 28_668_416
    assert source.sha256 == "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a"
    assert source.row_count == 233_171
    assert len(dataset.train_rows) == 16_224
    assert len(dataset.validation_rows) == 8_006
    assert (
        dataset.train_content_sha256
        == "be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2"
    )
    assert (
        dataset.validation_content_sha256
        == "4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06"
    )
    assert dataset.test_row_count == 0


def test_incumbent_replay_is_deterministic_and_local_only(dataset, incumbent_config) -> None:
    first = run_local_replay(dataset=dataset, config=incumbent_config)
    second = run_local_replay(dataset=dataset, config=incumbent_config)

    assert first.payload() == second.payload()
    assert first.prediction_identity_sha256 == second.prediction_identity_sha256
    assert first.authority_class == LOCAL_ENGINEERING_REPLAY_AUTHORITY_CLASS
    assert first.model_id == "V0_2_CURRENT_MODEL"
    assert first.metrics.comparable_row_count == 8_006


def test_candidate_manifest_is_frozen_to_four_runs() -> None:
    config_path = REPO_ROOT / "configs/maturity_curve.yaml"
    manifest = build_candidate_01_manifest(config_path)
    validate_candidate_01_manifest(manifest, config_path=config_path)

    assert manifest.manifest_hash == CANDIDATE_01_PARAMETER_MANIFEST_HASH_BOUND
    assert manifest.candidate_id == "01_parameter_calibration"
    assert tuple(run.candidate_run_ordinal for run in manifest.runs) == (1, 2, 3, 4)
    assert manifest.planned_run_count == 4


def test_four_candidate_runs_are_paired_to_the_same_validation_labels(
    dataset, incumbent_config
) -> None:
    config_path = REPO_ROOT / "configs/maturity_curve.yaml"
    manifest = build_candidate_01_manifest(config_path)
    incumbent = run_local_replay(dataset=dataset, config=incumbent_config)

    results = []
    for ordinal in range(1, 5):
        run, candidate_config = build_derived_candidate_config(manifest, ordinal)
        result = run_local_replay(dataset=dataset, config=candidate_config)
        results.append((run, result))

    assert len(results) == 4
    assert all(result.metrics.comparable_row_count == 8_006 for _, result in results)
    assert all(
        result.actual_label_set_identity_sha256 == incumbent.actual_label_set_identity_sha256
        for _, result in results
    )
    assert all(
        result.business_grain_set_identity_sha256 == incumbent.business_grain_set_identity_sha256
        for _, result in results
    )
    assert {run.random_seed for run, _ in results} == {20_260_624}


def test_result_payload_is_aggregate_only(dataset, incumbent_config) -> None:
    result = run_local_replay(dataset=dataset, config=incumbent_config)
    payload = result.payload()

    assert "predictions" not in payload
    assert "actual_kg" not in repr(payload)
    assert set(payload["metrics"]["breakdown_metrics"]) == {
        "forecast_horizon_days",
        "farm_business_key",
        "subfarm_business_key",
        "variety_business_key",
        "season_business_key",
        "model_identity",
    }
