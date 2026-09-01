"""S3-A2 default catalog forecast-port envelope handoff authorization tests."""

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
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-forecast-port-envelope-handoff-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-forecast-port-envelope-handoff-authorization.json"
)
PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_forecast_port_envelope_handoff.py"
)
FORECAST_PY = Path("backend/app/s3_daily_rowset/forecast_artifact.py")
CATALOG_PY = Path("backend/app/s3_daily_rowset/catalog_artifact.py")
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

BASE_MAIN_SHA = "970f0944a1b88e2622cd7ef52a607b667780fd55"
BASE_MAIN_TREE_SHA = "a19922f9caea75a0fce7b274a2c144b36053b6c0"
PARENT_CONTRACT_PR = 525
PARENT_CONTRACT_MERGE = "970f0944a1b88e2622cd7ef52a607b667780fd55"
PARENT_CONTRACT_COMMIT = "435c55f5aa0ec57ff7ddd172f65def98f21cafad"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "591d6f2cab746944ffd75fbc4620bdf2dd52b03dfb0cb650168b5186e07c7084"
)
GRANT_EVIDENCE_JSON_SHA256 = "4d6f979e725254373d53561a2dc96d62394784f2ddbd5e8422996a4bb50012c2"
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
CONTENT_IDENTITY_SHA256 = "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
REVIEW_EVIDENCE_DIGEST_SHA256 = "40e03141b52188cafe9e9cb6842d14f2ebd6caa3abe1fd80142ad71162781f64"
IN_MEMORY_CATALOG_IDENTITY_SHA256 = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
UNIQUE_FLIP = "S3_A2_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_IMPLEMENTATION_AUTHORIZED"
THIS_FAMILY_CONTRACT_AUTHORIZED = (
    "S3_A2_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_CONTRACT_AUTHORIZED"
)
THIS_FAMILY_IMPLEMENTED = "DETERMINISTIC_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_IMPLEMENTED"
CONTRACT_POINTER_HEADING = "#### Default catalog forecast-port envelope handoff contract pointer"
GRANT_POINTER_HEADING = (
    "#### Default catalog forecast-port envelope handoff implementation authorization pointer"
)
SECTION_211_HEADING = "## 211. Default catalog forecast-port envelope handoff contract pointer"
SECTION_212_HEADING = (
    "## 212. Default catalog forecast-port envelope handoff implementation authorization pointer"
)
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB = "d206aa94afc558ba21a5e89221107b5507dcc1c2"
COORDINATOR_REVIEWED_SET_PY_BLOB = "2ce94233f153f8e5297e4b978243323ca917dcf8"
CATALOG_NO_VERSIONED_CLOSEOUT_PY_BLOB = "72d946ccb94a4734919321733b82a90c7dc9b8b1"
TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
FORBIDDEN_THIS_GRANT_TOKENS = (
    "localhost",
    "5432",
    "psycopg",
    "content_bytes",
    "postgresql://",
    "greenlet",
    "MissingGreenlet",
    "OSError",
)
GRANT_FROZEN_REF = "916725cd2f2bd6992acf94829d9c9c293866db6f"


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


def test_grant_evidence_sha256_payload_matches_embedded_digest() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert embedded == GRANT_EVIDENCE_JSON_SHA256


def test_grant_package_is_docs_only() -> None:
    assert GRANT_WORKPAPER.is_file()
    assert GRANT_EVIDENCE.is_file()
    assert _path_missing_at(GRANT_FROZEN_REF, PRODUCTION_MODULE)
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


def test_frozen_python_blobs_remain_byte_identical() -> None:
    from backend.tests.s3_daily_rowset.s3_a2_frozen_blob_authority import (
        assert_evidence_frozen_python_blobs_match_constants,
    )

    assert_evidence_frozen_python_blobs_match_constants(
        GRANT_EVIDENCE,
        catalog_artifact_py_blob=CATALOG_ARTIFACT_PY_BLOB,
        forecast_artifact_py_blob=FORECAST_ARTIFACT_PY_BLOB,
        content_producer_py_blob=CONTENT_PRODUCER_PY_BLOB,
        content_for_reviewed_grains_py_blob=CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB,
        coordinator_reviewed_set_py_blob=COORDINATOR_REVIEWED_SET_PY_BLOB,
        catalog_no_versioned_closeout_py_blob=CATALOG_NO_VERSIONED_CLOSEOUT_PY_BLOB,
        test_catalog_artifact_py_blob=TEST_CATALOG_ARTIFACT_PY_BLOB,
    )


