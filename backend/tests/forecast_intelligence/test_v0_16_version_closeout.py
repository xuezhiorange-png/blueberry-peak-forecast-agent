"""Public frozen evidence only: no network, model, labels or experiment replay."""

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PATH = "docs/v0-16/evidence/v0.16.0-version-closeout-r1.json"
MANIFEST_PATH = "docs/v0-16/evidence/v0.16.0-version-closeout-manifest-r1.json"
MARKDOWN_PATH = "docs/v0-16/v0.16.0-closeout.md"
BASELINE = "b69e526a7a6d7c40bd22351cf16bad6c8befea14"
HEADS = (
    "33c57978789f78ed5f84f8343b283043ba04334a",
    "ec730ad1af5255eb808c169b248ceba0aaf332da",
    "49f9601564d1815cb3db1bfaa9c7d63a52676ec4",
    "4fd9279b434855baee1c32a35b50ed24373248ca",
    "49dee1b5717c2586679e854139f96468f1e5f5b2",
    "8c2e020e66a845edc1f860df56c067e50cb2c77e",
    "a1eb9b764e4e74282b61353e22d026264a60798c",
)
MERGES = (
    "1ae86e698803d5b581f79d460076d3238c23de4f",
    "b1ae3f06f982999af68ac4bdb0b2f0b94a845f24",
    "fa3958fa19e01676030f1f1f2d5451d8c9a8754a",
    "0d14913bcff599a24491c71e9d99ef88021e68db",
    "0084981e92869b24cad90dd1a066a125e73a8ba3",
    "6ab5d04463b516f8e9284ad586a7352d165d2f04",
    "97b76794ae0baa1cc06a9543b9ffe4b1b527e29b",
)
PR_RUNS = (
    37493305606,
    37554085687,
    37563638094,
    37574075477,
    37597910219,
    37616948941,
    37633143132,
)
MAIN_RUNS = (
    37548297293,
    37558144442,
    37567442986,
    37577683488,
    37602971084,
    37622083956,
    37638655954,
)
POLICY_HASHES = {
    "S2": "f35f2700011f440569c9a0140dc9deb482281d60190e8a601b5a503c79013efd",
    "S3": "950d7d4885c4a96b43bba5ad6b586ee7a424ae86482618a8be22ed272039a422",
    "S4": "6dfe2c1ac684844af636d936b5797d301e80f015c9e3dd880a102127a169ac1c",
    "S5": "740c0a48506b524ea822b88ad9c5b3443cf3356969026e02cff4a6e1a3c446b7",
    "S6": "c1712c6596a813816eefbcb8d51c7088304549cfcc1899a637dff1b150be6463",
}


def canonical(value):
    return (
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode()


def read(name):
    path = Path(name)
    assert not path.is_absolute() and ".." not in path.parts
    assert path.parts[0] in {"docs", "backend", "scripts"}
    assert path.suffix in {".json", ".md", ".py"}
    return (ROOT / path).read_bytes()


def load(name):
    return json.loads(read(name))


EVIDENCE = load(EVIDENCE_PATH)
MANIFEST = load(MANIFEST_PATH)


def test_frozen_source_map_cannot_be_rewritten_alongside_sources():
    assert hashlib.sha256(canonical(EVIDENCE["source_evidence_sha256"])).hexdigest() == (
        "a7074dffd3be78f34e4c5026ce1db67b508011e2ba2835fee97c8125d1a2d49d"
    )
    assert EVIDENCE["source_evidence_count"] == len(EVIDENCE["source_evidence_sha256"])
    scope = load("docs/v0-16/evidence/v0.16.0-version-plan-and-scope-freeze-r1.json")
    assert scope["S5_IMPLEMENTATION_AUTHORIZED"] is False
    assert scope["S6_IMPLEMENTATION_AUTHORIZED"] is False
    for stage, directory, filename in (
        (4, "forecastops-monitoring-r1", "v0.16-s4-forecastops-monitoring-r1.json"),
        (5, "business-loss-contract-r1", "v0.16-s5-business-loss-contract-r1.json"),
        (6, "what-if-decision-simulator-r1", "v0.16-s6-what-if-decision-simulator-r1.json"),
    ):
        snapshot = load(f"docs/v0-16/evidence/{directory}/{filename}")
        assert snapshot[f"s{stage}_formal_complete"] is False


def test_closeout_test_has_no_business_engine_or_external_execution_dependency():
    tree = ast.parse(Path(__file__).read_text())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module)
    assert imports == {"ast", "hashlib", "json", "re", "pathlib", "pytest"}


