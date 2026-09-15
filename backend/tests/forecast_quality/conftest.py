"""Small deterministic authority/database fixtures for S6 transport tests."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.area_yield.data import digest
from backend.app.forecast_quality import operational_peak_authority as authority_module
from backend.app.models.operational_peak import (
    OperationalPeakForecastDaily,
    OperationalPeakForecastRun,
)


def build_s6_authority_payload() -> dict[str, Any]:
    registry: dict[str, Any] = {
        "bases": [
            {
                "base_id": "base-yangliu",
                "canonical_base_name": "保山杨柳基地",
                "productive_area_mu": "394.000000",
                "active": True,
            }
        ],
        "enrichment_hashes": {},
        "source_hash": "source-s6",
        "version": "BASE_REGISTRY_V1",
    }
    registry["hash"] = digest(registry)
    profile: dict[str, Any] = {
        "available_bins": list(range(42)),
        "fold_id": "B",
        "missing_bin_policy": "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE",
        "profile_kg_per_mu_by_7_day_bin": {str(index): "1.000000000000" for index in range(42)},
        "reference_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "train_row_set_hash": "train-s6",
        "validation_labels_used": False,
    }
    payload: dict[str, Any] = {
        "authority_version": "OPERATIONAL_PEAK_AUTHORITY_V1",
        "policy_version": "OPERATIONAL_PEAK_POLICY_V1",
        "baseline_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "base_registry_payload_hash": registry["hash"],
        "base_registry_file_sha256": "0" * 64,
        "base_registry_payload": registry,
        "bases": registry["bases"],
        "reference_profile_fold": "B",
        "reference_profile_file_sha256": "1" * 64,
        "reference_profile_payload": profile,
        "weather_used": False,
    }
    payload["authority_hash"] = digest(payload)
    return payload


@pytest.fixture
def s6_authority(tmp_path, monkeypatch):
    payload = build_s6_authority_payload()
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    path = tmp_path / "operational-peak-authority.json"
    path.write_bytes(raw)
    monkeypatch.setattr(authority_module, "REGISTRY_FILE_SHA256", "0" * 64)
    monkeypatch.setattr(
        authority_module, "REGISTRY_PAYLOAD_HASH", payload["base_registry_payload_hash"]
    )
    monkeypatch.setattr(authority_module, "REFERENCE_PROFILE_FILE_SHA256", "1" * 64)
    monkeypatch.setenv("OPERATIONAL_PEAK_AUTHORITY_PATH", str(path))
    monkeypatch.setenv("OPERATIONAL_PEAK_AUTHORITY_SHA256", hashlib.sha256(raw).hexdigest())
    return payload


@pytest.fixture
async def s6_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/operational-peak.db",
        connect_args={"autocommit": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(OperationalPeakForecastRun.__table__.create)
        await connection.run_sync(OperationalPeakForecastDaily.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
