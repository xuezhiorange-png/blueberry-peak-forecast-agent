"""S3-A2 default catalog forecast-port envelope handoff contract tests."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    load_reviewed_grain_identity_set,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    uninstall_from_reviewed_set_loader,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.s3_a2_handoff_test_helpers import patch_handoff_disabled

CONTRACT_PATH = Path("docs/v0-3/s3/s3-default-catalog-forecast-port-envelope-handoff-contract.md")
WORKPAPER_PATH = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-forecast-port-envelope-handoff-contract.md"
)
EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-forecast-port-envelope-handoff-contract.json"
)
PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_forecast_port_envelope_handoff.py"
)
CATALOG_PY = Path("backend/app/s3_daily_rowset/catalog_artifact.py")
FORECAST_PY = Path("backend/app/s3_daily_rowset/forecast_artifact.py")
CONTENT_PY = Path("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
CONTENT_FOR_REVIEWED_PY = Path(
    "backend/app/s3_daily_rowset/s3_a2_incumbent_forecast_artifact_content_for_reviewed_grains.py"
)
COORDINATOR_PY = Path(
    "backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set.py"
)
CATALOG_CLOSEOUT_PY = Path(
    "backend/app/s3_daily_rowset/s3_a2_incumbent_forecast_artifact_catalog_no_versioned_closeout.py"
)
TEST_CATALOG_PY = Path("backend/tests/s3_daily_rowset/test_catalog_artifact.py")
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")

BASE_MAIN_SHA = "2755ce48823ae591e793b32a7f3ccba224e328cc"
BASE_MAIN_TREE_SHA = "4d3ea3ce69d5f54571f8f556dbb8aceed5f4d1bc"
PARENT_CATALOG_CLOSEOUT_R1_PR = 524
PARENT_CATALOG_CLOSEOUT_R1_MERGE = "2755ce48823ae591e793b32a7f3ccba224e328cc"
PARENT_CATALOG_CLOSEOUT_R1_COMMIT = "04305af0eccff7ac92476d882f17d805b935e3fa"
PARENT_CATALOG_CLOSEOUT_R1_EVIDENCE_JSON_SHA256 = (
    "5c3e801a1be1d21e38d63c68d808a5732686cd7a8cb4cf2ff37fca5e8dab7205"
)
THIS_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "591d6f2cab746944ffd75fbc4620bdf2dd52b03dfb0cb650168b5186e07c7084"
)
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
CONTENT_IDENTITY_SHA256 = "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
IN_MEMORY_CATALOG_IDENTITY_SHA256 = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
UNIQUE_FLIP = "S3_A2_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_CONTRACT_AUTHORIZED"
IMPLEMENTED = "DETERMINISTIC_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_IMPLEMENTED"
IMPLEMENTATION_AUTHORIZED = (
    "S3_A2_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_IMPLEMENTATION_AUTHORIZED"
)
POINTER_HEADING = "#### Default catalog forecast-port envelope handoff contract pointer"
SECTION_211_HEADING = "## 211. Default catalog forecast-port envelope handoff contract pointer"
SECTION_210_HEADING = "## 210. Incumbent forecast artifact catalog no-versioned closeout R1 pointer"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB = "d206aa94afc558ba21a5e89221107b5507dcc1c2"
COORDINATOR_REVIEWED_SET_PY_BLOB = "2ce94233f153f8e5297e4b978243323ca917dcf8"
CATALOG_NO_VERSIONED_CLOSEOUT_PY_BLOB = "72d946ccb94a4734919321733b82a90c7dc9b8b1"
TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
FORBIDDEN_PROSE_TOKENS = (
    "localhost",
    "5432",
    "psycopg",
    "content_bytes",
    "postgresql://",
    "greenlet",
    "MissingGreenlet",
    "OSError",
)
CONTRACT_FROZEN_REF = BASE_MAIN_SHA


def _git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def _git_blob_at(ref: str, path: Path) -> str:
    content = subprocess.check_output(
        ["git", "show", f"{ref}:{path.as_posix()}"],
    )
    return (
        subprocess.check_output(
            ["git", "hash-object", "--stdin"],
            input=content,
        )
        .decode()
        .strip()
    )


def _path_missing_at(ref: str, path: Path) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{ref}:{path.as_posix()}"],
            capture_output=True,
        ).returncode
        != 0
    )


@pytest.fixture(autouse=True)
def _uninstall_reviewed_set_hooks() -> Iterator[None]:
    uninstall_from_reviewed_set_loader()
    yield
    uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()


def test_contract_evidence_sha256_payload_without_self_key() -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert embedded == THIS_CONTRACT_EVIDENCE_JSON_SHA256


def test_frozen_blobs_unchanged() -> None:
    from backend.tests.s3_daily_rowset.s3_a2_frozen_blob_authority import (
        assert_evidence_frozen_python_blobs_match_constants,
    )

    assert_evidence_frozen_python_blobs_match_constants(
        EVIDENCE_PATH,
        catalog_artifact_py_blob=CATALOG_ARTIFACT_PY_BLOB,
        forecast_artifact_py_blob=FORECAST_ARTIFACT_PY_BLOB,
        content_producer_py_blob=CONTENT_PRODUCER_PY_BLOB,
        content_for_reviewed_grains_py_blob=CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB,
        coordinator_reviewed_set_py_blob=COORDINATOR_REVIEWED_SET_PY_BLOB,
        test_catalog_artifact_py_blob=TEST_CATALOG_ARTIFACT_PY_BLOB,
    )


def test_contract_package_is_docs_only() -> None:
    assert CONTRACT_PATH.is_file()
    assert WORKPAPER_PATH.is_file()
    assert EVIDENCE_PATH.is_file()
    assert PRODUCTION_MODULE.name == "s3_a2_default_catalog_forecast_port_envelope_handoff.py"
    assert _path_missing_at(CONTRACT_FROZEN_REF, PRODUCTION_MODULE)
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()


def test_bare_default_still_fail_closes_no_versioned_without_session() -> None:
    with patch(
        "backend.app.s3_daily_rowset.s3_a2_default_catalog_forecast_port_envelope_handoff."
        "deterministic_coordinator_reviewed_grains_forecast_artifact",
        return_value=None,
    ):
        with patch_handoff_disabled(), patch("backend.app.db.session.AsyncSessionMaker", None):
            result = EvaluationInstanceCatalogArtifactProductionService(
                dataset_identity=DATASET_IDENTITY,
            ).produce()
    assert result.reason_code is CatalogArtifactReasonCode.NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
    assert load_reviewed_grain_identity_set() == ()


def test_contract_documents_classifier_envelope_non_exposure() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "ENVELOPE_OBJECT_IS_NOT_EXPOSED_BY_CLASSIFIER_RESULT=true" in text
    assert "FORBIDDEN_ASSUMPTION=do_not_assume_result.artifact_exists" in text
    assert "CLASSIFIER_INJECTED_CATALOG_REASON" in text
    assert "BARE_DEFAULT_CATALOG_REASON" in text
    assert "TARGET_BARE_DEFAULT_CATALOG_REASON=ARTIFACT_PRODUCED" in text
    assert CONTENT_IDENTITY_SHA256 in text
    assert IN_MEMORY_CATALOG_IDENTITY_SHA256 in text


def test_contract_flags_implementation_not_authorized() -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert payload["flags"][UNIQUE_FLIP] is True
    assert payload["flags"][IMPLEMENTED] is False
    assert payload["flags"][IMPLEMENTATION_AUTHORIZED] is False
    assert payload["flags"]["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert payload["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert payload["unique_flip"]["this_family_unique_remaining_gap_closed"] is False
    parent_r1 = payload["parent_catalog_no_versioned_closeout_r1"]
    assert parent_r1["parent_catalog_no_versioned_closeout_r1_pr"] == PARENT_CATALOG_CLOSEOUT_R1_PR


def test_pointer_isolation_r1_snapshot_still_implemented_false() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert f"{UNIQUE_FLIP}=false" not in live_intro
    assert f"{IMPLEMENTED}=false" not in live_intro
    pointer = plan.split(POINTER_HEADING, 1)[1]
    if "### 4.5" in pointer:
        pointer = pointer.split("### 4.5", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in pointer
    assert f"{IMPLEMENTED}=false" in pointer
    assert "BARE_DEFAULT_CATALOG_REASON=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT" in pointer
    assert "CLASSIFIER_INJECTED_CATALOG_REASON=ARTIFACT_PRODUCED" in pointer
    assert amendment.count(SECTION_211_HEADING) == 1
    assert plan.count(POINTER_HEADING) == 1
    r1_snapshot = amendment.split(SECTION_210_HEADING, 1)[1]
    if SECTION_211_HEADING in r1_snapshot:
        r1_snapshot = r1_snapshot.split(SECTION_211_HEADING, 1)[0]
    assert IMPLEMENTED + "=false" in r1_snapshot
    assert UNIQUE_FLIP not in r1_snapshot
    handoff_snapshot = amendment.split(SECTION_211_HEADING, 1)[1]
    if "\n## " in handoff_snapshot:
        handoff_snapshot = handoff_snapshot.split("\n## ", 1)[0]
    assert f"{IMPLEMENTED}=false" in handoff_snapshot
    assert f"{UNIQUE_FLIP}=true" in handoff_snapshot
    assert CONTENT_IDENTITY_SHA256 in handoff_snapshot


def test_workpaper_and_contract_avoid_forbidden_tokens() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8") + WORKPAPER_PATH.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered, token
    assert "CONTRACT_AUTHORING_GRANT=true" in text
    assert f"BASE_MAIN_SHA={BASE_MAIN_SHA}" in text
    assert f"PARENT_CATALOG_NO_VERSIONED_CLOSEOUT_R1_PR={PARENT_CATALOG_CLOSEOUT_R1_PR}" in text
    assert f"EVIDENCE_JSON_SHA256={THIS_CONTRACT_EVIDENCE_JSON_SHA256}" in WORKPAPER_PATH.read_text(
        encoding="utf-8"
    )


def test_parent_catalog_closeout_r1_pins() -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    parent = payload["parent_catalog_no_versioned_closeout_r1"]
    assert (
        parent["parent_catalog_no_versioned_closeout_r1_merge"] == PARENT_CATALOG_CLOSEOUT_R1_MERGE
    )
    assert (
        parent["parent_catalog_no_versioned_closeout_r1_commit"]
        == PARENT_CATALOG_CLOSEOUT_R1_COMMIT
    )
    assert (
        parent["parent_catalog_no_versioned_closeout_r1_evidence_json_sha256"]
        == PARENT_CATALOG_CLOSEOUT_R1_EVIDENCE_JSON_SHA256
    )
    assert payload["audited_repository_sha"] == BASE_MAIN_SHA
    assert payload["audited_repository_tree_sha"] == BASE_MAIN_TREE_SHA
    assert payload["contract_authored_only"] is True
    assert payload["implementation_authorized"] is False
    assert payload["r1_authorized"] is False
