from __future__ import annotations

import copy
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.s4_candidate_execution import (
    CANDIDATE_01_ALLOWED_PARAMETER_PATHS,
    CANDIDATE_01_PARAMETER_MANIFEST_VERSION,
    AppendOnlyValidationJournal,
    Candidate01ContractError,
    Candidate01PreflightBlocked,
    ValidationBudgetReconciliation,
    build_candidate_01_manifest,
    build_candidate_gate_request,
    build_derived_candidate_config,
    candidate_01_execution_preflight,
    candidate_budget_preflight,
    reconcile_validation_budget,
    resolve_pairing_authority,
    validate_candidate_01_manifest,
    verify_parameter_allowlist,
)
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_VERSION,
    FROZEN_CANDIDATE_REGISTRY,
    GUARDRAIL_POLICY_HASH,
    GUARDRAIL_POLICY_VERSION,
    METRIC_CONTRACT_IDENTITY,
    METRIC_CONTRACT_VERSION,
    S4_A_EXPERIMENT_PLAN_HASH_BOUND,
    CandidateExecutionGateRequest,
    check_candidate_execution_gate,
)
from scripts.run_v03_s4_c01_parameter_calibration import _preflight_payload

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/maturity_curve.yaml"


def _identity(seed: str) -> str:
    return (seed * 64)[:64]


def _manifest():
    return build_candidate_01_manifest(CONFIG_PATH)


def _resolved_budget(
    *,
    status: str = "PASS",
    effective: int = 4,
    remaining: int = 28,
) -> ValidationBudgetReconciliation:
    blocked = status != "PASS"
    return ValidationBudgetReconciliation(
        status="BLOCKED" if blocked else "PASS",
        blocker="VALIDATION_BUDGET_RECONCILIATION_BLOCKED" if blocked else None,
        reason_code="VALIDATION_BUDGET_RECONCILIATION_BLOCKED" if blocked else None,
        canonical_ledger_row_count=0,
        canonical_started_evaluation_count=0,
        legacy_unledgered_c01_started_evaluation_count=4,
        effective_validation_evaluations_consumed=effective,
        remaining_effective_validation_budget=remaining,
    )


def _build_gate_request_kwargs(*, global_actual_evaluation_count: int) -> dict[str, object]:
    manifest = _manifest()
    return {
        "manifest": manifest,
        "run": manifest.run(1),
        "pairing_bindings": {
            "train_dataset_identity": _identity("a"),
            "validation_dataset_identity": _identity("b"),
            "actual_label_set_identity": _identity("c"),
            "exclusion_policy_identity": _identity("d"),
            "cutoff_policy_identity": _identity("e"),
            "forecast_horizon_set_identity": _identity("f"),
            "metric_contract_identity": METRIC_CONTRACT_IDENTITY,
            "business_grain_set_identity": _identity("1"),
            "common_comparable_set_identity": _identity("2"),
        },
        "candidate_actual_run_count": 0,
        "global_actual_evaluation_count": global_actual_evaluation_count,
        "code_commit_sha": "c" * 40,
        "evaluation_id": "evaluation-1",
    }


def _gate_request() -> CandidateExecutionGateRequest:
    return CandidateExecutionGateRequest(
        experiment_plan_version=EXPERIMENT_PLAN_VERSION,
        experiment_plan_hash=S4_A_EXPERIMENT_PLAN_HASH_BOUND,
        guardrail_policy_version=GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=GUARDRAIL_POLICY_HASH,
        candidate_id="01_parameter_calibration",
        candidate_run_ordinal=1,
        candidate_planned_run_count=4,
        candidate_actual_run_count=0,
        global_actual_evaluation_count=0,
        train_dataset_identity=_identity("a"),
        validation_dataset_identity=_identity("b"),
        actual_label_set_identity=_identity("c"),
        exclusion_policy_identity=_identity("d"),
        cutoff_policy_identity=_identity("e"),
        forecast_horizon_set_identity=_identity("f"),
        metric_contract_identity=METRIC_CONTRACT_IDENTITY,
        business_grain_set_identity=_identity("1"),
        common_comparable_set_identity=_identity("2"),
        metric_contract_version=METRIC_CONTRACT_VERSION,
        test_access_requested=False,
        test_sealed=True,
        parameter_manifest_hash=_identity("p"),
        code_commit_sha="c" * 40,
        random_seed=20260624,
        evaluation_id="evaluation-1",
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
    )


