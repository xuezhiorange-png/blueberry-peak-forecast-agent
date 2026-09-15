"""Offline S2-01 research qualification; not ingestion or production authority.

Intervals are evidence of independently verified normalized support, not a way to
invent hourly values from sparse native forecasts. No weather data are fetched,
interpolated, filled, fitted or written by this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

VARIABLES = (
    "temperature_2m",
    "tmin",
    "tmax",
    "precipitation",
    "dewpoint",
    "relative_humidity",
    "solar_radiation",
    "wind_if_required",
)
STATUSES = {"DOCUMENTED", "PROJECT_VERIFIED", "NOT_VERIFIED", "NOT_SUPPORTED", "NOT_APPLICABLE"}
LOCAL = ZoneInfo("Asia/Shanghai")


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunIdentity(Contract):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_cycle: str = Field(min_length=1)
    product: str = Field(min_length=1)
    stream: str = Field(min_length=1)
    member_or_control: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    model_initialization_at: AwareDatetime


class Support(Contract):
    """Half-open normalized interval, with explicit single-run provenance."""

    variable: str
    start: AwareDatetime
    end: AwareDatetime
    valid_time: AwareDatetime
    lead_time: int = Field(ge=0, description="Seconds since model initialization")
    run: RunIdentity

    @model_validator(mode="after")
    def valid_interval(self) -> Support:
        if self.start >= self.end or self.valid_time != self.end:
            raise ValueError("INVALID_SUPPORT_INTERVAL")
        if (self.valid_time - self.run.model_initialization_at).total_seconds() != self.lead_time:
            raise ValueError("INVALID_LEAD_TIME")
        return self


class Sample(Contract):
    base_id: str = Field(min_length=1)
    forecast_origin_at: AwareDatetime
    forecast_origin_timezone: Literal["Asia/Shanghai"]
    run: RunIdentity
    issued_at: AwareDatetime | None
    available_at: AwareDatetime | None
    retrieved_at: AwareDatetime
    raw_artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    processing_version: str = Field(min_length=1)
    role: str
    generation_mode: str
    # Status assertions must be backed by reviewable references. The offline
    # gate checks the contract, not authenticity of an external publisher.
    evidence: dict[str, str]
    evidence_references: dict[str, str]
    candidate_zone_used_as_authority: bool
    supports: tuple[Support, ...]


PROOF_KEYS = (
    "issued",
    "available",
    "archive_coverage",
    "access",
    "license",
    "commercial_use",
    "as_issued",
    "support_semantics",
)


def window(origin: datetime, days: int) -> tuple[datetime, datetime]:
    if origin.tzinfo is None or days not in (7, 15):
        raise ValueError("AWARE_ORIGIN_AND_W7_OR_W15_REQUIRED")
    tomorrow = origin.astimezone(LOCAL).date() + timedelta(days=1)
    start = datetime.combine(tomorrow, time.min, LOCAL)
    return start.astimezone(UTC), (start + timedelta(days=days)).astimezone(UTC)


def coverage(sample: Sample, days: int) -> bool:
    start, end = window(sample.forecast_origin_at, days)
    for variable in VARIABLES:
        intervals = sorted(
            (
                r
                for r in sample.supports
                if r.variable == variable and r.end > start and r.start < end
            ),
            key=lambda r: r.start,
        )
        cursor = start
        for row in intervals:
            # Crossing local-day boundaries needs independently normalized
            # support. Do not silently clip an accumulation interval.
            if row.start != cursor or row.end > end:
                return False
            cursor = row.end
        if cursor != end:
            return False
    return True


def qualify(sample: Sample) -> dict[str, Any]:
    reasons: set[str] = set()
    if sample.role != "HISTORICAL_FORECAST_ARCHIVE" or sample.generation_mode != "AS_ISSUED":
        reasons.add("NOT_AS_ISSUED_FORECAST")
    if sample.candidate_zone_used_as_authority:
        reasons.add("CANDIDATE_ZONE_AUTHORITY_FORBIDDEN")
    for key in PROOF_KEYS:
        if sample.evidence.get(key) != "PROJECT_VERIFIED" or not sample.evidence_references.get(
            key
        ):
            reasons.add(f"{key.upper()}_NOT_ESTABLISHED")
    if sample.issued_at is None:
        reasons.add("ISSUED_AT_MISSING")
    elif not sample.run.model_initialization_at <= sample.issued_at <= sample.forecast_origin_at:
        reasons.add("ISSUED_TIME_VIOLATION")
    if sample.available_at is None:
        reasons.add("AVAILABLE_AT_MISSING")
    elif not sample.run.model_initialization_at <= sample.available_at <= sample.forecast_origin_at:
        reasons.add("AVAILABLE_TIME_VIOLATION")
    if sample.issued_at and sample.available_at and sample.issued_at > sample.available_at:
        reasons.add("AVAILABILITY_PRECEDES_ISSUE")
    if sample.available_at and sample.retrieved_at < sample.available_at:
        reasons.add("RETRIEVAL_PRECEDES_AVAILABILITY")
    if any(r.run != sample.run for r in sample.supports):
        reasons.add("MIXED_RUN_FORBIDDEN")
    if any(r.variable not in VARIABLES for r in sample.supports):
        reasons.add("UNKNOWN_VARIABLE")
    payload = [r.model_dump(mode="json") for r in sample.supports]
    if digest(payload) != sample.normalized_payload_hash:
        reasons.add("NORMALIZED_PAYLOAD_HASH_MISMATCH")
    # Catch duplicates/overlap outside W7 as well: malformed source is not
    # rendered valid by cropping it to the requested operational window.
    for variable in VARIABLES:
        rows = sorted((r for r in sample.supports if r.variable == variable), key=lambda r: r.start)
        if any(a.end > b.start for a, b in zip(rows, rows[1:], strict=False)):
            reasons.add("DUPLICATE_OR_OVERLAPPING_SUPPORT")
    result: dict[str, Any] = {
        "pit_status": "PIT_NOT_ESTABLISHED" if reasons else "PIT_CONTRACT_PASS",
        "reasons": sorted(reasons),
        "weather_source_authority_frozen": False,
    }
    for days in (7, 15):
        complete = coverage(sample, days)
        result[f"w{days}_coverage_complete"] = complete
        result[f"w{days}_pit_status"] = "PASS" if complete and not reasons else "BLOCKED"
    result["qualification_hash"] = digest(result)
    return result


def validate_evidence(config: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate the checked-in audit structure and scope; never activate a source."""
    if config["weather_source_authority_frozen"] is not False:
        raise ValueError("AUTHORITY_FREEZE_FORBIDDEN")
    if config["candidate_zone_used_as_authority"] is not False:
        raise ValueError("CANDIDATE_ZONE_AUTHORITY_FORBIDDEN")
    if config["required_variables"] != list(VARIABLES):
        raise ValueError("VARIABLE_CONTRACT_CHANGED")
    if config["forecast_origin_timezone"] != "Asia/Shanghai" or config["windows"] != [7, 15]:
        raise ValueError("WINDOW_CONTRACT_CHANGED")
    if evidence["config_hash"] != digest(config):
        raise ValueError("CONFIG_HASH_MISMATCH")
    # R2 business authorization is separate from the unchanged strict PIT gate.
    # These are research-path permissions, not a training/ingestion execution.
    paths = {
        "historical_weather_feature_research": True,
        "historical_weather_source": "ERA5_LAND",
        "historical_weather_role": "REANALYSIS_REFERENCE",
        "historical_weather_available": True,
        "weather_feature_research_allowed": True,
        "weather_incremental_value_validation_allowed": True,
        "historical_as_issued_forecast_required_for_current_model_research": False,
        "historical_as_issued_forecast_blocks_s2": False,
        "strict_operational_forecast_replay": False,
        "strict_operational_forecast_replay_blocked": True,
        "live_weather_forecast_authority_frozen": False,
    }
    if config.get("research_paths") != paths:
        raise ValueError("RESEARCH_PATH_CONTRACT_CHANGED")
    if any(evidence["recommendation"].get(key) != value for key, value in paths.items()):
        raise ValueError("RESEARCH_PATH_EVIDENCE_MISMATCH")
    ids: set[str] = set()
    for record in evidence["official_evidence"]:
        for field in (
            "id",
            "source",
            "official_document_url",
            "document_title",
            "accessed_at",
            "documented_fact",
            "project_interpretation",
            "verification_status",
        ):
            if not record.get(field):
                raise ValueError(f"MISSING_EVIDENCE_{field}")
        if record["verification_status"] not in STATUSES or record["id"] in ids:
            raise ValueError("INVALID_EVIDENCE_STATUS_OR_DUPLICATE")
        ids.add(record["id"])
        if not record["official_document_url"].startswith("https://"):
            raise ValueError("INVALID_OFFICIAL_URL")
        stamp = datetime.fromisoformat(record["accessed_at"])
        if stamp.tzinfo is None or not re.fullmatch(r"[0-9a-f]{64}", record["snapshot_sha256"]):
            raise ValueError("INVALID_SNAPSHOT_METADATA")
    for source in evidence["source_matrix"]:
        if set(config["matrix_required_fields"]) - source.keys():
            raise ValueError("INCOMPLETE_SOURCE_MATRIX")
        if not source["evidence_ids"] or set(source["evidence_ids"]) - ids:
            raise ValueError("UNRESOLVED_SOURCE_REFERENCE")
    for variable in evidence["variable_matrix"]:
        if set(config["variable_required_fields"]) - variable.keys():
            raise ValueError("INCOMPLETE_VARIABLE_MATRIX")
        if set(variable["evidence_ids"]) - ids:
            raise ValueError("UNRESOLVED_VARIABLE_REFERENCE")
    for group in ("ERA5_LAND", "ECMWF_IFS", "OPEN_METEO"):
        if {r["variable"] for r in evidence["variable_matrix"] if r["source"] == group} != set(
            VARIABLES
        ):
            raise ValueError("MISSING_VARIABLE_COVERAGE")
    return {
        "status": "PASS",
        "config_hash": digest(config),
        "evidence_hash": digest(evidence),
        "network_used": False,
        "weather_source_authority_frozen": False,
        "research_paths": paths,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/weather_source_authority_r1.json")
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("docs/v0-5/s2/weather-source-authority-evidence-r1.json"),
    )
    parser.add_argument(
        "--sample", type=Path, help="Optional normalized support contract; offline only"
    )
    args = parser.parse_args()
    result = validate_evidence(
        json.loads(args.config.read_text()), json.loads(args.evidence.read_text())
    )
    if args.sample:
        result["sample"] = qualify(Sample.model_validate_json(args.sample.read_text()))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
