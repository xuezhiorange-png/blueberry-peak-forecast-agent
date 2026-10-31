"""Verify reviewed historical code blobs without freezing future runtime changes.

Only the explicitly authorized code/test paths below use Git. Frozen documents,
evidence, manifests and research assets always use current worktree bytes.
The fixed commit is the merged PR #716 implementation-authority snapshot. Each
adapted historical pin was independently checked against that snapshot before
adaptation; a digest mismatch never searches for another matching revision.
"""

import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath

from backend.app.core.historical_code_identity import read_code, registered

HISTORICAL_COMMIT = "320f2046e3105b1b55da9cb037892571110b584a"
ROOT = Path(__file__).resolve().parents[2]
AUTHORIZED_HISTORY_PATHS = frozenset(
    {
        "backend/app/main.py",
        "backend/app/core/config.py",
        "backend/app/models/__init__.py",
        "backend/app/api/forecast_intelligence_read.py",
        "backend/app/api/forecast_intelligence_decision.py",
        # S3's authorized mutable transport evolves; its V0.17/V0.18 historical
        # evidence still pins these independently verified PR #716 Git blobs.
        "backend/app/mcp/forecast_intelligence_http.py",
        "backend/app/mcp/forecast_intelligence_server.py",
        "pyproject.toml",
        "uv.lock",
        # S4 authorized business-flow UI replaces V0.17 technical identity entry.
        # These V0.17/18 evidence digests were independently verified against
        # this immutable PR #716 snapshot; current UI executes separate tests.
        "frontend/src/dashboard/api/client.ts",
        "frontend/src/dashboard/app/Dashboard.tsx",
        "frontend/src/dashboard/components/AuthorizedSavedRunSelector.tsx",
        "frontend/src/dashboard/context/ForecastContext.tsx",
        "frontend/src/dashboard/styles/dashboard.css",
        "frontend/src/dashboard/components/presentation.tsx",
        "frontend/src/test/selectorCancellation.test.tsx",
        "frontend/e2e/dashboard.spec.ts",
        "frontend/e2e/dashboard-cross-surface.spec.ts",
        "frontend/e2e/selector-cancel-reopen.spec.ts",
        "frontend/e2e/support/dashboard_api.py",
        "frontend/e2e/support/s6_api.py",
        *(
            "backend/tests/forecast_intelligence/" + name + ".py"
            for name in (
                "test_v0_17_s1_service_read_api",
                "test_v0_17_s2_decision_service",
                "test_v0_17_s3_read_access",
                "test_v0_17_version_closeout",
                "test_v0_18_scope_freeze",
                "test_v0_18_s1_preflight_contract",
                "test_v0_18_s1_simplified_local_auth_contract",
                "test_v0_18_s0_local_auth_scope_addendum_contract",
                "test_v0_18_roadmap_reassessment",
                "test_v0_18_s1_local_auth_implementation_contract",
            )
        ),
        "backend/tests/e2e/test_v0_17_s6_evidence_contract.py",
        "backend/tests/e2e/test_v0_17_s6_route_lifecycle_contract.py",
        "backend/tests/e2e/test_v0_17_s6_route_lifecycle_r2_contract.py",
    }
)


def validated_path(relative: str) -> str:
    path = PurePosixPath(relative)
    if (
        not relative
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in relative
        or ":" in relative
        or "\x00" in relative
        or str(path) != relative
    ):
        raise AssertionError("Invalid repository-relative historical path")
    return relative


def historical_bytes(relative: str, commit: str, *, root: Path = ROOT) -> bytes:
    validated_path(relative)
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise AssertionError("Historical commit must be a fixed full SHA")
    # Reviewed code receives additional Blob+SHA256 checks. No automatic
    # clean-graph fallback; unregistered/non-code evidence keeps its old path.
    if registered(commit, relative):
        return read_code(commit, relative, repo=root)
    exists = subprocess.run(
        ["git", "cat-file", "-e", commit + "^{commit}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if exists.returncode:
        raise AssertionError("Required historical commit unavailable")
    result = subprocess.run(
        ["git", "show", commit + ":" + relative],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError("Required historical source unavailable")
    return result.stdout


def source_bytes(relative: str | Path, *, root: Path = ROOT) -> bytes:
    relative = str(relative)
    validated_path(relative)
    if relative in AUTHORIZED_HISTORY_PATHS:
        return historical_bytes(relative, HISTORICAL_COMMIT, root=root)
    candidate = root / relative
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise AssertionError("Source path escapes repository")
    return candidate.read_bytes()


def verified_source(relative: str, expected: str, *, root: Path = ROOT) -> bytes:
    if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise AssertionError("Invalid expected SHA256")
    value = source_bytes(relative, root=root)
    if hashlib.sha256(value).hexdigest() != expected:
        raise AssertionError("Source SHA256 mismatch: " + relative)
    return value
