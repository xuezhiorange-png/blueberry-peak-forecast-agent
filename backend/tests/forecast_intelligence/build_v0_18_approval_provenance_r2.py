"""Additive, fail-closed approval recovery; never rewrite the frozen R1 receipt.

Offline generation uses captured original-source receipts and immutable Git
objects. A digest proves bytes, not authorship: channel authentication, action
scope, exact head, independence and event ordering are separate predicates.
No application, database, training or deployment module is imported.
"""

import argparse
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from backend.tests.forecast_intelligence.build_v0_18_version_closeout import (
    BASE,
    CLASSIFICATION,
    DOC,
    EVIDENCE,
    MANIFEST,
    RELEASE,
    SNAPSHOT,
    canonical,
    capture,
    command,
    digest,
    git_blob,
    git_blobs,
    pages,
)

START = "63a044b39bb0c7a9a6698b1700628c4ee31a1050"
TASK = "V0_18_CLOSEOUT_APPROVAL_PROVENANCE_RECOVERY_R2"
R2_DOC = "docs/v0-18/v0.18.0-closeout-provenance-recovery-r2.md"
R2_EVIDENCE = "docs/v0-18/evidence/v0.18.0-approval-provenance-r2.json"
SOURCES = "docs/v0-18/evidence/v0.18.0-approval-sources-r2.json"
BUILDER = "backend/tests/forecast_intelligence/build_v0_18_approval_provenance_r2.py"
TEST = "backend/tests/forecast_intelligence/test_v0_18_approval_provenance_r2.py"
R1_FILES = (
    DOC,
    EVIDENCE,
    MANIFEST,
    SNAPSHOT,
    "backend/tests/forecast_intelligence/build_v0_18_version_closeout.py",
    "backend/tests/forecast_intelligence/test_v0_18_version_closeout.py",
)
R2_FILES = (R2_DOC, R2_EVIDENCE, SOURCES, BUILDER, TEST)
S6 = "docs/v0-18/evidence/s6-business-and-security-acceptance-r1.json"
JUNIT = "docs/v0-18/evidence/s6-business-security-r1/run/backend.xml"
PLAYWRIGHT = "docs/v0-18/evidence/s6-business-security-r1/run/browser-results.json"
STAGES = ((710, 715), (717, 718, 721), (723,), (724,), (725,), (726,), (727,))
ACTIONS = ("INDEPENDENT_REVIEW", "OWNER_READY", "OWNER_MERGE")
CHANNELS = {
    "GITHUB_REVIEW",
    "GITHUB_ISSUE_COMMENT",
    "ORIGINAL_CHATGPT_CONVERSATION",
    "VERIFIABLE_CODEX_TRANSCRIPT",
    "OTHER_AUTHENTIC_ORIGINAL_RECORD",
}
STATUSES = {
    "VERIFIED",
    "PARTIAL_EVIDENCE",
    "PENDING_SOURCE_VERIFICATION",
    "NOT_FOUND",
    "CONFLICTING_EVIDENCE",
    "POST_HOC_ATTESTATION",
}


class AuditFailure(ValueError):
    """Missing, conflicting or unverified evidence cannot satisfy a gate."""


def require(condition, reason):
    if not condition:
        raise AuditFailure(reason)


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load(root, path):
    return json.loads((root / path).read_bytes())


def bound(root, path, expected):
    raw = (root / path).read_bytes()
    require(digest(raw) == expected, f"SHA256 mismatch: {path}")
    return raw


def original_r1(root):
    for path in R1_FILES:
        require((root / path).read_bytes() == git_blob(root, START, path), f"R1 changed: {path}")
    return load(root, EVIDENCE)


def event_time(public, action):
    event = "ready_for_review" if action == "OWNER_READY" else "merged"
    times = [e["created_at"] for e in public["timeline"] if e["event"] == event]
    # Multiple Ready transitions need their own approval binding, not an
    # arbitrary last event. Conservatively require the first transition here.
    return min(times) if times else None