@pytest.mark.parametrize("name", [EVIDENCE_PATH, MANIFEST_PATH])
def test_canonical_bytes(name):
    value = load(name)
    assert read(name) == canonical(value)
    assert canonical(dict(reversed(list(value.items())))) == read(name)


def test_manifest_members_and_scope():
    assert MANIFEST["schema"] == "V0_16_VERSION_CLOSEOUT_MANIFEST_R1"
    assert set(MANIFEST["members"]) == {EVIDENCE_PATH, MARKDOWN_PATH}
    for name, expected in MANIFEST["members"].items():
        assert hashlib.sha256(read(name)).hexdigest() == expected
    assert MANIFEST["source_evidence_count"] == len(EVIDENCE["source_evidence_sha256"])
    assert MANIFEST["privacy_scan"] == "PASS"
    assert MANIFEST["scope"] == "PUBLIC_FROZEN_EVIDENCE_ONLY"
    for field in (
        "private_data_read",
        "new_real_training",
        "new_real_scoring",
        "new_current_actual_access",
    ):
        assert MANIFEST[field] is False


@pytest.mark.parametrize("name,expected", sorted(EVIDENCE["source_evidence_sha256"].items()))
def test_source_bytes_and_frozen_stage_immutability(name, expected):
    assert re.fullmatch("[0-9a-f]{64}", expected)
    assert hashlib.sha256(read(name)).hexdigest() == expected


@pytest.mark.parametrize("index", range(7))
def test_exact_stage_lineage(index):
    stage = EVIDENCE["stage_chain"][index]
    assert stage["stage"] == f"S{index}"
    assert stage["pr_number"] == 691 + index
    assert stage["pr_state"] == "MERGED"
    assert stage["head_sha"] == HEADS[index]
    assert stage["merge_commit_sha"] == MERGES[index]
    assert stage["base_sha"] == (MERGES[index - 1] if index else BASELINE)
    assert stage["formal_complete_verified"] is True
    assert stage["independent_review_found"] is True
    assert stage["independent_review_exact_head_match"] is True
    assert stage["independent_review_state"] == "COMMENTED_PASS"
    assert stage["independent_review_count"] == len(stage["independent_reviews"])
    assert stage["independent_review_count"] >= 1
    for review in stage["independent_reviews"]:
        assert review["commit_id"] == HEADS[index]
        assert review["result"] == "PASS"
        assert review["state"] == "COMMENTED"
        assert "PASS" in review["summary"] and "independent" in review["summary"].lower()
        assert review["url"].endswith(f"#pullrequestreview-{review['review_id']}")
    for prefix, run, event, head in (
        ("exact_head_ci", PR_RUNS[index], "pull_request", HEADS[index]),
        ("post_merge_ci", MAIN_RUNS[index], "push", MERGES[index]),
    ):
        assert stage[f"{prefix}_run_id"] == run
        assert stage[f"{prefix}_head_sha"] == head
        assert stage[f"{prefix}_event"] == event
        assert stage[f"{prefix}_status"] == "completed"
        assert stage[f"{prefix}_conclusion"] == "success"
        assert stage[f"{prefix}_attempt"] >= 1
        jobs = stage[f"{prefix}_jobs"]
        counts = stage[f"{prefix}_job_counts"]
        assert len(jobs) == counts["total"]
        for status in ("success", "skipped", "failure", "cancelled"):
            assert counts[status] == sum(job["conclusion"] == status for job in jobs)
        assert counts["failure"] == counts["cancelled"] == 0
        assert counts["success"] == (12 if event == "pull_request" else 4)
        assert counts["skipped"] == (0 if event == "pull_request" else 8)
        assert (
            next(job for job in jobs if job["name"] == "full-suite-canary")["conclusion"]
            == "success"
        )


