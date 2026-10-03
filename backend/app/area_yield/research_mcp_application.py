"""Server-owned TEST_ONLY orchestration over E1/E2; no model or seal mathematics.

Process settings, not callers, select the registry and store. Synthetic CI entries
remain explicitly synthetic; original R1 entries are checked against E2 authority.
No actual import/evaluation, registration, discovery or real-mode path is exposed.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.area_yield import artifact_registration as e2
from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield import research_records as legacy
from backend.app.area_yield import research_records_r2 as r2
from backend.app.area_yield.data import digest
from backend.app.core.config import get_settings

Record = dict[str, Any]
PUBLIC = (
    Path(__file__).resolve().parents[3]
    / "docs/next-version/evidence/next-area-size-20261002-r1.json"
)


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TestForecastRequest(EmptyRequest):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    target_area_mu: str = Field(max_length=128)
    target_season: str = Field(pattern=r"^\d{4}-\d{4}$")
    base_or_farm_context: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")


class ForecastIdentity(EmptyRequest):
    forecast_id: str = Field(pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")


def enabled() -> bool:
    return get_settings().v0_12_research_mcp_enabled


def runtime() -> tuple[Path, Path, Record, Record]:
    if not enabled():
        raise ValueError("V0_12_RESEARCH_INTERFACE_DISABLED")
    settings = get_settings()
    try:
        if (
            not settings.v0_12_research_runtime_registry_path
            or not settings.v0_12_research_test_store_path
        ):
            raise ValueError("CONFIG_REQUIRED")
        path = Path(settings.v0_12_research_runtime_registry_path).resolve(strict=True)
        store = Path(settings.v0_12_research_test_store_path).resolve()
        parent = store if store.exists() else store.parent
        if not parent.is_dir() or not os.access(parent, os.W_OK | os.X_OK):
            raise ValueError("STORE_UNAVAILABLE")
        registry = legacy.read(path)
        legacy.verify(registry)
        if registry["schema"] != e1.SCHEMA or len(registry["entries"]) != 2:
            raise ValueError("VERIFIED_PAIR_REQUIRED")
        selected = []
        for role in ("RESEARCH_CANDIDATE", "COMPARATOR_BASELINE"):
            matches = [entry for entry in registry["entries"] if entry["model_role"] == role]
            if len(matches) != 1:
                raise ValueError("PAIR_ROLE_INVALID")
            entry = matches[0]
            for key in ("registry_id", "model_id"):
                if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", entry[key]) is None:
                    raise ValueError("IDENTITY_INVALID")
            model, resolved = e1._resolve(registry, entry["registry_id"], role, datetime.now(UTC))
            if model["artifact_hash"] != digest(
                {k: v for k, v in model.items() if k != "artifact_hash"}
            ):
                raise ValueError("ARTIFACT_SELF_HASH_INVALID")
            artifact = Path(entry["artifact_path"]).resolve(strict=True)
            if artifact.is_relative_to(store) or path.is_relative_to(store):
                raise ValueError("STORE_MUST_NOT_CONTAIN_AUTHORITY")
            selected.append((model, resolved))
        candidate, comparator = selected
        if candidate[1]["synthetic"] is not comparator[1]["synthetic"]:
            raise ValueError("MIXED_ARTIFACT_CLASS")
        if candidate[1]["synthetic"] is False:
            expected, _ = e2.verify_pair(
                Path(candidate[1]["artifact_path"]), Path(comparator[1]["artifact_path"]), PUBLIC
            )
            if [candidate[1], comparator[1]] != expected:
                raise ValueError("E2_REGISTRY_PAIR_MISMATCH")
        elif candidate[1]["synthetic"] is not True:
            raise ValueError("SYNTHETIC_CLASS_INVALID")
        return store, path, candidate[1], comparator[1]
    except Exception:
        raise ValueError("V0_12_RESEARCH_RUNTIME_NOT_READY") from None


def readiness() -> Record:
    _, _, candidate, comparator = runtime()
    return {
        "version": "0.12.0",
        "model_role": "RESEARCH_CANDIDATE",
        "S0_COMPLETE": True,
        "S1_COMPLETE": True,
        "E1_COMPLETE": True,
        "E2_COMPLETE": True,
        "E3_COMPLETE": True,
        "engineering_ready_for_future_validation": True,
        "artifact_identity_verified": True,
        "portable_recovery_ready": True,
        "real_prospective_enabled": False,
        "real_forecast_count": 0,
        "stable_gain_established": False,
        "prospective_accuracy_validated": False,
        "production_use_approved": False,
        "S2_authorized": False,
        "version_complete": False,
        "candidate_model_id": candidate["model_id"],
        "candidate_artifact_hash": candidate["artifact_hash"],
        "comparator_registry_id": comparator["registry_id"],
        "comparator_artifact_hash": comparator["artifact_hash"],
        "training_seasons": candidate["training_seasons"],
        "training_sample_count": candidate["training_sample_count"],
        "training_area_range_mu": [
            candidate["training_area_min_mu"],
            candidate["training_area_max_mu"],
        ],
        "synthetic_artifacts": candidate["synthetic"],
    }


def _sanitized(record: Record, *, daily: bool) -> Record:
    if record["test_only"] is not True or record["prospective_class"] != "TEST_NOT_PROSPECTIVE":
        raise ValueError("TEST_ONLY_RECORD_REQUIRED")
    request = record["request_snapshot"]
    output: Record = {
        "forecast_id": record["id"],
        "request_id": request["request_id"],
        "test_only": True,
        "prospective_class": "TEST_NOT_PROSPECTIVE",
        "target_area_mu": request["target_area_mu"],
        "target_season": request["target_season"],
        "base_or_farm_context": request["base_id_or_farm_context"],
        "forecast_start_date": request["forecast_start_date"],
        "forecast_end_date": request["forecast_end_date"],
        "area_applicability": {
            key: record["area_applicability"][key]
            for key in (
                "training_area_min_mu",
                "training_area_max_mu",
                "target_area_mu",
                "area_position",
                "warnings",
                "real_extrapolation_policy",
            )
        },
        "prediction_hash": record["prediction_hash"],
        "seal_hash": record["record_hash"],
        "issued_at": record["issued_at"],
        "sealed_at": record["sealed_at"],
        "metric_contract_version": record["metric_contract_version"],
        "prospective_accuracy_validated": False,
        "production_use_approved": False,
    }
    for name in ("candidate", "comparator"):
        prediction = record["prediction"][name]
        entry = record["artifact_entries"][name]
        summary = prediction["canonical_summary"]
        result = {
            "model_id": entry["model_id"],
            "registry_id": entry["registry_id"],
            "artifact_hash": entry["artifact_hash"],
            "predicted_season_total_kg": prediction["predicted_season_total_kg"],
            "single_day_peak": summary["single_day_peak"],
            "rolling_7day_peak": summary["rolling_7day_peak"],
        }
        if daily:
            result["daily_curve"] = [
                {key: row[key] for key in ("date", "predicted_daily_quantity_kg")}
                for row in prediction["daily_curve"]
            ]
        output[name] = result
    return output


def create_test_forecast(payload: Record) -> Record:
    # Application boundary independently rejects authority/model/path/mode overrides.
    try:
        body = TestForecastRequest.model_validate(payload)
    except ValueError:
        raise ValueError("INVALID_REQUEST_DOCUMENT") from None
    store, registry_path, candidate, comparator = runtime()
    stamp = datetime.now(UTC)
    year = body.target_season[:4]
    request = {
        "request_id": body.request_id,
        "request_mode": "TEST_ONLY",
        "requested_at": stamp.isoformat(),
        "target_area_mu": body.target_area_mu,
        "target_season": body.target_season,
        "base_id_or_farm_context": body.base_or_farm_context,
        "forecast_start_date": f"{year}-07-01",
        "forecast_end_date": f"{int(year) + 1}-04-15",
        "candidate_model_id": candidate["registry_id"],
        "candidate_artifact_hash": candidate["artifact_hash"],
        "candidate_config_hash": candidate["config_hash"],
        "comparator_id": comparator["registry_id"],
        "comparator_artifact_or_policy_hash": comparator["artifact_hash"],
        "request_source_id": f"MCP_{digest(body.request_id)}",
        "request_source_version": "E4_TEST_ONLY_R1",
        "request_source_hash": "0" * 64,
        "authorization_id": body.request_id,
        "authorization_status": "TEST_ONLY",
    }
    e1.validate_request(request, stamp)
    # Temporary server-owned exact source and authorization; E1 retains their
    # identities. They are TEST_ONLY operator material, not independent business proof.
    with tempfile.TemporaryDirectory(prefix=".e4-test-input-", dir=store.parent) as staged:
        source, authorization = Path(staged) / "source.json", Path(staged) / "authorization.json"
        r2._write(source, e1.request_source_payload(request))
        request["request_source_hash"] = legacy.file_hash(source)
        r2._write(
            authorization,
            {
                "authorization_id": body.request_id,
                "status": "TEST_ONLY",
                "request_hash": digest(request),
                "operator": "E4_TEST_ONLY_MCP",
            },
        )
        record = e1.create_research_forecast(
            store, registry_path, legacy.file_hash(registry_path), request, source, authorization
        )
    return _sanitized(record, daily=False)


def get_test_forecast(identity: str, *, verify: bool = False) -> Record:
    ForecastIdentity.model_validate({"forecast_id": identity})
    store, _, _, _ = runtime()
    record = (
        e1.verify_research_forecast(store, identity)
        if verify
        else e1.get_research_forecast(store, identity)
    )
    result = _sanitized(record, daily=not verify)
    if not verify:
        return result
    return {
        "forecast_id": record["id"],
        "seal_verified": True,
        "test_only": True,
        "prediction_hash": record["prediction_hash"],
        "seal_hash": record["record_hash"],
        "candidate_artifact_hash": record["artifact_entries"]["candidate"]["artifact_hash"],
        "comparator_artifact_hash": record["artifact_entries"]["comparator"]["artifact_hash"],
        "metric_contract_version": record["metric_contract_version"],
        "real_prospective": False,
        "production_use_approved": False,
    }
