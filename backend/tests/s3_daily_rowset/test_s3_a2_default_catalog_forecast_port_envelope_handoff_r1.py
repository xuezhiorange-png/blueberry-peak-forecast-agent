"""S3-A2 default catalog forecast-port envelope handoff R1 tests."""

from __future__ import annotations

import importlib
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
    IncumbentForecastArtifactEntry,
)
from backend.app.s3_daily_rowset.forecast_artifact import (
    IncumbentForecastArtifactAdapter,
    VersionedIncumbentForecastArtifact,
)
from backend.app.s3_daily_rowset.incumbent_forecast_artifact_content import (
    IncumbentForecastArtifactContentProducer,
)
from backend.app.s3_daily_rowset.incumbent_forecast_replay_identity_origin import (
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
)
from backend.app.s3_daily_rowset.registry import CatalogSourceKind
from backend.app.s3_daily_rowset.s2_identity_alignment_harvest_source import (
    S2IdentityAlignmentHarvestSource,
)
from backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set import (
    REVIEW_CUTOFF_AT,
    REVIEW_MEMBER_COUNT,
    REVIEW_MODEL_ID,
    REVIEW_QUANTILES,
    REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256,
    load_coordinator_reviewed_live_origin_grain_identity_set,
    uninstall_from_reviewed_set_loader,
)
from backend.app.s3_daily_rowset.s3_a2_default_catalog_forecast_port_envelope_handoff import (
    deterministic_coordinator_reviewed_grains_forecast_artifact,
)
from backend.tests.s3_daily_rowset.conftest import DATASET_IDENTITY

HANDOFF_MODULE = Path(
    "backend/app/s3_daily_rowset/s3_a2_default_catalog_forecast_port_envelope_handoff.py"
)
R1_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-forecast-port-envelope-handoff-r1.md"
)
R1_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-forecast-port-envelope-handoff-r1.json"
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
GRANT_WORKPAPER = Path(
    "docs/v0-3/s3/workpapers/s3-a2-default-catalog-forecast-port-envelope-handoff-authorization.md"
)
GRANT_EVIDENCE = Path(
    "docs/v0-3/s3/evidence/s3-a2-default-catalog-forecast-port-envelope-handoff-authorization.json"
)
CONTRACT_DOC = Path("docs/v0-3/s3/s3-default-catalog-forecast-port-envelope-handoff-contract.md")
AMENDMENT = Path("docs/v0-3/s3/s3-daily-rowset-amendment.md")
DEVELOPMENT_PLAN = Path("docs/v0-3/development-plan.md")

BASE_MAIN_SHA = "916725cd2f2bd6992acf94829d9c9c293866db6f"
BASE_MAIN_TREE_SHA = "40129dcfe1e5c2a3c6241ca1adde2168484cec82"
PARENT_GRANT_PR = 526
PARENT_GRANT_MERGE = "916725cd2f2bd6992acf94829d9c9c293866db6f"
PARENT_GRANT_COMMIT = "85cdc59d75c2123689fa9c1a94fc3954eeebc19d"
PARENT_GRANT_EVIDENCE_JSON_SHA256 = (
    "4d6f979e725254373d53561a2dc96d62394784f2ddbd5e8422996a4bb50012c2"
)
REVIEWED_SET_IDENTITY_SHA256 = "76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3"
CONTENT_IDENTITY_SHA256 = "06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5"
IN_MEMORY_CATALOG_IDENTITY_SHA256 = (
    "00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af"
)
IN_MEMORY_CATALOG_ENTRY_COUNT = 2427
UNIQUE_FLIP = "DETERMINISTIC_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_IMPLEMENTED"
IMPLEMENTATION_AUTHORIZED = (
    "S3_A2_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_IMPLEMENTATION_AUTHORIZED"
)
CONTRACT_AUTHORIZED = "S3_A2_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_CONTRACT_AUTHORIZED"
GRANT_POINTER_HEADING = (
    "#### Default catalog forecast-port envelope handoff implementation authorization pointer"
)
R1_POINTER_HEADING = "#### Default catalog forecast-port envelope handoff R1 pointer"
SECTION_212_HEADING = (
    "## 212. Default catalog forecast-port envelope handoff implementation authorization pointer"
)
SECTION_213_HEADING = "## 213. Default catalog forecast-port envelope handoff R1 pointer"
REVIEW_EVIDENCE_DIGEST_SHA256 = "40e03141b52188cafe9e9cb6842d14f2ebd6caa3abe1fd80142ad71162781f64"
PARENT_GRANT_PR = 526
CATALOG_ARTIFACT_PY_BLOB = "8196cb7dca33df8708f78789bd2eb9e8243b8354"
FORECAST_ARTIFACT_PY_BLOB = "49938d7107728987439a0a751a1273b73e0022e7"
HANDOFF_PY_BLOB = "a057802f598aada08e26aed35fb4ad76b4f8c4ce"
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


