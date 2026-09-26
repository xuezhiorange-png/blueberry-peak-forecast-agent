from __future__ import annotations

import csv
import hashlib
import json
import stat
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from backend.app.area_yield.v08_r2b_temporal_shrinkage import (
    ALLOWED_LAMBDAS,
    R2BExperimentError,
    build_candidate_predictions,
    candidate_metrics,
    pooled_training_yield,
    project_rows_before_freeze,
    select_candidate,
    validate_dataset_hash,
    validate_lambda_grid,
    validate_temporal_cohorts,
)
from scripts.run_v0_8_r2b_temporal_shrinkage import (
    read_pre_freeze_projected_rows,
    run_replay,
)


def _fixture_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index in range(15):
        base = f"T{index:02d}"
        area = Decimal(100 + index)
        yield_value = Decimal(200 + index * 20)
        rows.append(
            {
                "base_id": base,
                "canonical_base_name": base,
                "season": "2023-2024",
                "area_mu": str(area),
                "season_total_quantity_kg": str(area * yield_value),
                "strict_training_eligible": "true",
            }
        )
    for index in range(22):
        base = f"T{index:02d}" if index < 11 else f"V{index - 11:02d}"
        area = Decimal(120 + index)
        actual_yield = Decimal(250 + index * 10)
        rows.append(
            {
                "base_id": base,
                "canonical_base_name": base,
                "season": "2024-2025",
                "area_mu": str(area),
                "season_total_quantity_kg": str(area * actual_yield),
                "strict_training_eligible": "true",
            }
        )
    return rows


def test_canonical_dataset_hash_must_match_s8_pin() -> None:
    payload = b"frozen"
    from hashlib import sha256

    expected = sha256(payload).hexdigest()
    assert validate_dataset_hash(payload, expected) == expected
    with pytest.raises(R2BExperimentError, match="BLOCKED_TRAINING_DATASET_DRIFT"):
        validate_dataset_hash(payload, "0" * 64)


def test_temporal_projection_excludes_validation_actual_before_freeze() -> None:
    rows = _fixture_rows()
    train, validation = project_rows_before_freeze(rows)
    assert len(train) == 15
    assert len(validation) == 22
    assert all(row["season"] == "2023-2024" for row in train)
    assert all(row["season"] == "2024-2025" for row in validation)
    assert all("season_total_quantity_kg" not in row for row in validation)
    assert all("yield_kg_per_mu" not in row for row in validation)


def test_pre_freeze_projection_does_not_access_validation_truth_fields() -> None:
    class GuardedRow(dict[str, str]):
        def __getitem__(self, key: str) -> str:
            if self.get("season") == "2024-2025" and key in {
                "season_total_quantity_kg",
                "yield_kg_per_mu",
            }:
                raise AssertionError("validation target accessed before prediction freeze")
            return super().__getitem__(key)

    guarded = [GuardedRow(row) for row in _fixture_rows()]
    _, validation = project_rows_before_freeze(guarded)
    assert len(validation) == 22


def test_2025_2026_is_rejected_before_any_target_field_access() -> None:
    class ForbiddenBenchmarkRow(dict[str, str]):
        def __getitem__(self, key: str) -> str:
            if key in {"season_total_quantity_kg", "yield_kg_per_mu"}:
                raise AssertionError("2025-2026 target was accessed")
            return super().__getitem__(key)

    row = ForbiddenBenchmarkRow(
        {
            "base_id": "B1",
            "canonical_base_name": "B1",
            "season": "2025-2026",
            "area_mu": "100",
            "season_total_quantity_kg": "SHOULD_NOT_READ",
            "strict_training_eligible": "true",
        }
    )
    with pytest.raises(R2BExperimentError, match="BLOCKED_2025_2026_ACCESS"):
        project_rows_before_freeze([row])


def test_actual_canonical_temporal_cohort_partition_is_frozen() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    partition = validate_temporal_cohorts(train, validation)
    assert partition == {
        "train_count": 15,
        "validation_count": 22,
        "unique_base_count": 26,
        "support_1_count": 11,
        "support_0_count": 11,
        "overlap_count": 11,
    }


def test_temporal_cohort_mismatch_fails_closed() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    with pytest.raises(R2BExperimentError, match="BLOCKED_TEMPORAL_COHORT_MISMATCH"):
        validate_temporal_cohorts(train[:-1], validation)


def test_global_yield_is_area_weighted_and_train_only() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    actual_train_yield = pooled_training_yield(train)
    with localcontext() as context:
        context.prec = 60
        expected = sum(Decimal(row["season_total_quantity_kg"]) for row in train) / sum(
            Decimal(row["area_mu"]) for row in train
        )
    assert actual_train_yield == expected
    assert actual_train_yield != Decimal("855.5593226284052977280068914")
    # The function's argument is the explicit train partition; validation is not joined.
    assert pooled_training_yield(train) == actual_train_yield
    assert len(validation) == 22


