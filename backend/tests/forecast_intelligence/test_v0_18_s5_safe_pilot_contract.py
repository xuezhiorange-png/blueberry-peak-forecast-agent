"""Offline evidence integrity is distinct from current runtime/pilot acceptance."""

import hashlib
import json
from pathlib import Path

import pytest

from backend.tests.safe_pilot.evidence import ARCHIVE, EVIDENCE, R1_CHECKPOINT, ROOT, generate

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_s5_canonical_sources_history_and_actual_artifact_bindings():
    raw = EVIDENCE.read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    index = json.loads((ARCHIVE / "artifact-index.json").read_text())
    # Original R1 source integrity is not current cancellation-fix acceptance.
    # Only the three explicitly evolving test sources use the reviewed R1 blob;
    # all frozen documents, artifacts and other runtime sources stay byte-bound.
    assert value == generate(index, source_checkpoint=R1_CHECKPOINT)
    assert len(value["frozen_history_sha256"]) == 260
    assert value["local_backend"]["passed"] >= 16
    assert value["local_backend"]["failed"] == value["local_backend"]["skipped"] == 0
    assert value["browser"]["expected_case_count"] == 26
    assert value["browser"]["screenshots"] == 66
    origins = set()
    for relative, entry in value["artifacts"].items():
        path = Path(relative)
        assert not path.is_absolute() and ".." not in path.parts
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == entry["sha256"]
        origin = (entry["source_run"], entry["source_path"])
        assert origin not in origins
        origins.add(origin)


def test_s5_scope_and_future_authorization_are_not_conflated():
    value = json.loads(EVIDENCE.read_text())
    assert value["synthetic"] is True
    assert not any(value["governance"].values())
    assert value["limitations"]["production_readiness"] == "NOT_READY"
    assert value["limitations"]["mcp_topology"] == "SAME_HOST_POSIX_LOCAL_FILESYSTEM"
    for key in (
        "cross_host_revocation",
        "production_network_isolation",
        "real_ios_safari",
        "soft_keyboard",
        "screen_reader",
        "nfs",
        "windows",
    ):
        assert value["limitations"][key] == "NOT_VALIDATED"
    for key in (
        "real_accounts_or_grants_created",
        "current_actual_access",
        "new_forecast_or_model_experiment",
        "production_database_changed",
        "rollback_binary_downgrade_tested",
    ):
        assert value["limitations"][key] is False
    assert value["backup"]["post_restore_revoke_all_sessions_and_grants_before_listener"]
    assert value["backup"]["current_catalog_admin_explicit_reapproval_required"]
    assert value["dependency_audit"]["result"] == "COMPLETED_WITH_OPEN_ADVISORIES"
    assert value["dependency_audit"]["dependencies_changed"] is False
    assert value["ci"]["result"] == "PENDING_AT_COMMIT_EXACT_HEAD_RECEIPT_REQUIRED"


def test_s5_template_and_runbook_do_not_offer_production_auth_bypasses():
    template = (ROOT / "docs/v0-18/s5/SYNTHETIC.env.example").read_text()
    for name in (
        "LOCAL_AUTH_ORIGIN",
        "LOCAL_AUTH_LOGIN_BUCKET_SECRET",
        "LOCAL_AUTH_ORGANIZATION_IDS_JSON",
        "LOCAL_AUTH_SIMPLE_ADMIN_CATALOG_JSON",
        "LOCAL_AUTH_PUBLISHER_BOUNDARIES_JSON",
        "BUSINESS_ACCESS_SIGNING_KEY",
        "FORECAST_INTELLIGENCE_MCP_POLICY_FILE",
    ):
        assert name + "=" in template
    assert "<RANDOM_PRIVATE_TEST_ONLY_SECRET>" in template
    runbook = (ROOT / "docs/v0-18/s5/safe-pilot-runbook-r1.md").read_text()
    assert "PRODUCTION_READINESS=NOT_READY" in runbook
    assert "PENDING_OWNER_DECISION" in runbook
    assert "S6_AUTHORIZED=false" in runbook
    assert "--no-proxy-headers" in runbook
