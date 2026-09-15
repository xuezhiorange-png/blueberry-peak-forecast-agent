"""Source-file identity gates for the S6 operational-peak authority builder."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from backend.app.area_yield.data import digest
from scripts import build_operational_peak_authority_s6 as builder


def _registry() -> dict[str, Any]:
    registry: dict[str, Any] = {
        "bases": [
            {
                "base_id": "base-yangliu",
                "canonical_base_name": "保山杨柳基地",
                "productive_area_mu": "394.000000",
                "active": True,
            }
        ],
        "version": "BASE_REGISTRY_V1",
    }
    registry["hash"] = digest(registry)
    return registry


def _profile() -> dict[str, Any]:
    return {
        "fold_id": "B",
        "reference_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "profile_kg_per_mu_by_7_day_bin": {"0": "1.000000000000"},
    }


def _json_bytes(value: dict[str, Any], *, indent: int) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=indent).encode("utf-8") + b"\n"
    )


def _write_sources(
    tmp_path: Path,
    registry_raw: bytes,
    profile_raw: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    registry_path = tmp_path / "registry.json"
    profile_path = tmp_path / "reference-B.json"
    registry_path.write_bytes(registry_raw)
    profile_path.write_bytes(profile_raw)
    monkeypatch.setattr(builder, "REGISTRY_FILE_SHA256", hashlib.sha256(registry_raw).hexdigest())
    monkeypatch.setattr(
        builder,
        "REFERENCE_PROFILE_FILE_SHA256",
        hashlib.sha256(profile_raw).hexdigest(),
    )
    monkeypatch.setattr(builder, "REGISTRY_PAYLOAD_HASH", _registry()["hash"])
    return registry_path, profile_path


def test_builder_embeds_exact_input_source_file_hashes(tmp_path, monkeypatch):
    registry_raw = _json_bytes(_registry(), indent=2)
    profile_raw = _json_bytes(_profile(), indent=2)
    registry_path, profile_path = _write_sources(
        tmp_path,
        registry_raw,
        profile_raw,
        monkeypatch,
    )

    payload = builder.build(registry_path, profile_path)

    assert payload["base_registry_file_sha256"] == hashlib.sha256(registry_raw).hexdigest()
    assert payload["reference_profile_file_sha256"] == hashlib.sha256(profile_raw).hexdigest()


@pytest.mark.parametrize("source", ["registry", "profile"])
def test_builder_rejects_semantically_same_but_byte_different_source(
    tmp_path,
    monkeypatch,
    source,
):
    canonical_registry_raw = _json_bytes(_registry(), indent=2)
    canonical_profile_raw = _json_bytes(_profile(), indent=2)
    registry_path, profile_path = _write_sources(
        tmp_path,
        canonical_registry_raw,
        canonical_profile_raw,
        monkeypatch,
    )

    if source == "registry":
        registry_path.write_bytes(_json_bytes(_registry(), indent=4))
    else:
        profile_path.write_bytes(_json_bytes(_profile(), indent=4))

    with pytest.raises(ValueError, match="source file hash is not the approved SHA256"):
        builder.build(registry_path, profile_path)