def _git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


def _assert_harvest_replay_and_provider_remain_empty() -> None:
    clear_v0_2_live_postgres_session_provider()
    assert S2IdentityAlignmentHarvestSource().obtain() == ()
    assert IncumbentForecastReplaySource().obtain() == ()
    assert read_bindable_replay_identity_rows() == ()


def _clear_live_origin_construction_cache() -> None:
    import backend.app.s3_daily_rowset.s3_a2_default_catalog_live_origin_construction as loc

    loc._cached_maker_id = loc._CACHE_MISS
    loc._cached_bundle = None
    loc._nested_load = False
    loc._nested_bundle = None


@pytest.fixture(autouse=True)
def _uninstall_reviewed_set_hooks() -> Iterator[None]:
    uninstall_from_reviewed_set_loader()
    _clear_live_origin_construction_cache()
    yield
    uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()
    _clear_live_origin_construction_cache()


def test_handoff_module_import_has_no_loader_or_produce_side_effects() -> None:
    uninstall_from_reviewed_set_loader()
    clear_v0_2_live_postgres_session_provider()
    importlib.import_module(
        "backend.app.s3_daily_rowset.s3_a2_default_catalog_forecast_port_envelope_handoff"
    )
    assert load_reviewed_grain_identity_set() == ()
    _assert_harvest_replay_and_provider_remain_empty()


def test_handoff_produces_expected_content_identity() -> None:
    produced = deterministic_coordinator_reviewed_grains_forecast_artifact()
    assert produced is not None
    assert produced.content_identity_sha256 == CONTENT_IDENTITY_SHA256
    assert len(produced.rows) == 3
    assert (
        produced.catalog_source_kind
        == CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
    )
    assert produced.uses_harvest_date_as_forecast_cutoff is False


def test_bare_default_catalog_produce_succeeds_without_forecast_port_injection() -> None:
    _assert_harvest_replay_and_provider_remain_empty()
    first = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()
    second = EvaluationInstanceCatalogArtifactProductionService(
        dataset_identity=DATASET_IDENTITY,
    ).produce()
    assert first.reason_code is CatalogArtifactReasonCode.ARTIFACT_PRODUCED
    assert second.reason_code is CatalogArtifactReasonCode.ARTIFACT_PRODUCED
    assert first.catalog_identity_sha256 == second.catalog_identity_sha256
    assert first.catalog_identity_sha256 == IN_MEMORY_CATALOG_IDENTITY_SHA256
    assert len(first.catalog.entries()) == IN_MEMORY_CATALOG_ENTRY_COUNT
    _assert_harvest_replay_and_provider_remain_empty()
    assert load_reviewed_grain_identity_set() == ()


def test_handoff_forecast_artifact_content_determinism() -> None:
    first = deterministic_coordinator_reviewed_grains_forecast_artifact()
    second = deterministic_coordinator_reviewed_grains_forecast_artifact()
    assert first is not None
    assert second is not None
    assert first.content_identity_sha256 == second.content_identity_sha256
    assert first.content_identity_sha256 == CONTENT_IDENTITY_SHA256


