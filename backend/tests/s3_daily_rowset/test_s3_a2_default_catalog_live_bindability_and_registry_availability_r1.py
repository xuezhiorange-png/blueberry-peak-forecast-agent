"""S3-A2 default catalog live-bindability and registry availability R1 tests."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s3_daily_rowset import (
    s3_a2_default_catalog_live_bindability_and_registry_availability as authority_mod,
)
from backend.app.s3_daily_rowset.binding import (
    BindingClassification,
    BindingReasonCode,
    CatalogBindingCandidate,
    EvaluationInstanceCatalogBindingService,
    expected_catalog_binding_lineage,
)
from backend.app.s3_daily_rowset.catalog_artifact import (
    CatalogArtifactProductionResult,
    CatalogArtifactReasonCode,
    EvaluationInstanceCatalogArtifactProductionService,
)
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset.registry import (
    CatalogSourceKind,
    InMemoryEvaluationInstanceCatalog,
    RegistryCatalogEntry,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_bindable_repository import (
    BindableRepositoryReasonCode,
    DefaultCatalogBindableRepositoryClassifier,
)
from backend.app.s3_daily_rowset.s3_a2_evaluation_instance_registry_available_closeout import (
    AvailableCloseoutReasonCode,
    EvaluationInstanceRegistryAvailableCloseoutClassifier,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY, make_cell

PINNED_CATALOG_ENTRY_COUNT = authority_mod.PINNED_CATALOG_ENTRY_COUNT
PINNED_CATALOG_IDENTITY_SHA256 = authority_mod.PINNED_CATALOG_IDENTITY_SHA256
REGISTRY_SOURCE_STATUS_BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF = (
    authority_mod.REGISTRY_SOURCE_STATUS_BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
)
REVIEW_EVIDENCE_DIGEST_SHA256 = authority_mod.REVIEW_EVIDENCE_DIGEST_SHA256
AuthorityClassification = authority_mod.AuthorityClassification
AuthorityReasonCode = authority_mod.AuthorityReasonCode
DefaultCatalogLiveBindabilityAndRegistryAvailabilityClassifier = (
    authority_mod.DefaultCatalogLiveBindabilityAndRegistryAvailabilityClassifier
)

AUTHORITY_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_live_bindability_and_registry_availability.py"
)
R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-bindability-and-registry-availability-r1.md"
)
R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-bindability-and-registry-availability-r1.json"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-live-bindability-and-registry-availability-authorization.json"
)
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-bindability-and-registry-availability-authorization.md"
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

BASE_MAIN_SHA = "abcaf67b2690d976cdfdd60df407f0a55f4f20d4"
PARENT_GRANT_PR = 529
PARENT_GRANT_MERGE = "abcaf67b2690d976cdfdd60df407f0a55f4f20d4"
PARENT_GRANT_COMMIT = "46af703ea1cd3101e45b581850f45f3c1e15cdd7"
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "5e3a5413a8d29663cd6688237d0accac802235723902fa9b4caed4b3153ac6eb"
)
PARENT_CONTRACT_EVIDENCE_JSON_SHA256 = (
    "d81f0d3f8b4f9fb42496ac0186f91dac6e1164c3b08b765bf445393dd10a8c2c"
)
R1_EVIDENCE_JSON_SHA256 = "da73ada25845803cfb8adda0ef7450a5a85fe8df8bfe57a34dcd7ab8a7f3e951"
CONTENT_IDENTITY_SHA256 = "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
UNIQUE_FLIP = "DETERMINISTIC_DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_IMPLEMENTED"
IMPLEMENTATION_AUTHORIZED = (
    "S3_A2_DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED"
)
GRANT_POINTER_HEADING = (
    "#### Default catalog live-bindability and registry availability implementation "
    "authorization pointer"
)
R1_POINTER_HEADING = "#### Default catalog live-bindability and registry availability R1 pointer"
SECTION_215_HEADING = (
    "## 215. Default catalog live-bindability and registry availability implementation "
    "authorization pointer"
)
SECTION_216_HEADING = (
    "## 216. Default catalog live-bindability and registry availability R1 pointer"
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


def _pinned_catalog_production_result() -> CatalogArtifactProductionResult:
    cutoff = datetime(2026, 2, 16, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    entries = tuple(
        RegistryCatalogEntry(
            cell=make_cell(
                subfarm=f"subfarm-{index}",
                forecast_cutoff_at=cutoff,
                model_id="V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF",
                quantile="P50",
            ),
            partition="TRAIN",
        )
        for index in range(PINNED_CATALOG_ENTRY_COUNT)
    )
    catalog = InMemoryEvaluationInstanceCatalog(
        catalog_entries=entries,
        bound_registry_identity_sha256=PINNED_CATALOG_IDENTITY_SHA256,
        catalog_source_kind=CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF,
    )
    binding = EvaluationInstanceCatalogBindingService(
        dataset_identity=DATASET_IDENTITY,
        candidate=CatalogBindingCandidate(
            catalog=catalog,
            lineage=expected_catalog_binding_lineage(),
        ),
    ).validate()
    return CatalogArtifactProductionResult(
        reason_code=CatalogArtifactReasonCode.ARTIFACT_PRODUCED,
        catalog=catalog,
        catalog_identity_sha256=PINNED_CATALOG_IDENTITY_SHA256,
        binding_result=binding,
    )


def test_authority_module_import_has_no_global_side_effects() -> None:
    clear_v0_2_live_postgres_session_provider()
    importlib.import_module(
        "backend.app.s3_daily_rowset.s3_a2_default_catalog_live_bindability_and_registry_availability"
    )
    clear_v0_2_live_postgres_session_provider()


def test_fail_closed_without_session() -> None:
    clear_v0_2_live_postgres_session_provider()
    with patch("backend.app.db.session.AsyncSessionMaker", None):
        result = DefaultCatalogLiveBindabilityAndRegistryAvailabilityClassifier().classify()
    assert result.reason_code is AuthorityReasonCode.CATALOG_NOT_PRODUCED
    assert result.no_bindable_catalog_in_repository is True
    assert result.evaluation_instance_registry_available is False
    assert result.unique_remaining_gap_closed is False
    clear_v0_2_live_postgres_session_provider()


def test_success_flips_authority_and_registry_flags() -> None:
    production = _pinned_catalog_production_result()
    with patch.object(
        EvaluationInstanceCatalogArtifactProductionService,
        "produce",
        return_value=production,
    ):
        result = DefaultCatalogLiveBindabilityAndRegistryAvailabilityClassifier().classify()
    assert result.reason_code is AuthorityReasonCode.LIVE_BINDABLE_CATALOG
    assert result.authority_classification is AuthorityClassification.LIVE_BINDABLE
    assert result.authorized_live_bindable_classification is True
    assert result.binding_classification is BindingClassification.NOT_BINDABLE
    assert result.binding_reason_code is BindingReasonCode.NOT_BINDABLE
    assert result.in_memory_structural_acceptance is True
    assert result.frozen_binding_classifies_live_bindable is False
    assert result.no_bindable_catalog_in_repository is False
    assert result.evaluation_instance_registry_available is True
    assert result.coordinator_reviewed_available_closeout_exists is True
    assert (
        result.registry_source_status
        == REGISTRY_SOURCE_STATUS_BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
    )
    assert result.registry_snapshot_identity_matches_bound_catalog_identity is True
    assert result.current_s3_daily_rowset_completeness_verified is False
    assert result.live_bindability_implemented is True
    assert result.registry_availability_implemented is True
    assert result.unique_remaining_gap_closed is True
    clear_v0_2_live_postgres_session_provider()


def test_frozen_companion_classifiers_remain_not_bindable() -> None:
    production = _pinned_catalog_production_result()
    with patch.object(
        EvaluationInstanceCatalogArtifactProductionService,
        "produce",
        return_value=production,
    ):
        bindable = DefaultCatalogBindableRepositoryClassifier().classify()
        available = EvaluationInstanceRegistryAvailableCloseoutClassifier().classify()
    assert bindable.reason_code is BindableRepositoryReasonCode.NOT_BINDABLE
    assert bindable.no_bindable_catalog_in_repository is True
    assert (
        available.reason_code
        is AvailableCloseoutReasonCode.AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET
    )
    assert available.evaluation_instance_registry_available is False
    clear_v0_2_live_postgres_session_provider()


def test_frozen_python_blobs_unchanged_except_authority_module() -> None:
    assert _git_blob(CATALOG_PY) == CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(FORECAST_PY) == FORECAST_ARTIFACT_PY_BLOB
    assert _git_blob(BINDING_PY) == BINDING_PY_BLOB
    assert _git_blob(REGISTRY_PY) == REGISTRY_PY_BLOB
    assert _git_blob(BINDABLE_REPOSITORY_PY) == BINDABLE_REPOSITORY_PY_BLOB
    assert _git_blob(AVAILABLE_CLOSEOUT_PY) == AVAILABLE_CLOSEOUT_PY_BLOB
    assert _git_blob(HANDOFF_PY) == HANDOFF_PY_BLOB
    assert AUTHORITY_MODULE.is_file()


def test_r1_evidence_sha256_payload_matches_embedded_digest() -> None:
    payload = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert len(embedded) == 64


def test_r1_docs_avoid_forbidden_tokens() -> None:
    text = R1_WORKPAPER.read_text(encoding="utf-8") + R1_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = R1_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=可以实施" in workpaper
    assert "IMPLEMENTATION_R1=true" in workpaper
    assert "THIS_PR_IS_NOT_A_GRANT=true" in workpaper
    assert UNIQUE_FLIP + "=true" in workpaper
    assert REVIEW_EVIDENCE_DIGEST_SHA256 in workpaper
    assert PINNED_CATALOG_IDENTITY_SHA256 in workpaper


def test_r1_pointers_and_grant_snapshot_isolation() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert UNIQUE_FLIP + "=true" in live_intro
    assert IMPLEMENTATION_AUTHORIZED + "=true" in live_intro
    assert "UNIQUE_REMAINING_GAP_CLOSED=true" in live_intro
    assert "NO_BINDABLE_CATALOG_IN_REPOSITORY=false" in live_intro
    assert "EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true" in live_intro
    r1_pointer = plan.split(R1_POINTER_HEADING, 1)[1]
    if "### 4.5" in r1_pointer:
        r1_pointer = r1_pointer.split("### 4.5", 1)[0]
    assert UNIQUE_FLIP + "=true" in r1_pointer
    assert amendment.count(SECTION_215_HEADING) == 1
    assert amendment.count(SECTION_216_HEADING) == 1
    grant_snapshot = amendment.split(SECTION_215_HEADING, 1)[1]
    if SECTION_216_HEADING in grant_snapshot:
        grant_snapshot = grant_snapshot.split(SECTION_216_HEADING, 1)[0]
    assert IMPLEMENTATION_AUTHORIZED + "=true" in grant_snapshot
    assert UNIQUE_FLIP + "=false" not in grant_snapshot or (
        "DETERMINISTIC_DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_IMPLEMENTED=false"
        in grant_snapshot
    )


def test_parent_grant_pins_remain() -> None:
    grant = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert grant["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert grant["flags"][IMPLEMENTATION_AUTHORIZED] is True
    assert grant["flags"][UNIQUE_FLIP] is False
    r1 = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    assert r1["parent_grant_pr"] == PARENT_GRANT_PR
    assert r1["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert r1["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"]["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert r1["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert r1["flags"]["UNIQUE_REMAINING_GAP_CLOSED"] is True
    assert (
        r1["parent_contract"]["parent_contract_evidence_json_sha256"]
        == PARENT_CONTRACT_EVIDENCE_JSON_SHA256
    )


def test_official_live_classifier_fail_closed_or_success() -> None:
    script = """
import json
from backend.app.s3_daily_rowset.incumbent_forecast_v0_2_live_postgres_read import (
    clear_v0_2_live_postgres_session_provider,
)
from backend.app.s3_daily_rowset import (
    s3_a2_default_catalog_live_bindability_and_registry_availability as mod,
)
result = mod.DefaultCatalogLiveBindabilityAndRegistryAvailabilityClassifier().classify()
clear_v0_2_live_postgres_session_provider()
print(json.dumps({
    "reason_code": result.reason_code.value,
    "no_bindable": result.no_bindable_catalog_in_repository,
    "registry_available": result.evaluation_instance_registry_available,
    "gap_closed": result.unique_remaining_gap_closed,
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip())
    if payload["reason_code"] == AuthorityReasonCode.LIVE_BINDABLE_CATALOG.value:
        assert payload["no_bindable"] is False
        assert payload["registry_available"] is True
        assert payload["gap_closed"] is True
    else:
        assert payload["no_bindable"] is True
        assert payload["registry_available"] is False
        assert payload["gap_closed"] is False