def assess(record, source, public):
    """Recompute all booleans; never trust a caller's VERIFIED/PASS label."""
    result = dict(record)
    result.update(
        original_source_verified=False,
        head_binding_verified=False,
        temporal_order_verified=False,
        evidence_status="PENDING_SOURCE_VERIFICATION",
    )
    if source is None:
        result["reason"] = "Original source not available"
        return result
    authentic = (
        record["source_type"] in CHANNELS
        and source.get("channel") == record["source_type"]
        and source.get("record_id") == record["source_record_id"]
        and source.get("locator") == record["source_locator"]
        and source.get("provider_authenticated") is True
        and source.get("forwarded_or_summary") is False
        and digest(canonical(source)) == record["source_integrity_hash"]
    )
    result["original_source_verified"] = authentic
    if not authentic:
        result["reason"] = "Channel, original-source identity or integrity unverified"
        return result
    exact = (
        source.get("pr_number") == record["pr_number"] == public["number"]
        and source.get("head_sha") == record["reviewed_head_sha"] == public["head_sha"]
        and source.get("context_verified") is True
        and source.get("context_precedes_action") is True
    )
    result["head_binding_verified"] = exact
    if source.get("head_sha") is not None and source["head_sha"] != public["head_sha"]:
        result.update(
            evidence_status="CONFLICTING_EVIDENCE",
            reason="Original source targets a different HEAD",
        )
        return result
    action = record["action_type"]
    if action not in ACTIONS:
        result["reason"] = "Not a historical approval action"
        return result
    cutoff = public["merged_at"] if action == "INDEPENDENT_REVIEW" else event_time(public, action)
    source_time = source.get("timestamp")
    ordered = bool(
        cutoff
        and source_time == record["original_timestamp"]
        and timestamp(source_time) < timestamp(cutoff)
    )
    result["temporal_order_verified"] = ordered
    if source_time and timestamp(source_time) >= timestamp(public["merged_at"]):
        result.update(
            evidence_status="POST_HOC_ATTESTATION", reason="Original record is post-merge"
        )
        return result
    scope = source.get("scope", [])
    permitted = action in scope and action in record["authorization_scope"]
    identity = (
        source.get("actor") == record["actor"]
        and source.get("actor_role") == record["actor_role"]
        and source.get("decision") == record["decision"] == "PASS"
        and source.get("withdrawn", False) is False
        and source.get("self_receipt", False) is False
    )
    if action == "INDEPENDENT_REVIEW":
        identity = (
            identity
            and source.get("independent_from_implementer") is True
            and record["independent_from_implementer"] is True
            and source.get("actor_role") == "INDEPENDENT_REVIEWER"
            and source.get("self_receipt") is False
            and source.get("withdrawn") is False
        )
    else:
        identity = identity and source.get("actor_role") == "OWNER"
    if exact and ordered and permitted and identity:
        result.update(
            evidence_status="VERIFIED", reason="Original channel, head, scope and time verified"
        )
    else:
        result.update(
            evidence_status="PARTIAL_EVIDENCE",
            reason="Incomplete exact-head context, prior time, action scope or independent actor",
        )
    return result


def make_record(source, action, captured):
    return {
        "evidence_id": f"{source['channel']}:{source['record_id']}:{action}",
        "source_type": source["channel"],
        "source_locator": source["locator"],
        "source_record_id": source["record_id"],
        "source_integrity_hash": digest(canonical(source)),
        "original_timestamp": source["timestamp"],
        "captured_timestamp": captured,
        "actor": source["actor"],
        "actor_role": source["actor_role"],
        "pr_number": source["pr_number"],
        "reviewed_head_sha": source.get("head_sha"),
        "action_type": action,
        "decision": source["decision"],
        "authorization_scope": source["scope"],
        "independent_from_implementer": source.get("independent_from_implementer", False),
    }


