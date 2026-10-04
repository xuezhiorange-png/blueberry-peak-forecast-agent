"""Public-evidence-only S5 projection. Never imports research execution modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

BASE = "d1626550ced8ffde3dc689132e0a2779557a9a9c"
REPOSITORY = "xuezhiorange-png/blueberry-peak-forecast-agent"
TASK_ID = "V0_13_S5_FEATURE_VALUE_DECISION_AND_VERSION_CLOSEOUT_R1"
OUTPUT = "docs/v0-13/evidence/v0.13-s5-feature-value-decision-and-version-closeout-r1.json"
RESULT_FIELDS = (
    "WEATHER_INCREMENTAL_VALUE",
    "GDD_INCREMENTAL_VALUE",
    "WEATHER_PLUS_GDD_INCREMENTAL_VALUE",
    "PEAK_TIMING_INCREMENTAL_VALUE",
)
SLICES: list[dict[str, Any]] = [
    {
        "stage": "S0",
        "pr": 668,
        "head": "116f1b22c19b9e79d8d2c12be56f496b89550c50",
        "merge": "4b146965e9b47eb18140d7c0839035761faedba2",
        "exact_head_ci": 37109926038,
        "post_merge_ci": 37112958796,
        "stem": "v0.13.0-version-plan-and-scope-freeze",
    },
    {
        "stage": "S1",
        "pr": 669,
        "head": "a1e6535c45b87f025a4dbd310d5bfe7cf1cb8c61",
        "merge": "4f0caedaf7a4f9942371f1fd92dc5132c3c671b5",
        "exact_head_ci": 37115953375,
        "post_merge_ci": 37118275995,
        "stem": "v0.13-s1-gdd-scientific-definition-freeze",
    },
    {
        "stage": "S2",
        "pr": 670,
        "head": "1e63e450c2150b7b76441d80f495019e74ef0979",
        "merge": "e9397e6ac92fc03ba269b7e1b3efae7a13857624",
        "exact_head_ci": 37127000309,
        "post_merge_ci": 37129458883,
        "stem": "v0.13-s2-gdd-feature-coverage-audit-r2",
    },
    {
        "stage": "S3",
        "pr": 671,
        "head": "eb292e80635b55bdedafa7e61f8f1c8c357d7961",
        "merge": "eaaf9f592d9fa6793a206dd22e8823c96e36f977",
        "exact_head_ci": 37136013918,
        "post_merge_ci": 37167268254,
        "stem": "v0.13-s3-four-model-controlled-oot-r1",
    },
    {
        "stage": "S4",
        "pr": 672,
        "head": "26d0319e5bd29960728929e940bc2cc22e12ce8c",
        "merge": BASE,
        "exact_head_ci": 37173408844,
        "post_merge_ci": 37175977467,
        "stem": "v0.13-s4-temporal-peak-and-oracle-r2",
    },
]
# SHA256 of committed public JSON then corresponding Markdown, at each slice merge.
PINS = [
    (
        "445be5492dfcfe7e440eb7d66bcce8c3ab246c1e9024810d40e6a4242c30cdc6",
        "14cf5c6fb9f5977a4777b2e628ce7b9357a0f590de894422fe9a13acd3837f28",
    ),
    (
        "b4c141df6f10fb6861dd7063b8b2a81839d3713225823d3dd0324ce863ce777a",
        "f869fb2ec9bb49b7257d06f69e9e08fe88505a41d0ce08f02d6256e621e5d3d5",
    ),
    (
        "c34f31c7913dab7ca98b67b889937ad85fa4e2c35b515b88cca0abd3da498098",
        "108de65d3bb22cd9e067dd83b8c96bec08e187ec83705a9506290ec7bd01126e",
    ),
    (
        "50b91c5507e5fd48539f51cec6856ba7afb5c5de201c27a27cf367fd51fd7c5b",
        "f05b55072695519cc1d1abd3445fdf2b46c61fe1cc417fba7e537ec99bcd0da1",
    ),
    (
        "53bc283588951a266354be06b9f4c8afcb507db5a44729dccdec7efcd0464042",
        "4c7b81a6b769f63d91ac8ee2a81315bd9e5a4bcab9b84ed1bf449562fdb00de9",
    ),
]
BLOB_PINS = [
    ("b6b3bd3affe5400f68f1cbb16a31cc1ed0ffda52", "4a7b9613cbe54442362007b42d5a5cbf47ac608c"),
    ("ad54ea8fce156701c82e534a74fa967012179d0f", "3d53fed7d46b70ce1b296d8a706f0de1a5ec48d1"),
    ("dee87190e10bed457137df25233eca8aaa8bc7e1", "1c4d4703fd7d8bd3adfcc26bdc39f689f1974566"),
    ("6538202f0443b64ec5991c11a9f9f408e02b7208", "42f51675faf73429117a8c779cdad3efbb469a8a"),
    ("1a516ba3db4c8047c59bdf6976758b63430f55c0", "db2224d20e2923c2de3218db00379a4040cc4869"),
]


class CloseoutError(ValueError):
    """Stable fail-closed public authority error."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise CloseoutError(code)


