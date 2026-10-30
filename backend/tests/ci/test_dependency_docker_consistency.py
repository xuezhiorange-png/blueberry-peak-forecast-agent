"""TD-03D environment contracts; these tests never open a business database."""

from __future__ import annotations

import copy
import importlib.metadata
import json
import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scripts.ci import check_environment_consistency as environment

ROOT = Path(__file__).resolve().parents[3]


def _compose(name: str):
    return yaml.load((ROOT / name).read_text(), Loader=yaml.BaseLoader)


def _docker_install(dockerfile: str) -> None:
    assert dockerfile.splitlines()[0] == "FROM python:3.12-slim"
    lines = dockerfile.replace("\\\n", " ").splitlines()
    installs = [line for line in lines if line.startswith("RUN ") and '".[dev]"' in line]
    assert len(installs) == 1
    tokens = shlex.split(installs[0])
    assert tokens[tokens.index("-c") + 1] == "backend/constraints-ci.txt"
    assert tokens[-1] == ".[dev]"
    assert dockerfile.index("COPY backend ./backend") < dockerfile.index(installs[0][:7])


def _test_profile(config) -> None:
    service = config["services"]["postgres-test"]
    assert service["image"] == "postgres:16-alpine"
    assert service["ports"] == ["55432:5432"]
    assert service["environment"]["POSTGRES_DB"] == "blueberry_peak_test"
    assert service["environment"]["APP_ENV"] == "test"
    assert service["volumes"] == ["postgres_test_data_v16:/var/lib/postgresql/data"]
    assert config["volumes"] == {
        "postgres_test_data_v16": {"name": "blueberry_postgres_test_data_v16", "driver": "local"}
    }
    assert service["networks"] == ["blueberry_test_net"]
    assert "blueberry_peak_test" in service["healthcheck"]["test"][-1]


def test_docker_installs_with_the_existing_ci_constraints() -> None:
    _docker_install((ROOT / "backend/Dockerfile").read_text())


def test_test_profile_uses_postgres16_and_a_new_volume_without_changing_dev() -> None:
    _test_profile(_compose("docker-compose.test.yml"))
    dev = _compose("docker-compose.yml")
    assert dev["services"]["db"]["image"] == "postgres:16"
    assert dev["services"]["db"]["ports"] == ["5432:5432"]
    assert dev["services"]["db"]["volumes"] == ["postgres-data:/var/lib/postgresql/data"]


@pytest.mark.parametrize("constraint", ("", "-c wrong-constraints.txt"))
def test_docker_constraint_drift_is_detected(constraint: str) -> None:
    dockerfile = (ROOT / "backend/Dockerfile").read_text()
    dockerfile = dockerfile.replace("-c backend/constraints-ci.txt", constraint)
    with pytest.raises((AssertionError, ValueError)):
        _docker_install(dockerfile)


@pytest.mark.parametrize("drift", ("postgres15", "dev_port", "dev_database", "old_volume"))
def test_database_drift_and_old_volume_reuse_are_rejected(drift: str) -> None:
    config = copy.deepcopy(_compose("docker-compose.test.yml"))
    service = config["services"]["postgres-test"]
    if drift == "postgres15":
        service["image"] = "postgres:15-alpine"
    elif drift == "dev_port":
        service["ports"] = ["5432:5432"]
    elif drift == "dev_database":
        service["environment"]["POSTGRES_DB"] = "blueberry_peak"
    else:
        service["volumes"] = ["postgres_test_data:/var/lib/postgresql/data"]
    with pytest.raises(AssertionError):
        _test_profile(config)


def test_actual_installed_ci_dependencies_match_without_importing_models(monkeypatch) -> None:
    def no_import(_name: str) -> None:
        raise AssertionError("metadata must not import models")

    monkeypatch.setattr(environment.importlib, "import_module", no_import)
    report = environment.dependency_report(ROOT, enforce=True)
    assert report["constraint_mismatches"] == {}
    assert report["native_imports"] == []
    assert report["direct_without_ci_constraint"] == ["argon2-cffi", "certifi"]
    assert report["full_transitive_lock_claimed"] is False


def test_installed_constraint_drift_fails_closed(monkeypatch) -> None:
    actual = importlib.metadata.version
    monkeypatch.setattr(
        importlib.metadata, "version", lambda name: "1.18.4" if name == "alembic" else actual(name)
    )
    with pytest.raises(ValueError, match="DEPENDENCY_CONSTRAINT_MISMATCH"):
        environment.dependency_report(ROOT, enforce=True)


def _rendered(identity: str):
    return {
        "services": {
            "postgres-test": {
                "image": "postgres:16-alpine",
                "container_name": identity,
                "environment": {"POSTGRES_DB": "blueberry_peak_test", "APP_ENV": "test"},
                "ports": [{"target": 5432, "published": "55432"}],
                "volumes": [
                    {
                        "type": "volume",
                        "source": "postgres_test_data_v16",
                        "target": "/var/lib/postgresql/data",
                    }
                ],
                "networks": {"blueberry_test_net": None},
            }
        },
        "volumes": {"postgres_test_data_v16": {"name": identity + "_data"}},
        "networks": {"blueberry_test_net": {"name": identity + "_net"}},
    }


