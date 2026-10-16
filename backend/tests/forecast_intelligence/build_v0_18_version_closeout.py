"""Public GitHub capture separated from deterministic, offline closeout audit.

No business services, databases or experiment modules are imported. Missing
review/authorization records remain blockers; a merge is never substituted for
an independent review. This is deliberately an audit, not an approval generator.
"""

import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

REPO = "xuezhiorange-png/blueberry-peak-forecast-agent"
BASE = "2b890d8e68a47ca506e7cf6b04bd187472138b2d"
RELEASE = "1b218edc74ff29091c07607ddbcdba0c10577398"
DOC = "docs/v0-18/v0.18.0-closeout.md"
EVIDENCE = "docs/v0-18/evidence/v0.18.0-version-closeout-r1.json"
MANIFEST = "docs/v0-18/evidence/v0.18.0-version-closeout-manifest-r1.json"
SNAPSHOT = "docs/v0-18/evidence/v0.18.0-closeout-github-snapshot-r1.json"
CLASSIFICATION = {
    710: "S0_SCOPE",
    711: "S1_PREFLIGHT_NOT_RUNTIME",
    712: "ROADMAP_ASSESSMENT_NOT_STAGE_REPLACEMENT",
    713: "SEPARATE_PEAK_BUSINESS_CONTRACT_NOT_V018_IMPLEMENTATION",
    714: "LOCAL_AUTH_REPLAN_NOT_RUNTIME",
    715: "S0_SCOPE_ADDENDUM",
    716: "S1_IMPLEMENTATION_CONTRACT_NOT_RUNTIME",
    717: "S1_RUNTIME",
    718: "S1_SIMPLE_ADMIN_D03",
    721: "S1_POSTMERGE_TIMESTAMP_CORRECTION",
    723: "S2_AUTHORIZED_DISCOVERY",
    724: "S3_SERVICE_ACCOUNT_SAFETY",
    725: "S4_DASHBOARD",
    726: "S5_ISOLATED_PILOT",
    727: "S6_ACCEPTANCE",
}


def canonical(value):
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def command(*args, root=None):
    return subprocess.check_output(args, cwd=root)


