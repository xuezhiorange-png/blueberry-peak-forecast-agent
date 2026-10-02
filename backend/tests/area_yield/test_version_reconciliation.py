"""Public-only lifecycle acceptance and hostile evidence checks."""

import json
import shutil
from pathlib import Path

import pytest

from scripts.replay_v0_10_v0_11_closeout import verify

ROOT = Path(__file__).resolve().parents[3]


def test_public_closeout_replay() -> None:
    result = verify(ROOT)
    assert result["status"] == "PASS"
    assert result["historical_training_reproduced"] is False


def test_tampered_public_evidence_rejected(tmp_path: Path) -> None:
    shutil.copytree(
        ROOT / "artifacts/version-reconciliation", tmp_path / "artifacts/version-reconciliation"
    )
    manifest = json.loads(
        (ROOT / "artifacts/version-reconciliation/public-artifact-manifest.json").read_text()
    )
    for item in manifest["files"]:
        destination = tmp_path / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / item["path"], destination)
    target = tmp_path / "artifacts/version-reconciliation/baseline-metrics.csv"
    target.write_text(target.read_text().replace("FROZEN_M0", "PROMOTED_M0"))
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        verify(tmp_path)
