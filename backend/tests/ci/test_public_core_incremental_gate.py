"""TD01I: independent synthetic review, never publication or business data."""

import json
import subprocess
from dataclasses import replace

import pytest

from backend.app.core import public_core_incremental_gate as gate
from backend.app.core import public_core_incremental_rehearsal as rehearsal

pytestmark = pytest.mark.contract

CODE = (
    b'"""Independent synthetic extension."""\n\n\n'
    b"def amount(value: int) -> int:\n    return value + 1\n"
)
PATH = "backend/app/synthetic_extension.py"


def test_original_root_and_unreviewed_code_have_distinct_states():
    with rehearsal.graph() as graph:
        assert graph.check()["status"] == "PASS"
        commit = graph.commit({PATH: CODE})
        report = graph.check()
        assert report["status"] == "REVIEW_REQUIRED"
        assert "COMMIT_REVIEW_REQUIRED" in rehearsal.reasons(report)
        assert report["proposed_head"] == commit
        graph.review({PATH: CODE})
        assert graph.check()["status"] == "PASS"


def test_two_pull_requests_and_ordinary_merges():
    report = rehearsal.lifecycle()
    assert report["first_unreviewed"]["status"] == "REVIEW_REQUIRED"
    for stage in ("first_reviewed", "first_merged", "second_reviewed", "second_merged"):
        assert report[stage]["status"] == "PASS"
    assert report["second_merged"]["commit_count"] >= 5
    assert report["actual_remote_authorization"] == "UNVERIFIED"


def test_intermediate_deleted_data_is_still_blocked():
    with rehearsal.graph() as graph:
        graph.commit({"data/SYNTHETIC_ONLY.csv": b"SYNTHETIC_ONLY,not_proven\n"})
        graph.commit({"data/SYNTHETIC_ONLY.csv": None})
        report = graph.check()
        assert report["status"] == "BLOCKED"
        assert "UNREGISTERED_DATA_OR_BINARY" in rehearsal.reasons(report)


@pytest.mark.parametrize("oid", sorted(gate.BLOCKED_BLOBS))
def test_forbidden_blob_metadata_blocks_before_any_blob_body(monkeypatch, oid):
    with rehearsal.graph() as graph:
        graph.inject_missing_blob(oid)
        original = gate.Git.read

        def guarded(self, *arguments):
            assert arguments[:2] != ("cat-file", "blob"), "No Blob bodies may be opened"
            return original(self, *arguments)

        monkeypatch.setattr(gate.Git, "read", guarded)
        report = graph.check()
        assert report["status"] == "BLOCKED"
        assert "BLOCKED_BUSINESS_BLOB" in rehearsal.reasons(report)


def test_head_cannot_approve_its_own_policy_or_verifier():
    with rehearsal.graph() as graph:
        graph.commit(
            {
                PATH: CODE,
                "PUBLIC-CORE-MANIFEST.json": b'{"APPROVED":true,"sha256":"new"}\n',
                "tools/verify_public_core.py": b'print("PASS")\n',
                "tools/public_core_incremental_gate.py": b'print("PASS")\n',
                "PUBLIC-CORE-V2-EXECUTORS.json": b'{"APPROVED":true,"sha256":"new"}\n',
                ".github/workflows/self-approval.yml": b"permissions: write-all\n",
                "approval.json": b'{"SYNTHETIC_ONLY":true,"APPROVED":true}\n',
            }
        )
        report = graph.check()
        assert report["status"] == "BLOCKED"
        assert "UNTRUSTED_POLICY_CHANGE" in rehearsal.reasons(report)


@pytest.mark.parametrize(
    "kind",
    [
        "tag",
        "ref_rollback",
        "extra_ref",
        "alternate",
        "graft",
        "shallow",
        "remote",
        "dangling",
        "old_commit",
        "symlink",
        "submodule",
        "lfs",
        "binary",
        "missing",
        "wrong_base",
        "wrong_review",
        "dependency",
        "path",
    ],
)
def test_git_and_authority_negative_cases(kind):
    report = rehearsal.negative(kind)
    assert report["status"] == "BLOCKED", (kind, report)
    assert report["reasons"]
    text = json.dumps(report)
    assert "SYNTHETIC_PRIVATE_LITERAL_MUST_NOT_APPEAR" not in text
    assert "/Users/" not in text and "/tmp/" not in text


