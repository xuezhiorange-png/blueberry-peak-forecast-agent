"""Hermetic SYNTHETIC research entry; no real loader or retrospective PIT waiver.

The real-source nomination is metadata, never a formal C0. Executable inputs
are exclusively the built-in fictional fixtures from the reviewed S3 rehearsal.
A synthetic permit is not an Owner authorization or a security credential.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

from backend.research.v019_daily_curve import canonical_bytes, method_config
from backend.research.v019_replay_preparation import (
    KINDS,
    PreparationSeal,
    ReplayUnit,
    demo_labels,
    demo_units,
    evaluate_preparation,
    prepare_predictions,
)
from backend.research.v019_synthetic_validation import BASELINE, CANDIDATE, digest

PROTOCOL = "PROPOSED_NOT_EFFECTIVE"
FIXTURES = ("PAIR", "MISSING_INPUT", "UNVERIFIED_PHYSICAL_BASIS")
REAL_BLOCKERS = (
    "REAL_EXECUTION_NOT_AUTHORIZED",
    "UNRESOLVED_FARM_IMPACT",
    "PHYSICAL_BASIS_NOT_VERIFIED",
    "HISTORICAL_INPUT_KNOWLEDGE_NOT_PROVEN",
    "LATE_REPLAY_FAILS_EXISTING_ISSUANCE_GATE",
)


@dataclass(frozen=True)
class CandidateScope:
    """Owner-supplied nomination facts; no private names, areas or quantities."""

    source_id: str = "SOURCE_002"
    source_sha256: str = "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a"
    season: str = "2025-2026"
    start: str = "2025-08-05"
    end: str = "2026-04-15"
    candidate_bases: int = 39
    matched_farms: int = 75
    unresolved_farms: int = 9
    historical_area_bases: int = 39
    h7_structural_max: int = 9672
    h15_structural_max: int = 9360
    full_season_admitted: int = 0
    physical_basis_equivalence: str = "NOT_VERIFIED"
    historical_area_known_at: str = "NOT_PROVEN"
    unresolved_disposition: str = "BLOCKED_NOT_MAPPED_NOT_EXCLUDED"

    def validate(self) -> None:
        expected = asdict(CandidateScope())
        actual = asdict(self)
        if actual != expected or any(type(actual[k]) is not type(v) for k, v in expected.items()):
            raise ValueError("SOURCE_NOMINATION_CHANGED_NOT_AN_APPROVAL")
        days = (date.fromisoformat(self.end) - date.fromisoformat(self.start)).days + 1
        if (days - 6) * self.candidate_bases != self.h7_structural_max:
            raise ValueError("H7_STRUCTURAL_BOUND_INVALID")
        if (days - 14) * self.candidate_bases != self.h15_structural_max:
            raise ValueError("H15_STRUCTURAL_BOUND_INVALID")


@dataclass(frozen=True)
class Registration:
    experiment_id: str
    kind: str = "RETROSPECTIVE_REPLAY"
    fixture: str = "PAIR"
    data_class: str = "SYNTHETIC"
    protocol_status: str = PROTOCOL
    strict_pit: bool = False
    production_eligible: bool = False
    synthetic_clock: bool = True


@dataclass(frozen=True)
class SyntheticPermit:
    phase: str
    enabled: bool = True
    data_class: str = "SYNTHETIC"


@dataclass(frozen=True)
class FrozenC0:
    registration: Registration
    units: tuple[ReplayUnit, ...]
    raw: bytes
    sha256: str


@dataclass(frozen=True)
class ResearchSeal:
    c0: FrozenC0
    preparation: PreparationSeal
    raw: bytes
    sha256: str


def _permit(value: object, phase: str) -> None:
    # No boolean/string/dict coercion and no switch that grants real execution.
    if (
        type(value) is not SyntheticPermit
        or value.phase != phase
        or value.enabled is not True
        or value.data_class != "SYNTHETIC"
    ):
        raise PermissionError("SEPARATE_SYNTHETIC_PHASE_PERMISSION_REQUIRED_REAL_DISABLED")


def _validate_registration(value: Registration) -> None:
    if (
        type(value) is not Registration
        or value.data_class != "SYNTHETIC"
        or value.protocol_status != PROTOCOL
        or value.strict_pit is not False
        or value.production_eligible is not False
        or value.synthetic_clock is not True
    ):
        raise PermissionError("SYNTHETIC_ONLY_REAL_PROTOCOL_NOT_EFFECTIVE")
    if (
        not isinstance(value.experiment_id, str)
        or not value.experiment_id.startswith("SYNTHETIC-")
        or not 11 <= len(value.experiment_id) <= 128
        or any(not (c.isascii() and (c.isalnum() or c in "-_")) for c in value.experiment_id)
        or value.kind not in KINDS
        or value.fixture not in FIXTURES
    ):
        raise ValueError("INVALID_SYNTHETIC_REGISTRATION")


def _source_identity() -> dict[str, str]:
    """Seal current executable sources, not an immutable future-worktree test."""
    root = Path(__file__).resolve().parent
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in (
            "v019_daily_curve.py",
            "v019_synthetic_validation.py",
            "v019_replay_preparation.py",
            "v019_retrospective_entry.py",
        )
    }


def _fixture_units(registration: Registration) -> tuple[ReplayUnit, ...]:
    # Literal 2000-era data. There is deliberately no path, raw curve, real
    # artifact or caller-supplied label argument anywhere in the public entry.
    units = tuple(
        replace(unit, sample=replace(unit.sample, full_season_registered=False))
        for unit in demo_units(registration.kind)
        if unit.sample.window in {"H7_PREFIX", "H15_LOCAL"}
    )
    if registration.fixture == "MISSING_INPUT":
        units = tuple(
            replace(unit, curve=None) if unit.sample.base_id.endswith("B") else unit
            for unit in units
        )
    elif registration.fixture == "UNVERIFIED_PHYSICAL_BASIS":
        units = tuple(
            replace(unit, sample=replace(unit.sample, physical_basis="UNVERIFIED_PHYSICAL_BASIS"))
            for unit in units
        )
    return tuple(sorted(units, key=lambda unit: unit.sample.sample_id))


def register_synthetic(registration: Registration) -> FrozenC0:
    """Freeze C0 before labels; real nomination cannot become accepted members."""
    _validate_registration(registration)
    scope = CandidateScope()
    scope.validate()
    units = _fixture_units(registration)
    body = {
        "registration": asdict(registration),
        "real_source_nomination_not_data_authority": asdict(scope),
        "real_candidate_admission": "BLOCKED_NOT_FORMAL_C0",
        "real_blockers": REAL_BLOCKERS,
        "baseline": BASELINE,
        "candidate": CANDIDATE,
        "candidate_count": 1,
        "profile_fold": "B",
        "profile_identity": "SYNTHETIC_FIXTURE_NOT_REAL_FOLD_B_ARTIFACT",
        "source_code_sha256": _source_identity(),
        "config_sha256": digest(method_config()),
        "member_identity_sha256": digest(tuple(unit.sample.identity_sha256 for unit in units)),
        "registered_inputs_sha256": digest(units),
        "members": [
            {
                "sample_id": unit.sample.sample_id,
                "identity_sha256": unit.sample.identity_sha256,
                "window": unit.sample.window,
                "dates": [day.isoformat() for day in unit.sample.dates],
                "pre_registered_failure": "MISSING_REGISTERED_INPUT"
                if unit.curve is None
                else None,
            }
            for unit in units
        ],
        "labels_opened": False,
    }
    raw = canonical_bytes(body)
    return FrozenC0(registration, units, raw, hashlib.sha256(raw).hexdigest())


def _verify_c0(c0: FrozenC0) -> None:
    if type(c0) is not FrozenC0 or register_synthetic(c0.registration) != c0:
        raise ValueError("C0_SEAL_MISMATCH")


def generate_synthetic(c0: FrozenC0, *, permit: object = None) -> ResearchSeal:
    """Stage A: the existing baseline pass-through and sole S2 transformation."""
    _permit(permit, "A")
    _verify_c0(c0)
    prepared = prepare_predictions(c0.units, synthetic_authorized=True)
    raw = canonical_bytes(
        {
            "c0_sha256": c0.sha256,
            "prediction_seal_sha256": prepared.sha256,
            "experiment_type": c0.registration.kind,
            "clock_provenance": "EXPLICIT_SIMULATED_CLOCK",
            "labels_opened": False,
            "protocol_status": PROTOCOL,
        }
    )
    return ResearchSeal(c0, prepared, raw, hashlib.sha256(raw).hexdigest())


def score_synthetic(seal: ResearchSeal, *, permit: object = None) -> dict[str, Any]:
    """Stage B: separate permit and both seals BEFORE opening literal labels.

    Late retrospective units remain NOT_COMPUTABLE under the unchanged S3
    temporal gate. A separately named fictional AS_ISSUED lane tests arithmetic.
    No acceptance of external labels or real authorization flags is provided.
    """
    _permit(permit, "B")
    if type(seal) is not ResearchSeal:
        raise ValueError("PREDICTION_SEAL_REQUIRED")
    expected = generate_synthetic(seal.c0, permit=SyntheticPermit("A"))
    if seal != expected:
        raise ValueError("PREDICTION_SEAL_MISMATCH")
    labels = demo_labels(seal.preparation)
    result = evaluate_preparation(
        seal.preparation,
        labels,
        as_of=datetime.fromisoformat("2002-01-01T17:00:00+08:00"),
        synthetic_authorized=True,
    )
    body = {
        "experiment_type": seal.c0.registration.kind,
        "historical_status": "EXPOSED_HISTORICAL_BENCHMARK"
        if seal.c0.registration.kind == "RETROSPECTIVE_REPLAY"
        else "SYNTHETIC_POSITIVE_CONTROL_NOT_REAL_ISSUANCE",
        "clock_provenance": "EXPLICIT_SIMULATED_CLOCK",
        "data_class": "SYNTHETIC",
        "protocol_status": PROTOCOL,
        "strict_pit": False,
        "production_eligible": False,
        "c0_sha256": seal.c0.sha256,
        "prediction_sha256": seal.sha256,
        "real_data_accessed": False,
        "real_prediction_generated": False,
        "real_scoring_performed": False,
        "result": result,
    }
    return {**body, "report_sha256": digest(body)}


def demo() -> dict[str, Any]:
    reports = {}
    for kind in KINDS:
        c0 = register_synthetic(Registration("SYNTHETIC-EXPERIMENT-R1", kind))
        seal = generate_synthetic(c0, permit=SyntheticPermit("A"))
        reports[kind] = score_synthetic(seal, permit=SyntheticPermit("B"))
    return {"data_class": "SYNTHETIC", "real_scoring_performed": False, "reports": reports}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", required=True)
    parser.parse_args()
    print(canonical_bytes(demo()).decode(), end="")


if __name__ == "__main__":
    main()