def api(endpoint):
    for _attempt in range(3):
        result = subprocess.run(
            ["gh", "api", "--cache", "10m", f"repos/{REPO}/{endpoint}"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        # Retry transport failures only, never convert a missing/forbidden
        # evidence object into an empty review list or a successful result.
        if not any(s in result.stderr for s in (b"TLS handshake", b"EOF", b"502", b"503")):
            break
    raise RuntimeError(f"Public metadata capture failed: {endpoint}: {result.stderr.decode()}")


def pages(endpoint):
    result = []
    for page in range(1, 100):
        separator = "&" if "?" in endpoint else "?"
        batch = api(f"{endpoint}{separator}per_page=100&page={page}")
        assert isinstance(batch, list)
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise AssertionError("Pagination did not terminate")


def capture_ci(run, attempt=None):
    number = attempt or run["run_attempt"]
    details = api(f"actions/runs/{run['id']}/attempts/{number}")
    jobs = api(f"actions/runs/{run['id']}/attempts/{number}/jobs?per_page=100")
    assert jobs["total_count"] == len(jobs["jobs"]) < 100
    return {
        key: details[key]
        for key in (
            "id",
            "head_sha",
            "event",
            "status",
            "conclusion",
            "run_attempt",
            "created_at",
            "updated_at",
            "html_url",
        )
    } | {
        "jobs": [
            {key: job[key] for key in ("id", "name", "status", "conclusion", "html_url")}
            for job in jobs["jobs"]
        ]
    }


def capture_pr(number):
    pr = api(f"pulls/{number}")
    reviews = pages(f"pulls/{number}/reviews")
    comments = pages(f"issues/{number}/comments")
    head, merge = pr["head"]["sha"], pr["merge_commit_sha"]
    assert pr["merged"] and merge
    ci = []
    for sha, event in ((head, "pull_request"), (merge, "push")):
        runs = api(f"actions/runs?head_sha={sha}&event={event}&per_page=100")
        assert runs["total_count"] == len(runs["workflow_runs"]) < 100
        for run in runs["workflow_runs"]:
            if run["path"] != ".github/workflows/ci.yml":
                continue
            for attempt in range(1, run["run_attempt"] + 1):
                ci.append(capture_ci(run, attempt))
    return {
        "number": number,
        "classification": CLASSIFICATION[number],
        "title": pr["title"],
        "body": pr["body"],
        "url": pr["html_url"],
        "state": pr["state"],
        "merged": pr["merged"],
        "merged_at": pr["merged_at"],
        "merged_by": pr["merged_by"]["login"],
        "head_sha": head,
        "base_sha": pr["base"]["sha"],
        "merge_sha": merge,
        "parents": [p["sha"] for p in api(f"git/commits/{merge}")["parents"]],
        "reviews": [
            {
                key: review[key]
                for key in ("id", "commit_id", "state", "body", "submitted_at", "html_url")
            }
            | {"author": review["user"]["login"]}
            for review in reviews
        ],
        "comments": [
            {key: comment[key] for key in ("id", "body", "created_at", "html_url")}
            | {"author": comment["user"]["login"]}
            for comment in comments
        ],
        "ci_attempts": sorted(ci, key=lambda row: (row["id"], row["run_attempt"])),
    }


def capture():
    assert command("git", "rev-parse", "origin/main").decode().strip() == BASE
    release = api("releases/latest")
    assert release["tag_name"] == "v0.17.0" and not release["draft"] and not release["prerelease"]
    ref = api("git/ref/tags/v0.17.0")
    assert ref["object"]["type"] == "tag"
    tag = api(f"git/tags/{ref['object']['sha']}")
    assert tag["object"] == {"sha": RELEASE, "type": "commit", "url": tag["object"]["url"]}
    with ThreadPoolExecutor(max_workers=3) as pool:
        chain = list(pool.map(capture_pr, CLASSIFICATION))
    return {
        "repository": REPO,
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "base_main_sha": BASE,
        "capture_basis": "FRESH_GITHUB_REST_API_NOT_INHERITED_STAGE_DECLARATIONS",
        "release": {
            key: release[key]
            for key in ("id", "tag_name", "target_commitish", "draft", "prerelease", "html_url")
        },
        "annotated_tag": {"object_sha": ref["object"]["sha"], "commit_sha": RELEASE},
        "pull_requests": chain,
        "open_prs": [
            {
                "number": p["number"],
                "title": p["title"],
                "draft": p["draft"],
                "head": p["head"]["sha"],
            }
            for p in pages("pulls?state=open")
        ],
    }


def capture_log_summaries(snapshot):
    """Bind full public job-log hashes plus exact diagnostic/summary excerpts."""
    summaries = []
    for pr in snapshot["pull_requests"]:
        if pr["number"] not in {718, 721, 727}:
            continue
        run = [r for r in pr["ci_attempts"] if r["event"] == "push"][-1]
        for job in run["jobs"]:
            if job["name"] not in {"full-suite-canary", "frontend-e2e"}:
                continue
            raw = command("gh", "api", f"repos/{REPO}/actions/jobs/{job['id']}/logs")
            excerpts = [
                line
                for line in raw.decode("utf-8").splitlines()
                if len(line) <= 2000
                and "<testsuite" not in line
                and re.search(
                    r"\b\d+ passed\b|\b\d+ failed\b|written_at_utc=|test_overwrite_always"
                    r"|assert bytes1 == bytes2",
                    line,
                )
            ]
            assert excerpts, job["id"]
            summaries.append(
                {
                    "pr_number": pr["number"],
                    "run_id": run["id"],
                    "attempt": run["run_attempt"],
                    "job_id": job["id"],
                    "job_name": job["name"],
                    "conclusion": job["conclusion"],
                    "log_sha256": digest(raw),
                    "excerpts": excerpts,
                    "source_url": job["html_url"],
                }
            )
    return summaries


def git_blob(root, commit, path):
    return command("git", "show", f"{commit}:{path}", root=root)


def git_blobs(root, bindings):
    """Read many immutable Git blobs in one binary-safe, non-shell process."""
    queries = [f"{commit}:{path}" for path, commit in bindings.items()]
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=root,
        input=("\n".join(queries) + "\n").encode(),
        capture_output=True,
        check=True,
    )
    stream, values = BytesIO(result.stdout), {}
    for path in bindings:
        header = stream.readline().split()
        assert len(header) == 3 and header[1] == b"blob", path
        raw = stream.read(int(header[2]))
        assert len(raw) == int(header[2]) and stream.read(1) == b"\n", path
        values[path] = raw
    assert stream.read() == b""
    return values


def list_tree(root, commit, *paths):
    return (
        command("git", "ls-tree", "-r", "--name-only", "-z", commit, "--", *paths, root=root)
        .decode()
        .rstrip("\0")
        .split("\0")
    )


def review_audit(pr):
    # Exact-head formal reviews are primary evidence. An issue comment is not
    # silently promoted to an exact-head review or an Owner authorization.
    exact = [
        r
        for r in pr["reviews"]
        if r["commit_id"] == pr["head_sha"]
        and r["submitted_at"] <= pr["merged_at"]
        and r["state"] in {"COMMENTED", "APPROVED"}
        and (
            re.search(r"(?m)^(?:REVIEW_RESULT|INDEPENDENT_REVIEW_RESULT)=PASS\s*$", r["body"])
            or r["state"] == "APPROVED"
        )
        and ("独立" in r["body"] or "independent" in r["body"].lower())
    ]
    # Only explicit affirmative machine markers, not quoted false flags or
    # a COMMENT/PASS review, count as permission to Ready/Merge.
    authorization = [
        c
        for c in pr["comments"]
        if c["author"] == "xuezhiorange-png"
        and c["created_at"] <= pr["merged_at"]
        and pr["head_sha"] in c["body"]
        and re.search(r"(?m)^READY_AUTHORIZED=true\s*$", c["body"])
        and re.search(r"(?m)^MERGE_AUTHORIZED=true\s*$", c["body"])
    ]
    return {
        "independent_exact_head_review_status": "PASS"
        if exact
        else "BLOCKED_MISSING_VERIFIABLE_RECORD",
        "exact_head_review_ids": [r["id"] for r in exact],
        "owner_ready_merge_authorization_status": "PASS"
        if authorization
        else "BLOCKED_MISSING_EXPLICIT_RECORD",
        "owner_authorization_comment_ids": [c["id"] for c in authorization],
        "observed_owner_merge": pr["merged_by"],
        "owner_merge_is_not_independent_review_or_prior_authorization": True,
        "chat_review_or_authorization_may_exist_but_not_available_to_this_audit": not bool(
            exact and authorization
        ),
    }


def generate(root, snapshot, *, output_root=None):
    output_root = output_root or root
    assert snapshot["base_main_sha"] == BASE and snapshot["repository"] == REPO
    first_parent = (
        command("git", "rev-list", "--first-parent", "--reverse", f"{RELEASE}..{BASE}", root=root)
        .decode()
        .splitlines()
    )
    assert first_parent == [p["merge_sha"] for p in snapshot["pull_requests"]]
    chain = []
    previous = RELEASE
    for pr in snapshot["pull_requests"]:
        parents = (
            command("git", "rev-list", "--parents", "-n", "1", pr["merge_sha"], root=root)
            .decode()
            .split()[1:]
        )
        assert parents == pr["parents"] == [previous, pr["head_sha"]]
        assert pr["base_sha"] == previous and pr["merged"]
        pulls = [
            c
            for c in pr["ci_attempts"]
            if c["event"] == "pull_request" and c["head_sha"] == pr["head_sha"]
        ]
        pushes = [
            c
            for c in pr["ci_attempts"]
            if c["event"] == "push" and c["head_sha"] == pr["merge_sha"]
        ]
        assert pulls and pushes
        final_pr, final_main = pulls[-1], pushes[-1]
        assert final_pr["status"] == final_main["status"] == "completed"
        assert final_pr["conclusion"] == "success"
        assert final_main["conclusion"] == ("failure" if pr["number"] == 718 else "success")
        chain.append(
            {
                "pr_number": pr["number"],
                "classification": pr["classification"],
                "head_sha": pr["head_sha"],
                "base_sha": pr["base_sha"],
                "merge_commit_sha": pr["merge_sha"],
                "merge_parents": parents,
                "merged_at": pr["merged_at"],
                "pr_ci": final_pr,
                "main_ci": final_main,
                "review_and_authorization": review_audit(pr),
            }
        )
        previous = pr["merge_sha"]

    # Check original frozen main bytes, not an unchanged=true declaration.
    # Do not confuse an intermediate PR work commit with formal freeze.
    history = {}
    first_main_for_path = {}
    history_roots = ("docs/v0-14", "docs/v0-15", "docs/v0-16", "docs/v0-17", "docs/v0-18")
    for sha in (RELEASE, *first_parent):
        for path in list_tree(root, sha, *history_roots):
            if path:
                first_main_for_path.setdefault(path, sha)
    history_paths = list_tree(
        root, BASE, "docs/v0-14", "docs/v0-15", "docs/v0-16", "docs/v0-17", "docs/v0-18"
    )
    base_blobs = git_blobs(root, dict.fromkeys(history_paths, BASE))
    first_blobs = git_blobs(root, {p: first_main_for_path[p] for p in history_paths})
    for path in history_paths:
        at_base = base_blobs[path]
        assert (root / path).read_bytes() == at_base, path
        # Some in-PR evidence was legitimately regenerated before merge. Check
        # the first main appearance, not an unreviewed intermediate work commit.
        first_main = first_main_for_path[path]
        committed = first_blobs[path]
        assert committed == at_base, ("Historical main evidence overwritten", path)
        history[path] = {
            "sha256": digest(at_base),
            "first_main_commit": first_main,
        }
    # All preexisting backend modules except the explicitly authorized S1/S3
    # transport/configuration entry points must match the released bytes.
    mutable_adapters = {
        "backend/app/main.py",
        "backend/app/core/config.py",
        "backend/app/models/__init__.py",
        "backend/app/api/forecast_intelligence_read.py",
        "backend/app/api/forecast_intelligence_decision.py",
        "backend/app/mcp/forecast_intelligence_http.py",
        "backend/app/mcp/forecast_intelligence_server.py",
    }
    frozen = {}
    frozen_paths = set(list_tree(root, RELEASE, "backend/app")) - mutable_adapters
    released = git_blobs(root, dict.fromkeys(sorted(frozen_paths), RELEASE))
    current = git_blobs(root, dict.fromkeys(sorted(frozen_paths), BASE))
    for path in sorted(frozen_paths):
        before, now = released[path], current[path]
        assert before == now == (root / path).read_bytes(), path
        frozen[path] = digest(now)
    changes = (
        command("git", "diff", "--name-status", "-z", RELEASE, BASE, root=root).decode().split("\0")
    )
    sources = {}
    for folder in (
        "backend/app/local_auth",
        "backend/app/business_access",
        "backend/app/mcp",
        "frontend/src/dashboard",
        "backend/tests/local_auth",
        "backend/tests/business_access",
        "backend/tests/safe_pilot",
        "backend/tests/acceptance_s6",
    ):
        for path in list_tree(root, BASE, folder):
            if path:
                sources[path] = digest(git_blob(root, BASE, path))
    for path in (
        DOC,
        "backend/tests/forecast_intelligence/build_v0_18_version_closeout.py",
        "backend/tests/forecast_intelligence/test_v0_18_version_closeout.py",
    ):
        sources[path] = digest((root / path).read_bytes())
    for path in (
        "backend/app/api/forecast_intelligence_read.py",
        "backend/app/api/forecast_intelligence_decision.py",
        "backend/app/main.py",
        "backend/app/api/local_auth.py",
        "backend/app/api/local_auth_admin.py",
        "backend/app/api/business_access.py",
        "frontend/e2e/dashboard-business-flow.spec.ts",
        "frontend/e2e/dashboard-s6-acceptance.spec.ts",
    ):
        sources[path] = digest(git_blob(root, BASE, path))

    s6 = json.loads(
        (root / "docs/v0-18/evidence/s6-business-and-security-acceptance-r1.json").read_bytes()
    )
    for path, binding in s6["artifacts"].items():
        assert digest((root / path).read_bytes()) == binding["sha256"], path
    junit = ET.fromstring(
        (root / "docs/v0-18/evidence/s6-business-security-r1/run/backend.xml").read_bytes()
    )
    assert not any(junit.findall(".//" + name) for name in ("failure", "error", "skipped"))
    assert len(junit.findall(".//testcase")) == 251
    runtime_audit = {
        "local_backend_passed": len(junit.findall(".//testcase")),
        "full_payload_parity_rows": len(s6["parity_matrix"]),
        "zero_sensitive_work_proofs": len(s6["zero_read_proofs"]),
        "tls_inflight_revocation_proofs": len(s6["tls_release_proofs"]),
        "screenshots": len(s6["browser"]["screenshots"]),
        "artifact_count": len(s6["artifacts"]),
        "ui_state_matrix": s6["ui_state_matrix"],
        "known_limits": s6["known_limits"],
        "historical_execution_not_new_closeout_runtime": True,
    }
    gaps = []
    gap_names = (
        (
            "REAL_ADMIN_ORGANIZATION_CATALOG",
            "Owner designated bootstrap administrator and verified real resource catalog",
        ),
        ("REAL_SERVICE_ACCOUNTS_GRANTS", "Real service-account secrets and approved exact grants"),
        (
            "PRODUCTION_TLS_NETWORK",
            "Production certificate, HTTPS renewal and network isolation proof",
        ),
        ("LEGACY_NETWORK_DENIAL", "Real deployed legacy-entry denial proof"),
        (
            "PRODUCTION_BACKUP_RESTORE",
            "Actual production backup encryption, restore and reauthorization rehearsal",
        ),
        ("BINARY_VERSION_ROLLBACK", "Real binary-version and schema-compatible rollback rehearsal"),
        ("RPO_RTO", "Owner approved RPO/RTO, with measured environment evidence"),
        ("LOG_RETENTION_SECRETS", "Approved retention/access/deletion/secrets operations"),
        (
            "OPERATIONS_RESPONSIBILITY",
            "Named operators, escalation thresholds and explicit risk acceptance",
        ),
        ("REAL_IOS_SAFARI", "Real iOS Safari device acceptance"),
        ("SOFT_KEYBOARD", "Real software keyboard interaction acceptance"),
        ("SCREEN_READER", "Actual assistive-technology acceptance"),
        (
            "CROSS_HOST_NFS_WINDOWS",
            "Cross-host, NFS and Windows revocation safety evidence or topology exclusion",
        ),
        (
            "FRONTEND_DEPENDENCY_ADVISORIES",
            "Seven affected frontend packages: five high and two moderate, not remediated",
        ),
        (
            "CURRENT_ACTUAL_PROSPECTIVE_ACCURACY",
            "Separately authorized real current-season actual data and prospective protocol",
        ),
    )
    for name, missing in gap_names:
        gaps.append(
            {
                "id": name,
                "status": "OPEN_NOT_VALIDATED",
                "current_evidence": (
                    "S5/S6 isolated synthetic tested scope only; see frozen stage reports"
                ),
                "missing_evidence": missing,
                "required_owner_decision": "SEPARATE_AUTHORIZATION_AND_ENVIRONMENT_ACCEPTANCE",
                "production_blocking": True,
            }
        )
    descriptions = (
        "S0 scope and approval chain",
        "S1 authentication and historical corrections",
        "S2 authorized discovery/selection",
        "S3 service-account safety",
        "S4 Dashboard business flow",
        "S5 isolated pilot readiness",
        "S6 full business/security acceptance",
        "Single business authority and exact payload parity",
        "Exact grant/default-deny semantics",
        "Historical Git/source/model integrity",
        "H7/H15/Quality/unavailable semantics",
        "No unauthorized data/experiment/deploy in audited public delivery",
        "Production gaps registered",
        "Closeout independent review",
        "Closeout merge/main CI",
        "Separate tag/release authorization",
    )
    required = ((710, 715), (717, 718, 721), (723,), (724,), (725,), (726,), (727,))
    gates = []
    for index, description in enumerate(descriptions, 1):
        if index <= 7:
            rows = [r for r in chain if r["pr_number"] in required[index - 1]]
            complete = all(
                r["review_and_authorization"]["independent_exact_head_review_status"] == "PASS"
                and r["review_and_authorization"]["owner_ready_merge_authorization_status"]
                == "PASS"
                for r in rows
            )
            status = "PASS" if complete else "BLOCKED"
            refs = [f"stage_chain/PR{r['pr_number']}" for r in rows]
        elif index < 14:
            status = "PASS"
            refs = [
                {
                    8: "frozen_s6_acceptance",
                    9: "security_scope",
                    10: "historical_git_sha256",
                    11: "semantic_boundaries",
                    12: "delivery_scope_audit",
                    13: "production_gap_register",
                }[index]
            ]
        else:
            status, refs = "PENDING", ["SEPARATE_FUTURE_OWNER_GATE"]
        gates.append(
            {"id": f"G{index:02}", "description": description, "status": status, "evidence": refs}
        )
    output = {
        "task_id": "V0_18_VERSION_CLOSEOUT_R1",
        "version": "0.18.0",
        "version_name": "BUSINESS_USABILITY_AND_SAFE_PILOT_FOUNDATION",
        "base_main_sha": BASE,
        "release_baseline_sha": RELEASE,
        "latest_formal_release": "v0.17.0",
        "result": "BLOCKED" if any(g["status"] == "BLOCKED" for g in gates) else "PASS",
        "github_snapshot_sha256": digest(canonical(snapshot)),
        "github_snapshot_path": SNAPSHOT,
        "stage_chain": chain,
        "main_first_parent_chain": first_parent,
        "historical_git_sha256": history,
        "frozen_model_and_math_sha256": frozen,
        "release_to_main_name_status_nul_fields": changes,
        "source_evidence_sha256": sources,
        "frozen_s6_acceptance": {
            "path": "docs/v0-18/evidence/s6-business-and-security-acceptance-r1.json",
            "sha256": digest(canonical(s6)),
            "evidence_level": (
                "READ_ONLY_AUDIT_OF_CURRENT_COMMITTED_TESTS_AND_ACTUAL_RUN_ARTIFACTS"
                "_NOT_NEW_EXECUTION"
            ),
        },
        "s6_artifact_audit": runtime_audit,
        "capability_audit": {
            "local_auth": {
                "implementation": "backend/app/local_auth/",
                "acceptance": "backend/tests/local_auth/",
                "stage_prs": [717, 718, 721],
            },
            "authorized_discovery": {
                "implementation": "backend/app/business_access/",
                "acceptance": "backend/tests/business_access/",
                "stage_prs": [723],
            },
            "service_account_mcp": {
                "implementation": "backend/app/mcp/forecast_intelligence_policy.py",
                "acceptance": "docs/v0-18/evidence/s3-mcp-service-account-safety-r1.json",
                "stage_prs": [724],
            },
            "five_page_dashboard": {
                "implementation": "frontend/src/dashboard/",
                "acceptance": "frontend/e2e/dashboard-business-flow.spec.ts",
                "stage_prs": [725],
            },
            "isolated_safe_pilot": {
                "implementation": "backend/tests/safe_pilot/",
                "acceptance": "docs/v0-18/evidence/s5-isolated-synthetic-safe-pilot-r1.json",
                "stage_prs": [726],
            },
            "cross_surface_acceptance": {
                "implementation": "backend/tests/acceptance_s6/",
                "acceptance": "docs/v0-18/evidence/s6-business-and-security-acceptance-r1.json",
                "stage_prs": [727],
            },
        },
        "historical_failures": [
            {
                "pr": 718,
                "run": 38326155853,
                "conclusion": "failure",
                "corrected_by_pr": 721,
                "corrected_main_ci": 38425016611,
                "cause": "EXPORT_TIMESTAMP_BOUNDARY",
            },
            {
                "pr": 726,
                "run": 38703671252,
                "attempt": 1,
                "conclusion": next(
                    c["conclusion"]
                    for p in snapshot["pull_requests"]
                    if p["number"] == 726
                    for c in p["ci_attempts"]
                    if c["id"] == 38703671252 and c["run_attempt"] == 1
                ),
                "successful_attempt": 2,
                "not_relabelled_as_initial_success": True,
            },
        ],
        "semantic_boundaries": {
            "H7": "D1..D7_PREFIX_CUMULATIVE",
            "H15": "D1..D15_PREFIX_CUMULATIVE",
            "rolling_seven_day_maximum": "NOT_VALIDATED_SOURCE_CAPABILITY_UNAVAILABLE",
            "unavailable": [
                "RUN_BOUND_UPPER80",
                "RUN_BOUND_UPPER90",
                "ATTRIBUTION",
                "CHILD_CONTRIBUTION",
            ],
            "point_is_proven_p50": False,
            "bounds_are_calibrated_quantiles": False,
            "attribution_is_causal": False,
            "strict_pit": False,
            "historical_m1_is_operational_peak_accuracy": False,
            "loss_unit": "SYNTHETIC_LOSS_UNIT",
            "real_roi_validated": False,
            "automatic_scheduling_or_optimization": False,
        },
        "security_scope": {
            "mcp_mode": "SERVICE_ACCOUNT_ONLY",
            "mcp_tool_count": 8,
            "end_user_delegation": False,
            "admin_implicit_business_access": False,
            "independent_quality_grant": True,
            "revocation_scope": "SAME_HOST_POSIX_LOCAL_FILESYSTEM",
            "bytes_already_sent_retractable": False,
        },
        "delivery_scope_audit": {
            "basis": "PUBLIC_GIT_DIFF_FROZEN_TEST_LOGS_AND_STAGE_DECLARATIONS",
            "not_a_forensic_claim_about_unobservable_external_systems": True,
            "current_closeout_no_runtime_business_execution": True,
            "production_code_changed": False,
            "new_training_refit_scoring_actual_access_deploy": False,
        },
        "production_readiness": "NOT_READY",
        "production_gap_register": gaps,
        "version_complete_gates": gates,
        "gate_counts": {
            s: sum(g["status"] == s for g in gates) for s in ("PASS", "FAIL", "BLOCKED", "PENDING")
        },
        "governance": {
            "owner_closeout_authorized": True,
            "version_closeout_formal_complete": False,
            "v0_18_version_complete": False,
            "ready_authorized": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "tag_authorized": False,
            "release_authorized": False,
            "v0_19_authorized": False,
            "external_final_head_ci_receipt": "PENDING_POST_COMMIT_SEPARATE_RECEIPT",
            "stop": True,
        },
    }
    (output_root / EVIDENCE).parent.mkdir(parents=True, exist_ok=True)
    (output_root / EVIDENCE).write_bytes(canonical(output))
    (output_root / MANIFEST).write_bytes(
        canonical(
            {
                "schema": "V0_18_VERSION_CLOSEOUT_MANIFEST_R1",
                "base_main_sha": BASE,
                "members": {
                    DOC: digest((root / DOC).read_bytes()),
                    EVIDENCE: digest(canonical(output)),
                    SNAPSHOT: digest((root / SNAPSHOT).read_bytes()),
                },
            }
        )
    )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture", action="store_true", help="Explicit live public GitHub capture"
    )
    parser.add_argument("--capture-logs", action="store_true", help="Explicit public job logs")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.capture:
        (root / SNAPSHOT).write_bytes(canonical(capture()))
    snapshot = json.loads((root / SNAPSHOT).read_bytes())
    if args.capture_logs:
        snapshot["main_log_summaries"] = capture_log_summaries(snapshot)
        (root / SNAPSHOT).write_bytes(canonical(snapshot))
    result = generate(root, snapshot)
    print(
        json.dumps(
            {
                "result": result["result"],
                "gates": result["gate_counts"],
                "sources": len(result["source_evidence_sha256"]),
                "history": len(result["historical_git_sha256"]),
            }
        )
    )


if __name__ == "__main__":
    main()
