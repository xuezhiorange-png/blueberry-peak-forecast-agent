import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "docs/v0-9/s2/biological-data-observability-matrix-r1.csv"
SOURCE_REGISTER = ROOT / "docs/v0-9/s2/data-source-authority-register-r1.csv"
EVIDENCE = ROOT / "docs/v0-9/evidence/s2-existing-data-observability-and-gap-audit-r1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_s0_and_all_s1_artifacts_are_pinned_and_verified() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["head_sha"]
    assert evidence["branch"] == "codex/v0-9-version-plan-scope-freeze-r1"
    assert evidence["authority_pins"]["s0_authority_pinned"] is True
    assert evidence["validation"]["s0_hash_pins"] == "PASS"
    assert evidence["validation"]["s1_manifest_hashes"] == "PASS"

    manifest_path = ROOT / evidence["authority_pins"]["s1_manifest_path"]
    assert sha256(manifest_path) == evidence["authority_pins"]["s1_manifest_sha256"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 9
    for item in manifest["files"]:
        assert sha256(ROOT / item["path"]) == item["sha256"]


def test_matrix_covers_all_s1_contract_dimensions_without_duplicate_ids() -> None:
    rows = read_csv(MATRIX)
    ids = [row["variable_id"] for row in rows]
    assert len(ids) == len(set(ids))

    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    coverage = evidence["coverage"]
    dimensions = coverage["matrix_contract_coverage"]
    assert dimensions["biological_state_fields"] == 33
    assert dimensions["phenology_states"] == 21
    assert dimensions["management_event_types"] == 29
    assert dimensions["environment_inputs"] == 10
    assert dimensions["production_systems"] == 3
    assert dimensions["bloom_fruit_cohort_fields"] == 26
    assert dimensions["management_event_metadata_fields"] == 18
    assert dimensions["causal_edges"] == 33
    assert dimensions["quarantined_mechanisms"] == 6
    assert dimensions["environment_observation_metadata"] == 6
    assert dimensions["parameter_contract_fields"] == 13
    assert dimensions["parameter_authority_types"] == 6
    assert dimensions["literature_parameter_candidates"] == 25
    assert evidence["validation"]["full_s1_contract_coverage"] is True
    assert evidence["validation"]["unauthorized_mechanism_promotion_count"] == 0


def test_observability_and_authority_enums_are_separate_and_valid() -> None:
    valid_observability = {
        "AVAILABLE",
        "DERIVABLE",
        "PROXY_AVAILABLE",
        "BUSINESS_CONFIRMATION_REQUIRED",
        "NEW_COLLECTION_REQUIRED",
        "UNOBSERVABLE",
    }
    valid_authority = {
        "AUTHORITATIVE",
        "REVIEWED_SUPPORTING",
        "PRESENT_NOT_AUTHORIZED",
        "PROXY_ONLY",
        "UNKNOWN_AUTHORITY",
        "NOT_PRESENT",
    }
    for row in read_csv(MATRIX):
        assert row["actual_observability_status"] in valid_observability
        assert row["authority_status"] in valid_authority

    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    counts = evidence["coverage"]["actual_observability_status_counts"]
    assert sum(counts.values()) == evidence["coverage"]["total_contract_variables_audited"]


def test_benchmark_and_harvest_boundaries_fail_closed() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["asset_findings"]["benchmark_2025_2026_consumed"] is True
    assert evidence["asset_findings"]["benchmark_reuse_for_selection_allowed"] is False
    assert evidence["asset_findings"]["harvest_is_maturity_observation"] is False
    assert evidence["asset_findings"]["chilling_derivability"] == "CANNOT_DERIVE"
    assert evidence["asset_findings"]["forcing_derivability"] == "CANNOT_DERIVE"
    assert evidence["asset_findings"]["management_event_types_with_executed_records"] == 0
    assert evidence["asset_findings"]["era5_accepted_normalized_hourly_or_daily_rows"] == 0

    sources = {row["source_id"]: row for row in read_csv(SOURCE_REGISTER)}
    assert sources["HARVEST_RAW_2025_2026"]["leakage_class"] == "AUDIT_ONLY"
    assert sources["V08_R2C_BENCHMARK"]["leakage_class"] == "AUDIT_ONLY"
    assert sources["ECMWF_SNAPSHOT"]["leakage_class"] == "PROSPECTIVE_ONLY"
    assert sources["HARVEST_RAW_2024_2025"]["leakage_class"] == "TRAINING_ELIGIBLE"
    assert sources["APP_DB_LIVE_CONTENT"]["data_presence_status"] == "NOT_ASSESSED_BY_SCOPE"
    assert sources["V08_S4_AREA_PRIVATE_MANIFEST"]["source_hash"] == (
        "a52a8342693eb9ce1731e2487e8c23fcf029c198d3fe66193552e4d7f58a27ff"
    )
    assert all(row["quality_status"] for row in sources.values())
    assert all(
        row["source_hash"] for row in sources.values() if row["data_presence_status"] == "PRESENT"
    )
    assert evidence["validation"]["data_source_authority_register_complete"] is True
    assert evidence["validation"]["source_register_duplicate_id_count"] == 0
    assert evidence["validation"]["matrix_missing_source_hash_count"] == 0


def test_public_outputs_have_no_absolute_private_paths_and_hash_manifest_matches() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    public_paths = [
        ROOT / "docs/v0-9/s2/existing-data-observability-and-gap-audit-r1.md",
        MATRIX,
        SOURCE_REGISTER,
        ROOT / "docs/v0-9/s2/minimum-viable-biological-input-set-r1.csv",
        ROOT / "docs/v0-9/s2/minimum-new-data-collection-plan-r1.csv",
        ROOT / "docs/v0-9/s2/s3-prototype-readiness-matrix-r1.csv",
        EVIDENCE,
    ]
    for path in public_paths:
        content = path.read_text(encoding="utf-8")
        assert "/Users/" not in content
        assert "\\Users\\" not in content

    for artifact in evidence["deliverables"]:
        assert sha256(ROOT / artifact["path"]) == artifact["sha256"]
    assert evidence["evidence_self_sha256_excluded"] is True


def test_s2_did_not_start_model_or_later_stage_work() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    scope = evidence["scope"]
    assert scope["model_code_changed"] is False
    assert scope["model_trained"] is False
    assert scope["model_refit"] is False
    assert scope["parameter_fitting"] is False
    assert scope["parameter_selection"] is False
    assert scope["backtest_executed"] is False
    assert scope["s3_started"] is False
    assert scope["s4_started"] is False
    assert scope["deployment_performed"] is False
