"""S3-A2 default catalog live-bindability and registry availability authorization tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backend.app.rolling_backtest.canonical import sha256_payload

CONTRACT_PATH = Path(
    "docs/v0-3/s3/s3-default-catalog-live-bindability-and-registry-availability-contract.md"
)
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-bindability-and-registry-availability-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-bindability-and-registry-availability-authorization.json"
)
FUTURE_AUTHORITY_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_bindability_and_registry_availability.py"
)
BINDING_PY = Path("backend/app/s3_daily_rowset/binding.py")
REGISTRY_PY = Path("backend/app/s3_daily_rowset/registry.py")
CATALOG_PY = Path("backend/app/s3_daily_rowset/catalog_artifact.py")
FORECAST_PY = Path("backend/app/s3_daily_rowset/forecast_artifact.py")
HANDOFF_PY = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_forecast_port_envelope_handoff.py"
)
BINDABLE_REPOSITORY_PY = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py"
)
AVAILABLE_CLOSEOUT_PY = Path(
    "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")

BASE_MAIN_SHA = "59f1d1e15178eac4de4100751caaac98bf48343d"
BASE_MAIN_TREE_SHA = "47a2b83143b343310172a60b356fb1697aa8117a"
PARENT_CONTRACT_PR = 528
PARENT_CONTRACT_MERGE = "59f1d1e15178eac4de4100751caaac98bf48343d"
PARENT_CONTRACT_COMMIT = "3c8e1d026f67fd9356fb0459e79d69d247d0c8ee"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "d81f0d3f8b4f9fb42496ac0186f91dac6e1164c3b08b765bf445393dd10a8c2c"
)
GRANT_EVIDENCE_JSON_SHA256 = "5e3a5413a8d29663cd6688237d0accac802235723902fa9b4caed4b3153ac6eb"
CONTENT_IDENTITY_SHA256 = "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
IN_MEMORY_CATALOG_IDENTITY_SHA256 = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
UNIQUE_FLIP = (
    "S3_A2_DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED"
)
THIS_FAMILY_CONTRACT_AUTHORIZED = "LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_CONTRACT_AUTHORIZED"
THIS_FAMILY_IMPLEMENTED = (
    "DETERMINISTIC_DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_IMPLEMENTED"
)
CONTRACT_POINTER_HEADING = (
    "#### Default catalog live-bindability and registry availability contract pointer"
)
GRANT_POINTER_HEADING = (
    "#### Default catalog live-bindability and registry availability implementation "
    "authorization pointer"
)
SECTION_214_HEADING = (
    "## 214. Default catalog live-bindability and registry availability contract pointer"
)
SECTION_215_HEADING = (
    "## 215. Default catalog live-bindability and registry availability implementation "
    "authorization pointer"
)

CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
FORECAST_ARTIFACT_PY_BLOB = "49938d7107728987439a0a751a1273b73e0022e7"
BINDING_PY_BLOB = "0a335f682a923bcd73908b58cd70cd49c9ab0117"
REGISTRY_PY_BLOB = "ca16d518ab18136059cd08bcf4b247774d750bb5"
BINDABLE_REPOSITORY_PY_BLOB = "98948a405e4865a573f1b2332d128af3aaaccfd3"
AVAILABLE_CLOSEOUT_PY_BLOB = "cafca50d5c4ff4e416747644f7446a7ea24caee9"
HANDOFF_PY_BLOB = "a057802f598aada08e26aed35fb4ad76b4f8c4ce"

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
GRANT_FROZEN_REF = "59f1d1e15178eac4de4100751caaac98bf48343d"


def _git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def _path_missing_at(ref: str, path: Path) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{ref}:{path.as_posix()}"],
            capture_output=True,
        ).returncode
        != 0
    )


def test_grant_evidence_sha256_payload_matches_embedded_digest() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert embedded == GRANT_EVIDENCE_JSON_SHA256


def test_grant_package_is_docs_only() -> None:
    assert GRANT_WORKPAPER.is_file()
    assert GRANT_EVIDENCE.is_file()
    assert CONTRACT_PATH.is_file()
    assert _path_missing_at(GRANT_FROZEN_REF, FUTURE_AUTHORITY_MODULE)
    assert not FUTURE_AUTHORITY_MODULE.exists()


def test_frozen_python_blobs_remain_byte_identical() -> None:
    assert _git_blob(CATALOG_PY) == CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(FORECAST_PY) == FORECAST_ARTIFACT_PY_BLOB
    assert _git_blob(BINDING_PY) == BINDING_PY_BLOB
    assert _git_blob(REGISTRY_PY) == REGISTRY_PY_BLOB
    assert _git_blob(BINDABLE_REPOSITORY_PY) == BINDABLE_REPOSITORY_PY_BLOB
    assert _git_blob(AVAILABLE_CLOSEOUT_PY) == AVAILABLE_CLOSEOUT_PY_BLOB
    assert _git_blob(HANDOFF_PY) == HANDOFF_PY_BLOB


def test_grant_evidence_flags() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    flags = payload["flags"]
    assert flags[THIS_FAMILY_CONTRACT_AUTHORIZED] is True
    assert flags[UNIQUE_FLIP] is True
    assert flags[THIS_FAMILY_IMPLEMENTED] is False
    assert flags["IMPLEMENTATION_AUTHORIZED"] is True
    assert flags["IMPLEMENTED"] is False
    assert flags["LIVE_BINDABILITY_IMPLEMENTED"] is False
    assert flags["REGISTRY_AVAILABILITY_IMPLEMENTED"] is False
    assert flags["LIVE_BINDABILITY_IMPLEMENTATION_AUTHORIZED"] is False
    assert flags["REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED"] is False
    assert flags["AUTHORIZED_LIVE_BINDABLE_CLASSIFICATION"] is False
    assert flags["NO_BINDABLE_CATALOG_IN_REPOSITORY"] is True
    assert flags["EVALUATION_INSTANCE_REGISTRY_AVAILABLE"] is False
    assert flags["UNIQUE_REMAINING_GAP_CLOSED"] is False
    assert flags["FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE"] is False
    assert flags["COORDINATOR_REVIEWED_AVAILABLE_CLOSEOUT_EXISTS"] is False
    assert flags["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert flags["CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED"] is False
    assert flags["V0_3_S4_AUTHORIZED"] is False
    assert flags["FUTURE_AUTHORITY_MODULE_AUTHORIZED_FOR_LATER_R1"] is True
    assert flags["FUTURE_AUTHORITY_MODULE_CREATED_IN_GRANT"] is False
    assert payload["unique_flip"]["this_family_unique_remaining_gap_closed"] is False
    assert payload["parent_contract"]["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert (
        payload["parent_contract"]["parent_contract_evidence_json_sha256"]
        == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    )
    canonical = payload["canonical_authority_path"]
    assert canonical["canonical_option"] == "SEPARATE_AUTHORITY_CLASSIFIER"
    assert payload["implementation_r1_authorized"] is False
    assert payload["implementation_grant_authored_only"] is True
    assert payload["user_gate"] == "授权"
    assert payload["interpreted_gate"] == "IMPLEMENTATION_GRANT_AUTHORING"
    assert payload["audited_repository_sha"] == BASE_MAIN_SHA
    assert payload["audited_repository_tree_sha"] == BASE_MAIN_TREE_SHA
    blobs = payload["frozen_python_blobs"]
    assert blobs["binding_py_blob"] == BINDING_PY_BLOB
    assert blobs["registry_py_blob"] == REGISTRY_PY_BLOB


def test_grant_files_exist_and_avoid_forbidden_tokens() -> None:
    text = GRANT_WORKPAPER.read_text(encoding="utf-8") + GRANT_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_THIS_GRANT_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = GRANT_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=授权" in workpaper
    assert "INTERPRETED_GATE=IMPLEMENTATION_GRANT_AUTHORING" in workpaper
    assert "GRANT_ONLY=true" in workpaper
    assert "THIS_PR_IS_NOT_R1=true" in workpaper
    assert f"{UNIQUE_FLIP}=true" in workpaper
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in workpaper
    assert f"CONTENT_IDENTITY_SHA256={CONTENT_IDENTITY_SHA256}" in workpaper
    assert f"EVIDENCE_JSON_SHA256={GRANT_EVIDENCE_JSON_SHA256}" in workpaper
    assert "CANONICAL_OPTION=SEPARATE_AUTHORITY_CLASSIFIER" in workpaper
    assert "FUTURE_AUTHORITY_MODULE_CREATED_IN_GRANT=false" in workpaper
    assert "GRANT_MERGE_DOES_NOT_CREATE_AUTHORITY_CLASSIFIER=true" in workpaper
    assert "GRANT_MERGE_DOES_NOT_FLIP_NO_BINDABLE=true" in workpaper
    assert "GRANT_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true" in workpaper


def test_grant_pointers_are_appended_not_rewritten() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert f"{THIS_FAMILY_CONTRACT_AUTHORIZED}=true" in live_intro
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in live_intro
    assert "LIVE_BINDABILITY_IMPLEMENTATION_AUTHORIZED=false" in live_intro
    assert "REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED=false" in live_intro
    grant_pointer = plan.split(GRANT_POINTER_HEADING, 1)[1]
    if "### 4.5" in grant_pointer:
        grant_pointer = grant_pointer.split("### 4.5", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in grant_pointer
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in grant_pointer
    assert GRANT_EVIDENCE_JSON_SHA256 in grant_pointer
    assert PARENT_CONTRACT_EVIDENCE_JSON_SHA256 in grant_pointer
    grant_workpaper_name = (
        "s3-a2-default-catalog-live-bindability-and-registry-availability-authorization.md"
    )
    assert grant_workpaper_name in plan
    assert amendment.count(SECTION_214_HEADING) == 1
    assert amendment.count(SECTION_215_HEADING) == 1
    assert plan.count(CONTRACT_POINTER_HEADING) == 1
    assert plan.count(GRANT_POINTER_HEADING) == 1
    grant_snapshot = amendment.split(SECTION_215_HEADING, 1)[1]
    if "\n## " in grant_snapshot:
        grant_snapshot = grant_snapshot.split("\n## ", 1)[0]
    assert UNIQUE_FLIP + "=true" in grant_snapshot
    assert f"{THIS_FAMILY_IMPLEMENTED}=false" in grant_snapshot
    assert IN_MEMORY_CATALOG_IDENTITY_SHA256 in grant_snapshot
    contract_snapshot = amendment.split(SECTION_214_HEADING, 1)[1]
    if SECTION_215_HEADING in contract_snapshot:
        contract_snapshot = contract_snapshot.split(SECTION_215_HEADING, 1)[0]
    assert f"{UNIQUE_FLIP}=false" not in contract_snapshot or (
        "S3_A2_DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED=false"
        in contract_snapshot
    )
    assert f"{THIS_FAMILY_CONTRACT_AUTHORIZED}=true" in contract_snapshot


def test_parent_contract_exists_on_audited_base() -> None:
    payload = json.loads(
        Path(
            "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-bindability-and-registry-availability-contract.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["evidence_json_sha256"] == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    assert (
        subprocess.run(
            ["git", "cat-file", "-e", f"{PARENT_CONTRACT_MERGE}:{CONTRACT_PATH.as_posix()}"],
            capture_output=True,
        ).returncode
        == 0
    )
