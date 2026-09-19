"""Fresh-process regressions for the V0.6-S3 import boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _fresh_process(code: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "module",
    (
        "backend.app.rolling_backtest.canonical",
        "backend.app.models",
        "backend.app.pit.evaluation",
        "backend.app.pit.evaluation_persistence",
    ),
)
def test_s3_import_paths_start_in_fresh_process(module: str) -> None:
    result = _fresh_process(f"import {module}")
    assert result.returncode == 0, result.stderr
    assert "partially initialized module" not in result.stderr


def test_cli_area_forecast_starts_in_fresh_process() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "backend.app.cli", "area-forecast", "--help"],
        cwd=REPOSITORY_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPOSITORY_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "partially initialized module" not in result.stderr


def test_mcp_area_forecast_imports_in_fresh_process() -> None:
    result = _fresh_process("import backend.app.mcp.area_forecast")
    assert result.returncode == 0, result.stderr
    assert "partially initialized module" not in result.stderr


def test_pit_hash_uses_unchanged_shared_canonical_semantics() -> None:
    result = _fresh_process(
        """
from datetime import UTC, datetime
from decimal import Decimal
from backend.app.pit.canonical import hash_payload
from backend.app.rolling_backtest.canonical import sha256_payload

payload = {
    'decimal': Decimal('1.2300'),
    'timestamp': datetime(2026, 9, 19, 4, 0, tzinfo=UTC),
    'nested': {'values': [Decimal('0'), 'stable']},
}
assert hash_payload(payload) == sha256_payload(payload)
print(hash_payload(payload))
"""
    )
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout.strip() == "009fef4aa845ae1cad2ee5d792e785ac0467b640080ab948fcaa3444d733e73b"
    )
