"""Offline closeout integrity: public Git objects, no business or network access."""

import ast
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from backend.tests.forecast_intelligence.build_v0_18_version_closeout import (
    BASE,
    CLASSIFICATION,
    DOC,
    EVIDENCE,
    MANIFEST,
    RELEASE,
    SNAPSHOT,
    canonical,
    command,
    generate,
    git_blob,
    git_blobs,
    review_audit,
)

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def load(path):
    return json.loads((ROOT / path).read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("path", (EVIDENCE, MANIFEST, SNAPSHOT))
def test_canonical_bytes_and_key_order(path):
    value = load(path)
    assert (ROOT / path).read_bytes() == canonical(value)
    assert canonical(dict(reversed(list(value.items())))) == canonical(value)


def test_manifest_current_sources_and_frozen_git_bytes():
    value = load(EVIDENCE)
    manifest = load(MANIFEST)
    assert set(manifest["members"]) == {DOC, EVIDENCE, SNAPSHOT}
    for path, expected in manifest["members"].items():
        assert sha((ROOT / path).read_bytes()) == expected
    assert value["github_snapshot_sha256"] == sha((ROOT / SNAPSHOT).read_bytes())
    for path, expected in value["source_evidence_sha256"].items():
        assert re.fullmatch(r"[0-9a-f]{64}", expected)
        if path in {
            DOC,
            __file__.split(str(ROOT) + "/")[-1],
            "backend/tests/forecast_intelligence/build_v0_18_version_closeout.py",
        }:
            actual = (ROOT / path).read_bytes()
        else:
            actual = git_blob(ROOT, BASE, path)
        assert sha(actual) == expected, path
    assert len(value["historical_git_sha256"]) > 764
    historical = value["historical_git_sha256"]
    first = git_blobs(ROOT, {p: b["first_main_commit"] for p, b in historical.items()})
    for path, binding in historical.items():
        assert not Path(path).is_absolute() and ".." not in Path(path).parts
        frozen = first[path]
        assert sha(frozen) == binding["sha256"] == sha((ROOT / path).read_bytes()), path
    model_bindings = value["frozen_model_and_math_sha256"]
    models = git_blobs(ROOT, dict.fromkeys(model_bindings, RELEASE))
    audited = git_blobs(ROOT, dict.fromkeys(model_bindings, BASE))
    for path, expected in model_bindings.items():
        assert sha(models[path]) == expected
        assert sha(audited[path]) == expected
    assert value["historical_snapshot_policy"] == {
        "pre_v018_documents": "V0_17_ANNOTATED_RELEASE_COMMIT",
        "v018_documents": "FIRST_MAIN_APPEARANCE_WITHIN_AUDITED_CHAIN",
        "backend_code": "IMMUTABLE_RELEASE_AND_AUDITED_BASE_GIT_BLOBS",
        "not_a_permanent_freeze_of_all_future_backend_worktree_bytes": True,
    }


def test_complete_merge_chain_and_all_attempt_ci_binding():
    value, snapshot = load(EVIDENCE), load(SNAPSHOT)
    assert value["base_main_sha"] == BASE and value["release_baseline_sha"] == RELEASE
    assert snapshot["release"]["tag_name"] == "v0.17.0"
    assert snapshot["annotated_tag"]["commit_sha"] == RELEASE
    assert snapshot["release"]["draft"] is snapshot["release"]["prerelease"] is False
    prior = RELEASE
    assert [r["pr_number"] for r in value["stage_chain"]] == list(CLASSIFICATION)
    for row, public in zip(value["stage_chain"], snapshot["pull_requests"], strict=True):
        assert public["merged"] and public["state"] == "closed"
        assert row["merge_parents"] == [prior, row["head_sha"]] == public["parents"]
        actual = (
            command("git", "rev-list", "--parents", "-n", "1", row["merge_commit_sha"], root=ROOT)
            .decode()
            .split()[1:]
        )
        assert actual == row["merge_parents"]
        assert row["base_sha"] == prior
        assert row["classification"] == CLASSIFICATION[row["pr_number"]]
        for key, event, expected_sha in (
            ("pr_ci", "pull_request", row["head_sha"]),
            ("main_ci", "push", row["merge_commit_sha"]),
        ):
            ci = row[key]
            assert ci in public["ci_attempts"]
            assert ci["head_sha"] == expected_sha and ci["event"] == event
            assert ci["status"] == "completed" and ci["run_attempt"] >= 1
            assert len(ci["jobs"]) == len({j["id"] for j in ci["jobs"]}) == 12
            assert all(j["status"] == "completed" for j in ci["jobs"])
            expected_failure = key == "main_ci" and row["pr_number"] == 718
            assert ci["conclusion"] == ("failure" if expected_failure else "success")
            assert sum(j["conclusion"] == "failure" for j in ci["jobs"]) == int(expected_failure)
            assert sum(j["conclusion"] == "success" for j in ci["jobs"]) == (
                12 if key == "pr_ci" else 3 if expected_failure else 4
            )
            assert sum(j["conclusion"] == "skipped" for j in ci["jobs"]) == (
                0 if key == "pr_ci" else 8
            )
        prior = row["merge_commit_sha"]
    assert prior == BASE
    assert value["main_first_parent_chain"] == [r["merge_commit_sha"] for r in value["stage_chain"]]


def test_missing_reviews_do_not_become_pass_by_merge_or_self_receipt():
    snapshot, value = load(SNAPSHOT), load(EVIDENCE)
    for row, public in zip(value["stage_chain"], snapshot["pull_requests"], strict=True):
        assert row["review_and_authorization"] == review_audit(public)
        audit = row["review_and_authorization"]
        assert audit["owner_merge_is_not_independent_review_or_prior_authorization"] is True
        for review_id in audit["exact_head_review_ids"]:
            review = next(r for r in public["reviews"] if r["id"] == review_id)
            assert review["commit_id"] == public["head_sha"]
            assert review["submitted_at"] <= public["merged_at"]
    s6 = snapshot["pull_requests"][-1]
    assert s6["number"] == 727 and s6["reviews"] == []
    assert any(c["id"] == 6198085541 for c in s6["comments"])
    assert review_audit(s6)["independent_exact_head_review_status"].startswith("BLOCKED")
    no_reviews = copy.deepcopy(s6)
    no_reviews["comments"] = [
        {
            "id": 1,
            "author": "xuezhiorange-png",
            "body": "REVIEW_RESULT=PASS READY_AUTHORIZED=false MERGE_AUTHORIZED=false",
            "created_at": s6["merged_at"],
        }
    ]
    assert review_audit(no_reviews)["owner_ready_merge_authorization_status"].startswith("BLOCKED")


def test_history_failures_and_s5_cancelled_attempt_remain_separate():
    value, snapshot = load(EVIDENCE), load(SNAPSHOT)
    failure, cancelled = value["historical_failures"]
    assert failure == {
        "pr": 718,
        "run": 38326155853,
        "conclusion": "failure",
        "corrected_by_pr": 721,
        "corrected_main_ci": 38425016611,
        "cause": "EXPORT_TIMESTAMP_BOUNDARY",
    }
    s5 = next(p for p in snapshot["pull_requests"] if p["number"] == 726)
    attempts = [c for c in s5["ci_attempts"] if c["id"] == 38703671252]
    assert [(c["run_attempt"], c["conclusion"]) for c in attempts] == [
        (1, "cancelled"),
        (2, "success"),
    ]
    assert cancelled["conclusion"] == "cancelled" and cancelled["successful_attempt"] == 2
    s6 = value["stage_chain"][-1]["main_ci"]
    assert s6["id"] == 38826434182 and s6["conclusion"] == "success"
    logs = snapshot["main_log_summaries"]
    assert len(logs) == 6
    for log in logs:
        assert re.fullmatch(r"[0-9a-f]{64}", log["log_sha256"])
        assert log["source_url"] and log["excerpts"]
    red = next(r for r in logs if r["pr_number"] == 718 and r["job_name"] == "full-suite-canary")
    assert any("1 failed, 10044 passed, 5 skipped" in line for line in red["excerpts"])
    assert any(
        "test_overwrite_always_succeeds_and_replaces_bytes" in line for line in red["excerpts"]
    )
    final = [r for r in logs if r["pr_number"] == 727]
    assert any("10212 passed, 5 skipped" in line for r in final for line in r["excerpts"])
    assert any("142 passed" in line for r in final for line in r["excerpts"])


def test_review_wrong_head_dismissed_or_subset_pass_is_not_independent_pass():
    row = copy.deepcopy(load(SNAPSHOT)["pull_requests"][0])
    assert review_audit(row)["exact_head_review_ids"]
    for modification in (
        {"commit_id": "0" * 40},
        {"state": "DISMISSED"},
        {"body": "independent review BLOCKED; tested subset PASS"},
        {"submitted_at": "2999-01-01T00:00:00Z"},
    ):
        changed = copy.deepcopy(row)
        changed["reviews"] = [row["reviews"][0] | modification]
        assert review_audit(changed)["independent_exact_head_review_status"].startswith("BLOCKED")


@pytest.mark.parametrize(
    "commit,path", [("0" * 40, DOC), (BASE, "docs/nonexistent-closeout-source")]
)
def test_missing_git_source_never_becomes_empty_success(commit, path):
    with pytest.raises(AssertionError):
        git_blobs(ROOT, {path: commit})


def test_real_s6_proofs_and_artifact_integrity_are_not_new_execution():
    value = load(EVIDENCE)
    s6 = load(value["frozen_s6_acceptance"]["path"])
    assert sha(canonical(s6)) == value["frozen_s6_acceptance"]["sha256"]
    assert len(s6["parity_matrix"]) == 54 and len(s6["zero_read_proofs"]) == 8
    assert len(s6["tls_release_proofs"]) == 2
    for artifact, binding in s6["artifacts"].items():
        assert sha((ROOT / artifact).read_bytes()) == binding["sha256"]
    for proof in s6["zero_read_proofs"]:
        assert all(
            proof[key] == 0
            for key in (
                "BUSINESS_READ_COUNT",
                "QUALITY_FILE_READ_COUNT",
                "SIMULATION_EXECUTION_COUNT",
            )
        )
    for proof in s6["tls_release_proofs"]:
        assert proof["canonical_read_reached"] and proof["revocation_committed_before_release"]
        assert proof["sensitive_bytes_returned"] is False
    assert len(s6["browser"]["screenshots"]) == 62
    assert value["delivery_scope_audit"]["current_closeout_no_runtime_business_execution"]


def test_exact_tools_and_five_pages_current_authoritative_source():
    tree = ast.parse(git_blob(ROOT, BASE, "backend/app/mcp/forecast_intelligence_tools.py"))
    tools = next(
        n.value
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in n.targets)
    )
    assert [k.value for k in tools.keys] == [
        "get_forecast_overview",
        "get_forecast_curve",
        "get_hierarchical_forecast",
        "get_forecast_uncertainty",
        "get_forecast_attribution",
        "get_forecast_quality",
        "simulate_capacity",
        "compare_capacity_scenarios",
    ]
    dashboard = git_blob(ROOT, BASE, "frontend/src/dashboard/app/Dashboard.tsx").decode()
    assert re.findall(r'<Route path="([^"*]+)"', dashboard) == [
        "overview",
        "forecast",
        "attribution",
        "capacity",
        "quality",
    ]
    scope = load(EVIDENCE)["security_scope"]
    assert scope["mcp_tool_count"] == 8 and scope["mcp_mode"] == "SERVICE_ACCOUNT_ONLY"
    assert scope["independent_quality_grant"] is True
    assert scope["end_user_delegation"] is scope["admin_implicit_business_access"] is False


