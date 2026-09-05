"""SOURCE-002 frozen variety identity to canonical production Variety master resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from backend.app.rolling_backtest.canonical import sha256_payload

SOURCE_002_VARIETY_MASTER_IDENTITY_MAPPING_POLICY_VERSION: Final[str] = (
    "source-002-variety-master-identity-mapping-v1"
)

_GOVERNED_SOURCE_TO_MASTER_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("蓝莓原果D1", "D1", "D1"),
    ("蓝莓原果D10", "D10", "D10"),
    ("蓝莓原果D11", "D11", "D11"),
    ("蓝莓原果D12", "D12", "D12"),
    ("蓝莓原果D13", "D13", "D13"),
    ("蓝莓原果D19", "D19", "D19"),
    ("蓝莓原果D2", "D2", "D2"),
    ("蓝莓原果D3", "D3", "D3"),
    ("蓝莓原果D30", "D30", "D30"),
    ("蓝莓原果D31", "D31", "D31"),
    ("蓝莓原果D5", "D5", "D5"),
    ("蓝莓原果D8", "D8", "D8"),
    ("蓝莓原果Dx", "Dx", "Dx"),
    ("蓝莓原果N109", "Dx", "Dx"),
    ("蓝莓原果N200", "Dx", "Dx"),
    ("蓝莓原果N70", "Dx", "Dx"),
    ("蓝莓原果N71", "Dx", "Dx"),
    ("蓝莓原果N72", "Dx", "Dx"),
    ("蓝莓原果N73", "Dx", "Dx"),
    ("蓝莓原果N76", "Dx", "Dx"),
)


@dataclass(frozen=True, slots=True)
class Source002MasterVarietyIdentity:
    code: str
    name: str


_SOURCE_TO_MASTER: dict[str, Source002MasterVarietyIdentity] = {
    source_key: Source002MasterVarietyIdentity(code=master_code, name=master_name)
    for source_key, master_code, master_name in _GOVERNED_SOURCE_TO_MASTER_ENTRIES
}


def source_002_variety_master_identity_mapping_entries() -> tuple[
    tuple[str, Source002MasterVarietyIdentity], ...
]:
    """Return governed source→master entries in canonical order."""
    return tuple((source_key, identity) for source_key, identity in _SOURCE_TO_MASTER.items())


def build_source_002_variety_master_identity_mapping_payload() -> dict[str, object]:
    """Build the canonical mapping payload for deterministic identity hashing."""
    return {
        "mapping_policy_version": SOURCE_002_VARIETY_MASTER_IDENTITY_MAPPING_POLICY_VERSION,
        "entries": [
            {
                "source_variety_business_key": source_key,
                "master_code": identity.code,
                "master_name": identity.name,
            }
            for source_key, identity in source_002_variety_master_identity_mapping_entries()
        ],
    }


def source_002_variety_master_identity_mapping_sha256() -> str:
    """Return the deterministic SHA-256 of the governed mapping payload."""
    return sha256_payload(build_source_002_variety_master_identity_mapping_payload())


def resolve_source_002_master_variety_identity(
    source_variety_business_key: str,
) -> Source002MasterVarietyIdentity | None:
    """Resolve a governed SOURCE-002 variety business key to canonical master identity."""
    return _SOURCE_TO_MASTER.get(source_variety_business_key)


def canonical_master_variety_count() -> int:
    """Return the count of distinct canonical master Variety identities."""
    return len({(identity.code, identity.name) for identity in _SOURCE_TO_MASTER.values()})
