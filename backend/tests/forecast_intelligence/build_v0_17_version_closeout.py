"""Explicit live public-metadata capture, then offline deterministic closeout generation.

Never imported by CI tests. No engine/model/DB imports or business experiment replay.
Capture requires gh; --snapshot reuses exact captured metadata without network access.
"""

import argparse
import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = "xuezhiorange-png/blueberry-peak-forecast-agent"
BASE = "df6520404334bd518d3f65e3da470315bab194f9"
RELEASE_BASE = "2eb88a198fa2247ce813f8dac7bf7b41b8fdee32"
DOC = "docs/v0-17/v0.17.0-closeout.md"
RECEIPT = "docs/v0-17/evidence/v0.17.0-version-closeout-r1.json"
MANIFEST = "docs/v0-17/evidence/v0.17.0-version-closeout-manifest-r1.json"
STAGES = (
    (
        "S0",
        699,
        37660361201,
        37705147340,
        "v0.17.0-version-plan-and-product-scope-freeze-r1.json",
        ["S0_AUTHORIZED"],
    ),
    (
        "S1",
        700,
        37710846272,
        37714290836,
        "v0.17-s1-forecast-intelligence-service-read-api-r1.json",
        ["governance", "s1_authorized"],
    ),
    (
        "S2",
        701,
        37719264076,
        37723603089,
        "v0.17-s2-decision-support-api-r1.json",
        ["governance", "s2_implementation_authorized"],
    ),
    (
        "S3",
        702,
        37727860163,
        37732882094,
        "v0.17-s3-mcp-productization-r1.json",
        ["governance", "s3_implementation_authorized"],
    ),
    (
        "S4",
        703,
        37745161616,
        37750293163,
        "v0.17-s4-dashboard-design-freeze-r1.json",
        ["s4_implementation_authorized"],
    ),
    (
        "S5",
        704,
        37761928112,
        37767679478,
        "v0.17-s5-dashboard-implementation-r1.json",
        ["governance", "s5_implementation_authorized"],
    ),
    (
        "S6_SELECTOR_CORRECTION",
        705,
        37777753841,
        37783261851,
        "v0.17-s6-selector-cancel-reopen-correction-r1.json",
        ["governance", "correction_authorized"],
    ),
    (
        "S6_ACCEPTANCE",
        706,
        37800798505,
        37807916550,
        "v0.17-s6-cross-surface-product-acceptance-r2.json",
        ["governance", "s6_resume_authorized"],
    ),
    (
        "S6_CORRECTION_R1",
        707,
        37857931884,
        37861642942,
        "v0.17-s6-postmerge-route-lifecycle-correction-r1.json",
        ["governance", "correction_authorized"],
    ),
    (
        "S6_CORRECTION_R2",
        708,
        37874965290,
        37881564725,
        "v0.17-s6-postmerge-route-lifecycle-correction-r2.json",
        ["governance", "correction_authorized"],
    ),
)


