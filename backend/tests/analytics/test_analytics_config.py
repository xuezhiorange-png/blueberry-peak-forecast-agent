from pathlib import Path

import pytest

from backend.app.analytics.config import load_analytics_config


def _write_rules(path: Path, extra: str = "") -> None:
    path.write_text(
        f"""
version: "task3-v1"
analysis_months: [1, 2, 3, 4]
rolling_window_days: 3
stable_peak_method: "median"
mean_peak_method: "mean"
peak_concentration_definition: "stable_median_3d_peak_over_total"
spring_festival_codes:
  - "spring_festival"
unknown_farm_key: "__UNKNOWN_FARM__"
unknown_subfarm_key: "__UNKNOWN_SUBFARM__"
stream_batch_size: 5000
{extra}
""",
        encoding="utf-8",
    )


def test_load_analytics_config_returns_expected_values_and_stable_hash(tmp_path: Path) -> None:
    rules_path = tmp_path / "analytics_rules.yaml"
    _write_rules(rules_path)

    first = load_analytics_config(rules_path)
    second = load_analytics_config(rules_path)

    assert first.rules.version == "task3-v1"
    assert first.rules.analysis_months == (1, 2, 3, 4)
    assert first.rules.rolling_window_days == 3
    assert first.rules.stable_peak_method == "median"
    assert first.rules.mean_peak_method == "mean"
    assert first.rules.peak_concentration_definition == "stable_median_3d_peak_over_total"
    assert first.rules.spring_festival_codes == ("spring_festival",)
    assert first.rules.unknown_farm_key == "__UNKNOWN_FARM__"
    assert first.rules.unknown_subfarm_key == "__UNKNOWN_SUBFARM__"
    assert first.rules.stream_batch_size == 5000
    assert first.config_hash == second.config_hash
    assert first.snapshot == second.snapshot


def test_load_analytics_config_rejects_unknown_fields(tmp_path: Path) -> None:
    rules_path = tmp_path / "analytics_rules.yaml"
    _write_rules(rules_path, extra='unknown_field: "nope"\n')

    with pytest.raises(ValueError, match="unknown_field"):
        load_analytics_config(rules_path)
