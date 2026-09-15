"""Final artifact-set correction policy tests; real raw files stay private."""

import json
import math
from pathlib import Path

import pytest

from scripts.climate_source_r2 import digest
from scripts.normalize_era5_land_historical_weather_final_r1 import (
    CHARACTERIZATION_HASH,
    CORRECTION_VARIABLES,
    POLICY_VERSION,
    RAW_ARTIFACT_SET_HASH,
    SOURCE_MANIFEST_HASH,
    SOURCE_PRODUCT,
    apply_source_correction,
    compare_replays,
    load_final_config,
    validate_characterization,
)

pytestmark = pytest.mark.unit


def test_final_policy_has_no_numeric_envelope_and_only_two_correction_variables() -> None:
    config = load_final_config()
    assert config["source_artifact_policy_version"] == POLICY_VERSION
    assert config["source_manifest_hash"] == SOURCE_MANIFEST_HASH
    assert config["raw_artifact_set_hash"] == RAW_ARTIFACT_SET_HASH
    assert config["characterization_hash"] == CHARACTERIZATION_HASH
    assert config["tp_negative_numeric_envelope"] is None
    assert config["ssrd_negative_numeric_envelope"] is None
    assert CORRECTION_VARIABLES == {"tp", "ssrd"}


@pytest.mark.parametrize("variable", ["tp", "ssrd"])  # type: ignore[untyped-decorator]
@pytest.mark.parametrize("value", [-1e-20, -1e-8, -1.0, -1e9])  # type: ignore[untyped-decorator]
def test_final_policy_zeroes_every_negative_correction_variable_without_threshold(
    variable: str, value: float
) -> None:
    corrected, applied = apply_source_correction(variable, value)
    assert corrected == 0.0
    assert applied is True


@pytest.mark.parametrize("variable", ["tp", "ssrd", "t2m", "d2m", "u10", "v10"])  # type: ignore[untyped-decorator]
@pytest.mark.parametrize("value", [0.0, 1e-20, 0.001, 100.0])  # type: ignore[untyped-decorator]
def test_positive_values_are_bitwise_unchanged(variable: str, value: float) -> None:
    corrected, applied = apply_source_correction(variable, value)
    assert corrected.hex() == value.hex()
    assert applied is False


@pytest.mark.parametrize("variable", ["t2m", "d2m", "u10", "v10"])  # type: ignore[untyped-decorator]
def test_other_variables_are_not_corrected_even_when_negative(variable: str) -> None:
    corrected, applied = apply_source_correction(variable, -2.0)
    assert corrected == -2.0
    assert applied is False


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])  # type: ignore[untyped-decorator]
def test_nonfinite_values_fail_closed(value: float) -> None:
    with pytest.raises(ValueError, match="NONFINITE_NATIVE_VALUE"):
        apply_source_correction("tp", value)


def test_characterization_hash_is_verified_before_acceptance(tmp_path: Path) -> None:
    source = {
        "characterization_hash": "wrong",
        "source_product": SOURCE_PRODUCT,
    }
    path = tmp_path / "characterization.json"
    path.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="CHARACTERIZATION_HASH_MISMATCH"):
        validate_characterization(path)


def test_final_policy_does_not_create_agronomic_features() -> None:
    config = load_final_config()
    assert config["gdd_generated"] is False
    assert config["vpd_generated"] is False
    assert config["et0_generated"] is False
    assert config["weather_model_training"] is False
    assert config["weather_feature_selection"] is False


def test_replay_comparison_requires_byte_identical_outputs(tmp_path: Path) -> None:
    summary = {
        "hourly_row_count": 1,
        "hourly_dataset_hash": "hourly",
        "daily_row_count": 1,
        "daily_dataset_hash": "daily",
        "correction_record_count": 1,
        "correction_record_hash": "corrections",
        "raw_artifact_set_hash": RAW_ARTIFACT_SET_HASH,
    }
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    for directory in (first, second):
        for name in ("hourly.jsonl.gz", "daily.jsonl", "corrections.jsonl"):
            (directory / name).write_bytes(name.encode())
        (directory / "dataset-manifest.json").write_text(json.dumps(summary, sort_keys=True) + "\n")
    assert compare_replays(first, second)["deterministic_replay"] is True


def test_config_hash_is_deterministic() -> None:
    config = load_final_config()
    disk_config = json.loads(Path("configs/era5_land_historical_weather_final_r1.json").read_text())
    assert digest(config) == digest(disk_config)