def test_explicit_artifact_injection_precedence_preserved() -> None:
    injected = VersionedIncumbentForecastArtifact(
        content_identity_sha256="injected-only-forecast-artifact-hash-for-tests",
        rows=(
            IncumbentForecastArtifactEntry(
                model_id="injected-model",
                forecast_cutoff_at=load_coordinator_reviewed_live_origin_grain_identity_set()
                .members[0]
                .forecast_cutoff_at,
                forecast_quantile="P50",
            ),
        ),
        catalog_source_kind=CatalogSourceKind.BOUND_FIXTURE,
        uses_harvest_date_as_forecast_cutoff=False,
    )
    adapter = IncumbentForecastArtifactAdapter(artifact=injected)
    resolved = adapter._resolved_artifact()
    assert resolved is injected
    assert resolved.content_identity_sha256 == "injected-only-forecast-artifact-hash-for-tests"


def test_fail_closed_when_reviewed_origin_not_exact_policy_set() -> None:
    with patch(
        "backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set."
        "replay_identity_origin_entries",
        return_value=(),
    ):
        assert deterministic_coordinator_reviewed_grains_forecast_artifact() is None

    extra = (
        *replay_identity_origin_entries(),
        IncumbentForecastArtifactEntry(
            model_id=REVIEW_MODEL_ID,
            forecast_cutoff_at=last_legal_cutoff_before_test(),
            forecast_quantile="P50",
        ),
    )
    with patch(
        "backend.app.s3_daily_rowset.s3_a2_coordinator_reviewed_live_origin_grain_identity_set."
        "replay_identity_origin_entries",
        return_value=extra,
    ):
        assert deterministic_coordinator_reviewed_grains_forecast_artifact() is None


def test_fail_closed_when_content_producer_returns_none() -> None:
    with patch(
        "backend.app.s3_daily_rowset.incumbent_forecast_artifact_content."
        "IncumbentForecastArtifactContentProducer.produce",
        return_value=None,
    ):
        assert deterministic_coordinator_reviewed_grains_forecast_artifact() is None


def test_fail_closed_when_content_identity_mismatches_expected() -> None:
    wrong = VersionedIncumbentForecastArtifact(
        content_identity_sha256="wrong-content-identity-hash-for-handoff-fail-closed",
        rows=(
            IncumbentForecastArtifactEntry(
                model_id=REVIEW_MODEL_ID,
                forecast_cutoff_at=load_coordinator_reviewed_live_origin_grain_identity_set()
                .members[0]
                .forecast_cutoff_at,
                forecast_quantile="P50",
            ),
        ),
        catalog_source_kind=CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF,
        uses_harvest_date_as_forecast_cutoff=False,
    )
    with patch(
        "backend.app.s3_daily_rowset.incumbent_forecast_artifact_content."
        "IncumbentForecastArtifactContentProducer.produce",
        return_value=wrong,
    ):
        assert deterministic_coordinator_reviewed_grains_forecast_artifact() is None


def test_frozen_companion_blobs_unchanged_except_forecast_and_handoff() -> None:
    assert _git_blob(CATALOG_PY) == CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(TEST_CATALOG_PY) == TEST_CATALOG_ARTIFACT_PY_BLOB
    assert _git_blob(CONTENT_PY) == CONTENT_PRODUCER_PY_BLOB
    assert _git_blob(CONTENT_FOR_REVIEWED_PY) == CONTENT_FOR_REVIEWED_GRAINS_PY_BLOB
    assert _git_blob(COORDINATOR_PY) == COORDINATOR_REVIEWED_SET_PY_BLOB
    assert _git_blob(CATALOG_CLOSEOUT_PY) == CATALOG_NO_VERSIONED_CLOSEOUT_PY_BLOB
    assert _git_blob(FORECAST_PY) == FORECAST_ARTIFACT_PY_BLOB
    assert _git_blob(HANDOFF_MODULE) == HANDOFF_PY_BLOB


