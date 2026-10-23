"""Explicit hash-pinned model loading, reusing S6 seals and parameter restore.

No discovery, training, label file, random coefficients or fallback model.
The path is server-registered, never accepted from an HTTP caller.
"""

import hashlib
import json
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from backend.app.area_yield.v015_harvest_state import FEATURES
from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES
from backend.app.rolling_forecast.schemas import Contract, Hash, Name
from backend.research.v019_origin_models import CONFIG, MODELS, PreparedPair, compile_pair
from backend.research.v019_real_training_cli import unseal


class ModelArtifactError(ValueError):
    pass


class ModelReference(Contract):
    reference: Name
    path: str
    file_sha256: Hash
    fit_sha256: Hash
    source_code_identity: Hash
    source_code_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    experiment: Literal["B"] = "B"
    provenance: Literal["REAL_FROZEN_S6", "SYNTHETIC_TEST_FIXTURE"]
    execution_manifest_path: str | None = None
    execution_manifest_sha256: Hash | None = None


def load(reference: ModelReference) -> PreparedPair:
    path = Path(reference.path)
    try:
        if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("MODEL_IDENTITY_MISMATCH")
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("MODEL_IDENTITY_MISMATCH")
        raw = path.read_bytes()
    except OSError:
        raise ModelArtifactError("MODEL_ARTIFACT_UNAVAILABLE") from None
    except ValueError:
        raise ModelArtifactError("MODEL_IDENTITY_MISMATCH") from None
    try:
        if hashlib.sha256(raw).hexdigest() != reference.file_sha256:
            raise ValueError("MODEL_IDENTITY_MISMATCH")
        document = unseal(json.loads(raw))
        if document["code_identity"] != reference.source_code_identity:
            raise ValueError("MODEL_IDENTITY_MISMATCH")
        if reference.provenance == "REAL_FROZEN_S6":
            if (
                reference.execution_manifest_path is None
                or reference.execution_manifest_sha256 is None
            ):
                raise ValueError("MODEL_IDENTITY_MISMATCH")
            manifest_path = Path(reference.execution_manifest_path)
            if not manifest_path.is_absolute() or any(
                p.is_symlink() for p in (manifest_path, *manifest_path.parents)
            ):
                raise ValueError("MODEL_IDENTITY_MISMATCH")
            manifest_raw = manifest_path.read_bytes()
            manifest = json.loads(manifest_raw)
            if (
                hashlib.sha256(manifest_raw).hexdigest() != reference.execution_manifest_sha256
                or manifest["code_git_sha"] != reference.source_code_sha
                or manifest["code_identity"] != reference.source_code_identity
                or manifest["task_id"] != "V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1"
                or manifest["phase"] != "predict"
                or manifest["file_sha256"][path.name] != reference.file_sha256
            ):
                raise ValueError("MODEL_IDENTITY_MISMATCH")
        fitted = document["experiments"][reference.experiment]
        if fitted["sha256"] != reference.fit_sha256 or fitted["config"] != CONFIG:
            raise ValueError("MODEL_IDENTITY_MISMATCH")
        if set(fitted["training_seasons"]) - {"2023-2024", "2024-2025"}:
            raise ValueError("MODEL_IDENTITY_MISMATCH")
        pair = compile_pair(fitted)
        for model, artifact in pair.artifacts:
            expected = 10 if model == "M0" else 14
            numbers = (
                *artifact.coefficients,
                *artifact.feature_means,
                *artifact.feature_scales,
                artifact.intercept,
            )
            if (
                artifact.model_id != MODELS[model]
                or artifact.feature_names != BASE_FEATURES + (FEATURES if model == "M1" else ())
                or len(artifact.coefficients) != expected
                or len(artifact.feature_means) != expected
                or len(artifact.feature_scales) != expected
                or Decimal(artifact.alpha) != 10
                or not artifact.nonnegative_output_clip
                or any(not Decimal(v).is_finite() for v in numbers)
                or any(Decimal(v) <= 0 for v in artifact.feature_scales)
            ):
                raise ValueError("MODEL_IDENTITY_MISMATCH")
        return pair
    except OSError:
        raise ModelArtifactError("MODEL_ARTIFACT_UNAVAILABLE") from None
    except (ValueError, KeyError, TypeError, ValidationError, DecimalException):
        raise ModelArtifactError("MODEL_IDENTITY_MISMATCH") from None
