"""Offline R2 receipt integrity, not new prediction/scoring or network activity."""

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
FILE = ROOT / "docs/v0-17/evidence/v0.17-s6-cross-surface-product-acceptance-r2.json"


def load():
    return json.loads(FILE.read_text())


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_canonical_receipt_and_generated_matrices():
    paths = [FILE, *FILE.parent.joinpath("s6-cross-surface-r2").glob("*.json")]
    for path in paths:
        assert (
            path.read_text()
            == json.dumps(
                json.loads(path.read_text()), ensure_ascii=False, sort_keys=True, indent=2
            )
            + "\n"
        )


@pytest.mark.parametrize(
    "group",
    ["source_evidence_sha256", "artifact_sha256", "screenshot_sha256", "historical_copy_sha256"],
)
def test_all_pins_match_repository_bytes(group):
    first = json.loads(
        FILE.parent.joinpath("v0.17-s6-postmerge-route-lifecycle-correction-r1.json").read_text()
    )
    second = json.loads(
        FILE.parent.joinpath("v0.17-s6-postmerge-route-lifecycle-correction-r2.json").read_text()
    )
    assert set(first["historical_source_bindings"]) == {
        "frontend/e2e/dashboard.spec.ts",
        "backend/tests/e2e/test_v0_17_s6_evidence_contract.py",
    }
    for path, expected in load()[group].items():
        if group == "source_evidence_sha256" and path in second["historical_source_bindings"]:
            binding = second["historical_source_bindings"][path]
            prior = first["historical_source_bindings"].get(path)
            if prior is not None:
                assert prior["historical_sha256"] == expected
                assert prior["current_sha256"] == binding["historical_sha256"]
                assert hash_file(ROOT / prior["archive_path"]) == expected
            else:
                assert binding["historical_sha256"] == expected
            assert hash_file(ROOT / binding["archive_path"]) == binding["historical_sha256"]
            assert hash_file(ROOT / path) == binding["current_sha256"]
            continue
        if group == "source_evidence_sha256" and path in first["historical_source_bindings"]:
            binding = first["historical_source_bindings"][path]
            assert binding["historical_sha256"] == expected
            assert hash_file(ROOT / binding["archive_path"]) == expected
            assert hash_file(ROOT / path) == binding["current_sha256"]
            continue
        assert hash_file(ROOT / path) == expected, path


def test_original_seven_and_correction_chain_are_not_rewritten():
    receipt = load()
    correction = json.loads(
        (
            ROOT / "docs/v0-17/evidence/v0.17-s6-selector-cancel-reopen-correction-r1.json"
        ).read_text()
    )
    assert receipt["original_r1_artifacts_sha256"] == correction["original_s6_artifacts_sha256"]
    assert len(receipt["historical_copy_sha256"]) == 7
    assert receipt["correction"]["pr"] == 705
    assert receipt["correction"]["merge_sha"] == receipt["base_main_sha"]
    historical = (
        ROOT
        / "docs/v0-17/evidence/s6-cross-surface-r2/historical-r1/docs/v0-17/evidence"
        / "v0.17-s6-cross-surface-product-acceptance-r1.json"
    )
    assert json.loads(historical.read_text())["result"] == "BLOCKED"


def test_all_screenshots_have_exact_fresh_test_provenance():
    receipt = load()
    provenance = json.loads(
        FILE.parent.joinpath("s6-cross-surface-r2/screenshot-provenance.json").read_text()
    )
    records = provenance["screenshots"]
    report_path = FILE.parent.joinpath("s6-cross-surface-r2/screenshot-execution-report.json")
    report = json.loads(report_path.read_text())
    assert (
        hashlib.sha256(report_path.read_bytes()).hexdigest() == provenance["public_report_sha256"]
    )
    assert report["cases"] == records
    assert report["raw_report_sha256"] == provenance["browser_report_sha256"]
    assert len(records) == 44
    assert len({r["source_artifact_path"] for r in records}) == 44
    assert len({r["archive_path"] for r in records}) == 44
    assert {r["archive_path"]: r["sha256"] for r in records} == receipt["screenshot_sha256"]
    for record in records:
        assert record["execution_id"] == provenance["execution_id"]
        assert record["test_file"] == "e2e/dashboard-cross-surface.spec.ts"
        assert record["test_id"] and record["report_spec_id"] and record["test_title"]
        assert record["test_id"] == record["report_spec_id"]
        assert record["test_result_status"] == "passed"
        assert record["project"] in ("chromium-desktop", "chromium-mobile")
        assert not Path(record["source_artifact_path"]).is_absolute()
    assert provenance["duplicate_destination_policy"] == "REJECT_BEFORE_COPY"


