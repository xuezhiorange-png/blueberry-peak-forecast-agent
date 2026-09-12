"""Read authorized XLS, compare provenance, and stop before fit if no eligible pairs."""

import argparse
from pathlib import Path

from backend.app.area_yield import shape_r3 as s
from backend.app.area_yield.experiment import file_hash, read_json, write_csv, write_json


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train-xls", required=True, type=Path)
    p.add_argument("--validation-xls", required=True, type=Path)
    p.add_argument("--repo-source", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    a.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    config = read_json(Path("configs/shape_experiment_r3.json"))
    write_json(a.output / "experiment_config.json", config)
    old = [
        Path("/Users/charles/Documents/blueberry-area-yield-artifacts") / n
        for n in ("area-yield-r1", "area-curve-r2")
    ]
    before = {str(f): file_hash(f) for root in old for f in sorted(root.rglob("*")) if f.is_file()}
    write_json(a.output / "r1_r2_snapshot.json", before)
    hashes = [
        "8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20",
        "f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6",
        "a55cbf259f52e6a20e30d646b43d2aa0f104f60786d725dbc051e46c76b390d5",
    ]
    sources = [
        s.parse_source(path, h)
        for path, h in zip((a.train_xls, a.validation_xls, a.repo_source), hashes, strict=True)
    ]
    comparison = s.overlap(sources[1], sources[2])
    write_json(
        a.output / "input_manifest.json",
        {"sources": [v["profile"] for v in sources], "overlap": comparison},
    )
    inventories = [
        s.inventory(src, season, config)
        for src, season in zip(sources[:2], ("2023-2024", "2024-2025"), strict=True)
    ]
    write_csv(a.output / "farm_season_inventory.csv", inventories[0] + inventories[1])
    tables = [{r["farm"]: r for r in inv} for inv in inventories]
    pairs = []
    for farm in sorted(tables[0].keys() | tables[1].keys()):
        t, v = tables[0].get(farm), tables[1].get(farm)
        pairs.append(
            {
                "canonical_farm": farm,
                "season_23_24_available": t is not None,
                "season_24_25_available": v is not None,
                "23_24_completeness": t["completeness_status"] if t else "ABSENT",
                "24_25_completeness": v["completeness_status"] if v else "ABSENT",
                "match_status": "EXACT_LABEL" if farm else "AMBIGUOUS",
                "eligible_cross_season": bool(
                    farm and t and v and t["eligible_train"] and v["eligible_validation"]
                ),
            }
        )
    write_csv(a.output / "paired_farm_seasons.csv", pairs)
    eligible = sum(r["eligible_cross_season"] for r in pairs)
    if eligible:
        raise RuntimeError(
            "Eligible sources require reviewed execution integration; no implicit run"
        )
    # Preserve observed quantities; unknown calendar days have empty values, never inferred zeros.
    daily_rows = []
    for source, season in zip(sources[:2], ("2023-2024", "2024-2025"), strict=True):
        from collections import defaultdict
        from decimal import Decimal

        daily = defaultdict(Decimal)
        for r in source["rows"]:
            if r["date"] is not None and r["quantity"] is not None:
                daily[(r["farm"], r["date"])] += r["quantity"]
        for farm in sorted({r["farm"] for r in source["rows"]}):
            for day in s.season_calendar(season):
                known = (farm, day) in daily
                daily_rows.append(
                    {
                        "canonical_farm_id": farm,
                        "season_id": season,
                        "date": str(day),
                        "daily_harvest_kg": str(daily[(farm, day)]) if known else "",
                        "season_total_kg": "",
                        "daily_share": "",
                        "observation_status": "OBSERVED_UNQUALIFIED"
                        if known
                        else "UNKNOWN_MISSING",
                        "curve_eligibility": "NOT_NORMALIZED_INCOMPLETE_AUTHORITY",
                    }
                )
    write_csv(a.output / "canonical_daily_shape.csv", daily_rows)
    status = {
        "result": "BLOCKED_NO_CROSS_SEASON_MATCHED_SCOPE",
        "blocker": "NO_COMPLETENESS_QUALIFIED_PAIRED_FARM_SEASON",
        "raw_exact_label_pair_count": sum(
            bool(
                r["canonical_farm"] and r["season_23_24_available"] and r["season_24_25_available"]
            )
            for r in pairs
        ),
        "eligible_cross_season_farm_count": eligible,
        "trained_models": [],
        "training_executed": False,
        "validation_executed": False,
        "selected_model": None,
        "legacy_test_accessed": False,
        "validation_blindness": "NOT_BLIND",
        "r1_r2_artifacts_changed": False,
        "area_missing_is_blocker": False,
    }
    for f in (
        "train_manifest.json",
        "model_comparison_r3.json",
        "cross_season_metrics.json",
        "selected_shape_model.json",
    ):
        write_json(a.output / f, status)
    # Explicit no-evaluation sentinel, not fabricated predictions or metrics.
    write_csv(
        a.output / "cross_season_predictions.csv",
        [{"status": "NOT_EXECUTED", "reason": status["blocker"]}],
    )
    if any(file_hash(Path(path)) != h for path, h in before.items()):
        raise ValueError("R1/R2 artifacts changed")
    write_json(
        a.output / "artifact_manifest.json",
        {
            "files": {f.name: file_hash(f) for f in sorted(a.output.iterdir()) if f.is_file()},
            "status": status,
        },
    )
    print(
        __import__("json").dumps(
            {
                "profiles": [v["profile"] for v in sources],
                "overlap": {k: v for k, v in comparison.items() if k != "farm_total_differences"},
                "status": status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