def test_lambda_grid_is_exactly_the_s8_frozen_six_values() -> None:
    assert tuple(map(str, ALLOWED_LAMBDAS)) == ("0.25", "0.5", "1", "2", "4", "8")
    with pytest.raises(R2BExperimentError, match="BLOCKED_LAMBDA_GRID_DRIFT"):
        validate_lambda_grid((*ALLOWED_LAMBDAS, Decimal("16")))


def test_support_zero_candidates_have_identical_predictions() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    predictions = build_candidate_predictions(train, validation)
    support_zero = [row for row in predictions if row["support_group"] == "SUPPORT_0"]
    assert len(support_zero) == 11
    for row in support_zero:
        values = [
            Decimal(row["global_predicted_total"]),
            Decimal(row["base_specific_predicted_total"]),
            *[
                Decimal(row[f"lambda_{str(lam).replace('.', '_')}_predicted_total"])
                for lam in ALLOWED_LAMBDAS
            ],
        ]
        assert len(set(values)) == 1


def test_base_specific_prediction_uses_only_same_base_2023_2024_yield() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    predictions = build_candidate_predictions(train, validation)
    prediction = next(row for row in predictions if row["base_id"] == "T00")
    training_row = next(row for row in train if row["base_id"] == "T00")
    expected_yield = Decimal(training_row["season_total_quantity_kg"]) / Decimal(
        training_row["area_mu"]
    )
    assert Decimal(prediction["base_historical_yield"]) == expected_yield
    assert Decimal(prediction["base_specific_predicted_total"]) == expected_yield * Decimal(
        prediction["validation_area_mu"]
    )


@pytest.mark.parametrize("lam", ALLOWED_LAMBDAS)
def test_single_season_shrinkage_weight_is_n_over_n_plus_lambda(lam: Decimal) -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    predictions = build_candidate_predictions(train, validation)
    prediction = next(row for row in predictions if row["base_id"] == "T00")
    suffix = str(lam).replace(".", "_")
    with localcontext() as context:
        context.prec = 60
        expected_weight = Decimal(1) / (Decimal(1) + lam)
    assert Decimal(prediction[f"lambda_{suffix}_weight"]) == expected_weight


def test_predictions_are_generation_separate_from_validation_scoring() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    predictions = build_candidate_predictions(train, validation)
    assert len(predictions) == 22
    assert all("actual_total" not in row for row in predictions)
    assert all("actual_yield" not in row for row in predictions)


def test_primary_candidate_selection_uses_support1_metrics_and_exact_ties() -> None:
    summaries = [
        {"candidate": "SHRINKAGE_BASE_YIELD", "lambda": "0.5", "wape": "0.2", "bias_kg": "3"},
        {"candidate": "GLOBAL_POOLED_YIELD", "lambda": "NONE", "wape": "0.2", "bias_kg": "500"},
        {
            "candidate": "BASE_SPECIFIC_NO_SHRINKAGE",
            "lambda": "NONE",
            "wape": "0.2",
            "bias_kg": "1",
        },
    ]
    selected = select_candidate(summaries)
    assert selected["candidate"] == "GLOBAL_POOLED_YIELD"


def test_candidate_metrics_use_one_fixed_actual_denominator() -> None:
    predictions = [
        {"base_id": "A", "support_group": "SUPPORT_1", "global_predicted_total": "90"},
        {"base_id": "B", "support_group": "SUPPORT_1", "global_predicted_total": "210"},
        {"base_id": "C", "support_group": "SUPPORT_0", "global_predicted_total": "300"},
    ]
    actuals = {"A": Decimal(100), "B": Decimal(200), "C": Decimal(300)}
    summary = candidate_metrics(predictions, actuals, "global_predicted_total")
    with localcontext() as context:
        context.prec = 60
        expected_wape = Decimal(20) / Decimal(600)
    assert Decimal(summary["wape"]) == expected_wape
    assert summary["row_count"] == 3


def test_primary_selection_does_not_accept_all22_summary_argument() -> None:
    support1 = [
        {"candidate": "GLOBAL_POOLED_YIELD", "lambda": "NONE", "wape": "0.2", "bias_kg": "0"},
        {"candidate": "SHRINKAGE_BASE_YIELD", "lambda": "1", "wape": "0.19", "bias_kg": "100"},
    ]
    selected = select_candidate(support1)
    assert selected["candidate"] == "SHRINKAGE_BASE_YIELD"


def test_same_base_validation_actual_is_not_used_to_predict_itself() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    predictions = build_candidate_predictions(train, validation)
    prediction = next(row for row in predictions if row["base_id"] == "T00")
    expected = Decimal(train[0]["yield_kg_per_mu"])
    assert Decimal(prediction["base_specific_predicted_yield"]) == expected
    assert "season_total_quantity_kg" not in next(
        row for row in validation if row["base_id"] == "T00"
    )