def test_external_review_cannot_be_minted_from_different_expected_bytes():
    with rehearsal.graph() as graph:
        graph.commit({PATH: CODE})
        with pytest.raises(AssertionError, match="INDEPENDENT_REVIEW_INPUT_MISMATCH"):
            graph.review({PATH: CODE + b"# unexpected\n"})


def test_review_scope_and_exact_object_identity_are_bound():
    with rehearsal.graph() as graph:
        graph.commit({PATH: CODE})
        graph.review({PATH: CODE})
        authority = graph.authority()
        review = authority.reviews[-1]
        forged = replace(
            authority, reviews=(*authority.reviews[:-1], replace(review, tree="0" * 40))
        )
        report = gate.verify(graph.repo, graph.context(), forged)
        assert report["status"] == "BLOCKED"
        assert "REVIEW_IDENTITY_MISMATCH" in rehearsal.reasons(report)


def test_synthetic_bundle_uses_frozen_producer_and_complete_bytes():
    report = rehearsal.synthetic_bundle_case()
    assert report["valid"]["status"] == "PASS"
    assert report["changed_bytes"]["status"] == "BLOCKED"
    assert report["wrong_producer"]["status"] == "BLOCKED"


def test_self_consistent_reviewed_bundle_must_be_actual_frozen_generator_output():
    report = rehearsal.counterfeit_bundle_case()
    assert report["file_count"] == 5
    assert report["manifest_self_consistent"] is True
    assert report["independent_review_matches_all_blobs_and_sha256"] is True
    assert report["declared_seed"] == 43
    assert report["actual_generation_seed"] == 41
    assert report["gate"]["status"] == "BLOCKED"
    assert "SYNTHETIC_GENERATOR_OUTPUT_MISMATCH" in rehearsal.reasons(report["gate"])


def test_full_xlsx_container_is_compared_even_with_unchanged_sheet_values():
    report = rehearsal.counterfeit_bundle_case(xlsx_container_only=True)
    assert report["manifest_self_consistent"] is True
    assert report["independent_review_matches_all_blobs_and_sha256"] is True
    assert report["declared_seed"] == report["actual_generation_seed"] == 41
    assert report["gate"]["status"] == "BLOCKED"
    assert "SYNTHETIC_GENERATOR_OUTPUT_MISMATCH" in rehearsal.reasons(report["gate"])


def test_missing_trusted_regeneration_is_blocked_without_public_child_error(monkeypatch):
    original = subprocess.run

    def unavailable(command, *args, **kwargs):
        if len(command) > 3 and command[1:4] == ["-I", "-B", "-c"]:
            return subprocess.CompletedProcess(command, 2, b"", b"SYNTHETIC_PRIVATE_ERROR")
        return original(command, *args, **kwargs)

    monkeypatch.setattr(gate.subprocess, "run", unavailable)
    report = rehearsal.counterfeit_bundle_case()["gate"]
    assert report["status"] == "BLOCKED"
    assert "SYNTHETIC_REGENERATION_UNAVAILABLE" in rehearsal.reasons(report)
    assert "SYNTHETIC_PRIVATE_ERROR" not in json.dumps(report)


