"""Keep application/research type checks in the existing fail-closed static job."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]


def _workflow():
    return yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)


def _mypy_step(workflow):
    job = workflow["jobs"]["static"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert job.get("continue-on-error", "false") == "false"
    steps = [step for step in job["steps"] if step.get("name") == "Mypy"]
    assert len(steps) == 1
    step = steps[0]
    assert step.get("continue-on-error", "false") == "false"
    assert "if" not in step
    assert shlex.split(step["run"]) == ["mypy", "backend/app", "backend/research"]
    for value in (workflow, job, step):
        assert value.get("defaults", {}).get("run", {}).get("shell", "bash") == "bash"
    assert step.get("shell", "bash") == "bash"
    return step


def test_static_checks_both_directories_with_existing_strict_configuration() -> None:
    _mypy_step(_workflow())
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["mypy"]
    assert config["strict"] is True
    assert config["python_version"] == "3.12"
    assert not config.get("ignore_errors", False)
    assert not config.get("exclude", [])


@pytest.mark.parametrize("removed", ("backend/app", "backend/research"))
def test_removing_either_directory_fails_the_scope_contract(removed: str) -> None:
    workflow = _workflow()
    step = _mypy_step(workflow)
    step["run"] = shlex.join(token for token in shlex.split(step["run"]) if token != removed)
    with pytest.raises(AssertionError):
        _mypy_step(workflow)


@pytest.mark.parametrize("level", ("job", "step"))
def test_continue_on_error_cannot_hide_mypy_failure(level: str) -> None:
    workflow = _workflow()
    step = _mypy_step(workflow)
    target = workflow["jobs"]["static"] if level == "job" else step
    target["continue-on-error"] = "true"
    with pytest.raises(AssertionError):
        _mypy_step(workflow)


@pytest.mark.parametrize("bypass", ("conditional", "job_condition", "masked_exit"))
def test_skipping_or_masking_the_type_check_is_rejected(bypass: str) -> None:
    workflow = _workflow()
    step = _mypy_step(workflow)
    if bypass == "conditional":
        step["if"] = "false"
    elif bypass == "job_condition":
        workflow["jobs"]["static"]["if"] = "false"
    else:
        step["run"] += " || true"
    with pytest.raises(AssertionError):
        _mypy_step(workflow)


@pytest.mark.parametrize("invalid_research", (False, True))
def test_real_ci_command_propagates_a_synthetic_research_type_error(
    tmp_path: Path, invalid_research: bool
) -> None:
    # Only new synthetic Python files are checked; no application/research files
    # are edited, imported as business code, or executed as a prediction model.
    for folder in ("backend", "backend/app", "backend/research"):
        path = tmp_path / folder
        path.mkdir(exist_ok=True)
        (path / "__init__.py").write_text("")
    (tmp_path / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
    (tmp_path / "backend/app/synthetic.py").write_text("value: int = 1\n")
    value = "'not-an-int'" if invalid_research else "1"
    (tmp_path / "backend/research/synthetic.py").write_text(f"value: int = {value}\n")
    result = subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-e",
            "-o",
            "pipefail",
            "-c",
            _mypy_step(_workflow())["run"],
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
            "MYPY_CACHE_DIR": str(tmp_path / "mypy-cache"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (1 if invalid_research else 0), result.stdout + result.stderr
    if invalid_research:
        assert "backend/research/synthetic.py:1: error:" in result.stdout
        assert "[assignment]" in result.stdout
    else:
        assert "Success: no issues found" in result.stdout