def command(root: Path, args: list[str]) -> bytes:
    return subprocess.check_output(args, cwd=root)


def git(root: Path, *args: str) -> str:
    return command(root, ["git", *args]).decode().strip()


def verify_public_pin(data: bytes, sha256: str, original_blob: str, base_blob: str) -> None:
    require(
        original_blob == base_blob and hashlib.sha256(data).hexdigest() == sha256,
        "PREVIOUS_SLICE_EVIDENCE_DRIFT",
    )


def load_public_inputs(root: Path, *, verify_git: bool = True) -> dict[str, Any]:
    """Fixed public allowlist only; compare merge/base/worktree identities."""
    inputs: dict[str, Any] = {"pins": {}}
    for s, pins, blobs in zip(SLICES, PINS, BLOB_PINS, strict=True):
        paths = [f"docs/v0-13/evidence/{s['stem']}.json", f"docs/v0-13/{s['stem']}.md"]
        for i, (path, sha) in enumerate(zip(paths, pins, strict=True)):
            # CI uses explicit static public fixtures, not a claimed live Git audit.
            # The writing CLI always uses the default live-history verification.
            original = git(root, "rev-parse", f"{s['merge']}:{path}") if verify_git else blobs[i]
            current = git(root, "rev-parse", f"{BASE}:{path}") if verify_git else blobs[i]
            data = (
                command(root, ["git", "show", f"{BASE}:{path}"])
                if verify_git
                else (root / path).read_bytes()
            )
            verify_public_pin(data, sha, original, current)
            require(current == blobs[i], "PREVIOUS_SLICE_EVIDENCE_DRIFT")
            verify_public_pin((root / path).read_bytes(), sha, original, current)
            inputs["pins"][path] = {
                "stage": s["stage"],
                "slice_merge": s["merge"],
                "slice_merge_blob": original,
                "base_blob": current,
                "sha256": sha,
                "immutability": "PASS",
            }
            if i == 0:
                inputs[s["stage"]] = json.loads(data)
    return inputs


def validate_lineage_record(
    s: dict[str, Any], pr: dict[str, Any], ci: dict[str, Any], post: dict[str, Any]
) -> dict[str, Any]:
    require(
        pr.get("state") == "MERGED"
        and pr.get("headRefOid") == s["head"]
        and pr.get("mergeCommit", {}).get("oid") == s["merge"],
        "SLICE_PR_LINEAGE_MISMATCH",
    )
    for run, sha in [(ci, s["head"]), (post, s["merge"])]:
        jobs = run.get("jobs", [])
        require(
            run.get("status") == "completed"
            and run.get("conclusion") == "success"
            and run.get("headSha") == sha
            and len(jobs) == 12
            and all(j.get("conclusion") in ("success", "skipped") for j in jobs),
            "SLICE_CI_LINEAGE_MISMATCH",
        )
    return dict(
        s,
        lineage_pass="PASS",
        exact_head_jobs_success=sum(j["conclusion"] == "success" for j in ci["jobs"]),
        post_merge_jobs_success=sum(j["conclusion"] == "success" for j in post["jobs"]),
        post_merge_jobs_skipped=sum(j["conclusion"] == "skipped" for j in post["jobs"]),
    )


