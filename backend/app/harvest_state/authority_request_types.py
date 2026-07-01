from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.app.harvest_state.enums import AuthorityFamily
from backend.app.harvest_state.schemas import ParameterSourceRef, Task9ARequest


@dataclass(frozen=True, slots=True)
class ResolvedAuthorityBinding:
    authority_family: AuthorityFamily
    authority_id: int
    authority_stable_key: str
    business_version: str
    revision: int
    row_hash: str


@dataclass(frozen=True, slots=True)
class Task9AuthorityRequestAssembly:
    request: Task9ARequest
    authority_manifest: tuple[ResolvedAuthorityBinding, ...]
    parameter_source_refs: tuple[ParameterSourceRef, ...]
    canonical_payload: dict[str, object]
    assembly_hash: str


@dataclass(frozen=True, slots=True)
class Task9AuthorityAssemblyWindow:
    as_of_date: date
    forecast_start_date: date
    forecast_end_date: date