def test_reviewed_set_identity_and_members_match_contract_pins() -> None:
    identity_set = load_coordinator_reviewed_live_origin_grain_identity_set()
    assert identity_set.artifact_available is True
    assert identity_set.artifact_id == REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256
    assert identity_set.artifact_id == REVIEWED_SET_IDENTITY_SHA256
    assert len(identity_set.members) == REVIEW_MEMBER_COUNT
    assert identity_set.review_cutoff_at == REVIEW_CUTOFF_AT
    assert identity_set.review_model_id == REVIEW_MODEL_ID
    assert identity_set.review_quantiles == REVIEW_QUANTILES


def test_default_empty_content_producer_still_none_without_handoff_rows() -> None:
    assert IncumbentForecastArtifactContentProducer().produce() is None


def test_handoff_module_avoids_forbidden_tokens() -> None:
    source = HANDOFF_MODULE.read_text(encoding="utf-8")
    lowered = source.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered, token
    assert "IncumbentForecastArtifactContentForReviewedGrainsClassifier" not in source
    assert "install_into_reviewed_set_loader" not in source
    assert "set_v0_2_live_postgres_session_provider" not in source


def test_r1_evidence_sha256_payload_without_self_key() -> None:
    payload = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    embedded = payload["evidence_json_sha256"]
    without = {key: value for key, value in payload.items() if key != "evidence_json_sha256"}
    assert sha256_payload(without) == embedded
    assert len(embedded) == 64


def test_r1_pointer_isolation_grant_snapshot_still_implemented_false() -> None:
    plan = DEVELOPMENT_PLAN.read_text(encoding="utf-8")
    amendment = AMENDMENT.read_text(encoding="utf-8")
    live_intro = plan.split("### 4.4", 1)[1].split("The future S3 acceptance", 1)[0]
    assert UNIQUE_FLIP + "=true" in live_intro
    assert UNIQUE_FLIP + "=false" not in live_intro
    assert IMPLEMENTATION_AUTHORIZED + "=true" in live_intro
    assert CONTRACT_AUTHORIZED + "=true" in live_intro
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in live_intro
    assert "S3_A2_COMPLETENESS_PASS_AUTHORIZED=false" in live_intro
    grant_pointer = plan.split(GRANT_POINTER_HEADING, 1)[1]
    if R1_POINTER_HEADING in grant_pointer:
        grant_pointer = grant_pointer.split(R1_POINTER_HEADING, 1)[0]
    if "### 4.5" in grant_pointer:
        grant_pointer = grant_pointer.split("### 4.5", 1)[0]
    assert IMPLEMENTATION_AUTHORIZED + "=true" in grant_pointer
    assert UNIQUE_FLIP + "=false" in grant_pointer
    r1_pointer = plan.split(R1_POINTER_HEADING, 1)[1]
    if "### 4.5" in r1_pointer:
        r1_pointer = r1_pointer.split("### 4.5", 1)[0]
    assert UNIQUE_FLIP + "=true" in r1_pointer
    assert "BARE_DEFAULT_CATALOG_REASON=ARTIFACT_PRODUCED" in r1_pointer
    assert "THIS_R1_DOES_NOT_FLIP_NO_VERSIONED=true" in r1_pointer
    assert "UNIQUE_REMAINING_GAP_CLOSED=true" in r1_pointer
    assert CONTENT_IDENTITY_SHA256 in r1_pointer
    assert REVIEW_EVIDENCE_DIGEST_SHA256 in r1_pointer
    assert amendment.count(SECTION_212_HEADING) == 1
    assert amendment.count(SECTION_213_HEADING) == 1
    assert plan.count(GRANT_POINTER_HEADING) == 1
    assert plan.count(R1_POINTER_HEADING) == 1
    grant_snapshot = amendment.split(SECTION_212_HEADING, 1)[1]
    if SECTION_213_HEADING in grant_snapshot:
        grant_snapshot = grant_snapshot.split(SECTION_213_HEADING, 1)[0]
    assert UNIQUE_FLIP + "=false" in grant_snapshot
    r1_snapshot = amendment.split(SECTION_213_HEADING, 1)[1]
    if "\n## " in r1_snapshot:
        r1_snapshot = r1_snapshot.split("\n## ", 1)[0]
    assert UNIQUE_FLIP + "=true" in r1_snapshot
    assert "BARE_DEFAULT_CATALOG_REASON=ARTIFACT_PRODUCED" in r1_snapshot
    assert "NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true" in r1_snapshot