def test_grant_evidence_flags() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    flags = payload["flags"]
    assert flags[THIS_FAMILY_CONTRACT_AUTHORIZED] is True
    assert flags[UNIQUE_FLIP] is True
    assert flags[THIS_FAMILY_IMPLEMENTED] is False
    assert flags["IMPLEMENTATION_AUTHORIZED"] is True
    assert flags["IMPLEMENTED"] is False
    assert flags["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert flags["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert flags["THIS_GRANT_DOES_NOT_IMPLEMENT_HANDOFF"] is True
    assert flags["THIS_GRANT_DOES_NOT_MAKE_DEFAULT_CATALOG_PRODUCE_SUCCEED"] is True
    assert payload["unique_flip"]["this_family_unique_remaining_gap_closed"] is False
    assert payload["parent_contract"]["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert (
        payload["parent_contract"]["parent_contract_evidence_json_sha256"]
        == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    )
    assert payload["implementation_r1_authorized"] is False
    assert payload["implementation_grant_authored_only"] is True


def test_grant_files_exist_and_avoid_forbidden_tokens() -> None:
    text = GRANT_WORKPAPER.read_text(encoding="utf-8") + GRANT_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_THIS_GRANT_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = GRANT_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=授权" in workpaper
    assert "GRANT_ONLY=true" in workpaper
    assert "THIS_PR_IS_NOT_R1=true" in workpaper
    assert f"{UNIQUE_FLIP}=true" in workpaper
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in workpaper
    assert f"CONTENT_IDENTITY_SHA256={CONTENT_IDENTITY_SHA256}" in workpaper
    assert f"REVIEW_EVIDENCE_DIGEST_SHA256={REVIEW_EVIDENCE_DIGEST_SHA256}" in workpaper
    assert f"EVIDENCE_JSON_SHA256={GRANT_EVIDENCE_JSON_SHA256}" in workpaper
    assert "GRANT_MERGE_DOES_NOT_IMPLEMENT_HANDOFF=true" in workpaper
    assert "FORBIDDEN_MAKE_DEFAULT_CATALOG_PRODUCE_SUCCEED_IN_THIS_GRANT=true" in workpaper


def test_grant_pointers_are_appended_not_rewritten() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert f"{THIS_FAMILY_CONTRACT_AUTHORIZED}=true" in live_intro
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" not in live_intro
    assert f"{UNIQUE_FLIP}=false" not in live_intro
    grant_pointer = plan.split(GRANT_POINTER_HEADING, 1)[1]
    if "### 4.5" in grant_pointer:
        grant_pointer = grant_pointer.split("### 4.5", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in grant_pointer
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in grant_pointer
    assert "s3-a2-default-catalog-forecast-port-envelope-handoff-authorization.md" in plan
    assert amendment.count(SECTION_211_HEADING) == 1
    assert amendment.count(SECTION_212_HEADING) == 1
    assert plan.count(CONTRACT_POINTER_HEADING) == 1
    assert plan.count(GRANT_POINTER_HEADING) == 1
    grant_snapshot = amendment.split(SECTION_212_HEADING, 1)[1]
    if "\n## " in grant_snapshot:
        grant_snapshot = grant_snapshot.split("\n## ", 1)[0]
    assert UNIQUE_FLIP + "=true" in grant_snapshot
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in grant_snapshot
    assert CONTENT_IDENTITY_SHA256 in grant_snapshot
    assert REVIEW_EVIDENCE_DIGEST_SHA256 in grant_snapshot
    contract_snapshot = amendment.split(SECTION_211_HEADING, 1)[1]
    if SECTION_212_HEADING in contract_snapshot:
        contract_snapshot = contract_snapshot.split(SECTION_212_HEADING, 1)[0]
    assert f"{UNIQUE_FLIP}=false" in contract_snapshot
    assert f"{THIS_FAMILY_CONTRACT_AUTHORIZED}=true" in contract_snapshot
