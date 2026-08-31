"""S3-A2 coordinator-reviewed live-origin grain identity-set R1 tests."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.catalog_artifact import IncumbentForecastArtifactEntry
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    ORIGIN_MODEL_ID,
    ORIGIN_QUANTILES,
    last_legal_cutoff_before_test,
    replay_identity_origin_entries,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    read_bindable_replay_identity_rows,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_replay_identity_grain_identity_set import (
    load_reviewed_grain_identity_set,
    reviewed_grain_identity_set_artifact_available,
)
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_completeness_pass_closeout import (
    CompletenessPassCloseoutClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_CUTOFF_BUSINESS_DATE,
    REVIEW_MEMBER_COUNT,
    REVIEW_MODEL_ID,
    REVIEW_QUANTILES,
    REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
    hashable_reviewed_grain_identity_set_payload,
    install_into_reviewed_set_loader,
    load_coordinator_reviewed_live_origin_grain_identity_set,
    uninstall_from_reviewed_set_loader,
)
from backend.app.s3_daily_rowset.window import cutoff_business_date

PRODUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_coordinator_reviewed_live_origin_grain_identity_set.py"
)
COMPLETENESS_PASS_CLOSEOUT_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_completeness_pass_closeout.py"
)
REVIEWED_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_reviewed_grain_identity_set_closeout.py")
AVAILABLE_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
)
BINDABLE_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py")
CONSTRUCTION_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_construction.py"
)
OBTAIN_MODULE = Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_live_origin_obtain.py")
CATALOG_PY = Path("backend/app/s3_daily_rowset/catalog_artifact.py")
BINDING_PY = Path("backend/app/s3_daily_rowset/binding.py")
COMPLETENESS_PY = Path("backend/app/s3_daily_rowset/completeness.py")
TEST_CATALOG_PY = Path("backend/tests/s3_daily_rowset/test_catalog_artifact.py")
GRAIN_PY = Path(
    "backend/app/s3_daily_rowset/incumbent_forecast_v0_2_replay_identity_grain_identity_set.py"
)
CONTENT_PY = Path("backend/app/s3_daily_rowset/incumbent_forecast_artifact_content.py")
ALEMBIC_PY = Path("backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py")
FORECAST_PY = Path("backend/app/s3_daily_rowset/forecast_artifact.py")
ALIGNMENT_EVIDENCE_PY = Path(
    "backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py"
)
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-authorization.json"
)
CONTRACT_DOC = Path(
    "docs/v0-3/s3/s3-coordinator-reviewed-live-origin-grain-identity-set-contract.md"
)
CONTRACT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-contract.md"
)
CONTRACT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-contract.json"
)
R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-r1.md"
)
R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-coordinator-reviewed-live-origin-grain-identity-set-r1.json"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")

TEST_CATALOG_ARTIFACT_PY_BLOB = "af59a9f1d291ab32eff23684aca477f0e4a852cd"
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
GRAIN_IDENTITY_SET_PY_BLOB = "eed2ecbcacc2a8173003cba55853a6ef5b5f89c5"
CONTENT_PRODUCER_PY_BLOB = "0cc05fff3deff00d279070aa246f241ff3754e89"
ALEMBIC_BLOB = "1e0864ebef1d947d4c9466d71efaa759d44c7ad7"
OBTAIN_MODULE_BLOB = "97be63307d002d6878649cd241ff94f5149e0f8a"
CONSTRUCTION_MODULE_BLOB = "39b3a06bc768b728e5b283c1720a8f38ed5ff71a"
BINDABLE_REPOSITORY_PY_BLOB = "98948a405e4865a573f1b2332d128af3aaaccfd3"
AVAILABLE_CLOSEOUT_PY_BLOB = "cafca50d5c4ff4e416747644f7446a7ea24caee9"
REVIEWED_SET_CLOSEOUT_PY_BLOB = "ab9e2edf2e157b80dca5e230129374f5ac97810c"
COMPLETENESS_PY_BLOB = "06b778b75710a0de30035569d15c8e3d87b095d4"
COMPLETENESS_PASS_CLOSEOUT_PY_BLOB = "d1a6654b7f584c6e944628ecc63265ab8f9a1e7e"
BINDING_PY_BLOB = "0a335f682a923bcd73908b58cd70cd49c9ab0117"
FORECAST_ARTIFACT_PY_BLOB = "84576cf7d1ea7b4ab5f8bdef217483883ba638b8"
ALIGNMENT_EVIDENCE_PY_BLOB = "df000544dc0e0b4844b0a5a7c342f6abce957e86"
PARENT_GRANT_PR = 502
PARENT_GRANT_MERGE = "eb239e0dfd3cb123742ad163157815fe123ef099"
PARENT_GRANT_COMMIT = "71c2186b6cfeb1cf844c739ba7a24494521ffe42"
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "c6562788955093db383036dbf2f784888969c5e593d195e68f21a68cee868f93"
)
PARENT_GRANT_WORKPAPER_BLOB = "346b524ff947004470d171ea54b8ec71d96152d8"
PARENT_GRANT_EVIDENCE_BLOB = "ed6bb06c72817bb21880c28ee8cc7961c5f03b0b"
PARENT_CONTRACT_PR = 500
PARENT_CONTRACT_COMMIT = "7b0fad18d8daa52dc912883b2dc8e2bb50185d48"
PARENT_CONTRACT_MERGE = "7b32e0a97d2428c9621de312d24d6fc3be8a93fa"
PARENT_CONTRACT_DOC_BLOB = "ea729fc2e31d305a5f40baf2cbf028e9645d5745"
PARENT_CONTRACT_WORKPAPER_BLOB = "48bdd85f6bbcf5aebe225e8bbb0296090e6d10db"
PARENT_CONTRACT_EVIDENCE_BLOB = "c37aaf9c2de67e7c2ee788970378be339fc8e562"
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "df08ff6b70c079c3bc36f9841ecb8c9cb3eaeed7fdf4064990f8354994126dc2"
)
PARENT_COMPLETENESS_PASS_CLOSEOUT_R1_PR = 501
PARENT_COMPLETENESS_PASS_CLOSEOUT_R1_MERGE = "b0940a3e3d4155f847aa07ce6d4041a62addf2ec"
PARENT_COMPLETENESS_PASS_CLOSEOUT_R1_COMMIT = "81c4fdca78ea514ac99d8d3554494f54062f124a"
PARENT_COMPLETENESS_PASS_CLOSEOUT_R1_EVIDENCE_JSON_SHA256 = (
    "2c4e23bc107fa89a8ca36676ce117c2b0e0eb4dfcdd6f102075578347de1f224"
)
UNIQUE_FLIP = "DETERMINISTIC_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTED"
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


def _git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def _assert_harvest_replay_and_provider_remain_empty() -> None:
    clear_v0_2_live_postgres_session_provider()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


@pytest.fixture(autouse=True)
def _uninstall_reviewed_set_hooks() -> Iterator[None]:
    uninstall_from_reviewed_set_loader()
    yield
    uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()


def test_production_module_does_not_land_or_embed_connection_strings() -> None:
    source = PRODUCTION_MODULE.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "land_replay_identity_origin" not in source
    assert "postgresql://" not in lowered
    assert "create_engine(" not in lowered
    assert "content_bytes" not in source
    assert "sqlalchemy" not in lowered
    assert "dsn" not in lowered


def test_frozen_blobs_unchanged() -> None:
    assert _git_blob(CATALOG_PY) == CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(TEST_CATALOG_PY) == TEST_CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(GRAIN_PY) == GRAIN_IDENTITY_SET_PY_BLOB
    assert _git_blob(CONTENT_PY) == CONTENT_PRODUCER_PY_BLOB
    assert _git_blob(ALEMBIC_PY) == ALEMBIC_BLOB
    assert _git_blob(OBTAIN_MODULE) == OBTAIN_MODULE_BLOB
    assert _git_blob(CONSTRUCTION_MODULE) == CONSTRUCTION_MODULE_BLOB
    assert _git_blob(BINDABLE_MODULE) == BINDABLE_REPOSITORY_PY_BLOB
    assert _git_blob(AVAILABLE_MODULE) == AVAILABLE_CLOSEOUT_PY_BLOB
    assert _git_blob(REVIEWED_MODULE) == REVIEWED_SET_CLOSEOUT_PY_BLOB
    assert _git_blob(COMPLETENESS_PY) == COMPLETENESS_PY_BLOB
    assert _git_blob(COMPLETENESS_PASS_CLOSEOUT_MODULE) == COMPLETENESS_PASS_CLOSEOUT_PY_BLOB
    assert _git_blob(BINDING_PY) == BINDING_PY_BLOB
    assert _git_blob(FORECAST_PY) == FORECAST_ARTIFACT_PY_BLOB
    assert _git_blob(ALIGNMENT_EVIDENCE_PY) == ALIGNMENT_EVIDENCE_PY_BLOB
    assert _git_blob(GRANT_WORKPAPER) == PARENT_GRANT_WORKPAPER_BLOB
    assert _git_blob(GRANT_EVIDENCE) == PARENT_GRANT_EVIDENCE_BLOB
    assert _git_blob(CONTRACT_DOC) == PARENT_CONTRACT_DOC_BLOB
    assert _git_blob(CONTRACT_WORKPAPER) == PARENT_CONTRACT_WORKPAPER_BLOB
    assert _git_blob(CONTRACT_EVIDENCE) == PARENT_CONTRACT_EVIDENCE_BLOB


def test_default_import_does_not_wire_reviewed_set_loader() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_artifact_has_exactly_three_policy_grains() -> None:
    origin = replay_identity_origin_entries()
    cutoff = last_legal_cutoff_before_test()
    assert len(origin) == REVIEW_MEMBER_COUNT
    assert cutoff_business_date(cutoff) == date(2026, 2, 16)
    assert ORIGIN_MODEL_ID == REVIEW_MODEL_ID
    assert ORIGIN_QUANTILES == REVIEW_QUANTILES
    artifact = load_coordinator_reviewed_live_origin_grain_identity_set()
    assert artifact.artifact_available is True
    assert artifact.reason_code is None
    assert artifact.review_cutoff_business_date == date.fromisoformat(REVIEW_CUTOFF_BUSINESS_DATE)
    assert artifact.review_cutoff_at == REVIEW_CUTOFF_AT
    assert artifact.review_model_id == REVIEW_MODEL_ID
    assert artifact.review_quantiles == REVIEW_QUANTILES
    assert len(artifact.members) == REVIEW_MEMBER_COUNT
    assert artifact.artifact_id == REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    assert tuple(member.forecast_quantile for member in artifact.members) == REVIEW_QUANTILES
    for member, entry in zip(artifact.members, origin, strict=True):
        assert member.forecast_cutoff_at == entry.forecast_cutoff_at
        assert member.forecast_cutoff_at.isoformat() == REVIEW_CUTOFF_AT
        assert member.model_id == entry.model_id == REVIEW_MODEL_ID
        assert member.forecast_quantile == entry.forecast_quantile
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()


def test_hashable_identity_is_stable() -> None:
    payload = hashable_reviewed_grain_identity_set_payload()
    assert payload["review_cutoff_business_date"] == "2026-02-16"
    assert payload["review_cutoff_at"] == "2026-02-16T00:00:00+08:00"
    assert payload["review_model_id"] == REVIEW_MODEL_ID
    assert payload["review_quantiles"] == ["P50", "P80", "P90"]
    assert payload["members"] == [
        {
            "forecast_cutoff_at": "2026-02-16T00:00:00+08:00",
            "model_id": REVIEW_MODEL_ID,
            "forecast_quantile": quantile,
        }
        for quantile in ("P50", "P80", "P90")
    ]
    assert sha256_payload(payload) == REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    assert REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256 == (
        "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
    )


def test_install_wires_and_uninstall_restores_empty() -> None:
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    install_into_reviewed_set_loader()
    try:
        assert reviewed_grain_identity_set_artifact_available() is True
        loaded = load_reviewed_grain_identity_set()
        assert len(loaded) == REVIEW_MEMBER_COUNT
        assert tuple(member.forecast_quantile for member in loaded) == REVIEW_QUANTILES
        assert all(member.forecast_cutoff_at.isoformat() == REVIEW_CUTOFF_AT for member in loaded)
        assert all(member.model_id == REVIEW_MODEL_ID for member in loaded)
    finally:
        uninstall_from_reviewed_set_loader()
    assert reviewed_grain_identity_set_artifact_available() is False
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_fail_closed_when_origin_is_not_exact_policy_set() -> None:
    with patch(
        "backend.app.s3_daily_rowset."
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set."
        "replay_identity_origin_entries",
        return_value=(),
    ):
        empty = load_coordinator_reviewed_live_origin_grain_identity_set()
        install_into_reviewed_set_loader()
        try:
            assert empty.artifact_available is False
            assert empty.members == ()
            assert empty.artifact_id == ""
            assert empty.reason_code == "ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS"
            assert reviewed_grain_identity_set_artifact_available() is False
            assert load_reviewed_grain_identity_set() == ()
        finally:
            uninstall_from_reviewed_set_loader()

    extra = (
        *replay_identity_origin_entries(),
        IncumbentForecastArtifactEntry(
            model_id=REVIEW_MODEL_ID,
            forecast_cutoff_at=last_legal_cutoff_before_test(),
            forecast_quantile="P50",
        ),
    )
    with patch(
        "backend.app.s3_daily_rowset."
        "s3_a2_coordinator_reviewed_live_origin_grain_identity_set."
        "replay_identity_origin_entries",
        return_value=extra,
    ):
        mismatched = load_coordinator_reviewed_live_origin_grain_identity_set()
    assert mismatched.artifact_available is False
    assert mismatched.members == ()
    assert mismatched.reason_code == "ORIGIN_ENTRIES_NOT_EXACTLY_THREE_POLICY_GRAINS"


def test_completeness_pass_closeout_remains_unauthorized_without_install() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        result = CompletenessPassCloseoutClassifier().classify()
    assert result.s3_a2_completeness_pass_authorized is False
    assert result.coordinator_reviewed_identity_set_exists is False
    assert result.live_origin_grains_are_reviewed_set is False
    assert result.reviewed_identity_set_member_count == 0
    assert result.no_reviewed_grain_identity_set_in_repository is True
    assert result.weather_unavailable is True
    assert result.plans_unavailable is True
    assert result.weather_and_plans_block_completeness_pass is True
    assert result.forbidden_treat_live_origin_grains_as_reviewed_set is True
    _assert_harvest_replay_and_provider_remain_empty()


def test_completeness_pass_closeout_does_not_flip_pass_after_install() -> None:
    install_into_reviewed_set_loader()
    try:
        with patch("backend.app.db.session.AsyncSessionMaker", None):
            result = CompletenessPassCloseoutClassifier().classify()
        assert result.s3_a2_completeness_pass_authorized is False
        assert result.live_origin_grains_are_reviewed_set is False
        assert result.no_reviewed_grain_identity_set_in_repository is True
        assert result.weather_unavailable is True
        assert result.plans_unavailable is True
        assert result.weather_and_plans_block_completeness_pass is True
        assert result.forbidden_treat_live_origin_grains_as_reviewed_set is True
        assert result.no_bindable_catalog_in_repository is True
        assert result.evaluation_instance_registry_available is False
        assert result.current_s3_daily_rowset_completeness_verified is False
    finally:
        uninstall_from_reviewed_set_loader()
    _assert_harvest_replay_and_provider_remain_empty()


def test_parent_grant_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["flags"][
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED"
    ]
    assert payload["flags"][UNIQUE_FLIP] is False
    assert payload["flags"]["NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY"] is True
    assert payload["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    r1 = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    assert r1["parent_grant_pr"] == PARENT_GRANT_PR
    assert r1["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert r1["parent_grant_commit"] == PARENT_GRANT_COMMIT
    assert r1["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert r1["parent_contract_pr"] == PARENT_CONTRACT_PR
    assert r1["parent_contract_merge"] == PARENT_CONTRACT_MERGE
    assert r1["parent_contract_commit"] == PARENT_CONTRACT_COMMIT
    assert (
        r1["parent_completeness_pass_closeout_r1_commit"]
        == PARENT_COMPLETENESS_PASS_CLOSEOUT_R1_COMMIT
    )
    assert (
        r1["parent_completeness_pass_closeout_r1_evidence_json_sha256"]
        == PARENT_COMPLETENESS_PASS_CLOSEOUT_R1_EVIDENCE_JSON_SHA256
    )
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"][
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED"
    ]
    assert r1["flags"]["NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY"] is False
    assert r1["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert r1["flags"]["NO_BINDABLE_CATALOG_IN_REPOSITORY"] is True
    assert r1["flags"]["EVALUATION_INSTANCE_REGISTRY_AVAILABLE"] is False
    assert r1["flags"]["WEATHER_UNAVAILABLE"] is True
    assert r1["flags"]["PLANS_UNAVAILABLE"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_WEATHER"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_PLANS"] is True
    assert r1["flags"]["WEATHER_AND_PLANS_DO_NOT_BLOCK_NON_CURVE_IMPLEMENTATION"] is True
    assert r1["flags"]["WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS"] is True
    assert r1["flags"]["FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002"] is True
    assert r1["flags"]["FORBIDDEN_INVENT_ADDITIONAL_MEMBERS"] is True
    assert r1["reviewed_set"]["review_member_count"] == 3
    assert r1["reviewed_set"]["identity_sha256"] == (
        "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
    )
    assert GRANT_WORKPAPER.is_file()
    assert R1_WORKPAPER.is_file()


def test_r1_evidence_sha256_payload_matches_embedded_digest() -> None:
    payload = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert len(embedded) == 64


def test_r1_pointers_are_appended_not_rewritten() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert UNIQUE_FLIP + "=true" in live_intro
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=true"
        in live_intro
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in live_intro
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in live_intro
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    assert "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-r1.md" in plan
    assert "## 189." in amendment
    assert "## 188." in amendment
    assert "## 187." in amendment
    assert "## 186." in amendment
    assert UNIQUE_FLIP + "=true" in amendment
    grant_snapshot = amendment.split("## 188.", 1)[1]
    if "## 189." in grant_snapshot:
        grant_snapshot = grant_snapshot.split("## 189.", 1)[0]
    assert UNIQUE_FLIP + "=false" in grant_snapshot
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=true"
        in grant_snapshot
    )
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true" in grant_snapshot
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in grant_snapshot
    r1_snapshot = amendment.split("## 189.", 1)[1]
    if "## 190." in r1_snapshot:
        r1_snapshot = r1_snapshot.split("## 190.", 1)[0]
    assert UNIQUE_FLIP + "=true" in r1_snapshot
    assert "NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false" in r1_snapshot
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in r1_snapshot
    contract_snapshot = amendment.split("## 186.", 1)[1].split("## 187.", 1)[0]
    assert (
        "S3_A2_COORDINATOR_REVIEWED_LIVE_ORIGIN_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=false"
        in contract_snapshot
    )
    contract_pointer = plan.split("### 4.5", maxsplit=1)[0]
    assert "s3-a2-coordinator-reviewed-live-origin-grain-identity-set-r1.md" in contract_pointer


def test_r1_docs_avoid_forbidden_tokens() -> None:
    text = R1_WORKPAPER.read_text(encoding="utf-8") + R1_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = R1_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=可以实施" in workpaper
    assert "IMPLEMENTATION_R1=true" in workpaper
    assert "THIS_PR_IS_NOT_A_GRANT=true" in workpaper
    assert "REVIEW_MEMBER_COUNT=3" in workpaper
    assert "REVIEW_CUTOFF_BUSINESS_DATE=2026-02-16" in workpaper


def test_s3_daily_rowset_has_no_production_init_py() -> None:
    assert PRODUCTION_MODULE.is_file()
    assert not Path("backend/app/s3_daily_rowset/__init__.py").exists()
    assert COMPLETENESS_PASS_CLOSEOUT_MODULE.is_file()