def test_r1_docs_avoid_forbidden_tokens() -> None:
    text = R1_WORKPAPER.read_text(encoding="utf-8") + R1_EVIDENCE.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in FORBIDDEN_PROSE_TOKENS:
        assert token.lower() not in lowered, token
    workpaper = R1_WORKPAPER.read_text(encoding="utf-8")
    assert "USER_GATE=可以实施" in workpaper
    assert "USER_GATE_RECEIVED_DURING_DRAFT_REVIEW_CORRECTION=true" in workpaper
    assert "ORIGINAL_DRAFT_PRECEDED_EXPLICIT_GATE=true" in workpaper
    assert "NO_RETROACTIVE_AUTHORIZATION_CLAIM=true" in workpaper
    assert "User said 「可以实施」" not in workpaper
    assert "IMPLEMENTATION_R1=true" in workpaper
    assert "THIS_PR_IS_NOT_A_GRANT=true" in workpaper
    assert UNIQUE_FLIP + "=true" in workpaper
    assert CONTENT_IDENTITY_SHA256 in workpaper
    assert REVIEW_EVIDENCE_DIGEST_SHA256 in workpaper
    assert "THIS_R1_DOES_NOT_FLIP_NO_VERSIONED=true" in workpaper
    assert "UNIQUE_REMAINING_GAP_CLOSED=true" in workpaper
    assert "LATER_R1_MUST_NOT_FLIP_NO_VERSIONED" not in workpaper


def test_parent_grant_pins_remain() -> None:
    payload = json.loads(GRANT_EVIDENCE.read_text(encoding="utf-8"))
    assert payload["evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert payload["flags"][IMPLEMENTATION_AUTHORIZED] is True
    assert payload["flags"][UNIQUE_FLIP] is False
    r1 = json.loads(R1_EVIDENCE.read_text(encoding="utf-8"))
    assert r1["parent_grant_pr"] == PARENT_GRANT_PR
    assert r1["parent_grant_merge"] == PARENT_GRANT_MERGE
    assert r1["parent_grant_commit"] == PARENT_GRANT_COMMIT
    assert r1["parent_grant_evidence_json_sha256"] == PARENT_GRANT_EVIDENCE_JSON_SHA256
    assert r1["flags"][UNIQUE_FLIP] is True
    assert r1["flags"]["NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY"] is True
    assert r1["flags"]["S3_A2_COMPLETENESS_PASS_AUTHORIZED"] is False
    assert r1["flags"]["THIS_R1_DOES_NOT_FLIP_NO_VERSIONED"] is True
    assert r1["flags"]["UNIQUE_REMAINING_GAP_CLOSED"] is True
    assert r1["flags"]["BARE_DEFAULT_CATALOG_REASON"] == "ARTIFACT_PRODUCED"
    assert r1["authorization_chronology"]["no_retroactive_authorization_claim"] is True
    assert r1["authorization_chronology"]["current_correction_and_validation_authorized"] is True
    assert r1["review"]["content_identity_sha256"] == CONTENT_IDENTITY_SHA256
    assert r1["review"]["review_evidence_digest_sha256"] == REVIEW_EVIDENCE_DIGEST_SHA256
    assert r1["review"]["in_memory_catalog_identity_sha256"] == IN_MEMORY_CATALOG_IDENTITY_SHA256
    assert r1["review"]["in_memory_catalog_entry_count"] == IN_MEMORY_CATALOG_ENTRY_COUNT
