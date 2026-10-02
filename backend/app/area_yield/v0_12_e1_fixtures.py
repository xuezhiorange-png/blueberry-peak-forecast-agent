"""Explicit public hand-specified E1 fixtures: no training or real business facts."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield.data import calendar, digest
from backend.app.area_yield.research_records import file_hash

BASE_SHA = "c9a226a108da30840945ae932256209846a17606"


def _write(path: Path, value: Any) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def make_fixture(root: Path, *, area: str = "736") -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=False)
    entries = []
    for kind in ("candidate", "baseline"):
        model: dict[str, Any] = {
            "model_id": f"SYNTHETIC_E1_{kind.upper()}_NOT_R1_ARTIFACT",
            "model_family": kind,
            "model_version": "1",
            "model_role": "RESEARCH_CANDIDATE",
            "created_at": "2026-10-02T00:00:00+00:00",
            "training_identity": {"synthetic": True, "training_executed": False},
            "training_seasons": ["2023-2024"],
            "training_sample_count": 0,
            "training_area_range_mu": ["216", "2548"],
            "training_bases": ["SYNTHETIC_BASE"],
            "parameters": {
                "pooled_yield": "2",
                "mean_log_area": math.log(736),
                "alpha": math.log(2.1),
                "beta": 0.02,
                "penalty": 1.0,
            },
            "curve_parameters": {
                day.strftime("%m-%d"): float(day.month)
                for day in calendar(date(2027, 7, 1), date(2028, 4, 15))
            },
            "target_definition": e1.SPEC["window"],
            "quantity_precision": "0.000001kg_HALF_EVEN",
            "features": ["log_area_mu"] if kind == "candidate" else [],
            "weather_used": False,
            "holdout_used_for_fit": False,
            "fixture_role": "HAND_SPECIFIED_NOT_TRAINED_NOT_BUSINESS_DATA",
        }
        model["artifact_hash"] = digest(model)
        path = root / f"SYNTHETIC-{kind}.json"
        _write(path, model)
        entries.append(
            e1.register_artifact(
                path,
                {
                    "registry_id": model["model_id"]
                    if kind == "candidate"
                    else "SYNTHETIC_V0_12_COMPARATOR_BASELINE",
                    "model_role": "RESEARCH_CANDIDATE"
                    if kind == "candidate"
                    else "COMPARATOR_BASELINE",
                    "training_manifest_hash": digest(model["training_identity"]),
                    "training_cutoff": "2024-04-15",
                    "code_sha": BASE_SHA,
                    "source_execution_id": "E1_SYNTHETIC_HAND_SPECIFIED",
                    "synthetic": True,
                    "active_for_research": True,
                },
            )
        )
    registry = root / "SYNTHETIC-registry.json"
    e1.save_registry(registry, entries)
    request = {
        "request_id": "SYNTHETIC_REQUEST_E1",
        "request_mode": "TEST_ONLY",
        "requested_at": "2028-06-01T00:00:00+08:00",
        "target_area_mu": area,
        "target_season": "2028-2029",
        "base_id_or_farm_context": "SYNTHETIC_BASE",
        "forecast_start_date": "2028-07-01",
        "forecast_end_date": "2029-04-15",
        "candidate_model_id": entries[0]["registry_id"],
        "candidate_artifact_hash": entries[0]["artifact_hash"],
        "candidate_config_hash": entries[0]["config_hash"],
        "comparator_id": entries[1]["registry_id"],
        "comparator_artifact_or_policy_hash": entries[1]["artifact_hash"],
        "request_source_id": "SYNTHETIC_SOURCE",
        "request_source_version": "1",
        "request_source_hash": "0" * 64,
        "authorization_id": "SYNTHETIC_AUTHORIZATION",
        "authorization_status": "TEST_ONLY",
    }
    source = root / "SYNTHETIC-request-source.json"
    _write(source, e1.request_source_payload(request))
    request["request_source_hash"] = file_hash(source)
    authorization = root / "SYNTHETIC-authorization.json"
    _write(
        authorization,
        {
            "authorization_id": request["authorization_id"],
            "status": "TEST_ONLY",
            "request_hash": digest(request),
            "operator": "SYNTHETIC_TEST_OPERATOR",
        },
    )
    _write(root / "example-request.json", request)
    actual = {
        "actual_revision_id": "SYNTHETIC_ACTUAL_1",
        "forecast_id": "BIND_AFTER_TEST_ISSUE",
        "base_id": "SYNTHETIC_BASE",
        "season": "2028-2029",
        "unit": "kg",
        "request_mode": "TEST_ONLY",
        "rows": [
            {
                "business_date": day.isoformat(),
                "quantity_status": "AUTHORIZED_ZERO" if i == 0 else "OBSERVED",
                "new_quantity_kg": "0.000000" if i == 0 else "10.000000",
            }
            for i, day in enumerate(calendar(date(2028, 7, 1), date(2029, 4, 15)))
        ],
        "source_id": "SYNTHETIC_ACTUAL_SOURCE",
        "source_version": "1",
        "source_hash": "0" * 64,
        "normalization_version": "EXACT_MICROKG_JSON_E1",
        "first_seen_at": "2029-04-16T00:00:00+08:00",
        "recorded_at": "2029-04-16T01:00:00+08:00",
        "parent_revision_id": None,
        "supersedes_revision_id": None,
        "revision_reason": None,
    }
    return {
        "store": root / "records",
        "registry": registry,
        "request": request,
        "source": source,
        "authorization": authorization,
        "actual": actual,
        "actual_source": root / "SYNTHETIC-actual-source.json",
        "issue_clock": datetime.fromisoformat("2028-06-02T00:00:00+08:00"),
        "actual_clock": datetime.fromisoformat("2029-04-17T00:00:00+08:00"),
    }


def bind_actual(case: dict[str, Any], forecast_id: str) -> None:
    """Generate a public synthetic source after its TEST_ONLY forecast exists."""
    case["actual"]["forecast_id"] = forecast_id
    _write(case["actual_source"], e1.actual_source_payload(case["actual"]))
    case["actual"]["source_hash"] = file_hash(case["actual_source"])
    _write(case["actual_source"].with_name("example-actual.json"), case["actual"])