def verify_live_lineage(root: Path) -> list[dict[str, Any]]:
    require(git(root, "rev-parse", "origin/main") == BASE, "V0_13_BASE_CHANGED_BEFORE_S5")
    require(
        git(root, "remote", "get-url", "origin").removesuffix(".git")
        == f"https://github.com/{REPOSITORY}",
        "REPOSITORY_IDENTITY_MISMATCH",
    )
    records = []
    previous = None
    for s in SLICES:
        for ancestor in [s["merge"], previous]:
            if ancestor:
                subprocess.run(
                    [
                        "git",
                        "merge-base",
                        "--is-ancestor",
                        ancestor,
                        s["merge"] if ancestor == previous else BASE,
                    ],
                    cwd=root,
                    check=True,
                )
        require(
            s["head"] in git(root, "show", "-s", "--format=%P", s["merge"]).split(),
            "REVIEWED_HEAD_NOT_MERGE_PARENT",
        )
        pr = json.loads(
            command(
                root,
                [
                    "gh",
                    "pr",
                    "view",
                    str(s["pr"]),
                    "--repo",
                    REPOSITORY,
                    "--json",
                    "state,headRefOid,mergeCommit",
                ],
            )
        )
        runs = [
            json.loads(
                command(
                    root,
                    [
                        "gh",
                        "run",
                        "view",
                        str(s[k]),
                        "--repo",
                        REPOSITORY,
                        "--json",
                        "status,conclusion,headSha,jobs",
                    ],
                )
            )
            for k in ("exact_head_ci", "post_merge_ci")
        ]
        records.append(validate_lineage_record(s, pr, *runs))
        previous = s["merge"]
    return records


def map_predictive_gate(status: str) -> str:
    mapping = {
        "MEETS_SUPPORTED_CRITERIA": "SUPPORTED",
        "MEETS_NOT_SUPPORTED_CRITERIA": "NOT_SUPPORTED",
        "INCONCLUSIVE_BY_FROZEN_RULE": "INCONCLUSIVE",
    }
    require(status in mapping, "UNKNOWN_PREDICTIVE_GATE")
    return mapping[status]


def joint_incremental_decision(
    vs_base: str, gdd_on_weather: str, weather_on_gdd: str
) -> tuple[str, bool]:
    """RQ3 requires BOTH incremental legs, never the vs-base gain alone."""
    require(
        all(
            v in ("SUPPORTED", "INCONCLUSIVE", "NOT_SUPPORTED")
            for v in (vs_base, gdd_on_weather, weather_on_gdd)
        ),
        "UNKNOWN_DECISION",
    )
    legs = (gdd_on_weather, weather_on_gdd)
    if "NOT_SUPPORTED" in legs:
        return "NOT_SUPPORTED", False
    if all(v == "SUPPORTED" for v in legs):
        return "SUPPORTED", True
    return "INCONCLUSIVE", False