def _start_payload(
    *,
    evaluation_id: str = "evaluation-1",
    invocation_type: str = "NORMAL_RUN",
) -> dict[str, object]:
    return {
        "evaluation_id": evaluation_id,
        "experiment_plan_version": EXPERIMENT_PLAN_VERSION,
        "candidate_id": "01_parameter_calibration",
        "candidate_run_ordinal": 1,
        "global_evaluation_ordinal": 1,
        "invocation_type": invocation_type,
        "trigger_source": "COORDINATOR_S4_C01",
        "started_at": "2026-09-08T00:00:00Z",
        "finished_at": None,
        "execution_status": "STARTED",
        "metric_result_status": "PENDING",
        "dataset_hash": _identity("d"),
        "validation_split_hash": _identity("s"),
        "code_commit_sha": "c" * 40,
        "parameter_manifest_hash": _identity("p"),
        "random_seed": 20260624,
        "retry_of_evaluation_id": None,
        "counted_toward_budget": True,
        "budget_count_reason": "STARTED_INVOCATION",
    }


def test_incumbent_config_authority_is_current_and_stable() -> None:
    first = _manifest()
    second = _manifest()
    assert first.incumbent_config_file_sha256 == (
        "fc023976a228c36556ed5f7ababe722a3dd8a558ed11e0473eb415b52dd69ace"
    )
    assert first.incumbent_config_hash == (
        "3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c"
    )
    assert first.incumbent_config_file_sha256 == second.incumbent_config_file_sha256
    assert first.incumbent_config_hash == second.incumbent_config_hash


def test_manifest_has_exact_four_runs_and_order() -> None:
    manifest = _manifest()
    assert manifest.version == CANDIDATE_01_PARAMETER_MANIFEST_VERSION
    assert manifest.allowed_parameter_paths == CANDIDATE_01_ALLOWED_PARAMETER_PATHS
    assert [run.candidate_run_ordinal for run in manifest.runs] == [1, 2, 3, 4]
    assert [dict(run.authorized_parameter_delta) for run in manifest.runs] == [
        {"curve.spline_knot_count": 5, "curve.ridge_alpha": Decimal("0.10")},
        {"curve.spline_knot_count": 7, "curve.ridge_alpha": Decimal("0.10")},
        {"curve.spline_knot_count": 6, "curve.ridge_alpha": Decimal("0.05")},
        {"curve.spline_knot_count": 6, "curve.ridge_alpha": Decimal("0.20")},
    ]


def _manifest_with_run(manifest, ordinal: int, **changes):
    runs = list(manifest.runs)
    runs[ordinal - 1] = replace(runs[ordinal - 1], **changes)
    return replace(manifest, runs=tuple(runs))


def _snapshot_with_value(manifest, ordinal: int, path: str, value: object):
    snapshot = copy.deepcopy(dict(manifest.run(ordinal).full_parameter_snapshot))
    section, key = path.split(".")
    snapshot[section][key] = value
    return snapshot


@pytest.mark.parametrize(
    ("ordinal", "path", "value"),
    [
        (1, "curve.spline_knot_count", 4),
        (2, "curve.spline_knot_count", 8),
        (3, "curve.ridge_alpha", Decimal("0.07")),
        (4, "curve.ridge_alpha", Decimal("0.25")),
    ],
)
def test_exact_frozen_run_value_mutation_is_rejected(
    ordinal: int,
    path: str,
    value: object,
) -> None:
    manifest = _manifest()
    forged = _manifest_with_run(
        manifest,
        ordinal,
        full_parameter_snapshot=_snapshot_with_value(manifest, ordinal, path, value),
    )
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(forged)


