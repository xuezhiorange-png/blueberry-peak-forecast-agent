"""Offline adapter to the standalone trusted-base V2 CI runner."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.app.core import public_core_incremental_gate as gate

ROOT = Path(__file__).resolve().parents[3]


def execute(
    repo: Path,
    context: gate.Context,
    authority: gate.Authority,
    output: Path,
    *,
    trusted_executors: Path | None = None,
) -> dict[str, object]:
    verifier = (
        trusted_executors / "tools/public_core_incremental_gate.py"
        if trusted_executors
        else ROOT / "backend/app/core/public_core_incremental_gate.py"
    )
    security = (
        trusted_executors / "tests/test_public_gate_v2.py"
        if trusted_executors
        else ROOT / "public_core/td01i_v2/test_gate.py"
    )
    runner = (
        trusted_executors / "tools/run_public_ci_v2.py"
        if trusted_executors
        else ROOT / "public_core/td01i_v2/run_public_ci.py"
    )
    with tempfile.TemporaryDirectory(prefix="TD01I_EXTERNAL_REVIEW_") as directory:
        folder = Path(directory)
        folder.chmod(0o700)
        request = folder / "context.json"
        review = folder / "independent-review.json"
        request.write_bytes(gate.canonical(gate.context_payload(context)))
        raw = gate.canonical(gate.authority_payload(authority))
        review.write_bytes(raw)
        review.chmod(0o600)
        command = [
            sys.executable,
            "-I",
            "-B",
            str(runner),
            "--repository",
            str(repo),
            "--context",
            str(request),
            "--gate-script",
            str(verifier),
            "--gate-sha256",
            gate.digest(verifier.read_bytes()),
            "--security-test",
            str(security),
            "--security-test-sha256",
            gate.digest(security.read_bytes()),
            "--synthetic-review-authority",
            str(review),
            "--independent-authority-sha256",
            gate.digest(raw),
            "--output-dir",
            str(output),
            "--executor-origin-base",
            context.base if trusted_executors else "SYNTHETIC_BOOTSTRAP_HOST",
        ]
        result = subprocess.run(command, capture_output=True, check=False)
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name, data in (
            ("orchestrator.stdout.log", result.stdout),
            ("orchestrator.stderr.log", result.stderr),
        ):
            file = output / name
            file.write_bytes(data)
            file.chmod(0o600)
        if result.returncode:
            raise RuntimeError("V2_LOCAL_CI_EQUIVALENCE_FAILED")
        report: dict[str, object] = json.loads((output / "summary.json").read_bytes())
        return report
