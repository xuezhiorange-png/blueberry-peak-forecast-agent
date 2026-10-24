"""Workbook identity and source equivalence, with no user-row ingestion."""

import hashlib
from types import SimpleNamespace

import pytest

from backend.app.local_auth.sessions import AuthError
from backend.app.rolling_forecast import spreadsheet_demo as demo
from backend.tests.rolling_forecast.spreadsheet_demo_package import create_demo


def bound(selected, kind="xlsx", scenario="complete"):
    asset = selected.assets[kind]
    return demo.Binding(
        scenario=scenario,
        format=kind,
        binding_hash=selected.binding_hash,
        file_sha256=asset.sha256,
        projection_hash=selected.projection_hash,
        sheet=asset.sheet,
        header=asset.header,
        mapping=asset.mapping,
        declared_unit="kg",
        declared_basis="RECORDED_INBOUND_WEIGHT",
    )


def test_repeatable_workbook_projection_and_readiness(tmp_path):
    catalog, _, path = create_demo(tmp_path / "SYNTHETIC-a")
    again, _, other = create_demo(tmp_path / "SYNTHETIC-b")
    manifest = demo.Manifest.model_validate_json(path.read_bytes())
    second = demo.Manifest.model_validate_json(other.read_bytes())
    for scenario, selected in manifest.scenarios.items():
        c = next(c for c in catalog.contexts if c.reference == selected.context)
        for kind in ("xlsx", "csv"):
            assert selected.assets[kind].sha256 == second.scenarios[scenario].assets[kind].sha256
            assert selected.projection_hash == second.scenarios[scenario].projection_hash
            verified = demo.validate_binding(
                selected, c, c.snapshots[0], bound(selected, kind, scenario)
            )
            assert (verified["readiness"]["m1_feature_readiness"] == "COMPUTABLE") == (
                scenario == "complete"
            )
    assert not catalog.capabilities and not again.capabilities


@pytest.mark.parametrize(
    "change",
    [
        dict(file_sha256="a" * 64),
        dict(projection_hash="a" * 64),
        dict(header=0),
        dict(mapping={"weight": 0}),
        dict(binding_hash="b" * 64),
    ],
)
def test_relabel_and_mapping_cannot_authorize_user_file(tmp_path, change):
    catalog, _, path = create_demo(tmp_path / "SYNTHETIC")
    selected = demo.Manifest.model_validate_json(path.read_bytes()).scenarios["complete"]
    with pytest.raises(ValueError, match="UNREGISTERED_PREVIEW_FILE"):
        demo.validate_binding(
            selected,
            catalog.contexts[0],
            catalog.contexts[0].snapshots[0],
            bound(selected).model_copy(update=change),
        )


def test_real_environment_rejected_before_any_object_read(tmp_path, monkeypatch):
    catalog, _, path = create_demo(tmp_path / "SYNTHETIC")
    settings = SimpleNamespace(
        app_env="production",
        pre_data_demo_manifest_path=str(path),
        pre_data_demo_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(demo.inbound, "read", lambda *a: pytest.fail("unauthorized content read"))
    with pytest.raises(AuthError, match="SYNTHETIC_DEMO_UNAVAILABLE"):
        demo.resolve(settings, catalog, None, "complete", "read")
