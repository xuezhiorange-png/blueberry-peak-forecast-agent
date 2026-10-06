"""Deterministic offline closure projection, never a database or model loader.

Access observations must be supplied by the operator; absent access stays absent.
Only the previously committed sanitized audit is consumed. No secrets, actual
sources, production runtime, credentials, raw GRIB or labels are loaded here.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.audit_v0_15_s0_existing_assets import aware, digest, validate_public

STEPS = tuple(range(3, 145, 3)) + tuple(range(150, 361, 6))
FIELDS = tuple((p, s) for p in ("2t", "10u", "10v") for s in STEPS) + tuple(
    (p, s) for p in ("tp", "ssrd") for s in (168, 360)
)
POLICY = {
    "policy_id": "V0_15_S0_PIT_EVIDENCE_TIERS_R1",
    "time_fields": [
        "event_time",
        "effective_time",
        "source_timestamp",
        "created_at",
        "ingested_at",
        "updated_at",
        "available_at",
        "retrieved_at",
    ],
    "tier_a": (
        "Direct immutable revision/acquisition/ingestion evidence; exact payload lineage; "
        "available_at <= cutoff. Event/effective/mtime/current retrieval never suffice."
    ),
    "tier_b": (
        "Real data, frozen conservative result-independent assumption. PIT_STRICT=false. "
        "No assumption rule instantiated by this closure."
    ),
    "tier_c": (
        "Final existence only; contemporaneous availability unknown. Exploratory/proxy only; "
        "forbidden in strict blind PIT benchmark."
    ),
    "unknown_identity": "REVIEW_REQUIRED; no fuzzy mapping or automatic binding",
    "result_based_promotion": False,
    "operational_vault_deployed": False,
    "scope": "Metadata classification, not operational predictor admission or blind vault",
}
GAP_CATEGORIES = (
    "TRUE_DATA_MISSING",
    "ACCESS_BLOCKED",
    "AUTHORITY_UNKNOWN",
    "HISTORICAL_AVAILABLE_AT_UNKNOWN",
    "IDENTITY_UNRESOLVED",
    "NOT_APPLICABLE",
    "OPTIONAL_ENHANCEMENT",
)


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def classify_tier(evidence: dict[str, Any], cutoff: str) -> str:
    boundary = aware(cutoff)
    direct = evidence.get("evidence_kind") in {
        "IMMUTABLE_INGESTION",
        "VERSIONED_REVISION",
        "HISTORICAL_ACQUISITION",
        "APPEND_ONLY_EVENT",
    }
    if (
        direct
        and evidence.get("immutable") is True
        and valid_hash(evidence.get("source_hash"))
        and evidence.get("available_at")
    ):
        if aware(evidence["available_at"]) <= boundary:
            return "PIT_EVIDENCE_TIER_A_STRICT"
        return "PIT_EVIDENCE_TIER_C_RETROSPECTIVE"
    if (
        valid_hash(evidence.get("assumption_policy_hash"))
        and evidence.get("assumption_frozen") is True
        and evidence.get("result_independent") is True
    ):
        return "PIT_EVIDENCE_TIER_B_ASSUMED"
    return "PIT_EVIDENCE_TIER_C_RETROSPECTIVE"


def sanitized_access_receipt(raw: dict[str, Any]) -> dict[str, Any]:
    code = raw.get("http_status")
    return {
        "http_status": code,
        "classification": "ACCESS_BLOCKED" if code in {401, 403} else "REQUIRES_GRIB_VALIDATION",
        "absence_proven": False,
    }


def audit_schema_readonly(connection: Any) -> list[Any]:
    """Metadata only, caller-owned authorized PostgreSQL connection.

    No connection discovery, credentials, quantities, actual records, migration,
    DML or commits. Real semantic/season-scoped audit remains a separate gate.
    This helper is synthetic-tested only in this execution.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN READ ONLY")
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone() != ("on",):
                raise ValueError("DATABASE_READ_ONLY_NOT_ENFORCED")
            cursor.execute(
                "SELECT table_schema, table_name, column_name, data_type "
                "FROM information_schema.columns "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY table_schema, table_name, ordinal_position"
            )
            return list(cursor.fetchall())
    finally:
        connection.rollback()