def build_closeout(inputs: dict[str, Any], lineage: list[dict[str, Any]]) -> dict[str, Any]:
    s0, s1, s2, s3, s4 = (inputs[f"S{i}"] for i in range(5))
    require(s0["result_fields"] == list(RESULT_FIELDS), "S0_RESULT_FIELD_CONTRACT_MISMATCH")
    require(
        len(lineage) == 5
        and all(
            all(r.get(k) == s[k] for k in s) and r.get("lineage_pass") == "PASS"
            for r, s in zip(lineage, SLICES, strict=True)
        ),
        "SLICE_LINEAGE_INCOMPLETE",
    )
    require(
        s1["GDD_DEFINITION_ID"] == "V0_13_GDD_7C_SIMPLE_MEAN_R1"
        and s1["ROLLING_GDD_WINDOWS"] == [7, 14, 30]
        and s2["V0_13_S2_COMPLETE"] is True,
        "PRIOR_DEFINITION_OR_COVERAGE_MISMATCH",
    )
    require(
        s3["V0_7_WEATHER_INCREMENTAL_VALUE"] == "INCONCLUSIVE"
        and s3["V0_13_S3_COMPLETE"] is True
        and s4["V0_13_S4_COMPLETE"] is True
        and s4["ORACLE_DEPLOYABLE"] is False
        and s4["ORACLE_PROSPECTIVE_EQUIVALENT"] is False
        and s4["ORACLE_SUPPORT_CLASSIFICATION"] == "NOT_APPLICABLE_RESEARCH_UPPER_BOUND_ONLY",
        "SCIENTIFIC_AUTHORITY_OR_ORACLE_BOUNDARY_MISMATCH",
    )
    comparisons = s3["control_report"]["comparisons"]
    gates = {name: value["gate"]["status"] for name, value in comparisons.items()}
    mapped = {name: map_predictive_gate(value) for name, value in gates.items()}
    joint, complementary = joint_incremental_decision(
        mapped["COMBINED_VALUE"], mapped["GDD_ON_TOP_OF_WEATHER"], mapped["WEATHER_ON_TOP_OF_GDD"]
    )
    timing = s4["control_report"]["timing_gates"]
    peak = s4["PEAK_TIMING_INCREMENTAL_VALUE"]
    require(
        peak in s0["decision_labels"]
        and all(v["status"] in s0["decision_labels"] for v in timing.values()),
        "UNKNOWN_TIMING_GATE",
    )
    results = dict(
        zip(RESULT_FIELDS, [mapped["WEATHER_VALUE"], mapped["GDD_VALUE"], joint, peak], strict=True)
    )
    evidence: dict[str, Any] = {
        "TASK_ID": TASK_ID,
        "BASE_SHA": BASE,
        "VERSION": s0["VERSION"],
        "VERSION_NAME": s0["VERSION_NAME"],
        "VERSION_NAME_CN": s0["VERSION_NAME_CN"],
        "RELEASE_CLASS": s0["RELEASE_CLASS"],
        "RESULT": "PASS",
        "MODE": "PUBLIC_EVIDENCE_ONLY_DECISION_AND_VERSION_CLOSEOUT",
        "git_lineage": lineage,
        "ALL_PR_MERGED": True,
        "ALL_MERGE_COMMITS_ANCESTORS_OF_MAIN": True,
        "SLICE_ORDER_S0_S1_S2_S3_S4": "PASS",
        "public_evidence_pins": inputs["pins"],
        "PREVIOUS_SLICE_EVIDENCE_IMMUTABILITY": "PASS",
        "final_results": results,
        "research_questions": s0["research_questions"],
        "rq_results": dict(zip(s0["research_questions"], results.values(), strict=True)),
        "closeout_labels": {k: f"RESEARCH_CLOSEOUT_FEATURE_{v}" for k, v in results.items()},
        "S3_predictive_gates": gates,
        "S3_quantity_evidence": comparisons,
        "S4_timing_evidence": timing,
        "S4_H15_authoritative_views": s4["control_report"]["h15_counts"],
        "WEATHER_GDD_COMPLEMENTARITY_ESTABLISHED": complementary,
        "M3_VS_M0_QUANTITY_GATE": gates["COMBINED_VALUE"],
        "WEATHER_QUANTITY_INCREMENTAL_VALUE": mapped["WEATHER_VALUE"],
        "WEATHER_PEAK_TIMING_INCREMENTAL_VALUE": timing["WEATHER_TIMING"]["status"],
        "PEAK_TIMING_SUPPORTED_FAMILY": s4["PEAK_TIMING_SUPPORTED_FAMILY"],
        "oracle": {
            "support_classification": s4["ORACLE_SUPPORT_CLASSIFICATION"],
            "upper_bound_evidence": "MIXED",
            "comparisons": s4["control_report"]["oracle_comparisons"],
            "two_fold_rolling7_direction_consistent": False,
            "deployable": False,
            "prospective_equivalent": False,
            "as_issued_forecast": False,
        },
        "ORACLE_UPPER_BOUND_EVIDENCE": "MIXED",
        "WEATHER_INCREMENTAL_VALUE_SCOPE": (
            "HISTORICAL_PAST_OBSERVED_WEATHER_QUANTITY_SIGNAL_ON_FROZEN_H7_H15_OOT_TASK"
        ),
        "WEATHER_SUPPORT_SCOPE": "HISTORICAL_PAST_OBSERVED_H7_H15_QUANTITY_ONLY",
        "WEATHER_LANE_A": "PAST_OBSERVED_WEATHER",
        "ERA5_FORECAST_TIME_KNOWN_AT_STATUS": "NOT_ESTABLISHED",
        "GDD_DEFINITION_ID": s1["GDD_DEFINITION_ID"],
        "GDD_WINDOWS": ["W7", "W14", "W30"],
        "GDD_SCOPE": (
            "CURRENT_PREDECLARED_7C_ROLLING_REPRESENTATION_ON_CONSUMED_HISTORICAL_OOT_ONLY"
        ),
        "GDD_IS_UNIVERSAL_PHYSIOLOGY": False,
        "V0_7_WEATHER_INCREMENTAL_VALUE": "INCONCLUSIVE",
        "VERSION_RESEARCH_OUTCOME_DESCRIPTOR": "MIXED_FEATURE_FAMILY_OUTCOME",
        "NEXT_PHASE_QUANTITY_RECOMMENDATION": "PROSPECTIVE_AS_ISSUED_WEATHER_VALIDATION",
        "NEXT_PHASE_TIMING_RECOMMENDATION": "DIRECT_PHENOLOGY_AND_IN_SEASON_STATE_RESEARCH",
        "CURRENT_7C_ROLLING_GDD_NEXT_PHASE_PRIORITY": "DEPRIORITIZE_CURRENT_REPRESENTATION",
        "quantity_validation_requirements": [
            "issued_at",
            "known_at<=forecast_origin",
            "forecast_snapshot_sealing",
            "future_actual_accumulation",
            "locked_scoring",
        ],
        "timing_recommendation_only": [
            "direct_phenology_anchors",
            "cultivar_botanical_identity",
            "tree_age_productive_structure",
            "flower_fruit_set_observations",
            "current_season_harvest_progression",
            "maturity_harvest_ready_inventory_state",
        ],
        "NEW_VERSION_REQUIRED_FOR_GDD_RESTART": True,
        "NEW_BIOLOGICAL_AUTHORITY_OR_NEW_PREDECLARED_HYPOTHESIS_REQUIRED": True,
        "CI_STRATEGY": "Public evidence and synthetic contract fixtures only; no private data.",
        "HEAD_CI_BINDING": (
            "Final head and terminal exact-head CI are external PR/receipt authorities, "
            "not self-referenced in this commit."
        ),
    }
    evidence.update(results)
    for name, gate in gates.items():
        evidence[f"{name}_PREDICTIVE_GATE_STATUS"] = gate
    for name, value in timing.items():
        evidence[f"{name}_STATUS"] = value["status"]
        evidence[f"{name}_SHAPE_COMBINED_DELTA"] = (
            value["deltas"]["combined"]["shape_error"] or "NOT_COMPUTABLE"
        )
    for i in range(6):
        evidence[f"V0_13_S{i}_COMPLETE"] = True
    for i in range(5):
        evidence[f"S{i}_EVIDENCE_MODIFIED"] = False
    for key in (
        "V0_13_VERSION_CLOSEOUT_COMPLETE",
        "V0_13_VERSION_COMPLETE",
        "V0_13_RESEARCH_WORKFLOW_COMPLETE",
        "V0_13_FEATURE_DEVELOPMENT_FROZEN",
        "NO_MORE_V0_13_GDD_THRESHOLD_SEARCH",
        "NO_MORE_V0_13_WEATHER_FEATURE_SEARCH",
        "NO_MORE_V0_13_ORACLE_SEARCH",
        "V0_13_S5_AUTHORIZED",
    ):
        evidence[key] = True
    for key in (
        "PRIVATE_HARVEST_ROW_READ",
        "PRIVATE_WEATHER_DATA_READ",
        "MODEL_TRAINING_EXECUTED",
        "BACKTEST_EXECUTED",
        "SCORING_EXECUTED",
        "MODEL_PREDICTIONS_GENERATED",
        "ORACLE_EXECUTED",
        "HYPERPARAMETER_SEARCH",
        "FEATURE_SEARCH",
        "GDD_SWEEP",
        "S3_REEXECUTION",
        "S4_REEXECUTION",
        "NEW_MODEL_ARTIFACT",
        "NEW_PREDICTION_ARTIFACT",
        "NEW_MCP_TOOL",
        "PRODUCTION_CONFIG_CHANGE",
        "NEW_BLIND_VALIDATION",
        "PROSPECTIVE_ACCURACY_VALIDATED",
        "PRODUCTION_USE_APPROVED",
        "MODEL_PRODUCTION_PROMOTION_AUTHORIZED",
        "WEATHER_MODEL_PROMOTION_AUTHORIZED",
        "PRODUCTION_LIKE_WEATHER_VALIDATION",
        "REAL_PROSPECTIVE_ENABLED",
        "ORACLE_DEPLOYABLE",
        "ORACLE_PROSPECTIVE_EQUIVALENT",
        "AS_ISSUED_FORECAST",
        "WEATHER_PEAK_TIMING_SUPPORTED",
        "CURRENT_GDD_REPRESENTATION_SUPPORTED",
        "V0_14_AUTHORIZED",
        "NEXT_VERSION_IMPLEMENTATION_AUTHORIZED",
        "PRIVATE_DATA_REQUIRED_FOR_CI",
        "V0_12_REOPENED",
        "V0_12_ARTIFACTS_CHANGED",
        "V0_7_FILES_MODIFIED",
        "V0_9_FILES_MODIFIED",
        "READY_AUTHORIZED",
        "MERGE_AUTHORIZED",
        "AUTO_MERGE",
        "TAG_AUTHORIZED",
        "RELEASE_AUTHORIZED",
        "TAG_CREATED",
        "RELEASE_CREATED",
    ):
        evidence[key] = False
    evidence["LATEST_FORMAL_RELEASE"] = "v0.11.0"
    evidence["closeout_hash"] = hashlib.sha256(canonical(evidence)).hexdigest()
    return evidence


def canonical(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Validate existing public closeout; no writes"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = build_closeout(load_public_inputs(root), verify_live_lineage(root))
    target = root / OUTPUT
    if args.check:
        require(target.read_bytes() == canonical(report), "CLOSEOUT_PROJECTION_DRIFT")
    else:
        # Fixed public output only; reject overwrite or any operator-selected private path.
        with target.open("xb") as stream:
            stream.write(canonical(report))
    print(
        json.dumps({"TASK_ID": TASK_ID, "RESULT": "PASS", "closeout_hash": report["closeout_hash"]})
    )


if __name__ == "__main__":
    main()