def test_main_release_and_historical_draft_isolation():
    assert len(EVIDENCE["stage_chain"]) == 7
    assert EVIDENCE["base_main_sha"] == MERGES[-1]
    assert EVIDENCE["release_baseline_sha"] == BASELINE
    assert EVIDENCE["latest_formal_release"] == "v0.15.0"
    isolation = EVIDENCE["isolation"]
    for name in (
        "v0_14_changed",
        "v0_15_changed",
        "old_stage_evidence_rewritten",
        "pr690_modified",
    ):
        assert isolation[name] is False
    assert isolation["pre_formal_draft_pr_690_excluded_from_formal_stage_chain"] is True
    assert isolation["pr690_state"] == "OPEN_DRAFT"
    assert isolation["pr690_head"] == "5b5f01683e47c32e0cae45b791e9d0d41d8e66c2"
    assert isolation["v0_12_release_status"] == "UNRELEASED_RESEARCH_ENGINEERING_LINE"
    assert EVIDENCE["metadata_authority"]["s6_post_merge_canary_log"] == {
        "job_id": 112851458836,
        "passed": 9227,
        "skipped": 5,
        "warnings": 465,
        "duration_seconds": "2215.39",
        "summary": "9227 passed, 5 skipped, 465 warnings in 2215.39s (0:36:55)",
    }


@pytest.mark.parametrize("stage", POLICY_HASHES)
def test_frozen_policy_semantic_hash_and_manifest(stage):
    pin = EVIDENCE["frozen_policy_pins"][stage]
    policy = load(pin["path"])
    assert pin["policy_hash"] == policy["policy_hash"] == POLICY_HASHES[stage]
    assert hashlib.sha256(canonical(policy["policy"])).hexdigest() == POLICY_HASHES[stage]
    manifest_path = str(Path(pin["path"]).parent / "manifest-r1.json")
    manifest = load(manifest_path)
    assert manifest["policy_hash"] == POLICY_HASHES[stage]
    for name, expected in manifest["files"].items():
        assert hashlib.sha256(read(str(Path(manifest_path).parent / name))).hexdigest() == expected


def test_s1_hierarchy_and_negative_boundaries():
    pin = EVIDENCE["frozen_policy_pins"]["S1"]
    stage = load("docs/v0-16/evidence/v0.16-s1-hierarchical-forecast-reconciliation-r1.json")
    assert (
        pin["hierarchy_contract_version"]
        == stage["hierarchy_contract_version"]
        == "V0_16_HIERARCHY_R1"
    )
    assert (
        pin["reconciliation_policy_version"]
        == stage["reconciliation_policy_version"]
        == "HIERARCHICAL_BOTTOM_UP_EXACT_SUM_R1"
    )
    assert pin["reconciliation_method"] == stage["RECONCILIATION_METHOD"] == "BOTTOM_UP_EXACT_SUM"
    assert pin["hierarchy"] == ["BASE", "REGION", "COMPANY"]
    assert pin["forecast_atomic_entity_type"] == "BASE"
    assert pin["incomplete_status"] == "INCOMPLETE_CHILD_COVERAGE"
    for field in (
        "farm_hierarchy_admitted",
        "factory_hierarchy_admitted",
        "missing_child_as_zero",
        "sum_child_peaks_allowed",
    ):
        assert pin[field] is False


def test_observations_are_copied_not_recomputed_or_overclaimed():
    frozen = EVIDENCE["frozen_results"]
    coverage = load(
        "docs/v0-16/evidence/uncertainty-conformal-calibration-r1/coverage-summary-r1.json"
    )
    assert frozen["s2_daily_target_row_coverage"] == coverage
    for horizon in coverage.values():
        for metric in horizon.values():
            assert metric["observation"] == "UNDER_NOMINAL"
            assert (
                metric["candidate_row_count"]
                == metric["computable_row_count"] + metric["not_computable_row_count"]
            )
    assert frozen["s3_reconstruction"] == load(
        "docs/v0-16/evidence/forecast-attribution-r1/reconstruction-summary-r1.json"
    )
    assert frozen["s3_reconstruction"]["exact_prediction_match_count"] == 131625
    assert frozen["s3_reconstruction"]["exact_prediction_mismatch_count"] == 0
    assert (
        frozen["s4_historical_point_quality"]
        == load("docs/v0-16/evidence/forecastops-monitoring-r1/point-quality-summary-r1.json")[
            "horizons"
        ]
    )
    assert frozen["s4_runtime_observability"] == load(
        "docs/v0-16/evidence/forecastops-monitoring-r1/runtime-observability-summary-r1.json"
    )
    s6 = frozen["s6_acceptance"]
    assert (s6["runs"], s6["comparison_groups"]) == (27, 9)
    assert s6["synthetic"] is True and s6["rounded_utilization_used_for_ranking"] is False