def test_exact_original_four_run_manifest_passes_content_validation() -> None:
    manifest = _manifest()
    validate_candidate_01_manifest(manifest)
    assert manifest.manifest_hash == (
        "eba8af27f926635d654aa4c5331f323a9e4edfa399659e1917b729ac6550910b"
    )


def test_authorized_delta_must_match_full_snapshot() -> None:
    manifest = _manifest()
    forged = _manifest_with_run(
        manifest,
        1,
        authorized_parameter_delta={
            "curve.spline_knot_count": 5,
            "curve.ridge_alpha": Decimal("0.11"),
        },
    )
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(forged)


@pytest.mark.parametrize(
    "field",
    ["parameter_manifest_hash", "candidate_config_hash", "incumbent_config_hash"],
)
def test_forged_run_hashes_are_rejected(field: str) -> None:
    manifest = _manifest()
    forged = _manifest_with_run(manifest, 1, **{field: "0" * 64})
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(forged)


def test_forged_incumbent_file_hash_is_rejected() -> None:
    manifest = _manifest()
    forged = replace(manifest, incumbent_config_file_sha256="0" * 64)
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(forged)


def test_random_seed_drift_is_rejected() -> None:
    manifest = _manifest()
    forged = _manifest_with_run(manifest, 1, random_seed=20260625)
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(forged)


def test_same_ordinals_and_allowlist_do_not_permit_different_values() -> None:
    manifest = _manifest()
    snapshot = _snapshot_with_value(manifest, 1, "curve.spline_knot_count", 8)
    forged = _manifest_with_run(
        manifest,
        1,
        full_parameter_snapshot=snapshot,
        authorized_parameter_delta={
            "curve.spline_knot_count": 8,
            "curve.ridge_alpha": Decimal("0.10"),
        },
    )
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(forged)


def test_top_level_manifest_content_hash_mismatch_is_rejected() -> None:
    manifest = _manifest()
    forged = replace(manifest, hypothesis=manifest.hypothesis + "_forged")
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(forged)


def test_gate_request_rejects_run_not_belonging_to_frozen_manifest() -> None:
    manifest = _manifest()
    forged_run = replace(manifest.run(1), parameter_manifest_hash="0" * 64)
    bindings = {
        "train_dataset_identity": _identity("a"),
        "validation_dataset_identity": _identity("b"),
        "actual_label_set_identity": _identity("c"),
        "exclusion_policy_identity": _identity("d"),
        "cutoff_policy_identity": _identity("e"),
        "forecast_horizon_set_identity": _identity("f"),
        "metric_contract_identity": METRIC_CONTRACT_IDENTITY,
        "business_grain_set_identity": _identity("1"),
        "common_comparable_set_identity": _identity("2"),
    }
    with pytest.raises(Candidate01ContractError):
        build_candidate_gate_request(
            manifest=manifest,
            run=forged_run,
            pairing_bindings=bindings,
            candidate_actual_run_count=0,
            global_actual_evaluation_count=0,
            code_commit_sha="c" * 40,
            evaluation_id="evaluation-1",
        )


def test_manifest_hash_is_stable_and_mutation_changes_it() -> None:
    manifest = _manifest()
    assert manifest.manifest_hash == _manifest().manifest_hash
    payload = manifest.payload()
    payload["runs"][0]["full_parameter_snapshot"]["curve"]["spline_degree"] = 2  # type: ignore[index]
    assert sha256_payload(payload) != manifest.manifest_hash


def test_candidate_manifest_rejects_adaptive_insertion() -> None:
    manifest = _manifest()
    inserted = replace(manifest, runs=manifest.runs + (manifest.runs[-1],))
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(inserted)


def test_candidate_manifest_rejects_run_ordinal_skip_and_fifth_run() -> None:
    manifest = _manifest()
    skipped = replace(manifest.runs[1], candidate_run_ordinal=4)
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(
            replace(manifest, runs=(manifest.runs[0], skipped, *manifest.runs[2:]))
        )
    fifth = replace(manifest.runs[3], candidate_run_ordinal=5)
    with pytest.raises(Candidate01ContractError):
        validate_candidate_01_manifest(replace(manifest, runs=(*manifest.runs[:3], fifth)))


