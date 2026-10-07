"""Offline, fixed synthetic acceptance. No forecast/label/runtime adapters."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield.v015_research_cohort import canonical, digest
from backend.app.forecast_intelligence import what_if as w
from backend.app.forecast_intelligence.business_loss import synthetic_contracts

REPOSITORY = Path(__file__).resolve().parents[1]
BASE = "6ab5d04463b516f8e9284ad586a7352d165d2f04"
TASK = "V0_16_S6_WHAT_IF_DECISION_SIMULATOR_R1"
FIXTURE = (
    "backend/tests/forecast_intelligence/fixtures/v0_16_s6_synthetic_saved_forecast_case_01.json"
)
S5_ROOT = "docs/v0-16/evidence/business-loss-contract-r1"
S2_ROOT = "docs/v0-16/evidence/uncertainty-conformal-calibration-r1"
S5_POLICY = "740c0a48506b524ea822b88ad9c5b3443cf3356969026e02cff4a6e1a3c446b7"
S2_POLICY = "f35f2700011f440569c9a0140dc9deb482281d60190e8a601b5a503c79013efd"
COST_HASHES = (
    "35f8316fbf2688b108e173d0d8438ce6323aa0f9db208f7a143f72e07aa5679f",
    "8d6f2567a18bd298f1a261a059a88b2772d77bcc6f03e313dc3853c9cd2f0f3f",
    "6cec3474d85b6421467d43ff71fb6a52a4b4904289cded15c4fdcea74e49fe36",
)
OUTPUT_NAMES = ("synthetic-scenario-results.json", "scenario-ranking-summary.json")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def reject_number(value: str) -> None:
    raise ValueError("NATIVE_FLOAT_FORBIDDEN")


def load(path: Path) -> Any:
    return json.loads(path.read_bytes(), parse_float=reject_number, parse_constant=reject_number)


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(canonical(value))


def output_guard(path: Path, sources: tuple[Path, ...] = ()) -> None:
    p = path.resolve()
    if any(
        p == s.resolve() or p.is_relative_to(s.resolve()) or s.resolve().is_relative_to(p)
        for s in (REPOSITORY, *sources)
    ):
        raise ValueError("OUTPUT_LOCATION_INVALID")


def upstream() -> dict[str, str]:
    """Consume public hashes only; do not import any prior acceptance operator."""
    bound: dict[str, str] = {}
    for root, name, pin in (
        (S5_ROOT, "business-loss-policy-r1.json", S5_POLICY),
        (S2_ROOT, "conformal-policy-r1.json", S2_POLICY),
    ):
        contract = load(REPOSITORY / root / name)
        manifest = load(REPOSITORY / root / "manifest-r1.json")
        if (
            contract["policy_hash"] != pin
            or digest(contract["policy"]) != pin
            or manifest["policy_hash"] != pin
        ):
            raise ValueError("UPSTREAM_POLICY_DRIFT")
        for filename, expected in manifest["files"].items():
            if Path(filename).name != filename:
                raise ValueError("UPSTREAM_SOURCE_DRIFT")
            relative = f"{root}/{filename}"
            if sha((REPOSITORY / relative).read_bytes()) != expected:
                raise ValueError("UPSTREAM_SOURCE_DRIFT")
            bound[relative] = expected
        bound[f"{root}/manifest-r1.json"] = sha(
            (REPOSITORY / root / "manifest-r1.json").read_bytes()
        )
        for relative, expected in contract["policy"]["source_evidence_sha256"].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("UPSTREAM_SOURCE_DRIFT")
            if sha((REPOSITORY / relative).read_bytes()) != expected:
                raise ValueError("UPSTREAM_SOURCE_DRIFT")
            bound[relative] = expected
    costs = [c.payload() | {"contract_hash": c.contract_hash} for c in synthetic_contracts()]
    if tuple(c["contract_hash"] for c in costs) != COST_HASHES or costs != load(
        REPOSITORY / S5_ROOT / "synthetic-cost-contracts-r1.json"
    ):
        raise ValueError("UPSTREAM_S5_AUTHORITY_DRIFT")
    for name in (
        "docs/v0-16/v0.16.0-version-plan-and-scope-freeze.md",
        "docs/v0-16/evidence/v0.16.0-version-plan-and-scope-freeze-r1.json",
        "docs/v0-16/evidence/v0.16-s1-hierarchical-forecast-reconciliation-r1.json",
        "backend/app/forecast_intelligence/what_if.py",
        "scripts/run_v0_16_s6_what_if_decision_simulator.py",
        FIXTURE,
    ):
        bound[name] = sha((REPOSITORY / name).read_bytes())
    return bound


def policy() -> dict[str, Any]:
    return {
        "what_if_policy_version": w.POLICY_VERSION,
        "capacity_policy_version": w.CAPACITY_POLICY_VERSION,
        "backlog_policy_version": w.BACKLOG_POLICY_VERSION,
        "decision_loss_mapping_policy_version": w.LOSS_MAPPING_POLICY_VERSION,
        "scenario_comparison_policy_version": w.COMPARISON_POLICY_VERSION,
        "scenario_ranking_policy_version": w.RANKING_POLICY_VERSION,
        "amendment_id": w.AMENDMENT_ID,
        "utilization_numeric_policy_version": w.UTILIZATION_POLICY_VERSION,
        "utilization_exact_authority": "NUMERATOR_DENOMINATOR_PAIR",
        "utilization_decimal_is_derived": True,
        "utilization_decimal_precision": 50,
        "utilization_decimal_rounding": "ROUND_HALF_EVEN",
        "utilization_inexact_allowed": True,
        "utilization_inexact_exception_scope": "DAILY_AND_AGGREGATE_CAPACITY_UTILIZATION_ONLY",
        "authoritative_kg_inexact_allowed": False,
        "authoritative_loss_inexact_allowed": False,
        "authoritative_decimal_precision": 50,
        "native_float_allowed": False,
        "display_quantization": False,
        "rounded_utilization_used_for_ranking": False,
        "initial_backlog_kg": "0",
        "buffer_semantics": "SAME_DAY_ADDITIVE_HANDLING_CAPACITY",
        "workforce_formula": "workforce_count * explicitly_supplied_productivity_kg_per_person_day",
        "balance": "opening + demand = processed + closing; processed=min(opening+demand,capacity)",
        "overload": "max(planning_demand-effective_capacity,0)",
        "over_capacity": "max(effective_capacity-planning_demand,0)",
        "cumulative_shortfall": "sum(daily_overload)",
        "max_backlog": "max(closing_backlog)",
        "loss_mapping": "S5.row_loss(actual_kg=planning_demand,forecast_kg=effective_capacity)",
        "loss_semantics": "ASYMMETRIC_PLANNING_GAP_LOSS_NOT_BACKLOG_AGING_COST",
        "planning_levels": list(w.PLANNING_LEVELS),
        "hierarchy_levels": list(w.HIERARCHY_LEVELS),
        "point_is_proven_p50": False,
        "upper_planning_bound_is_quantile": False,
        "ranking_key": [
            "total_business_loss",
            "max_backlog_kg",
            "cumulative_shortfall_kg",
            "ending_backlog_kg",
            "scenario_id",
        ],
        "ranking_semantics": "DESCRIPTIVE_ORDER_UNDER_GIVEN_INPUTS_AND_COST_CONTRACT",
        "comparison_authority": [
            "saved_source_curve_origin",
            "hierarchy_entity_authority",
            "planning_level",
            "date_set",
            "cost_contract_unit",
            "initial_backlog_policy",
        ],
        "synthetic": True,
        "s5_business_loss_policy_hash": S5_POLICY,
        "s2_policy_hash": S2_POLICY,
        "cost_contract_hashes": list(COST_HASHES),
        "privacy_policy": "EXPLICIT_SYNTHETIC_FIXTURE_AND_RESULTS_ONLY",
        "source_evidence_sha256": upstream(),
    }


def inputs() -> tuple[w.SavedForecastCurve, dict[str, tuple[w.CapacityDay, ...]]]:
    f = load(REPOSITORY / FIXTURE)
    if f["synthetic"] is not True or f["hierarchy_entity_id"] != "SYNTHETIC_COMPANY":
        raise ValueError("SYNTHETIC_INPUT_REQUIRED")
    rows = tuple(
        w.SavedForecastDay(
            date.fromisoformat(r["date"]),
            Decimal(r["point_forecast_kg"]),
            Decimal(r["upper_planning_bound_80_kg"]),
            Decimal(r["upper_planning_bound_90_kg"]),
        )
        for r in f["daily_rows"]
    )
    curve = w.SavedForecastCurve(
        f["fixture_id"],
        digest(f["daily_rows"]),
        datetime.fromisoformat(f["forecast_origin"]),
        f["hierarchy_level"],
        f["hierarchy_entity_id"],
        digest({"synthetic": True, "entity": "SYNTHETIC_COMPANY"}),
        rows,
    )
    schedules = {
        s["scenario_id"]: tuple(
            w.CapacityDay(
                r.date,
                s["capacity_mode"],
                Decimal(s["daily_handling_capacity_kg"])
                if s["daily_handling_capacity_kg"] is not None
                else None,
                s["workforce_count"],
                Decimal(s["productivity_kg_per_person_day"])
                if s["productivity_kg_per_person_day"] is not None
                else None,
                s["buffer_supplied"],
                Decimal(s["buffer_handling_capacity_kg"]),
            )
            for r in rows
        )
        for s in f["scenarios"]
    }
    if len(rows) != 15 or len(schedules) != 3:
        raise ValueError("SYNTHETIC_MATRIX_ACCOUNTING_FAILED")
    return curve, schedules


def prepare(output: Path) -> None:
    output_guard(output)
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    p = policy()
    contract = {"task_id": TASK, "base_main_sha": BASE, "policy": p, "policy_hash": digest(p)}
    save(output / "contract.json", contract)


def verify(output: Path) -> dict[str, Any]:
    c = load(output / "contract.json")
    if c != {
        "task_id": TASK,
        "base_main_sha": BASE,
        "policy": policy(),
        "policy_hash": digest(policy()),
    }:
        raise ValueError("WHAT_IF_CONTRACT_DRIFT")
    return dict(c)


def operational(result: dict[str, Any]) -> dict[str, Any]:
    """Exclude identity/provenance, retain every physical/loss/utilization field."""
    excluded = {
        "scenario_id",
        "scenario_hash",
        "result_hash",
        "daily_rows",
        "total_base_handling_capacity_kg",
        "total_buffer_capacity_kg",
    }
    daily_excluded = {
        "capacity_mode",
        "daily_handling_capacity_kg",
        "workforce_count",
        "productivity_kg_per_person_day",
        "buffer_supplied",
        "buffer_handling_capacity_kg",
        "row_hash",
    }
    return {k: v for k, v in result.items() if k not in excluded} | {
        "daily_rows": [
            {k: v for k, v in r.items() if k not in daily_excluded} for r in result["daily_rows"]
        ]
    }


def acceptance_matrix() -> tuple[dict[str, Any], dict[str, Any]]:
    curve, schedules = inputs()
    results, groups = {}, {}
    for level in w.PLANNING_LEVELS:
        for cost in synthetic_contracts():
            key = f"{level}__{cost.contract_id}"
            scenarios = tuple(
                w.DecisionScenario(sid, "R1", curve, level, cost, rows)
                for sid, rows in sorted(schedules.items())
            )
            evaluated = [w.simulate(s) for s in scenarios]
            if operational(evaluated[1]) != operational(evaluated[2]):
                raise ValueError("EQUIVALENT_CAPACITY_PARITY_FAILED")
            results[key] = evaluated
            groups[key] = w.compare_and_rank(scenarios)
    if len(groups) != 9 or sum(len(v) for v in results.values()) != 27:
        raise ValueError("SYNTHETIC_MATRIX_ACCOUNTING_FAILED")
    return results, groups


def run(output: Path) -> None:
    output_guard(output)
    c = verify(output)
    save(output / "run-started.json", {"policy_hash": c["policy_hash"]})
    save(output / "process-receipt.json", {"process_id": os.getpid()})
    results, groups = acceptance_matrix()
    if c["policy"]["source_evidence_sha256"] != upstream():
        raise ValueError("SOURCE_ARTIFACT_MUTATION")
    save(output / OUTPUT_NAMES[0], {"synthetic": True, "results": results})
    save(output / OUTPUT_NAMES[1], {"synthetic": True, "comparison_groups": groups})
    save(
        output / "execution-receipt.json",
        {
            "policy_hash": c["policy_hash"],
            "source_immutability_status": "PASS",
            "equivalent_capacity_parity": "PASS",
            "artifact_hashes": {n: sha((output / n).read_bytes()) for n in OUTPUT_NAMES},
        },
    )


def privacy(value: Any) -> None:
    if isinstance(value, dict):
        if {
            "base_id",
            "row_key",
            "actual",
            "actual_kg",
            "labels",
            "password",
            "token",
            "secret",
            "credentials",
            "database_url",
            "source_file",
        } & value.keys():
            raise ValueError("PUBLIC_PRIVATE_DATA_LEAK")
        if "hierarchy_entity_id" in value and value["hierarchy_entity_id"] != "SYNTHETIC_COMPANY":
            raise ValueError("PUBLIC_PRIVATE_DATA_LEAK")
        for v in value.values():
            privacy(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            privacy(v)
    elif isinstance(value, str) and re.search(
        r"/(?:Users|home|root|tmp|private)/|(?:postgres(?:ql)?|https?)://|(?i:bearer\s)", value
    ):
        raise ValueError("PUBLIC_PRIVATE_DATA_LEAK")


def publish(primary: Path, replay: Path, public: Path) -> None:
    output_guard(public, (primary, replay))
    if primary.resolve() == replay.resolve() or load(primary / "process-receipt.json") == load(
        replay / "process-receipt.json"
    ):
        raise ValueError("FRESH_PROCESS_REPLAY_REQUIRED")
    c = verify(primary)
    receipt = load(primary / "execution-receipt.json")
    if verify(replay) != c or receipt != load(replay / "execution-receipt.json"):
        raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    for name in ("contract.json", *OUTPUT_NAMES):
        raw = (primary / name).read_bytes()
        if raw != (replay / name).read_bytes() or (
            name in OUTPUT_NAMES and sha(raw) != receipt["artifact_hashes"][name]
        ):
            raise ValueError("DETERMINISTIC_REPLAY_FAILED")
    if public.exists():
        raise ValueError("PUBLIC_OUTPUT_ALREADY_EXISTS")
    # Equal/tampered copies alone are not proof: rederive the fixed synthetic matrix.
    results, groups = acceptance_matrix()
    expected_outputs = (
        {"synthetic": True, "results": results},
        {"synthetic": True, "comparison_groups": groups},
    )
    if any(
        (primary / name).read_bytes() != canonical(expected)
        for name, expected in zip(OUTPUT_NAMES, expected_outputs, strict=True)
    ) or receipt != {
        "policy_hash": c["policy_hash"],
        "source_immutability_status": "PASS",
        "equivalent_capacity_parity": "PASS",
        "artifact_hashes": {
            name: sha(canonical(expected))
            for name, expected in zip(OUTPUT_NAMES, expected_outputs, strict=True)
        },
    }:
        raise ValueError("SYNTHETIC_RESULT_DRIFT")
    flags = {
        k: False
        for k in (
            "current_season_actual_dependency",
            "current_season_actual_read",
            "current_season_actual_import",
            "current_season_actual_scoring",
            "point_forecast_reexecuted",
            "model_training_executed",
            "model_refit_executed",
            "model_tuning_executed",
            "new_forecast_model_created",
            "optimization_implemented",
            "auto_capacity_search_implemented",
            "workforce_scheduling_implemented",
            "multi_factory_routing_implemented",
            "automatic_peak_shaving_implemented",
            "automatic_execution_implemented",
            "db_migration_created",
            "http_what_if_api_implemented",
            "mcp_what_if_tools_implemented",
            "frontend_changed",
            "scheduler_created",
            "systemd_timer_changed",
            "s0_s5_changed",
            "canonical_company_cost_established",
            "real_roi_validated",
            "s6_formal_complete",
            "ready_authorized",
            "merge_authorized",
            "version_closeout_authorized",
            "version_closeout_started",
            "v0_16_version_complete",
            "v0_17_started",
            "tag_authorized",
            "release_authorized",
        )
    }
    evidence = flags | {
        "task_id": TASK,
        "version": "0.16.0",
        "stage": "S6",
        "base_main_sha": BASE,
        "synthetic": True,
        "s6_implementation_authorized": True,
        "engineering_result": "PASS",
        "s5_formal_prerequisite_verified": True,
        "s5_merge_commit_sha": BASE,
        "s5_post_merge_ci_run_id": 37622083956,
        "what_if_policy_hash": c["policy_hash"],
        "s5_business_loss_policy_hash": S5_POLICY,
        "s2_policy_hash": S2_POLICY,
        "what_if_is_scenario_simulation": True,
        "what_if_is_new_forecast_model": False,
        "initial_backlog_kg": "0",
        "buffer_semantics": "SAME_DAY_ADDITIVE_HANDLING_CAPACITY",
        "supported_planning_levels": list(w.PLANNING_LEVELS),
        "supported_hierarchy_levels": list(w.HIERARCHY_LEVELS),
        "farm_hierarchy_admitted": False,
        "factory_hierarchy_admitted": False,
        "acceptance_planning_level_count": 3,
        "acceptance_cost_contract_count": 3,
        "acceptance_scenario_count": 3,
        "acceptance_scenario_run_count": 27,
        "acceptance_comparison_group_count": 9,
        "utilization_numeric_exception_authorized": True,
        "amendment_id": w.AMENDMENT_ID,
        "utilization_numeric_policy_version": w.UTILIZATION_POLICY_VERSION,
        "deterministic_replay": "PASS",
        "source_immutability_status": "PASS",
        "privacy_status": "PASS",
        "direct_and_workforce_equivalent_capacity_parity": "PASS",
        "external_exact_head_ci": "REQUIRED_SEPARATE_TERMINAL_PR_RECEIPT",
        "stop": True,
    }
    evidence |= {
        k: v
        for k, v in c["policy"].items()
        if k.endswith("policy_version")
        or k.startswith("utilization_")
        or k
        in (
            "authoritative_kg_inexact_allowed",
            "authoritative_loss_inexact_allowed",
            "rounded_utilization_used_for_ranking",
        )
    }
    files = {
        "what-if-policy-r1.json": c,
        "synthetic-saved-forecast-r1.json": {
            "synthetic": True,
            "saved_forecast": inputs()[0].payload(),
        },
        "synthetic-scenarios-r1.json": load(REPOSITORY / FIXTURE),
        "synthetic-scenario-results-r1.json": load(primary / OUTPUT_NAMES[0]),
        "scenario-ranking-summary-r1.json": load(primary / OUTPUT_NAMES[1]),
        "deterministic-replay-report-r1.json": {
            "result": "PASS",
            "fresh_processes_verified": True,
            "artifact_hashes": receipt["artifact_hashes"],
        },
        "source-binding-r1.json": {
            "source_hashes": c["policy"]["source_evidence_sha256"],
            "source_immutability_status": "PASS",
        },
        "privacy-scan-report-r1.json": {
            "result": "PASS",
            "synthetic": True,
            "public_private_data_leak": False,
        },
        "v0.16-s6-what-if-decision-simulator-r1.json": evidence,
    }
    for value in files.values():
        privacy(value)
    for name, value in files.items():
        save(public / name, value)
    save(
        public / "manifest-r1.json",
        {
            "policy_hash": c["policy_hash"],
            "files": {n: sha((public / n).read_bytes()) for n in sorted(files)},
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline synthetic what-if acceptance")
    parser.add_argument("phase", choices=("PREPARE", "RUN", "REPLAY", "PUBLISH"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay-output", type=Path)
    parser.add_argument("--public-output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.phase == "PREPARE":
            prepare(args.output)
        elif args.phase == "RUN":
            run(args.output)
        elif args.phase == "REPLAY":
            if args.replay_output is None or not (args.output / "execution-receipt.json").is_file():
                raise ValueError("PRIMARY_AND_REPLAY_REQUIRED")
            verify(args.output)
            output_guard(args.replay_output, (args.output,))
            prepare(args.replay_output)
            run(args.replay_output)
        else:
            if args.replay_output is None or args.public_output is None:
                raise ValueError("REPLAY_AND_PUBLIC_REQUIRED")
            publish(args.output, args.replay_output, args.public_output)
    except Exception as exc:
        code = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch("[A-Z][A-Z0-9_]+", str(exc))
            else "WHAT_IF_OPERATOR_FAILED"
        )
        print(json.dumps({"result": "FAIL", "code": code}))
        return 1
    print(json.dumps({"result": "PASS", "phase": args.phase}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
