"""Executable closed-SYNTHETIC retrospective engine. No real execution switch.

Stage A has no label argument/import. The baseline's existing area/profile
calculator and sole S2 candidate operate on the same full calendar, then slice.
Simulation permits are deliberately NOT Owner approvals or real C0 admission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any, NoReturn

from backend.app.forecast_quality.operational_peak import (
    BASELINE_ID,
    MISSING_BIN_POLICY,
    RegisteredBase,
    _daily_row,
    load_frozen_reference_profile,
)
from backend.research import v019_synthetic_validation as math
from backend.research.v019_daily_curve import (
    CurveInput,
    DailyKg,
    canonical_bytes,
    generate_candidate,
    method_config,
)

ROOT = Path(__file__).resolve().parents[2]
START, END = date(2000, 7, 1), date(2000, 7, 21)
FIXTURES = ("DEFAULT", "CLEAN", "ZERO_ACTUAL", "MISSING_LABEL", "INVALID_LABEL", "INVALID_PROFILE")
# Identity of the separately committed literal fixture payload, not its values.
LABEL_PAYLOAD_SHA256 = "19a233d721a63e1317651c166e74b0975aeca308fb91ee21cf585afac9fdc926"


def generate_real_predictions(*args: object, **kwargs: object) -> NoReturn:
    raise PermissionError(
        "REAL_PHASE_A_EXECUTION_DISABLED_SEPARATE_IMPLEMENTATION_AND_AUTH_REQUIRED"
    )


@dataclass(frozen=True)
class Experiment:
    experiment_id: str = "SYNTHETIC-RETROSPECTIVE-ENGINE-R1"
    fixture: str = "DEFAULT"
    data_class: str = "SYNTHETIC"
    computed_at: str = "2002-01-01T00:00:00+00:00"
    score_at: str = "2003-01-01T00:00:00+00:00"


@dataclass(frozen=True)
class SimulationPermit:
    phase: str
    object_sha256: str
    data_class: str = "SYNTHETIC"


@dataclass(frozen=True)
class Candidates:
    experiment: Experiment
    samples: tuple[math.Sample, ...]
    raw: bytes
    sha256: str


@dataclass(frozen=True)
class AdmittedC0:
    candidates: Candidates
    raw: bytes
    sha256: str


@dataclass(frozen=True)
class PhaseASeal:
    c0: AdmittedC0
    predictions: math.PredictionSeal
    full_curves: dict[str, dict[str, tuple[DailyKg, ...]]]
    failures: tuple[dict[str, str], ...]
    raw: bytes
    sha256: str


def _permit(value: object, phase: str, sha256: str) -> None:
    if (
        type(value) is not SimulationPermit
        or value.phase != phase
        or value.object_sha256 != sha256
        or value.data_class != "SYNTHETIC"
    ):
        raise PermissionError("EXACT_SEPARATE_SYNTHETIC_PHASE_PERMISSION_REQUIRED_REAL_DISABLED")


def _validate(e: Experiment) -> None:
    if (
        type(e) is not Experiment
        or e.data_class != "SYNTHETIC"
        or e.fixture not in FIXTURES
        or e.experiment_id != "SYNTHETIC-RETROSPECTIVE-ENGINE-R1"
    ):
        raise PermissionError("CLOSED_SYNTHETIC_REGISTRY_ONLY_REAL_DISABLED")
    computed, score = datetime.fromisoformat(e.computed_at), datetime.fromisoformat(e.score_at)
    if (
        computed.utcoffset() is None
        or score.utcoffset() is None
        or computed.date() <= END
        or score < computed
    ):
        raise ValueError("EXPLICIT_LATE_SIMULATED_CLOCKS_REQUIRED_NO_BACKDATING")


def _source_identity() -> dict[str, str]:
    # Do not read/import the separate label fixture here, even to hash it.
    return {
        p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        for p in (
            "backend/research/v019_retrospective_engine.py",
            "backend/research/v019_retrospective_scoring.py",
            "backend/research/v019_daily_curve.py",
            "backend/research/v019_synthetic_validation.py",
            "backend/research/v019_owner_scope_adapter.py",
            "backend/app/forecast_quality/operational_peak.py",
        )
    }


def _profile() -> dict[str, Any]:
    return {
        "reference_id": BASELINE_ID,
        "fold_id": "B",
        "validation_labels_used": False,
        "missing_bin_policy": MISSING_BIN_POLICY,
        "profile_kg_per_mu_by_7_day_bin": {"0": "1", "1": "3", "2": "0.5"},
        "identity": "SYNTHETIC_PROFILE_NOT_REAL_REFERENCE_B",
    }


def _bases() -> tuple[RegisteredBase, ...]:
    return tuple(
        RegisteredBase(f"SYNTHETIC-BASE-{key}", f"SYNTHETIC-{key}", Decimal(area))
        for key, area in (("A", "10"), ("B", "20"), ("C", "5"), ("D", "10"))
    )


def _registered_profile(base: RegisteredBase, fixture: str) -> dict[str, Any]:
    payload = _profile()
    if base.base_id.endswith("D") and fixture == "INVALID_PROFILE":
        return {**payload, "validation_labels_used": True}
    return payload


def nominate(experiment: Experiment) -> Candidates:
    """Register all inputs and failures before A; no labels/curve calculation."""
    _validate(experiment)
    population = math.digest("SYNTHETIC-REGISTERED-POPULATION-V1")
    label_hash = math.digest({"payload": LABEL_PAYLOAD_SHA256, "variant": experiment.fixture})
    samples = []
    for b in _bases():
        profile_hash = math.digest(_registered_profile(b, experiment.fixture))
        requests = [("H7_PREFIX", 7, d) for d in (date(2000, 7, 3), date(2000, 7, 6))]
        requests += [("H15_LOCAL", 15, d) for d in (date(2000, 7, 3), date(2000, 7, 6))]
        # Separate complete FICTIONAL calendar control, not real season admission.
        requests += [("FULL_SEASON", 21, START - timedelta(days=1))]
        for window, n, origin_day in requests:
            origin = datetime.fromisoformat(f"{origin_day}T23:59:59+08:00")
            samples.append(
                math.Sample(
                    sample_id=f"{b.base_id}-{window}-{origin_day}",
                    base_id=b.base_id,
                    organization_id="SYNTHETIC-ORG",
                    subfarm_id="SYNTHETIC-SUBFARM",
                    variety_id="SYNTHETIC-VARIETY",
                    season="SYNTHETIC-SEASON-2000",
                    area_mu=b.productive_area_mu,
                    area_effective_date=date(1999, 1, 1),
                    origin=origin,
                    issued_at=datetime.fromisoformat(experiment.computed_at),
                    cutoff=origin,
                    input_available_at=origin,
                    input_ingested_at=origin,
                    dates=tuple(origin_day + timedelta(days=i + 1) for i in range(n)),
                    window=window,
                    physical_basis="ACTUAL_HARVEST_KG",
                    unit="kg",
                    profile_sha256=profile_hash,
                    input_sha256=math.digest(
                        {
                            "base": b,
                            "profile": profile_hash,
                            "support": [START, END],
                            "input_available": not (
                                b.base_id.endswith("D") and experiment.fixture == "DEFAULT"
                            ),
                        }
                    ),
                    label_authority_sha256=label_hash,
                    train_scope_sha256=population,
                    split="SYNTHETIC_COMPLETE_CALENDAR_CONTROL"
                    if window == "FULL_SEASON"
                    else "RETROSPECTIVE_REPLAY",
                    full_season_registered=window == "FULL_SEASON",
                    authorities=tuple(
                        math.Authority(k, "AVAILABLE", population) for k in math.AUTHORITIES
                    ),
                    comparison_family="SYNTHETIC-RETROSPECTIVE-FROZEN-V1",
                    source_population_sha256=population,
                    evaluation_scope_sha256=population,
                )
            )
    units = tuple(sorted(samples, key=lambda s: s.sample_id))
    body = {
        "data_class": "SYNTHETIC",
        "experiment": asdict(experiment),
        "profile": _profile(),
        "registered_profiles": {
            b.base_id: _registered_profile(b, experiment.fixture) for b in _bases()
        },
        "input_availability": {
            b.base_id: not (b.base_id.endswith("D") and experiment.fixture == "DEFAULT")
            for b in _bases()
        },
        "bases": math._json(_bases()),
        "support": [str(START), str(END)],
        "members": math._json(units),
        "method_config": method_config(),
        "source_code_sha256": _source_identity(),
        "label_payload_sha256": LABEL_PAYLOAD_SHA256,
        "labels_opened": False,
        "real_formally_admitted_c0_count": 0,
    }
    raw = canonical_bytes(body)
    return Candidates(experiment, units, raw, hashlib.sha256(raw).hexdigest())


def admit(candidates: Candidates, *, permit: object = None) -> AdmittedC0:
    _permit(permit, "C0", candidates.sha256)
    if nominate(candidates.experiment) != candidates:
        raise ValueError("C0_IDENTITY_MEMBERSHIP_OR_SOURCE_MISMATCH")
    raw = canonical_bytes(
        {
            "candidate_sha256": candidates.sha256,
            "status": "ADMITTED_SYNTHETIC_SIMULATION_ONLY",
            "synthetic_member_count": len(candidates.samples),
            "real_formally_admitted_c0_count": 0,
        }
    )
    return AdmittedC0(candidates, raw, hashlib.sha256(raw).hexdigest())


def generate(c0: AdmittedC0, *, permit: object = None) -> PhaseASeal:
    """Actual profile×area baseline, sole S2 transformation, then H7/H15 cuts."""
    _permit(permit, "A", c0.sha256)
    expected = admit(c0.candidates, permit=SimulationPermit("C0", c0.candidates.sha256))
    if expected != c0:
        raise ValueError("C0_ADMISSION_SEAL_MISMATCH")
    full: dict[str, dict[str, tuple[DailyKg, ...]]] = {}
    errors: dict[str, str] = {}
    with localcontext(Context(prec=50)):
        for base in _bases():
            try:
                if base.base_id.endswith("D") and c0.candidates.experiment.fixture == "DEFAULT":
                    raise ValueError("MISSING_REGISTERED_INPUT")
                payload = _registered_profile(base, c0.candidates.experiment.fixture)
                profile = load_frozen_reference_profile(payload)
                old = tuple(
                    DailyKg(
                        day, _daily_row(day, START, base.productive_area_mu, profile).predicted_kg
                    )
                    for day in (START + timedelta(days=i) for i in range(21))
                )
                request = CurveInput(
                    START, START, END, old, math.digest(_profile()), BASELINE_ID, "Asia/Shanghai"
                )
                candidate = generate_candidate(request)
                full[base.base_id] = {"baseline": old, "candidate": candidate.rows}
            except ValueError as exc:
                errors[base.base_id] = str(exc)
    pairs = []
    failures = []
    for s in c0.candidates.samples:
        if s.base_id in errors:
            reason = errors[s.base_id]
            pairs.append(math.Pair(s.sample_id, None, None, reason))
            failures.append({"sample_id": s.sample_id, "base_id": s.base_id, "reason": reason})
            continue
        forecasts = []
        for key, model in (("baseline", math.BASELINE), ("candidate", math.CANDIDATE)):
            all_rows = full[s.base_id][key]
            lookup = {r.day: r for r in all_rows}
            fit = s.profile_sha256 if key == "baseline" else math.digest(method_config())
            forecasts.append(
                math.Forecast(
                    model,
                    s.identity_sha256,
                    fit,
                    math.digest(all_rows),
                    tuple(lookup[d] for d in s.dates),
                )
            )
        pairs.append(math.Pair(s.sample_id, forecasts[0], forecasts[1]))
    predictions = math.freeze_predictions(
        c0.candidates.samples, tuple(pairs), synthetic_authorized=True
    )
    body = {
        "data_class": "SYNTHETIC",
        "experiment_type": "RETROSPECTIVE_REPLAY",
        "clock_provenance": "EXPLICIT_SIMULATED_CLOCK_NOT_HISTORICAL_ISSUANCE",
        "experiment": asdict(c0.candidates.experiment),
        "c0_sha256": c0.sha256,
        "candidate_registration": json.loads(c0.candidates.raw),
        "admission": json.loads(c0.raw),
        "predictions": json.loads(predictions.raw),
        "full_curves": math._json(full),
        "failures": failures,
        "labels_opened": False,
        "strict_pit": False,
    }
    raw = canonical_bytes(body)
    return PhaseASeal(c0, predictions, full, tuple(failures), raw, hashlib.sha256(raw).hexdigest())


def verify(seal: PhaseASeal) -> None:
    if type(seal) is not PhaseASeal:
        raise ValueError("PHASE_A_SEAL_REQUIRED")
    expected = generate(seal.c0, permit=SimulationPermit("A", seal.c0.sha256))
    if seal != expected:
        raise ValueError("PHASE_A_SEAL_OR_SOURCE_MISMATCH")


def envelope(seal: PhaseASeal) -> dict[str, Any]:
    return {"sha256": seal.sha256, "payload": json.loads(seal.raw)}


def load_seal(path: Path) -> PhaseASeal:
    """Explicit bounded synthetic artifact; no arbitrary input/profile loader."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 4_000_000:
            raise ValueError("INVALID_SEAL_FILE")
        raw = f.read(4_000_001)

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for k, v in items:
            if k in result:
                raise ValueError("DUPLICATE_SEAL_FIELD")
            result[k] = v
        return result

    value = json.loads(raw, object_pairs_hook=pairs)
    config = value["payload"]["experiment"]
    c0 = nominate(Experiment(**config))
    admission = admit(c0, permit=SimulationPermit("C0", c0.sha256))
    seal = generate(admission, permit=SimulationPermit("A", admission.sha256))
    if value != envelope(seal):
        raise ValueError("PHASE_A_SEAL_OR_SOURCE_MISMATCH")
    return seal