def verify_weather8(metadata: list[dict[str, Any]]) -> dict[str, Any]:
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    runs = set()
    errors = []
    units = {"2t": "K", "10u": "m s**-1", "10v": "m s**-1", "tp": "m", "ssrd": "J m**-2"}
    param_ids = {"2t": 167, "10u": 165, "10v": 166, "tp": 228, "ssrd": 169}
    for row in metadata:
        key = (row["shortName"], row["endStep"])
        if key not in FIELDS or key in seen:
            errors.append("UNEXPECTED_OR_DUPLICATE_FIELD")
            continue
        seen[key] = row
        runs.add(
            (row.get("dataDate"), row.get("dataTime"), row.get("expver"), row.get("model_cycle"))
        )
        expected_type = "accum" if key[0] in {"tp", "ssrd"} else "instant"
        if row.get("units") != units[key[0]] or row.get("stepType") != expected_type:
            errors.append("UNIT_OR_TEMPORAL_SEMANTICS_MISMATCH")
        if expected_type == "accum" and row.get("startStep") != 0:
            errors.append("ACCUMULATION_ORIGIN_MISMATCH")
        if row.get("paramId") != param_ids[key[0]]:
            errors.append("PARAMETER_ID_MISMATCH")
        if row.get("dataTime") not in {0, 1200}:
            errors.append("INELIGIBLE_CYCLE")
        try:
            issued = datetime.strptime(
                f"{row['dataDate']}{row['dataTime']:04d}", "%Y%m%d%H%M"
            ).replace(tzinfo=UTC)
            valid = issued + timedelta(hours=key[1])
            if (row.get("validityDate"), row.get("validityTime")) != (
                int(valid.strftime("%Y%m%d")),
                int(valid.strftime("%H%M")),
            ):
                errors.append("VALID_TIME_MISMATCH")
        except (KeyError, TypeError, ValueError):
            errors.append("INVALID_RUN_TIMESTAMP")
        if (
            row.get("stream") != "oper"
            or row.get("type") != "fc"
            or row.get("levtype") != "sfc"
            or row.get("class") != "od"
        ):
            errors.append("PRODUCT_IDENTITY_MISMATCH")
        if any(
            row.get(k) in (None, "")
            for k in (
                "dataDate",
                "dataTime",
                "expver",
                "model_cycle",
                "validityDate",
                "validityTime",
                "paramId",
                "resolution",
            )
        ):
            errors.append("PROVENANCE_INCOMPLETE")
    if len(runs) > 1:
        errors.append("MIXED_RUNS")
    missing = sorted(set(FIELDS) - set(seen))
    return {
        "required_field_count": 256,
        "observed_field_count": len(seen),
        "missing_field_count": len(missing),
        "missing_fields": missing,
        "errors": sorted(set(errors)),
        "complete": not missing and not errors,
    }


def reclassify_gap(gap: dict[str, Any]) -> dict[str, Any]:
    field = gap["missing_field"]
    if "available_at" in field:
        category = "HISTORICAL_AVAILABLE_AT_UNKNOWN"
    elif field in {
        "controlled_database_read_only_access",
        "ecmwf_archive_account_entitlement",
        "weather",
    }:
        category = "ACCESS_BLOCKED"
    elif field == "identity":
        category = "IDENTITY_UNRESOLVED"
    elif field in {"management", "variety"}:
        category = "OPTIONAL_ENHANCEMENT"
    else:
        category = "AUTHORITY_UNKNOWN"
    return {
        **gap,
        "closure_category": category,
        "true_company_data_missing_proven": False,
        "new_data_upload_requested": False,
        "classification_scope": "Access/provenance review; company absence not established",
    }


