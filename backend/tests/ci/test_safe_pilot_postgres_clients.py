"""Canary must provision the client major used by its PostgreSQL test service."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
STEP = "Install matching PostgreSQL 16 test clients"


def check_client_dependency(workflow):
    steps = workflow["jobs"]["full-suite-canary"]["steps"]
    found = [s for s in steps if s.get("name") == STEP]
    assert len(found) == 1
    step = found[0]
    assert steps.index(step) < next(
        i for i, s in enumerate(steps) if s.get("name") == "Full pytest suite"
    )
    assert not step.get("continue-on-error", False)
    script = step["run"]
    assert "apt-get install -y --no-install-recommends postgresql-client-16" in script
    assert "/usr/lib/postgresql/16/bin/pg_dump --version" in script
    assert "/usr/lib/postgresql/16/bin/pg_restore --version" in script
    assert "|| true" not in script


def test_canary_explicitly_provisions_matching_client_dependency():
    check_client_dependency(yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text()))


@pytest.mark.parametrize("mutation", ["missing", "wrong_major", "ignored_failure"])
def test_dependency_contract_rejects_missing_or_unchecked_clients(mutation):
    workflow = deepcopy(yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text()))
    steps = workflow["jobs"]["full-suite-canary"]["steps"]
    step = next(s for s in steps if s.get("name") == STEP)
    if mutation == "missing":
        steps.remove(step)
    elif mutation == "wrong_major":
        step["run"] = step["run"].replace("postgresql-client-16", "postgresql-client-18")
    else:
        step["continue-on-error"] = True
    with pytest.raises(AssertionError):
        check_client_dependency(workflow)
