"""SYNTHETIC=true grants; authorization must precede any service access."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from backend.app.forecast_intelligence.read_access import (
    QualityGrant,
    RunGrant,
    ServiceAccount,
    authorize_quality,
    authorize_run,
)
from backend.app.forecast_intelligence.read_schemas import QualityReadQuery, ReadError
from backend.tests.forecast_intelligence.test_v0_17_s1_service_read_api import query


def account(**updates):
    selection = query()
    values = dict(
        principal_id="SYNTHETIC_SERVICE",
        secret=SecretStr("SYNTHETIC_TEST_CREDENTIAL_ONLY"),
        permissions=frozenset({"may_read_forecast", "may_read_quality"}),
        run_grants=(
            RunGrant(
                principal_id="SYNTHETIC_SERVICE",
                forecast_identity=selection.model_dump(exclude={"expected_source_result_hash"}),
                source_result_hash="a" * 64,
            ),
        ),
        quality_grants=(QualityGrant(mode="HISTORICAL_VALIDATION"),),
    )
    return ServiceAccount(**(values | updates))


def test_exact_grant_pins_optional_hash_without_changing_identity():
    pinned = authorize_run(account(), query())
    assert pinned.expected_source_result_hash == "a" * 64
    assert pinned.model_dump(exclude={"expected_source_result_hash"}) == query().model_dump(
        exclude={"expected_source_result_hash"}
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"run_id": 2},
        {"entity_id": "A2"},
        {"target_season": "2026-2027"},
        {"forecast_family": "OTHER"},
        {"policy_version": "OTHER"},
        {"expected_source_result_hash": "b" * 64},
    ],
)
def test_ungranted_selection_never_admitted(updates):
    with pytest.raises(ReadError, match="FORBIDDEN"):
        authorize_run(account(), query(**updates))


def test_capability_permissions_are_independent():
    with pytest.raises(ReadError, match="FORBIDDEN"):
        authorize_run(account(permissions=frozenset({"may_read_quality"})), query())
    with pytest.raises(ReadError, match="FORBIDDEN"):
        authorize_quality(account(permissions=frozenset({"may_read_forecast"})), QualityReadQuery())
    with pytest.raises(ReadError, match="FORBIDDEN"):
        authorize_quality(account(), QualityReadQuery(mode="CURRENT_PRODUCTION_ACCURACY"))


@pytest.mark.parametrize("secret", ["", " "])
def test_empty_credential_is_not_configuration(secret):
    with pytest.raises(ValidationError):
        account(secret=SecretStr(secret))


def test_configuration_cannot_expand_or_cross_principal():
    grant = account().run_grants[0]
    with pytest.raises(ValidationError):
        account(run_grants=(grant.model_copy(update={"principal_id": "OTHER"}),))
    with pytest.raises(ValidationError):
        account(run_grants=(grant, grant))
    with pytest.raises(ValidationError):
        account(permissions=frozenset({"allow_all"}))


def evidence():
    root = Path(__file__).resolve().parents[3]
    raw = (root / "docs/v0-17/evidence/v0.17-s3-mcp-productization-r1.json").read_bytes()
    return root, raw, json.loads(raw)


def test_public_evidence_is_canonical_source_bound_and_private_free():
    root, raw, value = evidence()
    assert raw == (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    assert value["source_evidence_count"] == len(value["source_evidence_sha256"])
    for name, expected in value["source_evidence_sha256"].items():
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    assert all(flag is False for flag in value["isolation"].values())
    assert len(value["eight_tool_mapping"]) == 8
    assert value["governance"]["s3_implementation_authorized"]
    for key in (
        "s3_formal_complete",
        "s4_authorized",
        "ready_authorized",
        "merge_authorized",
        "deploy_authorized",
        "tag_authorized",
        "release_authorized",
    ):
        assert value["governance"][key] is False
    for key in (
        "production_deployed",
        "production_service_account_configured",
        "production_run_grants_verified",
        "production_access_isolation_verified",
    ):
        assert value["known_limitations"][key] is False
    for forbidden in (
        "postgresql://",
        "password=",
        "/private/",
        "/Users/",
        "row_key",
        "SYNTHETIC_TEST_CREDENTIAL_ONLY",
        "SYNTHETIC_OTHER_CREDENTIAL",
    ):
        assert forbidden not in raw.decode()


async def test_legacy_and_new_sdk_registry_contract_hashes():
    from mcp import Client

    from backend.app.mcp.area_forecast import server
    from backend.app.mcp.forecast_intelligence_tools import tools

    _, _, value = evidence()

    def hashes(items):
        return {
            t.name: hashlib.sha256(
                json.dumps(
                    t.model_dump(mode="json", by_alias=True, exclude_none=True),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            for t in items
        }

    async with Client(server) as sdk:
        legacy = (await sdk.list_tools()).tools
    assert hashes(legacy) == value["legacy_mcp_compatibility"]["tool_contract_sha256"]
    assert hashes(tools()) == value["product_tool_contract_sha256"]