def github_sources(public):
    """Public COMMENTED review is not APPROVED and never an Owner permission."""
    result = []
    unresolved_change_request = any(r["state"] == "CHANGES_REQUESTED" for r in public["reviews"])
    for review in public["reviews"]:
        body = review["body"] or ""
        passed = bool(re.search(r"(?:REVIEW_RESULT|INDEPENDENT_EXACT_HEAD_REVIEW)=PASS\b", body))
        result.append(
            {
                "channel": "GITHUB_REVIEW",
                "record_id": str(review["id"]),
                "locator": review["html_url"],
                "provider_authenticated": True,
                "forwarded_or_summary": False,
                "pr_number": public["number"],
                "head_sha": review["commit_id"],
                "timestamp": review["submitted_at"],
                "actor": review["author"],
                "actor_role": "INDEPENDENT_REVIEWER",
                "scope": ["INDEPENDENT_REVIEW"],
                "decision": "PASS" if passed else "UNRESOLVED",
                "context_verified": review["commit_id"] in body,
                "context_precedes_action": True,
                "independent_from_implementer": (
                    "independent" in body.lower() and "Codex" not in body[:120]
                ),
                "self_receipt": False,
                "withdrawn": (
                    review["state"] not in {"COMMENTED", "APPROVED"} or unresolved_change_request
                ),
                "github_state": review["state"],
                "body_sha256": digest(body.encode()),
                "body": body,
                "independence_basis": (
                    "Explicit independent review record, not PR author account separation"
                ),
            }
        )
    for comment in public["comments"]:
        body = comment["body"] or ""
        scope = [
            action
            for action, literal in (
                ("OWNER_READY", "READY_AUTHORIZED=true"),
                ("OWNER_MERGE", "MERGE_AUTHORIZED=true"),
            )
            if re.search(rf"(?m)^\s*{literal}\s*$", body)
        ]
        if not scope:
            continue
        result.append(
            {
                "channel": "GITHUB_ISSUE_COMMENT",
                "record_id": str(comment["id"]),
                "locator": comment["html_url"],
                "provider_authenticated": True,
                "forwarded_or_summary": False,
                "pr_number": public["number"],
                "head_sha": public["head_sha"] if public["head_sha"] in body else None,
                "timestamp": comment["created_at"],
                "actor": comment["author"],
                "actor_role": "OWNER" if comment["author"] == "xuezhiorange-png" else "UNVERIFIED",
                "scope": scope,
                "decision": "PASS",
                "context_verified": public["head_sha"] in body,
                "context_precedes_action": True,
                "body_sha256": digest(body.encode()),
                "body": body,
            }
        )
    return result


def approval_audit(capture):
    audit, all_records = [], []
    for public in capture["github"]["pull_requests"]:
        public = public | {
            "timeline": capture["github"]["approval_timelines"][str(public["number"])]
        }
        sources = github_sources(public) + [
            s for s in capture["chat_sources"] if s["pr_number"] == public["number"]
        ]
        records = [
            assess(
                make_record(
                    s,
                    a,
                    capture["captured_at_utc"]
                    if s["channel"] == "ORIGINAL_CHATGPT_CONVERSATION"
                    else capture["github"]["captured_at_utc"],
                ),
                s,
                public,
            )
            for s in sources
            for a in s["scope"]
            if a in ACTIONS
        ]
        states = {
            a: "VERIFIED"
            if any(r["action_type"] == a and r["evidence_status"] == "VERIFIED" for r in records)
            else "PARTIAL_EVIDENCE"
            if any(r["action_type"] == a for r in records)
            else "NOT_FOUND"
            for a in ACTIONS
        }
        audit.append(
            {
                "pr_number": public["number"],
                "head_sha": public["head_sha"],
                "classification": CLASSIFICATION[public["number"]],
                "actions": states,
                "evidence_ids": [r["evidence_id"] for r in records],
                "missing_records": [a for a, s in states.items() if s != "VERIFIED"],
                "merge_is_not_prior_permission": True,
            }
        )
        all_records.extend(records)
    return audit, all_records


