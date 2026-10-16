"""Offline negative controls for original approvals and evidence-derived gates."""

import copy
import json
from pathlib import Path

import pytest

from backend.tests.forecast_intelligence import build_v0_18_approval_provenance_r2 as builder
from backend.tests.forecast_intelligence.build_v0_18_approval_provenance_r2 import (
    ACTIONS,
    BASE,
    EVIDENCE,
    JUNIT,
    R1_FILES,
    R2_DOC,
    R2_EVIDENCE,
    R2_FILES,
    SOURCES,
    START,
    VALIDATORS,
    assess,
    bound,
    canonical,
    digest,
    generate,
    git_blob,
    github_sources,
    load,
    make_record,
    original_r1,
    validate_gate,
)

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def synthetic_approval(action="INDEPENDENT_REVIEW"):
    """SYNTHETIC unit input; never included in recovered historical records."""
    source = {
        "SYNTHETIC": True,
        "channel": "OTHER_AUTHENTIC_ORIGINAL_RECORD",
        "record_id": "SYNTHETIC_MESSAGE_1",
        "locator": "SYNTHETIC_OFFLINE_TEST_ONLY",
        "provider_authenticated": True,
        "forwarded_or_summary": False,
        "pr_number": 999,
        "head_sha": "a" * 40,
        "timestamp": "2026-01-01T00:00:00Z",
        "actor": "SYNTHETIC_REVIEWER" if action == "INDEPENDENT_REVIEW" else "SYNTHETIC_OWNER",
        "actor_role": "INDEPENDENT_REVIEWER" if action == "INDEPENDENT_REVIEW" else "OWNER",
        "scope": [action],
        "decision": "PASS",
        "context_verified": True,
        "context_precedes_action": True,
        "independent_from_implementer": True,
        "self_receipt": False,
        "withdrawn": False,
    }
    public = {
        "number": 999,
        "head_sha": "a" * 40,
        "merged_at": "2026-01-01T02:00:00Z",
        "timeline": [
            {"event": "ready_for_review", "created_at": "2026-01-01T01:00:00Z"},
            {"event": "merged", "created_at": "2026-01-01T02:00:00Z"},
        ],
    }
    return source, public


@pytest.mark.parametrize("action", ACTIONS)
def test_explicit_original_scope_with_prior_head_binding_can_verify(action):
    source, public = synthetic_approval(action)
    record = make_record(source, action, "2026-01-02T00:00:00Z")
    assert assess(record, source, public)["evidence_status"] == "VERIFIED"


@pytest.mark.parametrize(
    "change",
    [
        {"head_sha": "b" * 40},
        {"timestamp": "2026-01-01T03:00:00Z"},
        {"withdrawn": True},
        {"independent_from_implementer": False},
        {"self_receipt": True, "actor": "Codex implementer"},
        {"scope": ["IMPLEMENTATION"]},
        {"decision": "BLOCKED"},
        {"context_verified": False},
        {"context_precedes_action": False},
        {"forwarded_or_summary": True},
        {"provider_authenticated": False},
        {"actor_role": "IMPLEMENTER"},
    ],
)
def test_invalid_review_cannot_become_verified(change):
    source, public = synthetic_approval()
    source.update(change)
    record = make_record(source, "INDEPENDENT_REVIEW", "2026-01-02T00:00:00Z")
    assert assess(record, source, public)["evidence_status"] != "VERIFIED"


@pytest.mark.parametrize("scope", [["IMPLEMENTATION"], ["OWNER_READY"], [], ["MERGED_FACT"]])
def test_ready_only_implementation_or_merge_fact_does_not_authorize_merge(scope):
    source, public = synthetic_approval("OWNER_MERGE")
    source["scope"] = scope
    record = make_record(source, "OWNER_MERGE", "2026-01-02T00:00:00Z")
    assert assess(record, source, public)["evidence_status"] != "VERIFIED"


