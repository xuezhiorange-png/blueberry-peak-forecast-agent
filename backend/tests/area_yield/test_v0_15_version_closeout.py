"""Public frozen-evidence closeout only; never load private datasets or models."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/v0-15/evidence"
CLOSEOUT = EVIDENCE / "v0.15.0-version-closeout-r1.json"
MANIFEST = EVIDENCE / "v0.15.0-version-closeout-manifest-r1.json"


def read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def canonical(value: dict) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()


def test_closeout_source_lineage_and_deterministic_bytes() -> None:
    evidence = read(CLOSEOUT)
    assert CLOSEOUT.read_bytes() == canonical(evidence)
    for relative, expected in evidence["source_evidence_sha256"].items():
        assert relative.startswith("docs/v0-15/evidence/")
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
    manifest = read(MANIFEST)
    for relative, expected in manifest["members"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_exact_merge_and_ci_chain() -> None:
    chain = read(CLOSEOUT)["stage_chain"]
    assert [row["pr"] for row in chain] == list(range(682, 688))
    assert [row["post_merge_ci_run"] for row in chain] == [
        37350682886,
        37387154258,
        37420467521,
        37432636209,
        37446340825,
        37458657975,
    ]
    for row in chain:
        assert row["state"] == "MERGED"
        assert row["base_branch"] == "develop/v0.15"
        assert row["ci_head_sha"] == row["merge_commit"]
        assert row["ci_conclusion"] == "success"
        assert row["ci_status"] == "completed"
        assert row["ci_event"] == "workflow_dispatch"


def test_authority_pins() -> None:
    pins = read(CLOSEOUT)["authority_manifest_hashes"]
    assert pins["S2"] == "7f76d97c34679c31824271ca817835a9ed953504261abf2a249b896713e2e178"
    assert pins["S4"] == "a71b4998d6242709433d6fea334270b4c439c0cdd6f7a4492a1d29533fe82567"
    assert pins["S5"] == "ab43fc93be10aff7deceea18ee3bddd0f1574714ed962f1f2826cf23ccad37d0"
    for stage, directory in [
        ("S2", "data-quality-and-dataset-materialization-r1"),
        ("S4", "harvest-state-feature-freeze-r1"),
        ("S5", "harvest-state-incremental-value-r1"),
    ]:
        source = read(EVIDENCE / directory / "manifest.json")
        assert source.pop("manifest_hash") == pins[stage]
        assert hashlib.sha256(canonical(source)).hexdigest() == pins[stage]
        members = source.get("members", source.get("public_members"))
        entries = (
            [(item["name"], item["sha256"]) for item in members]
            if isinstance(members, list)
            else list(members.items())
        )
        for filename, expected in entries:
            assert (
                hashlib.sha256((EVIDENCE / directory / filename).read_bytes()).hexdigest()
                == expected
            )


def test_counts_and_structural_exclusions() -> None:
    counts = read(CLOSEOUT)["counts"]
    assert counts["base10_origins"] == 20020
    assert counts["base10_target_rows"] == 20020 * 15
    assert counts["logical_harvest_records"] == 33033
    assert counts["raw_evidence_rows"] == 2 * 33033
    assert counts["harvest_state_origins"] == 17892
    assert counts["warmup_exclusions"] == 76 * 28 == 20020 - 17892
    assert counts["weather_train_origins"] == 0
    assert counts["weather_numeric_origins"] == 3058 + 9867


@pytest.mark.parametrize("split", ["validation", "exposed_oot"])
def test_metrics_are_exact_frozen_public_evidence(split: str) -> None:
    closeout = read(CLOSEOUT)
    source = read(
        EVIDENCE / "harvest-state-incremental-value-r1" / f"{split.replace('_', '-')}-metrics.json"
    )
    assert closeout["s5_metrics"][split] == source
    for model in ("M0", "M1"):
        assert source[model]["CURVE_SHAPE_ERROR"] is None
    for horizon in ("H7", "H15"):
        metric = f"{horizon}_DAILY_WAPE"
        assert Decimal(source["M1"][metric]) < Decimal(source["M0"][metric])


def test_negative_signal_and_non_overclaim() -> None:
    closeout = read(CLOSEOUT)
    assert closeout["rolling7_negative_signal"]["delta_days"] == (
        "+0.0641595441595441595441595441595441595441595441595"
    )
    assert closeout["s3_conclusions"]["BASE10_RESEARCH_LEADER"] == "NO_CLEAR_LEADER"
    assert closeout["s5_classification"]["harvest_state_incremental_value"] == "SUPPORTED"
    for key, value in closeout["prohibited_claims"].items():
        assert value is False, key
    assert closeout["strict_pit"] is False
    assert closeout["retrospective_authority_used"] is True
    assert closeout["weather_benchmark_ready"] is False
    assert closeout["curve_shape_not_used_to_establish_support"] is True


def test_governance_scope_and_privacy() -> None:
    closeout = read(CLOSEOUT)
    assert closeout["governance"]["delivery_state"] == "DRAFT_REQUIRES_OWNER_REVIEW"
    for key in (
        "main_integration_authorized",
        "ready_authorized",
        "merge_authorized",
        "tag_authorized",
        "release_authorized",
        "v0_16_authorized",
        "new_model_training_executed",
        "new_scoring_executed",
        "current_2026_27_actual_accessed",
        "v0_14_changed",
    ):
        assert closeout["governance"][key] is False
    text = CLOSEOUT.read_text()
    for forbidden in ('"base_id":', '"quantity_kg":', '"password":', '"token":'):
        assert forbidden not in text
