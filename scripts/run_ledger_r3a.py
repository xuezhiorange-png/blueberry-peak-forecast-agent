"""R3A reuses hash-bound R3 aggregation; never repeats XLS identity/overlap audit."""

import argparse
import json
from datetime import date
from pathlib import Path

from backend.app.area_yield.experiment import file_hash, read_csv, read_json, write_csv, write_json
from backend.app.area_yield.ledger_r3a import qualify


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--r3", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = read_json(args.r3 / "artifact_manifest.json")
    for name in ("input_manifest.json", "canonical_daily_shape.csv", "paired_farm_seasons.csv"):
        if file_hash(args.r3 / name) != manifest["files"][name]:
            raise ValueError("R3 artifact integrity mismatch")
    sources = read_json(args.r3 / "input_manifest.json")["sources"][:2]
    rows = read_csv(args.r3 / "canonical_daily_shape.csv")
    pairs = read_csv(args.r3 / "paired_farm_seasons.csv")
    matched = {
        r["canonical_farm"]
        for r in pairs
        if r["season_23_24_available"] == "True" and r["season_24_25_available"] == "True"
    }
    assert len(matched) == 35
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    all_matrix, calendars = [], []
    for source, season, suffix in zip(
        sources, ("2023-2024", "2024-2025"), ("23_24", "24_25"), strict=True
    ):
        # Pagination/schema consistency is not proof of unfiltered full system export.
        matrix, calendar = qualify(
            [r for r in rows if r["season_id"] == season],
            season,
            date.fromisoformat(source["date_min"]),
            date.fromisoformat(source["date_max"]),
            False,
            matched,
        )
        all_matrix.extend(matrix)
        calendars.append(calendar)
        write_csv(args.output / f"source_active_calendar_{suffix}.csv", calendar)
    write_csv(args.output / "farm_season_qualification_r3a.csv", all_matrix)
    mapping = {(r["farm"], r["season"]): r for r in all_matrix}
    paired = []
    for farm in sorted(matched):
        a, b = mapping[(farm, "2023-2024")], mapping[(farm, "2024-2025")]
        paired.append(
            {
                "farm": farm,
                "strict_eligible_23_24": a["strict_eligible"],
                "strict_eligible_24_25": b["strict_eligible"],
                "eligible_cross_season": a["strict_eligible"] and b["strict_eligible"],
                "eligible_if_source_confirmed": a["eligible_if_source_confirmed"]
                and b["eligible_if_source_confirmed"],
                "diagnostic_only": True,
                "reason_23_24": a["exclusion_reason"],
                "reason_24_25": b["exclusion_reason"],
            }
        )
    write_csv(args.output / "paired_farm_qualification_r3a.csv", paired)
    potential = sum(r["eligible_if_source_confirmed"] for r in paired)
    status = {
        "task_id": "NEXT_VERSION_MULTI_SEASON_LEDGER_QUALIFICATION_AND_SHAPE_TRAINING_R3A",
        "result": "NEEDS_SINGLE_SOURCE_SEMANTIC_CONFIRMATION"
        if potential
        else "NO_STRICT_ELIGIBLE_CROSS_SEASON_SCOPE",
        "source_export_completeness_23_24": "NOT_ESTABLISHED",
        "source_export_completeness_24_25": "NOT_ESTABLISHED",
        "global_no_record_day_counts": [
            sum(not r["source_active_day"] for r in c) for c in calendars
        ],
        "matched_farm_count": 35,
        "strict_eligible_counts": [0, 0],
        "eligible_cross_season_count": 0,
        "paired_eligible_if_source_confirmed_count": potential,
        "diagnostic_only_paired_farm_count": 35,
        "need_user_confirmation_no_record_semantics": True,
        "training_executed": False,
        "trained_models": [],
        "selected_shape_model": None,
        "source_audit_repeated": False,
        "source_structural_evidence": {
            "same_headers_across_pages": True,
            "xls_pagination_65535_data_rows": True,
            "complete_unfiltered_export_proven_by_pagination": False,
        },
        "source_inputs": [
            {"hash": s["sha256"], "file_start": s["date_min"], "file_end": s["date_max"]}
            for s in sources
        ],
        "r3_input_hashes": {
            n: manifest["files"][n] for n in ("input_manifest.json", "canonical_daily_shape.csv")
        },
        "confirmation_question": (
            "这两个XLS是否为对应期间扫码称重系统的完整导出，"
            "某农场某日无记录时是否可解释为当天该农场入库/采摘量为0？"
        ),
    }
    write_json(args.output / "qualification_summary_r3a.json", status)
    write_json(
        args.output / "artifact_manifest.json",
        {f.name: file_hash(f) for f in sorted(args.output.iterdir()) if f.is_file()},
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
