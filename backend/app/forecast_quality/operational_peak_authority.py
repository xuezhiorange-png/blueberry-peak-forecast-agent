"""Server-owned, hash-pinned authority for the S5 operational peak product."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.area_yield.data import digest
from backend.app.forecast_quality.operational_peak import (
    BASELINE_ID,
    POLICY_VERSION,
    load_frozen_reference_profile,
)

AUTHORITY_VERSION = "OPERATIONAL_PEAK_AUTHORITY_V1"
REGISTRY_FILE_SHA256 = "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904"
REGISTRY_PAYLOAD_HASH = "d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293"
REFERENCE_PROFILE_FOLD = "B"
REFERENCE_PROFILE_FILE_SHA256 = "a0a5cbc3c3ca5bd2b0b8860328eee73840499b38da89c11a104f83d02fd77c5b"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class OperationalPeakAuthorityError(RuntimeError):
    """Fail-closed authority error with a stable, non-sensitive code."""

    status_code = 503

    def __init__(self, code: str, reason: str | None = None) -> None:
        self.code = code
        self.reason = reason or code
        super().__init__(self.reason)


@dataclass(frozen=True, slots=True)
class OperationalPeakAuthoritySnapshot:
    authority_version: str
    policy_version: str
    baseline_id: str
    authority_hash: str
    registry: dict[str, Any]
    reference_profile: Mapping[Any, Any]
    reference_profile_fold: str
    weather_used: bool


def _authority_hash(payload: dict[str, Any]) -> str:
    return digest({key: value for key, value in payload.items() if key != "authority_hash"})


def _require_hash(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        raise OperationalPeakAuthorityError(code, "authority hash is malformed")
    return value


def _read_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise OperationalPeakAuthorityError("AUTHORITY_FILE_UNREADABLE") from exc
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperationalPeakAuthorityError("AUTHORITY_PAYLOAD_INVALID") from exc
    if not isinstance(value, dict):
        raise OperationalPeakAuthorityError("AUTHORITY_PAYLOAD_INVALID")
    return raw, value


def _validate_authority(value: dict[str, Any]) -> OperationalPeakAuthoritySnapshot:
    if value.get("authority_version") != AUTHORITY_VERSION:
        raise OperationalPeakAuthorityError("POLICY_AUTHORITY_MISMATCH")
    if value.get("policy_version") != POLICY_VERSION or value.get("baseline_id") != BASELINE_ID:
        raise OperationalPeakAuthorityError("POLICY_AUTHORITY_MISMATCH")
    if value.get("weather_used") is not False:
        raise OperationalPeakAuthorityError("POLICY_AUTHORITY_MISMATCH")

    stored_authority_hash = _require_hash(value.get("authority_hash"), "AUTHORITY_PAYLOAD_INVALID")
    if _authority_hash(value) != stored_authority_hash:
        raise OperationalPeakAuthorityError("AUTHORITY_PAYLOAD_INVALID")

    if (
        value.get("base_registry_file_sha256") != REGISTRY_FILE_SHA256
        or value.get("base_registry_payload_hash") != REGISTRY_PAYLOAD_HASH
    ):
        raise OperationalPeakAuthorityError("REGISTRY_AUTHORITY_MISMATCH")
    registry = value.get("base_registry_payload")
    bases = value.get("bases")
    if not isinstance(registry, dict) or not isinstance(bases, list):
        raise OperationalPeakAuthorityError("REGISTRY_AUTHORITY_MISMATCH")
    if registry.get("hash") != REGISTRY_PAYLOAD_HASH or registry.get("bases") != bases:
        raise OperationalPeakAuthorityError("REGISTRY_AUTHORITY_MISMATCH")
    if digest({key: item for key, item in registry.items() if key != "hash"}) != registry.get(
        "hash"
    ):
        raise OperationalPeakAuthorityError("REGISTRY_AUTHORITY_MISMATCH")

    profile = value.get("reference_profile_payload")
    if (
        value.get("reference_profile_fold") != REFERENCE_PROFILE_FOLD
        or value.get("reference_profile_file_sha256") != REFERENCE_PROFILE_FILE_SHA256
        or not isinstance(profile, dict)
    ):
        raise OperationalPeakAuthorityError("REFERENCE_PROFILE_AUTHORITY_MISMATCH")
    try:
        reference_profile = load_frozen_reference_profile(profile)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise OperationalPeakAuthorityError("REFERENCE_PROFILE_AUTHORITY_MISMATCH") from exc

    return OperationalPeakAuthoritySnapshot(
        authority_version=AUTHORITY_VERSION,
        policy_version=POLICY_VERSION,
        baseline_id=BASELINE_ID,
        authority_hash=stored_authority_hash,
        registry={"bases": bases},
        reference_profile=reference_profile,
        reference_profile_fold=REFERENCE_PROFILE_FOLD,
        weather_used=False,
    )


def load_operational_peak_authority() -> OperationalPeakAuthoritySnapshot:
    """Load and validate the configured authority exactly once per execution."""

    configured_path = os.environ.get("OPERATIONAL_PEAK_AUTHORITY_PATH")
    expected_file_hash = os.environ.get("OPERATIONAL_PEAK_AUTHORITY_SHA256")
    if not configured_path or not expected_file_hash:
        raise OperationalPeakAuthorityError("AUTHORITY_NOT_CONFIGURED")
    try:
        path = Path(configured_path)
    except (TypeError, ValueError) as exc:
        raise OperationalPeakAuthorityError("AUTHORITY_FILE_UNREADABLE") from exc
    raw, value = _read_json(path)
    if hashlib.sha256(raw).hexdigest() != expected_file_hash:
        raise OperationalPeakAuthorityError("AUTHORITY_FILE_HASH_MISMATCH")
    return _validate_authority(value)


__all__ = [
    "AUTHORITY_VERSION",
    "OperationalPeakAuthorityError",
    "OperationalPeakAuthoritySnapshot",
    "load_operational_peak_authority",
]