def test_candidate_config_diff_is_exactly_allowlisted() -> None:
    manifest = _manifest()
    for ordinal, run in enumerate(manifest.runs, start=1):
        diff = verify_parameter_allowlist(
            incumbent_snapshot=manifest.incumbent_parameter_snapshot,
            candidate_snapshot=run.full_parameter_snapshot,
        )
        assert diff.unauthorized_parameter_diff_count == 0
        assert set(diff.changed_paths).issubset(set(CANDIDATE_01_ALLOWED_PARAMETER_PATHS))
        assert run.unauthorized_parameter_diff_count == 0
        derived_run, config = build_derived_candidate_config(manifest, ordinal)
        assert derived_run == run
        assert config.rules.random_seed == 20260624


def test_unauthorized_parameter_path_is_rejected() -> None:
    manifest = _manifest()
    snapshot = copy.deepcopy(dict(manifest.runs[0].full_parameter_snapshot))
    snapshot["curve"]["spline_degree"] = 4
    diff = verify_parameter_allowlist(
        incumbent_snapshot=manifest.incumbent_parameter_snapshot,
        candidate_snapshot=snapshot,
    )
    assert diff.unauthorized_paths == ("curve.spline_degree",)


def test_native_float_candidate_snapshot_is_rejected() -> None:
    manifest = _manifest()
    snapshot = copy.deepcopy(dict(manifest.runs[0].full_parameter_snapshot))
    snapshot["curve"]["ridge_alpha"] = 0.11
    drifted = replace(manifest.runs[0], full_parameter_snapshot=snapshot)
    with pytest.raises(Candidate01ContractError):
        build_derived_candidate_config(replace(manifest, runs=(drifted, *manifest.runs[1:])), 1)


def test_pairing_resolution_does_not_invent_hashes(tmp_path: Path) -> None:
    resolution = resolve_pairing_authority(tmp_path)
    assert resolution.status == "BLOCKED"
    assert resolution.bindings == ()
    assert resolution.first_non_derivable_authority == "S3_FINAL_CLOSEOUT_EVIDENCE"


def test_current_pairing_preflight_blocks_before_started_event(tmp_path: Path) -> None:
    manifest = _manifest()
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")
    result = candidate_01_execution_preflight(
        repo_root=REPO_ROOT,
        manifest=manifest,
        journal=journal,
    )
    assert result.status == "BLOCKED"
    assert result.reason_code == ("CANDIDATE_01_ALREADY_STARTED")
    assert result.current_ledger_row_count == 0
    assert result.actual_validation_evaluation_count == 4
    assert not journal.path.exists()


def _current_preflight_payload(tmp_path: Path) -> dict[str, object]:
    manifest = _manifest()
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")
    result = candidate_01_execution_preflight(
        repo_root=REPO_ROOT,
        manifest=manifest,
        journal=journal,
    )
    return _preflight_payload(result)


def test_official_c01_preflight_blocked_payload_reports_effective_four_consumed(
    tmp_path: Path,
) -> None:
    payload = _current_preflight_payload(tmp_path)

    assert payload["CURRENT_LEDGER_ROW_COUNT"] == 0
    assert payload["ACTUAL_VALIDATION_EVALUATION_COUNT"] == 4
    assert payload["EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED"] == 4


def test_official_c01_preflight_blocked_payload_reports_remaining_twenty_eight(
    tmp_path: Path,
) -> None:
    payload = _current_preflight_payload(tmp_path)

    assert payload["REMAINING_GLOBAL_VALIDATION_BUDGET"] == 28
    assert payload["REMAINING_EFFECTIVE_VALIDATION_BUDGET"] == 28


def test_official_c01_preflight_keeps_canonical_ledger_row_count_zero(
    tmp_path: Path,
) -> None:
    payload = _current_preflight_payload(tmp_path)

    assert payload["CANONICAL_LEDGER_ROW_COUNT"] == 0
    assert payload["CANONICAL_LEDGER_STARTED_EVALUATION_COUNT"] == 0
    assert payload["LEGACY_RECONCILED_VALIDATION_DEBIT"] == 4