def test_gates_and_pre_ci_execution_snapshot_do_not_claim_completion():
    gates = EVIDENCE["version_complete_gates"]
    assert [g["gate_id"] for g in gates] == [f"G{i:02}" for i in range(1, 17)]
    assert all(g["evidence"] for g in gates)
    assert [g["status"] for g in gates] == ["PASS"] * 13 + ["PENDING"] * 3
    assert (
        EVIDENCE["passed_gate_count"],
        EVIDENCE["pending_gate_count"],
        EVIDENCE["failed_gate_count"],
    ) == (13, 3, 0)
    governance = EVIDENCE["governance"]
    assert all(governance[f"s{i}_formal_complete_verified"] for i in range(7))
    assert governance["research_and_engineering_tasks_complete"] is True
    assert governance["version_closeout_implementation_authorized"] is True
    assert governance["version_closeout_implementation_complete"] is False
    assert governance["external_exact_head_ci"] == "REQUIRED_SEPARATE_TERMINAL_PR_RECEIPT"
    assert governance["version_closeout_independent_review"] == "PENDING"
    for field in (
        "version_closeout_formal_complete",
        "v0_16_version_complete",
        "ready_authorized",
        "merge_authorized",
        "tag_authorized",
        "release_authorized",
        "tag_created",
        "release_created",
        "v0_17_authorized",
        "v0_17_started",
    ):
        assert governance[field] is False
    assert EVIDENCE["release_readiness_audit"] == "PASS"
    assert (
        EVIDENCE["release_readiness_status"]
        == "PENDING_CLOSEOUT_REVIEW_MERGE_POST_MERGE_CI_AND_OWNER_TAG_RELEASE_AUTHORIZATION"
    )


def test_public_only_data_and_no_prohibited_claims():
    assert EVIDENCE["scope"] == "PUBLIC_FROZEN_EVIDENCE_ONLY"
    for field in (
        "private_data_read",
        "new_real_training",
        "new_real_scoring",
        "new_actual_access",
        "new_forecast_execution",
        "new_simulation_experiment",
        "production_code_changed",
    ):
        assert EVIDENCE[field] is False
    data = EVIDENCE["data_authority"]
    for field in (
        "strict_pit",
        "historical_actual_available_at_proven",
        "current_season_actual_available",
        "current_season_actual_dependency",
        "current_season_actual_read",
        "current_season_actual_import",
        "current_season_actual_scoring",
    ):
        assert data[field] is False
    assert data["retrospective_authority_used"] is True
    assert set(EVIDENCE["prohibited_claims"]) == {
        "prospective_accuracy_validated",
        "production_use_approved",
        "production_model_promotion_approved",
        "strict_historical_pit_proven",
        "point_forecast_proven_p50",
        "true_quantile_semantics_established",
        "prospective_interval_coverage_validated",
        "attribution_is_causal",
        "production_alert_thresholds_established",
        "canonical_company_cost_established",
        "real_roi_validated",
        "what_if_is_optimizer",
        "automatic_execution_approved",
        "current_season_actual_used",
    }
    assert EVIDENCE["prohibited_claims"] and all(
        v is False for v in EVIDENCE["prohibited_claims"].values()
    )
    assert EVIDENCE["v0_17_recommended_direction"] == "HARVEST_STATE_PROSPECTIVE_SHADOW_VALIDATION"
    for path in (EVIDENCE_PATH, MANIFEST_PATH, MARKDOWN_PATH):
        text = read(path).decode()
        assert not re.search(
            r"/(?:Users|home|root|tmp|private)/|postgres(?:ql)?://|gh[pousr]_[A-Za-z0-9]+", text
        )
    forbidden = {
        "base_id",
        "row_key",
        "daily_actual",
        "daily_forecast",
        "coefficients",
        "feature_means",
        "feature_scales",
        "password",
        "token",
        "credential",
    }

    def walk(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(EVIDENCE)
