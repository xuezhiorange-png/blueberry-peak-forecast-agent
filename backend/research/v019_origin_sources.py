"""Exact frozen-source joins and prior-only feature projection for S6.

The materializer DOES read the full historical source. Its output contains only
origin-specific past aggregates, not target weights; no never-exposed claim.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.research import v019_accuracy_study as study
from backend.research import v019_origin_features as features
from backend.research import v019_owner_replay as owner
from backend.research import v019_owner_scope_adapter as scope
from backend.research import v019_real_training as training
from backend.research import v019_stability_cli as previous
from backend.research.v019_synthetic_validation import digest

TRACE_PINS = {
    "training-manifest.json": "2cbaec57b51feb8814f1748b2ebf76c7430918b352ddddbb5665e49f91b40e74",
    "input-manifest.json": "c9f41495cc45c80b45ccfc4d51e472dbbc6e39a689ae7d4d8991be5b5c5c833e",
}
# Measured canonical member bytes from the individually pinned S4 prediction file.
# Not recalculated from a new working tree, nor inferred from candidate counts.
MEMBER_SHA256 = {
    "A": "322d9a4105e76c9ee81a36a7c16e3e3fad2df503800ace5f881d9345303d760f",
    "B": "c9619d458234198a409abc818707dfef1ae776b03fe77878060c0b0fbcb34e83",
}


def validate_members(members: dict[str, Any]) -> None:
    if set(members) != set(MEMBER_SHA256) or any(
        digest(members[e]) != h for e, h in MEMBER_SHA256.items()
    ):
        raise ValueError("EXACT_FROZEN_C0_MEMBER_PAYLOAD_MISMATCH")


def csv_rows(root: Path, name: str) -> list[dict[str, str]]:
    key = next(k for k in training.PINS if k.endswith("/" + name))
    rr = list(
        csv.DictReader(
            io.StringIO(owner.read_bytes(root / key, training.PINS[key]).decode("utf-8-sig"))
        )
    )
    if any(r["season"] not in features.SEASONS for r in rr):
        raise ValueError("UNAUTHORIZED_SEASON_ENVELOPE")
    return rr


def bridge_prior(
    ledger: list[dict[str, str]],
    overlay: list[dict[str, str]],
    identity: list[dict[str, str]],
    meta: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reuse old zero/observed authority only when exact member identities agree."""
    current: dict[str, list[str]] = defaultdict(list)
    old: dict[str, list[str]] = defaultdict(list)
    for r in meta["mapping"]:
        if r["research_base_id"]:
            current[r["research_base_id"]].append(r["source_identity_sha256"])
    for r in identity:
        if r["season"] == "2025-2026" and r["mapping_status"] in {
            "EXACT",
            "AUTHORIZED_ALIAS",
            "BUSINESS_CONFIRMED_MAPPING",
        }:
            old[r["canonical_base_id"]].append(r["source_identity_sha256"])

    def idx(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], dict[str, str]]:
        out = {}
        for r in rows:
            k = r["base_id"], r["season"], r["date"]
            if k in out:
                raise ValueError("DUPLICATE_AUTHORITY_DAY")
            out[k] = r
        return out

    ld, ov = idx(ledger), idx(overlay)
    history = []
    audit: dict[str, Any] = {}
    for bid, members in sorted(current.items()):
        same = sorted(members) == sorted(old[bid])
        audit[bid] = {
            "exact_members_equal": same,
            "current_members_sha256": digest(sorted(members)),
            "historical_members_sha256": digest(sorted(old[bid])),
            "accepted_prior_days": 0,
            "rejected_prior_days": 0,
        }
        for i in range(14):
            day = str(date(2025, 7, 22) + timedelta(days=i))
            key = bid, "2025-2026", day
            r, z = ld.get(key), ov.get(key)
            valid = same and r is not None and z is not None
            if valid:
                assert r is not None and z is not None
                valid = (
                    r["source_sha256"] == scope.SOURCE_SHA256
                    and z["authority_eligible_daily"] == "true"
                    and z["identity_unresolved_conflict"] == "false"
                    and z["source_coverage_status"] == "VERIFIED_SEASON_SOURCE_HASH"
                    and int(z["member_expected_count"]) == len(members)
                    and z["new_completeness_status"]
                    in {"AUTHORIZED_ZERO", "COMPLETE_MAPPED_MEMBERS"}
                )
            kg, state = None, "UNKNOWN"
            if valid:
                assert r is not None and z is not None
                value = Decimal(z["new_quantity_kg"])
                inherited_zero = (
                    z.get("resolution_reason") == "UNCHANGED_EXISTING_AUTHORITY"
                    and r["quantity_status"] == "CONFIRMED_ZERO"
                    and r["quantity_completeness_status"] == "AUTHORIZED_ZERO"
                    and r["confirmed_zero_basis"] == "R7B_SOURCE_ZERO_SEMANTICS"
                    and int(r["source_row_count"]) == int(z["source_row_count"]) == 0
                    and Decimal(r["mapped_observed_subtotal_kg"]) == value == 0
                )
                # S6 explicitly retained existing R7B zero authority unchanged.
                # The S4 helper only needed the earlier training seasons; do not
                # confuse that narrow adapter with the frozen S6 zero contract.
                if z["new_quantity_status"] == "CONFIRMED_ZERO" and (
                    training._authorized_zero(r, z, value) or inherited_zero
                ):
                    kg, state = str(value), "CONFIRMED_ZERO"
                elif (
                    z["new_quantity_status"] == "KNOWN_MAPPED_SUBTOTAL"
                    and value == Decimal(r["mapped_observed_subtotal_kg"])
                    and value.is_finite()
                    and value >= 0
                ):
                    kg, state = str(value), "VALID_OBSERVED"
            audit[bid]["accepted_prior_days" if state != "UNKNOWN" else "rejected_prior_days"] += 1
            history.append(
                {
                    "base_id": bid,
                    "season": "2025-2026",
                    "date": day,
                    "state": state,
                    "kg": kg,
                    "source_sha256": scope.SOURCE_SHA256,
                    "authority_sha256": digest({"ledger": r, "overlay": z, "members_equal": same}),
                    "reason": None
                    if state != "UNKNOWN"
                    else "HISTORICAL_MEMBER_AUTHORITY_NOT_TRANSFERABLE",
                }
            )
    return history, audit


