import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.etl.history import synthetic_migration as migration

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_actual_synthetic_history_replay_and_content_hash_compatibility():
    result = migration.simulate()
    assert result["data_class"] == "SYNTHETIC_ONLY"
    assert result["old_main_tree_has_private_path"] is False
    assert result["old_history_reaches_private_blob"] is True
    assert result["clean_repository_has_private_blob"] is False
    assert result["old_commit_locator_resolves_in_clean"] is False
    assert result["wrong_mapping_rejected"] is True
    assert result["real_repository_history_rewritten"] is False
    assert len(result["commit_mapping"]) == 3
    assert len(result["tag_mapping"]) == 2
    assert all(row["old_commit"] != row["new_commit"] for row in result["commit_mapping"])
    assert all(row["content_sha256_unchanged"] for row in result["commit_mapping"])
    assert result["commit_mapping"][-1]["old_tree"] == result["commit_mapping"][-1]["new_tree"]


def test_real_or_external_repository_cannot_be_a_simulation_target(tmp_path, monkeypatch):
    def no_command(*args, **kwargs):
        raise AssertionError("no Git command before ownership admission")

    monkeypatch.setattr(migration.subprocess, "run", no_command)
    with pytest.raises(ValueError, match="SYNTHETIC_REPOSITORY_REQUIRED"):
        migration.require_owned(tmp_path / "other", tmp_path / "owned")


def test_independent_process_migration_results_are_deterministic():
    cmd = [sys.executable, "-m", "backend.app.etl.history.synthetic_migration"]
    results = [subprocess.check_output(cmd) for _ in range(2)]
    assert results[0] == results[1]
    assert json.loads(results[0])["correct_mapping_verified"] is True


def test_mapping_cannot_replace_the_independent_original_expected_hash():
    original = b"SYNTHETIC_ONLY_ORIGINAL_CODE"
    replacement = b"SYNTHETIC_ONLY_DIFFERENT_CODE"
    pin = hashlib.sha256(original).hexdigest()
    migration.verify_code_binding(original, pin, pin)
    with pytest.raises(ValueError, match="ORIGINAL_CODE_HASH_MISMATCH"):
        migration.verify_code_binding(replacement, pin, hashlib.sha256(replacement).hexdigest())


def test_committed_rehearsal_is_actual_deterministic_computation():
    file = (
        Path(__file__).resolve().parents[3] / "docs/tech-debt/td01c-synthetic-migration-result.json"
    )
    assert json.loads(file.read_text()) == migration.simulate()
