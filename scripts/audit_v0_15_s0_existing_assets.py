"""Read-only audit report assembly and synthetic leakage-contract validation.

This does not build training rows, fit models, score labels or create authority.
Operator projections carry source hashes. Actual archive probes are separate
operator evidence and never run in ordinary CI.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ASSET_STATUSES = frozenset(
    {
        "AVAILABLE_VALID",
        "AVAILABLE_PARTIAL",
        "MISSING",
        "CONFLICTING",
        "NOT_APPLICABLE",
        "UNKNOWN_REQUIRES_REVIEW",
    }
)
DOMAINS = ("harvest", "area", "weather", "identity", "season", "variety", "management")
ARCHIVE_STATUSES = frozenset(
    {
        "AS_ISSUED_COMPLETE",
        "AS_ISSUED_PARTIAL",
        "ARCHIVE_EXISTS_ACCESS_BLOCKED",
        "NO_MATCHING_ARCHIVE_FOUND",
        "NOT_AUDITED",
    }
)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def classify_readiness(row: dict[str, str], *, new_base_no_history: bool = False) -> str:
    if any(row.get(k) not in ASSET_STATUSES for k in DOMAINS):
        raise ValueError("UNKNOWN_ASSET_STATUS")
    if new_base_no_history and row["harvest"] == "MISSING":
        return "NEW_BASE_NO_HISTORY"
    blocked = [
        d
        for d in ("area", "identity", "harvest", "season")
        if row[d] not in {"AVAILABLE_VALID", "NOT_APPLICABLE"}
    ]
    if len(blocked) > 1:
        return "BLOCKED_BY_MULTIPLE_AUTHORITIES"
    if blocked:
        return "BLOCKED_BY_" + blocked[0].upper()
    if any(row[d] != "AVAILABLE_VALID" for d in DOMAINS):
        return "TRAINING_READY_WITH_LIMITATION"
    return "TRAINING_READY"


def coverage_matrix(
    entities: list[dict[str, Any]],
    seasons: list[str],
    facts: dict[tuple[str, str], dict[str, str]],
) -> list[dict[str, Any]]:
    ids = [str(e["entity_id"]) for e in entities]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_ENTITY")
    if len(seasons) != len(set(seasons)):
        raise ValueError("DUPLICATE_SEASON")
    if any(entity not in ids or season not in seasons for entity, season in facts):
        raise ValueError("FACT_OUTSIDE_AUDIT_UNIVERSE")
    if any(set(state) - set(DOMAINS) for state in facts.values()):
        raise ValueError("UNKNOWN_ASSET_DOMAIN")
    rows: list[dict[str, Any]] = []
    metadata = {str(e["entity_id"]): e for e in entities}
    for entity_id in sorted(ids):
        for season in sorted(seasons):
            state = dict.fromkeys(DOMAINS, "UNKNOWN_REQUIRES_REVIEW")
            state.update(facts.get((entity_id, season), {}))
            readiness = classify_readiness(state)
            rows.append(
                {
                    "entity_id": entity_id,
                    "canonical_name": metadata[entity_id].get("canonical_name", ""),
                    "entity_kind": metadata[entity_id].get("entity_kind", "UNCLASSIFIED"),
                    "season_id": season,
                    **state,
                    "asset_readiness": readiness,
                }
            )
    return rows


def identity_conflicts(records: list[dict[str, str]]) -> list[dict[str, Any]]:
    names: dict[str, set[str]] = {}
    ids: dict[str, set[str]] = {}
    for r in records:
        names.setdefault(r["name"], set()).add(r["entity_id"])
        ids.setdefault(r["entity_id"], set()).add(r["name"])
    result: list[dict[str, Any]] = []
    for name, values in sorted(names.items()):
        if len(values) > 1:
            result.append(
                {"kind": "SAME_NAME_MULTIPLE_IDS", "name": name, "entity_ids": sorted(values)}
            )
    for entity, values in sorted(ids.items()):
        if len(values) > 1:
            result.append(
                {
                    "kind": "ID_NAME_VARIATION",
                    "entity_id": entity,
                    "names": sorted(values),
                    "automatic_merge": False,
                }
            )
    return result


def owner_gaps(rows: list[dict[str, Any]], searched_sources: list[str]) -> list[dict[str, Any]]:
    if not searched_sources:
        raise ValueError("GAP_WITHOUT_SEARCH_EVIDENCE")
    gaps = []
    for row in rows:
        if all(row[d] == "UNKNOWN_REQUIRES_REVIEW" for d in DOMAINS):
            gaps.append(
                {
                    "entity_id": row["entity_id"],
                    "season": row["season_id"],
                    "missing_field": "source_label_season_applicability",
                    "status": "UNKNOWN_REQUIRES_REVIEW",
                    "why_required": (
                        "No evidence for this Cartesian cell; not seven missing datasets"
                    ),
                    "existing_evidence": [],
                    "searched_sources": sorted(set(searched_sources)),
                    "blocking_or_optional": "OPTIONAL",
                    "owner_action": "CONFIRM_APPLICABILITY_NOT_REUPLOAD",
                    "minimum_required_value": (
                        "Applicability or explicit non-company identity decision"
                    ),
                    "new_data_upload_requested": False,
                }
            )
            continue
        for domain in DOMAINS:
            status = row[domain]
            if status in {"AVAILABLE_VALID", "NOT_APPLICABLE"}:
                continue
            gaps.append(
                {
                    "entity_id": row["entity_id"],
                    "season": row["season_id"],
                    "missing_field": domain,
                    "status": status,
                    "why_required": "Forecast-time authority required; not an inferred value",
                    "existing_evidence": row.get("evidence_ids", []),
                    "searched_sources": sorted(set(searched_sources)),
                    "blocking_or_optional": "OPTIONAL"
                    if domain in {"variety", "management"}
                    else "BLOCKING",
                    "owner_action": "REVIEW_EXISTING_AUTHORITY_FIRST",
                    "minimum_required_value": (
                        f"Exact {domain} source identity, scope, and historical available_at; "
                        "applicability confirmation if no history"
                    ),
                    "new_data_upload_requested": False,
                }
            )
    return gaps


def aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed


def admit_predictor(feature: dict[str, Any], cutoff: str) -> None:
    """Metadata admission only; no feature value or label is read here."""
    if feature.get("lane") != "PREDICTOR_ZONE":
        raise ValueError("LABEL_ZONE_DENIED")
    if feature.get("role") in {
        "FUTURE_HARVEST",
        "FUTURE_TOTAL",
        "FUTURE_PEAK",
        "FUTURE_CUMULATIVE",
        "ERA5_FUTURE",
        "REANALYSIS_FUTURE",
        "OBSERVED_FUTURE_WEATHER",
    }:
        raise ValueError("TARGET_LEAKAGE")
    boundary = aware(cutoff)
    if feature.get("available_at") is None:
        raise ValueError("HISTORICAL_AVAILABILITY_NOT_ESTABLISHED")
    if aware(feature["available_at"]) > boundary:
        raise ValueError("AVAILABLE_AFTER_CUTOFF")
    if feature.get("role") == "ARCHIVED_OPERATIONAL_FORECAST":
        required = {
            "issue_time",
            "valid_time",
            "model",
            "cycle",
            "step",
            "parameter",
            "provider",
            "retrieval_provenance",
            "stream",
            "expver",
            "resolution",
        }
        if (
            required - feature.keys()
            or any(feature.get(k) in (None, "", [], {}) for k in required)
            or feature.get("operational_run") is not True
        ):
            raise ValueError("ARCHIVE_PROVENANCE_INCOMPLETE")
        issue, valid = aware(feature["issue_time"]), aware(feature["valid_time"])
        if issue > boundary or issue >= valid or aware(feature["available_at"]) < issue:
            raise ValueError("FUTURE_OR_INVALID_RUN")


def authorize_label_unlock(seal: dict[str, Any], consumed: bool) -> None:
    if consumed:
        raise ValueError("BLIND_TEST_ALREADY_CONSUMED")
    if seal.get("prediction_package_hash") is None or seal.get("sealed_at") is None:
        raise ValueError("FORECAST_NOT_SEALED")
    if seal.get("actual_access_before_seal") is not False:
        raise ValueError("ACTUAL_ACCESS_BEFORE_SEAL")
    body = {k: v for k, v in seal.items() if k != "seal_hash"}
    if seal.get("seal_hash") != digest(body):
        raise ValueError("SEAL_HASH_MISMATCH")


def validate_archive_claim(claim: dict[str, Any]) -> None:
    if claim["status"] not in ARCHIVE_STATUSES:
        raise ValueError("UNKNOWN_ARCHIVE_STATUS")
    if claim["status"] == "AS_ISSUED_COMPLETE" and not all(
        claim.get(k) is True
        for k in (
            "retrieval_success",
            "grib_validated",
            "all_256_fields",
            "historical_available_at_proven",
        )
    ):
        raise ValueError("UNPROVEN_ARCHIVE_COMPLETENESS")
    if claim.get("solar_parameter") == "ssr" and claim.get("weather8_complete"):
        raise ValueError("NET_SOLAR_IS_NOT_DOWNWARD_SSRD")
    if claim.get("proxy_is_as_issued"):
        raise ValueError("PROXY_IS_NOT_AS_ISSUED")


def validate_public(value: Any) -> None:
    if isinstance(value, dict):
        denied = {
            "lat",
            "lon",
            "lng",
            "latitude",
            "longitude",
            "coordinates",
            "coefficients",
            "predicted_daily_kg",
            "weather_values",
            "private_path",
            "credentials",
        }
        if denied & {str(key).lower() for key in value}:
            raise ValueError("PUBLIC_PRIVATE_FIELD")
        for child in value.values():
            validate_public(child)
    elif isinstance(value, list):
        for child in value:
            validate_public(child)
    elif isinstance(value, str) and (
        value.startswith("/")
        or ":\\" in value
        or "file://" in value.lower()
        or re.search(r"/(?:Users|tmp|private|opt|var|etc|home)/", value, re.IGNORECASE)
    ):
        raise ValueError("PUBLIC_PRIVATE_PATH")


def attach_audit_metadata(row: dict[str, Any], extra: dict[str, Any]) -> None:
    allowed = {
        "statuses",
        "entity_id",
        "season_id",
        "canonical_name",
        "entity_kind",
        "evidence_ids",
        "historical_as_issued_weather",
        "weather8",
        "pit_backtest_ready",
        "historical_available_at",
        "source_label_scope",
        "harvest_completeness_counts",
        "proxy360_supported_cycle_count",
    }
    if set(extra) - allowed or extra.get("pit_backtest_ready", False) is not False:
        raise ValueError("AUDIT_CONCLUSION_OVERRIDE")
    for key in ("canonical_name", "entity_kind"):
        if key in extra and extra[key] != row[key]:
            raise ValueError("ENTITY_METADATA_CONFLICT")
    row.update(
        {
            k: v
            for k, v in extra.items()
            if k not in {"statuses", "entity_id", "season_id", "canonical_name", "entity_kind"}
        }
    )
    row.setdefault("historical_as_issued_weather", "NOT_AUDITED")
    row.setdefault("weather8", "NOT_AUDITED")
    row["pit_backtest_ready"] = False
    if row["historical_as_issued_weather"] not in ARCHIVE_STATUSES:
        raise ValueError("UNKNOWN_ARCHIVE_STATUS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("AUDIT_OUTPUT_ALREADY_EXISTS")
    source = json.loads(args.audit_input.read_text())
    facts = {(r["entity_id"], r["season_id"]): r["statuses"] for r in source["facts"]}
    if len(facts) != len(source["facts"]):
        raise ValueError("DUPLICATE_FACT")
    rows = coverage_matrix(source["entities"], source["seasons"], facts)
    extras = {(r["entity_id"], r["season_id"]): r for r in source["facts"]}
    for row in rows:
        extra = extras.get((row["entity_id"], row["season_id"]), {})
        attach_audit_metadata(row, extra)
    gaps = owner_gaps(rows, source["searched_sources"]) + source.get("additional_gaps", [])
    result = {
        "schema": "V0_15_S0_READ_ONLY_AUDIT_R2",
        "input_hash": digest(source),
        "cohort_selected": False,
        "model_training_executed": False,
        "matrix": rows,
        "owner_data_supplement_package": gaps,
        "domain_reports": source["domain_reports"],
        "limitations": source["limitations"],
    }
    validate_public(result)
    args.output.mkdir(mode=0o700, parents=True)
    for name, body in [("audit-report.json", result), ("owner-data-supplement-package.json", gaps)]:
        path = args.output / name
        with path.open("x") as stream:
            json.dump(body, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
        path.chmod(0o600)
    with (args.output / "base-season-coverage-matrix.csv").open("x") as stream:
        fields = [
            "entity_id",
            "canonical_name",
            "entity_kind",
            "season_id",
            *DOMAINS,
            "asset_readiness",
            "historical_as_issued_weather",
            "weather8",
            "pit_backtest_ready",
        ]
        writer = csv.DictWriter(
            stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "base-season-coverage-matrix.csv").chmod(0o600)
    print(json.dumps({"matrix_row_count": len(rows), "audit_hash": digest(result)}))


if __name__ == "__main__":
    main()