def test_ambiguous_yes_missing_context_and_missing_ready_event_fail_closed():
    source, public = synthetic_approval("OWNER_MERGE")
    source.update(public_excerpt="可以", context_verified=False)
    record = make_record(source, "OWNER_MERGE", "2026-01-02T00:00:00Z")
    assert assess(record, source, public)["evidence_status"] == "PARTIAL_EVIDENCE"
    source, public = synthetic_approval("OWNER_READY")
    public["timeline"] = []
    record = make_record(source, "OWNER_READY", "2026-01-02T00:00:00Z")
    assert assess(record, source, public)["temporal_order_verified"] is False
    assert assess(record, source, public)["evidence_status"] != "VERIFIED"


def test_approval_after_ready_or_merge_is_not_prior_authorization():
    source, public = synthetic_approval("OWNER_READY")
    source["timestamp"] = "2026-01-01T01:30:00Z"
    record = make_record(source, "OWNER_READY", "2026-01-02T00:00:00Z")
    assert assess(record, source, public)["evidence_status"] != "VERIFIED"
    source["timestamp"] = "2026-01-01T03:00:00Z"
    record = make_record(source, "OWNER_READY", "2026-01-02T00:00:00Z")
    assert assess(record, source, public)["evidence_status"] == "POST_HOC_ATTESTATION"


def test_hash_mismatch_missing_original_source_and_actor_spoof_fail():
    source, public = synthetic_approval()
    record = make_record(source, "INDEPENDENT_REVIEW", "2026-01-02T00:00:00Z")
    record["source_integrity_hash"] = "0" * 64
    assert assess(record, source, public)["evidence_status"] == "PENDING_SOURCE_VERIFICATION"
    assert assess(record, None, public)["evidence_status"] == "PENDING_SOURCE_VERIFICATION"
    record = make_record(source, "INDEPENDENT_REVIEW", "2026-01-02T00:00:00Z")
    record["actor"] = "SYNTHETIC_FORGED_ACTOR"
    assert assess(record, source, public)["evidence_status"] != "VERIFIED"


def test_unresolved_changes_request_cannot_hide_behind_earlier_pass():
    capture = load(ROOT, SOURCES)
    public = copy.deepcopy(capture["github"]["pull_requests"][0])
    public["timeline"] = capture["github"]["approval_timelines"]["710"]
    public["reviews"].append(public["reviews"][0] | {"id": 999, "state": "CHANGES_REQUESTED"})
    for source in github_sources(public):
        record = make_record(source, "INDEPENDENT_REVIEW", capture["captured_at_utc"])
        assert assess(record, source, public)["evidence_status"] != "VERIFIED"


def test_owner_authorization_withdrawal_and_self_receipt_never_verify():
    source, public = synthetic_approval("OWNER_MERGE")
    for change in ({"withdrawn": True}, {"self_receipt": True}):
        altered = source | change
        record = make_record(altered, "OWNER_MERGE", "2026-01-02T00:00:00Z")
        assert assess(record, altered, public)["evidence_status"] != "VERIFIED"


def test_source_hash_does_not_replace_action_scope_actor_or_head_checks():
    source, public = synthetic_approval("OWNER_MERGE")
    record = make_record(source, "OWNER_MERGE", "2026-01-02T00:00:00Z")
    record.update(evidence_status="VERIFIED", head_binding_verified=True)
    source["head_sha"] = "f" * 40
    record["source_integrity_hash"] = digest(canonical(source))
    assert assess(record, source, public)["evidence_status"] != "VERIFIED"


def test_real_original_chat_message_does_not_infer_missing_prior_review_context():
    evidence = load(ROOT, R2_EVIDENCE)
    originals = [
        r
        for r in evidence["approval_records"]
        if r["source_type"] == "ORIGINAL_CHATGPT_CONVERSATION"
    ]
    owner = [r for r in originals if r["action_type"] in {"OWNER_READY", "OWNER_MERGE"}]
    assert len(owner) == 2
    assert all(r["original_source_verified"] for r in owner)
    assert all(r["temporal_order_verified"] for r in owner)
    assert all(not r["head_binding_verified"] for r in owner)
    assert all(r["evidence_status"] == "PARTIAL_EVIDENCE" for r in owner)
    summary = next(r for r in originals if r["action_type"] == "INDEPENDENT_REVIEW")
    assert summary["evidence_status"] == "PENDING_SOURCE_VERIFICATION"
    assert evidence["recovered_record_counts"] == {
        "INDEPENDENT_REVIEW": 4,
        "OWNER_READY": 0,
        "OWNER_MERGE": 0,
    }


