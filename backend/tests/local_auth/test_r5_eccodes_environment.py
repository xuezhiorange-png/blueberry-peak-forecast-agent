"""Native synthetic GRIB acceptance; no external weather or harvest data."""

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import sysconfig
import tomllib
from pathlib import Path

import eccodes
import numpy as np

from backend.tests.historical_source import historical_bytes

ROOT = Path(__file__).resolve().parents[3]
PREVIOUS = "cdcbf70339dd98b65d5c40f2cad8d08d2ed36872"


def test_r5_installed_versions_and_unrelated_lock_versions():
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    previous = tomllib.loads(historical_bytes("uv.lock", PREVIOUS).decode())
    current = {p["name"]: p["version"] for p in lock["package"]}
    original = {p["name"]: p["version"] for p in previous["package"]}
    assert all(current[name] == version for name, version in original.items())
    assert set(current) - set(original) == {"eccodeslib", "eckitlib"}
    for name, version in {
        "eccodes": "2.48.0",
        "anyio": "4.14.2",
        "pyjwt": "2.15.0",
        "mcp": "2.2.0",
    }.items():
        assert current[name] == importlib.metadata.version(name) == version
    if platform.system() in {"Linux", "Darwin"}:
        assert importlib.metadata.version("eccodeslib") == "2.48.0.26"
        assert importlib.metadata.version("eckitlib") == "2.1.1.26"
        assert "eckitlib==2.1.1.26" in importlib.metadata.requires("eccodeslib")


def test_r5_complete_installed_environment_is_consistent():
    result = subprocess.run(
        [sys.executable, "-m", "pip", "check"], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No broken requirements found" in result.stdout


def test_r5_selfcheck_uses_bundled_library_without_private_loader_paths():
    environment = dict(os.environ)
    for key in (
        "ECCODES_DIR",
        "ECCODES_LIB_DIR",
        "ECCODES_DEFINITION_PATH",
        "ECCODES_SAMPLES_PATH",
        "ECCODES_PYTHON_USE_FINDLIBS",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
    ):
        environment.pop(key, None)
    result = subprocess.run(
        [sys.executable, "-m", "eccodes", "selfcheck"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ecCodes v2.48.0" in result.stdout
    assert "Your system is ready" in result.stdout
    if platform.system() in {"Linux", "Darwin"}:
        library = next(line for line in result.stdout.splitlines() if line.startswith("Library:"))
        path = Path(library.split(":", 1)[1].strip()).resolve()
        assert path.is_relative_to(Path(sysconfig.get_path("purelib")).resolve())
        assert "eccodeslib" in path.parts
        assert path.is_file()


def synthetic_grib():
    handle = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        eccodes.codes_set(handle, "dataDate", 20260101)
        eccodes.codes_set(handle, "dataTime", 0)
        count = eccodes.codes_get(handle, "numberOfPoints")
        eccodes.codes_set_values(handle, np.full(count, 273.15))
        return eccodes.codes_get_message(handle)
    finally:
        eccodes.codes_release(handle)


def test_r5_evidence_preserves_r4_snapshot_and_frozen_history():
    path = ROOT / "docs/v0-18/s1/eccodes-environment-consistency-r5.json"
    raw = path.read_bytes()
    value = json.loads(raw)
    assert raw == (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    assert value["previous_head_sha"] == PREVIOUS
    original = historical_bytes("docs/v0-18/s1/local-auth-runtime-r1.json", PREVIOUS)
    assert hashlib.sha256(original).hexdigest() == value["previous_r4_evidence_sha256"]
    old = json.loads(original)
    current = json.loads((ROOT / "docs/v0-18/s1/local-auth-runtime-r1.json").read_bytes())
    assert old["frozen_history_sha256"] == current["frozen_history_sha256"]
    assert len(current["frozen_history_sha256"]) == 260
    assert old["security_acceptance"] == current["security_acceptance"]
    assert old["r4_correction"] == current["r4_correction"]
    for relative, digest in value["source_evidence_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    for relative, digest in current["frozen_history_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    assert all(enabled is False for enabled in value["prohibited_actions"].values())
    assert value["real_admin_and_org_authority"] == "PENDING"
    audit = json.loads((ROOT / "docs/v0-18/s1/r5-dependency-audit.json").read_bytes())
    assert not any(item.get("vulns") for item in audit["dependencies"])
    native = {
        item["name"]
        for item in audit["dependencies"]
        if item["name"] in {"eccodes", "eccodeslib", "eckitlib"}
    }
    assert native == {"eccodes", "eccodeslib", "eckitlib"}


def test_r5_real_synthetic_grib2_roundtrip_is_deterministic():
    first, second = synthetic_grib(), synthetic_grib()
    assert first == second
    assert first.startswith(b"GRIB") and first.endswith(b"7777")
    assert first[7] == 2
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    handle = eccodes.codes_new_from_message(first)
    try:
        assert eccodes.codes_get(handle, "edition") == 2
        assert eccodes.codes_get(handle, "dataDate") == 20260101
        assert eccodes.codes_get(handle, "gridType") == "regular_ll"
        assert eccodes.codes_get(handle, "Ni") > 0
        assert eccodes.codes_get(handle, "Nj") > 0
        values = eccodes.codes_get_values(handle)
        assert len(values) == eccodes.codes_get(handle, "numberOfPoints")
        np.testing.assert_allclose(values, 273.15, atol=0.0001, rtol=0)
    finally:
        eccodes.codes_release(handle)