def test_verified_root_executes_before_reading_any_proposed_bundle_blob(monkeypatch):
    original_read = gate.Git.read
    original_regenerate = gate._regenerate
    verified_root_blobs = set()
    regenerated = False

    def replay(git, root, seed):
        nonlocal regenerated
        assert verified_root_blobs == {f.blob for f in root.values()}
        result = original_regenerate(git, root, seed)
        regenerated = True
        return result

    def guarded(self, *arguments):
        if arguments[:2] == ("cat-file", "blob"):
            assert arguments[2] in verified_root_blobs or regenerated
        return original_read(self, *arguments)

    with rehearsal.graph() as graph:
        root = gate._bootstrap(gate.Git(graph.repo))
        verified_root_blobs.update(f.blob for f in root.values())
        monkeypatch.setattr(gate, "_regenerate", replay)
        monkeypatch.setattr(gate.Git, "read", guarded)
        # Nested fixture roots have the identical sealed Blob identities.
        report = rehearsal.counterfeit_bundle_case()["gate"]
    assert regenerated is True
    assert report["status"] == "BLOCKED"
    assert "SYNTHETIC_GENERATOR_OUTPUT_MISMATCH" in rehearsal.reasons(report)


def test_checked_out_test_merge_is_not_the_trusted_base():
    report = rehearsal.checkout_case()
    assert report["valid"]["status"] == "PASS"
    assert report["wrong_checkout"]["status"] == "BLOCKED"
    assert report["untrusted_origin"]["status"] == "BLOCKED"


def test_report_is_identical_in_two_independent_processes(tmp_path):
    report = rehearsal.independent_processes(tmp_path)
    assert report["equal"] is True
    assert report["process_count"] == 2
    assert report["exit_codes"] == [0, 0]
    assert report["independent_graph_results_equal"] is True
    assert report["independent_graph_exit_codes"] == [0, 0]


def test_advanced_base_and_feature_use_the_actual_divergent_merge_base():
    with rehearsal.graph() as graph:
        proposed = graph.commit({PATH: CODE})
        branch = graph.branch
        graph.review({PATH: CODE})
        graph.write_git("checkout", "-q", "main")
        graph.head = graph.base
        graph.branch = "refs/heads/main"
        note = {"backend/app/synthetic_base_extension.py": b"VALUE = 3\n"}
        advanced = graph.commit(note)
        graph.review(note)
        graph.base = advanced
        graph.head = proposed
        graph.branch = branch
        graph.checked_out = proposed
        graph.write_git("checkout", "-q", "--detach", proposed)
        report = graph.check()
        assert report["status"] == "PASS"
        assert report["merge_base"] == gate.V1_ROOT
        assert report["trusted_base"] != report["merge_base"]
        assert graph.merge({PATH: CODE})["status"] == "PASS"


def test_deletions_and_exact_blob_renames_need_independent_review():
    with rehearsal.graph() as graph:
        graph.commit({PATH: CODE})
        graph.review({PATH: CODE})
        graph.merge({PATH: CODE})
        renamed = "backend/app/synthetic_renamed.py"
        graph.commit({PATH: None, renamed: CODE})
        report = graph.check()
        assert report["status"] == "REVIEW_REQUIRED"
        assert any(row.get("exact_blob_rename_to") == renamed for row in report["proposed_diff"])
        graph.review({PATH: None, renamed: CODE})
        assert graph.check()["status"] == "PASS"


def test_external_review_pin_and_head_path_cannot_self_authorize(tmp_path):
    with rehearsal.graph() as graph:
        file = tmp_path / "trusted-review.json"
        raw = gate.canonical(gate.authority_payload(graph.authority()))
        file.write_bytes(raw)
        file.chmod(0o600)
        original_seal = gate.digest(raw)
        assert gate.read_authority(file, original_seal, graph.repo) == graph.authority()
        file.write_bytes(raw.replace(gate.AUTHORITY_KIND.encode(), b"SELF_APPROVED"))
        with pytest.raises(gate.Violation, match="SEAL_MISMATCH"):
            gate.read_authority(file, original_seal, graph.repo)
        head_file = graph.repo / "self-approved.json"
        head_file.write_bytes(file.read_bytes())
        with pytest.raises(gate.Violation, match="PROPOSED_HEAD_IS_NOT_AUTHORITY"):
            gate.read_authority(head_file, gate.digest(head_file.read_bytes()), graph.repo)