def test_runtime_override_preserves_profile_and_only_names_new_resources() -> None:
    identity = "blueberry_td03d_0123456789ab"
    override = environment.isolated_override(identity)
    assert "image" not in override["services"]["postgres-test"]
    assert "ports" not in override["services"]["postgres-test"]
    assert override["volumes"]["postgres_test_data_v16"]["name"] == identity + "_data"
    environment.validate_rendered_profile(_rendered(identity), identity)


@pytest.mark.parametrize("identity", ("blueberry", "blueberry_postgres_test_data", "../unsafe", ""))
def test_nonowned_resource_identity_is_rejected(identity: str) -> None:
    with pytest.raises(ValueError, match="UNSAFE_RESOURCE_IDENTITY"):
        environment.isolated_override(identity)


@pytest.mark.parametrize("drift", ("volume", "port", "database", "network", "dev_service"))
def test_rendered_profile_is_checked_before_any_resource_creation(drift: str) -> None:
    identity = "blueberry_td03d_0123456789ab"
    config = _rendered(identity)
    service = config["services"]["postgres-test"]
    if drift == "volume":
        config["volumes"]["postgres_test_data_v16"]["name"] = "blueberry_postgres_test_data"
    elif drift == "port":
        service["ports"][0]["published"] = "5432"
    elif drift == "database":
        service["environment"]["POSTGRES_DB"] = "blueberry_peak"
    elif drift == "network":
        config["networks"]["blueberry_test_net"]["name"] = "default"
    else:
        config["services"]["db"] = {}
    with pytest.raises(ValueError):
        environment.validate_rendered_profile(config, identity)


def test_real_docker_probe_remains_required_in_the_existing_compose_job() -> None:
    workflow = _compose(".github/workflows/ci.yml")
    job = workflow["jobs"]["compose-smoke"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert job.get("continue-on-error", "false") == "false"
    steps = {step.get("name"): step for step in job["steps"]}
    step = steps["Build constrained backend and verify disposable PostgreSQL 16"]
    assert "if" not in step
    assert step.get("continue-on-error", "false") == "false"
    assert shlex.split(step["run"].replace("\\\n", " ")) == [
        "python",
        "scripts/ci/check_environment_consistency.py",
        "docker",
        "--root",
        ".",
        "--report-dir",
        "reports/environment",
    ]
    assert steps["Stop Docker Compose"]["if"] == "always()"
    assert steps["Start PostgreSQL with Docker Compose"]["run"] == "docker compose up -d db"
    assert steps["Upload environment consistency receipt"]["with"]["if-no-files-found"] == "error"


def test_preexisting_volume_is_never_reused_or_removed(monkeypatch, tmp_path: Path) -> None:
    identity = "blueberry_td03d_0123456789ab"
    monkeypatch.setattr(environment, "uuid4", lambda: SimpleNamespace(hex="0123456789ab"))
    monkeypatch.setattr(environment, "_output", lambda _command: identity + "_data")

    def no_mutation(*_args, **_kwargs):
        raise AssertionError("preexisting volume must be rejected before any mutation")

    monkeypatch.setattr(environment.subprocess, "run", no_mutation)
    with pytest.raises(ValueError, match="OWNED_VOLUME_ALREADY_EXISTS"):
        environment.docker_smoke(ROOT, tmp_path)


def test_query_failure_cleans_only_the_new_owned_resources(monkeypatch, tmp_path: Path) -> None:
    identity = "blueberry_td03d_0123456789ab"
    monkeypatch.setattr(environment, "uuid4", lambda: SimpleNamespace(hex="0123456789ab"))
    mutations = []

    def run(command, **_kwargs):
        mutations.append(command)
        return subprocess.CompletedProcess(command, 0)

    def output(command):
        if "config" in command:
            return json.dumps(_rendered(identity))
        if command[:2] == ["docker", "inspect"]:
            return json.dumps(
                [
                    {
                        "Mounts": [{"Name": identity + "_data"}],
                        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostPort": "55432"}]}},
                    }
                ]
            )
        if "psql" in command:
            raise RuntimeError("SYNTHETIC_QUERY_FAILURE")
        if "/td03d.py" in command:
            return "{}"
        return "preexisting_unrelated_volume"

    monkeypatch.setattr(environment.subprocess, "run", run)
    monkeypatch.setattr(environment, "_output", output)
    with pytest.raises(RuntimeError, match="SYNTHETIC_QUERY_FAILURE"):
        environment.docker_smoke(ROOT, tmp_path)
    assert mutations[-2][-2:] == ["down", "-v"]
    assert mutations[-2][3] == identity
    assert mutations[-1] == ["docker", "image", "rm", "--no-prune", "blueberry-td03d:" + identity]