def s6_materials(root, r1):
    value = json.loads(bound(root, S6, r1["frozen_s6_acceptance"]["sha256"]))
    for path, binding in value["artifacts"].items():
        bound(root, path, binding["sha256"])
    for path, expected in value["source_evidence_sha256"].items():
        bound(root, path, expected)
    executed = load(
        root, "docs/v0-18/evidence/s6-business-security-r1/run/s6-executed-sources.json"
    )
    require(executed["SYNTHETIC"] is True, "Execution source receipt is not synthetic")
    require(len(executed["source_sha256"]) == 10, "Execution source binding incomplete")
    for path, expected in executed["source_sha256"].items():
        bound(root, path, expected)
    junit = ET.fromstring((root / JUNIT).read_bytes())
    require(len(junit.findall(".//testcase")) == 251, "S6 actual JUnit case set missing")
    require(
        not any(junit.findall(".//" + k) for k in ("failure", "error", "skipped")),
        "S6 nonpassing execution",
    )
    return value, junit


def properties(junit, name, include_case=False):
    result = []
    for case in junit.findall(".//testcase"):
        for prop in case.findall(".//property"):
            if prop.get("name") != name:
                continue
            value = json.loads(prop.attrib["value"])
            if include_case:
                value["case"] = case.attrib["name"]
            result.extend(value if isinstance(value, list) else [value])
    return result


def g08(root, r1):
    s6, junit = s6_materials(root, r1)
    rows = properties(junit, "S6_PARITY_MATRIX")
    require(rows == s6["parity_matrix"] and len(rows) == 54, "Actual parity payload/JUnit mismatch")
    tools = {
        "get_forecast_overview",
        "get_forecast_curve",
        "get_hierarchical_forecast",
        "get_forecast_uncertainty",
        "get_forecast_attribution",
        "get_forecast_quality",
        "simulate_capacity",
        "compare_capacity_scenarios",
    }
    require({r["tool"] for r in rows} == tools, "Eight-tool parity incomplete")
    require(
        {r["forecast_identity"]["hierarchy_level"] for r in rows if r["forecast_identity"]}
        == {"BASE", "REGION", "COMPANY"},
        "Hierarchy parity incomplete",
    )
    for row in rows:
        require(row["numeric_hash_semantic_parity"] == "PASS", "Payload parity failed")
        require(re.fullmatch(r"[0-9a-f]{64}", row["projection_hash"]), "Projection hash absent")
        if row["forecast_identity"]:
            require(re.fullmatch(r"[0-9a-f]{64}", row["source_result_hash"]), "Source hash absent")
    repository = properties(junit, "S6_CANONICAL_REPOSITORY_PROOF")
    require(
        len(repository) == 3 and all(p["raw_decimal_and_dates_equal"] for p in repository),
        "Canonical repository proof absent",
    )
    browser = load(root, PLAYWRIGHT)
    require(
        browser["stats"]["expected"] == s6["browser"]["case_count"] == 48,
        "Browser execution mismatch",
    )
    require(
        all(browser["stats"][k] == 0 for k in ("unexpected", "flaky", "skipped")),
        "Browser execution did not pass",
    )
    observations = [p for p in s6["artifacts"] if "/browser-observations/" in p]
    require(len(observations) == 28, "Browser raw observations missing")
    payloads = [load(root, path) for path in observations]
    reads = [p.get("proof", p) for p in payloads if "overview" in p.get("proof", p)]
    decisions = [
        p
        for p in payloads
        if p.get("capability") in {"SIMULATE_CAPACITY", "COMPARE_CAPACITY_SCENARIOS"}
    ]
    require(len(reads) == 18 and len(decisions) == 6, "Raw browser read/decision proof missing")
    require(all(p["SYNTHETIC"] is True for p in reads), "Unlabelled browser read fixture")
    require(all(p["synthetic"] is True for p in decisions), "Unlabelled browser decision fixture")
    require(
        all(p["projection_hash"] and p["source_result_hash"] for p in decisions),
        "Browser decision authority missing",
    )
    require(
        all(
            p["canonical_company_cost"] is False
            and p["real_roi_validated"] is False
            and p["loss_unit"] == "SYNTHETIC_LOSS_UNIT"
            for p in decisions
        ),
        "Raw decision response overstates financial authority",
    )
    code = (root / "backend/tests/acceptance_s6/test_tls_authority.py").read_text()
    require(
        "actual.structured_content == response.json() == expected" in code,
        "Full payload assertion absent",
    )
    browser_code = (root / "frontend/e2e/dashboard-s6-acceptance.spec.ts").read_text()
    require(
        all(
            fragment in browser_code
            for fragment in (
                'await expect(kpi).toHaveAttribute("title", value)',
                "toContainText(row.point_forecast_kg)",
                "expect(actual).toEqual(authority.canonical_and_sdk)",
                "toContainText(actual.engine_result_hash)",
            )
        ),
        "Browser raw-value/DOM or canonical SDK assertion missing",
    )
    return {
        "parity_rows": len(rows),
        "canonical_levels": 3,
        "browser_cases": 48,
        "raw_browser_observations": len(observations),
        "artifacts": len(s6["artifacts"]),
        "evidence_level": "AUDIT_OF_BOUND_ACTUAL_EXECUTION_NOT_NEW_RUNTIME",
    }