def load(root: Path) -> dict[str, Any]:
    bundle = training.load_training(root)
    old_training, _, old = previous.load_old(root)
    if bundle["admission"] != old_training["payload"]["admission"]:
        raise ValueError("OLD_TRAINING_ADMISSION_CHANGED")
    raw = owner.read_bytes(
        root / "v0-19-s3-owner-controlled-replay-r1-CEYrwE/a/phase-a.json",
        study.S3_PINS["a/phase-a.json"],
    )
    s3 = json.loads(raw)
    if s3["sha256"] != old["payload"]["s3_a_sha256"]:
        raise ValueError("S3_SOURCE_LINK")
    content = s3["payload"]["content"]
    meta = json.loads(content["input_snapshots_utf8"]["metadata"])
    if meta["source_sha256"] != scope.SOURCE_SHA256 or meta["scope_version"] != scope.SCOPE_VERSION:
        raise ValueError("OWNER_SCOPE_SOURCE")
    label_raw = owner.read_bytes(
        root / previous.S4_RUN / "b/comparison.json", previous.PINS["b/comparison.json"]
    )
    daily = json.loads(label_raw)["actual_daily"]
    authorities = {(r["base_id"], r["date"]): r for r in meta["days"]}
    if {(r["base_id"], r["date"]) for r in daily} != set(authorities) or len(daily) != len(
        authorities
    ):
        raise ValueError("SOURCE002_CALENDAR")
    history = []
    for r in bundle["admission"]["daily"]:
        history.append(
            {
                "base_id": r["base_id"],
                "season": r["season"],
                "date": r["date"],
                "kg": r["kg"],
                "state": "CONFIRMED_ZERO" if r["status"] == "CONFIRMED_ZERO" else "VALID_OBSERVED",
                "source_sha256": r["raw_source_sha256"],
                "authority_sha256": r["row_sha256"],
            }
        )
    for r in daily:
        authority = authorities[r["base_id"], r["date"]]
        if authority["authority_eligible_daily"] != "true" or authority[
            "new_completeness_status"
        ] not in {"AUTHORIZED_ZERO", "COMPLETE_MAPPED_MEMBERS"}:
            raise ValueError("SOURCE002_DAILY_AUTHORITY")
        if authority["new_quantity_status"] == "CONFIRMED_ZERO" and Decimal(r["kg"]) != 0:
            raise ValueError("ZERO_AUTHORITY_VALUE_CONFLICT")
        history.append(
            {
                "base_id": r["base_id"],
                "season": "2025-2026",
                "date": r["date"],
                "kg": r["kg"],
                "state": "CONFIRMED_ZERO"
                if authority["new_quantity_status"] == "CONFIRMED_ZERO"
                else "VALID_OBSERVED",
                "source_sha256": scope.SOURCE_SHA256,
                "authority_sha256": digest(authority),
            }
        )
    early, bridge = bridge_prior(
        csv_rows(root, "canonical-base-daily-ledger-r1.csv"),
        csv_rows(root, "canonical-daily-harvest-zero-semantics-overlay-r1.csv"),
        csv_rows(root, "cross-season-base-identity-authority-r1.csv"),
        meta,
    )
    history += early
    trace_manifest = json.loads(
        owner.read_bytes(
            root / training.PROFILE_DIR / "artifact-manifest.json",
            training.PINS[training.PROFILE_DIR + "/artifact-manifest.json"],
        )
    )
    trace = {}
    for n, h in TRACE_PINS.items():
        if trace_manifest[n] != h:
            raise ValueError("PROFILE_TRACE_SOURCE")
        trace[n] = json.loads(owner.read_bytes(root / training.PROFILE_DIR / n, h))
    return {
        "bundle": bundle,
        "old_predictions": old["payload"],
        "history": history,
        "bridge": bridge,
        "profile_trace": trace,
        "source_access_audit": {
            "full_historical_sources_read_by_feature_materializer": True,
            "prior_data_never_exposed_claim": False,
            "source002_full_weight_report_read": True,
            "source002_report_sha256": previous.PINS["b/comparison.json"],
            "quantities_selected": {
                "2023-2024": "ADMITTED_15_BASE_SEASONS",
                "2024-2025": "ADMITTED_22_BASE_SEASONS",
                "2025-2026": "OWNER_SCOPE_DAILY_PLUS_EXACT_MEMBER_AUTHORIZED_PRIOR_BRIDGE",
            },
            "current_2026_2027_read": False,
            "historical_available_at": "NOT_PROVEN",
        },
    }