def build_reports(root: Path, observation: dict[str, Any]) -> dict[str, Any]:
    # This execution has no authenticated archive or DB proof. Never promote
    # flags supplied by an operator into an unsupported successful audit.
    if observation.get("ecmwf_auth_available") or observation.get("db_access_available"):
        raise ValueError("LIVE_PROOF_REQUIRED_BEFORE_ACCESS_CLOSURE_PROJECTION")
    if observation.get("protected_runtime_accessed") or observation.get("current_actual_accessed"):
        raise ValueError("PROTECTED_BOUNDARY_BREACH")
    allowed_observation_keys = {
        "ecmwf_auth_available",
        "db_access_available",
        "protected_runtime_accessed",
        "current_actual_accessed",
        "observed_at",
        "discovery_scope",
        "ecmwf_standard_config_present",
        "database_config_file_present",
    }
    if set(observation) - allowed_observation_keys:
        raise ValueError("UNSAFE_ACCESS_OBSERVATION_FIELD")

    def load(name: str) -> Any:
        return json.loads((root / name).read_text())

    area = load("area-authority-coverage-report-r2.json")["base_season_authority"]
    identity = load("identity-conflict-report-r2.json")["identity_rows"]
    gaps = [reclassify_gap(g) for g in load("owner-data-supplement-package-r2.json")]
    matrix = list(csv.DictReader((root / "base-season-coverage-matrix-r2.csv").open()))
    seasons = {r["season_id"] for r in matrix}
    if seasons != {"2023-2024", "2024-2025", "2025-2026"}:
        raise ValueError("FUTURE_OR_UNAUTHORIZED_SEASON")
    area_rows = []
    for r in area:
        if r.get("available_at") is not None or r.get("historical_known_at") is not None:
            raise ValueError("NEW_AVAILABILITY_EVIDENCE_REQUIRES_REVIEW")
        area_rows.append(
            {
                "base_id": r["base_id"],
                "season": r["event_time_scope"],
                "source_row_hash": digest(r),
                "tier": "PIT_EVIDENCE_TIER_C_RETROSPECTIVE",
                "available_at": None,
                "reason": "Confirmed historical authority; availability unknown; DB inaccessible",
            }
        )
    for row in matrix:
        tier = (
            "PIT_EVIDENCE_TIER_C_RETROSPECTIVE"
            if row["entity_kind"] == "CANONICAL_BASE"
            else "UNCLASSIFIED_NO_BOUND_AUTHORITY"
        )
        row.update(
            pit_evidence_tier=tier, closure_db_access="ACCESS_BLOCKED", strict_pit_ready=False
        )
    categories = {k: sum(g["closure_category"] == k for g in gaps) for k in GAP_CATEGORIES}
    reports: dict[str, Any] = {
        "authenticated-ecmwf-historical-retrieval-report": {
            "auth_available": False,
            "authenticated_request_executed": False,
            "retrieval_success": False,
            "classification": "ACCESS_BLOCKED",
            "query_date": "2025-01-15",
            "query_cycle": "00",
            "new_network_request_executed": False,
            "prior_403_is_baseline_not_new_request": True,
            "access_observation": observation,
            "next_action": "Authorize secure credentials; never send secrets in chat/Git",
        },
        "historical-grib-validation-report": {
            "sample_available": False,
            "decode_executed": False,
            "download_success": False,
            "status": "NOT_EXECUTED_ACCESS_BLOCKED",
            "http_200_alone_sufficient": False,
        },
        "weather8-historical-support-report": {
            **verify_weather8([]),
            "window_a": "NOT_ESTABLISHED_ACCESS_BLOCKED",
            "window_b": "NOT_ESTABLISHED_ACCESS_BLOCKED",
            "missing_interpretation": "Not retrieved/validated; not proven absent from archive",
            "ssr_substitution_allowed": False,
            "tigge_grid_substitution_allowed": False,
            "run_policy_frozen": False,
            "run_policy_reason": "Fields/availability unverified; no run selection executed",
        },
        "historical-database-readonly-audit-report": {
            "read_access": False,
            "read_only_enforced_on_real_connection": False,
            "audit_completed": False,
            "records_queried": False,
            "status": "ACCESS_BLOCKED",
            "data_absence_claimed": False,
            "schema_names_not_data_semantics": True,
            "future_actual_read": False,
            "connection_requirement": "Authorized read-only connection/export; no service changes",
        },
        "pit-evidence-tier-policy": {**POLICY, "policy_hash": digest(POLICY)},
        "area-available-at-classification": {
            "rows": area_rows,
            "tier_a_count": 0,
            "tier_b_count": 0,
            "tier_c_count": len(area_rows),
            "source": "Committed S0 baseline; reclassification, not new area authority",
        },
        "identity-authority-closure-report": {
            "source_row_count": len(identity),
            "source_report_hash": digest(load("identity-conflict-report-r2.json")),
            "strict_authority_count": 0,
            "unresolved_count": sum(r["mapping_status"] == "UNRESOLVED" for r in identity),
            "unresolved_count_scope": "Baseline mapping rows, not unique bases; no new proof",
            "identity_rebound": False,
            "historical_available_at": "UNKNOWN",
            "status": "NOT_CLOSED",
            "source_rows_reinterpreted_as_strict": False,
        },
        "revised-owner-data-supplement-package": {
            "category_counts": categories,
            "blocking_count": sum(g["blocking_or_optional"] == "BLOCKING" for g in gaps),
            "optional_count": sum(g["blocking_or_optional"] == "OPTIONAL" for g in gaps),
            "true_new_data_required_count": 0,
            "true_new_data_count_interpretation": "No proven new-data request; no absence claim",
            "items": gaps,
        },
        "revised-base-season-coverage-matrix": {
            "rows": matrix,
            "scope": "432 audit entities, not company universe; prior statuses preserved",
            "strict_ready_count": 0,
        },
        "s0-final-readiness-recommendation": {
            "result": "PARTIAL",
            "s0_final_ready": False,
            "s1_ready": False,
            "s1_authorized": False,
            "operational_vault_deployed": False,
            "future_vault_blockers": [
                "Predictor role allowlist",
                "Actual package bytes/hash and timestamp/custody validation",
            ],
            "remaining_blockers": [
                "ECMWF authenticated access",
                "Authorized historical DB read-only access",
                "Contemporaneous authority availability evidence",
            ],
            "models_trained": False,
            "scoring_executed": False,
            "v014_accessed_or_modified": False,
        },
    }
    for report in reports.values():
        validate_public(report)
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--access-observation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = build_reports(args.baseline, json.loads(args.access_observation.read_text()))
    if args.output.exists():
        raise ValueError("OUTPUT_EXISTS_NO_OVERWRITE")
    args.output.mkdir(parents=True)
    for name, report in reports.items():
        (args.output / (name + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
    print(json.dumps({"report_hash": digest(reports), "result": "PARTIAL"}))


if __name__ == "__main__":
    main()