def g09(root, r1):
    s6, junit = s6_materials(root, r1)
    zeros = properties(junit, "S6_ZERO_READ_PROOF", include_case=True)
    release = properties(junit, "S6_TLS_RELEASE_PROOF", include_case=True)
    require(
        zeros == s6["zero_read_proofs"] and len(zeros) == 8, "Zero-read proof missing/mismatched"
    )
    for p in zeros:
        require(
            all(
                p[k] == 0
                for k in (
                    "BUSINESS_READ_COUNT",
                    "QUALITY_FILE_READ_COUNT",
                    "SIMULATION_EXECUTION_COUNT",
                )
            ),
            "Unauthorized sensitive work detected",
        )
    require(
        release == s6["tls_release_proofs"] and len(release) == 2, "Actual release proof missing"
    )
    require(
        all(
            p["canonical_read_reached"]
            and p["revocation_committed_before_release"]
            and p["sensitive_bytes_returned"] is False
            for p in release
        ),
        "Revocation release contract failed",
    )
    names = {c.attrib["name"] for c in junit.findall(".//testcase")}
    require(
        "test_s6_observers_detect_actual_allowed_work" in names,
        "Zero-read observer lacks positive control",
    )
    require(
        r1["security_scope"]
        == {
            "mcp_mode": "SERVICE_ACCOUNT_ONLY",
            "mcp_tool_count": 8,
            "end_user_delegation": False,
            "admin_implicit_business_access": False,
            "independent_quality_grant": True,
            "revocation_scope": "SAME_HOST_POSIX_LOCAL_FILESYSTEM",
            "bytes_already_sent_retractable": False,
        },
        "Security scope widened",
    )
    return {
        "zero_work_cases": len(zeros),
        "inflight_tls_release_cases": len(release),
        "scope": r1["security_scope"],
    }


def g10(root, r1):
    historical = r1["historical_git_sha256"]
    require(len(historical) == 888, "Historical source register incomplete")
    old = git_blobs(root, {p: b["first_main_commit"] for p, b in historical.items()})
    for path, binding in historical.items():
        require(digest(old[path]) == binding["sha256"], f"Historical Git source changed: {path}")
        bound(root, path, binding["sha256"])
    models = r1["frozen_model_and_math_sha256"]
    require(len(models) == 557, "Frozen backend/model scope incomplete")
    released = git_blobs(root, dict.fromkeys(models, RELEASE))
    audited = git_blobs(root, dict.fromkeys(models, BASE))
    for path, expected in models.items():
        require(
            digest(released[path]) == digest(audited[path]) == expected,
            f"Frozen math changed: {path}",
        )
    return {
        "historical_files": len(historical),
        "frozen_backend_modules": len(models),
        "fixed_git_commits_not_future_runtime_freeze": True,
    }