def test_unreviewed_head_never_reaches_installation(tmp_path):
    from backend.app.core import public_core_incremental_ci as ci

    with rehearsal.graph() as graph:
        graph.commit({PATH: CODE})
        output = tmp_path / "blocked-install"
        with pytest.raises(RuntimeError, match="V2_LOCAL_CI_EQUIVALENCE_FAILED"):
            ci.execute(graph.repo, graph.context(), graph.authority(), output)
        result = json.loads((output / "summary.json").read_bytes())
        assert result["status"] == "REVIEW_REQUIRED"
        assert set(result["commands"]) == {"trusted-base-gate"}
        assert not (output / "v1-ci").exists()


def test_workflow_trust_gates_and_original_ci_are_distinct():
    import yaml

    workflow = (rehearsal.ROOT / "public_core/td01i_v2/workflow.yml").read_text()
    payload = yaml.safe_load(workflow)
    triggers = payload.get("on", payload.get(True))
    assert set(triggers) == {"pull_request", "push", "workflow_dispatch"}
    assert payload["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in workflow
    assert "persist-credentials: false" in workflow
    assert "--synthetic-review-authority" not in workflow
    assert "TRUSTED_V2_BOOTSTRAP_NOT_INSTALLED" in workflow
    assert "trusted-base/tools/public_core_incremental_gate.py" in workflow
    assert "continue-on-error" not in workflow and "|| true" not in workflow
    assert "--no-tags" in workflow and "refs/heads/trusted-base" in workflow


def test_external_config_include_is_rejected_before_git_runs(monkeypatch):
    with rehearsal.graph() as graph:
        file = graph.repo / ".git/config"
        file.write_text(file.read_text() + "\n[include]\n path = /SYNTHETIC_DO_NOT_OPEN\n")

        def forbidden(*args):
            pytest.fail("Git must not resolve external config")

        monkeypatch.setattr(gate.Git, "read", forbidden)
        report = graph.check()
        assert report["status"] == "BLOCKED"
        assert "UNREVIEWED_GIT_CONFIGURATION" in rehearsal.reasons(report)


def test_local_archive_attributes_cannot_hide_source():
    with rehearsal.graph() as graph:
        file = graph.repo / ".git/info/attributes"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("* export-ignore\n")
        report = graph.check()
        assert report["status"] == "BLOCKED"


def test_new_dependency_lock_requires_a_new_reviewed_installation_contract():
    with rehearsal.graph() as graph:
        lock = b"SYNTHETIC_PACKAGE==1.0\n"
        path = "requirements-lock.txt"
        graph.commit({path: lock})
        graph.review({path: lock}, kinds={path: "DEPENDENCY"})
        report = graph.check()
        assert report["status"] == "REVIEW_REQUIRED"
        assert "DEPENDENCY_CLOSURE_REVIEW_REQUIRED" in rehearsal.reasons(report)


def test_schema_is_reviewed_content_not_an_automatic_data_clearance():
    with rehearsal.graph() as graph:
        path = "schemas/synthetic.schema.json"
        raw = b'{"type":"object","properties":{"value":{"type":"number"}}}\n'
        graph.commit({path: raw})
        assert graph.check()["status"] == "REVIEW_REQUIRED"
        graph.review({path: raw}, kinds={path: "SCHEMA"})
        assert graph.check()["status"] == "PASS"


def test_forbidden_identity_in_deleted_intermediate_tree_is_not_hidden():
    with rehearsal.graph() as graph:
        graph.inject_missing_blob(sorted(gate.BLOCKED_BLOBS)[0])
        (graph.repo / "renamed.py").write_text("SYNTHETIC_PLACEHOLDER_NOT_REAL_DATA\n")
        graph.commit({"renamed.py": None})
        assert "renamed.py" not in gate.Git(graph.repo).tree(graph.head)
        report = graph.check()
        assert report["status"] == "BLOCKED"
        assert "BLOCKED_BUSINESS_BLOB" in rehearsal.reasons(report)


def test_clean_head_tree_does_not_erase_unreviewed_code_commits():
    with rehearsal.graph() as graph:
        graph.commit({PATH: CODE})
        graph.commit({PATH: None})
        assert gate.Git(graph.repo).tree(graph.head) == gate.Git(graph.repo).tree(gate.V1_ROOT)
        report = graph.check()
        assert report["status"] == "REVIEW_REQUIRED"
        assert len([r for r in report["reasons"] if r["code"] == "COMMIT_REVIEW_REQUIRED"]) == 2


def test_trusted_workflow_event_adapter_and_argument_rejection(tmp_path):
    import subprocess
    import sys

    with rehearsal.graph() as graph:
        graph.commit({PATH: CODE})
        graph.review({PATH: CODE})
        assert graph.branch is not None
        old_branch = graph.branch
        graph.write_git("update-ref", "refs/heads/trusted-base", graph.base)
        graph.write_git("update-ref", "refs/heads/proposed-head", graph.head)
        graph.write_git("symbolic-ref", "HEAD", "refs/heads/proposed-head")
        graph.write_git("update-ref", "-d", old_branch)
        graph.write_git("update-ref", "-d", "refs/heads/main")
        graph.write_git(
            "config", "remote.origin.url", "https://github.com/SYNTHETIC_ONLY/SYNTHETIC_PUBLIC_CORE"
        )
        output = tmp_path / "event.json"
        command = [
            sys.executable,
            "-I",
            "-B",
            str(rehearsal.ROOT / "public_core/td01i_v2/workflow_context.py"),
            "--base",
            graph.base,
            "--head",
            graph.head,
            "--expected-repository",
            "SYNTHETIC_ONLY/SYNTHETIC_PUBLIC_CORE",
            "--output",
            str(output),
        ]
        assert subprocess.run(command, capture_output=True).returncode == 0
        assert (
            gate.verify(graph.repo, gate.read_context(output), graph.authority())["status"]
            == "PASS"
        )
        bad = [*command[:6], "--head=--help", *command[8:]]
        result = subprocess.run(bad, capture_output=True)
        assert result.returncode != 0


def test_v1_files_and_original_workflow_are_not_changed():
    rehearsal.verify_v1_preserved()


def test_v2_executor_manifest_records_bytes_but_grants_no_review_authority():
    manifest = json.loads(
        (rehearsal.ROOT / "public_core/td01i_v2/executor-manifest.json").read_bytes()
    )
    sources = {
        "tools/public_core_incremental_gate.py": "backend/app/core/public_core_incremental_gate.py",
        "tools/run_public_ci_v2.py": "public_core/td01i_v2/run_public_ci.py",
        "tools/public_core_v2_context.py": "public_core/td01i_v2/workflow_context.py",
        "tests/test_public_gate_v2.py": "public_core/td01i_v2/test_gate.py",
    }
    assert manifest["review_authority"] == "NOT_CONFIGURED_SOURCE_IDENTITIES_ONLY"
    assert manifest["publication_authorized"] is False
    assert {row["path"] for row in manifest["files"]} == set(sources)
    for row in manifest["files"]:
        raw = (rehearsal.ROOT / sources[row["path"]]).read_bytes()
        assert gate.digest(raw) == row["sha256"]
        assert gate.blob_id(raw) == row["git_blob_oid"]


@pytest.mark.integration
def test_v2_local_ci_equivalence_uses_fresh_install_and_original_38(tmp_path):
    report = rehearsal.ci_equivalent(tmp_path / "td01i-ci")
    assert report["status"] == "PASS"
    assert report["v1_public_tests"] == 38
    assert report["active_head_functional_tests"] == 24
    assert report["v2_security_tests"] == 15
    assert report["reviewed_head_tests"] == 15
    assert report["executor_origin_base"] == report["gate"]["trusted_base"]
    assert report["executor_origin_base"] != "SYNTHETIC_BOOTSTRAP_HOST"
    assert report["actual_new_remote_github_actions"] == "NOT_RUN"
