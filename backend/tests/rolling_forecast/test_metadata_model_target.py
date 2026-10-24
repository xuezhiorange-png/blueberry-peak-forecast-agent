"""S6 family declaration is not model-file validation; SYNTHETIC fixtures only."""

import json
from pathlib import Path

import pytest

from backend.app.rolling_forecast import inbound, model_artifacts
from backend.tests.rolling_forecast.inbound_fixture import write
from backend.tests.rolling_forecast.source_readiness_package import create_package
from backend.tests.rolling_forecast.test_source_readiness import inspect


@pytest.fixture
def real_format_catalog(tmp_path):
    # Public frozen SYNTHETIC parameters in a valid S6 provenance envelope,
    # never a claim to be real training data or real model-parameter evidence.
    catalog, _ = create_package(tmp_path / "SYNTHETIC-package")
    c = catalog.contexts[0]
    model = c.models[0]
    manifest = dict(
        task_id="V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1",
        phase="predict",
        code_git_sha=model.source_code_sha,
        code_identity=model.source_code_identity,
        file_sha256={Path(model.path).name: model.file_sha256},
    )
    path = tmp_path.resolve() / "SYNTHETIC-execution-manifest.json"
    sha = write(path, manifest)
    model = model.model_copy(
        update=dict(
            provenance="REAL_FROZEN_S6",
            model_training_target_quantity_basis=None,
            execution_manifest_path=str(path),
            execution_manifest_sha256=sha,
        )
    )
    return catalog.model_copy(update={"contexts": (c.model_copy(update={"models": (model,)}),)})


def metadata_without_model_or_day_io(catalog, monkeypatch):
    source = catalog.contexts[0].snapshots[0]
    original = Path.open
    opened = []

    def guarded(path, *args, **kwargs):
        assert str(path) == source.manifest_path, "METADATA_OPENED_MODEL_OR_DAY"
        opened.append(path)
        return original(path, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("METADATA_CALLED_MODEL_LOADER")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", guarded)
        patch.setattr(model_artifacts, "load", forbidden)
        result = inspect(catalog)
    assert opened and result["day_payloads_read"] == 0
    assert result["model_contents_validated"] is False
    return result


@pytest.mark.parametrize("explicit", [None, "RECORDED_INBOUND_WEIGHT"])
def test_real_s6_optional_target_matches_s8_after_independent_validation(
    real_format_catalog, monkeypatch, explicit
):
    c = real_format_catalog.contexts[0]
    model = c.models[0].model_copy(update={"model_training_target_quantity_basis": explicit})
    catalog = real_format_catalog.model_copy(
        update={"contexts": (c.model_copy(update={"models": (model,)}),)}
    )
    # The actual S8 loader verifies frozen SYNTHETIC bytes first, outside the
    # S9 no-I/O guard. S9 itself neither opens nor claims to validate them.
    pair = model_artifacts.load(model)
    inbound.require_target(c.snapshots[0], pair)
    result = metadata_without_model_or_day_io(catalog, monkeypatch)
    assert result["status"] == "METADATA_VALID"
    assert (
        result["model_training_target_quantity_basis"]
        == pair.model_training_target_quantity_basis
        == "RECORDED_INBOUND_WEIGHT"
    )
    assert result["checks"]["model_file_contents"] == "NOT_PROVEN_NOT_READ"
    if explicit is None:
        assert (
            result["checks"]["model_target_declaration"]
            == "REAL_FROZEN_S6_FAMILY_CONTRACT_ONLY_NOT_FILE_VERIFIED"
        )
    assert model.model_training_target_quantity_basis == explicit
    assert result["m1_feature_readiness"] == "NOT_PROVEN"


@pytest.mark.parametrize("problem", ["target", "invalid_target", "fit", "binding"])
def test_incompatible_explicit_target_or_fit_or_missing_binding_still_rejected(
    real_format_catalog, monkeypatch, problem
):
    c = real_format_catalog.contexts[0]
    model, source = c.models[0], c.snapshots[0]
    if problem in ("target", "invalid_target"):
        model = model.model_copy(
            update={
                "model_training_target_quantity_basis": "FIELD_HARVEST_WEIGHT"
                if problem == "target"
                else "UNREGISTERED_BASIS"
            }
        )
        with pytest.raises(model_artifacts.ModelArtifactError, match="MODEL_IDENTITY_MISMATCH"):
            model_artifacts.load(model)
    elif problem == "fit":
        source = source.model_copy(
            update={
                "target_binding": source.target_binding.model_copy(update={"fit_sha256": "9" * 64})
            }
        )
    else:
        source = source.model_copy(update={"target_binding": None})
    if problem in ("fit", "binding"):
        pair = model_artifacts.load(model)
        with pytest.raises(ValueError, match="SOURCE_BASIS_UNVERIFIED"):
            inbound.require_target(source, pair)
    catalog = real_format_catalog.model_copy(
        update={"contexts": (c.model_copy(update={"models": (model,), "snapshots": (source,)}),)}
    )
    result = metadata_without_model_or_day_io(catalog, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert "SOURCE_BASIS_UNVERIFIED" in result["blockers"]


def test_synthetic_missing_target_does_not_inherit_real_family_contract(tmp_path, monkeypatch):
    catalog, _ = create_package(tmp_path / "SYNTHETIC-package")
    c = catalog.contexts[0]
    model = c.models[0].model_copy(update={"model_training_target_quantity_basis": None})
    catalog = catalog.model_copy(update={"contexts": (c.model_copy(update={"models": (model,)}),)})
    result = metadata_without_model_or_day_io(catalog, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert result["model_training_target_quantity_basis"] is None
    assert "model_target_declaration" not in result["checks"]


@pytest.mark.parametrize("problem", ["physical_basis", "physical_proof"])
def test_optional_model_target_cannot_substitute_for_source_evidence(
    real_format_catalog, tmp_path, monkeypatch, problem
):
    from backend.research.v019_synthetic_validation import digest

    c = real_format_catalog.contexts[0]
    source = c.snapshots[0]
    raw = json.loads(Path(source.manifest_path).read_bytes())
    if problem == "physical_basis":
        raw["physical_definition"]["measure"] = "NET_WEIGHT"
    else:
        del raw["physical_definition"]["proof_hash"]
    path = tmp_path.resolve() / "SYNTHETIC-alternative-index.json"
    sha = write(path, raw)
    source = source.model_copy(
        update={
            "manifest_path": str(path),
            "manifest_sha256": sha,
            "snapshot_hash": digest(raw),
            "physical_definition_hash": digest(raw["physical_definition"]),
        }
    )
    catalog = real_format_catalog.model_copy(
        update={"contexts": (c.model_copy(update={"snapshots": (source,)}),)}
    )
    result = metadata_without_model_or_day_io(catalog, monkeypatch)
    assert result["status"] == "BLOCKED"
    assert (
        "SOURCE_BASIS_UNVERIFIED" if problem == "physical_basis" else "SOURCE_SCHEMA_INVALID"
    ) in result["blockers"]