def g11(root, r1):
    s6, _ = s6_materials(root, r1)
    semantics = r1["semantic_boundaries"]
    require(
        semantics["H7"] == "D1..D7_PREFIX_CUMULATIVE"
        and semantics["H15"] == "D1..D15_PREFIX_CUMULATIVE",
        "Horizon is not a saved prefix",
    )
    require(
        semantics["rolling_seven_day_maximum"]
        == s6["known_limits"]["rolling_seven_day_maximum_four_surface_metric"]
        == "NOT_VALIDATED_SOURCE_CAPABILITY_UNAVAILABLE",
        "Rolling maximum falsely validated",
    )
    require(
        set(semantics["unavailable"])
        == {"RUN_BOUND_UPPER80", "RUN_BOUND_UPPER90", "ATTRIBUTION", "CHILD_CONTRIBUTION"},
        "Missing unavailable boundary",
    )
    for key in (
        "point_is_proven_p50",
        "bounds_are_calibrated_quantiles",
        "attribution_is_causal",
        "strict_pit",
        "historical_m1_is_operational_peak_accuracy",
        "real_roi_validated",
        "automatic_scheduling_or_optimization",
    ):
        require(semantics[key] is False, f"Unsupported claim: {key}")
    require(semantics["loss_unit"] == "SYNTHETIC_LOSS_UNIT", "Financial authority invented")
    for row in s6["parity_matrix"]:
        if row["tool"] in {"get_forecast_uncertainty", "get_forecast_attribution"}:
            require(row["status"] == "NOT_AVAILABLE", "Unbound authority made ready")
    quality = []
    for path in s6["artifacts"]:
        if "/browser-observations/" in path:
            observation = load(root, path)
            proof = observation.get("proof", observation)
            if isinstance(proof, dict) and "quality" in proof:
                quality.append(proof["quality"])
    require(quality, "Historical Quality raw response missing")
    for response in quality:
        raw = json.dumps(response, sort_keys=True)
        require(
            "V0_15_S5_M1_RIDGE" in raw and "EXPOSED_OOT" in raw and "BASE_COHORT_AGGREGATE" in raw,
            "Quality identity re-labelled",
        )
        require(response["data"]["strict_pit"] is False, "Quality strict PIT overclaim")
        require(
            response["data"]["current_season_actual_available"] is False
            and response["data"]["production_accuracy_validated"] is False
            and response["data"]["prospective_interval_coverage_validated"] is False,
            "Historical Quality falsely promoted to current/prospective accuracy",
        )
    return {
        "semantic_boundaries": semantics,
        "raw_quality_responses": len(quality),
        "known_limits": s6["known_limits"],
    }


