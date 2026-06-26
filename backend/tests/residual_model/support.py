from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def residual_model_config_path() -> Path:
    return repo_root() / "configs" / "residual_model.yaml"
