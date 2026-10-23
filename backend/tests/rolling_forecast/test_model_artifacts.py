"""No missing/forged file can become a fallback M1."""

import hashlib
import json

import pytest

from backend.app.rolling_forecast import model_artifacts as models
from backend.research.v019_daily_curve import canonical_bytes
from backend.tests.rolling_forecast.training_fixture import frozen_document


def reference(tmp_path):
    path = tmp_path.resolve() / "SYNTHETIC-models.json"
    data = frozen_document()
    raw = canonical_bytes(data)
    path.write_bytes(raw)
    ref = models.ModelReference(
        reference="SYNTHETIC",
        path=str(path),
        file_sha256=hashlib.sha256(raw).hexdigest(),
        fit_sha256=data["payload"]["experiments"]["B"]["sha256"],
        source_code_identity="a" * 64,
        source_code_sha="0" * 40,
        provenance="SYNTHETIC_TEST_FIXTURE",
    )
    return ref, data


def test_frozen_parameters_restore_without_any_fit_or_source_access(tmp_path, monkeypatch):
    ref, _ = reference(tmp_path)

    def forbidden(*a, **k):
        raise AssertionError("TRAINING_EXECUTED")

    monkeypatch.setattr(
        "backend.app.area_yield.weather_aware_backtest.fit_ridge_artifact", forbidden
    )
    pair = models.load(ref)
    assert pair == models.load(ref) and len(pair.artifacts) == 2


@pytest.mark.parametrize(
    "field,value",
    [("file_sha256", "b" * 64), ("fit_sha256", "b" * 64), ("source_code_identity", "b" * 64)],
)
def test_wrong_identity_rejected(tmp_path, field, value):
    ref, _ = reference(tmp_path)
    with pytest.raises(models.ModelArtifactError, match="MODEL_IDENTITY_MISMATCH"):
        models.load(ref.model_copy(update={field: value}))


def test_missing_corrupt_and_relative_model_never_fallback(tmp_path):
    ref, _ = reference(tmp_path)
    with pytest.raises(models.ModelArtifactError, match="UNAVAILABLE"):
        models.load(ref.model_copy(update={"path": str(tmp_path.resolve() / "missing")}))
    with pytest.raises(models.ModelArtifactError, match="IDENTITY"):
        models.load(ref.model_copy(update={"path": "relative.json"}))
    from pathlib import Path

    Path(ref.path).write_text(json.dumps({"M1": "RANDOM_OR_STATIC"}))
    with pytest.raises(models.ModelArtifactError, match="IDENTITY"):
        models.load(ref)


def test_real_provenance_requires_exact_independent_execution_manifest(tmp_path):
    ref, _ = reference(tmp_path)
    real = ref.model_copy(update={"provenance": "REAL_FROZEN_S6"})
    with pytest.raises(models.ModelArtifactError, match="IDENTITY"):
        models.load(real)
    path = tmp_path.resolve() / "execution.json"
    manifest = {
        "code_git_sha": ref.source_code_sha,
        "code_identity": ref.source_code_identity,
        "task_id": "V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1",
        "phase": "predict",
        "file_sha256": {"SYNTHETIC-models.json": ref.file_sha256},
    }
    raw = json.dumps(manifest).encode()
    path.write_bytes(raw)
    real = real.model_copy(
        update={
            "execution_manifest_path": str(path),
            "execution_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
    assert models.load(real) == models.load(ref)
    manifest["code_git_sha"] = "f" * 40
    raw = json.dumps(manifest).encode()
    path.write_bytes(raw)
    forged = real.model_copy(update={"execution_manifest_sha256": hashlib.sha256(raw).hexdigest()})
    with pytest.raises(models.ModelArtifactError, match="IDENTITY"):
        models.load(forged)
