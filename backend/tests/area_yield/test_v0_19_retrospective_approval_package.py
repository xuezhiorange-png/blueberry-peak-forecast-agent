"""Offline checks of a proposed approval package, never a real execution permit.

Historical source checks use fixed Git objects, not future worktree contents.
No private roster, harvest label, profile or Registry is opened by these tests.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "docs/v0-19/evidence/v0.19-s3-retrospective-approval-package-r1.json"
REPORT = ROOT / "docs/v0-19/s3/retrospective-protocol-and-c0-approval-r1.md"
BASE = "3298b9c8daefc3dbc51b99954baaaa713353271c"
S1 = "docs/v0-19/evidence/v0.19-s1-model-baseline-peak-protocol-r1.json"


def historical(path: str, commit: str, expected: str | None = None) -> bytes:
    p = PurePosixPath(path)
    if (
        not re.fullmatch(r"[0-9a-f]{40}", commit)
        or p.is_absolute()
        or ".." in p.parts
        or str(p) != path
        or ":" in path
        or "\\" in path
    ):
        raise ValueError("INVALID_HISTORICAL_REFERENCE")
    subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    raw = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("HISTORICAL_HASH_MISMATCH")
    return raw


def load() -> dict[str, Any]:
    result: dict[str, Any] = json.loads(CONTRACT.read_bytes())
    return result


def constants(path: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for node in ast.parse(historical(path, BASE)).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass  # Nonliteral code is not executed to inspect constants.
    return result


def check(c: dict[str, Any]) -> None:
    """Assertions constrain this proposal; changing a JSON flag grants nothing."""
    assert c["task_id"] == "V0_19_S3_RETROSPECTIVE_PROTOCOL_AND_C0_APPROVAL_PACKAGE_R1"
    assert c["base_main_sha"] == BASE
    assert c["identity"] == {
        "experiment_type": "RETROSPECTIVE_REPLAY",
        "historical_status": "EXPOSED_HISTORICAL_BENCHMARK",
        "protocol_status": "PROPOSED_NOT_EFFECTIVE",
        "comparison_family": "V019_SOURCE002_FOLD_B_CROSS_SOURCE_REPLAY_PROPOSED_R1",
        "strict_pit": False,
        "production_eligible": False,
    }
    assert c["states"] and all(type(v) is bool and v is False for v in c["states"].values())
    assert set(c["states"]) == {
        "retrospective_protocol_effective",
        "real_prediction_authorized",
        "real_scoring_authorized",
        "real_prediction_generated",
        "real_scoring_performed",
        "model_training_authorized",
        "s3_formal_complete",
        "ready_authorized",
        "merge_authorized",
        "deploy_authorized",
    }
    assert c["c0"]["formally_admitted_count"] == 0
    assert c["c0"]["status"] == "C0_CANDIDATE_ONLY"
    assert c["c0"]["formal_seal_sha256"] is None
    assert c["c0"]["roster_disposition"] == "REFERENCE_EXISTING_PRIVATE_PINNED_MANIFESTS_NO_COPY"
    scope = c["scope"]
    assert scope["version"] == "V0_19_SOURCE002_OWNER_RESEARCH_SCOPE_R1"
    assert (
        scope["bases"],
        scope["included_farms"],
        scope["excluded_farms"],
        scope["unresolved"],
    ) == (
        39,
        80,
        4,
        0,
    )
    assert scope["season"] == "2025-2026"
    assert scope["target_start"] == "2025-08-05" and scope["target_end"] == "2026-04-15"
    assert scope["full_season_admitted"] == 0
    assert scope["exclusion_scope"] == "RESEARCH_ONLY_PRESERVE_RAW_AND_GLOBAL_V08_AUTHORITY"
    assert scope["exclusions"] == ["嘉果莓森", "曲靖师宗农场", "格莱莓农场", "老挝巴松一场"]
    owner = constants("backend/research/v019_owner_scope_adapter.py")
    r1 = constants("backend/research/v019_real_phase_a_adapter.py")
    assert scope["exact_additional_bindings"] == {k: list(v) for k, v in owner["BINDINGS"].items()}
    assert c["input_identities"] == {
        "source002_reference_not_phase_a_input": owner["SOURCE_SHA256"],
        "reference-B.json": r1["PROFILE_SHA256"],
        "base-registry-v1.json": r1["REGISTRY_SHA256"],
        "registry_payload_sha256": r1["REGISTRY_PAYLOAD_HASH"],
        "owner_decision_sha256": owner["DECISION_SHA256"],
        "owner-scope-metadata-r2.json": owner["METADATA_SHA256"],
        "h7-candidates.csv": owner["H7_SHA256"],
        "h15-candidates.csv": owner["H15_SHA256"],
    }
    previous = scope["prior_metadata_reference_only"]
    assert (previous["base_days"], previous["observed"], previous["authorized_zero"]) == (
        9906,
        6416,
        3490,
    )
    assert previous["zero_to_observed_changes"] == owner["ZERO_CHANGES"]
    assert previous["reverified_private_objects_this_task"] is False
    assert c["algorithm"]["baseline"] == "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
    assert c["algorithm"]["candidate"] == "BIN_CENTER_LINEAR_PER_BIN_MASS_V1"
    assert c["algorithm"]["fold"] == "B" and c["algorithm"]["candidate_count"] == 1
    assert c["algorithm"]["full_support"] == ["2025-07-01", "2026-04-15"]
    assert c["algorithm"]["season_anchor"] == "2025-07-01"
    assert c["algorithm"]["query"] == "SLICE_PRECOMPUTED_SUPPORT_NO_RENORMALIZATION"
    assert c["algorithm"]["tuning"] is False
    assert c["algorithm"]["generation_order"] == "FULL_SHARED_SUPPORT_THEN_H7_H15_SLICE"
    assert c["algorithm"]["profile_train_row_set_hash"] == (
        "c8b2da43696071648ac8280569fc2e28d7fa4b987f0a63b9edaae22122cc717e"
    )
    assert c["time"]["business_timezone"] == "Asia/Shanghai"
    assert c["time"]["historical_issuance_evidence"] == "NOT_PROVEN"
    assert c["time"]["origin_and_cutoff_registration"] == "OWNER_DECISION_REQUIRED_DATE_ONLY_NOW"
    assert c["time"]["executed_at"] == "ACTUAL_TIMEZONE_AWARE_UTC_NEVER_BACKDATED"
    assert c["limitations"]["physical_basis_equivalence"] == "NOT_PROVEN"
    assert c["limitations"]["historical_area_known_at"] == "NOT_PROVEN"
    assert c["limitations"]["strict_scorer_disposition"] == "UNCHANGED_REFUSE_LATE_ISSUANCE"
    for w, days, count, last in (
        ("H7_PREFIX", 7, 9672, "2026-04-08"),
        ("H15_LOCAL", 15, 9360, "2026-03-31"),
    ):
        item = c["c0"]["windows"][w]
        assert item["horizon_days"] == days and item["count"] == count
        assert item["origin_first"] == "2025-08-04" and item["origin_last"] == last
        n = (
            date.fromisoformat(scope["target_end"]) - date.fromisoformat(scope["target_start"])
        ).days
        assert count == 39 * (n + 2 - days)
        assert item["status"] == "C0_CANDIDATE_ONLY"
    assert c["c0"]["selection_uses"] == [
        "IDENTITY",
        "DATES",
        "SOURCE",
        "WINDOW",
        "AUTHORIZED_COMPLETENESS",
    ]
    assert c["c0"]["failure_policy"] == "KEEP_ALL_REGISTERED_MEMBERS_FAILURES_AND_REASONS"
    assert c["c0"]["freeze_before_labels"] is True
    assert c["c0"]["post_score_membership_changes"] is False
    assert c["c0"]["candidate_columns"] == r1["FIELDS"] or (
        c["c0"]["candidate_columns"] == list(r1["FIELDS"])
    )
    assert c["phase_a"]["requires"] == [
        "PROTOCOL",
        "FORMAL_C0",
        "A_INPUT_READ",
        "A_EXECUTION",
        "INDEPENDENT_REVIEWED_RESEARCH_IMPLEMENTATION",
    ]
    assert c["phase_a"]["input_objects"] == [
        "reference-B.json",
        "base-registry-v1.json",
        "h7-candidates.csv",
        "h15-candidates.csv",
        "owner-scope-metadata-r2.json",
    ]
    assert c["phase_a"]["label_access"] == "FORBIDDEN_INCLUDING_SOURCE002_WORKBOOK"
    assert c["phase_a"]["execution_status"] == "UNAVAILABLE_UNCONDITIONAL_REFUSAL"
    assert c["phase_b"]["execution_status"] == "BLOCKED_NO_REAL_SCORING_IMPLEMENTATION_APPROVED"
    assert c["phase_b"]["strict_scorer_bypass"] is False
    assert c["phase_b"]["requires"] == [
        "PROTOCOL",
        "FORMAL_C0",
        "A_INPUT_READ",
        "A_EXECUTION",
        "A_SEAL_REVIEW",
        "B_LABEL_READ",
        "B_SCORING",
        "INDEPENDENT_REVIEWED_RESEARCH_IMPLEMENTATION",
    ]
    assert (
        c["seal"]["canonicalization"]
        == "UTF8_SORT_KEYS_INDENT2_ENSURE_ASCII_FALSE_ALLOW_NAN_FALSE_TRAILING_LF"
    )
    assert c["seal"]["digest"] == "SHA256_NOT_SIGNATURE_OR_TRUSTED_TIMESTAMP"
    assert set(c["seal"]["contains"]) >= {
        "c0_member_manifest_hashes",
        "profile_registry_area_scope_hashes",
        "code_commit_and_blob_hashes",
        "method_config_hash",
        "full_support_curves_and_window_slices",
        "all_failures",
        "actual_executed_at",
        "origin_cutoff_target_semantics",
        "approval_provenance",
    }
    assert set(c["decisions"]) == {
        "PROTOCOL",
        "FORMAL_C0",
        "A_INPUT_READ",
        "A_EXECUTION",
        "A_SEAL_REVIEW",
        "B_LABEL_READ",
        "B_SCORING",
        "INDEPENDENT_REVIEWED_RESEARCH_IMPLEMENTATION",
    }
    for d in c["decisions"].values():
        assert d["status"] == "NOT_APPROVED" and d["approved"] is False
        assert d["github_or_private_decision_reference"] is None and d["decided_at"] is None
    assert c["metrics"]["definitions"] == json.loads(historical(S1, BASE))["metrics"]
    assert (
        c["metrics"]["source_comparison_key"] == json.loads(historical(S1, BASE))["comparison_key"]
    )
    assert c["metrics"]["full_season"] == "NOT_COMPUTABLE_NOT_ADMITTED"
    assert c["metrics"]["common_cohort"] == "PER_METRIC_PAIRED_CM_KEEP_C0_FAILURES"
    assert (
        c["metrics"]["aggregation"]
        == "ONE_PREREGISTERED_COMPARISON_FAMILY_WINDOW_SPLIT_SOURCE_TRAIN_SCOPE"
    )
    assert (
        c["metrics"]["claims"]
        == "CONDITIONAL_RESEARCH_ONLY_NO_PRODUCTION_ACCURACY_PROMOTION_OR_BLIND_OOT"
    )
    assert len(c["metrics"]["definitions"]) == 10
    assert (c["metrics"]["h7_rolling_start_count"], c["metrics"]["h15_rolling_start_count"]) == (
        1,
        9,
    )
    assert c["execution_this_task"] and all(
        type(v) is bool and v is False for v in c["execution_this_task"].values()
    )
    assert c["report_sha256"] == hashlib.sha256(REPORT.read_bytes()).hexdigest()
    assert set(c["historical_sources_sha256"]) == {
        "backend/research/v019_owner_scope_adapter.py",
        "backend/research/v019_real_phase_a_adapter.py",
        "backend/research/v019_daily_curve.py",
        "backend/research/v019_replay_preparation.py",
        "backend/research/v019_retrospective_entry.py",
        "backend/research/v019_synthetic_validation.py",
        "docs/v0-19/s1/peak-metrics-and-experiment-protocol-r1.md",
        S1,
        "docs/v0-19/s3/owner-scope-adapter-rebind-r2.md",
        "docs/v0-19/evidence/v0.19-s3-owner-scope-adapter-rebind-r2.json",
    }
    for path, sha in c["historical_sources_sha256"].items():
        historical(path, BASE, sha)


def test_approval_package_is_consistent() -> None:
    check(load())


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("states", "real_prediction_authorized", True),
        ("states", "real_scoring_authorized", True),
        ("states", "retrospective_protocol_effective", True),
        ("states", "s3_formal_complete", True),
        ("identity", "strict_pit", True),
        ("identity", "historical_status", "BLIND_OOT"),
        ("c0", "status", "APPROVED"),
        ("c0", "formally_admitted_count", 19032),
        ("c0", "freeze_before_labels", False),
        ("c0", "post_score_membership_changes", True),
        ("c0", "selection_uses", ["ACTUAL_WEIGHT", "LOWEST_ERROR"]),
        ("scope", "included_farms", 75),
        ("scope", "full_season_admitted", 39),
        ("scope", "unresolved", 9),
        ("algorithm", "tuning", True),
        ("algorithm", "fold", "A"),
        ("algorithm", "query", "RENORMALIZE_EACH_WINDOW"),
        ("algorithm", "full_support", ["2025-08-05", "2026-04-15"]),
        ("time", "executed_at", "BACKDATE_TO_ORIGIN"),
        ("limitations", "physical_basis_equivalence", "PROVEN"),
        ("limitations", "historical_area_known_at", "PROVEN"),
        ("phase_a", "label_access", "ALLOWED"),
        ("phase_a", "execution_status", "ENABLED"),
        ("phase_b", "strict_scorer_bypass", True),
        ("metrics", "full_season", "COMPUTABLE"),
        ("metrics", "aggregation", "POOL_SEASONS_SOURCES_AND_WINDOWS"),
        ("input_identities", "h7-candidates.csv", "0" * 64),
        ("input_identities", "h15-candidates.csv", "0" * 64),
        ("input_identities", "owner-scope-metadata-r2.json", "0" * 64),
        ("phase_a", "input_objects", ["原果入库汇总表.xls"]),
        ("phase_b", "requires", ["B_SCORING"]),
        ("scope", "exact_additional_bindings", {}),
    ],
)
def test_rejects_unauthorized_promotion_or_semantic_drift(
    section: str,
    key: str,
    value: object,
) -> None:
    c = copy.deepcopy(load())
    c[section][key] = value
    with pytest.raises(AssertionError):
        check(c)


def test_approval_and_metric_tampering_fail() -> None:
    c = load()
    c["decisions"]["PROTOCOL"]["approved"] = True
    with pytest.raises(AssertionError):
        check(c)
    c = load()
    c["metrics"]["definitions"]["DAILY_WAPE"]["formula"] = "mean(daily_percentage_error)"
    with pytest.raises(AssertionError):
        check(c)


@pytest.mark.parametrize(
    "commit,path,expected,error",
    [
        ("0" * 40, S1, None, subprocess.CalledProcessError),
        (BASE, "does-not-exist.json", None, subprocess.CalledProcessError),
        (BASE, S1, "0" * 64, ValueError),
        ("HEAD", S1, None, ValueError),
        (BASE, "../private.csv", None, ValueError),
    ],
)
def test_bad_historical_sources_fail(
    commit: str,
    path: str,
    expected: str | None,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        historical(path, commit, expected)


def test_future_worktree_is_not_historical_source(tmp_path: Path) -> None:
    # A future edited copy is not passed to historical(); no tracked file is mutated.
    p = tmp_path / "v019_owner_scope_adapter.py"
    p.write_text("# SYNTHETIC future legitimate edit\n")
    path = "backend/research/v019_owner_scope_adapter.py"
    expected = load()["historical_sources_sha256"][path]
    assert hashlib.sha256(p.read_bytes()).hexdigest() != expected
    assert hashlib.sha256(historical(path, BASE, expected)).hexdigest() == expected
