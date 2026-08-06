from __future__ import annotations

import subprocess

import pytest


def test_emit_batch_a_ruff_format_diff() -> None:
    result = subprocess.run(
        [
            "ruff",
            "format",
            "--diff",
            "backend/app/actual_harvest_import/batch_a_contracts.py",
            "backend/app/actual_harvest_import/schemas.py",
            "backend/tests/actual_harvest_import/test_batch_a_synthetic_contracts.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    pytest.fail(
        f"ruff format diagnostic returncode={result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
