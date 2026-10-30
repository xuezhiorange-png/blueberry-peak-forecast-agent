"""TD-03D dependency receipts and an explicitly invoked disposable Docker probe."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
import tempfile
import tomllib
from contextlib import redirect_stdout
from pathlib import Path
from uuid import uuid4


def dependency_report(root: Path, *, enforce: bool = False, native: bool = False) -> dict:
    # packaging is already installed by the project's existing dependencies.
    # The host-side Docker probe itself only needs the standard library.
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    requirements = project["dependencies"] + project["optional-dependencies"]["dev"]
    versions = {}
    for text in requirements:
        requirement = Requirement(text)
        if requirement.marker is None or requirement.marker.evaluate({"extra": "dev"}):
            version = importlib.metadata.version(requirement.name)
            if version not in requirement.specifier:
                raise ValueError(f"PROJECT_REQUIREMENT_MISMATCH: {requirement.name}")
            versions[canonicalize_name(requirement.name)] = version
    pinned = {}
    mismatches = {}
    for line in (root / "backend/constraints-ci.txt").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        name = canonicalize_name(requirement.name)
        installed = importlib.metadata.version(name)
        pinned[name] = installed
        if installed not in requirement.specifier:
            mismatches[name] = {"installed": installed, "required": str(requirement.specifier)}
    if enforce and mismatches:
        raise ValueError(
            f"DEPENDENCY_CONSTRAINT_MISMATCH: {json.dumps(mismatches, sort_keys=True)}"
        )
    if enforce and sys.version_info[:2] != (3, 12):
        raise ValueError("PYTHON_VERSION_MISMATCH")
    imports = []
    if native:
        for module in (
            "fastapi",
            "sqlalchemy",
            "asyncpg",
            "aiosqlite",
            "eccodes",
            "sklearn",
            "lightgbm",
            "catboost",
        ):
            with redirect_stdout(sys.stderr):
                importlib.import_module(module)
            imports.append(module)
    return {
        "python": platform.python_version(),
        "platform": sys.platform,
        "direct_versions": dict(sorted(versions.items())),
        "constraint_versions": dict(sorted(pinned.items())),
        "constraint_mismatches": mismatches,
        "direct_without_ci_constraint": sorted(versions.keys() - pinned.keys()),
        "native_imports": imports,
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("pyproject.toml", "backend/constraints-ci.txt", "uv.lock")
        },
        "full_transitive_lock_claimed": False,
    }


def _output(command: list[str]) -> str:
    return subprocess.check_output(command, text=True).strip()


def isolated_override(identity: str) -> dict:
    if re.fullmatch(r"blueberry_td03d_[0-9a-f]{12}", identity) is None:
        raise ValueError("UNSAFE_RESOURCE_IDENTITY")
    return {
        "services": {"postgres-test": {"container_name": identity}},
        "volumes": {"postgres_test_data_v16": {"name": identity + "_data"}},
        "networks": {"blueberry_test_net": {"name": identity + "_net"}},
    }


def validate_rendered_profile(config: dict, identity: str) -> None:
    isolated_override(identity)
    if set(config["services"]) != {"postgres-test"}:
        raise ValueError("UNEXPECTED_DATABASE_SERVICE")
    service = config["services"]["postgres-test"]
    if (
        service["image"] != "postgres:16-alpine"
        or service["container_name"] != identity
        or service["environment"]["POSTGRES_DB"] != "blueberry_peak_test"
        or service["environment"]["APP_ENV"] != "test"
    ):
        raise ValueError("UNSAFE_TEST_DATABASE_PROFILE")
    if [(int(p["target"]), str(p["published"])) for p in service["ports"]] != [(5432, "55432")]:
        raise ValueError("UNSAFE_TEST_DATABASE_PORT")
    mounts = service["volumes"]
    if len(mounts) != 1 or any(
        mounts[0].get(key) != value
        for key, value in {
            "type": "volume",
            "source": "postgres_test_data_v16",
            "target": "/var/lib/postgresql/data",
        }.items()
    ):
        raise ValueError("UNSAFE_TEST_DATABASE_MOUNT")
    if config["volumes"]["postgres_test_data_v16"]["name"] != identity + "_data":
        raise ValueError("UNSAFE_TEST_DATABASE_VOLUME")
    if config["networks"]["blueberry_test_net"]["name"] != identity + "_net":
        raise ValueError("UNSAFE_TEST_DATABASE_NETWORK")
    if set(service["networks"]) != {"blueberry_test_net"}:
        raise ValueError("UNSAFE_TEST_DATABASE_NETWORK_ATTACHMENT")


def docker_smoke(root: Path, report_dir: Path) -> dict:
    identity = "blueberry_td03d_" + uuid4().hex[:12]
    image = "blueberry-td03d:" + identity
    before = set(_output(["docker", "volume", "ls", "--format", "{{.Name}}"]).splitlines())
    if identity + "_data" in before:
        raise ValueError("OWNED_VOLUME_ALREADY_EXISTS")
    if image in _output(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"]):
        raise ValueError("OWNED_IMAGE_ALREADY_EXISTS")
    for args, name in (
        (["network", "ls", "--format", "{{.Name}}"], identity + "_net"),
        (["ps", "-a", "--format", "{{.Names}}"], identity),
    ):
        if name in _output(["docker", *args]).splitlines():
            raise ValueError("OWNED_RESOURCE_ALREADY_EXISTS")
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {"identity": identity, "preexisting_volumes": sorted(before)}
    with tempfile.TemporaryDirectory(prefix="td03d-") as temporary:
        override = Path(temporary) / "override.json"
        override.write_text(json.dumps(isolated_override(identity)))
        compose = [
            "docker",
            "compose",
            "-p",
            identity,
            "-f",
            str(root / "docker-compose.test.yml"),
            "-f",
            str(override),
        ]
        config = json.loads(_output([*compose, "config", "--format", "json"]))
        validate_rendered_profile(config, identity)
        started = False
        image_built = False
        try:
            subprocess.run(
                ["docker", "build", "-f", str(root / "backend/Dockerfile"), "-t", image, str(root)],
                check=True,
            )
            image_built = True
            # No app server, production environment, database URL or label access.
            runtime = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "-v",
                f"{Path(__file__).resolve()}:/td03d.py:ro",
                image,
            ]
            dependencies = json.loads(
                _output(
                    [
                        *runtime,
                        "python",
                        "/td03d.py",
                        "dependencies",
                        "--root",
                        "/app",
                        "--enforce",
                        "--native",
                    ]
                )
            )
            report["docker_dependencies"] = dependencies
            subprocess.run([*runtime, "python", "-m", "pip", "check"], check=True)
            started = True
            subprocess.run([*compose, "up", "-d", "--wait", "--wait-timeout", "90"], check=True)
            inspect = json.loads(_output(["docker", "inspect", identity]))[0]
            if {mount["Name"] for mount in inspect["Mounts"]} != {identity + "_data"}:
                raise ValueError("DATABASE_MOUNT_IDENTITY_MISMATCH")
            ports = inspect["NetworkSettings"]["Ports"]["5432/tcp"]
            if {p["HostPort"] for p in ports} != {"55432"}:
                raise ValueError("DATABASE_PUBLISHED_PORT_MISMATCH")
            psql = [
                *compose,
                "exec",
                "-T",
                "postgres-test",
                "psql",
                "-X",
                "-q",
                "-t",
                "-A",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "-d",
                "blueberry_peak_test",
            ]
            actual = _output(
                [
                    *psql,
                    "-c",
                    "SELECT current_database() || '|' || current_user || '|' || "
                    "current_setting('server_version_num')",
                ]
            )
            db, user, version = actual.split("|")
            if (
                db != "blueberry_peak_test"
                or user != "postgres"
                or not 160000 <= int(version) < 170000
            ):
                raise ValueError("POSTGRES_SERVER_IDENTITY_MISMATCH")
            quantity = _output(
                [
                    *psql,
                    "-c",
                    "CREATE TEMP TABLE td03d_synthetic(value numeric(20,6)); "
                    "INSERT INTO td03d_synthetic VALUES (1.000000), (2.000000); "
                    "SELECT sum(value) FROM td03d_synthetic;",
                ]
            )
            if quantity != "3.000000":
                raise ValueError("POSTGRES_SYNTHETIC_ROUNDTRIP_MISMATCH")
            report["postgres"] = {
                "server_version_num": int(version),
                "database": db,
                "published_port": 55432,
                "synthetic_sum": quantity,
                "volume": identity + "_data",
            }
        finally:
            try:
                if started:
                    subprocess.run([*compose, "down", "-v"], check=True)
            finally:
                if image_built:
                    subprocess.run(["docker", "image", "rm", "--no-prune", image], check=True)
        after = set(_output(["docker", "volume", "ls", "--format", "{{.Name}}"]).splitlines())
        if before != after:
            raise ValueError("VOLUME_INVENTORY_CHANGED_AFTER_CLEANUP")
        if identity in _output(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines():
            raise ValueError("OWNED_DATABASE_CONTAINER_NOT_REMOVED")
        if (
            identity + "_net"
            in _output(["docker", "network", "ls", "--format", "{{.Name}}"]).splitlines()
        ):
            raise ValueError("OWNED_DATABASE_NETWORK_NOT_REMOVED")
        report["preexisting_volumes_unchanged"] = True
        report["owned_resources_removed"] = True
        (report_dir / "docker-postgres.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("dependencies", "docker"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    if args.mode == "dependencies":
        result = dependency_report(args.root, enforce=args.enforce, native=args.native)
    else:
        if args.report_dir is None:
            parser.error("docker mode requires --report-dir")
        result = docker_smoke(args.root.resolve(), args.report_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