def test_gate_request_requires_budget_reconciliation() -> None:
    with pytest.raises(
        Candidate01PreflightBlocked,
        match="VALIDATION_BUDGET_RECONCILIATION_REQUIRED",
    ):
        build_candidate_gate_request(**_build_gate_request_kwargs(global_actual_evaluation_count=0))


def test_gate_request_rejects_global_count_zero_when_reconciled_count_is_four() -> None:
    with pytest.raises(
        Candidate01PreflightBlocked,
        match="VALIDATION_BUDGET_RECONCILIATION_MISMATCH",
    ):
        build_candidate_gate_request(
            **_build_gate_request_kwargs(global_actual_evaluation_count=0),
            budget_reconciliation=_resolved_budget(),
        )


def test_gate_request_accepts_matching_effective_count_four() -> None:
    request = build_candidate_gate_request(
        **_build_gate_request_kwargs(global_actual_evaluation_count=4),
        budget_reconciliation=_resolved_budget(),
    )

    assert request.global_actual_evaluation_count == 4


def test_blocked_budget_reconciliation_cannot_build_gate_request() -> None:
    with pytest.raises(
        Candidate01PreflightBlocked,
        match="VALIDATION_BUDGET_RECONCILIATION_BLOCKED",
    ):
        build_candidate_gate_request(
            **_build_gate_request_kwargs(global_actual_evaluation_count=4),
            budget_reconciliation=_resolved_budget(status="BLOCKED"),
        )