def test_all_required_record_fields_and_fresh_15_pr_scope():
    evidence = load(ROOT, R2_EVIDENCE)
    required = {
        "evidence_id",
        "source_type",
        "source_locator",
        "source_record_id",
        "source_integrity_hash",
        "original_timestamp",
        "captured_timestamp",
        "actor",
        "actor_role",
        "pr_number",
        "reviewed_head_sha",
        "action_type",
        "decision",
        "authorization_scope",
        "independent_from_implementer",
        "original_source_verified",
        "head_binding_verified",
        "temporal_order_verified",
        "evidence_status",
    }
    assert evidence["historical_pr_count"] == len(evidence["approval_audit"]) == 15
    assert all(required <= set(r) for r in evidence["approval_records"])
    assert len({r["evidence_id"] for r in evidence["approval_records"]}) == len(
        evidence["approval_records"]
    )
    assert evidence["approval_audit"][1]["classification"] == "S1_PREFLIGHT_NOT_RUNTIME"
    assert (
        evidence["approval_audit"][3]["classification"]
        == "SEPARATE_PEAK_BUSINESS_CONTRACT_NOT_V018_IMPLEMENTATION"
    )


def test_r1_snapshot_and_all_history_remain_original_bytes():
    evidence = original_r1(ROOT)
    assert evidence["gate_counts"] == {"PASS": 6, "BLOCKED": 7, "PENDING": 3, "FAIL": 0}
    for path in R1_FILES:
        assert (ROOT / path).read_bytes() == git_blob(ROOT, START, path)
    assert validate_gate("G10", ROOT, evidence)["status"] == "PASS"


@pytest.mark.parametrize("gate", VALIDATORS)
def test_g08_g13_have_real_positive_evidence(gate):
    assert validate_gate(gate, ROOT, load(ROOT, EVIDENCE))["status"] == "PASS"


@pytest.mark.parametrize("gate", VALIDATORS)
def test_g08_g13_missing_proof_cannot_pass(gate):
    r1 = load(ROOT, EVIDENCE)
    if gate in {"G08", "G09", "G11", "G13"}:
        r1["frozen_s6_acceptance"]["sha256"] = "0" * 64
    elif gate == "G10":
        r1["historical_git_sha256"] = {}
    else:
        del r1["delivery_scope_audit"]["not_a_forensic_claim_about_unobservable_external_systems"]
    assert validate_gate(gate, ROOT, r1)["status"] == "BLOCKED"


@pytest.mark.parametrize("gate", ["G11", "G12", "G13"])
def test_semantics_execution_boundary_and_risk_mutations_block(gate):
    r1 = load(ROOT, EVIDENCE)
    if gate == "G11":
        r1["semantic_boundaries"]["historical_m1_is_operational_peak_accuracy"] = True
    elif gate == "G12":
        r1["delivery_scope_audit"]["not_a_forensic_claim_about_unobservable_external_systems"] = (
            False
        )
    else:
        r1["production_gap_register"][0]["production_blocking"] = False
    assert validate_gate(gate, ROOT, r1)["status"] == "BLOCKED"


def overlay(tmp_path, target, raw):
    """Copy-on-write test fixture, never mutate actual frozen source bytes."""
    parents = Path(target).parts
    original, temporary = ROOT, tmp_path
    for component in parents[:-1]:
        for child in original.iterdir():
            if child.name != component and not (temporary / child.name).exists():
                (temporary / child.name).symlink_to(child, target_is_directory=child.is_dir())
        original /= component
        temporary /= component
        temporary.mkdir()
    for child in original.iterdir():
        if child.name != parents[-1]:
            (temporary / child.name).symlink_to(child, target_is_directory=child.is_dir())
    if raw is not None:
        (tmp_path / target).write_bytes(raw)
    return tmp_path


@pytest.mark.parametrize("gate", ["G08", "G09", "G11", "G13"])
@pytest.mark.parametrize("mutation", ["missing", "tamper"])
def test_actual_execution_bytes_missing_or_changed_fail_closed(tmp_path, gate, mutation):
    raw = (ROOT / JUNIT).read_bytes() + b" " if mutation == "tamper" else None
    root = overlay(tmp_path, JUNIT, raw)
    assert validate_gate(gate, root, load(ROOT, EVIDENCE))["status"] == "BLOCKED"