def materialize(source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle = source["bundle"]
    old = source["old_predictions"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in source["history"]:
        grouped[r["base_id"], r["season"]].append(r)
    areas = {
        (r["base_id"], r["season"]): r["area_mu"]
        for r in bundle["admission"]["inventory"]
        if r["status"] == "ADMIT"
    }
    areas.update(
        {
            (r["base_id"], "2025-2026"): str(r["productive_area_mu"])
            for r in bundle["registry"]["bases"]
        }
    )
    requests: dict[tuple[str, str, date], int] = {}
    cutoffs: dict[tuple[str, str, date], str] = {}
    members = {e: ex["members"] for e, ex in old["experiments"].items()}
    validate_members(members)
    for e, mm in members.items():
        season = "2024-2025" if e == "A" else "2025-2026"
        for m in mm:
            origin = date.fromisoformat(m["target_start"]) - timedelta(days=1)
            features.validate_cutoff(origin, m["origin"])
            if m["cutoff"] != m["origin"]:
                raise ValueError("ORIGIN_RESEARCH_SEMANTICS_CHANGED")
            key = m["base_id"], season, origin
            if key in cutoffs and cutoffs[key] != m["cutoff"]:
                raise ValueError("INCONSISTENT_FROZEN_ORIGIN")
            cutoffs[key] = m["cutoff"]
            requests[key] = max(requests.get(key, 0), 7 if m["window"] == "H7_PREFIX" else 15)
    # Fixed complete 15-day training origins, independent of label magnitudes.
    for item in bundle["admission"]["inventory"]:
        if item["status"] != "ADMIT":
            continue
        start, end = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
        for i in range((end - start).days - 15 + 2):
            origin = start + timedelta(days=i - 1)
            key = item["base_id"], item["season"], origin
            requests[key] = max(requests.get(key, 0), 15)
    records = {}
    for (bid, season, origin), days in sorted(requests.items()):
        rr = features.snapshot(
            bid,
            season,
            origin,
            Decimal(areas[bid, season]),
            grouped[bid, season],
            days,
            cutoff=cutoffs.get((bid, season, origin)),
        )
        records[rr["row_key"]] = rr
    if len(records) != len(requests):
        raise ValueError("DUPLICATE_ORIGIN_IDENTITY")
    training_labels = [
        {k: r[k] for k in ("base_id", "season", "date", "kg")} for r in bundle["admission"]["daily"]
    ]
    result = {
        "version": 1,
        "records": records,
        "members": members,
        "registry": bundle["registry"],
        "input_pins": training.PINS,
        "profile_trace_pins": TRACE_PINS,
        "source_access_audit": source["source_access_audit"],
        "prior_bridge": source["bridge"],
        "feature_policy": features.VERSION,
        "calendar_policy": "V015_FROZEN_BOUNDARIES_NO_REBASE",
        "source002_candidate_window_count": len(members["B"]),
        "scope_version": scope.SCOPE_VERSION,
        "research_included_farms": 80,
        "research_excluded_farms": 4,
        "projection_source_pins": {
            **training.PINS,
            **{training.PROFILE_DIR + "/" + n: h for n, h in TRACE_PINS.items()},
            **{
                previous.S4_RUN + "/" + n: h
                for n, h in previous.PINS.items()
                if n not in {"b/report.md", "b/report.html"}
            },
            "v0-19-s3-owner-controlled-replay-r1-CEYrwE/a/phase-a.json": study.S3_PINS[
                "a/phase-a.json"
            ],
        },
        "strict_pit": False,
    }
    counts = Counter((r["season"], r["complete"]) for r in records.values())
    result["coverage_by_season"] = [
        {"season": s, "complete": b, "origin_count": n} for (s, b), n in sorted(counts.items())
    ]
    return result, {
        "daily": training_labels,
        "input_pins": training.PINS,
        "evaluation_2025_2026_labels_included": False,
    }
