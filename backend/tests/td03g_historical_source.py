"""Exact pre-TD03G code and transitive test pins; all documents stay live."""

import hashlib
import subprocess
import sys
import types
from pathlib import Path

from backend.tests.historical_source import historical_bytes

BASE = "0124371b433d1b3c34e5e59a2a9a5e621a570f3b"
OBTAIN = "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_obtain.py"
QUERY = (
    "backend/app/s3_daily_rowset/"
    "accepted_s2_train_val_source_002_row_level_read_live_async_session_query.py"
)
EXPECTED_BLOBS = {
    OBTAIN: "97be63307d002d6878649cd241ff94f5149e0f8a",
    QUERY: "4d946c02acff3a257817e714ad824f9b311d42ec",
}

# Exact transitive test-source pins: their assertions and old Blob constants stay intact.
_TRANSITIVE_TEST_BLOBS = (
    ("test_s3_a2_completeness_pass_observation_r1.py", "7b108973384f6a5dcff5bfc17126107f0c9f88b2"),
    (
        "test_s3_a2_incumbent_forecast_artifact_catalog_no_versioned_closeout_authorization.py",
        "c24c748476b8b98e31d57e3e9b30998cd4343d86",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_catalog_no_versioned_closeout_contract.py",
        "a407032430cb8866be5de13220464768366fca0c",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_authorization.py",
        "1d9ca027b67066d66e51874894aeab1a1d26bcda",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_contract.py",
        "12d9a22e64737ea66c99747bb5c6c764d751299f",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains_r1.py",
        "11c88c6c9831bbefb1ed902bd9c06cc68266e76d",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_no_versioned_flip_authorization.py",
        "bb6c7b87e82f1524dfe88ecd4b71c5ada84dba55",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_no_versioned_flip_contract.py",
        "ac2c49eb2a0251f74cd85588e8b22fb45cf850e0",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_no_versioned_flip_r1.py",
        "1d3223f67ddac2492bfda871c2b0b0d0f722e1ff",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_presence_package_independent_review_authorization.py",
        "9a5d05ae12b50c5fcc3e5c6e9fe8650fadd79e78",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_presence_package_independent_review_contract.py",
        "eb0a8807bbbf496335450e988bc19fb4ebf48f66",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_presence_package_independent_review_r1.py",
        "e4a6bc5a6f19c3b447c25004aae98982058f578e",
    ),
    (
        "test_s3_a2_incumbent_forecast_artifact_repository_presence_observation_contract.py",
        "a7a4cd0e4937c284b01cdedc76bc4bddbab38e7a",
    ),
)
EXPECTED_BLOBS.update(
    {"backend/tests/s3_daily_rowset/" + name: blob for name, blob in _TRANSITIVE_TEST_BLOBS}
)


def fixed_bytes(path: str) -> bytes:
    expected = EXPECTED_BLOBS[path]
    data = historical_bytes(path, BASE)
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert blob == expected, "Historical code Blob mismatch"
    return data


def source_blob(path: str | Path) -> str:
    candidate = Path(path)
    root = Path(__file__).resolve().parents[2]
    relative = (
        str(candidate.relative_to(root)) if candidate.is_relative_to(root) else str(candidate)
    )
    if relative in EXPECTED_BLOBS:
        fixed_bytes(relative)
        return EXPECTED_BLOBS[relative]
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def frozen_query_module(monkeypatch):
    """Keep TD03F's deliberately unsafe topology diagnostic on its old code.

    Current runtime behavior is tested separately against real wire I/O by
    test_asyncpg_cross_loop_probes; this never replaces a production function.
    """
    name = "backend.tests.td03g_frozen_query_source"
    module = types.ModuleType(name)
    module.__file__ = BASE + ":" + QUERY
    monkeypatch.setitem(sys.modules, name, module)
    exec(compile(fixed_bytes(QUERY), module.__file__, "exec"), module.__dict__)
    return module