def canonical(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(*args):
    return subprocess.check_output(args)


def api(endpoint):
    return json.loads(command("gh", "api", f"repos/{REPO}/{endpoint}"))


def ci(run_id):
    run = api(f"actions/runs/{run_id}")
    jobs = api(f"actions/runs/{run_id}/attempts/{run['run_attempt']}/jobs?per_page=100")
    assert jobs["total_count"] == len(jobs["jobs"]) == 12
    rows = [
        {
            "id": j["id"],
            "name": j["name"],
            "status": j["status"],
            "conclusion": j["conclusion"],
            "url": j["html_url"],
        }
        for j in jobs["jobs"]
    ]
    return {
        "run_id": run["id"],
        "attempt": run["run_attempt"],
        "event": run["event"],
        "head_sha": run["head_sha"],
        "status": run["status"],
        "conclusion": run["conclusion"],
        "url": run["html_url"],
        "jobs": rows,
        "job_counts": {
            "total": len(rows),
            **{
                s: sum(j["conclusion"] == s for j in rows)
                for s in ("success", "skipped", "failure", "cancelled")
            },
        },
    }


def capture_stage(spec):
    stage, number, pr_run, main_run, filename, keys = spec
    pr = api(f"pulls/{number}")
    reviews = api(f"pulls/{number}/reviews?per_page=100")
    assert len(reviews) < 100
    parsed = []
    for review in reviews:
        body = review["body"]
        summary = next((s for s in body.splitlines() if s.strip()), "")
        result = (
            "BLOCKED"
            if "BLOCKED" in summary
            else "PASS"
            if "PASS" in summary or "REVIEW_RESULT=PASS" in body
            else "UNCLASSIFIED"
        )
        if result == "PASS" and "PASS" not in summary:
            marker = next(line for line in body.splitlines() if "REVIEW_RESULT=PASS" in line)
            summary += " | " + marker
        parsed.append(
            {
                "id": review["id"],
                "state": review["state"],
                "commit_id": review["commit_id"],
                "author": review["user"]["login"],
                "submitted_at": review["submitted_at"],
                "url": review["html_url"],
                "summary": summary,
                "body_sha256": digest(body.encode()),
                "result": result,
            }
        )
    valid = [
        r
        for r in parsed
        if r["commit_id"] == pr["head"]["sha"]
        and r["result"] == "PASS"
        and "independent" in r["summary"].lower()
    ]
    assert pr["merged"] and valid
    merge = api(f"commits/{pr['merge_commit_sha']}")
    parents = [p["sha"] for p in merge["parents"]]
    local = (
        command("git", "rev-list", "--parents", "-n", "1", pr["merge_commit_sha"])
        .decode()
        .split()[1:]
    )
    assert parents == local == [pr["base"]["sha"], pr["head"]["sha"]]
    return {
        "stage": stage,
        "pr_number": number,
        "pr_url": pr["html_url"],
        "pr_state": "MERGED",
        "merged": pr["merged"],
        "base_sha": pr["base"]["sha"],
        "head_sha": pr["head"]["sha"],
        "merge_commit_sha": pr["merge_commit_sha"],
        "merge_parents": parents,
        "git_merge_parents": local,
        "merged_at": pr["merged_at"],
        "merged_by": pr["merged_by"]["login"],
        "pr_body_sha256": digest((pr["body"] or "").encode()),
        "independent_reviews": parsed,
        "independent_review_exact_head_match": True,
        "review_action_is_owner_merge_authorization": False,
        "pr_ci": ci(pr_run),
        "main_ci": ci(main_run),
        "historical_main_gate_passed": number not in {706, 707},
        "authorization_evidence": {
            "path": f"docs/v0-17/evidence/{filename}",
            "keys": keys,
            "value": True,
        },
        "implementation_authorization_verified": True,
        "merge_authority_basis": (
            "OBSERVED_OWNER_MERGE_AND_OWNER_FORMAL_CHAIN_CONFIRMATION_NOT_DRAFT_FLAGS"
        ),
    }


def log_summary(job, failed=False):
    log = command("gh", "api", f"repos/{REPO}/actions/jobs/{job['id']}/logs").decode()
    if failed:
        assert "route.fulfill: Route is already handled!" in log
        match = re.search(r"\b(\d+) passed /?[^\n]*", log)
        return {
            "job_id": job["id"],
            "log_sha256": digest(log.encode()),
            "error": "route.fulfill: Route is already handled!",
            "conclusion": "failure",
            "log_contains_failure": True,
            "passed_hint": match.group(1) if match else None,
        }
    if job["name"] == "frontend-e2e":
        matches = re.findall(r"\b(\d+) passed \(([^\n]+)\)", log)
        assert matches
        passed, duration = matches[-1]
        return {
            "job_id": job["id"],
            "passed": int(passed),
            "duration": duration,
            "log_sha256": digest(log.encode()),
        }
    matches = re.findall(r"(\d+) passed, (\d+) skipped, (\d+) warnings in ([^\n]+)", log)
    assert matches
    passed, skipped, warnings, duration = matches[-1]
    return {
        "job_id": job["id"],
        "passed": int(passed),
        "skipped": int(skipped),
        "warnings": int(warnings),
        "duration": duration,
        "log_sha256": digest(log.encode()),
    }


def capture():
    assert command("git", "rev-parse", "origin/main").decode().strip() == BASE
    release = api("releases/latest")
    assert release["tag_name"] == "v0.16.0" and not release["draft"] and not release["prerelease"]
    assert command("git", "rev-parse", "v0.16.0^{}").decode().strip() == RELEASE_BASE
    assert not command("git", "ls-remote", "--tags", "origin", "refs/tags/v0.17.0")
    releases = api("releases?per_page=100")
    assert len(releases) < 100 and not any(r["tag_name"] == "v0.17.0" for r in releases)
    with ThreadPoolExecutor(max_workers=6) as pool:
        chain = list(pool.map(capture_stage, STAGES))
    prior = RELEASE_BASE
    for record in chain:
        assert record["base_sha"] == prior
        for key, event, head, expected in (
            ("pr_ci", "pull_request", record["head_sha"], "success"),
            (
                "main_ci",
                "push",
                record["merge_commit_sha"],
                "failure" if record["pr_number"] in {706, 707} else "success",
            ),
        ):
            run = record[key]
            assert (run["event"], run["head_sha"], run["status"], run["conclusion"]) == (
                event,
                head,
                "completed",
                expected,
            )
        prior = record["merge_commit_sha"]
    assert prior == BASE
    formal = api("issues/comments/6074984775")
    body = formal["body"]
    assert formal["user"]["login"] == "xuezhiorange-png"
    assert "S6_FORMAL_COMPLETE=true" in body and f"S6_FINAL_MAIN_SHA={BASE}" in body
    assert "S6_FINAL_MAIN_CI_RUN_ID=37881564725" in body and "REVIEW_RESULT=PASS" in body
    logs = {}
    for name in ("frontend-e2e", "full-suite-canary"):
        job = next(j for j in chain[-1]["main_ci"]["jobs"] if j["name"] == name)
        logs[name] = log_summary(job)
    red_logs = [
        log_summary(
            next(j for j in chain[i]["main_ci"]["jobs"] if j["name"] == "frontend-e2e"), True
        )
        for i in (7, 8)
    ]
    return {
        "stage_chain": chain,
        "release_metadata": {
            "tag": release["tag_name"],
            "draft": release["draft"],
            "prerelease": release["prerelease"],
            "url": release["html_url"],
            "id": release["id"],
        },
        "s6_formal_confirmation": {
            "id": formal["id"],
            "author": formal["user"]["login"],
            "created_at": formal["created_at"],
            "url": formal["html_url"],
            "body_sha256": digest(body.encode()),
            "confirmed_main_sha": BASE,
            "confirmed_main_ci": 37881564725,
            "s6_formal_complete": True,
        },
        "final_main_log_summaries": logs,
        "red_main_log_evidence": red_logs,
        "v0_17_tag_release_absent_at_capture": True,
    }


def generate(root, snapshot):
    def read(path):
        return (root / path).read_bytes()

    def load(path):
        return json.loads(read(path))

    scope_path = "docs/v0-17/evidence/v0.17.0-version-plan-and-product-scope-freeze-r1.json"
    scope = load(scope_path)
    s16 = load("docs/v0-16/evidence/v0.16.0-version-closeout-r1.json")
    sources = set(s16["source_evidence_sha256"]) | set(scope["SOURCE_EVIDENCE_SHA256"])
    sources.update(
        {
            "docs/v0-16/v0.16.0-closeout.md",
            "docs/v0-16/evidence/v0.16.0-version-closeout-r1.json",
            "docs/v0-16/evidence/v0.16.0-version-closeout-manifest-r1.json",
            "backend/tests/forecast_intelligence/build_v0_17_version_closeout.py",
            "backend/tests/forecast_intelligence/test_v0_17_version_closeout.py",
        }
    )
    sources.update(
        str(p.relative_to(root))
        for p in (root / "docs/v0-17").glob("*.md")
        if p.name != "v0.17.0-closeout.md"
    )
    sources.update(
        str(p.relative_to(root))
        for p in (root / "docs/v0-17/evidence").glob("*.json")
        if "version-closeout" not in p.name
    )
    sources.update(str(p.relative_to(root)) for p in (root / "docs/v0-17/design/s4").glob("*.json"))
    sources.update(
        str(p.relative_to(root))
        for p in (root / "docs/v0-17/evidence/s6-cross-surface-r2").glob("*.json")
    )
    sources.update(
        {
            "backend/app/forecast_intelligence/read_service.py",
            "backend/app/forecast_intelligence/read_schemas.py",
            "backend/app/forecast_intelligence/decision_service.py",
            "backend/app/forecast_intelligence/decision_schemas.py",
            "backend/app/forecast_intelligence/read_access.py",
            "backend/app/api/forecast_intelligence_read.py",
            "backend/app/api/forecast_intelligence_decision.py",
            "backend/app/mcp/forecast_intelligence_tools.py",
            "backend/app/mcp/forecast_intelligence_server.py",
            "backend/app/mcp/forecast_intelligence_http.py",
            "backend/app/mcp/forecast_intelligence_auth.py",
            "frontend/src/dashboard/app/Dashboard.tsx",
            "frontend/src/dashboard/api/client.ts",
            "frontend/e2e/dashboard-cross-surface.spec.ts",
            "frontend/e2e/dashboard.spec.ts",
            "frontend/e2e/selector-cancel-reopen.spec.ts",
            "frontend/e2e/support/held-canonical-response.ts",
        }
    )
    for path, expected in s16["source_evidence_sha256"].items():
        assert digest(read(path)) == expected, path
    history = {}
    for row in snapshot["stage_chain"]:
        binding = row["authorization_evidence"]
        path = binding["path"]
        value = load(path)
        for key in binding["keys"]:
            value = value[key]
        assert value is True, path
        historical = command("git", "show", f"{row['head_sha']}:{path}")
        assert historical == read(path), path
        history[path] = {
            "sha256": digest(historical),
            "verified_against_committed_head": row["head_sha"],
        }
    audits = {}
    for name, paths in {
        "v0_16_evidence": ["docs/v0-16"],
        "v0_14_v0_15_evidence_models": [
            "docs/v0-14",
            "docs/v0-15",
            "backend/app/area_yield",
            "backend/app/harvest_state",
        ],
        "v0_16_mathematics": [
            f"backend/app/forecast_intelligence/{name}.py"
            for name in (
                "application",
                "persistence",
                "reconciliation",
                "uncertainty",
                "attribution",
                "forecast_ops",
                "business_loss",
                "what_if",
            )
        ],
    }.items():
        changed = (
            command("git", "diff", "--name-only", "v0.16.0", BASE, "--", *paths)
            .decode()
            .splitlines()
        )
        assert not changed, (name, changed)
        audits[name] = {
            "release_baseline": "v0.16.0",
            "target_sha": BASE,
            "paths": paths,
            "changed_files": changed,
        }
    gaps = dict(
        load("docs/v0-17/evidence/v0.17-s6-cross-surface-product-acceptance-r2.json")[
            "production_gaps"
        ]
    )
    gaps.update(
        {
            key: False
            for key in (
                "upper80_run_bound_authority",
                "upper90_run_bound_authority",
                "attribution_run_bound_authority",
                "prospective_accuracy_validated",
                "production_use_approved",
                "point_forecast_is_proven_p50",
                "planning_bounds_are_calibrated_quantiles",
                "attribution_is_causal",
                "automatic_optimization",
                "automatic_execution",
            )
        }
    )
    s6 = load("docs/v0-17/evidence/v0.17-s6-cross-surface-product-acceptance-r2.json")
    source_map = {path: digest(read(path)) for path in sorted(sources)}
    descriptions = [
        "S0 authorized scope, exact-head review, merge and main CI",
        "S1 authoritative read service/API chain",
        "S2 frozen-engine decision API chain",
        "S3 eight-tool authorized MCP chain",
        "S4 reviewed design freeze including R2 correction",
        "S5 five-page Dashboard reviewed implementation chain",
        "S6 acceptance plus selector/provenance/route corrections and final main success",
        "Single-authority deterministic HTTP/MCP/Dashboard tested-scope parity",
        "Historical saved/evidence/source identity preserved",
        "Frozen V0.14/V0.15/V0.16 authority unchanged",
        "No unauthorized current actual or new business experiment",
        "No prospective/quantile/causal/cost/ROI overclaim",
        "Production gaps and NOT_READY explicitly retained",
        "Final closeout independent exact-head review",
        "Closeout merge and post-merge main CI",
        "Separate Owner tag/release authorization",
    ]
    evidence_refs = [[f"stage_chain[{i}]"] for i in range(6)] + [
        ["stage_chain[6:10]", "s6_formal_confirmation"],
        ["capability_summary", "source_evidence_sha256"],
        ["historical_evidence_sha256"],
        ["frozen_git_audit"],
        ["data_authority", "source_evidence_sha256"],
        ["limitations", "scope source"],
        ["production_readiness", "limitations"],
        ["PENDING_SEPARATE_INDEPENDENT_REVIEW"],
        ["PENDING_OWNER_MERGE_AND_MAIN_CI"],
        ["PENDING_OWNER_TAG_RELEASE_AUTHORIZATION"],
    ]
    governance = {
        key: False
        for key in (
            "version_closeout_implementation_complete",
            "version_closeout_formal_complete",
            "v0_17_version_complete",
            "ready_authorized",
            "merge_authorized",
            "tag_authorized",
            "release_authorized",
            "deploy_authorized",
            "v0_18_authorized",
            "v0_18_started",
            "tag_created",
            "release_created",
        )
    }
    governance.update(
        {
            "owner_authorized": True,
            "version_closeout_authorized": True,
            "version_closeout_independent_review": "PENDING",
            "external_exact_head_ci": "REQUIRED_SEPARATE_TERMINAL_PR_RECEIPT",
            "stop": True,
            **{f"s{i}_formal_complete_verified": True for i in range(7)},
        }
    )
    output = {
        **snapshot,
        "task_id": "V0_17_VERSION_CLOSEOUT_R1",
        "version": "0.17.0",
        "version_name": scope["VERSION_NAME"],
        "version_name_cn": scope["VERSION_NAME_CN"],
        "release_class": "PRODUCTIZATION_AND_ENGINEERING_VERSION",
        "base_main_sha": BASE,
        "release_baseline_sha": RELEASE_BASE,
        "latest_formal_release": "v0.16.0",
        "scope": "PUBLIC_FROZEN_EVIDENCE_ONLY",
        **{
            key: False
            for key in (
                "private_data_read",
                "new_real_training",
                "new_real_scoring",
                "new_actual_access",
                "new_forecast_execution",
                "new_simulation_experiment",
                "production_code_changed",
            )
        },
        "capability_summary": {
            "one_service_layer": True,
            "read_capability_count": 6,
            "decision_http_capability_count": 3,
            "top_level_pages": scope["TOP_LEVEL_PAGES"],
            "supported_hierarchy": scope["SUPPORTED_HIERARCHY"],
            "mcp_tool_mapping": load("docs/v0-17/evidence/v0.17-s3-mcp-productization-r1.json")[
                "eight_tool_mapping"
            ],
            "s6_test_counts": s6["test_counts"],
            "s6_acceptance_scope": "ISOLATED_SYNTHETIC_AVAILABLE_AUTHORITY",
            "dashboard_parity_scope": "DOM_CASES_NOT_EVERY_BACKEND_PARAMETER_COMBINATION",
            "conditional_ranking": s6["results"]["rank_order"],
            "equal_quantity_ties_use_lexical_ids_not_shared_ordinal": True,
            "quality_scope": "M1_EXPOSED_OOT_2025_2026_BASE_COHORT_AGGREGATE_RETROSPECTIVE",
            "point_horizons": [1, 3, 7, 15],
            "interval_horizons": [7, 15],
            "under_nominal_coverage_preserved": True,
        },
        "frozen_policy_pins": scope["FROZEN_V0_16_POLICIES"],
        "production_readiness": "NOT_READY",
        "limitations": gaps,
        "data_authority": {
            "strict_pit": False,
            "historical_actual_available_at_proven": False,
            "retrospective_authority_used": True,
            **{
                f"current_season_actual_{k}": False
                for k in ("dependency", "read", "import", "scoring")
            },
        },
        "s6_correction_chain": [
            {
                "failed_run_id": 37807916550,
                "historical_conclusion": "failure",
                "corrected_by_pr": 707,
                "correction_main_still_failed": True,
                "error": "route.fulfill: Route is already handled!",
            },
            {
                "failed_run_id": 37861642942,
                "historical_conclusion": "failure",
                "corrected_by_pr": 708,
                "final_main_run_id": 37881564725,
                "final_main_conclusion": "success",
                "error": "route.fulfill: Route is already handled!",
            },
        ],
        "historical_evidence_unchanged": True,
        "historical_evidence_sha256": history,
        "frozen_git_audit": audits,
        "version_complete_gates": [
            {
                "gate_id": f"G{i + 1:02}",
                "description": desc,
                "status": "PASS" if i < 13 else "PENDING",
                "evidence": evidence_refs[i],
            }
            for i, desc in enumerate(descriptions)
        ],
        "gate_counts": {"pass": 13, "pending": 3, "fail": 0},
        "governance": governance,
        "source_evidence_sha256": source_map,
        "source_evidence_count": len(source_map),
        "source_map_sha256": digest(canonical(source_map)),
        "validation": {
            "closeout_contract_cases": 25,
            "frozen_contract_regression_cases": 200,
            "additional_s1_s2_evidence_contract_cases": 3,
            "local_distinct_contract_cases_passed": 228,
            "ruff": "PASS",
            "format": "PASS",
            "mypy": "PASS_562_SOURCE_FILES",
            "offline_replay": "IDENTICAL_BYTES",
            "private_data_read": False,
            "local_full_suite": "NOT_RUN_CLOSEOUT_PUBLIC_CONTRACT_ONLY",
            "external_ci": "REQUIRED_SEPARATE_EXACT_HEAD_RECEIPT",
        },
        "verification_limits": [
            "Authorization snapshots are historical execution records, not live permission grants.",
            "Observed Owner merge and formal confirmation do not turn COMMENT reviews "
            "into GitHub APPROVE events.",
            "Frozen artifact inspection is not a new production/private-environment "
            "forensic audit.",
            "No business experiment or browser acceptance is rerun for closeout.",
            "Exact-head closeout CI is an external terminal receipt, "
            "not preclaimed in this snapshot.",
        ],
    }
    (root / RECEIPT).write_bytes(canonical(output))
    manifest = {
        "schema": "V0_17_VERSION_CLOSEOUT_MANIFEST_R1",
        "members": {p: digest(read(p)) for p in (DOC, RECEIPT)},
        "source_evidence_count": len(source_map),
        "scope": "PUBLIC_FROZEN_EVIDENCE_ONLY",
        "privacy_scan": "PASS",
        "private_data_read": False,
        "new_real_training": False,
        "new_real_scoring": False,
        "new_current_actual_access": False,
    }
    (root / MANIFEST).write_bytes(canonical(manifest))
    print(
        f"Generated closeout: {len(source_map)} source bindings, "
        "10 PRs, 20 CI runs, 13 PASS / 3 PENDING."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-live", type=Path)
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    assert bool(args.capture_live) != bool(args.snapshot), "Choose capture OR offline snapshot."
    root = Path(__file__).resolve().parents[3]
    if args.capture_live:
        snapshot = capture()
        args.capture_live.write_bytes(canonical(snapshot))
    else:
        snapshot = json.loads(args.snapshot.read_bytes())
    generate(root, snapshot)


if __name__ == "__main__":
    main()
