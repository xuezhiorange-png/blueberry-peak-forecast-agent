"""Operator policy is explicit, scoped, expiring and fail-closed."""

import json
from datetime import UTC, datetime

import pytest

from backend.app.local_auth.sessions import AuthError, Principal
from backend.app.rolling_forecast.policy import Catalog, load_catalog
from backend.tests.rolling_forecast.test_engine import inputs
from backend.tests.rolling_forecast.test_model_artifacts import reference


def catalog(tmp_path):
    calendar, area, _, _, _ = inputs()
    model, _ = reference(tmp_path)
    return Catalog.model_validate(
        {
            "schema_version": "ROLLING_SHADOW_CATALOG_V1",
            "revision": "SYNTHETIC",
            "contexts": [
                {
                    "reference": "C",
                    "organization_id": "ORG",
                    "area": area,
                    "calendar": calendar,
                    "models": [model],
                    "modes": ["RESEARCH_SHADOW"],
                    "snapshots": [
                        {
                            "reference": "S",
                            "snapshot_id": 1,
                            "snapshot_hash": "b" * 64,
                            "source_system": "synthetic",
                            "provenance": "SYNTHETIC_TEST_FIXTURE",
                            "members": [
                                {
                                    "season_business_key": "S",
                                    "farm_business_key": "F",
                                    "subfarm_business_key": "P",
                                    "variety_business_key": "V",
                                }
                            ],
                            "membership_authority_hash": "a" * 64,
                            "mapping_registry_hash": "b" * 64,
                            "completeness_authority_hash": "c" * 64,
                            "completeness_known_at": "2026-01-01T00:00:00Z",
                            "complete_dates": [],
                        }
                    ],
                }
            ],
            "capabilities": [
                {
                    "principal_id": "A",
                    "auth_revision": 1,
                    "grant_revision": 1,
                    "contexts": ["C"],
                    "operations": ["issue", "read"],
                    "valid_from": "2020-01-01T00:00:00Z",
                    "valid_until": "2035-01-01T00:00:00Z",
                }
            ],
        }
    )


def subject(**changes):
    return Principal(
        **{
            "account_id": "A",
            "principal_id": "A",
            "session_id": "S",
            "role": "BUSINESS_USER",
            "must_change_password": False,
            "auth_revision": 1,
            "grant_revision": 1,
            **changes,
        }
    )


def test_explicit_scope_no_admin_inheritance_and_revision_binding(tmp_path):
    value = catalog(tmp_path)
    assert len(value.allowed(subject(), "read")) == 1
    assert value.allowed(subject(principal_id="B", role="ADMIN"), "read") == []
    assert value.allowed(subject(grant_revision=2), "read") == []
    assert value.allowed(subject(auth_revision=2), "read") == []
    assert value.allowed(subject(), "compare") == []
    cap = value.capabilities[0].model_copy(update={"valid_until": datetime(2021, 1, 1, tzinfo=UTC)})
    assert value.model_copy(update={"capabilities": (cap,)}).allowed(subject(), "read") == []


def test_current_real_data_and_ambiguous_members_fail_before_source_read(tmp_path):
    value = catalog(tmp_path).model_dump(mode="json")
    value["contexts"][0]["snapshots"][0]["provenance"] = "AUTHORIZED_HISTORICAL"
    with pytest.raises(ValueError, match="CURRENT_SEASON_REAL_READ_NOT_AUTHORIZED"):
        Catalog.model_validate(value)
    value = catalog(tmp_path).model_dump(mode="json")
    duplicate = json.loads(json.dumps(value["contexts"][0]))
    duplicate["reference"] = "OTHER"
    duplicate["area"]["base_id"] = "OTHER_BASE"
    value["contexts"].append(duplicate)
    with pytest.raises(ValueError, match="AMBIGUOUS_BASE_MEMBERSHIP"):
        Catalog.model_validate(value)


def test_private_catalog_reload_organization_and_file_safety(tmp_path):
    value = catalog(tmp_path)
    path = tmp_path.resolve() / "policy.json"
    path.write_text(value.model_dump_json())
    path.chmod(0o600)
    assert load_catalog(str(path), ["ORG"]) == value
    path.write_text(value.model_copy(update={"revision": "REVOKED"}).model_dump_json())
    assert load_catalog(str(path), ["ORG"]).fingerprint != value.fingerprint
    with pytest.raises(AuthError):
        load_catalog(str(path), ["OTHER_ORG"])
    path.chmod(0o666)
    with pytest.raises(AuthError):
        load_catalog(str(path), ["ORG"])
    with pytest.raises(AuthError):
        load_catalog("relative.json", ["ORG"])
