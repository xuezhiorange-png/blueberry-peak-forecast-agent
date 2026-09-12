"""R3 source audit and fail-closed shape primitives. Never imports legacy datasets.

Source XLS remains read-only. Row data and farm inventories belong in private artifacts.
An export filename is not a proof of ledger completeness or zero-harvest dates.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import numpy as np
import xlrd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from backend.app.area_yield.data import digest, fixed
from backend.app.area_yield.experiment import file_hash

HEADERS = ["时间", "链路", "农场", "分场", "品种", "果径", "入库公斤数"]


def validate_headers(headers: list[str]) -> None:
    if headers[:7] != HEADERS:
        raise ValueError("source schema mismatch")


def canonical_farm(label: str, ambiguous: list[str]) -> str:
    value = label.strip()
    if not value or value in ambiguous:
        raise ValueError("ambiguous or missing farm")
    return value


def is_summary(label: str) -> bool:
    return any(token in label for token in ("合计", "总计", "小计", "汇总"))


def season_calendar(season: str) -> list[date]:
    year = int(season[:4])
    start, end = date(year, 7, 1), date(year + 1, 7, 1)
    return [start + timedelta(days=i) for i in range((end - start).days)]


def normalize(values: list[float]) -> list[float]:
    array = np.maximum(np.asarray(values, dtype=float), 0)
    if not np.isfinite(array).all() or array.sum() <= 0:
        raise ValueError("invalid shape")
    return [float(v) for v in array / array.sum()]


def complete_curve(
    daily: dict[date, Decimal], calendar: list[date], coverage_proven: bool
) -> list[float] | None:
    if not coverage_proven or any(d not in daily for d in calendar):
        return None
    return normalize([float(daily[d]) for d in calendar])


def fit_shape(curves: list[list[float]], season: str, kind: str) -> dict[str, Any]:
    if season != "2023-2024":
        raise ValueError("train season must be 2023-2024")
    if not curves or len({len(c) for c in curves}) != 1:
        raise ValueError("empty or inconsistent curves")
    curves = [normalize(c) for c in curves]
    mean = np.asarray(curves).mean(axis=0)
    model: dict[str, Any] = {"kind": kind, "season": season, "train_hash": digest(curves)}
    if kind == "empirical":
        model["values"] = mean.tolist()
    elif kind == "ridge":
        positions = np.arange(len(mean)) / len(mean)
        x = harmonics(positions)
        scaler = StandardScaler().fit(x)
        # Fit each farm curve equally; no volume weighting or validation totals.
        tiled = np.tile(scaler.transform(x), (len(curves), 1))
        reg = Ridge(alpha=10.0, solver="svd").fit(tiled, np.asarray(curves).ravel())
        model.update(
            mean=scaler.mean_.tolist(),
            scale=scaler.scale_.tolist(),
            coefficients=reg.coef_.tolist(),
            intercept=float(reg.intercept_),
            alpha=10.0,
        )
    else:
        raise ValueError("unknown shape model")
    model["hash"] = digest(model)
    return model


def harmonics(positions: Any) -> Any:
    return np.asarray(
        [[fn(2 * np.pi * k * p) for k in (1, 2) for fn in (np.sin, np.cos)] for p in positions]
    )


def predict_shape(model: dict[str, Any], days: int) -> list[float]:
    if digest({k: v for k, v in model.items() if k != "hash"}) != model["hash"]:
        raise ValueError("shape integrity mismatch")
    if days < 7:
        raise ValueError("calendar too short")
    positions = np.arange(days) / days
    if model["kind"] == "empirical":
        values = model["values"]
        out = np.interp(positions, np.arange(len(values)) / len(values), values)
    else:
        x = (harmonics(positions) - model["mean"]) / model["scale"]
        out = x @ model["coefficients"] + model["intercept"]
    return normalize(out.tolist())


def shape_metrics(actual: list[float], predicted: list[float]) -> dict[str, Any]:
    if len(actual) != len(predicted) or len(actual) < 7:
        raise ValueError("not comparable complete calendar")
    a, p = np.asarray(normalize(actual)), np.asarray(normalize(predicted))
    ai, pi = int(a.argmax()), int(p.argmax())
    aw, pw = np.convolve(a, np.ones(7), "valid"), np.convolve(p, np.ones(7), "valid")
    aj, pj = int(aw.argmax()), int(pw.argmax())
    return {
        "actual_peak_index": ai,
        "predicted_peak_index": pi,
        "peak_date_error_days": abs(ai - pi),
        "actual_7day_start_index": aj,
        "predicted_7day_start_index": pj,
        "rolling_7day_window_shift_days": abs(aj - pj),
        "daily_share_mae": float(np.abs(a - p).mean()),
        "daily_share_wape": float(np.abs(a - p).sum() / a.sum()),
        "peak_share_error": float(abs(a[ai] - p[pi])),
        "seven_day_share_error": float(abs(aw[aj] - pw[pj])),
    }


def parse_source(path: Path, expected_hash: str) -> dict[str, Any]:
    if file_hash(path) != expected_hash:
        raise ValueError("source hash mismatch")
    workbook = xlrd.open_workbook(str(path))
    rows: list[dict[str, Any]] = []
    sheets = []
    signatures: Counter[tuple[str, ...]] = Counter()
    invalid_date_count = 0
    for sheet in workbook.sheets():
        headers = [str(v).strip() for v in sheet.row_values(0)]
        validate_headers(headers)
        sheets.append({"name": sheet.name, "row_count": sheet.nrows - 1, "column_names": headers})
        for i in range(1, sheet.nrows):
            values = sheet.row_values(i)
            if not any(v != "" for v in values):
                continue
            try:
                raw = values[0]
                day = (
                    xlrd.xldate_as_datetime(raw, workbook.datemode).date()
                    if sheet.cell_type(i, 0) == xlrd.XL_CELL_DATE
                    else date.fromisoformat(str(raw).strip()[:10])
                )
            except (ValueError, TypeError):
                invalid_date_count += 1
                day = None
            text = [str(v).strip() for v in values[1:6]]
            quantity: Decimal | None
            try:
                quantity = Decimal(str(values[6]).strip())
                if not quantity.is_finite():
                    quantity = None
            except InvalidOperation:
                quantity = None
            sig = (str(day), *text, str(quantity))
            signatures[sig] += 1
            rows.append(
                {
                    "date": day,
                    "chain": text[0],
                    "farm": text[1],
                    "subfarm": text[2],
                    "variety": text[3],
                    "size": text[4],
                    "quantity": quantity,
                    "signature": sig,
                    "sheet": sheet.name,
                    "row": i + 1,
                }
            )
    dates = [r["date"] for r in rows if r["date"] is not None]
    profile = {
        "file_name": path.name,
        "sha256": expected_hash,
        "sheets": sheets,
        "row_count": len(rows),
        "date_min": str(min(dates)),
        "date_max": str(max(dates)),
        "invalid_date_count": invalid_date_count,
        "farm_label_count": len({r["farm"] for r in rows}),
        "subfarm_label_count": len({r["subfarm"] for r in rows}),
        "variety_label_count": len({r["variety"] for r in rows}),
        "quantity_column": "入库公斤数",
        "quantity_unit": "KG",
        "null_quantity_row_count": sum(r["quantity"] is None for r in rows),
        "negative_quantity_row_count": sum(
            r["quantity"] is not None and r["quantity"] < 0 for r in rows
        ),
        "duplicate_row_count": sum(n - 1 for n in signatures.values() if n > 1),
        "duplicate_semantics": "EXACT_SEVEN_FIELD_CONTENT_NOT_UNIQUE_TRANSACTION_ID",
        "arrival_equals_harvest": True,
    }
    return {"profile": profile, "rows": rows, "signatures": signatures}


def overlap(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_rows, right_rows = left["signatures"], right["signatures"]
    common = sum((left_rows & right_rows).values())

    def totals(source: dict[str, Any], fields: tuple[str, ...]) -> dict[tuple[Any, ...], Decimal]:
        out: dict[tuple[Any, ...], Decimal] = defaultdict(Decimal)
        for row in source["rows"]:
            if row["quantity"] is not None:
                out[tuple(row[k] for k in fields)] += row["quantity"]
        return out

    same = left["profile"]["sha256"] == right["profile"]["sha256"]
    relation = (
        "IDENTICAL"
        if same
        else "SEMANTICALLY_EQUIVALENT"
        if left_rows == right_rows
        else "PARTIAL_OVERLAP"
        if common
        else "DIFFERENT_SOURCE"
    )
    daily_l, daily_r = totals(left, ("date",)), totals(right, ("date",))
    farm_l, farm_r = totals(left, ("farm",)), totals(right, ("farm",))
    return {
        "relation": relation,
        "record_multiset_overlap_count": common,
        "uploaded_only_rows": sum((left_rows - right_rows).values()),
        "repo_only_rows": sum((right_rows - left_rows).values()),
        "farm_labels_equal": set(farm_l) == set(farm_r),
        "daily_totals_equal": daily_l == daily_r,
        "farm_totals_equal": farm_l == farm_r,
        "daily_difference_count": sum(
            daily_l.get(k) != daily_r.get(k) for k in daily_l.keys() | daily_r.keys()
        ),
        "farm_difference_count": sum(
            farm_l.get(k) != farm_r.get(k) for k in farm_l.keys() | farm_r.keys()
        ),
        "canonical_source": "UPLOADED_24_25_ONLY",
        "reason": "Explicit new input; repository source comparison only, never concatenated",
        "farm_total_differences": [
            {
                "farm": k,
                "uploaded_kg": fixed(farm_l.get(k, Decimal(0))),
                "repo_kg": fixed(farm_r.get(k, Decimal(0))),
            }
            for k in sorted(farm_l.keys() | farm_r.keys())
            if farm_l.get(k) != farm_r.get(k)
        ],
    }


def inventory(source: dict[str, Any], season: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    calendar = season_calendar(season)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source["rows"]:
        groups[row["farm"]].append(row)
    result = []
    for farm, rows in sorted(groups.items()):
        daily: dict[date, Decimal] = defaultdict(Decimal)
        reasons = []
        try:
            canonical_farm(farm, config["ambiguous_farms"])
        except ValueError:
            reasons.append("AMBIGUOUS_FARM")
        if any(r["date"] is None or r["date"] not in calendar for r in rows):
            reasons.append("DATES_OUTSIDE_FIXED_SEASON_OR_INVALID")
        if any(r["quantity"] is None or r["quantity"] < 0 for r in rows):
            reasons.append("INVALID_QUANTITY")
        if any(source["signatures"][r["signature"]] > 1 for r in rows):
            reasons.append("DUPLICATE_CONTENT_WITHOUT_TRANSACTION_ID")
        if any(is_summary(r[k]) for r in rows for k in ("farm", "subfarm", "variety", "size")):
            reasons.append("SUMMARY_GRAIN_REQUIRES_DISAMBIGUATION")
        for row in rows:
            if row["date"] in calendar and row["quantity"] is not None and row["quantity"] >= 0:
                daily[row["date"]] += row["quantity"]
        # No authority entry exists for these newly uploaded complete farm seasons yet.
        coverage = any(
            a["source_hash"] == source["profile"]["sha256"]
            and a["farm"] == farm
            and a["season"] == season
            and a["start"] == str(calendar[0])
            and a["end"] == str(calendar[-1])
            for a in config["ledger_coverage_authorities"]
        )
        if not coverage:
            reasons.append("FARM_SEASON_COMPLETE_LEDGER_COVERAGE_NOT_PROVEN")
        missing = len(calendar) - len(daily)
        if missing:
            reasons.append("UNKNOWN_MISSING_DAYS_NOT_ZERO")
        dates = sorted(daily)
        result.append(
            {
                "farm": farm,
                "season": season,
                "first_date": str(dates[0]) if dates else "",
                "last_date": str(dates[-1]) if dates else "",
                "calendar_days": len(calendar),
                "observed_days": len(daily),
                "authorized_zero_days": 0,
                "unknown_missing_days": missing,
                "season_total_kg": "" if reasons else fixed(sum(daily.values(), Decimal(0))),
                "observed_partial_total_kg": fixed(sum(daily.values(), Decimal(0))),
                "completeness_status": "UNKNOWN" if reasons else "COMPLETE",
                "eligible_train": not reasons and season == "2023-2024",
                "eligible_validation": not reasons and season == "2024-2025",
                "exclusion_reason": ";".join(reasons),
            }
        )
    return result