def test_empty_ledger_plus_legacy_c01_debit_resolves_to_four_consumed(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")

    result = reconcile_validation_budget(repo_root=REPO_ROOT, journal=journal)

    assert result.status == "PASS"
    assert result.canonical_ledger_row_count == 0
    assert result.legacy_unledgered_c01_started_evaluation_count == 4
    assert result.effective_validation_evaluations_consumed == 4


def test_effective_remaining_budget_is_twenty_eight(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")

    result = candidate_budget_preflight(
        repo_root=REPO_ROOT,
        journal=journal,
        candidate_id="02_quantile_calibration",
        candidate_actual_run_count=0,
    )

    assert result.effective_validation_evaluations_consumed == 4
    assert result.remaining_effective_validation_budget == 28


def test_legacy_reconciliation_does_not_create_fake_ledger_rows(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")

    reconcile_validation_budget(repo_root=REPO_ROOT, journal=journal)

    assert journal.materialize() == ()
    assert not journal.path.exists()


def test_legacy_reconciliation_does_not_make_c01_evidence_authoritative() -> None:
    artifact = json.loads(
        (REPO_ROOT / "docs/v0-3/s4/evidence/s4-validation-budget-reconciliation-r1.json").read_text(
            encoding="utf-8"
        )
    )

    assert artifact["LEGACY_EXECUTION_CONTRACT_VALID"] is False
    assert artifact["LEGACY_NUMERIC_EVIDENCE_SELECTION_AUTHORITY"] is False
    assert artifact["CANDIDATE_01_RERUN_PERFORMED"] is False


def test_budget_gate_blocks_when_ledger_and_reconciliation_disagree(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")
    journal.append_started(_start_payload())

    result = candidate_budget_preflight(
        repo_root=REPO_ROOT,
        journal=journal,
        candidate_id="02_quantile_calibration",
        candidate_actual_run_count=1,
    )

    assert result.status == "BLOCKED"
    assert result.reason_code == "VALIDATION_LEDGER_RECONCILIATION_MISMATCH"


def test_candidate_02_preflight_observes_effective_budget_4_of_32(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")

    result = candidate_budget_preflight(
        repo_root=REPO_ROOT,
        journal=journal,
        candidate_id="02_quantile_calibration",
        candidate_actual_run_count=0,
    )

    assert result.status == "PASS"
    assert result.effective_validation_evaluations_consumed == 4
    assert result.remaining_effective_validation_budget == 28


def test_execution_gate_rejects_run_ordinal_skip_and_fifth_run() -> None:
    skipped = check_candidate_execution_gate(replace(_gate_request(), candidate_run_ordinal=2))
    assert skipped.status == "BLOCKED"
    assert "RUN_ORDINAL_COUNT_MISMATCH" in skipped.reason_codes
    fifth = check_candidate_execution_gate(replace(_gate_request(), candidate_run_ordinal=5))
    assert fifth.status == "BLOCKED"
    assert "CANDIDATE_RUN_ORDINAL_EXCEEDS_LIMIT" in fifth.reason_codes


def test_execution_gate_rejects_missing_and_malformed_pairing_identity() -> None:
    missing = check_candidate_execution_gate(
        replace(_gate_request(), actual_label_set_identity=None)
    )
    assert missing.status == "BLOCKED"
    assert "ACTUAL_LABEL_SET_IDENTITY_MISSING" in missing.reason_codes
    malformed = check_candidate_execution_gate(
        replace(_gate_request(), validation_dataset_identity="not-a-sha")
    )
    assert malformed.status == "BLOCKED"
    assert "VALIDATION_DATASET_IDENTITY_MALFORMED" in malformed.reason_codes


def test_execution_gate_rejects_plan_policy_and_test_access() -> None:
    result = check_candidate_execution_gate(
        replace(
            _gate_request(),
            experiment_plan_hash="0" * 64,
            guardrail_policy_hash="1" * 64,
            test_access_requested=True,
        )
    )
    assert result.status == "BLOCKED"
    assert "EXPERIMENT_PLAN_HASH_MISMATCH" in result.reason_codes
    assert "GUARDRAIL_POLICY_HASH_MISMATCH" in result.reason_codes
    assert "TEST_ACCESS_FORBIDDEN" in result.reason_codes


def test_started_event_counts_toward_budget_without_terminal(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")
    journal.append_started(_start_payload())
    rows = journal.materialize()
    assert len(rows) == 1
    assert rows[0]["execution_status"] == "STARTED"
    assert rows[0]["counted_toward_budget"] is True


def test_terminal_event_does_not_erase_started_count(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")
    journal.append_started(_start_payload())
    journal.append_terminal(
        evaluation_id="evaluation-1",
        finished_at="2026-09-08T00:01:00Z",
        execution_status="COMPLETED",
        metric_result_status="COMPUTED",
    )
    rows = journal.materialize()
    assert len(rows) == 1
    assert rows[0]["execution_status"] == "COMPLETED"
    assert rows[0]["finished_at"] == "2026-09-08T00:01:00Z"


def test_duplicate_evaluation_id_is_rejected(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")
    journal.append_started(_start_payload())
    with pytest.raises(Candidate01ContractError):
        journal.append_started(_start_payload())


def test_ledger_mutation_is_detected(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")
    journal.append_started(_start_payload())
    text = journal.path.read_text(encoding="utf-8")
    journal.path.write_text(text.replace("evaluation-1", "evaluation-mutated"), encoding="utf-8")
    with pytest.raises(Candidate01ContractError):
        journal.materialize()


def test_retry_invocation_is_rejected_for_this_task(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")
    with pytest.raises(Candidate01ContractError):
        journal.append_started(_start_payload(invocation_type="AUTOMATIC_RETRY"))


def test_ledger_rows_are_sorted_by_global_ordinal(tmp_path: Path) -> None:
    journal = AppendOnlyValidationJournal(tmp_path / "journal.jsonl")
    first = _start_payload(evaluation_id="evaluation-2")
    first["global_evaluation_ordinal"] = 2
    second = _start_payload(evaluation_id="evaluation-1")
    second["global_evaluation_ordinal"] = 1
    journal.append_started(first)
    journal.append_started(second)
    assert [row["evaluation_id"] for row in journal.materialize()] == [
        "evaluation-1",
        "evaluation-2",
    ]


def test_test_boundary_is_sealed_in_gate_request() -> None:
    result = check_candidate_execution_gate(_gate_request())
    assert result.allowed is True
    assert _gate_request().test_sealed is True
