"""Prevent the PR-green/main-red exhaustive-validation gap from returning."""

from pathlib import Path

import pytest
import yaml


@pytest.mark.unit
def test_full_suite_canary_runs_on_pr_and_main_with_identical_steps() -> None:
    workflow = yaml.load(Path(".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    assert "pull_request" in workflow["on"]
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert not workflow["on"]["pull_request"]  # No path filter or event subtype exclusion.
    job = workflow["jobs"]["full-suite-canary"]
    assert "if" not in job
    assert job["services"]["postgres"]["image"] == "postgres:16"
    steps = {step.get("name", step.get("uses")): step for step in job["steps"]}
    for name in (
        "Install dependencies",
        "Create isolated test database",
        "Validate isolated PostgreSQL test identity",
        "Alembic upgrade head",
        "Full pytest suite",
    ):
        assert "if" not in steps[name]
    assert '-c backend/constraints-ci.txt -e ".[dev]"' in steps["Install dependencies"]["run"]
    assert steps["Alembic upgrade head"]["run"] == "alembic -c backend/alembic.ini upgrade head"
    command = steps["Full pytest suite"]["run"]
    assert "pytest -q --tb=long" in command
    assert "--durations=30" in command
    assert "--junitxml=reports/test-results/full.xml" in command
    assert steps["Full pytest suite"]["env"]["RUN_POSTGRES_INTEGRATION"] == "1"
    assert steps["Full pytest suite"]["env"]["APP_ENV"] == "test"


@pytest.mark.unit
def test_canary_manifest_includes_premerge_exhaustive_coverage() -> None:
    manifest = yaml.safe_load(Path("ci-shard-manifest.yml").read_text())
    canary = next(row for row in manifest["shards"] if row["job"] == "full-suite-canary")
    assert set(canary["event"]) == {"pull_request", "push", "schedule", "workflow_dispatch"}
    assert canary["pytest_args"] == [
        "-q",
        "--tb=long",
        "--durations=30",
        "--junitxml=reports/test-results/full.xml",
    ]
