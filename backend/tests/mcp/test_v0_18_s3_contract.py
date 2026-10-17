"""S3 evidence integrity; not a replacement for current SDK/PostgreSQL tests."""

import hashlib
import json
from pathlib import Path

from backend.app.mcp.forecast_intelligence_tools import tools
from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/v0-18/evidence/s3-mcp-service-account-safety-r1.json"


def test_canonical_s3_evidence_and_source_hashes():
    raw = EVIDENCE.read_bytes()
    data = json.loads(raw)
    assert raw == (json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    assert data["base_main_sha"] == "3410dd4426618a7a4b29c08cbf58aaef20196939"
    assert data["task_id"] == "V0_18_S3_MCP_SERVICE_ACCOUNT_SAFETY_R1"
    assert data["source_evidence_count"] == len(data["source_evidence_sha256"])
    for field in (
        "source_evidence_sha256",
        "frozen_sources_sha256",
        "unchanged_business_sources_sha256",
    ):
        for relative, digest in data[field].items():
            path = Path(relative)
            assert not path.is_absolute() and ".." not in path.parts
            revised = {
                "backend/tests/business_access/test_contract.py",
                "backend/tests/historical_source.py",
                "backend/tests/local_auth/test_runtime_evidence_contract.py",
                "backend/tests/mcp/test_v0_18_s3_contract.py",
            }
            revised_authorization = (
                field == "unchanged_business_sources_sha256"
                and relative == "backend/app/local_auth/authorization.py"
            )
            source = (
                historical_bytes(relative, data["base_main_sha"])
                if revised_authorization
                else (
                    historical_bytes(relative, "08b185b4621bf517846c986841bb5579b6c37b35")
                    if relative in revised
                    else (ROOT / path).read_bytes()
                )
            )
            assert hashlib.sha256(source).hexdigest() == digest
            if field != "source_evidence_sha256":
                current_or_approved_history = (
                    source if revised_authorization else (ROOT / path).read_bytes()
                )
                assert current_or_approved_history == historical_bytes(
                    relative, data["base_main_sha"]
                )
    for relative, binding in data["historical_source_adaptation"].items():
        assert (
            hashlib.sha256(historical_bytes(relative, binding["commit"])).hexdigest()
            == binding["sha256"]
        )
    original = json.loads((ROOT / "docs/v0-18/s1/local-auth-runtime-r1.json").read_bytes())
    assert len(original["frozen_history_sha256"]) == 260
    for relative, digest in original["frozen_history_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_eight_tool_contracts_and_security_scope_are_not_overstated():
    data = json.loads(EVIDENCE.read_bytes())
    original = json.loads(
        (ROOT / "docs/v0-17/evidence/v0.17-s3-mcp-productization-r1.json").read_bytes()
    )
    actual = {
        tool.name: hashlib.sha256(
            json.dumps(
                tool.model_dump(mode="json", by_alias=True, exclude_none=True),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        for tool in tools()
    }
    assert actual == original["product_tool_contract_sha256"] == data["tool_contract_sha256"]
    assert len(actual) == 8
    assert data["tool_order"] == [t.name for t in tools()]
    runtime = data["runtime"]
    assert runtime["mode"] == "SERVICE_ACCOUNT_ONLY"
    assert runtime["operational_factory"] == "create_service_account_app"
    assert runtime["end_user_delegation"] is False
    assert runtime["exact_run_grants"] and runtime["independent_quality_grants"]
    assert runtime["pre_response_policy_recheck"] and runtime["lock_through_actual_asgi_send"]
    assert runtime["static_environment_fallback"] is False
    assert runtime["policy_revision_scope"] == "ENTIRE_DOCUMENT_CONSERVATIVE_INVALIDATION"
    assert data["limitations"]["cross_host_revocation_validated"] is False
    assert data["limitations"]["immutable_composition_revocation_guaranteed"] is False
    assert data["service_account_safety_acceptance"] == "PASS_ISOLATED_POSIX_LOCAL_FILESYSTEM_SCOPE"
    assert all(value is False for value in data["governance"].values())
    assert data["production_readiness"] == "NOT_READY"
    assert data["ci"]["result"] == "PENDING_AT_COMMIT_EXACT_HEAD_RECEIPT_REQUIRED"
