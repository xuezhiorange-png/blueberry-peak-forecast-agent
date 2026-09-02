"""S3-A2 default catalog live-bindability and registry availability contract tests."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset.binding import BindingClassification, BindingReasonCode
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
    land_replay_identity_origin_into_sync_session,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_source import (
    IncumbentForecastReplaySource,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
    read_bindable_replay_identity_rows,
)
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_bindable_repository import (
    BindableRepositoryReasonCode,
    DefaultCatalogBindableRepositoryClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_evaluation_instance_registry_available_closeout import (
    AvailableCloseoutReasonCode,
    EvaluationInstanceRegistryAvailableCloseoutClassifier,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY
from backend.tests.s3_daily_rowset.test_s3_a2_live_catalog_execution import (
    _in_season_rows,
    _patch_official_counts,
    _session_maker_with_rows,
)

CONTRACT_PATH = Path(
    "docs/v0-3/s3/s3-default-catalog-live-bindability-and-registry-availability-contract.md"
)
WORKPAPER_PATH = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-bindability-and-registry-availability-contract.md"
)
EVIDENCE_PATH = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-bindability-and-registry-availability-contract.json"
)
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")

BASE_MAIN_SHA = "f5809d30e08be6214852143784b7577d1b0bbcc5"
BASE_MAIN_TREE_SHA = "6415af5372bf8af4d1575f5a6f24283418871efb"
THIS_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "d81f0d3f8b4f9fb42496ac0186f91dac6e1164c3b08b765bf445393dd10a8c2c"
)
PARENT_HANDOFF_R1_PR = 527
PARENT_HANDOFF_R1_MERGE = "f5809d30e08be6214852143784b7577d1b0bbcc5"
PARENT_HANDOFF_R1_EVIDENCE_JSON_SHA256 = (
    "2dd029a946817e0272a2dc352a4181ad9d0cc64a6d96f5ffad3326450b03b94c"
)
CONTENT_IDENTITY_SHA256 = "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
IN_MEMORY_CATALOG_IDENTITY_SHA256 = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
UNIQUE_FLIP = "LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_CONTRACT_AUTHORIZED"
UNIQUE_GAP_SCOPE = "DEFAULT_CATALOG_LIVE_BINDABLE_AUTHORITY_AND_REGISTRY_AVAILABLE_TRANSITION_ONLY"
UNIQUE_REMAINING_GAP = (
    "_no_coordinator_reviewed_authority_to_promote_the_already_produced_structurally_accepted_"
    "default_catalog_into_a_live_bindable_catalog_and_available_evaluation_instance_registry"
)
POINTER_HEADING = "#### Default catalog live-bindability and registry availability contract pointer"
SECTION_214_HEADING = (
    "## 214. Default catalog live-bindability and registry availability contract pointer"
)

CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
FORECAST_ARTIFACT_PY_BLOB = "49938d7107728987439a0a751a1273b73e0022e7"
BINDING_PY_BLOB = "0a335f682a923bcd73908b58cd70cd49c9ab0117"
REGISTRY_PY_BLOB = "ca16d518ab18136059cd08bcf4b247774d750bb5"
BINDABLE_REPOSITORY_PY_BLOB = "98948a405e4865a573f1b2332d128af3aaaccfd3"
AVAILABLE_CLOSEOUT_PY_BLOB = "cafca50d5c4ff4e416747644f7446a7ea24caee9"
HANDOFF_PY_BLOB = "a057802f598aada08e26aed35fb4ad76b4f8c4ce"

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


def test_frozen_production_blobs_unchanged() -> None:
    assert _git_blob(Path("backend/app/s3_daily_rowset/catalog_artifact.py")) == (
        CATALOG_ARTIFACT_PY_BLOB
    )
    assert _git_blob(Path("backend/app/s3_daily_rowset/forecast_artifact.py")) == (
        FORECAST_ARTIFACT_PY_BLOB
    )
    assert _git_blob(Path("backend/app/s3_daily_rowset/binding.py")) == BINDING_PY_BLOB
    assert _git_blob(Path("backend/app/s3_daily_rowset/registry.py")) == REGISTRY_PY_BLOB
    assert (
        _git_blob(Path("backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py"))
        == BINDABLE_REPOSITORY_PY_BLOB
    )
    assert (
        _git_blob(
            Path(
                "backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py"
            )
        )
        == AVAILABLE_CLOSEOUT_PY_BLOB
    )
    assert (
        _git_blob(
            Path(
                "backend/app/s3_daily_rowset/s3_a2_default_catalog_forecast_port_envelope_handoff.py"
            )
        )
        == HANDOFF_PY_BLOB
    )


def test_fail_closed_runtime_preserves_no_bindable_and_registry_unavailable() -> None:
    clear_v0_2_live_postgres_session_provider()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        produced = EvaluationInstanceCatalogArtifactProductionService(
            dataset_identity=DATASET_IDENTITY,
        ).produce()
        bindable = DefaultCatalogBindableRepositoryClassifier().classify()
        available = EvaluationInstanceRegistryAvailableCloseoutClassifier().classify()
    assert produced.reason_code == CatalogArtifactReasonCode.NO_S2_IDENTITY_ALIGNMENT
    assert produced.no_bindable_catalog_in_repository is True
    assert produced.evaluation_instance_registry_available is False
    assert produced.current_s3_daily_rowset_completeness_verified is False
    assert bindable.reason_code is BindableRepositoryReasonCode.CATALOG_NOT_PRODUCED
    assert bindable.no_bindable_catalog_in_repository is True
    assert bindable.evaluation_instance_registry_available is False
    assert available.reason_code is AvailableCloseoutReasonCode.CATALOG_NOT_PRODUCED
    assert available.coordinator_reviewed_available_closeout_exists is False
    assert available.frozen_binding_classifies_live_bindable is False
    assert available.no_bindable_catalog_in_repository is True
    assert available.evaluation_instance_registry_available is False
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def test_patched_session_still_classifies_not_bindable_with_structural_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_rows, validation_rows = _in_season_rows()
    session_maker = _session_maker_with_rows(train_rows, validation_rows)
    _patch_official_counts(
        monkeypatch,
        train_rows=train_rows,
        validation_rows=validation_rows,
    )

    async def _land() -> None:
        async with session_maker() as session:
            await session.run_sync(land_replay_identity_origin_into_sync_session)

    asyncio.run(_land())

    with patch("backend.app.db.session.AsyncSessionMaker", session_maker):
        bindable = DefaultCatalogBindableRepositoryClassifier().classify()
        available = EvaluationInstanceRegistryAvailableCloseoutClassifier().classify()

    assert bindable.reason_code is BindableRepositoryReasonCode.NOT_BINDABLE
    assert bindable.catalog_produced is True
    assert bindable.binding_classification is BindingClassification.NOT_BINDABLE
    assert bindable.binding_reason_code is BindingReasonCode.NOT_BINDABLE
    assert bindable.in_memory_structural_acceptance is True
    assert bindable.no_bindable_catalog_in_repository is True
    assert bindable.evaluation_instance_registry_available is False
    assert (
        available.reason_code
        is AvailableCloseoutReasonCode.AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET
    )
    assert available.coordinator_reviewed_available_closeout_exists is False
    assert available.frozen_binding_classifies_live_bindable is False
    assert available.no_bindable_catalog_in_repository is True
    assert available.evaluation_instance_registry_available is False
    clear_v0_2_live_postgres_session_provider()


FORBIDDEN_AMBIGUOUS_OPTION_PROSE = (
    "does not choose Option A or B",
    "does not choose option a or b",
    "either option must satisfy",
)


def test_contract_rejects_ambiguous_dual_option_prose() -> None:
    text = (
        CONTRACT_PATH.read_text(encoding="utf-8") + WORKPAPER_PATH.read_text(encoding="utf-8")
    ).lower()
    for phrase in FORBIDDEN_AMBIGUOUS_OPTION_PROSE:
        assert phrase not in text


def test_contract_is_authorized_and_not_implementation_grant() -> None:
    text = CONTRACT_PATH.read_text(encoding="utf-8")
    assert f"{UNIQUE_FLIP}=true" in text
    assert "USER_GATE=可以" in text
    assert "INTERPRETED_GATE=CONTRACT_AUTHORING_ONLY" in text
    assert "USER_GATE_AUDIT_CORRECTED=true" in text
    assert "USER_GATE=CONTRACT_AUTHORING_ONLY" not in text
    assert "LIVE_BINDABILITY_IMPLEMENTATION_AUTHORIZED=false" in text
    assert "REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED=false" in text
    assert "CONTRACT_AUTHORED_ONLY=true" in text
    assert "DETERMINISTIC_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_IMPLEMENTED=true" in text
    assert "THIS_PR_IS_NOT_A_GRANT=true" in text
    assert "THIS_PR_IS_NOT_R1=true" in text
    assert "CONTRACT_ONLY=true" in text
    assert f"UNIQUE_GAP_SCOPE={UNIQUE_GAP_SCOPE}" in text
    assert f"UNIQUE_REMAINING_GAP={UNIQUE_REMAINING_GAP}" in text
    assert "UNIQUE_REMAINING_GAP_CLOSED=false" in text
    assert (
        "CURRENT_FIRST_BLOCKER=NO_AUTHORIZED_LIVE_BINDABLE_CATALOG_AND_NO_AVAILABLE_REGISTRY_CLOSEOUT"
        in text
    )
    assert "DO_NOT_DUPLICATE_OLD_FAMILY=true" in text
    assert "CANONICAL_OPTION=SEPARATE_AUTHORITY_CLASSIFIER" in text
    assert "BINDING_PY_REMAINS_FROZEN=true" in text
    assert "DIRECT_BINDING_PY_LIVE_BINDABLE_EXTENSION_IS_NOT_CANONICAL=true" in text
    assert "FROZEN_BINDING_CLASSIFICATION=NOT_BINDABLE" in text
    assert "FROZEN_BINDING_REASON_CODE=NOT_BINDABLE" in text
    assert "FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE=false" in text
    assert "AUTHORIZED_LIVE_BINDABLE_CLASSIFICATION_REQUIRED=true" in text
    assert "FUTURE_AUTHORITY_CLASSIFICATION_SUCCESS=LIVE_BINDABLE" in text
    assert "FUTURE_AUTHORITY_REASON_CODE_SUCCESS=LIVE_BINDABLE_CATALOG" in text
    assert "FORBIDDEN_FUTURE_PREDICATE=FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE=true" in text
    assert "REQUIRED_FUTURE_PREDICATE=AUTHORIZED_LIVE_BINDABLE_CLASSIFICATION=true" in text
    assert "DefaultCatalogLiveBindabilityAndRegistryAvailabilityClassifier" in text
    assert "s3_a2_default_catalog_live_bindability_and_registry_availability.py" in text
    assert "BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF" in text
    assert "NO_VERSIONED_IS_NOT_LIVE_BINDABILITY_PREREQUISITE=true" in text
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in text
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in text
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in text
    assert "CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false" in text
    assert CONTENT_IDENTITY_SHA256 in text
    assert IN_MEMORY_CATALOG_IDENTITY_SHA256 in text
    assert "CATALOG_ENTRY_COUNT=2427" in text
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_evidence_json_sha256_matches_payload_without_self_key() -> None:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    digest = payload["evidence_json_sha256"]
    assert digest == THIS_CONTRACT_EVIDENCE_JSON_SHA256
    stripped = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(stripped) == digest
    assert payload["flags"][UNIQUE_FLIP] is True
    assert payload["flags"]["LIVE_BINDABILITY_IMPLEMENTATION_AUTHORIZED"] is False
    assert payload["flags"]["REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED"] is False
    assert payload["flags"]["NO_BINDABLE_CATALOG_IN_REPOSITORY"] is True
    assert payload["flags"]["EVALUATION_INSTANCE_REGISTRY_AVAILABLE"] is False
    assert payload["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert payload["flags"][
        "DETERMINISTIC_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_IMPLEMENTED"
    ]
    assert payload["user_gate"] == "可以"
    assert payload["interpreted_gate"] == "CONTRACT_AUTHORING_ONLY"
    assert payload["contract_authoring_authorized"] is True
    assert payload["user_gate_audit_corrected"] is True
    canonical = payload["canonical_authority_path"]
    assert canonical["canonical_option"] == "SEPARATE_AUTHORITY_CLASSIFIER"
    assert canonical["binding_py_remains_frozen"] is True
    assert payload["frozen_binding"]["frozen_binding_classifies_live_bindable"] is False
    assert payload["authority_layer"]["future_authority_classification_success"] == (
        "LIVE_BINDABLE"
    )
    assert payload["authority_layer"]["required_future_predicate"] == (
        "AUTHORIZED_LIVE_BINDABLE_CLASSIFICATION=true"
    )
    assert payload["unique_gap"]["unique_gap_scope"] == UNIQUE_GAP_SCOPE
    assert payload["unique_gap"]["unique_remaining_gap"] == UNIQUE_REMAINING_GAP
    assert payload["unique_gap"]["unique_remaining_gap_closed"] is False
    catalog = payload["catalog_artifact"]
    assert catalog["catalog_identity_sha256"] == IN_MEMORY_CATALOG_IDENTITY_SHA256
    assert catalog["catalog_entry_count"] == 2427
    assert payload["audited_repository_sha"] == BASE_MAIN_SHA
    assert payload["audited_repository_tree_sha"] == BASE_MAIN_TREE_SHA
    parent = payload["parent_handoff_r1"]
    assert parent["parent_handoff_r1_pr"] == PARENT_HANDOFF_R1_PR
    assert parent["parent_handoff_r1_merge"] == PARENT_HANDOFF_R1_MERGE
    assert (
        parent["parent_handoff_r1_evidence_json_sha256"] == PARENT_HANDOFF_R1_EVIDENCE_JSON_SHA256
    )


def test_pointer_isolation_and_amendment_section_214() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in live_intro
    assert "LIVE_BINDABILITY_IMPLEMENTATION_AUTHORIZED=false" in live_intro
    assert "REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED=false" in live_intro
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=true" in live_intro
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false" in live_intro
    assert plan.count(POINTER_HEADING) == 1
    pointer = plan.split(POINTER_HEADING, 1)[1]
    if "### 4.5" in pointer:
        pointer = pointer.split("### 4.5", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in pointer
    assert THIS_CONTRACT_EVIDENCE_JSON_SHA256 in pointer
    assert amendment.count(SECTION_214_HEADING) == 1
    section_214 = amendment.split(SECTION_214_HEADING, 1)[1]
    if "\n## " in section_214:
        section_214 = section_214.split("\n## ", 1)[0]
    assert f"{UNIQUE_FLIP}=true" in section_214
    assert "UNIQUE_REMAINING_GAP_CLOSED=false" in section_214


def test_workpaper_avoids_forbidden_tokens() -> None:
    text = WORKPAPER_PATH.read_text(encoding="utf-8")
    assert f"EVIDENCE_JSON_SHA256={THIS_CONTRACT_EVIDENCE_JSON_SHA256}" in text
    assert "USER_GATE=可以" in text
    assert "INTERPRETED_GATE=CONTRACT_AUTHORING_ONLY" in text
    assert "CANONICAL_OPTION=SEPARATE_AUTHORITY_CLASSIFIER" in text
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered


def test_future_authority_module_not_created_in_contract_pr() -> None:
    assert not Path(
        "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_bindability_and_registry_availability.py"
    ).exists()
