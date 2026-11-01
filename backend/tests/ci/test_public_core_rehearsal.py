"""TD01G scope; preserves the original TD01F historical-audit failure ledger."""

import json

import pytest

from backend.app.core import public_core_rehearsal as public

pytestmark = pytest.mark.contract


def test_frozen_td01f_manifests_and_scope_have_not_been_replaced():
    old = json.loads(
        (
            public.ROOT / "docs/tech-debt/td01f-rehearsal-r1/public-ci-compatibility-report.json"
        ).read_bytes()
    )
    assert old["isolated_checks"]["synthetic_publication_tests"]["passed"] == 24
    assert old["isolated_checks"]["synthetic_publication_tests"]["failed"] == 1
    assert old["isolated_checks"]["synthetic_publication_tests"]["status"] == "BLOCKED"
    assert (
        public.previous.CATALOG_SHA256
        == "2a4386ee221bab46832c69f0a9be98836791df4db8bdc5db9e9f860f22466255"
    )
    paths = {row["repository_relative_path"] for row in public.catalog()}
    assert "backend/tests/etl/test_synthetic_publication.py" not in paths
    assert "pyproject.toml" not in paths
    assert len(paths) == 27


def test_controlled_root_reuses_exact_code_without_original_git_objects():
    with public.previous.owned_repository() as root:
        proof = public.materialize(root)
        assert proof["git_objects"]["status"] == "PASS"
        assert proof["git_objects"]["file_count"] == 28
        assert proof["git_objects"]["remote_count"] == 0
        assert proof["git_objects"]["parent_count"] == 0
        assert proof["historical_td01f_result_preserved"]["blocked"] == 1
        for oid in public.previous.BLOCKED_BLOBS:
            assert public.history._run(root, "cat-file", "-e", oid).returncode != 0
        assert not (root / "docs/tech-debt/td01c-public-derived-audit-summary.json").exists()


def test_unknown_catalog_identity_cannot_be_self_approved(tmp_path, monkeypatch):
    payload = json.loads(public.CATALOG.read_bytes())
    payload["publication_authorized"] = True
    payload["entries"][0]["sha256"] = "0" * 64
    file = tmp_path / "forged.json"
    file.write_text(json.dumps(payload))
    monkeypatch.setattr(public, "CATALOG", file)
    with pytest.raises(AssertionError, match="CATALOG_SEAL_MISMATCH"):
        public.catalog()


def test_foreign_repository_is_never_written(tmp_path):
    with pytest.raises(AssertionError, match="OWNED_TEMPORARY"):
        public.materialize(tmp_path)


def test_public_workflow_keeps_all_gates_and_has_no_release_command():
    workflow = (public.ROOT / "public_core/td01g_v1/workflow.yml").read_text()
    assert "python-version: '3.12'" in workflow
    assert "python -I -B tools/verify_public_core.py" in workflow
    assert "python -I -B tools/run_public_ci.py" in workflow
    assert "persist-credentials: false" in workflow
    assert "contents: read" in workflow
    assert "continue-on-error" not in workflow
    runner = (public.ROOT / "public_core/td01g_v1/run_public_ci.py").read_text()
    for required in (
        '"--require-hashes"',
        '"--no-deps"',
        '"strict-mypy"',
        '"public-contracts"',
        "system_site_packages=False",
    ):
        assert required in runner
    assert "sys.executable" not in workflow
    assert "ACTUAL_NEW_REMOTE_GITHUB_ACTIONS" in runner


@pytest.mark.integration
@pytest.mark.contract
def test_independent_public_environment_and_ci_equivalent(tmp_path):
    # New isolated install is mandatory here; no inherited environment counts.
    report = public.rehearse(tmp_path / "td01g-independent")
    assert report["status"] == "PASS"
    ci = report["public_ci"]
    assert ci["status"] == "PASS"
    assert ci["actual_new_remote_github_actions"] == "NOT_RUN"
    assert ci["isolated_install"]["system_site_packages"] is False
    assert ci["installed_imports"]["all_local_modules_installed_in_owned_venv"] is True
    assert all(command["exit_code"] == 0 for command in ci["commands"].values())
    assert ci["git_object_verification"] == ci["git_object_verification_after"]
