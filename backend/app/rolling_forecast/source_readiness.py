"""Offline metadata preflight / SYNTHETIC-only source quality inspection.

No importer, model loader, prediction issuance, label reader or enrollment.
Uses S8's sole parser and S7's authoritative Harvest State calculation.
"""

import argparse
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from backend.app.rolling_forecast import engine, inbound
from backend.app.rolling_forecast.policy import Catalog, Context, InboundSnapshot
from backend.app.rolling_forecast.source_requirements import (
    SourceRequirements,
    public_checklist,
    template,
)
from backend.research.v019_synthetic_validation import digest

Mode = Literal["metadata", "synthetic-full"]


def public_name(value: str) -> str:
    return "REDACTED-" + digest(value)[:12] if "/" in value or "\\" in value else value


def error_code(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        errors = [e.get("ctx", {}).get("error") for e in exc.errors(include_input=False)]
        codes = {str(e) for e in errors if isinstance(e, ValueError)}
        if len(codes) == 1 and all(re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", c) for c in codes):
            return next(iter(codes))
        return "SOURCE_SCHEMA_INVALID"
    text = str(exc)
    return text if re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", text) else "SOURCE_VALIDATION_FAILED"


def read_metadata(path: Path) -> bytes:
    """Explicit, bounded plan/catalog reads; no discovery and no Day access."""
    absolute = path.absolute()
    aliases = {Path("/tmp"), Path("/var")}
    if (
        absolute.is_symlink()
        or any(p.is_symlink() and p not in aliases for p in absolute.parents)
        or not absolute.is_file()
        or absolute.stat().st_mode & 0o022
        or absolute.stat().st_size > 8 * 1024 * 1024
    ):
        raise ValueError("UNSAFE_METADATA_FILE")
    return absolute.read_bytes()


def dates(start: date, end_exclusive: date) -> list[date]:
    return [start + timedelta(days=i) for i in range(max(0, (end_exclusive - start).days))]


def _empty(
    base: str,
    season: str,
    origin: date,
    cutoff: datetime,
    mode: Mode,
    requirements: SourceRequirements | None = None,
) -> dict[str, Any]:
    return dict(
        schema_version="INBOUND_SOURCE_READINESS_V1",
        base_id=public_name(base),
        season=season,
        origin=str(origin),
        cutoff=cutoff.astimezone(UTC).isoformat(),
        mode=mode,
        quantity_basis="RECORDED_INBOUND_WEIGHT",
        model_training_target_quantity_basis=None,
        authority_status="PENDING_SOURCE_AUTHORITY",
        real_business_use_authorized=False,
        real_business_data_read=False,
        real_business_data_scored=False,
        strict_pit_validated=False,
        prospective_accuracy_validated=False,
        automatic_enrollment=False,
        prediction_issued=False,
        model_contents_validated=False,
        day_payloads_read=0,
        m1_feature_readiness="NOT_PROVEN",
        status="BLOCKED",
        blockers=[],
        checks={},
        daily=[],
        windows={},
        identities={},
        source_requirements=public_checklist(requirements or template()),
    )


def _finish(report: dict[str, Any]) -> dict[str, Any]:
    report["blockers"] = sorted(set(report["blockers"]))
    if report["mode"] == "synthetic-full" and report["status"] == "BLOCKED":
        report["m1_feature_readiness"] = "NOT_COMPUTABLE"
    report["counts"] = {
        s: sum(d["status"] == s for d in report["daily"])
        for s in (
            "COMPLETE",
            "CONFIRMED_ZERO",
            "MISSING",
            "PARTIAL",
            "LATE",
            "CONFLICT",
            "UNKNOWN",
            "NOT_PROVEN",
        )
    }
    report["index_issue_counts"] = {
        "missing_index_days": sum("MISSING_DAY_INDEX" in d["reasons"] for d in report["daily"]),
        "partial_member_days": sum(
            "PARTIAL_MEMBER_COVERAGE" in d["reasons"] for d in report["daily"]
        ),
        "unproven_time_days": sum(
            any(
                r in d["reasons"]
                for r in (
                    "DAY_TIME_AUTHORITY_MISSING",
                    "SOURCE_TIME_UNVERIFIED",
                    "SOURCE_TIMESTAMP_MISSING",
                )
            )
            for d in report["daily"]
        ),
    }
    return {**report, "business_summary_hash": digest(report)}


def inspect_source(
    context: Context,
    source_reference: str,
    model_reference: str,
    origin: date,
    cutoff: datetime,
    *,
    mode: Mode = "metadata",
    requirements: SourceRequirements | None = None,
) -> dict[str, Any]:
    if cutoff.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    report = _empty(
        context.area.base_id, context.calendar.season, origin, cutoff, mode, requirements
    )
    sources = [s for s in context.snapshots if s.reference == source_reference]
    models = [m for m in context.models if m.reference == model_reference]
    if len(sources) != 1 or len(models) != 1 or not isinstance(sources[0], InboundSnapshot):
        report["blockers"].append("EXPLICIT_INBOUND_RESOURCE_REQUIRED")
        return _finish(report)
    source, model = sources[0], models[0]
    report.update(
        source_reference=public_name(source.reference),
        source_system=public_name(source.source_system),
        data_class=source.provenance,
        context_reference=public_name(context.reference),
        model_training_target_quantity_basis=model.model_training_target_quantity_basis,
        feature_date_start=str(context.calendar.start),
        business_timezone=context.calendar.timezone,
        feature_date_end=str(origin - timedelta(days=1)),
        forecast_date_start=str(origin + timedelta(days=1)),
        forecast_date_end=str(origin + timedelta(days=15)),
    )
    report["identities"] = dict(
        snapshot_hash=source.snapshot_hash,
        manifest_sha256=source.manifest_sha256,
        physical_definition_hash=source.physical_definition_hash,
        fit_sha256=model.fit_sha256,
        model_file_sha256=model.file_sha256,
        membership_authority_hash=source.membership_authority_hash,
        mapping_registry_hash=source.mapping_registry_hash,
        area_authority_hash=context.area.source_hash,
        calendar_authority_hash=context.calendar.source_hash,
    )
    if mode == "synthetic-full" and source.provenance != "SYNTHETIC_TEST_FIXTURE":
        report["blockers"].append("REAL_SOURCE_EXECUTION_NOT_AUTHORIZED")
        return _finish(report)
    if mode not in ("metadata", "synthetic-full"):
        report["blockers"].append("UNSUPPORTED_INSPECTION_MODE")
        return _finish(report)
    checks, blockers = report["checks"], report["blockers"]
    try:
        engine.harvest_features(
            context.calendar, context.area, origin, cutoff, [], "RESEARCH_SHADOW"
        )
        checks["origin_calendar_area"] = "PASS"
    except ValueError as exc:
        checks["origin_calendar_area"] = error_code(exc)
        blockers.append(error_code(exc))
    if (
        not context.calendar.start <= origin <= context.calendar.end
        or (origin - context.calendar.start).days > 400
    ):
        return _finish(report)
    try:
        inbound.require_target_metadata(
            source, model.model_training_target_quantity_basis, model.fit_sha256, model.provenance
        )
        checks["registered_fit_binding"] = "PASS_METADATA_ONLY"
    except ValueError as exc:
        checks["registered_fit_binding"] = error_code(exc)
        blockers.append(error_code(exc))
    try:
        index = inbound.read_index(context, source)
        checks["schema_and_source_identity"] = "PASS"
    except (ValueError, OSError) as exc:
        blockers.append(error_code(exc))
        checks["schema_and_source_identity"] = error_code(exc)
        return _finish(report)
    if not index.physical_definition.verified():
        blockers.append("SOURCE_BASIS_UNVERIFIED")
    checks["physical_definition"] = (
        "PASS_DECLARED_CONTRACT_ONLY"
        if index.physical_definition.verified()
        else "SOURCE_BASIS_UNVERIFIED"
    )
    checks["source_authority"] = "PENDING_SOURCE_AUTHORITY"
    checks["model_file_contents"] = "NOT_PROVEN_NOT_READ"
    checks["revision_policy"] = index.revision_rule
    checks["grade_policy"] = "REGISTERED_DISJOINT_SETS"
    items = {d.business_date: d for d in index.days}
    expected = {digest(m.model_dump(mode="json")) for m in source.members}
    if any(
        not context.calendar.start <= d.business_date <= context.calendar.end for d in index.days
    ):
        blockers.append("SOURCE_INDEX_OUTSIDE_CALENDAR")
    metadata: dict[date, dict[str, Any]] = {}
    for day in dates(context.calendar.start, origin):
        item = items.get(day)
        reasons = []
        covered: set[str] = set()
        if item is None:
            reasons.append("MISSING_DAY_INDEX")
        else:
            try:
                _, covered = inbound.member_coverage(source, item)
            except ValueError as exc:
                reasons.append(error_code(exc))
                blockers.append(error_code(exc))
            if covered != expected:
                reasons.append("PARTIAL_MEMBER_COVERAGE")
            if item.completeness_status != "COMPLETE":
                reasons.append("SOURCE_COMPLETENESS_" + item.completeness_status)
            if item.known_at is None:
                reasons.append("DAY_TIME_AUTHORITY_MISSING")
            elif item.known_at > cutoff:
                reasons.append("LATE_COMPLETENESS_AUTHORITY")
        if day not in source.complete_dates:
            reasons.append("NO_COMPLETENESS_AUTHORITY_FOR_DAY")
        if source.completeness_known_at > cutoff:
            reasons.append("SOURCE_COMPLETENESS_AFTER_CUTOFF")
        metadata[day] = dict(
            business_date=str(day),
            status="NOT_PROVEN",
            reasons=sorted(set(reasons)),
            claimed_complete=bool(item and not reasons),
            expected_member_count=len(expected),
            covered_member_count=len(covered),
            missing_members=["MEMBER-" + h[:12] for h in sorted(expected - covered)],
            record_count=None,
            excluded_record_count=None,
            time_status="NOT_PROVEN",
        )
    observations = []
    if mode == "synthetic-full" and not blockers:
        conflicts: set[date] = set()
        try:
            for checked in inbound.inspect_days(context, source, origin, cutoff):
                row = metadata[checked.business_date]
                report["day_payloads_read"] += int(checked.payload_read)
                row.update(
                    record_count=checked.record_count,
                    excluded_record_count=checked.excluded_record_count,
                    reasons=list(checked.reasons),
                )
                if checked.error is not None:
                    blockers.extend(checked.reasons)
                    conflicts.update(checked.conflict_dates)
                if checked.observation is not None:
                    observations.append(checked.observation)
                    row["status"] = (
                        (
                            "CONFIRMED_ZERO"
                            if checked.observation.record_state == "CONFIRMED_ZERO"
                            else "COMPLETE"
                        )
                        if checked.observation.observation_completeness == "COMPLETE"
                        else "UNKNOWN"
                    )
                else:
                    row["status"] = "CONFLICT"
                if any("LATE" in r or "AFTER_CUTOFF" in r for r in row["reasons"]):
                    row["status"] = "LATE"
                elif (
                    "PARTIAL_MEMBER_COVERAGE" in row["reasons"]
                    or "SOURCE_COMPLETENESS_PARTIAL" in row["reasons"]
                ):
                    row["status"] = "PARTIAL"
                elif any(
                    r in row["reasons"]
                    for r in ("MISSING_DAY_INDEX", "NO_RECORD_WITHOUT_ZERO_AUTHORITY")
                ):
                    row["status"] = "MISSING"
                row["time_status"] = (
                    "PASS_SYNTHETIC_EVIDENCE"
                    if row["status"] in ("COMPLETE", "CONFIRMED_ZERO")
                    else "UNKNOWN_OR_LATE"
                )
            for day in conflicts:
                if day in metadata:
                    metadata[day]["status"] = "CONFLICT"
                    metadata[day]["reasons"] = sorted(
                        set(metadata[day]["reasons"] + ["SOURCE_CONFLICT"])
                    )
        except (ValueError, OSError) as exc:
            blockers.append(error_code(exc))
    feature = (
        engine.harvest_features(
            context.calendar, context.area, origin, cutoff, observations, "RESEARCH_SHADOW"
        )
        if checks["origin_calendar_area"] == "PASS"
        else None
    )
    for key, length in (
        ("past_7d_harvest_kg", 7),
        ("past_14d_harvest_kg", 14),
        ("past_28d_harvest_kg", 28),
        ("season_to_date_harvest_kg", None),
    ):
        required = dates(
            origin - timedelta(days=length) if length else context.calendar.start, origin
        )
        selected = [
            metadata.get(
                d, dict(business_date=str(d), status="MISSING", reasons=["OUTSIDE_SEASON_SUPPORT"])
            )
            for d in required
        ]
        complete = sum(d["status"] in ("COMPLETE", "CONFIRMED_ZERO") for d in selected)
        window = dict(
            required_count=len(required),
            complete_count=complete,
            claimed_complete_count=sum(bool(d.get("claimed_complete")) for d in selected),
            missing_dates=[
                d["business_date"]
                for d in selected
                if d["status"] == "MISSING" or "MISSING_DAY_INDEX" in d["reasons"]
            ],
            late_dates=[
                d["business_date"]
                for d in selected
                if d["status"] == "LATE"
                or any("LATE" in r or "AFTER_CUTOFF" in r for r in d["reasons"])
            ],
            time_unproven_dates=[
                d["business_date"]
                for d in selected
                if any(
                    r in d["reasons"]
                    for r in (
                        "DAY_TIME_AUTHORITY_MISSING",
                        "SOURCE_TIMESTAMP_MISSING",
                        "SOURCE_TIME_UNVERIFIED",
                    )
                )
            ],
            partial_member_dates=[
                d["business_date"] for d in selected if "PARTIAL_MEMBER_COVERAGE" in d["reasons"]
            ],
            conflict_dates=[d["business_date"] for d in selected if d["status"] == "CONFLICT"],
            unverified_dates=[
                d["business_date"]
                for d in selected
                if d["status"] not in ("COMPLETE", "CONFIRMED_ZERO")
            ],
            status="NOT_PROVEN"
            if mode == "metadata"
            else "PASS"
            if complete == len(required)
            else "INCOMPLETE",
        )
        report["windows"][key] = window
        if mode == "synthetic-full" and not blockers and feature is not None:
            audit_key = key.replace("_harvest_kg", "_missing_count")
            if feature["audit"][audit_key] != len(required) - complete:
                blockers.append("READINESS_RUNTIME_PARITY_MISMATCH")
    report["daily"] = list(metadata.values())
    if mode == "metadata":
        report["status"] = "BLOCKED" if blockers else "METADATA_VALID"
    elif blockers:
        report["m1_feature_readiness"], report["status"] = "NOT_COMPUTABLE", "BLOCKED"
    elif feature is not None and feature["complete"]:
        report["m1_feature_readiness"], report["status"] = "COMPUTABLE", "SYNTHETIC_FULL_VALIDATED"
    else:
        report["m1_feature_readiness"], report["status"] = "NOT_COMPUTABLE", "INCOMPLETE"
        blockers.extend(feature["reasons"] if feature else ["ORIGIN_AUTHORITY_UNVERIFIED"])
    return _finish(report)


def write_reports(report: dict[str, Any], output_dir: Path) -> None:
    from backend.app.rolling_forecast.source_readiness_report import write_reports as render

    render(report, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--catalog", required=True, type=Path)
    inspect.add_argument("--context", required=True)
    inspect.add_argument("--source", default="SYNTHETIC-INBOUND-SNAPSHOT")
    inspect.add_argument("--model", default="SYNTHETIC")
    inspect.add_argument("--origin", required=True, type=date.fromisoformat)
    inspect.add_argument("--cutoff", required=True, type=datetime.fromisoformat)
    inspect.add_argument("--mode", choices=("metadata", "synthetic-full"), default="metadata")
    inspect.add_argument("--requirements", type=Path)
    inspect.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.cutoff.tzinfo is None:
        parser.error("TIMEZONE_REQUIRED")
    report = _empty("UNKNOWN", "UNKNOWN", args.origin, args.cutoff, args.mode)
    try:
        raw = json.loads(read_metadata(args.catalog))
        if not isinstance(raw, dict) or not isinstance(raw.get("contexts"), list):
            raise ValueError("SOURCE_SCHEMA_INVALID")
        if any(not isinstance(c, dict) for c in raw["contexts"]):
            raise ValueError("SOURCE_SCHEMA_INVALID")
        matches = [c for c in raw["contexts"] if c.get("reference") == args.context]
        if len(matches) != 1:
            raise ValueError("CONTEXT_IDENTITY_MISMATCH")
        snapshots = matches[0].get("snapshots")
        if not isinstance(snapshots, list) or any(not isinstance(s, dict) for s in snapshots):
            raise ValueError("SOURCE_SCHEMA_INVALID")
        selected = [s for s in snapshots if s.get("reference") == args.source]
        if args.mode == "synthetic-full" and (
            len(selected) != 1 or selected[0].get("provenance") != "SYNTHETIC_TEST_FIXTURE"
        ):
            raise ValueError("REAL_SOURCE_EXECUTION_NOT_AUTHORIZED")
        catalog = Catalog.model_validate(raw)
        context = next(c for c in catalog.contexts if c.reference == args.context)
        requirements = (
            SourceRequirements.model_validate_json(read_metadata(args.requirements))
            if args.requirements
            else None
        )
        report = inspect_source(
            context,
            args.source,
            args.model,
            args.origin,
            args.cutoff,
            mode=args.mode,
            requirements=requirements,
        )
    except (ValueError, OSError) as exc:
        report["blockers"].append(error_code(exc))
        report = _finish(report)
    try:
        write_reports(report, args.output_dir)
    except (OSError, ValueError) as exc:
        parser.exit(2, error_code(exc) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("status", "m1_feature_readiness", "business_summary_hash", "blockers")
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0 if report["status"] in ("METADATA_VALID", "SYNTHETIC_FULL_VALIDATED") else 2)


if __name__ == "__main__":
    main()
