"""Current component inventory is distinct from immutable engineering releases."""

import json
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from backend.app.core.config import AppSettings
from backend.app.core.version import APP_VERSION
from backend.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.unit, pytest.mark.contract]


def manifest() -> dict:
    return json.loads((ROOT / "version-manifest.json").read_text())


def test_python_component_and_lock_match_declared_component_version():
    declared = manifest()["components"]["python_package"]
    project = tomllib.loads((ROOT / declared["source"]).read_text())["project"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    packages = [p for p in lock["package"] if p["name"] == project["name"]]
    assert project["version"] == declared["version"]
    assert len(packages) == 1
    assert packages[0]["version"] == declared["version"]


def test_frontend_component_and_both_lock_versions_match():
    declared = manifest()["components"]["frontend_application"]
    package = json.loads((ROOT / declared["source"]).read_text())
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text())
    assert package["private"] is True
    assert package["version"] == lock["version"] == lock["packages"][""]["version"]
    assert package["version"] == declared["version"]


def test_service_openapi_identity_remains_the_component_not_release():
    contract = manifest()
    component = contract["components"]["fastapi_service"]
    app = create_app(AppSettings(app_env="test"))
    assert APP_VERSION == component["version"]
    assert app.version == APP_VERSION
    assert app.openapi()["info"]["version"] == APP_VERSION
    assert component["source"] == "backend/app/core/version.py"
    assert component["symbol"] == "APP_VERSION"


def test_release_inventory_is_explicit_and_does_not_claim_current_git_identity():
    contract = manifest()
    release = contract["engineering_release"]
    assert contract["schema_version"] == 1
    assert release["tag"] == "v" + release["version"]
    assert re.fullmatch(r"[0-9a-f]{40}", release["commit"])
    assert release["url"].endswith("/releases/tag/" + release["tag"])
    assert (ROOT / release["scope_document"]).is_file()
    assert contract["checkout_identity"] == {
        "source": "git rev-parse --verify HEAD",
        "dirty_source": "git status --porcelain=v1",
        "release_record_is_current_checkout": False,
    }
    assert contract["runtime_reads_manifest"] is False
    assert contract["component_policy"] == "RETAIN_EXISTING_COMPATIBILITY_IDENTITIES"


@pytest.mark.parametrize(
    "document",
    ["AGENTS.md", "CODEX_MASTER_PROMPT.md", "CODEX_TASKS.md", "README.md", "VERSIONING.md"],
)
def test_current_guidance_relative_links_resolve(document):
    text = (ROOT / document).read_text()
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
    assert links
    for link in links:
        if "://" in link or link.startswith("#"):
            continue
        assert (ROOT / link.split("#", 1)[0]).exists(), (document, link)


@pytest.mark.parametrize("season", ["2024_2025", "2025_2026"])
def test_legacy_workbooks_remain_untracked(season):
    # A custodian may retain an ignored local original; never open or delete it.
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", f"data/raw/{season}_receipts.xls"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1 and not result.stdout