def test_wrong_source_expected_hash_fails_instead_of_recomputing(tmp_path):
    (tmp_path / "source").write_bytes(b"SYNTHETIC")
    with pytest.raises(ValueError, match="SHA256"):
        bound(tmp_path, "source", "0" * 64)


def test_historical_delivery_does_not_freeze_future_authorized_runtime(monkeypatch):
    """SYNTHETIC Git command transcript; no real ref or working tree mutation."""
    merge, delivery = "b" * 40, "c" * 40

    def git(*args, root=None):
        if args == ("git", "diff", "--name-status", BASE, START):
            return "".join("A\t" + p + "\n" for p in R1_FILES).encode()
        if args[:3] == ("git", "rev-list", "--ancestry-path"):
            return (merge + "\n").encode()
        if args == ("git", "rev-list", "--parents", "-n", "1", merge):
            return f"{merge} {BASE} {delivery}\n".encode()
        # No latest HEAD/worktree diff may replace the immutable delivery end.
        assert args == ("git", "diff", "--name-only", START, delivery)
        return "\n".join(R2_FILES).encode()

    monkeypatch.setattr(builder, "command", git)
    assert validate_gate("G12", ROOT, load(ROOT, EVIDENCE))["status"] == "PASS"


@pytest.mark.parametrize("path", [R2_EVIDENCE, SOURCES])
def test_canonical_source_bindings_and_deterministic_output(path):
    assert (ROOT / path).read_bytes() == canonical(load(ROOT, path))
    evidence = load(ROOT, R2_EVIDENCE)
    for member, expected in evidence["source_evidence_sha256"].items():
        assert digest((ROOT / member).read_bytes()) == expected
    assert canonical(generate(ROOT)) == (ROOT / R2_EVIDENCE).read_bytes()
    assert canonical(generate(ROOT)) == canonical(generate(ROOT))


def test_current_governance_missing_approvals_and_future_gates_not_auto_closed():
    evidence = load(ROOT, R2_EVIDENCE)
    assert evidence["result"] == "BLOCKED"
    assert evidence["base_main_sha"] == BASE
    gates = evidence["version_complete_gates"]
    assert [g["status"] for g in gates[:7]] == ["BLOCKED"] * 7
    assert [g["status"] for g in gates[7:13]] == ["PASS"] * 6
    assert [g["status"] for g in gates[13:]] == ["PENDING"] * 3
    governance = evidence["governance"]
    for key in (
        "version_closeout_formal_complete",
        "v0_18_version_complete",
        "ready_authorized",
        "merge_authorized",
        "deploy_authorized",
        "tag_authorized",
        "release_authorized",
        "v0_19_authorized",
    ):
        assert governance[key] is False
    assert evidence["production_readiness"] == "NOT_READY"
    assert governance["stop"] is True
    assert len(R2_FILES) == 5 and R2_DOC in R2_FILES


def test_no_full_private_chat_or_fabricated_historical_authorizations_published():
    capture = load(ROOT, SOURCES)
    assert capture["search_scope"]["full_private_chat_published"] is False
    assert capture["search_scope"]["original_chat_approval_chain_verified"] is False
    assert all("SYNTHETIC" not in r["record_id"] for r in capture["chat_sources"])
    assert all("text" not in r for r in capture["chat_sources"])
    assert all(r["context_verified"] is False for r in capture["chat_sources"])
    # The original phrase is authentic; its missing preceding context cannot
    # be reconstructed from a later assistant summary or a task instruction.
    source = capture["chat_sources"][0]
    assert source["public_excerpt"] == "可以ready合并"
    assert source["original_message_body_sha256"] == digest("可以ready合并".encode())


def test_record_copy_mutation_does_not_alter_frozen_capture():
    capture = load(ROOT, SOURCES)
    original = canonical(capture)
    changed = copy.deepcopy(capture)
    changed["chat_sources"][0]["head_sha"] = "0" * 40
    assert canonical(capture) == original != canonical(changed)
    assert json.loads(original)["chat_sources"][0]["head_sha"] is None
