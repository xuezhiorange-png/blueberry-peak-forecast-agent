from __future__ import annotations

import copy
import hashlib
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.s4_candidate_03_execution import (
    C03_ALLOWED_PARAMETER_PATHS,
    C03_EXCLUDED_PARAMETER_PATHS,
    C03_OWNER_DECISION_ID,
    C03_PARAMETER_MANIFEST_VERSION,
    C03_RUN_VALUES,
    C03_SEMANTIC_AUTHORITY,
    CANDIDATE_03_ID,
    C03PairingIdentities,
    Candidate03ContractError,
    build_candidate_03_derived_config,
    build_candidate_03_execution_context,
    build_candidate_03_gate_request,
    build_candidate_03_manifest,
    validate_candidate_03_manifest,
    verify_c03_parameter_allowlist,
)
from backend.app.s4_experiment import (
    FROZEN_CANDIDATE_REGISTRY,
    check_candidate_execution_gate,
)
from scripts.run_v03_s4_c03_phenology_offset import (
    C03RunnerContractError,
    _execute,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "configs/maturity_curve.yaml"


def _manifest():
    return build_candidate_03_manifest(CONFIG_PATH)


def _identity(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _pairing_identities() -> C03PairingIdentities:
    return C03PairingIdentities(
        train_dataset_identity=_identity("c03-train"),
        validation_dataset_identity=_identity("c03-validation"),
        actual_label_set_identity=_identity("c03-labels"),
        exclusion_policy_identity=_identity("c03-exclusion"),
        cutoff_policy_identity=_identity("c03-cutoff"),
        forecast_horizon_set_identity=_identity("c03-horizons"),
        business_grain_set_identity=_identity("c03-grains"),
        common_comparable_set_identity=_identity("c03-comparable"),
    )


def _nested_set(snapshot: dict[str, object], path: str, value: object) -> None:
    section, key = path.split(".")
    child = snapshot[section]
    assert isinstance(child, dict)
    child[key] = value


def _manifest_with_run_snapshot(manifest, path: str, value: object):
    run = manifest.run(1)
    snapshot = copy.deepcopy(dict(run.full_parameter_snapshot))
    _nested_set(snapshot, path, value)
    changed_run = replace(run, full_parameter_snapshot=snapshot)
    runs = list(manifest.runs)
    runs[0] = changed_run
    return replace(manifest, runs=tuple(runs))


def test_c03_owner_semantic_decision_bound() -> None:
    manifest = _manifest()
    assert manifest.semantic_authority_decision_id == C03_OWNER_DECISION_ID
    assert manifest.semantic_authority == C03_SEMANTIC_AUTHORITY
    assert manifest.allowed_parameter_paths == ("offset.maximum_abs_shift_days",)


def test_c03_registry_binding() -> None:
    registration = next(
        item for item in FROZEN_CANDIDATE_REGISTRY if item.candidate_id == CANDIDATE_03_ID
    )
    manifest = _manifest()
    assert manifest.candidate_id == registration.candidate_id
    assert manifest.candidate_family == registration.candidate_family
    assert manifest.parent_model_id == registration.parent_model_id
    assert manifest.hypothesis == registration.hypothesis
    assert manifest.planned_run_count == registration.planned_run_count == 4
    assert manifest.random_seed_policy == registration.random_seed_policy
    assert registration.selection_eligibility == "REGISTERED_AND_GUARDRAIL_ELIGIBLE"


def test_c03_incumbent_config_hash_bound() -> None:
    manifest = _manifest()
    assert manifest.incumbent_config_path == "configs/maturity_curve.yaml"
    assert manifest.incumbent_config_file_sha256 == (
        "fc023976a228c36556ed5f7ababe722a3dd8a558ed11e0473eb415b52dd69ace"
    )
    assert manifest.incumbent_config_hash == (
        "3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c"
    )


def test_c03_incumbent_offset_is_21_and_forecast_path_is_14() -> None:
    snapshot = _manifest().incumbent_parameter_snapshot
    assert snapshot["offset"]["maximum_abs_shift_days"] == Decimal("21")
    assert snapshot["offset"]["minimum_training_samples"] == 3
    assert snapshot["forecast"]["observed_phase_adjustment_max_days"] == Decimal("14")


def test_c03_allowed_parameter_path_is_exactly_one() -> None:
    manifest = _manifest()
    assert manifest.allowed_parameter_paths == C03_ALLOWED_PARAMETER_PATHS
    assert len(manifest.allowed_parameter_paths) == 1


def test_c03_excludes_forecast_observed_phase_adjustment() -> None:
    assert C03_EXCLUDED_PARAMETER_PATHS == ("forecast.observed_phase_adjustment_max_days",)
    forged = _manifest_with_run_snapshot(
        _manifest(), "forecast.observed_phase_adjustment_max_days", Decimal("10")
    )
    with pytest.raises(Candidate03ContractError, match="C03_UNAUTHORIZED_PARAMETER_PATH"):
        validate_candidate_03_manifest(forged)


def test_c03_manifest_has_exactly_four_runs() -> None:
    manifest = _manifest()
    assert manifest.version == C03_PARAMETER_MANIFEST_VERSION
    assert len(manifest.runs) == 4
    assert manifest.planned_run_count == 4


def test_c03_run_values_are_14_18_24_28() -> None:
    manifest = _manifest()
    assert (
        tuple(
            run.authorized_parameter_delta["offset.maximum_abs_shift_days"] for run in manifest.runs
        )
        == C03_RUN_VALUES
    )


def test_c03_run_ordinals_are_1_2_3_4() -> None:
    assert [run.candidate_run_ordinal for run in _manifest().runs] == [1, 2, 3, 4]


def test_c03_manifest_hash_replays() -> None:
    first = _manifest()
    second = _manifest()
    assert first.manifest_hash == second.manifest_hash


def test_c03_each_run_hash_replays() -> None:
    first = _manifest()
    second = _manifest()
    assert [run.parameter_manifest_hash for run in first.runs] == [
        run.parameter_manifest_hash for run in second.runs
    ]
    assert [run.candidate_config_hash for run in first.runs] == [
        run.candidate_config_hash for run in second.runs
    ]


def test_c03_manifest_mutation_changes_hash() -> None:
    manifest = _manifest()
    mutated = replace(manifest, semantic_authority_decision_id="OTHER_DECISION")
    assert mutated.manifest_hash != manifest.manifest_hash
    with pytest.raises(Candidate03ContractError, match="C03_OWNER_DECISION_MISMATCH"):
        validate_candidate_03_manifest(mutated)


def test_c03_run_order_mutation_changes_hash() -> None:
    manifest = _manifest()
    mutated = replace(manifest, runs=tuple(reversed(manifest.runs)))
    assert mutated.manifest_hash != manifest.manifest_hash
    with pytest.raises(Candidate03ContractError, match="C03_RUN_ORDER_NOT_FROZEN"):
        validate_candidate_03_manifest(mutated)


def test_c03_allowed_path_mutation_changes_hash() -> None:
    manifest = _manifest()
    mutated = replace(manifest, allowed_parameter_paths=("curve.ridge_alpha",))
    assert mutated.manifest_hash != manifest.manifest_hash
    with pytest.raises(Candidate03ContractError, match="C03_PARAMETER_ALLOWLIST_MISMATCH"):
        validate_candidate_03_manifest(mutated)


def test_c03_native_float_rejected() -> None:
    forged = _manifest_with_run_snapshot(_manifest(), "offset.maximum_abs_shift_days", 14.0)
    with pytest.raises(Candidate03ContractError, match="C03_NATIVE_FLOAT_FORBIDDEN"):
        validate_candidate_03_manifest(forged)


def test_c03_adaptive_search_forbidden() -> None:
    manifest = _manifest()
    mutated = replace(manifest, adaptive_search_allowed=True)
    with pytest.raises(Candidate03ContractError, match="C03_ADAPTIVE_SEARCH_FORBIDDEN"):
        validate_candidate_03_manifest(mutated)


def test_c03_incumbent_snapshot_not_mutated() -> None:
    manifest = _manifest()
    before = copy.deepcopy(dict(manifest.incumbent_parameter_snapshot))
    for ordinal in (1, 2, 3, 4):
        _, derived = build_candidate_03_derived_config(manifest, ordinal)
        assert derived.rules.offset.maximum_abs_shift_days == C03_RUN_VALUES[ordinal - 1]
    assert dict(manifest.incumbent_parameter_snapshot) == before
    assert manifest.incumbent_parameter_snapshot["offset"]["maximum_abs_shift_days"] == Decimal(
        "21"
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("curve.ridge_alpha", Decimal("0.20")),
        ("pooling.minimum_samples", 9),
        ("offset.minimum_training_samples", 4),
        ("forecast.observed_phase_adjustment_max_days", Decimal("10")),
    ],
)
def test_c03_rejects_unauthorized_parameter_paths(path: str, value: object) -> None:
    forged = _manifest_with_run_snapshot(_manifest(), path, value)
    with pytest.raises(Candidate03ContractError, match="C03_UNAUTHORIZED_PARAMETER_PATH"):
        validate_candidate_03_manifest(forged)


def test_c03_rejects_two_parameter_change() -> None:
    manifest = _manifest()
    run = manifest.run(1)
    snapshot = copy.deepcopy(dict(run.full_parameter_snapshot))
    _nested_set(snapshot, "curve.ridge_alpha", Decimal("0.20"))
    forged_run = replace(run, full_parameter_snapshot=snapshot)
    runs = list(manifest.runs)
    runs[0] = forged_run
    with pytest.raises(Candidate03ContractError, match="C03_UNAUTHORIZED_PARAMETER_PATH"):
        validate_candidate_03_manifest(replace(manifest, runs=tuple(runs)))


def test_c03_allowlist_reports_only_authorized_change_for_frozen_runs() -> None:
    manifest = _manifest()
    diff = verify_c03_parameter_allowlist(
        incumbent_snapshot=manifest.incumbent_parameter_snapshot,
        candidate_snapshot=manifest.run(1).full_parameter_snapshot,
    )
    assert diff.changed_paths == C03_ALLOWED_PARAMETER_PATHS
    assert diff.unauthorized_parameter_diff_count == 0
    assert diff.native_float_present is False


def test_c03_derived_config_changes_only_training_shift_bound() -> None:
    manifest = _manifest()
    run, derived = build_candidate_03_derived_config(manifest, 1)
    assert run.candidate_run_ordinal == 1
    assert derived.rules.offset.maximum_abs_shift_days == Decimal("14")
    assert derived.rules.offset.minimum_training_samples == 3
    assert derived.rules.forecast.observed_phase_adjustment_max_days == Decimal("14")


def test_c03_gate_request_uses_effective_count_four_and_exact_registry() -> None:
    manifest = _manifest()
    request = build_candidate_03_gate_request(
        manifest=manifest,
        run=manifest.run(1),
        pairing_identities=_pairing_identities(),
        code_commit_sha="c" * 40,
        evaluation_id="c03-evaluation-1",
    )
    assert request.candidate_id == CANDIDATE_03_ID
    assert request.candidate_actual_run_count == 0
    assert request.candidate_run_ordinal == 1
    assert request.global_actual_evaluation_count == 4
    assert request.candidate_registry == FROZEN_CANDIDATE_REGISTRY
    assert request.test_access_requested is False
    assert request.test_sealed is True
    assert check_candidate_execution_gate(request).allowed is True


def test_c03_execution_context_binds_manifest_run_and_pairing_identities() -> None:
    manifest = _manifest()
    context = build_candidate_03_execution_context(
        manifest=manifest,
        run=manifest.run(1),
        pairing_identities=_pairing_identities(),
        code_commit_sha="c" * 40,
        evaluation_id="c03-context-1",
    )
    assert context.manifest_hash == manifest.manifest_hash
    assert context.candidate_id == CANDIDATE_03_ID
    assert context.candidate_run_ordinal == 1
    assert context.parameter_manifest_hash == manifest.run(1).parameter_manifest_hash
    assert context.candidate_config_hash == manifest.run(1).candidate_config_hash
    assert context.pairing_identities.metric_contract_identity


def test_c03_preflight_requires_manifest_hash() -> None:
    manifest = _manifest()
    request = build_candidate_03_gate_request(
        manifest=manifest,
        run=manifest.run(1),
        pairing_identities=_pairing_identities(),
        code_commit_sha="c" * 40,
        evaluation_id="c03-evaluation-2",
    )
    blocked = check_candidate_execution_gate(replace(request, parameter_manifest_hash=None))
    assert blocked.allowed is False
    assert "PARAMETER_MANIFEST_MISSING" in blocked.reason_codes


def test_c03_contract_does_not_start_validation_event_or_access_test() -> None:
    manifest = _manifest()
    build_candidate_03_derived_config(manifest, 1)
    assert "TEST" not in manifest.payload()
    assert manifest.run(1).parameter_manifest_hash


def test_c03_runner_blocks_without_execution_authorization() -> None:
    result = main([])
    assert result == 2


def test_c03_runner_main_is_machine_readable_and_sealed(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(["--execution-main-sha", "c" * 40])
    output = capsys.readouterr().out
    assert result == 2
    assert '"EXECUTION_STATUS": "BLOCKED"' in output
    assert '"REASON_CODE": "CANDIDATE_EXECUTION_NOT_AUTHORIZED"' in output
    assert '"VALIDATION_STARTED_CREATED": false' in output
    assert '"SCORER_CALLED": false' in output
    assert '"TEST_REMAINS_SEALED": true' in output


def test_c03_internal_execute_fails_closed_before_scoring() -> None:
    with pytest.raises(C03RunnerContractError, match="CANDIDATE_EXECUTION_NOT_AUTHORIZED"):
        _execute(object())  # type: ignore[arg-type]


def test_c03_runner_has_no_scoring_import_or_bypass() -> None:
    source = (REPO_ROOT / "scripts/run_v03_s4_c03_phenology_offset.py").read_text()
    assert "run_local_replay" not in source
    assert "--authorize" not in source
    assert "--force" not in source
    assert "--skip-gate" not in source
