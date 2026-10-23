"""Runtime source identity without Git discovery or access to business artifacts."""

import hashlib
import sys
from pathlib import Path

import numpy

from backend.research.v019_synthetic_validation import digest

FILES = (
    "backend/app/rolling_forecast/engine.py",
    "backend/app/rolling_forecast/schemas.py",
    "backend/app/rolling_forecast/model_artifacts.py",
    "backend/app/rolling_forecast/observations.py",
    "backend/app/rolling_forecast/application.py",
    "backend/app/rolling_forecast/policy.py",
    "backend/app/rolling_forecast/identity.py",
    "backend/app/rolling_forecast/harvest_state.py",
    "backend/app/area_yield/v015_harvest_state.py",
    "backend/app/area_yield/weather_aware_backtest.py",
    "backend/research/v019_origin_models.py",
    "backend/research/v019_origin_evaluation.py",
    "backend/research/v019_synthetic_validation.py",
    "backend/research/v019_daily_curve.py",
)


def _source_hash() -> str:
    root = Path(__file__).resolve().parents[3]
    return digest(
        {
            "source_sha256": {
                p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in FILES
            },
            "python": list(sys.version_info[:3]),
            "numpy": numpy.__version__,
        }
    )


_LOADED_SOURCE_HASH = _source_hash()


def implementation_hash() -> str:
    current = _source_hash()
    if current != _LOADED_SOURCE_HASH:
        raise ValueError("IMPLEMENTATION_SOURCE_MISMATCH")
    return current