def g12(root, r1):
    expected = set(R1_FILES)
    fields = command("git", "diff", "--name-status", BASE, START, root=root).decode().splitlines()
    require({line.split("\t")[1] for line in fields} == expected, "Unexpected R1 delivery files")
    require(all(line.startswith("A\t") for line in fields), "R1 was not additive")
    # A future authorized runtime task must not be frozen by this historical
    # audit. Once merged (including a CI test merge), inspect this delivery's
    # second-parent HEAD, not every later main commit or future worktree.
    delivery = None
    merges = (
        command(
            "git",
            "rev-list",
            "--ancestry-path",
            "--merges",
            "--reverse",
            f"{START}..HEAD",
            root=root,
        )
        .decode()
        .splitlines()
    )
    for merge in merges:
        parents = (
            command("git", "rev-list", "--parents", "-n", "1", merge, root=root).decode().split()
        )
        if len(parents) == 3 and parents[1] == BASE:
            delivery = parents[2]
            break
    args = ("git", "diff", "--name-only", START)
    current = command(*args, *((delivery,) if delivery else ()), root=root).decode().splitlines()
    untracked = (
        []
        if delivery
        else (
            command("git", "ls-files", "--others", "--exclude-standard", root=root)
            .decode()
            .splitlines()
        )
    )
    require(set(current + untracked) <= set(R2_FILES), "R2 exceeds audit-only file allowlist")
    require(
        r1["delivery_scope_audit"]["not_a_forensic_claim_about_unobservable_external_systems"]
        is True,
        "Unobservable absence overclaim",
    )
    require(
        r1["delivery_scope_audit"]["production_code_changed"] is False, "R1 production mutation"
    )
    return {
        "r1_added_files": sorted(expected),
        "r2_allowlist": list(R2_FILES),
        "range_policy": "FIXED_CLOSEOUT_MERGE_SECOND_PARENT_OR_CURRENT_UNMERGED_DELIVERY",
        "scope": "OBSERVABLE_GIT_DELIVERY_AND_BOUND_EXECUTION_ONLY",
        "external_unobservable_actions": "NOT_VALIDATED",
    }


def g13(root, r1):
    s6, _ = s6_materials(root, r1)
    gaps = r1["production_gap_register"]
    required = {
        "REAL_ADMIN_ORGANIZATION_CATALOG",
        "REAL_SERVICE_ACCOUNTS_GRANTS",
        "PRODUCTION_TLS_NETWORK",
        "LEGACY_NETWORK_DENIAL",
        "PRODUCTION_BACKUP_RESTORE",
        "BINARY_VERSION_ROLLBACK",
        "RPO_RTO",
        "LOG_RETENTION_SECRETS",
        "OPERATIONS_RESPONSIBILITY",
        "REAL_IOS_SAFARI",
        "SOFT_KEYBOARD",
        "SCREEN_READER",
        "CROSS_HOST_NFS_WINDOWS",
        "FRONTEND_DEPENDENCY_ADVISORIES",
        "CURRENT_ACTUAL_PROSPECTIVE_ACCURACY",
    }
    require(
        len(gaps) == len(required) and {g["id"] for g in gaps} == required,
        "Production gap omitted/duplicated",
    )
    for gap in gaps:
        require(
            gap["status"] == "OPEN_NOT_VALIDATED" and gap["production_blocking"] is True,
            "Production blocker hidden",
        )
        require(
            all(
                isinstance(gap[k], str) and gap[k].strip()
                for k in ("current_evidence", "missing_evidence", "required_owner_decision")
            ),
            "Risk lacks evidence/decision",
        )
    for key in (
        "real_ios_safari",
        "soft_keyboard",
        "screen_reader",
        "cross_host_nfs_windows_revocation",
        "production_credentials_network_certificates",
    ):
        require(
            s6["known_limits"][key] == "NOT_VALIDATED", f"Unvalidated production gap hidden: {key}"
        )
    security = "docs/v0-18/s5/frontend-dependency-security-review-r1.md"
    raw = bound(root, security, r1["historical_git_sha256"][security]["sha256"])
    require(
        b"high" in raw.lower() and b"moderate" in raw.lower(), "Historical advisory severity absent"
    )
    require(r1["production_readiness"] == "NOT_READY", "Release readiness falsely upgraded")
    return {
        "gap_count": len(gaps),
        "production_readiness": "NOT_READY",
        "risk_register": gaps,
        "advisory_source": security,
        "not_a_new_dependency_audit": True,
    }


VALIDATORS = {f"G{i:02}": v for i, v in enumerate((g08, g09, g10, g11, g12, g13), 8)}


def validate_gate(gate, root, r1):
    try:
        proof = VALIDATORS[gate](root, r1)
        return {"id": gate, "status": "PASS", "validation": proof}
    except (
        AuditFailure,
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        AssertionError,
        ET.ParseError,
    ) as exc:
        return {"id": gate, "status": "BLOCKED", "reason": str(exc) or type(exc).__name__}