def test_complete_executed_matrix_and_real_sdk_parity():
    receipt = load()
    assert receipt["test_counts"]["parity"] == 25
    assert receipt["test_counts"]["permissions"] == 22
    assert receipt["test_counts"]["failures"] == 12
    assert receipt["test_counts"]["browser"] == 60
    assert receipt["execution"]["real_mcp_sdk_client_session"]
    assert receipt["execution"]["same_database_http_mcp_browser"]
    assert receipt["execution"]["mcp_tool_count"] == 8
    assert receipt["source_evidence_count"] == len(receipt["source_evidence_sha256"])
    assert receipt["screenshot_count"] == len(receipt["screenshot_sha256"])
    matrix = json.loads(FILE.parent.joinpath("s6-cross-surface-r2/parity-matrix.json").read_text())
    assert {row["tool"] for row in matrix} == {
        "get_forecast_overview",
        "get_forecast_curve",
        "get_hierarchical_forecast",
        "get_forecast_uncertainty",
        "get_forecast_attribution",
        "get_forecast_quality",
        "simulate_capacity",
        "compare_capacity_scenarios",
    }
    assert all(row["http_mcp_full_json_equality"] == "PASS" for row in matrix)


def test_no_production_or_governance_overclaim():
    receipt = load()
    assert not any(receipt["production_gaps"].values())
    governance = receipt["governance"]
    assert governance["s6_authorized"] and governance["s6_resume_authorized"]
    assert governance["stop"]
    assert not any(
        value
        for key, value in governance.items()
        if key not in ("s6_authorized", "s6_resume_authorized", "stop")
    )
    for key in (
        "post_seed_business_dml_count",
        "unauthorized_sql_count",
        "unauthorized_business_execution_count",
    ):
        assert receipt["execution"][key] == 0
    for key in (
        "current_actual_accessed",
        "private_data_accessed",
        "model_training",
        "new_forecast_execution",
    ):
        assert not receipt["execution"][key]


def test_real_device_limitations_and_all_thirty_viewport_pages():
    qa = json.loads(
        FILE.parent.joinpath("s6-cross-surface-r2/accessibility-results.json").read_text()
    )
    assert qa["unique_page_viewport_combinations"] == 30
    for key in ("real_ios_safari", "soft_keyboard", "screen_reader"):
        assert qa[key] == "NOT_VALIDATED"
    paths = load()["screenshot_sha256"]
    for width, height in qa["viewports"]:
        for page in ("overview", "forecast", "attribution", "capacity", "quality"):
            assert any(path.endswith(f"/{page}-{width}x{height}.jpg") for path in paths)


def test_five_page_eight_state_contract_never_fabricates_ready_authority():
    state = json.loads(
        FILE.parent.joinpath("s6-cross-surface-r2/failure-state-matrix.json").read_text()
    )
    assert len(state["states"]) == 5
    for page in state["states"].values():
        assert set(page) == {
            "LOADING",
            "READY",
            "EMPTY",
            "PARTIAL",
            "NOT_AVAILABLE",
            "ERROR",
            "AUTHORITY_MISMATCH",
            "NO_CURRENT_ACTUAL",
        }
    assert "NOT_FABRICATED" in state["states"]["ATTRIBUTION"]["READY"]["runtime_scope"]


def test_public_receipt_does_not_embed_runtime_credentials_or_private_paths():
    receipt = load()
    strings = [FILE.read_text()]
    strings.extend((ROOT / path).read_text() for path in receipt["artifact_sha256"])
    for text in strings:
        for forbidden in (
            "/Users/",
            "/private/tmp/",
            "postgresql://",
            "postgresql+asyncpg://",
            "Authorization: Bearer",
            "SYNTHETIC_S6_SERVER_ONLY_CREDENTIAL",
        ):
            assert forbidden not in text