def _write_bundle(output: Path, files: dict[str, bytes]) -> dict[str, str]:
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    hashes = {}
    for name, raw in files.items():
        fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    manifest = {
        "data_class": "SYNTHETIC",
        "actual_process_completed_at": datetime.now(UTC).isoformat(),
        "file_sha256": hashes,
        "real_prediction_generated": False,
        "real_scoring_performed": False,
    }
    fd = os.open(output / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(canonical_bytes(manifest))
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("demo", "stage-a", "stage-b"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", choices=FIXTURES, default="DEFAULT")
    parser.add_argument("--seal", type=Path)
    args = parser.parse_args()
    if args.command == "stage-b":
        if args.seal is None:
            parser.error("stage-b requires --seal")
        seal = load_seal(args.seal)
    else:
        candidates = nominate(Experiment(fixture=args.fixture))
        c0 = admit(candidates, permit=SimulationPermit("C0", candidates.sha256))
        seal = generate(c0, permit=SimulationPermit("A", c0.sha256))
    files = {
        "c0-candidates.json": seal.c0.candidates.raw,
        "synthetic-c0-admission.json": seal.c0.raw,
        "phase-a.json": canonical_bytes(envelope(seal)),
    }
    if args.command in ("demo", "stage-b"):
        from backend.research.v019_retrospective_scoring import render, score

        report = score(seal, permit=SimulationPermit("B", seal.sha256))
        files.update({"report.json": canonical_bytes(report), **render(report)})
    hashes = _write_bundle(args.output, files)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "phase_a_sha256": seal.sha256,
                "files": hashes,
                "data_class": "SYNTHETIC",
                "real_execution": "BLOCKED",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    # Keep exact-type permit checks intact across -m and imported Phase B.
    from backend.research.v019_retrospective_engine import main as entrypoint

    entrypoint()
