from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.baseline.config import load_baseline_config


def test_load_baseline_config_accepts_task4_shape(tmp_path: Path) -> None:
    path = tmp_path / "baseline.yaml"
    path.write_text(
        """
model:
  version: task4-baseline-v1
  target: stable_median_3d_peak_kg
  ridge:
    alpha: 1.0
    fit_intercept: true
  features:
    - total_weight_kg
    - variety_hhi
    - farm_hhi
    - subfarm_hhi
evaluation:
  primary_scheme: leave_one_season_out
  minimum_training_rows: 4
  mape_zero_policy: exclude
  unit: kg
random_seed: 20260621
""",
        encoding="utf-8",
    )
    config = load_baseline_config(path)
    assert config.rules.version == "task4-baseline-v1"
    assert config.rules.ridge.features == (
        "total_weight_kg",
        "variety_hhi",
        "farm_hhi",
        "subfarm_hhi",
    )
    assert config.rules.benchmark_mode == "historical_oracle"
    assert config.rules.production_eligible is False


def test_load_baseline_config_rejects_leaky_feature_list(tmp_path: Path) -> None:
    path = tmp_path / "baseline.yaml"
    path.write_text(
        """
model:
  version: task4-baseline-v1
  target: stable_median_3d_peak_kg
  ridge:
    alpha: 1.0
    fit_intercept: true
  features:
    - total_weight_kg
    - peak_concentration
    - farm_hhi
    - subfarm_hhi
evaluation:
  primary_scheme: leave_one_season_out
  minimum_training_rows: 4
  mape_zero_policy: exclude
  unit: kg
random_seed: 20260621
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ridge features must be exactly"):
        load_baseline_config(path)


def test_baseline_config_hash_is_stable_for_same_input(tmp_path: Path) -> None:
    path = tmp_path / "baseline.yaml"
    path.write_text(
        """
model:
  version: task4-baseline-v1
  target: stable_median_3d_peak_kg
  ridge:
    alpha: 1.0
    fit_intercept: true
  features:
    - total_weight_kg
    - variety_hhi
    - farm_hhi
    - subfarm_hhi
evaluation:
  primary_scheme: leave_one_season_out
  minimum_training_rows: 4
  mape_zero_policy: exclude
  unit: kg
random_seed: 20260621
""",
        encoding="utf-8",
    )
    first = load_baseline_config(path)
    second = load_baseline_config(path)
    assert first.config_hash == second.config_hash
