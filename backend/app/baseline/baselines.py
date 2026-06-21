from __future__ import annotations

from backend.app.baseline.metrics import evaluated_row, excluded_row
from backend.app.baseline.schemas import BacktestResultRow, BaselineSample


def previous_season_by_start_date(samples: list[BaselineSample]) -> dict[str, str | None]:
    ordered = sorted(
        {(sample.season_code, sample.season_start_date) for sample in samples},
        key=lambda item: item[1],
    )
    result: dict[str, str | None] = {}
    previous_code: str | None = None
    for season_code, _start_date in ordered:
        result[season_code] = previous_code
        previous_code = season_code
    return result


def _sample_index(samples: list[BaselineSample]) -> dict[tuple[str, int], BaselineSample]:
    return {(sample.season_code, sample.factory_id): sample for sample in samples}


def evaluate_previous_season_peak(samples: list[BaselineSample]) -> list[BacktestResultRow]:
    previous_by_season = previous_season_by_start_date(samples)
    sample_by_key = _sample_index(samples)
    rows: list[BacktestResultRow] = []
    for sample in sorted(samples, key=lambda item: (item.season_start_date, item.factory_id)):
        previous_code = previous_by_season[sample.season_code]
        if previous_code is None or (previous_code, sample.factory_id) not in sample_by_key:
            previous_season_id = None
            if previous_code is not None and (previous_code, sample.factory_id) in sample_by_key:
                previous_season_id = sample_by_key[(previous_code, sample.factory_id)].season_id
            rows.append(
                excluded_row(
                    baseline_name="previous_season_peak",
                    target_season_id=sample.season_id,
                    target_season_code=sample.season_code,
                    factory_id=sample.factory_id,
                    factory_name=sample.factory_name,
                    fold_key=f"season:{sample.season_code}",
                    previous_season_code=previous_code,
                    previous_season_id=previous_season_id,
                    actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                    exclusion_reason="missing_previous_season_factory_metric",
                )
            )
            continue
        previous = sample_by_key[(previous_code, sample.factory_id)]
        if sample.stable_median_3d_peak_kg <= 0:
            rows.append(
                excluded_row(
                    baseline_name="previous_season_peak",
                    target_season_id=sample.season_id,
                    target_season_code=sample.season_code,
                    factory_id=sample.factory_id,
                    factory_name=sample.factory_name,
                    fold_key=f"season:{sample.season_code}",
                    previous_season_id=previous.season_id,
                    previous_season_code=previous.season_code,
                    actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                    exclusion_reason="non_positive_actual_peak",
                )
            )
            continue
        rows.append(
            evaluated_row(
                baseline_name="previous_season_peak",
                target_season_id=sample.season_id,
                target_season_code=sample.season_code,
                factory_id=sample.factory_id,
                factory_name=sample.factory_name,
                previous_season_id=previous.season_id,
                previous_season_code=previous.season_code,
                fold_key=f"season:{sample.season_code}",
                actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                predicted_stable_peak_kg=previous.stable_median_3d_peak_kg,
                input_features={
                    "previous_season_stable_peak_kg": previous.stable_median_3d_peak_kg,
                },
            )
        )
    return rows


def evaluate_volume_previous_concentration(
    samples: list[BaselineSample],
) -> list[BacktestResultRow]:
    previous_by_season = previous_season_by_start_date(samples)
    sample_by_key = _sample_index(samples)
    rows: list[BacktestResultRow] = []
    for sample in sorted(samples, key=lambda item: (item.season_start_date, item.factory_id)):
        previous_code = previous_by_season[sample.season_code]
        if previous_code is None or (previous_code, sample.factory_id) not in sample_by_key:
            rows.append(
                excluded_row(
                    baseline_name="volume_previous_concentration",
                    target_season_id=sample.season_id,
                    target_season_code=sample.season_code,
                    factory_id=sample.factory_id,
                    factory_name=sample.factory_name,
                    fold_key=f"season:{sample.season_code}",
                    previous_season_code=previous_code,
                    actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                    exclusion_reason="missing_previous_season_factory_metric",
                )
            )
            continue
        previous = sample_by_key[(previous_code, sample.factory_id)]
        if previous.peak_concentration <= 0:
            rows.append(
                excluded_row(
                    baseline_name="volume_previous_concentration",
                    target_season_id=sample.season_id,
                    target_season_code=sample.season_code,
                    factory_id=sample.factory_id,
                    factory_name=sample.factory_name,
                    fold_key=f"season:{sample.season_code}",
                    previous_season_id=previous.season_id,
                    previous_season_code=previous.season_code,
                    actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                    exclusion_reason="invalid_previous_season_peak_concentration",
                )
            )
            continue
        if sample.stable_median_3d_peak_kg <= 0:
            rows.append(
                excluded_row(
                    baseline_name="volume_previous_concentration",
                    target_season_id=sample.season_id,
                    target_season_code=sample.season_code,
                    factory_id=sample.factory_id,
                    factory_name=sample.factory_name,
                    fold_key=f"season:{sample.season_code}",
                    previous_season_id=previous.season_id,
                    previous_season_code=previous.season_code,
                    actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                    exclusion_reason="non_positive_actual_peak",
                )
            )
            continue
        rows.append(
            evaluated_row(
                baseline_name="volume_previous_concentration",
                target_season_id=sample.season_id,
                target_season_code=sample.season_code,
                factory_id=sample.factory_id,
                factory_name=sample.factory_name,
                previous_season_id=previous.season_id,
                previous_season_code=previous.season_code,
                fold_key=f"season:{sample.season_code}",
                actual_stable_peak_kg=sample.stable_median_3d_peak_kg,
                predicted_stable_peak_kg=sample.total_weight_kg * previous.peak_concentration,
                input_features={
                    "oracle_total_weight_kg": sample.total_weight_kg,
                    "previous_season_peak_concentration": previous.peak_concentration,
                },
            )
        )
    return rows
