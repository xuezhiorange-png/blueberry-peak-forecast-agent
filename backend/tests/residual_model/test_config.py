from __future__ import annotations

from pathlib import Path


def test_load_residual_model_config() -> None:
    from backend.app.residual_model.config import load_residual_model_config

    config = load_residual_model_config(
        Path("/Users/charles/Documents/智能agent开发/configs/residual_model.yaml")
    )

    assert config.rules.model_family == "hist_gradient_boosting_quantile"
    assert config.rules.quantiles == (0.5, 0.8, 0.9)
    assert len(config.config_hash) == 64

