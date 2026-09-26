"""Read-only scale/shape diagnosis over immutable V0.8-S8 artifacts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

QUANTUM = Decimal("0.000001")
OOT_SEASON = "2025-2026"
OOT_START = date(2025, 7, 22)
OOT_END = date(2026, 4, 15)
EXPECTED_DAYS = (OOT_END - OOT_START).days + 1


class S9DiagnosisError(ValueError):
    """Raised when frozen S8 evidence or diagnosis inputs fail closed."""


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise S9DiagnosisError(f"INVALID_DECIMAL:{field}") from exc
    if not result.is_finite():
        raise S9DiagnosisError(f"NONFINITE_DECIMAL:{field}")
    return result


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise S9DiagnosisError("NONFINITE_DECIMAL_OUTPUT")
    return format(value, "f")


def _precise_sum(values: Sequence[Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return sum(values, Decimal(0))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise S9DiagnosisError(f"JSON_INPUT_INVALID:{path.name}") from exc
    if not isinstance(value, dict):
        raise S9DiagnosisError(f"JSON_ROOT_NOT_OBJECT:{path.name}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError as exc:
        raise S9DiagnosisError(f"CSV_INPUT_MISSING:{path.name}") from exc


def csv_bytes(fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fieldnames),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({name: _csv_value(row.get(name)) for name in fieldnames})
    return stream.getvalue().encode("utf-8")


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def percentile(values: Sequence[Decimal], quantile: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = Decimal(len(ordered) - 1) * quantile
    lower = int(rank)
    fraction = rank - Decimal(lower)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def training_support_counts(
    training_rows: Sequence[Mapping[str, str]], target_base_ids: Sequence[str]
) -> dict[str, int]:
    counts = dict.fromkeys(target_base_ids, 0)
    keys: set[tuple[str, str]] = set()
    for row in training_rows:
        base_id = str(row["base_id"])
        season = str(row["season"])
        key = (base_id, season)
        if season not in {"2023-2024", "2024-2025"}:
            raise S9DiagnosisError("OOT_SEASON_IN_TRAINING_SUPPORT_ROWS")
        if key in keys:
            raise S9DiagnosisError("DUPLICATE_TRAINING_BASE_SEASON_FOR_SUPPORT")
        keys.add(key)
        if base_id in counts:
            counts[base_id] += 1
    return counts


def area_tertile_cutpoints(
    training_area_values: Sequence[Decimal], q33: Decimal, q67: Decimal
) -> tuple[Decimal, Decimal]:
    if not training_area_values or not Decimal(0) <= q33 <= q67 <= Decimal(1):
        raise S9DiagnosisError("INVALID_TRAINING_AREA_TERTILE_INPUT")
    low = percentile(training_area_values, q33)
    high = percentile(training_area_values, q67)
    if low is None or high is None:
        raise S9DiagnosisError("TRAINING_AREA_TERTILE_CUTPOINTS_MISSING")
    return low, high


def normalized_shares(values: Sequence[Decimal]) -> list[Decimal]:
    if not values or any(value < 0 for value in values):
        raise S9DiagnosisError("SHARE_INPUT_EMPTY_OR_NEGATIVE")
    total = sum(values, Decimal(0))
    if total <= 0:
        raise S9DiagnosisError("ZERO_TOTAL_CANNOT_DEFINE_SHARES")
    with localcontext() as context:
        context.prec = 80
        result = [value / total for value in values]
        result[-1] = Decimal(1) - sum(result[:-1], Decimal(0))
        normalized_total = sum(result, Decimal(0))
    if any(value < 0 for value in result) or normalized_total != Decimal(1):
        raise S9DiagnosisError("NORMALIZED_SHARES_DO_NOT_SUM_TO_ONE")
    return result


def counterfactual_curve(total: Decimal, shares: Sequence[Decimal]) -> list[Decimal]:
    if total < 0 or not shares or _precise_sum(shares) != Decimal(1):
        raise S9DiagnosisError("INVALID_COUNTERFACTUAL_INPUT")
    with localcontext() as context:
        context.prec = 80
        quantities = [total * share for share in shares[:-1]]
        quantities.append(total - sum(quantities, Decimal(0)))
        quantity_total = sum(quantities, Decimal(0))
    if quantity_total != total:
        raise S9DiagnosisError("COUNTERFACTUAL_MASS_BALANCE_FAILED")
    return quantities


def error_metrics(actual: Sequence[Decimal], predicted: Sequence[Decimal]) -> dict[str, Any]:
    if len(actual) != len(predicted) or not actual:
        raise S9DiagnosisError("METRIC_COHORT_EMPTY_OR_MISMATCHED")
    errors = [abs(pred - truth) for truth, pred in zip(actual, predicted, strict=True)]
    signed = [pred - truth for truth, pred in zip(actual, predicted, strict=True)]
    actual_total = sum(actual, Decimal(0))
    prediction_total = sum(predicted, Decimal(0))
    absolute_error = sum(errors, Decimal(0))
    bias_sum = sum(signed, Decimal(0))
    return {
        "n": len(actual),
        "actual_sum": decimal_text(actual_total),
        "predicted_sum": decimal_text(prediction_total),
        "absolute_error_sum": decimal_text(absolute_error),
        "wape": decimal_text(absolute_error / actual_total)
        if actual_total > 0
        else "NOT_COMPUTABLE_ZERO_ACTUAL_DENOMINATOR",
        "mae": decimal_text(absolute_error / Decimal(len(actual))),
        "bias_sum_predicted_minus_actual": decimal_text(bias_sum),
        "bias_mean_predicted_minus_actual": decimal_text(bias_sum / Decimal(len(actual))),
    }


def _peak(dates: Sequence[date], quantities: Sequence[Decimal]) -> tuple[date, Decimal]:
    if not dates or len(dates) != len(quantities):
        raise S9DiagnosisError("PEAK_SERIES_EMPTY_OR_MISMATCHED")
    index = next(i for i, value in enumerate(quantities) if value == max(quantities))
    return dates[index], quantities[index]


def _rolling7(dates: Sequence[date], quantities: Sequence[Decimal]) -> tuple[date, date, Decimal]:
    if len(dates) < 7 or len(dates) != len(quantities):
        raise S9DiagnosisError("ROLLING7_SERIES_TOO_SHORT_OR_MISMATCHED")
    if any(dates[i + 1] - dates[i] != timedelta(days=1) for i in range(len(dates) - 1)):
        raise S9DiagnosisError("ROLLING7_DATES_NOT_CONSECUTIVE")
    values = [sum(quantities[start : start + 7], Decimal(0)) for start in range(len(dates) - 6)]
    index = next(i for i, value in enumerate(values) if value == max(values))
    return dates[index], dates[index] + timedelta(days=6), values[index]


def _validate_manifest(repo_root: Path, s8_root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    evidence_path = (
        repo_root / "docs/v0-8/evidence/s8-canonical-training-and-independent-oot-backtest-r1.json"
    )
    config_path = repo_root / "configs/v0_8_s8_training_backtest_r1.json"
    evidence_sha = sha256_file(evidence_path)
    config_sha = sha256_file(config_path)
    if evidence_sha != config["s8_repository_evidence_sha256"]:
        raise S9DiagnosisError("BLOCKED_S8_ARTIFACT_DRIFT:REPOSITORY_EVIDENCE")
    if config_sha != config["s8_repository_config_sha256"]:
        raise S9DiagnosisError("BLOCKED_S8_ARTIFACT_DRIFT:REPOSITORY_CONFIG")
    evidence = read_json(evidence_path)
    if (
        evidence.get("base_main_sha") != config["s8_baseline_main_sha"]
        or evidence.get("task_id") != "V0_8_S8_CANONICAL_TRAINING_AND_INDEPENDENT_OOT_BACKTEST_R1"
    ):
        raise S9DiagnosisError("BLOCKED_S8_ARTIFACT_DRIFT:EVIDENCE_IDENTITY")
    manifest_path = s8_root / "artifact-manifest.json"
    manifest_sha = sha256_file(manifest_path)
    if manifest_sha != config["s8_private_manifest_sha256"]:
        raise S9DiagnosisError("BLOCKED_S8_ARTIFACT_DRIFT:PRIVATE_MANIFEST")
    manifest = read_json(manifest_path)
    artifact_hashes = manifest.get("artifacts")
    if not isinstance(artifact_hashes, dict):
        raise S9DiagnosisError("BLOCKED_S8_ARTIFACT_DRIFT:PRIVATE_MANIFEST_SCHEMA")
    mismatches: list[dict[str, str]] = []
    for relative, expected in sorted(artifact_hashes.items()):
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts:
            raise S9DiagnosisError("BLOCKED_S8_ARTIFACT_DRIFT:UNSAFE_MANIFEST_PATH")
        path = s8_root / rel
        if path.is_symlink() or not path.is_file():
            actual = "MISSING_OR_SYMLINK"
        else:
            actual = sha256_file(path)
        if actual != expected:
            mismatches.append({"path": relative, "expected": str(expected), "actual": actual})
    if mismatches:
        raise S9DiagnosisError(f"BLOCKED_S8_ARTIFACT_DRIFT:{mismatches[0]['path']}")
    expected_selected = config["expected_s8_artifacts"]
    for relative, expected in expected_selected.items():
        if artifact_hashes.get(relative) != expected:
            raise S9DiagnosisError(f"BLOCKED_S8_ARTIFACT_DRIFT:PIN_MISMATCH:{relative}")
    if len(artifact_hashes) != 59:
        raise S9DiagnosisError("BLOCKED_S8_ARTIFACT_DRIFT:ARTIFACT_COUNT")
    if manifest_sha != evidence.get("private_artifacts", {}).get("manifest_sha256"):
        raise S9DiagnosisError("BLOCKED_S8_ARTIFACT_DRIFT:EVIDENCE_MANIFEST_PIN")
    return {
        "manifest_sha256": manifest_sha,
        "repository_evidence_sha256": evidence_sha,
        "repository_config_sha256": config_sha,
        "artifact_count": len(artifact_hashes),
        "artifact_hashes": dict(sorted(artifact_hashes.items())),
        "evidence": evidence,
    }


def _rows_by_base_date(
    rows: Sequence[Mapping[str, str]], label: str
) -> dict[str, list[dict[str, str]]]:
    by_base: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for original in rows:
        row = dict(original)
        base_id = row.get("base_id", "")
        day = row.get("date", "")
        key = (base_id, day)
        if not base_id or key in seen:
            raise S9DiagnosisError(f"{label}_EMPTY_BASE_OR_DUPLICATE_DAY")
        seen.add(key)
        by_base[base_id].append(row)
    for base_id, group in by_base.items():
        group.sort(key=lambda item: item["date"])
        dates = [date.fromisoformat(item["date"]) for item in group]
        if len(group) != EXPECTED_DAYS or dates[0] != OOT_START or dates[-1] != OOT_END:
            raise S9DiagnosisError(f"{label}_INCOMPLETE_OOT_DAILY_CURVE:{base_id}")
        if any(
            dates[index + 1] - dates[index] != timedelta(days=1) for index in range(len(dates) - 1)
        ):
            raise S9DiagnosisError(f"{label}_NONCONSECUTIVE_DAILY_CURVE:{base_id}")
    return by_base


def validate_cohort_separation(
    training_rows: Sequence[Mapping[str, str]],
    oot_rows: Sequence[Mapping[str, str]],
    v07_base_ids: Sequence[str],
) -> None:
    training_keys = [(row["base_id"], row["season"]) for row in training_rows]
    oot_keys = [(row["base_id"], row["season"]) for row in oot_rows]
    if len(training_keys) != 37 or len(set(training_keys)) != 37:
        raise S9DiagnosisError("S8_TRAINING_COHORT_MUST_BE_37_UNIQUE_ROWS")
    if len(oot_keys) != 39 or len(set(oot_keys)) != 39:
        raise S9DiagnosisError("S8_OOT_COHORT_MUST_BE_39_UNIQUE_ROWS")
    if set(training_keys) & set(oot_keys):
        raise S9DiagnosisError("S8_TRAIN_OOT_KEY_OVERLAP")
    if any(season not in {"2023-2024", "2024-2025"} for _, season in training_keys):
        raise S9DiagnosisError("S8_OOT_ACTUAL_FOUND_IN_TRAINING_COHORT")
    if any(season != OOT_SEASON for _, season in oot_keys):
        raise S9DiagnosisError("S8_OOT_SEASON_IDENTITY_MISMATCH")
    if len(v07_base_ids) != 30 or len(set(v07_base_ids)) != 30:
        raise S9DiagnosisError("V07_COMMON_COHORT_MUST_BE_30_UNIQUE_BASES")
    if not set(v07_base_ids).issubset({base for base, _ in oot_keys}):
        raise S9DiagnosisError("V07_COMMON_COHORT_NOT_SUBSET_OF_FULL39")


def _map_unique(
    rows: Sequence[Mapping[str, str]], key_names: Sequence[str], label: str
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for source in rows:
        row = dict(source)
        key = (
            row[key_names[0]] if len(key_names) == 1 else "|".join(row[name] for name in key_names)
        )
        if key in result:
            raise S9DiagnosisError(f"DUPLICATE_{label}_KEY:{key}")
        result[key] = row
    return result


def _average(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else None


def _rank(values: Sequence[Decimal]) -> list[Decimal]:
    ordered = sorted((value, index) for index, value in enumerate(values))
    ranks = [Decimal(0)] * len(values)
    position = 1
    offset = 0
    while offset < len(ordered):
        end = offset + 1
        while end < len(ordered) and ordered[end][0] == ordered[offset][0]:
            end += 1
        rank = (Decimal(position) + Decimal(position + end - offset - 1)) / Decimal(2)
        for _, index in ordered[offset:end]:
            ranks[index] = rank
        position += end - offset
        offset = end
    return ranks


def _correlation(left: Sequence[Decimal], right: Sequence[Decimal]) -> str | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    with localcontext() as context:
        context.prec = 60
        mean_left = sum(left, Decimal(0)) / Decimal(len(left))
        mean_right = sum(right, Decimal(0)) / Decimal(len(right))
        centered_left = [value - mean_left for value in left]
        centered_right = [value - mean_right for value in right]
        sum_left = sum((value * value for value in centered_left), Decimal(0))
        sum_right = sum((value * value for value in centered_right), Decimal(0))
        denominator = (sum_left * sum_right).sqrt()
        if denominator == 0:
            return None
        covariance = sum(
            (a * b for a, b in zip(centered_left, centered_right, strict=True)), Decimal(0)
        )
        return decimal_text(covariance / denominator)


def _metric_for_bases(
    rows: Sequence[Mapping[str, Any]], actual_key: str, pred_key: str
) -> dict[str, Any] | None:
    if not rows:
        return None
    actual = [decimal_value(row[actual_key], actual_key) for row in rows]
    predicted = [decimal_value(row[pred_key], pred_key) for row in rows]
    return error_metrics(actual, predicted)


def _group_metric(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any] | None:
    if not rows:
        return None
    return error_metrics(
        [decimal_value(row["actual_total_kg"], "actual_total") for row in rows],
        [decimal_value(row[field], field) for row in rows],
    )


def diagnose_curves(actual: Sequence[Decimal], predicted: Sequence[Decimal]) -> dict[str, Any]:
    """Pure mathematical helper used by regression tests and the S9 runner."""
    if len(actual) != len(predicted) or not actual:
        raise S9DiagnosisError("CURVE_LENGTH_INVALID")
    actual_total = sum(actual, Decimal(0))
    predicted_total = sum(predicted, Decimal(0))
    actual_share = normalized_shares(actual)
    predicted_share = normalized_shares(predicted)
    scale_only = counterfactual_curve(predicted_total, actual_share)
    shape_only = counterfactual_curve(actual_total, predicted_share)
    shape_abs = [abs(a - p) for a, p in zip(actual_share, predicted_share, strict=True)]
    cumulative_actual = Decimal(0)
    cumulative_predicted = Decimal(0)
    cumulative_differences: list[Decimal] = []
    for a_share, p_share in zip(actual_share, predicted_share, strict=True):
        cumulative_actual += a_share
        cumulative_predicted += p_share
        cumulative_differences.append(abs(cumulative_actual - cumulative_predicted))
    return {
        "actual_total": actual_total,
        "predicted_total": predicted_total,
        "actual_share": actual_share,
        "predicted_share": predicted_share,
        "scale_only": scale_only,
        "shape_only": shape_only,
        "shape_l1": sum(shape_abs, Decimal(0)),
        "shape_mae": sum(shape_abs, Decimal(0)) / Decimal(len(actual)),
        "max_cumulative_share_deviation": max(cumulative_differences),
    }


def _format_distribution(values: Sequence[Decimal]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None}
    return {
        "count": len(values),
        "min": decimal_text(min(values)),
        "p25": decimal_text(percentile(values, Decimal("0.25")) or Decimal(0)),
        "median": decimal_text(percentile(values, Decimal("0.5")) or Decimal(0)),
        "p75": decimal_text(percentile(values, Decimal("0.75")) or Decimal(0)),
        "max": decimal_text(max(values)),
    }


def _source_share_hash(rows: Sequence[Mapping[str, str]]) -> str:
    canonical = [
        [
            row["base_id"],
            row["date"],
            decimal_text(decimal_value(row["predicted_share"], "predicted_share")),
        ]
        for row in sorted(rows, key=lambda item: (item["base_id"], item["date"]))
    ]
    return sha256_bytes(canonical_json_bytes(canonical))


def _build_diagnosis(
    *, s8_root: Path, config: Mapping[str, Any], pins: Mapping[str, Any]
) -> tuple[dict[str, bytes], dict[str, Any]]:
    names = config["expected_s8_artifacts"]
    paths = {name: s8_root / name for name in names}
    train = read_csv(paths["v0-8-canonical-training-dataset-r1.csv"])
    oot = read_csv(paths["v0-8-canonical-oot-dataset-r1.csv"])
    v08_daily_raw = read_csv(paths["v0-8-oot-daily-predictions-r1.csv"])
    baseline_daily_raw = read_csv(paths["baseline-oot-daily-predictions-r1.csv"])
    v07_daily_raw = read_csv(paths["v0-7-oot-daily-predictions-r1.csv"])
    v08_totals = _map_unique(
        read_csv(paths["v0-8-oot-season-total-predictions-r1.csv"]), ["base_id"], "V08_TOTAL"
    )
    baseline_totals = _map_unique(
        read_csv(paths["baseline-oot-predictions-r1.csv"]), ["base_id"], "BASELINE_TOTAL"
    )
    v07_totals = _map_unique(
        read_csv(paths["v0-7-oot-predictions-r1.csv"]), ["base_id"], "V07_TOTAL"
    )
    area_audit = _map_unique(
        read_csv(paths["area-extrapolation-audit-r1.csv"]), ["base_id"], "AREA_AUDIT"
    )
    model = read_json(paths["model-artifact/training-replay-1/v0-8-model-artifact-r1.json"])
    v08_daily = _rows_by_base_date(v08_daily_raw, "V08")
    baseline_daily = _rows_by_base_date(baseline_daily_raw, "BASELINE")
    v07_daily = _rows_by_base_date(v07_daily_raw, "V07")
    v07_ids_from_predictions = sorted({row["base_id"] for row in v07_daily_raw})
    validate_cohort_separation(train, oot, v07_ids_from_predictions)
    oot_by_base = _map_unique(oot, ["base_id"], "OOT_DATASET")
    base_ids = sorted(oot_by_base)
    if set(base_ids) != set(v08_daily) or set(base_ids) != set(baseline_daily):
        raise S9DiagnosisError("FULL39_DAILY_COHORT_MISMATCH")
    if set(v07_daily) != set(v07_totals) or len(v07_daily) != 30:
        raise S9DiagnosisError("COMMON30_V07_COHORT_INVALID")
    common_ids = sorted(v07_daily)
    if len(common_ids) != 30 or not set(common_ids).issubset(base_ids):
        raise S9DiagnosisError("COMMON30_COHORT_INVALID")

    training_by_base: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in train:
        training_by_base[row["base_id"]].append(row)
    model_stage_a = model.get("stage_a", {})
    model_yields = model_stage_a.get("base_yield_kg_per_mu", {})
    global_yield = decimal_value(
        model_stage_a.get("pooled_training_yield_kg_per_mu"), "pooled_yield"
    )
    training_quantity = sum(
        (decimal_value(row["season_total_quantity_kg"], "training_total") for row in train),
        Decimal(0),
    )
    training_area = sum(
        (decimal_value(row["area_mu"], "training_area") for row in train), Decimal(0)
    )
    with localcontext() as context:
        # Match S8's frozen pooled-yield arithmetic precision exactly.
        context.prec = 40
        recomputed_global_yield = training_quantity / training_area
    if recomputed_global_yield != global_yield:
        raise S9DiagnosisError("S8_POOLED_YIELD_RECOMPUTATION_MISMATCH")
    training_yields = [decimal_value(row["yield_kg_per_mu"], "training_yield") for row in train]
    training_areas = [decimal_value(row["area_mu"], "training_area") for row in train]
    train_yield_min = min(training_yields)
    train_yield_max = max(training_yields)
    area_quantiles = config["analysis_contract"]["area_tertile_cutpoints"]
    area_cut_low, area_cut_high = area_tertile_cutpoints(
        training_areas,
        decimal_value(area_quantiles[0], "area_tertile_p33"),
        decimal_value(area_quantiles[1], "area_tertile_p67"),
    )
    support_by_base = training_support_counts(train, base_ids)

    actual_total_by_base: dict[str, Decimal] = {}
    v08_sum_by_base: dict[str, Decimal] = {}
    baseline_sum_by_base: dict[str, Decimal] = {}
    diagnosis: dict[str, dict[str, Any]] = {}
    counter_rows: list[dict[str, Any]] = []
    peak_rows: list[dict[str, Any]] = []
    full_shape_rows: list[dict[str, Any]] = []
    common_shape_rows: list[dict[str, Any]] = []
    stored_v08_shape_rows: list[dict[str, str]] = []
    stored_baseline_shape_rows: list[dict[str, str]] = []
    stored_v07_shape_rows: list[dict[str, str]] = []
    per_base_support_rows: list[dict[str, Any]] = []
    base_global_rows: list[dict[str, Any]] = []
    area_diagnostic_rows: list[dict[str, Any]] = []
    extrapolation_rows: list[dict[str, Any]] = []

    for base_id in base_ids:
        oot_row = oot_by_base[base_id]
        actual_rows = v08_daily[base_id]
        baseline_rows = baseline_daily[base_id]
        dates = [date.fromisoformat(row["date"]) for row in actual_rows]
        actual = [decimal_value(row["actual_quantity_kg"], "actual_daily") for row in actual_rows]
        v08_values = [
            decimal_value(row["predicted_daily_quantity_kg"], "v08_daily") for row in actual_rows
        ]
        baseline_values = [
            decimal_value(row["predicted_daily_quantity_kg"], "baseline_daily")
            for row in baseline_rows
        ]
        if [row["date"] for row in actual_rows] != [row["date"] for row in baseline_rows]:
            raise S9DiagnosisError(f"BASELINE_V08_DATES_DIFFER:{base_id}")
        if [row["actual_quantity_kg"] for row in actual_rows] != [
            row["actual_quantity_kg"] for row in baseline_rows
        ]:
            raise S9DiagnosisError(f"ACTUAL_LABEL_PARITY_FAILED:{base_id}")
        actual_total = decimal_value(oot_row["actual_season_total_quantity_kg"], "oot_actual_total")
        if sum(actual, Decimal(0)) != actual_total:
            raise S9DiagnosisError(f"OOT_DAILY_ACTUAL_TOTAL_MISMATCH:{base_id}")
        v08_total = decimal_value(v08_totals[base_id]["predicted_season_total_kg"], "v08_total")
        baseline_total = decimal_value(
            baseline_totals[base_id]["predicted_season_total_kg"], "baseline_total"
        )
        v08_daily_sum = sum(v08_values, Decimal(0))
        baseline_daily_sum = sum(baseline_values, Decimal(0))
        if v08_daily_sum != v08_total or baseline_daily_sum != baseline_total:
            raise S9DiagnosisError(f"FROZEN_TOTAL_DAILY_RECONCILIATION_FAILED:{base_id}")
        actual_total_by_base[base_id] = actual_total
        v08_sum_by_base[base_id] = v08_total
        baseline_sum_by_base[base_id] = baseline_total
        shares = diagnose_curves(actual, v08_values)
        actual_shares = shares["actual_share"]
        v08_shares = shares["predicted_share"]
        scale_only = shares["scale_only"]
        shape_only = shares["shape_only"]
        baseline_shares = normalized_shares(baseline_values)
        v08_frozen_shares = [
            decimal_value(row["predicted_share"], "v08_share") for row in actual_rows
        ]
        baseline_frozen_shares = [
            decimal_value(row["predicted_share"], "baseline_share") for row in baseline_rows
        ]
        stored_v08_shape_rows.extend(actual_rows)
        stored_baseline_shape_rows.extend(baseline_rows)
        if v08_frozen_shares != baseline_frozen_shares:
            # Determine exact shared Stage-B profile from its canonical stored shares.
            shape_parity = False
        else:
            shape_parity = True
        v08_obs = error_metrics(actual, v08_values)
        scale_metric = error_metrics(actual, scale_only)
        shape_metric = error_metrics(actual, shape_only)
        baseline_obs = error_metrics(actual, baseline_values)
        actual_peak_date, actual_peak_qty = _peak(dates, actual)
        predicted_peak_date, predicted_peak_qty = _peak(dates, v08_values)
        scale_peak_date, scale_peak_qty = _peak(dates, scale_only)
        shape_peak_date, shape_peak_qty = _peak(dates, shape_only)
        actual_r7_start, actual_r7_end, actual_r7_qty = _rolling7(dates, actual)
        predicted_r7_start, predicted_r7_end, predicted_r7_qty = _rolling7(dates, v08_values)
        scale_r7_start, scale_r7_end, scale_r7_qty = _rolling7(dates, scale_only)
        shape_r7_start, shape_r7_end, shape_r7_qty = _rolling7(dates, shape_only)
        support = support_by_base[base_id]
        area_mu = decimal_value(oot_row["area_mu"], "oot_area")
        model_yield = decimal_value(
            model_yields.get(base_id, global_yield), "model_base_or_fallback_yield"
        )
        global_deviation = (model_yield / global_yield) - Decimal(1)
        model_error = v08_total - actual_total
        actual_yield = decimal_value(oot_row["actual_yield_kg_per_mu"], "oot_yield")
        if area_mu <= area_cut_low:
            area_stratum = "SMALL_TRAINING_AREA_TERTILE"
        elif area_mu <= area_cut_high:
            area_stratum = "MEDIUM_TRAINING_AREA_TERTILE"
        else:
            area_stratum = "LARGE_TRAINING_AREA_TERTILE"
        area_status = area_audit[base_id]["area_extrapolation_status"]
        if area_status not in {"IN_RANGE", "LOW_EXTRAPOLATION", "HIGH_EXTRAPOLATION"}:
            raise S9DiagnosisError(f"UNKNOWN_AREA_EXTRAPOLATION_STATUS:{base_id}")
        yield_status = (
            "OUTSIDE_TRAIN_YIELD_RANGE"
            if actual_yield < train_yield_min or actual_yield > train_yield_max
            else "IN_TRAIN_YIELD_RANGE"
        )
        base_diag = {
            "base_id": base_id,
            "canonical_base_name": oot_row["canonical_base_name"],
            "actual_total_kg": actual_total,
            "v08_predicted_total_kg": v08_total,
            "total_abs_error_kg": abs(model_error),
            "total_ape": abs(model_error) / actual_total,
            "observed_daily_wape": decimal_value(v08_obs["wape"], "observed_wape"),
            "scale_only_daily_wape": decimal_value(scale_metric["wape"], "scale_wape"),
            "shape_only_daily_wape": decimal_value(shape_metric["wape"], "shape_wape"),
            "observed_daily_mae": decimal_value(v08_obs["mae"], "observed_mae"),
            "scale_only_daily_mae": decimal_value(scale_metric["mae"], "scale_mae"),
            "shape_only_daily_mae": decimal_value(shape_metric["mae"], "shape_mae"),
            "normalized_shape_l1": shares["shape_l1"],
            "normalized_shape_mae": shares["shape_mae"],
            "max_cumulative_share_deviation": shares["max_cumulative_share_deviation"],
            "actual_peak_date": actual_peak_date,
            "predicted_peak_date": predicted_peak_date,
            "shape_only_peak_date": shape_peak_date,
            "scale_only_peak_date": scale_peak_date,
            "actual_rolling7_start": actual_r7_start,
            "predicted_rolling7_start": predicted_r7_start,
            "shape_only_rolling7_start": shape_r7_start,
            "scale_only_rolling7_start": scale_r7_start,
            "train_support_count_for_base": support,
            "area_mu": area_mu,
            "area_range_status": area_status,
            "area_stratum": area_stratum,
            "actual_yield_kg_per_mu": actual_yield,
            "yield_range_status": yield_status,
            "base_specific_or_fallback_yield": model_yield,
            "base_vs_global_yield_deviation": global_deviation,
            "prediction_basis": v08_totals[base_id].get("prediction_basis", ""),
            "baseline_daily_wape": decimal_value(baseline_obs["wape"], "baseline_daily_wape"),
            "baseline_shape_l1": sum(
                (abs(a - b) for a, b in zip(actual_shares, baseline_shares, strict=True)),
                Decimal(0),
            ),
            "baseline_v08_frozen_shape_parity": shape_parity,
            "actual_peak_quantity_kg": actual_peak_qty,
            "predicted_peak_quantity_kg": predicted_peak_qty,
            "shape_only_peak_quantity_kg": shape_peak_qty,
            "scale_only_peak_quantity_kg": scale_peak_qty,
            "actual_rolling7_quantity_kg": actual_r7_qty,
            "predicted_rolling7_quantity_kg": predicted_r7_qty,
            "shape_only_rolling7_quantity_kg": shape_r7_qty,
            "scale_only_rolling7_quantity_kg": scale_r7_qty,
            "shape_only_peak_date_error_days": abs((shape_peak_date - actual_peak_date).days),
            "predicted_peak_date_error_days": abs((predicted_peak_date - actual_peak_date).days),
            "shape_only_rolling7_start_error_days": abs((shape_r7_start - actual_r7_start).days),
            "predicted_rolling7_start_error_days": abs((predicted_r7_start - actual_r7_start).days),
            "shape_only_peak_quantity_abs_error_kg": abs(shape_peak_qty - actual_peak_qty),
            "shape_only_rolling7_abs_error_kg": abs(shape_r7_qty - actual_r7_qty),
            "scale_only_peak_quantity_abs_error_kg": abs(scale_peak_qty - actual_peak_qty),
            "scale_only_rolling7_abs_error_kg": abs(scale_r7_qty - actual_r7_qty),
        }
        diagnosis[base_id] = base_diag
        for index, day in enumerate(dates):
            counter_rows.append(
                {
                    "base_id": base_id,
                    "canonical_base_name": oot_row["canonical_base_name"],
                    "date": day.isoformat(),
                    "actual_quantity_kg": actual[index],
                    "actual_share": actual_shares[index],
                    "v08_predicted_quantity_kg": v08_values[index],
                    "v08_predicted_share": v08_shares[index],
                    "scale_only_quantity_kg": scale_only[index],
                    "shape_only_quantity_kg": shape_only[index],
                }
            )
        full_shape_rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": oot_row["canonical_base_name"],
                "actual_total_kg": actual_total,
                "v08_predicted_total_kg": v08_total,
                "baseline_predicted_total_kg": baseline_total,
                "v08_observed_daily_wape": base_diag["observed_daily_wape"],
                "v08_scale_only_daily_wape": base_diag["scale_only_daily_wape"],
                "v08_shape_only_daily_wape": base_diag["shape_only_daily_wape"],
                "v08_normalized_shape_l1": base_diag["normalized_shape_l1"],
                "baseline_normalized_shape_l1": base_diag["baseline_shape_l1"],
                "baseline_v08_frozen_shape_parity": shape_parity,
                "max_cumulative_share_deviation": base_diag["max_cumulative_share_deviation"],
                "train_support_count": support,
                "area_stratum": area_stratum,
                "area_extrapolation_status": area_status,
                "actual_yield_range_status": yield_status,
            }
        )
        per_base_support_rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": oot_row["canonical_base_name"],
                "train_support_count": support,
                "support_stratum": "0" if support == 0 else "1" if support == 1 else "2_PLUS",
                "area_mu": area_mu,
                "actual_total_kg": actual_total,
                "v08_predicted_total_kg": v08_total,
                "total_abs_error_kg": abs(model_error),
                "total_ape": base_diag["total_ape"],
                "total_bias_kg": model_error,
                "normalized_shape_l1": base_diag["normalized_shape_l1"],
                "shape_only_daily_wape": base_diag["shape_only_daily_wape"],
                "shape_only_peak_date_error_days": base_diag["shape_only_peak_date_error_days"],
                "shape_only_rolling7_start_error_days": base_diag[
                    "shape_only_rolling7_start_error_days"
                ],
            }
        )
        base_global_rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": oot_row["canonical_base_name"],
                "training_season_support_count": support,
                "historical_base_specific_yield_kg_per_mu": decimal_value(
                    model_yields[base_id], "base_yield"
                )
                if base_id in model_yields
                else None,
                "pooled_training_yield_kg_per_mu": global_yield,
                "model_estimated_yield_kg_per_mu": model_yield,
                "yield_source": "BASE_SPECIFIC_TRAINING_MEAN"
                if base_id in model_yields
                else "POOLED_TRAINING_YIELD_FALLBACK",
                "base_specific_yield_deviation_from_global": global_deviation
                if base_id in model_yields
                else None,
                "oot_actual_yield_kg_per_mu_diagnostic_only": actual_yield,
                "oot_actual_yield_range_status": yield_status,
            }
        )
        area_diagnostic_rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": oot_row["canonical_base_name"],
                "area_mu": area_mu,
                "training_row_area_p33_cut_mu": area_cut_low,
                "training_row_area_p67_cut_mu": area_cut_high,
                "training_area_stratum": area_stratum,
                "train_support_count": support,
                "actual_total_kg": actual_total,
                "v08_predicted_total_kg": v08_total,
                "season_total_abs_error_kg": abs(model_error),
                "season_total_ape": base_diag["total_ape"],
                "area_extrapolation_status": area_status,
                "actual_yield_range_status": yield_status,
            }
        )
        extrapolation_rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": oot_row["canonical_base_name"],
                "area_mu": area_mu,
                "area_extrapolation_status": area_status,
                "actual_yield_kg_per_mu_diagnostic_only": actual_yield,
                "train_yield_min_kg_per_mu": train_yield_min,
                "train_yield_max_kg_per_mu": train_yield_max,
                "actual_yield_extrapolation_status": yield_status,
                "season_total_abs_error_kg": abs(model_error),
                "season_total_ape": base_diag["total_ape"],
                "normalized_shape_l1": base_diag["normalized_shape_l1"],
                "included_in_oot": True,
            }
        )
        peak_rows.append(
            {
                "base_id": base_id,
                "canonical_base_name": oot_row["canonical_base_name"],
                "actual_peak_date": actual_peak_date,
                "v08_peak_date": predicted_peak_date,
                "scale_only_peak_date": scale_peak_date,
                "shape_only_peak_date": shape_peak_date,
                "actual_peak_quantity_kg": actual_peak_qty,
                "v08_peak_quantity_kg": predicted_peak_qty,
                "scale_only_peak_quantity_kg": scale_peak_qty,
                "shape_only_peak_quantity_kg": shape_peak_qty,
                "v08_peak_date_error_days": base_diag["predicted_peak_date_error_days"],
                "shape_only_peak_date_error_days": base_diag["shape_only_peak_date_error_days"],
                "actual_rolling7_start": actual_r7_start,
                "v08_rolling7_start": predicted_r7_start,
                "scale_only_rolling7_start": scale_r7_start,
                "shape_only_rolling7_start": shape_r7_start,
                "actual_rolling7_quantity_kg": actual_r7_qty,
                "v08_rolling7_quantity_kg": predicted_r7_qty,
                "scale_only_rolling7_quantity_kg": scale_r7_qty,
                "shape_only_rolling7_quantity_kg": shape_r7_qty,
                "v08_rolling7_start_error_days": base_diag["predicted_rolling7_start_error_days"],
                "shape_only_rolling7_start_error_days": base_diag[
                    "shape_only_rolling7_start_error_days"
                ],
                "shape_only_peak_quantity_abs_error_kg": base_diag[
                    "shape_only_peak_quantity_abs_error_kg"
                ],
                "shape_only_rolling7_abs_error_kg": base_diag["shape_only_rolling7_abs_error_kg"],
            }
        )

    if len(common_ids) != 30:
        raise S9DiagnosisError("COMMON_COMPARATOR_COUNT_NOT_30")
    for base_id in common_ids:
        actual_rows = v08_daily[base_id]
        v07_rows = v07_daily[base_id]
        if [row["date"] for row in actual_rows] != [row["date"] for row in v07_rows]:
            raise S9DiagnosisError(f"V07_COMMON30_DATE_MISMATCH:{base_id}")
        actual = [decimal_value(row["actual_quantity_kg"], "actual") for row in actual_rows]
        v08_values = [
            decimal_value(row["predicted_daily_quantity_kg"], "v08_predicted")
            for row in actual_rows
        ]
        baseline_values = [
            decimal_value(row["predicted_daily_quantity_kg"], "baseline_predicted")
            for row in baseline_daily[base_id]
        ]
        v07_values = [
            decimal_value(row["predicted_daily_quantity_kg"], "v07_predicted") for row in v07_rows
        ]
        actual_shares = normalized_shares(actual)
        model_shares = {
            "baseline": normalized_shares(baseline_values),
            "v07": normalized_shares(v07_values),
            "v08": normalized_shares(v08_values),
        }
        entry: dict[str, Any] = {
            "base_id": base_id,
            "canonical_base_name": oot_by_base[base_id]["canonical_base_name"],
            "actual_total_kg": sum(actual, Decimal(0)),
            "train_support_count": diagnosis[base_id]["train_support_count_for_base"],
        }
        for model_name, predicted_values in (
            ("baseline", baseline_values),
            ("v07", v07_values),
            ("v08", v08_values),
        ):
            share_values = model_shares[model_name]
            shape_l1 = sum(
                (abs(a - p) for a, p in zip(actual_shares, share_values, strict=True)), Decimal(0)
            )
            shape_only = counterfactual_curve(sum(actual, Decimal(0)), share_values)
            observed = error_metrics(actual, predicted_values)
            shape_error = error_metrics(actual, shape_only)
            entry[f"{model_name}_observed_daily_wape"] = decimal_value(
                observed["wape"], "daily_wape"
            )
            entry[f"{model_name}_normalized_shape_l1"] = shape_l1
            entry[f"{model_name}_shape_only_daily_wape"] = decimal_value(
                shape_error["wape"], "shape_wape"
            )
            if model_name == "v07":
                stored_v07_shape_rows.extend(v07_rows)
        common_shape_rows.append(entry)

    # Confirm all three frozen headline WAPEs from the immutable prediction files.
    actual_totals = [actual_total_by_base[base_id] for base_id in base_ids]
    v08_total_values = [v08_sum_by_base[base_id] for base_id in base_ids]
    baseline_total_values = [baseline_sum_by_base[base_id] for base_id in base_ids]
    full_total_v08 = error_metrics(actual_totals, v08_total_values)
    full_total_baseline = error_metrics(actual_totals, baseline_total_values)
    full_daily_actual = [
        decimal_value(row["actual_quantity_kg"], "actual")
        for base in base_ids
        for row in v08_daily[base]
    ]
    full_daily_v08 = [
        decimal_value(row["predicted_daily_quantity_kg"], "pred_v08")
        for base in base_ids
        for row in v08_daily[base]
    ]
    full_daily_baseline = [
        decimal_value(row["predicted_daily_quantity_kg"], "pred_baseline")
        for base in base_ids
        for row in baseline_daily[base]
    ]
    full_daily_v08_metrics = error_metrics(full_daily_actual, full_daily_v08)
    full_daily_baseline_metrics = error_metrics(full_daily_actual, full_daily_baseline)
    common_actual_totals = [actual_total_by_base[base] for base in common_ids]
    common_v07_totals = [
        decimal_value(v07_totals[base]["predicted_season_total_kg"], "v07_total")
        for base in common_ids
    ]
    common_v08_totals = [v08_sum_by_base[base] for base in common_ids]
    common_total_v07 = error_metrics(common_actual_totals, common_v07_totals)
    common_total_v08 = error_metrics(common_actual_totals, common_v08_totals)
    common_daily_actual = [
        decimal_value(row["actual_quantity_kg"], "actual")
        for base in common_ids
        for row in v08_daily[base]
    ]
    common_daily_v07 = [
        decimal_value(row["predicted_daily_quantity_kg"], "v07")
        for base in common_ids
        for row in v07_daily[base]
    ]
    common_daily_v08 = [
        decimal_value(row["predicted_daily_quantity_kg"], "v08")
        for base in common_ids
        for row in v08_daily[base]
    ]
    common_daily_v07_metrics = error_metrics(common_daily_actual, common_daily_v07)
    common_daily_v08_metrics = error_metrics(common_daily_actual, common_daily_v08)
    frozen = config["frozen_s8_metrics"]
    parity_pairs = [
        (
            full_total_baseline["wape"],
            frozen["baseline_season_total_wape_full39"],
            "baseline_total_full39",
        ),
        (full_total_v08["wape"], frozen["v08_season_total_wape_full39"], "v08_total_full39"),
        (
            full_daily_baseline_metrics["wape"],
            frozen["baseline_daily_wape_full39"],
            "baseline_daily_full39",
        ),
        (full_daily_v08_metrics["wape"], frozen["v08_daily_wape_full39"], "v08_daily_full39"),
        (common_total_v07["wape"], frozen["v07_season_total_wape_common30"], "v07_total_common30"),
        (common_daily_v07_metrics["wape"], frozen["v07_daily_wape_common30"], "v07_daily_common30"),
    ]
    for actual_metric, expected_metric, label in parity_pairs:
        if abs(
            decimal_value(actual_metric, label) - decimal_value(expected_metric, label)
        ) > Decimal("1e-27"):
            raise S9DiagnosisError(f"S8_PRIMARY_METRIC_PARITY_FAILED:{label}")

    # Same Stage-B normalized profile is verified from stored S8 shares (pre-quantity rounding).
    v08_share_hash = _source_share_hash(stored_v08_shape_rows)
    baseline_share_hash = _source_share_hash(stored_baseline_shape_rows)
    shape_parity_all = v08_share_hash == baseline_share_hash
    base_share_parity_count = sum(
        1 for row in diagnosis.values() if row["baseline_v08_frozen_shape_parity"]
    )
    if shape_parity_all != (base_share_parity_count == 39):
        raise S9DiagnosisError("FROZEN_SHAPE_PARITY_INTERNAL_MISMATCH")

    base_rows = [diagnosis[base] for base in base_ids]
    scale_daily_all: list[Decimal] = []
    shape_daily_all: list[Decimal] = []
    actual_daily_all: list[Decimal] = []
    v08_daily_all: list[Decimal] = []
    for row in counter_rows:
        actual_daily_all.append(decimal_value(row["actual_quantity_kg"], "actual"))
        v08_daily_all.append(decimal_value(row["v08_predicted_quantity_kg"], "v08"))
        scale_daily_all.append(decimal_value(row["scale_only_quantity_kg"], "scale"))
        shape_daily_all.append(decimal_value(row["shape_only_quantity_kg"], "shape"))
    full_observed_daily = error_metrics(actual_daily_all, v08_daily_all)
    full_scale_daily = error_metrics(actual_daily_all, scale_daily_all)
    full_shape_daily = error_metrics(actual_daily_all, shape_daily_all)

    shape_l1_values = [row["normalized_shape_l1"] for row in base_rows]
    cumulative_values = [row["max_cumulative_share_deviation"] for row in base_rows]
    total_ape_values = [row["total_ape"] for row in base_rows]
    base_specific_deviations = [
        row["base_specific_yield_deviation_from_global"]
        for row in base_global_rows
        if row["historical_base_specific_yield_kg_per_mu"] is not None
    ]
    yield_variability_rows: list[dict[str, Any]] = []
    two_season_cv: list[Decimal] = []
    two_season_spread: list[Decimal] = []
    for base_id, values in sorted(training_by_base.items()):
        season_yields = sorted(
            (row["season"], decimal_value(row["yield_kg_per_mu"], "train_yield")) for row in values
        )
        relative_spread: Decimal | None = None
        cv_population: Decimal | None = None
        if len(season_yields) == 2:
            mean_yield = (season_yields[0][1] + season_yields[1][1]) / Decimal(2)
            relative_spread = abs(season_yields[1][1] - season_yields[0][1]) / mean_yield
            cv_population = relative_spread / Decimal(2)
            two_season_cv.append(cv_population)
            two_season_spread.append(relative_spread)
        yield_variability_rows.append(
            {
                "base_id": base_id,
                "training_support_count": len(season_yields),
                "season_1": season_yields[0][0],
                "yield_1_kg_per_mu": season_yields[0][1],
                "season_2": season_yields[1][0] if len(season_yields) > 1 else None,
                "yield_2_kg_per_mu": season_yields[1][1] if len(season_yields) > 1 else None,
                "two_season_relative_spread": relative_spread,
                "two_season_population_cv": cv_population,
                "interpretation": "TWO_SEASON_PAIR_ONLY_NOT_RELIABLE_VARIANCE_ESTIMATE"
                if len(season_yields) == 2
                else "ONE_SEASON_NO_WITHIN_BASE_VARIABILITY_ESTIMATE",
            }
        )

    support_counts = {
        "0": sum(count == 0 for count in support_by_base.values()),
        "1": sum(count == 1 for count in support_by_base.values()),
        "2_plus": sum(count >= 2 for count in support_by_base.values()),
    }
    strata_rows: list[dict[str, Any]] = []
    strata_summary: dict[str, Any] = {}
    for key in ("0", "1", "2_plus"):
        if key == "0":
            selected = [row for row in base_rows if row["train_support_count_for_base"] == 0]
        elif key == "1":
            selected = [row for row in base_rows if row["train_support_count_for_base"] == 1]
        else:
            selected = [row for row in base_rows if row["train_support_count_for_base"] >= 2]
        if selected:
            totals = error_metrics(
                [row["actual_total_kg"] for row in selected],
                [row["v08_predicted_total_kg"] for row in selected],
            )
            shape_daily_wape = sum(
                (row["shape_only_daily_wape"] * row["actual_total_kg"] for row in selected),
                Decimal(0),
            ) / sum((row["actual_total_kg"] for row in selected), Decimal(0))
            strata_summary[key] = {
                "n": len(selected),
                "season_total_wape": totals["wape"],
                "season_total_mae_kg": totals["mae"],
                "season_total_bias_kg": totals["bias_mean_predicted_minus_actual"],
                "normalized_shape_l1_mean": decimal_text(
                    _average([row["normalized_shape_l1"] for row in selected]) or Decimal(0)
                ),
                "normalized_shape_l1_median": decimal_text(
                    percentile([row["normalized_shape_l1"] for row in selected], Decimal("0.5"))
                    or Decimal(0)
                ),
                "shape_only_daily_wape_actual_weighted_base_wape": decimal_text(shape_daily_wape),
                "shape_only_peak_date_mae_days": decimal_text(
                    _average([Decimal(row["shape_only_peak_date_error_days"]) for row in selected])
                    or Decimal(0)
                ),
                "shape_only_rolling7_start_mae_days": decimal_text(
                    _average(
                        [Decimal(row["shape_only_rolling7_start_error_days"]) for row in selected]
                    )
                    or Decimal(0)
                ),
            }
            strata_rows.append({"support_stratum": key, **strata_summary[key]})
        else:
            strata_summary[key] = {"n": 0, "status": "NOT_COMPUTABLE_EMPTY_STRATUM"}
            strata_rows.append(
                {"support_stratum": key, "n": 0, "status": "NOT_COMPUTABLE_EMPTY_STRATUM"}
            )

    # Area-strata and area/yield-extrapolation tables are grouped only after fixed cutpoints.
    area_strata_summary: dict[str, Any] = {}
    extrap_summary: dict[str, Any] = {}
    group_specs: list[tuple[str, list[str], dict[str, Any]]] = [
        (
            "area_stratum",
            [
                "SMALL_TRAINING_AREA_TERTILE",
                "MEDIUM_TRAINING_AREA_TERTILE",
                "LARGE_TRAINING_AREA_TERTILE",
            ],
            area_strata_summary,
        ),
        (
            "area_range_status",
            ["IN_RANGE", "LOW_EXTRAPOLATION", "HIGH_EXTRAPOLATION"],
            extrap_summary,
        ),
    ]
    for field, categories, dest in group_specs:
        for category in categories:
            selected = [row for row in base_rows if row[field] == category]
            total_metrics = (
                error_metrics(
                    [row["actual_total_kg"] for row in selected],
                    [row["v08_predicted_total_kg"] for row in selected],
                )
                if selected
                else None
            )
            shape_metrics = (
                error_metrics(
                    [
                        decimal_value(day["actual_quantity_kg"], "actual")
                        for day in counter_rows
                        if day["base_id"] in {row["base_id"] for row in selected}
                    ],
                    [
                        decimal_value(day["shape_only_quantity_kg"], "shape")
                        for day in counter_rows
                        if day["base_id"] in {row["base_id"] for row in selected}
                    ],
                )
                if selected
                else None
            )
            dest[category] = {
                "n": len(selected),
                "season_total_wape": total_metrics["wape"] if total_metrics else None,
                "season_total_mae_kg": total_metrics["mae"] if total_metrics else None,
                "shape_only_daily_wape": shape_metrics["wape"] if shape_metrics else None,
                "normalized_shape_l1_mean": decimal_text(
                    _average([row["normalized_shape_l1"] for row in selected]) or Decimal(0)
                )
                if selected
                else None,
            }
    yield_outside = [
        row
        for row in extrapolation_rows
        if row["actual_yield_extrapolation_status"] == "OUTSIDE_TRAIN_YIELD_RANGE"
    ]
    extrap_summary["ACTUAL_YIELD_OUTSIDE_TRAIN_RANGE"] = {
        "n": len(yield_outside),
        "base_ids": [row["base_id"] for row in yield_outside],
        "retained_in_full_oot": True,
        "season_total_wape": error_metrics(
            [diagnosis[row["base_id"]]["actual_total_kg"] for row in yield_outside],
            [diagnosis[row["base_id"]]["v08_predicted_total_kg"] for row in yield_outside],
        )["wape"]
        if yield_outside
        else None,
    }

    full_baseline_shape_l1 = [row["baseline_shape_l1"] for row in base_rows]
    v07_common_shape_l1 = [
        decimal_value(row["v07_normalized_shape_l1"], "v07_shape_l1") for row in common_shape_rows
    ]
    # Recompute common30 pooled shape-only WAPE at day grain, not by averaging Base WAPEs.
    common30_actual_daily: list[Decimal] = []
    common30_v07_shape_daily: list[Decimal] = []
    common30_v08_shape_daily: list[Decimal] = []
    for base_id in common_ids:
        actual = [decimal_value(row["actual_quantity_kg"], "actual") for row in v08_daily[base_id]]
        actual_total = sum(actual, Decimal(0))
        actual_shares = normalized_shares(actual)
        for model_name, model_rows in (("v07", v07_daily[base_id]), ("v08", v08_daily[base_id])):
            pred = [
                decimal_value(row["predicted_daily_quantity_kg"], model_name) for row in model_rows
            ]
            pred_shares = normalized_shares(pred)
            curve = counterfactual_curve(actual_total, pred_shares)
            if model_name == "v07":
                common30_v07_shape_daily.extend(curve)
            else:
                common30_v08_shape_daily.extend(curve)
        common30_actual_daily.extend(actual)
    common30_v07_shape_metric = error_metrics(common30_actual_daily, common30_v07_shape_daily)
    common30_v08_shape_metric = error_metrics(common30_actual_daily, common30_v08_shape_daily)

    baseline_stage_b_parity = shape_parity_all
    baseline_shape_only_wape = full_shape_daily["wape"] if baseline_stage_b_parity else None
    baseline_shape_l1_distribution = _format_distribution(full_baseline_shape_l1)
    v07_share_hash = _source_share_hash(stored_v07_shape_rows)
    for base_id in common_ids:
        actual_rows = v08_daily[base_id]
        v08_values = [
            decimal_value(row["predicted_daily_quantity_kg"], "v08") for row in actual_rows
        ]
        base_diag = diagnosis[base_id]
        common_shape_rows[common_ids.index(base_id)].update(
            {
                "v08_full39_normalized_shape_l1": base_diag["normalized_shape_l1"],
                "v08_full39_shape_only_daily_wape": base_diag["shape_only_daily_wape"],
                "baseline_full39_normalized_shape_l1": base_diag["baseline_shape_l1"],
            }
        )

    # Deterministic ranking diagnostics, without combining scale and shape into a score.
    sorted_total = sorted(base_rows, key=lambda row: (-row["total_ape"], row["base_id"]))
    sorted_shape = sorted(base_rows, key=lambda row: (row["normalized_shape_l1"], row["base_id"]))
    q75_total = percentile(total_ape_values, Decimal("0.75"))
    q25_shape = percentile(shape_l1_values, Decimal("0.25"))
    q25_total = percentile(total_ape_values, Decimal("0.25"))
    q75_shape = percentile(shape_l1_values, Decimal("0.75"))
    assert (
        q75_total is not None
        and q25_shape is not None
        and q25_total is not None
        and q75_shape is not None
    )
    total_bad_shape_good = [
        row["base_id"]
        for row in base_rows
        if row["total_ape"] >= q75_total and row["normalized_shape_l1"] <= q25_shape
    ]
    total_good_shape_bad = [
        row["base_id"]
        for row in base_rows
        if row["total_ape"] <= q25_total and row["normalized_shape_l1"] >= q75_shape
    ]

    v08_total_bias_sum = sum(
        (v08_sum_by_base[base] - actual_total_by_base[base] for base in base_ids), Decimal(0)
    )
    actual_grand_total = sum(actual_totals, Decimal(0))
    over_count = sum(v08_sum_by_base[base] > actual_total_by_base[base] for base in base_ids)
    under_count = sum(v08_sum_by_base[base] < actual_total_by_base[base] for base in base_ids)
    unchanged_count = len(base_ids) - over_count - under_count
    deviations = sorted(base_specific_deviations)
    two_season_cv_summary = _format_distribution(two_season_cv)
    two_season_spread_summary = _format_distribution(two_season_spread)
    support_mean = sum(
        (Decimal(row["train_support_count_for_base"]) for row in base_rows), Decimal(0)
    ) / Decimal(len(base_rows))
    baseline_v08_shape_exact = baseline_stage_b_parity
    scale_daily_wape = decimal_value(full_scale_daily["wape"], "scale_daily_wape")
    shape_daily_wape = decimal_value(full_shape_daily["wape"], "shape_daily_wape")
    # The frozen S8 comparator proves that the baseline and V0.8 share Stage B;
    # the S8 loss versus baseline is therefore attributable to Stage-A total scale.
    retain_shape: bool | str
    replace_total: bool | str
    if baseline_v08_shape_exact and decimal_value(
        full_total_v08["wape"], "v08_total_wape"
    ) > decimal_value(full_total_baseline["wape"], "baseline_total_wape"):
        primary_failure = "SEASON_TOTAL_SCALE"
        retain_shape = True
        replace_total = True
    elif scale_daily_wape > shape_daily_wape:
        primary_failure = "SEASON_TOTAL_SCALE"
        retain_shape = True
        replace_total = True
    elif shape_daily_wape > scale_daily_wape:
        primary_failure = "DAILY_SHAPE"
        retain_shape = False
        replace_total = False
    else:
        primary_failure = "INSUFFICIENT_EVIDENCE"
        retain_shape = "UNDETERMINED"
        replace_total = "UNDETERMINED"

    summary: dict[str, Any] = {
        "task_id": "V0_8_S9_SCALE_SHAPE_ERROR_DECOMPOSITION_AND_MODEL_DIAGNOSIS_R1",
        "result": "PASS_SCALE_SHAPE_DIAGNOSIS_COMPLETED",
        "s8_artifact_pinning": "PASS",
        "s8_2025_2026_status": "FROZEN_EVALUATION_BENCHMARK",
        "future_model_tuning_on_s8_results_breaks_pristine_oot": True,
        "s8_predictions_changed": False,
        "cohorts": {"full_oot_count": 39, "common_comparator_count": 30, "training_rows": 37},
        "model": {
            "model_family": model.get("model_family"),
            "base_specific_fallback_policy": model_stage_a.get("unseen_base_fallback"),
            "daily_shape_source": model.get("stage_b", {}).get("profile_method"),
            "baseline_daily_shape_source": (
                "SAME_FROZEN_TRAINING_NORMALIZED_SHAPE_AS_V0_8_FOR_DAILY_COMPARISON"
            ),
            "training_support_counts": support_counts,
            "mean_historical_season_support_per_oot_base": decimal_text(support_mean),
            "global_pooled_training_yield_kg_per_mu": decimal_text(global_yield),
        },
        "full39": {
            "observed_v08_daily_metrics": full_observed_daily,
            "scale_only_counterfactual_daily_metrics": full_scale_daily,
            "shape_only_counterfactual_daily_metrics": full_shape_daily,
            "v08_normalized_shape_l1_mean": decimal_text(_average(shape_l1_values) or Decimal(0)),
            "v08_normalized_shape_l1_median": decimal_text(
                percentile(shape_l1_values, Decimal("0.5")) or Decimal(0)
            ),
            "v08_normalized_shape_mae_mean": decimal_text(
                _average([row["normalized_shape_mae"] for row in base_rows]) or Decimal(0)
            ),
            "max_cumulative_share_deviation_mean": decimal_text(
                _average(cumulative_values) or Decimal(0)
            ),
            "max_cumulative_share_deviation_median": decimal_text(
                percentile(cumulative_values, Decimal("0.5")) or Decimal(0)
            ),
            "baseline_v08_identical_frozen_daily_shape": baseline_stage_b_parity,
            "baseline_v08_frozen_shape_hash_parity": {
                "baseline_sha256": baseline_share_hash,
                "v08_sha256": v08_share_hash,
                "equal": baseline_stage_b_parity,
                "base_count_equal": base_share_parity_count,
            },
            "baseline_shape_only_daily_wape": baseline_shape_only_wape
            if baseline_stage_b_parity
            else "NOT_APPLICABLE_DIFFERENT_SHAPE",
            "baseline_normalized_shape_l1_distribution": baseline_shape_l1_distribution,
            "season_total_v08_metrics": full_total_v08,
            "season_total_baseline_metrics": full_total_baseline,
            "total_bias_sum_kg": decimal_text(v08_total_bias_sum),
            "total_bias_ratio": decimal_text(v08_total_bias_sum / actual_grand_total),
            "overpredict_base_count": over_count,
            "underpredict_base_count": under_count,
            "unchanged_base_count": unchanged_count,
            "total_ape_vs_shape_l1_correlation": {
                "n": len(base_ids),
                "pearson": _correlation(total_ape_values, shape_l1_values),
                "spearman": _correlation(_rank(total_ape_values), _rank(shape_l1_values)),
            },
            "rank_diagnostic_cutpoints": {
                "total_ape_p25": decimal_text(q25_total),
                "total_ape_p75": decimal_text(q75_total),
                "shape_l1_p25": decimal_text(q25_shape),
                "shape_l1_p75": decimal_text(q75_shape),
            },
            "high_total_error_low_shape_error_base_ids": total_bad_shape_good,
            "low_total_error_high_shape_error_base_ids": total_good_shape_bad,
            "top_five_total_ape_base_ids": [row["base_id"] for row in sorted_total[:5]],
            "bottom_five_shape_l1_base_ids": [row["base_id"] for row in sorted_shape[:5]],
            "recomputed_frozen_s8_metrics": {
                "baseline_season_total_wape_full39": full_total_baseline["wape"],
                "v08_season_total_wape_full39": full_total_v08["wape"],
                "baseline_daily_wape_full39": full_daily_baseline_metrics["wape"],
                "v08_daily_wape_full39": full_daily_v08_metrics["wape"],
                "v07_season_total_wape_common30": common_total_v07["wape"],
                "v07_daily_wape_common30": common_daily_v07_metrics["wape"],
                "v08_season_total_wape_common30": common_total_v08["wape"],
            },
        },
        "common30": {
            "base_ids": common_ids,
            "v07_shape_only_daily_wape": common30_v07_shape_metric["wape"],
            "v08_shape_only_daily_wape": common30_v08_shape_metric["wape"],
            "v07_shape_l1_mean": decimal_text(_average(v07_common_shape_l1) or Decimal(0)),
            "v07_shape_l1_median": decimal_text(
                percentile(v07_common_shape_l1, Decimal("0.5")) or Decimal(0)
            ),
            "v08_observed_daily_wape": common_daily_v08_metrics["wape"],
            "v07_observed_daily_wape": common_daily_v07_metrics["wape"],
            "v07_frozen_share_hash": v07_share_hash,
        },
        "support_strata": strata_summary,
        "support_counts": support_counts,
        "base_specific_vs_global_yield_deviation_distribution": _format_distribution(deviations),
        "historical_two_season_yield_variability": {
            "two_season_base_count": len(two_season_cv),
            "population_cv_distribution_two_observations_only": two_season_cv_summary,
            "relative_spread_distribution_two_observations_only": two_season_spread_summary,
            "median_population_cv_two_observations_only": decimal_text(
                percentile(two_season_cv, Decimal("0.5")) or Decimal(0)
            )
            if two_season_cv
            else None,
            "median_relative_spread_two_observations_only": decimal_text(
                percentile(two_season_spread, Decimal("0.5")) or Decimal(0)
            )
            if two_season_spread
            else None,
            "interpretation": "PAIRWISE_DESCRIPTIVE_ONLY_NOT_RELIABLE_VARIANCE_ESTIMATE",
        },
        "area_strata_cutpoints": {
            "training_area_p33_mu": decimal_text(area_cut_low),
            "training_area_p67_mu": decimal_text(area_cut_high),
            "basis": "37_TRAINING_BASE_SEASON_AREA_ROWS",
        },
        "area_strata": area_strata_summary,
        "area_extrapolation_strata": extrap_summary,
        "peak_counterfactual_summary": {
            "observed_v08_peak_date_mae_days": decimal_text(
                _average([Decimal(row["predicted_peak_date_error_days"]) for row in base_rows])
                or Decimal(0)
            ),
            "shape_only_peak_date_mae_days": decimal_text(
                _average([Decimal(row["shape_only_peak_date_error_days"]) for row in base_rows])
                or Decimal(0)
            ),
            "observed_v08_rolling7_start_mae_days": decimal_text(
                _average([Decimal(row["predicted_rolling7_start_error_days"]) for row in base_rows])
                or Decimal(0)
            ),
            "shape_only_rolling7_start_mae_days": decimal_text(
                _average(
                    [Decimal(row["shape_only_rolling7_start_error_days"]) for row in base_rows]
                )
                or Decimal(0)
            ),
            "shape_only_peak_quantity_wape": error_metrics(
                [row["actual_peak_quantity_kg"] for row in base_rows],
                [row["shape_only_peak_quantity_kg"] for row in base_rows],
            )["wape"],
            "shape_only_rolling7_quantity_wape": error_metrics(
                [row["actual_rolling7_quantity_kg"] for row in base_rows],
                [row["shape_only_rolling7_quantity_kg"] for row in base_rows],
            )["wape"],
        },
        "primary_failure_mode": primary_failure,
        "retain_current_daily_shape_for_r2": retain_shape,
        "replace_season_total_model_for_r2": replace_total,
        "r2_candidate_directions": [
            "REPLACE_STAGE_A_RETAIN_STAGE_B_AS_CONTROLLED_MINIMAL_CHANGE",
            "TRAINING_ONLY_PARTIAL_POOLING_OR_SHRINKAGE_IF_SUPPORT_VARIANCE_JUSTIFIES",
            "TRAINING_ONLY_GLOBAL_YIELD_PLUS_REGULARIZED_BASE_EFFECT_IF_SAMPLE_SUPPORT_ALLOWS",
        ],
        "s8_eval_boundary": {
            "2025_2026_is_frozen_evaluation_benchmark": True,
            "future_r2_hyperparameter_tuning_may_use_2025_2026": False,
            "new_independent_unseen_oot_claim_allowed": False,
        },
        "diagnostic_caveats": [
            "Counterfactual absolute errors are independent scenarios and are not additive.",
            "Area and yield out-of-range OOT Bases remain included.",
            "No business acceptance threshold was defined; diagnosis is not production approval.",
        ],
    }

    base_diag_fields = [
        "base_id",
        "canonical_base_name",
        "actual_total_kg",
        "v08_predicted_total_kg",
        "total_abs_error_kg",
        "total_ape",
        "observed_daily_wape",
        "scale_only_daily_wape",
        "shape_only_daily_wape",
        "observed_daily_mae",
        "scale_only_daily_mae",
        "shape_only_daily_mae",
        "normalized_shape_l1",
        "normalized_shape_mae",
        "max_cumulative_share_deviation",
        "actual_peak_date",
        "predicted_peak_date",
        "shape_only_peak_date",
        "scale_only_peak_date",
        "actual_rolling7_start",
        "predicted_rolling7_start",
        "shape_only_rolling7_start",
        "scale_only_rolling7_start",
        "train_support_count_for_base",
        "area_mu",
        "area_range_status",
        "area_stratum",
        "actual_yield_kg_per_mu",
        "yield_range_status",
        "base_specific_or_fallback_yield",
        "base_vs_global_yield_deviation",
        "prediction_basis",
        "baseline_daily_wape",
        "baseline_shape_l1",
        "baseline_v08_frozen_shape_parity",
        "actual_peak_quantity_kg",
        "predicted_peak_quantity_kg",
        "shape_only_peak_quantity_kg",
        "scale_only_peak_quantity_kg",
        "actual_rolling7_quantity_kg",
        "predicted_rolling7_quantity_kg",
        "shape_only_rolling7_quantity_kg",
        "scale_only_rolling7_quantity_kg",
        "shape_only_peak_date_error_days",
        "predicted_peak_date_error_days",
        "shape_only_rolling7_start_error_days",
        "predicted_rolling7_start_error_days",
        "shape_only_peak_quantity_abs_error_kg",
        "shape_only_rolling7_abs_error_kg",
        "scale_only_peak_quantity_abs_error_kg",
        "scale_only_rolling7_abs_error_kg",
    ]
    output: dict[str, bytes] = {
        "v0-8-scale-shape-counterfactual-daily-r1.csv": csv_bytes(
            [
                "base_id",
                "canonical_base_name",
                "date",
                "actual_quantity_kg",
                "actual_share",
                "v08_predicted_quantity_kg",
                "v08_predicted_share",
                "scale_only_quantity_kg",
                "shape_only_quantity_kg",
            ],
            counter_rows,
        ),
        "scale-shape-diagnosis-by-base-r1.csv": csv_bytes(base_diag_fields, base_rows),
        "full39-shape-comparison-r1.csv": csv_bytes(list(full_shape_rows[0]), full_shape_rows),
        "common30-shape-comparison-r1.csv": csv_bytes(
            list(common_shape_rows[0]), common_shape_rows
        ),
        "training-support-by-base-r1.csv": csv_bytes(
            list(per_base_support_rows[0]), per_base_support_rows
        ),
        "training-support-error-strata-r1.csv": csv_bytes(list(strata_rows[0]), strata_rows),
        "historical-yield-variability-r1.csv": csv_bytes(
            list(yield_variability_rows[0]), yield_variability_rows
        ),
        "base-vs-global-yield-r1.csv": csv_bytes(list(base_global_rows[0]), base_global_rows),
        "area-strata-diagnosis-r1.csv": csv_bytes(
            list(area_diagnostic_rows[0]), area_diagnostic_rows
        ),
        "extrapolation-diagnosis-r1.csv": csv_bytes(
            list(extrapolation_rows[0]), extrapolation_rows
        ),
        "peak-counterfactual-diagnosis-r1.csv": csv_bytes(list(peak_rows[0]), peak_rows),
        "diagnosis-summary-r1.json": canonical_json_bytes(summary) + b"\n",
    }
    return output, {"summary": summary}


def run_diagnosis(
    *, repo_root: Path, s8_root: Path, artifact_root: Path, config_path: Path
) -> dict[str, Any]:
    config = read_json(config_path)
    pins = _validate_manifest(repo_root, s8_root, config)
    outputs, report = _build_diagnosis(s8_root=s8_root, config=config, pins=pins)
    # Recheck all private inputs immediately before writing; S8 stays immutable.
    final_pins = _validate_manifest(repo_root, s8_root, config)
    if final_pins["manifest_sha256"] != pins["manifest_sha256"]:
        raise S9DiagnosisError("BLOCKED_S8_ARTIFACT_DRIFT:DURING_DIAGNOSIS")
    if artifact_root.exists():
        raise S9DiagnosisError(f"OUTPUT_DIRECTORY_ALREADY_EXISTS:{artifact_root}")
    artifact_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(artifact_root, 0o700)
    output_hashes: dict[str, str] = {}
    for name, payload in sorted(outputs.items()):
        path = artifact_root / name
        with path.open("xb") as handle:
            handle.write(payload)
        os.chmod(path, 0o600)
        output_hashes[name] = sha256_bytes(payload)
    manifest = {
        "task_id": config["task_id"],
        "artifact_policy": {
            "directory_mode": "0700",
            "file_mode": "0600",
            "private_row_level_data": True,
        },
        "s8_pins": {
            "private_manifest_sha256": pins["manifest_sha256"],
            "repository_evidence_sha256": pins["repository_evidence_sha256"],
            "repository_config_sha256": pins["repository_config_sha256"],
            "all_59_artifact_hashes_verified": True,
            "artifacts": pins["artifact_hashes"],
        },
        "s9_config_sha256": sha256_file(config_path),
        "s9_code_sha256": sha256_file(Path(__file__)),
        "artifacts": output_hashes,
        "result": report["summary"]["result"],
    }
    manifest_payload = canonical_json_bytes(manifest) + b"\n"
    manifest_path = artifact_root / "artifact-manifest.json"
    with manifest_path.open("xb") as handle:
        handle.write(manifest_payload)
    os.chmod(manifest_path, 0o600)
    report["artifact_manifest_sha256"] = sha256_bytes(manifest_payload)
    report["artifact_hashes"] = output_hashes
    return report
