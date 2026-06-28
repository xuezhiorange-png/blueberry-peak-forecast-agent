from __future__ import annotations

import os
from pathlib import Path

from backend.tests.residual_model.support import residual_model_config_path


def test_load_residual_model_config() -> None:
    from backend.app.residual_model.config import load_residual_model_config

    config = load_residual_model_config(residual_model_config_path())

    assert config.rules.model_family == "hist_gradient_boosting_quantile"
    assert config.rules.quantiles == (0.5, 0.8, 0.9)
    assert len(config.config_hash) == 64


def test_load_residual_model_config_from_non_repo_cwd(tmp_path: Path) -> None:
    from backend.app.residual_model.config import load_residual_model_config

    previous_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        config = load_residual_model_config(residual_model_config_path())
    finally:
        os.chdir(previous_cwd)

    assert config.rules.model_family == "hist_gradient_boosting_quantile"