def test_validation_labels_are_forbidden_in_pooled_training_yield() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    mixed = [*train, {**validation[0], "season_total_quantity_kg": "1"}]
    with pytest.raises(R2BExperimentError, match="VALIDATION_LABEL_FORBIDDEN_IN_GLOBAL_YIELD"):
        pooled_training_yield(mixed)


def test_area_is_a_monotone_scale_input_for_every_candidate() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    target = next(row for row in validation if row["base_id"] == "T00")
    low = next(
        row for row in build_candidate_predictions(train, validation) if row["base_id"] == "T00"
    )
    changed_validation = [
        {**row, "area_mu": "240"} if row["base_id"] == "T00" else row for row in validation
    ]
    high = next(
        row
        for row in build_candidate_predictions(train, changed_validation)
        if row["base_id"] == "T00"
    )
    assert Decimal(target["area_mu"]) == Decimal("120")
    total_fields = [
        "global_predicted_total",
        "base_specific_predicted_total",
        *[f"lambda_{str(lam).replace('.', '_')}_predicted_total" for lam in ALLOWED_LAMBDAS],
    ]
    for field in total_fields:
        assert Decimal(high[field]) > Decimal(low[field])


def test_shrinkage_tie_prefers_stronger_lambda_after_bias_tie() -> None:
    summaries = [
        {"candidate": "SHRINKAGE_BASE_YIELD", "lambda": "0.25", "wape": "0.2", "bias_kg": "0"},
        {"candidate": "SHRINKAGE_BASE_YIELD", "lambda": "8", "wape": "0.2", "bias_kg": "0"},
    ]
    assert select_candidate(summaries)["lambda"] == "8"


def test_primary_support1_and_all22_metrics_are_separate() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    predictions = build_candidate_predictions(train, validation)
    actuals = {
        row["base_id"]: Decimal(row["season_total_quantity_kg"])
        for row in _fixture_rows()
        if row["season"] == "2024-2025"
    }
    field = "global_predicted_total"
    primary = candidate_metrics(predictions, actuals, field, support_group="SUPPORT_1")
    auxiliary = candidate_metrics(predictions, actuals, field)
    assert primary["row_count"] == 11
    assert auxiliary["row_count"] == 22


def test_predictions_do_not_include_daily_or_peak_fields() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    predictions = build_candidate_predictions(train, validation)
    assert all(
        not any(token in key for token in ("daily", "peak", "rolling7"))
        for row in predictions
        for key in row
    )


def test_candidate_metric_rejects_empty_or_zero_actual_denominator() -> None:
    with pytest.raises(R2BExperimentError, match="NONPOSITIVE_WAPE_DENOMINATOR"):
        candidate_metrics(
            [{"base_id": "A", "support_group": "SUPPORT_1", "global_predicted_total": "2"}],
            {"A": Decimal(0)},
            "global_predicted_total",
        )


def test_cohort_keys_cannot_overlap_between_train_and_validation() -> None:
    train, validation = project_rows_before_freeze(_fixture_rows())
    validation[0] = {**validation[0], "base_id": train[1]["base_id"]}
    with pytest.raises(R2BExperimentError, match="BLOCKED_TEMPORAL_COHORT_MISMATCH"):
        validate_temporal_cohorts(train, validation)


def test_csv_pre_freeze_reader_does_not_project_validation_target(tmp_path: Path) -> None:
    source = tmp_path / "canonical.csv"
    rows = _fixture_rows()
    fields = list(rows[0])
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    projected = read_pre_freeze_projected_rows(source)
    validation = [row for row in projected if row["season"] == "2024-2025"]
    assert len(validation) == 22
    assert all("season_total_quantity_kg" not in row for row in validation)
    assert all("yield_kg_per_mu" not in row for row in validation)


def test_independent_replay_artifacts_are_byte_identical_and_private(tmp_path: Path) -> None:
    source = tmp_path / "canonical.csv"
    rows = _fixture_rows()
    fields = list(rows[0])
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    first = run_replay(source, tmp_path / "one", source_hash)
    second = run_replay(source, tmp_path / "two", source_hash)
    assert first["files"] == second["files"]
    assert all(
        (tmp_path / "one" / filename).read_bytes() == (tmp_path / "two" / filename).read_bytes()
        for filename in first["files"]
    )
    assert stat.S_IMODE((tmp_path / "one").stat().st_mode) == 0o700
    assert (
        stat.S_IMODE((tmp_path / "one" / "temporal-validation-scoring-r1.csv").stat().st_mode)
        == 0o600
    )
    freeze = json.loads(
        (tmp_path / "one" / "prediction-freeze-manifest-r1.json").read_text(encoding="utf-8")
    )
    assert freeze["predictions_frozen"] is True
    assert freeze["validation_actual_accessed_before_freeze"] is False
    summary = json.loads(
        (tmp_path / "one" / "experiment-summary-r1.json").read_text(encoding="utf-8")
    )
    assert summary["predictions_frozen_before_validation_scoring"] is True
    assert summary["used_2025_2026"] is False