def test_semantics_gaps_and_unapproved_gates_remain_truthful():
    value = load(EVIDENCE)
    semantics = value["semantic_boundaries"]
    assert semantics["H7"] == "D1..D7_PREFIX_CUMULATIVE"
    assert semantics["H15"] == "D1..D15_PREFIX_CUMULATIVE"
    assert semantics["rolling_seven_day_maximum"] == "NOT_VALIDATED_SOURCE_CAPABILITY_UNAVAILABLE"
    assert len(semantics["unavailable"]) == 4
    assert semantics["strict_pit"] is semantics["real_roi_validated"] is False
    assert semantics["loss_unit"] == "SYNTHETIC_LOSS_UNIT"
    assert value["production_readiness"] == "NOT_READY"
    assert len(value["production_gap_register"]) == 15
    for gap in value["production_gap_register"]:
        assert gap["status"] == "OPEN_NOT_VALIDATED" and gap["production_blocking"]
        assert (
            gap["current_evidence"] and gap["missing_evidence"] and gap["required_owner_decision"]
        )
    gates = value["version_complete_gates"]
    assert [g["id"] for g in gates] == [f"G{i:02}" for i in range(1, 17)]
    assert all(g["evidence"] for g in gates)
    assert [g["status"] for g in gates[13:]] == ["PENDING"] * 3
    assert gates[6]["status"] == "BLOCKED" and value["result"] == "BLOCKED"
    assert value["gate_counts"] == {
        s: sum(g["status"] == s for g in gates) for s in ("PASS", "FAIL", "BLOCKED", "PENDING")
    }
    for key, flag in value["governance"].items():
        if key in {"owner_closeout_authorized", "stop"}:
            assert flag is True
        elif key == "external_final_head_ci_receipt":
            assert flag == "PENDING_POST_COMMIT_SEPARATE_RECEIPT"
        else:
            assert flag is False


def test_offline_generator_is_byte_deterministic(tmp_path):
    # Only generated outputs enter tmp_path; Git sources stay read-only.
    first = generate(ROOT, load(SNAPSHOT), output_root=tmp_path)
    before = (tmp_path / EVIDENCE).read_bytes()
    second = generate(ROOT, load(SNAPSHOT), output_root=tmp_path)
    assert canonical(first) == canonical(second) == before == (ROOT / EVIDENCE).read_bytes()
    assert (tmp_path / MANIFEST).read_bytes() == (ROOT / MANIFEST).read_bytes()
