"""Decision registration and C0 preflight, without private reads or execution."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.research import v019_owner_scope_adapter as adapter
from backend.research import v019_real_phase_a_adapter as r1
from backend.research.v019_daily_curve import canonical_bytes
from backend.tests.area_yield.test_v0_19_retrospective_approval_package import historical

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/v0-19/evidence/v0.19-s3-owner-protocol-decision-c0-preflight-r1.json"
BASE = "9e84439da7ee27b08448804d87413d9a9af24b41"
PR747 = "8f80659f7775f7f0c98552da58d156e6584e800c"
OLD_JSON = "docs/v0-19/evidence/v0.19-s3-retrospective-approval-package-r1.json"
OLD_MD = "docs/v0-19/s3/retrospective-protocol-and-c0-approval-r1.md"
PENDING = {
    "FORMAL_C0",
    "A_INPUT_READ",
    "A_EXECUTION",
    "A_SEAL_REVIEW",
    "B_LABEL_READ",
    "B_SCORING",
    "INDEPENDENT_REVIEWED_RESEARCH_IMPLEMENTATION",
}
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def load() -> dict[str, Any]:
    value: dict[str, Any] = json.loads(EVIDENCE.read_bytes())
    return value


def check(c: dict[str, Any]) -> None:
    old = json.loads(historical(OLD_JSON, PR747, c["predecessor"]["json_sha256"]))
    assert c["task_id"] == "V0_19_S3_OWNER_PROTOCOL_APPROVAL_AND_C0_PREFLIGHT_R1"
    assert c["base_main_sha"] == BASE
    assert c["version"] == "V0_19_S3_OWNER_PROTOCOL_DECISION_R1"
    assert c["predecessor"]["pr"] == 747
    assert c["predecessor"]["head_sha"] == PR747
    assert c["predecessor"]["merge_sha"] == BASE
    assert c["predecessor"]["json_sha256"] == (
        "7d65a7d6787a67c9583fb8c383e996acb47bb289737ae0423a25d7a252027ece"
    )
    assert c["predecessor"]["markdown_sha256"] == (
        "918624c6f443404a96b96c7eeaf17515e29b7f5d9a7538c3fc4a0cbf8a3c0158"
    )
    historical(OLD_MD, PR747, c["predecessor"]["markdown_sha256"])
    for path, field in ((OLD_MD, "markdown_git_blob"), (OLD_JSON, "json_git_blob")):
        blob = subprocess.run(
            ["git", "rev-parse", f"{PR747}:{path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert c["predecessor"][field] == blob
        assert (ROOT / path).read_bytes() == historical(path, PR747)
    assert all(d["status"] == "NOT_APPROVED" for d in old["decisions"].values())
    assert c["protocol_owner_decision"] == "APPROVED_LIMITED"
    assert c["decisions"]["PROTOCOL"] == {
        "status": "OWNER_APPROVED_LIMITED",
        "owner_approved": True,
        "does_not_grant_c0_or_execution": True,
    }
    assert set(c["decisions"]) == PENDING | {"PROTOCOL"}
    for key in PENDING:
        assert c["decisions"][key] == {"status": "NOT_APPROVED", "owner_approved": False}
    assert c["scope"] == old["scope"]
    assert c["scope_section_sha256"] == hashlib.sha256(canonical_bytes(old["scope"])).hexdigest()
    assert c["scope_section_hash_kind"] == (
        "CANONICAL_PREDECESSOR_SCOPE_SECTION_NOT_NEW_PRIVATE_AUTHORITY"
    )
    assert c["input_identities"] == old["input_identities"]
    assert c["algorithm"] == old["algorithm"]
    assert c["identity"]["experiment_type"] == "RETROSPECTIVE_REPLAY"
    assert c["identity"]["historical_status"] == "EXPOSED_HISTORICAL_BENCHMARK"
    assert c["identity"]["strict_pit"] is False
    assert c["identity"]["production_eligible"] is False
    assert c["identity"]["status"] == "OWNER_APPROVED_LIMITED_NOT_EFFECTIVE"
    assert c["identity"]["comparison_family"] == old["identity"]["comparison_family"]
    assert c["accepted_limitations"] == {
        "physical_basis_equivalence": "NOT_PROVEN",
        "historical_area_known_at": "NOT_PROVEN",
        "historical_issuance_evidence": "NOT_PROVEN",
        "does_not_prove_production_accuracy": True,
        "training_tuning_promotion_forbidden": True,
    }
    assert c["states"] == old["states"]
    assert all(type(v) is bool and v is False for v in c["states"].values())
    assert c["c0"]["status"] == "C0_CANDIDATE_ONLY"
    assert c["c0"]["formally_admitted_count"] == 0
    assert c["c0"]["formal_seal_sha256"] is None
    assert c["c0"]["candidate_windows"] == old["c0"]["windows"]
    assert c["c0"]["candidate_columns"] == old["c0"]["candidate_columns"]
    assert c["c0"]["failure_inventory"]["status"] == "PENDING_EXACT_MEMBER_REVIEW_NOT_ZERO_FAILURES"
    assert c["c0"]["failure_inventory"]["actual_failure_count"] is None
    assert c["c0"]["failure_inventory"]["sha256"] is None
    assert c["c0"]["review_rows_sha256"] is None
    assert c["c0"]["private_objects_reopened_this_task"] is False
    assert c["c0"]["roster_location"] == "EXISTING_CONTROLLED_MANIFEST_EXPLICIT_PATH_NO_DISCOVERY"
    assert c["c0"]["support_status"] == "PROPOSED_FOR_C0_REVIEW"
    checks = c["c0"]["review_checklist"]
    assert set(checks) == {
        "EXACT_MEMBERS_REGISTRY",
        "CALENDAR_ZERO_AREA_SOURCE",
        "H7_MEMBERS_AND_FAILURES",
        "H15_MEMBERS_AND_FAILURES",
        "ORIGIN_CUTOFF_SEMANTICS",
        "C0_SEAL_AND_APPROVAL_BOUNDARY",
    }
    assert all(
        x["status"] == "PENDING_OWNER_C0_REVIEW" and x["required_evidence"] for x in checks.values()
    )
    provenance = c["approval_provenance"]
    assert provenance["source_kind"] == "OWNER_REPLY_CONFIRMED_BY_CURRENT_OWNER_CORRECTION"
    assert provenance["source_task_id"] == c["task_id"]
    assert provenance["original_approved_at"] is None
    assert provenance["github_authorization_url"] is None
    assert provenance["external_signature"] is None
    assert provenance["chat_message_id"] is None
    assert provenance["timestamp_evidence"] == "RECORDING_CLOCK_ONLY_ORIGINAL_DECISION_TIME_UNKNOWN"
    assert provenance["captured_excerpt"] == "可以"
    assert (
        provenance["structured_scope_author"] == "ASSISTANT_INTERPRETATION_NOT_VERBATIM_OWNER_REPLY"
    )
    assert (
        provenance["excerpt_hash_semantics"]
        == "OWNER_REPLY_BYTES_ONLY_NOT_REQUEST_CONTEXT_OR_SIGNATURE"
    )
    assert provenance["provenance_correction"]["supersedes_commit"] == (
        "e6969a42282d979d8a23951db5ebe4f944b86349"
    )
    assert (
        provenance["captured_excerpt_sha256"]
        == hashlib.sha256(provenance["captured_excerpt"].encode("utf-8")).hexdigest()
    )
    recorded = datetime.fromisoformat(c["recorded_at"].replace("Z", "+00:00"))
    assert recorded.utcoffset() == timedelta(0) and c["recorded_at"].endswith("Z")
    assert c["recorded_at_source"] == "CLOCK_CURR_TIME_AT_RECORD_CONSTRUCTION"
    assert c["recorded_at_is_owner_approval_time"] is False
    time = c["research_time_proposal"]
    assert time["status"] == "PROPOSED_NOT_APPROVED_FOR_FORMAL_C0"
    assert time["timezone"] == "Asia/Shanghai"
    assert time["origin_at_rule"] == "ORIGIN_LOCAL_DATE_T23:59:59+08:00"
    assert time["cutoff_rule"] == "SAME_AS_RESEARCH_ORIGIN_AT_NO_HISTORICAL_AVAILABILITY_CLAIM"
    assert time["historical_issued_at"] is None
    assert time["actual_executed_at_rule"] == "ACTUAL_UTC_TIME_NEVER_ORIGIN_BACKDATE"
    assert c["seal_proposal"]["formal_seal_generated"] is False
    assert c["seal_proposal"]["approval_reference_order"] == [
        "CANDIDATE_REVIEW_BODY_HASH",
        "OWNER_FORMAL_C0_DECISION_REFERENCES_BODY_HASH",
        "NEW_FORMAL_C0_SEAL_REFERENCES_BOTH_NO_CIRCULAR_SELF_HASH",
    ]
    assert (
        c["seal_proposal"]["membership_selection"]
        == "IDENTITY_CALENDAR_AUTHORIZED_COMPLETENESS_NOT_WEIGHTS_OR_ERRORS"
    )
    assert c["execution_boundary"] == {
        "phase_a": "UNCONDITIONAL_REFUSAL_UNCHANGED",
        "phase_b": "REAL_SCORING_NOT_AUTHORIZED",
        "strict_scorer": "UNCHANGED_REFUSE_LATE_ISSUANCE",
        "activation_review": "PENDING_SEPARATE_REVIEW_NO_FLAGS_ENABLE_EXECUTION",
    }
    assert c["execution_this_task"] and all(
        type(v) is bool and v is False for v in c["execution_this_task"].values()
    )
    assert set(c["new_document_sha256"]) == {
        "docs/v0-19/s3/owner-protocol-decision-r1.md",
        "docs/v0-19/s3/owner-c0-admission-preflight-r1.md",
    }
    assert c["historical_sources_sha256"] == old["historical_sources_sha256"]
    for path, sha in c["new_document_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha
    for path, sha in c["historical_sources_sha256"].items():
        historical(path, BASE, sha)


def test_versioned_owner_decision_and_c0_preflight() -> None:
    check(load())


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("protocol_owner_decision", "", "NOT_APPROVED"),
        ("states", "retrospective_protocol_effective", True),
        ("states", "real_prediction_authorized", True),
        ("states", "real_scoring_authorized", True),
        ("states", "s3_formal_complete", True),
        ("c0", "formally_admitted_count", 19032),
        ("c0", "status", "APPROVED"),
        ("c0", "formal_seal_sha256", "a" * 64),
        ("c0", "private_objects_reopened_this_task", True),
        ("identity", "strict_pit", True),
        ("identity", "historical_status", "BLIND_OOT"),
        ("scope", "included_farms", 75),
        ("scope", "unresolved", 9),
        ("algorithm", "fold", "A"),
        ("algorithm", "tuning", True),
        ("algorithm", "query", "RENORMALIZE_WINDOW"),
        ("input_identities", "h7-candidates.csv", "0" * 64),
        ("input_identities", "h15-candidates.csv", "0" * 64),
        ("approval_provenance", "original_approved_at", "2026-10-21T14:42:00Z"),
        ("approval_provenance", "github_authorization_url", "https://github.com/fake"),
        ("approval_provenance", "external_signature", "fabricated"),
        ("research_time_proposal", "historical_issued_at", "2025-08-04T23:59:59+08:00"),
        ("execution_boundary", "phase_a", "ENABLED"),
        ("recorded_at_is_owner_approval_time", "", True),
        ("research_time_proposal", "status", "APPROVED"),
        ("seal_proposal", "formal_seal_generated", True),
        ("execution_this_task", "real_scoring_performed", True),
    ],
)
def test_no_implicit_permissions_or_invented_provenance(
    section: str,
    key: str,
    value: object,
) -> None:
    c = copy.deepcopy(load())
    if key:
        c[section][key] = value
    else:
        c[section] = value
    with pytest.raises(AssertionError):
        check(c)


@pytest.mark.parametrize("decision", sorted(PENDING))
def test_each_other_decision_remains_unapproved(decision: str) -> None:
    c = load()
    c["decisions"][decision] = {"status": "APPROVED", "owner_approved": True}
    with pytest.raises(AssertionError):
        check(c)


def test_unknown_failure_inventory_is_not_zero() -> None:
    c = load()
    c["c0"]["failure_inventory"]["actual_failure_count"] = 0
    with pytest.raises(AssertionError):
        check(c)


@pytest.mark.parametrize("fake", ["Owner 已明确同意受限协议", "PROTOCOL=OWNER_APPROVED_LIMITED"])
def test_assistant_scope_cannot_be_labeled_as_verbatim_owner_reply(fake: str) -> None:
    c = load()
    c["approval_provenance"]["captured_excerpt"] = fake
    c["approval_provenance"]["captured_excerpt_sha256"] = hashlib.sha256(fake.encode()).hexdigest()
    with pytest.raises(AssertionError):
        check(c)


@pytest.mark.parametrize("horizon,last,count", [(7, "2026-04-08", 9672), (15, "2026-03-31", 9360)])
def test_proposed_time_is_before_target_not_proof_of_historical_issuance(
    horizon: int,
    last: str,
    count: int,
) -> None:
    first = date(2025, 8, 4)
    end = date.fromisoformat(last)
    assert ((end - first).days + 1) * 39 == count
    for origin in (first, end):
        cutoff = datetime.fromisoformat(f"{origin}T23:59:59+08:00")
        target_start = datetime.fromisoformat(f"{origin + timedelta(days=1)}T00:00:00+08:00")
        assert cutoff < target_start
        assert origin + timedelta(days=horizon) <= date(2026, 4, 15)
    assert load()["research_time_proposal"]["historical_issued_at"] is None


def test_synthetic_review_body_hash_is_order_independent_and_not_formal_seal() -> None:
    rows = [
        {"candidate_id": "SYNTHETIC-B", "disposition": "PENDING_REVIEW"},
        {"candidate_id": "SYNTHETIC-A", "disposition": "MISSING_AUTHORITY"},
    ]

    def digest(items: list[dict[str, str]]) -> str:
        assert len({r["candidate_id"] for r in items}) == len(items)
        return hashlib.sha256(
            canonical_bytes(sorted(items, key=lambda r: r["candidate_id"]))
        ).hexdigest()

    assert digest(rows) == digest(list(reversed(rows)))
    with pytest.raises(AssertionError):
        digest(rows + rows[:1])
    assert digest(rows) != digest(rows[:1])  # Failures cannot disappear without changing seal.
    assert load()["c0"]["formal_seal_sha256"] is None


@pytest.mark.parametrize("forged", [False, True])
def test_protocol_document_cannot_enable_real_generation_or_touch_inputs(
    forged: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval = load()
    if forged:
        approval["decisions"] = {k: {"owner_approved": True} for k in approval["decisions"]}
        approval["states"]["real_prediction_authorized"] = True

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("INPUT_LABEL_OR_PREDICTION_TOUCHED")

    monkeypatch.setattr(r1, "_read_pinned", forbidden)
    monkeypatch.setattr(r1, "generate_candidate", forbidden)
    monkeypatch.setattr(r1, "rehearse_synthetic", forbidden)
    with pytest.raises(PermissionError, match="REAL_PHASE_A_EXECUTION_DISABLED"):
        adapter.generate_real_predictions(approval, owner_authorized=True)
