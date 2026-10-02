"""Public-only V0.10 extraction acceptance; no model/data experiment."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.replay_v0_10_closeout import file_hash, verify, verify_changed_paths

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = Path("artifacts/v0-10-closeout")
BOUNDARY = Path("docs/v0-10/evidence/release-lifecycle-boundary-r1.json")


@pytest.fixture
def exported(tmp_path: Path) -> Path:
    manifest = json.loads((ROOT / PUBLIC / "public-artifact-manifest.json").read_text())
    for item in manifest["files"]:
        target = tmp_path / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / item["path"], target)
    shutil.copyfile(
        ROOT / PUBLIC / "public-artifact-manifest.json",
        tmp_path / PUBLIC / "public-artifact-manifest.json",
    )
    return tmp_path


def update(root: Path, path: Path, payload: dict) -> None:
    (root / path).write_text(json.dumps(payload))
    manifest_path = root / PUBLIC / "public-artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for row in manifest["files"]:
        if row["path"] == str(path):
            row["sha256"] = file_hash(root / path)
    manifest_path.write_text(json.dumps(manifest))


def test_public_replay() -> None:
    result = verify(ROOT)
    assert result["status"] == "PASS"
    assert result["private_row_level_data_required"] is False
    assert result["model_training_executed"] is False
    assert result["new_backtest_executed"] is False


def test_clean_export_replay(exported: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(exported / "scripts/replay_v0_10_closeout.py"),
            "--root",
            str(exported),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(result.stdout)["status"] == "PASS"


def test_tamper_rejected(exported: Path) -> None:
    path = exported / PUBLIC / "baseline-metrics.csv"
    path.write_text(path.read_text().replace("FROZEN_M0", "PROMOTED_M0"))
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        verify(exported)


@pytest.mark.parametrize(
    "key",
    [
        "V0_10_ORIGINAL_S2_S4_COMPLETE",
        "V0_10_STABLE_PREDICTIVE_GAIN",
        "V0_10_PROSPECTIVE_VALIDATION",
        "V0_10_PRODUCTION_USE_APPROVED",
        "VERSION_COMPLETE",
        "V0_11_TAG_CREATE",
        "V0_11_GITHUB_RELEASE_CREATE",
        "GITHUB_RELEASE_CREATED",
    ],
)
def test_lifecycle_promotion_rejected(exported: Path, key: str) -> None:
    payload = json.loads((exported / BOUNDARY).read_text())
    payload[key] = True
    update(exported, BOUNDARY, payload)
    with pytest.raises(ValueError, match="LIFECYCLE"):
        verify(exported)


def test_v11_extraction_rejected(exported: Path) -> None:
    path = PUBLIC / "extraction-manifest.json"
    payload = json.loads((exported / path).read_text())
    row = next(r for r in payload["files"] if r["classification"] == "V0_11_ONLY")
    row["destination"] = row["source_path"]
    update(exported, path, payload)
    with pytest.raises(ValueError, match="EXCLUDED_SOURCE"):
        verify(exported)


@pytest.mark.parametrize(
    "path",
    [
        "docs/v0-11/status.md",
        "backend/app/cli.py",
        "backend/app/area_yield/m0_baseline.py",
        "configs/new-model.json",
        "scripts/replay_v0_10_v0_11_closeout.py",
    ],
)
def test_foreign_changed_file_rejected(path: str) -> None:
    with pytest.raises(ValueError, match="RELEASE_TREE"):
        verify_changed_paths([path])


def test_release_prerelease_not_formal(exported: Path) -> None:
    path = PUBLIC / "release-chain-audit.json"
    payload = json.loads((exported / path).read_text())
    next(r for r in payload["versions"] if r["tag"] == "v0.3.0-plan")["formal_chain_included"] = (
        True
    )
    update(exported, path, payload)
    with pytest.raises(ValueError, match="RELEASE_CHAIN"):
        verify(exported)


def test_unsafe_manifest_path_rejected(exported: Path) -> None:
    path = exported / PUBLIC / "public-artifact-manifest.json"
    payload = json.loads(path.read_text())
    payload["files"][0]["path"] = "../outside.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="PUBLIC_PATH"):
        verify(exported)


def test_stale_notes_do_not_negate_release() -> None:
    rows = json.loads((ROOT / PUBLIC / "release-chain-audit.json").read_text())["versions"]
    assert {r["tag"] for r in rows if r["stale_release_note_text"]} == {"v0.5.0", "v0.6.0"}
    assert all(r["github_release_exists"] and not r["release_draft"] for r in rows)


def test_no_v11_dependency_in_verifier() -> None:
    source = (ROOT / "scripts/replay_v0_10_closeout.py").read_text()
    assert "from backend" not in source
    assert "import backend" not in source
    assert "conditional_growth" not in source
