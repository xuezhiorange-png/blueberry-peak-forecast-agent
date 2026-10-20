"""Literal SYNTHETIC rehearsal, not a historical data loader or PIT amendment.

AS_ISSUED_FORECAST and RETROSPECTIVE_REPLAY have separate seals/reports. All
clocks in the demo are explicitly fictional. A late replay keeps its computation
time as issued_at and is rejected by the unchanged S3 scorer, not backdated.
"""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Context, Decimal, localcontext
from typing import Any

from backend.research.v019_daily_curve import (
    BASELINE_POLICY,
    CurveInput,
    DailyKg,
    canonical_bytes,
    generate_candidate,
)
from backend.research.v019_synthetic_validation import (
    AUTHORITIES,
    ERROR_METRICS,
    Authority,
    Labels,
    PredictionSeal,
    Sample,
    _peak,
    digest,
    evaluate_synthetic,
    generate_synthetic_predictions,
)

KINDS = ("AS_ISSUED_FORECAST", "RETROSPECTIVE_REPLAY")


@dataclass(frozen=True)
class ReplayUnit:
    sample: Sample
    curve: CurveInput | None
    prediction_kind: str
    computed_at: datetime


@dataclass(frozen=True)
class PreparationSeal:
    units: tuple[ReplayUnit, ...]
    predictions: PredictionSeal
    raw: bytes
    sha256: str


def prepare_predictions(
    units: tuple[ReplayUnit, ...], *, synthetic_authorized: bool
) -> PreparationSeal:
    """Phase A accepts only registered inputs, never labels or filesystem paths.

    Baseline rows are frozen inputs; the existing S3 generator passes them
    through and invokes the existing S2 candidate, without fitting any model.
    Missing/invalid inputs remain registered failures in C0.
    """
    if not units:
        raise ValueError("REGISTERED_C0_REQUIRED")
    if len({u.prediction_kind for u in units}) != 1:
        raise ValueError("PREDICTION_KINDS_REQUIRE_SEPARATE_REPORTS")
    for unit in units:
        if unit.prediction_kind not in KINDS:
            raise ValueError("UNKNOWN_PREDICTION_KIND")
        if unit.computed_at.utcoffset() is None:
            raise ValueError("COMPUTATION_TIMEZONE_REQUIRED")
        if unit.sample.issued_at != unit.computed_at:
            raise ValueError("COMPUTATION_ISSUANCE_MISMATCH_NO_BACKDATING")
        if unit.sample.origin.utcoffset() is None or unit.computed_at < unit.sample.origin:
            raise ValueError("ORIGIN_TIME_INVALID")
    units = tuple(sorted(units, key=lambda u: u.sample.sample_id))
    predictions = generate_synthetic_predictions(
        tuple(u.sample for u in units),
        {u.sample.sample_id: u.curve for u in units if u.curve is not None},
        synthetic_authorized=synthetic_authorized,
    )
    raw = canonical_bytes(
        {
            "data_class": "SYNTHETIC",
            "prediction_kind": units[0].prediction_kind,
            "registered_inputs_sha256": digest(units),
            "prediction_seal_sha256": predictions.sha256,
            "labels_read": False,
            "clocks_are_synthetic": True,
            "real_replay_protocol_status": "PROPOSED_NOT_EFFECTIVE",
        }
    )
    return PreparationSeal(units, predictions, raw, hashlib.sha256(raw).hexdigest())


def _curve_view(rows: tuple[DailyKg, ...], *, labels: bool = False) -> dict[str, Any]:
    """Presentation of sealed values, reusing the frozen scorer's peak rule."""
    if not rows:
        return {"status": "NOT_COMPUTABLE", "reason": "INCOMPLETE_CALENDAR"}
    day, quantity = _peak(rows, False)
    positive = any(row.kg > 0 for row in rows)
    rolling = None
    if len(rows) >= 7:
        start, mass = _peak(rows, True)
        rolling = {
            "start_date": start.isoformat() if positive or not labels else None,
            "quantity_kg": str(mass),
        }
    return {
        "daily": [{"date": row.day.isoformat(), "kg": str(row.kg)} for row in rows],
        "single_day_peak": {
            "date": day.isoformat() if positive or not labels else None,
            "quantity_kg": str(quantity),
        },
        "rolling7_peak": rolling,
    }