def generate(root):
    r1 = original_r1(root)
    capture = load(root, SOURCES)
    require((root / SOURCES).read_bytes() == canonical(capture), "Capture is not canonical")
    public = capture["github"]
    require(
        [p["number"] for p in public["pull_requests"]] == list(CLASSIFICATION),
        "15-PR audit incomplete",
    )
    require(public["base_main_sha"] == BASE, "Capture base mismatch")
    for p, old in zip(public["pull_requests"], load(root, SNAPSHOT)["pull_requests"], strict=True):
        for key in ("head_sha", "base_sha", "merge_sha", "parents", "merged_at", "ci_attempts"):
            require(p[key] == old[key], f"Fresh public chain drift: PR{p['number']} {key}")
    audit, records = approval_audit(capture)
    gates = []
    for index, required in enumerate(STAGES, 1):
        stage = [p for p in audit if p["pr_number"] in required]
        complete = len(stage) == len(required) and all(
            all(v == "VERIFIED" for v in p["actions"].values()) for p in stage
        )
        gates.append(
            {
                "id": f"G{index:02}",
                "status": "PASS" if complete else "BLOCKED",
                "required_prs": list(required),
                "approval_requirements": list(ACTIONS),
            }
        )
    gates.extend(validate_gate(gate, root, r1) for gate in VALIDATORS)
    gates.extend(
        {"id": f"G{i}", "status": "PENDING", "reason": "SEPARATE_FUTURE_OWNER_GATE"}
        for i in (14, 15, 16)
    )
    return {
        "task_id": TASK,
        "base_main_sha": BASE,
        "start_head_sha": START,
        "result": "BLOCKED" if any(g["status"] == "BLOCKED" for g in gates) else "PASS",
        "original_r1_snapshot_preserved": True,
        "original_r1_gate_counts": r1["gate_counts"],
        "historical_pr_count": len(audit),
        "approval_audit": audit,
        "approval_records": records,
        "recovered_record_counts": {
            a: sum(r["action_type"] == a and r["evidence_status"] == "VERIFIED" for r in records)
            for a in ACTIONS
        },
        "chat_source_verification": capture["search_scope"],
        "accepted_channels": sorted(CHANNELS),
        "evidence_statuses": sorted(STATUSES),
        "version_complete_gates": gates,
        "gate_counts": {
            s: sum(g["status"] == s for g in gates) for s in ("PASS", "BLOCKED", "PENDING", "FAIL")
        },
        "source_evidence_sha256": {
            p: digest((root / p).read_bytes()) for p in (*R1_FILES, R2_DOC, SOURCES, BUILDER, TEST)
        },
        "historical_failure_chain": r1["historical_failures"],
        "current_head_ci": "POST_COMMIT_EXTERNAL_EXACT_HEAD_RECEIPT_REQUIRED",
        "production_readiness": "NOT_READY",
        "governance": r1["governance"] | {"owner_provenance_recovery_authorized": True},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture-public",
        action="store_true",
        help="Explicit fresh public API capture; preserve original private-message receipts",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.capture_public:
        sources = load(root, SOURCES)
        public = capture()
        public["approval_timelines"] = {
            str(p["number"]): [
                e
                for e in pages(f"issues/{p['number']}/timeline")
                if e.get("event")
                in {"ready_for_review", "convert_to_draft", "merged", "review_dismissed"}
            ]
            for p in public["pull_requests"]
        }
        sources["github"] = public
        # Original chat capture timestamps are not rewritten by public refresh.
        (root / SOURCES).write_bytes(canonical(sources))
    result = generate(root)
    (root / R2_EVIDENCE).write_bytes(canonical(result))
    print(
        json.dumps(
            {
                "result": result["result"],
                "gates": result["gate_counts"],
                "recovered": result["recovered_record_counts"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
