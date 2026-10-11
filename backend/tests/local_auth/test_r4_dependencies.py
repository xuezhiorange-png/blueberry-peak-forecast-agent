"""Current installed security pins, not a historical snapshot of dependencies."""

import base64
import hashlib
import importlib.metadata
import json
import sys
import tomllib
from pathlib import Path

import anyio
import jwt
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "package,version", [("anyio", "4.14.2"), ("PyJWT", "2.15.0"), ("mcp", "2.2.0")]
)
def test_r4_installed_versions_match_lock_and_ci_constraints(package, version):
    assert importlib.metadata.version(package) == version
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    assert next(p["version"] for p in lock["package"] if p["name"] == package.lower()) == version
    constraints = (ROOT / "backend/constraints-ci.txt").read_text().splitlines()
    assert f"{package}=={version}" in constraints
    assert sys.version_info >= (3, 12)


def test_r4_pyjwt_deep_payload_is_a_safe_decode_error():
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(b"[" * 20000 + b"]" * 20000).rstrip(b"=")
    token = (header + b"." + payload + b".Zm9yZ2Vk").decode()
    with pytest.raises(jwt.DecodeError):
        jwt.decode(token, options={"verify_signature": False})


async def test_r4_anyio_cancellation_isolated_and_next_request_recovers():
    entered = anyio.Event()
    completed = []

    async def request_a():
        entered.set()
        await anyio.sleep_forever()
        completed.append("a")

    async with anyio.create_task_group() as group:
        group.start_soon(request_a)
        await entered.wait()
        group.cancel_scope.cancel()
    await anyio.to_thread.run_sync(lambda: completed.append("b"))
    assert completed == ["b"]


def test_r4_public_audit_snapshot_covers_installed_target_packages():
    path = ROOT / "backend/tests/local_auth/fixtures/r4-dependency-audit.json"
    audit = json.loads(path.read_bytes())
    evidence = json.loads((ROOT / "docs/v0-18/s1/local-auth-runtime-r1.json").read_bytes())
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == evidence["r4_correction"]["dependency_audit_sha256"]
    )
    assert not [p for p in audit["dependencies"] if p.get("vulns")]
    targets = {
        p["name"]: p for p in audit["dependencies"] if p["name"] in {"anyio", "pyjwt", "mcp"}
    }
    assert set(targets) == {"anyio", "pyjwt", "mcp"}
    for name, result in targets.items():
        assert result["version"] == importlib.metadata.version(name)
        assert result["vulns"] == []
