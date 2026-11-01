"""Synthetic-only standalone entry points; no real-source or model admission."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from backend.app.etl.history import synthetic_publication as publication
from backend.research.v019_daily_curve import (
    BASELINE_POLICY,
    CurveInput,
    DailyKg,
    canonical_bytes,
    generate_candidate,
    select_window,
)

IDENTITY = "TD01G_SYNTHETIC_EXECUTABLE_CORE_V1"
LIMITS = {
    "DATA_CLASS": "SYNTHETIC_ONLY",
    "REAL_FORECAST_VALIDATED": False,
    "STRICT_REAL_PIT_VALIDATED": False,
    "PRODUCTION_MODEL_ADMITTED": False,
}


def _write(path: Path, payload: object) -> str:
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as file:
        file.write(raw)
    return hashlib.sha256(raw).hexdigest()


def generate(seed: int, destination: Path, *, real_source: Path | None = None) -> dict[str, object]:
    # Existing producer refuses non-generated inputs before exists/open/hash.
    package = publication.generate(seed, source_path=real_source)
    hashes = publication.export(package, destination)
    counts = Counter(reason for row in package.rows for reason in row.issues)
    for season in sorted({row.season for row in package.rows}):
        prefix = "SYNTHETIC_ONLY_" + season.replace("-", "_")
        publication.check_csv((destination / (prefix + ".csv")).read_bytes(), package, season)
        publication.check_xlsx((destination / (prefix + ".xlsx")).read_bytes(), package, season)
    report = {
        **LIMITS,
        "contract": IDENTITY,
        "seed": seed,
        "source_identity": package.source_identity,
        "quantity_basis": "SYNTHETIC_DECLARED_LEGACY_RECEIPT_KG",
        "formal_source_admitted": False,
        "row_count": len(package.rows),
        "seasons": sorted({row.season for row in package.rows}),
        "quality_reasons": dict(sorted(counts.items())),
        "generated_file_sha256": hashes,
    }
    _write(destination / "quality-report.json", report)
    return report


def curve(seed: int) -> dict[str, object]:
    # The seed's legality is inherited from the frozen independent generator.
    publication.generate(seed)
    rng = random.Random(seed)
    start = date(2040, 7, 1)
    micros = [rng.randrange(0, 9_000_001) for _ in range(4)]
    rates = [Decimal(f"{q // 1_000_000}.{q % 1_000_000:06d}") for q in micros]
    rows = tuple(DailyKg(start + timedelta(days=i), rates[i // 7]) for i in range(28))
    source = {"data_class": "SYNTHETIC_ONLY", "seed": seed, "rates": [str(r) for r in rates]}
    request = CurveInput(
        season_start=start,
        support_start=start,
        support_end=rows[-1].day,
        baseline=rows,
        baseline_source_sha256=hashlib.sha256(canonical_bytes(source)).hexdigest(),
        baseline_policy=BASELINE_POLICY,
        timezone="Asia/Shanghai",
    )
    result = generate_candidate(request)
    repeated = generate_candidate(request)
    origin = start + timedelta(days=2)
    h15 = select_window(result, origin=origin, horizon=15)
    h7 = select_window(result, origin=origin, horizon=7)
    checks = {
        "deterministic": result == repeated,
        "nonnegative_six_decimal_kg": all(
            r.kg >= 0 and r.kg.as_tuple().exponent == -6 for r in result.rows
        ),
        "continuous_dates": all(
            row.day == start + timedelta(days=i) for i, row in enumerate(result.rows)
        ),
        "bin_mass_conserved": all(b.baseline_micro_kg == b.candidate_micro_kg for b in result.bins),
        "h7_is_h15_prefix": h7 == h15[:7],
    }
    if not all(checks.values()):
        raise ValueError("FROZEN_DAILY_CURVE_CONTRACT_FAILED")
    return {
        **LIMITS,
        "contract": IDENTITY,
        "seed": seed,
        "origin": origin.isoformat(),
        "result_sha256": result.result_sha256,
        "invariants": checks,
        "daily": [
            {"date": row.day.isoformat(), "kg": format(row.kg, ".6f")} for row in result.rows
        ],
        "h7": [{"date": row.day.isoformat(), "kg": format(row.kg, ".6f")} for row in h7],
        "h15": [{"date": row.day.isoformat(), "kg": format(row.kg, ".6f")} for row in h15],
    }


def execute(seed: int, destination: Path, *, real_source: Path | None = None) -> dict[str, str]:
    if real_source is not None:
        publication.generate(seed, source_path=real_source)
    daily = curve(seed)
    quality = generate(seed, destination)
    hashes = {
        "quality-report.json": hashlib.sha256(
            (destination / "quality-report.json").read_bytes()
        ).hexdigest(),
        "daily-curve-report.json": _write(destination / "daily-curve-report.json", daily),
    }
    _write(
        destination / "public-core-run.json",
        {**LIMITS, "report_sha256": hashes, "source_identity": quality["source_identity"]},
    )
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "curve", "demo"])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", choices=[IDENTITY], default=IDENTITY)
    parser.add_argument("--source", type=Path, help="always refused; no real source reader")
    args = parser.parse_args()
    if args.source is not None:
        publication.generate(args.seed, source_path=args.source)
    if args.command == "generate":
        result: object = generate(args.seed, args.output_dir)
    elif args.command == "curve":
        data = curve(args.seed)
        args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        result = {"report_sha256": _write(args.output_dir / "daily-curve-report.json", data)}
    else:
        result = execute(args.seed, args.output_dir)
    print(json.dumps({**LIMITS, "result": result}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