def evaluate_preparation(
    seal: PreparationSeal,
    labels: Iterable[Labels],
    *,
    as_of: datetime,
    synthetic_authorized: bool,
) -> dict[str, Any]:
    """Phase B verifies BOTH seals and inputs before opening the label iterable.

    No timestamp rewriting, alternate metric implementation or replay exemption
    is provided. Late replays keep curves, failures and NOT_COMPUTABLE metrics.
    """
    expected = prepare_predictions(seal.units, synthetic_authorized=synthetic_authorized)
    if expected != seal:
        raise ValueError("PREPARATION_SEAL_MISMATCH")
    label_rows = tuple(labels)
    evaluation = evaluate_synthetic(
        seal.predictions, label_rows, as_of=as_of, synthetic_authorized=synthetic_authorized
    )
    labs = {lab.sample_id: lab for lab in label_rows}
    views = {}
    comparisons = {}
    with localcontext(Context(prec=50)):
        for key, group in evaluation["groups"].items():
            comparisons[key] = {
                name: str(Decimal(m["candidate"]["value"]) - Decimal(m["baseline"]["value"]))
                if m["candidate"]["value"] is not None and m["baseline"]["value"] is not None
                else None
                for name in ERROR_METRICS
                for m in (group["metrics"][name],)
            }
        common = {
            member
            for group in evaluation["groups"].values()
            for member in group["metrics"]["DAILY_MAE"]["common_member_ids"]
        }
        for pair in seal.predictions.pairs:
            views[pair.sample_id] = {
                "baseline": _curve_view(pair.baseline.rows) if pair.baseline else None,
                "candidate": _curve_view(pair.candidate.rows) if pair.candidate else None,
                "labels": _curve_view(labs[pair.sample_id].rows, labels=True)
                if pair.sample_id in common
                else {"status": "NOT_COMPUTABLE"},
                "generation_failure": pair.failure,
            }
    result = {
        "data_class": "SYNTHETIC",
        "prediction_kind": seal.units[0].prediction_kind,
        "preparation_seal_sha256": seal.sha256,
        "evaluation": evaluation,
        "curves_and_peaks": views,
        "paired_error_delta_candidate_minus_baseline": comparisons,
        "clock_provenance": [
            {
                "sample_id": u.sample.sample_id,
                "historical_origin": u.sample.origin.isoformat(),
                "input_cutoff": u.sample.cutoff.isoformat(),
                "computed_at_and_issued_at": u.computed_at.isoformat(),
            }
            for u in seal.units
        ],
        "strict_pit": False,
        "real_data_accessed": False,
        "real_scoring_performed": False,
        "retrospective_real_replay_performed": False,
        "real_replay_protocol_status": "PROPOSED_NOT_EFFECTIVE",
        "s3_formal_complete": False,
    }
    return {**result, "result_sha256": digest(result)}


def demo_units(prediction_kind: str = "AS_ISSUED_FORECAST") -> tuple[ReplayUnit, ...]:
    """Fixed fictional C0, no file/DB/artifact discovery and no actual labels."""
    origin = datetime.fromisoformat("2000-01-01T17:00:00+08:00")
    computed = origin if prediction_kind == "AS_ISSUED_FORECAST" else origin + timedelta(days=366)
    start = date(2000, 1, 2)
    h = digest("SYNTHETIC-SOURCE-AND-AUTHORITY-NOT-A-REAL-RECORD")
    baseline = tuple(
        DailyKg(start + timedelta(days=i), Decimal((10, 30, 5)[i // 7])) for i in range(21)
    )
    curve = CurveInput(
        start, start, baseline[-1].day, baseline, h, BASELINE_POLICY, "Asia/Shanghai"
    )
    input_hash = generate_candidate(curve).input_sha256
    units = []
    for index, (window, n) in enumerate((("H7_PREFIX", 7), ("H15_LOCAL", 15), ("FULL_SEASON", 21))):
        for base in ("A", "B"):
            sample = Sample(
                sample_id=f"SYNTHETIC-{index}-{base}",
                base_id=f"SYNTHETIC-BASE-{base}",
                organization_id="SYNTHETIC-ORG",
                subfarm_id=f"SYNTHETIC-PLOT-{base}",
                variety_id="SYNTHETIC-VARIETY",
                season="SYNTHETIC-SEASON",
                area_mu=Decimal(10),
                area_effective_date=date(1999, 1, 1),
                origin=origin,
                issued_at=computed,
                cutoff=origin,
                input_available_at=origin,
                input_ingested_at=origin,
                dates=tuple(row.day for row in baseline[:n]),
                window=window,
                physical_basis="ACTUAL_HARVEST_KG",
                unit="kg",
                profile_sha256=h,
                input_sha256=input_hash,
                label_authority_sha256=h,
                train_scope_sha256=h,
                split="SYNTHETIC_EXPOSED_HISTORICAL_BENCHMARK",
                full_season_registered=window == "FULL_SEASON",
                authorities=tuple(Authority(name, "AVAILABLE", h) for name in AUTHORITIES),
                comparison_family="SYNTHETIC-REGISTERED-PAIR",
                source_population_sha256=h,
                evaluation_scope_sha256=h,
            )
            units.append(ReplayUnit(sample, curve, prediction_kind, computed))
    return tuple(units)


def demo_labels(seal: PreparationSeal) -> tuple[Labels, ...]:
    """Independent literal synthetic labels, invoked only AFTER Phase A."""
    at = datetime.fromisoformat("2000-02-01T17:00:00+08:00")
    shaped = (8, 8, 8, 8, 11, 13, 14, 20, 25, 30, 35, 40, 35, 25, 7, 6, 5, 4, 3, 4, 6)
    out = []
    for unit in seal.units:
        sample = unit.sample
        values = shaped if sample.base_id.endswith("A") else (10,) * 7 + (30,) * 7 + (5,) * 7
        rows = tuple(
            DailyKg(day, Decimal(value))
            for day, value in zip(sample.dates, values[: len(sample.dates)], strict=True)
        )
        out.append(
            Labels(
                sample.sample_id,
                sample.identity_sha256,
                sample.label_authority_sha256,
                rows,
                at,
                at,
                True,
            )
        )
    return tuple(out)


def demo() -> dict[str, Any]:
    """Both lanes: computable synthetic control AND blocked late replay."""
    reports = {}
    at = datetime.fromisoformat("2002-01-01T17:00:00+08:00")
    for kind in KINDS:
        seal = prepare_predictions(demo_units(kind), synthetic_authorized=True)
        reports[kind] = evaluate_preparation(
            seal, demo_labels(seal), as_of=at, synthetic_authorized=True
        )
    return {"data_class": "SYNTHETIC", "reports": reports}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", required=True)
    parser.parse_args()
    print(canonical_bytes(demo()).decode(), end="")


if __name__ == "__main__":
    main()
