import subprocess
import sys
from pathlib import Path

from research.blueberry_vision.r2_common import read_json
from research.blueberry_vision.r4.cli import run_acceptance


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "research.blueberry_vision.r4.cli", *args],
        capture_output=True,
        text=True,
    )


def test_recovery_and_nullable_evaluation_cli(tmp_path: Path) -> None:
    recovered = tmp_path / "recovered"
    assert invoke("recover-predictions", "--output", str(recovered)).returncode == 0
    assert read_json(recovered / "A.json")["prediction_hash"] == (
        "60cb65963dcd555aa1b23c4fd49e178fdb4bcabb36fbd443a736a4da39200bbb"
    )
    report = tmp_path / "report.json"
    assert invoke("evaluate-frozen", "--coco", "--output", str(report)).returncode == 0
    assert read_json(report)["status"] == "NOT_EVALUABLE"
    output = tmp_path / "business"
    assert (
        invoke(
            "render-business-report", "--evaluation", str(report), "--output", str(output)
        ).returncode
        == 0
    )
    assert "NOT_EVALUABLE" in (output / "report.html").read_text()
    assert "1161" in (output / "report.md").read_text()
    assert (
        invoke(
            "render-business-report", "--evaluation", str(report), "--output", str(output)
        ).returncode
        != 0
    )


def test_r4_acceptance_cli_keeps_no_gt_distinct(tmp_path: Path) -> None:
    output = tmp_path / "acceptance"
    result = invoke("run-r4-acceptance", "--skip-tests", "--output", str(output))
    assert result.returncode == 0, result.stderr
    report = read_json(output / "acceptance.json")
    assert report["task_result"] == "PARTIAL"
    assert report["real_evaluation_complete"] is False
    assert report["qualified_gt_available"] is False
    assert report["engineering_integrity"] == "PASS"
    assert report["tests"]["status"] == "NOT_RUN_IN_THIS_COMMAND"
    assert (
        invoke("verify-artifacts", "--manifest", str(output / "artifact_manifest.json")).returncode
        == 0
    )


def test_pending_pair_cli_not_fake_human_agreement(tmp_path: Path) -> None:
    output = tmp_path / "pending.json"
    assert invoke("compare-human-drafts", "--output", str(output)).returncode == 0
    value = read_json(output)
    assert value["independent_human_reviews_completed"] == 0
    assert all(row["comparison"] is None for row in value["per_image"])


def test_acceptance_never_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "already-exists"
    output.mkdir()
    import pytest

    with pytest.raises(ValueError, match="OUTPUT_ALREADY_EXISTS"):
        run_acceptance(output, skip_tests=True)
