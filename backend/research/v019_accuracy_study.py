"""S4 fixed-source diagnostics and synthetic four-method experiment.

No discovery of private files, no real model fitting, no production integration.
Existing S1 arithmetic is reused without changing its PIT authorization gate.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any, cast

from backend.research import v019_accuracy_models as models
from backend.research import v019_owner_replay as owner
from backend.research import v019_research_evaluation as evaluation
from backend.research import v019_retrospective_scoring as views
from backend.research import v019_synthetic_validation as metrics
from backend.research.v019_daily_curve import (
    BASELINE_POLICY,
    CurveInput,
    DailyKg,
    canonical_bytes,
    generate_candidate,
)

S3_PINS = {
    "a/phase-a.json": "0444ee2be8acd31fe307d02f138dee4d36d70f90dc7858e1dc02335271d56ffe",
    "verify-a/phase-a-verification.json": (
        "8a2c33d8bd846095bcf2ed1d10b81014be1daa532e971febad745580082db810"
    ),
    "b/report.json": "eb69bf1d6088d523047fbd964a9c202590d5831980dd70877cff1b6c2d68b5c1",
}
LIMITS = [
    "EXPOSED_HISTORICAL_BENCHMARK; STRICT_PIT=false; NO_BLIND_HOLDOUT_AVAILABLE",
    "SOURCE_002 is recorded inbound net weight, not proven total field harvest.",
    "Historical training physical-basis equivalence and area known_at NOT_PROVEN.",
    "19032 overlapping windows are not 19032 independent samples.",
    "H7 rolling7 start error zero is structural: only one seven-day window.",
    "No full-season admission; no production accuracy or model promotion claim.",
    "Bin-mass error is a lower bound; residual is NOT a causal timing attribution.",
]


def fraction(n: Decimal, d: Decimal) -> dict[str, str | None]:
    return metrics._fraction(n, d)


def compare(
    curves: dict[str, dict[str, tuple[DailyKg, ...]]],
    actual: dict[str, tuple[DailyKg, ...]],
    members: list[dict[str, Any]],
    *,
    label_identity: str = "SYNTHETIC_FIXTURE",
    scored_at: datetime | None = None,
) -> dict[str, Any]:
    """Joint Cm across all supplied methods; no per-model favorable exclusions."""
    with localcontext(Context(prec=50)):
        return _compare(curves, actual, members, label_identity=label_identity, scored_at=scored_at)


def _compare(
    curves: dict[str, dict[str, tuple[DailyKg, ...]]],
    actual: dict[str, tuple[DailyKg, ...]],
    members: list[dict[str, Any]],
    *,
    label_identity: str,
    scored_at: datetime | None,
) -> dict[str, Any]:
    if "baseline" not in curves:
        raise ValueError("BASELINE_REQUIRED")
    if len({m["candidate_id"] for m in members}) != len(members) or any(
        m["window"] not in {"H7_PREFIX", "H15_LOCAL"} for m in members
    ):
        raise ValueError("COHORT_IDENTITY")
    groups = {w: {m: evaluation._accumulator() for m in curves} for w in ("H7_PREFIX", "H15_LOCAL")}
    failures = []
    for member in members:
        bid, start = member["base_id"], date.fromisoformat(member["target_start"])
        days = 7 if member["window"] == "H7_PREFIX" else 15
        reason = None
        errors: dict[str, dict[str, Decimal]] = {}
        total = Decimal(0)
        try:
            aa = models.window(actual.get(bid, ()), start, days)
            pp = {m: models.window(cc.get(bid, ()), start, days) for m, cc in curves.items()}
            total = sum((r.kg for r in aa), Decimal(0))
            lab = metrics.Labels(
                member["candidate_id"],
                label_identity,
                label_identity,
                aa,
                scored_at or datetime(2026, 1, 1, tzinfo=UTC),
                scored_at or datetime(2026, 1, 1, tzinfo=UTC),
                True,
            )
            for m, rr in pp.items():
                errors[m] = metrics._errors(metrics.Forecast(m, "s", "s", "s", rr), lab)
        except ValueError as exc:
            reason = (
                "INCOMPLETE_CALENDAR"
                if str(exc) == "INCOMPLETE_WINDOW"
                else "INVALID_VALUE_OR_DUPLICATE_DATE"
            )
            failures.append({"candidate_id": member["candidate_id"], "reason": reason})
        for m in curves:
            evaluation._add(
                groups[member["window"]][m],
                member,
                reason,
                total,
                {"baseline": errors.get("baseline", {}), "candidate": errors.get(m, {})},
                total > 0,
            )
    return {
        "groups": {
            w: {m: evaluation._finish(a) for m, a in mm.items()} for w, mm in groups.items()
        },
        "failures": failures,
        "candidate_count": len(members),
    }


def synthetic() -> dict[str, Any]:
    """Early-season fit -> next-season validation -> unchanged fit exposed test."""
    training = tuple(
        models.TrainingBin(
            "SYNTHETIC-A",
            date(2023, 7, 1),
            date(2023, 7, 1) + timedelta(days=7 * i),
            Decimal(2),
            (Decimal(2),) * 7,
            tuple(map(Decimal, ("1", "2", "3", "4", "5", "6", "7"))),
            "a" * 64,
        )
        for i in range(6)
    )
    fitted = models.fit(training, evaluation_start=date(2024, 7, 1), data_class="SYNTHETIC")
    studies = {}
    with localcontext(Context(prec=50)):
        for year in (2024, 2025):
            start = date(year, 7, 1)
            curves: dict[str, dict[str, tuple[DailyKg, ...]]] = {
                m: {} for m in ("baseline", "S2", "VOLUME_CALIBRATION_V1", "VOLUME_TIMING_V1")
            }
            actual, members = {}, []
            for bid, kind in (
                ("SYNTHETIC-A", "IMPROVEMENT"),
                ("SYNTHETIC-B", "DEGRADATION"),
                ("SYNTHETIC-Z", "ZERO"),
            ):
                baseline = tuple(DailyKg(start + timedelta(days=i), Decimal(2)) for i in range(21))
                curves["baseline"][bid] = baseline
                curves["S2"][bid] = generate_candidate(
                    CurveInput(
                        start,
                        start,
                        baseline[-1].day,
                        baseline,
                        "a" * 64,
                        BASELINE_POLICY,
                        "Asia/Shanghai",
                    )
                ).rows
                for m, rr in models.predict(fitted, bid, start, baseline).items():
                    curves[m][bid] = rr
                actual[bid] = tuple(
                    DailyKg(
                        r.day,
                        Decimal(i % 7 + 1)
                        if kind == "IMPROVEMENT"
                        else Decimal(2)
                        if kind == "DEGRADATION"
                        else Decimal(0),
                    )
                    for i, r in enumerate(baseline)
                )
                for days, w in ((7, "H7_PREFIX"), (15, "H15_LOCAL")):
                    for offset in range(22 - days):
                        members.append(
                            {
                                "candidate_id": f"{bid}-{year}-{days}-{offset}",
                                "base_id": bid,
                                "window": w,
                                "target_start": str(start + timedelta(days=offset)),
                            }
                        )
            result = compare(curves, actual, members)
            studies[str(year)] = {
                "role": "TEMPORAL_VALIDATION" if year == 2024 else "EXPOSED_SYNTHETIC_TEST",
                "comparison": result,
                "fit_sha256": fitted["sha256"],
                "daily": {
                    m: {
                        b: [{"date": str(r.day), "kg": str(r.kg)} for r in rr]
                        for b, rr in cc.items()
                    }
                    for m, cc in curves.items()
                },
            }
    body = {
        "data_class": "SYNTHETIC",
        "fit": fitted,
        "studies": studies,
        "parameter_selection_from_validation": False,
        "real_training": False,
    }
    return {**body, "sha256": metrics.digest(body)}


def diagnostics(report: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    actual = {(r["base_id"], r["date"]): Decimal(r["kg"]) for r in report["actual_daily"]}
    bases = {b["base_id"]: b for b in registry["bases"]}
    dates: dict[str, Any] = {}
    monthly: dict[str, Any] = {}
    totals: dict[str, Any] = {}
    zero_vs_positive: dict[str, Any] = {}
    perbase = []
    daily_rows = []
    with localcontext(Context(prec=50)):
        for bid, cc in report["daily_predictions"].items():
            predictions: dict[str, dict[str, Decimal]] = {
                m: {r["date"]: Decimal(r["kg"]) for r in rr} for m, rr in cc.items()
            }
            keys = sorted(d for b, d in actual if b == bid)
            bins: dict[int, list[str]] = defaultdict(list)
            for d in keys:
                bins[(date.fromisoformat(d) - date(2025, 7, 1)).days // 7].append(d)
            record: dict[str, Any] = {
                "base_id": bid,
                "name": bases[bid]["canonical_base_name"],
                "area_mu": bases[bid]["productive_area_mu"],
                "date_count": len(keys),
                "actual_kg": str(sum(actual[bid, d] for d in keys)),
            }
            area = Decimal(record["area_mu"])
            record["observed_period_kg_per_mu"] = str(Decimal(record["actual_kg"]) / area)
            for m, pp in predictions.items():
                pred = sum((pp[d] for d in keys), Decimal(0))
                ae = sum((abs(pp[d] - actual[bid, d]) for d in keys), Decimal(0))
                lower = sum(
                    (
                        abs(sum((pp[d] - actual[bid, d] for d in dd), Decimal(0)))
                        for dd in bins.values()
                    ),
                    Decimal(0),
                )
                assert lower <= ae
                rr = tuple(DailyKg(date.fromisoformat(d), pp[d]) for d in keys)
                record[m] = {
                    "predicted_kg": str(pred),
                    "predicted_kg_per_mu": str(pred / area),
                    "signed_bias_kg": str(pred - Decimal(record["actual_kg"])),
                    "absolute_error_kg": str(ae),
                    "bin_mass_error_lower_bound_kg": str(lower),
                    "noncausal_residual_kg": str(ae - lower),
                    "bin_bound_share": fraction(lower, ae),
                    "bin_count": len(bins),
                    "partial_bins": [i for i, dd in bins.items() if len(dd) < 7],
                    "observed_period_peaks_not_full_season": views._view(rr, actual=False),
                }
            record["actual_observed_period_peaks_not_full_season"] = views._view(
                tuple(DailyKg(date.fromisoformat(d), actual[bid, d]) for d in keys), actual=True
            )
            perbase.append(record)
            for d in keys:
                row = {
                    "base_id": bid,
                    "date": d,
                    "actual": str(actual[bid, d]),
                    **{m: str(pp[d]) for m, pp in predictions.items()},
                }
                daily_rows.append(row)
                for bucket, key in (
                    (dates, d),
                    (monthly, d[:7]),
                    (totals, "all"),
                    (zero_vs_positive, "ZERO" if actual[bid, d] == 0 else "POSITIVE"),
                ):
                    entry = bucket.setdefault(
                        key,
                        {
                            "actual": Decimal(0),
                            "rows": 0,
                            **{
                                m: {
                                    "prediction": Decimal(0),
                                    "absolute_error": Decimal(0),
                                    "signed_error": Decimal(0),
                                }
                                for m in predictions
                            },
                        },
                    )
                    entry["actual"] += actual[bid, d]
                    entry["rows"] += 1
                    for m, pp in predictions.items():
                        entry[m]["prediction"] += pp[d]
                        entry[m]["absolute_error"] += abs(pp[d] - actual[bid, d])
                        entry[m]["signed_error"] += pp[d] - actual[bid, d]
        leads: dict[str, Any] = {}
        lookup = {(r["base_id"], r["date"]): r for r in daily_rows}
        for member in report["members"]:
            if member["not_computable_reason"]:
                continue
            n = 7 if member["window"] == "H7_PREFIX" else 15
            for i in range(n):
                d = str(date.fromisoformat(member["target_start"]) + timedelta(days=i))
                r = lookup[member["base_id"], d]
                entry = leads.setdefault(f"{member['window']}:D{i + 1}", [Decimal(0)] * 3)
                entry[0] += Decimal(r["actual"])
                for j, m in enumerate(("baseline", "candidate"), 1):
                    entry[j] += abs(Decimal(r[m]) - Decimal(r["actual"]))
        leads = {
            k: {"baseline": fraction(v[1], v[0]), "candidate": fraction(v[2], v[0])}
            for k, v in leads.items()
        }
        perbase.sort(key=lambda r: (-Decimal(r["baseline"]["absolute_error_kg"]), r["base_id"]))
        macro = {
            w: {
                side: str(
                    sum(
                        Decimal(g[w]["metrics"]["DAILY_WAPE"][side]["value"])
                        for g in report["per_base"].values()
                    )
                    / len(bases)
                )
                for side in ("baseline", "candidate")
            }
            for w in report["groups"]
        }
        macro_metrics: dict[str, Any] = {}
        weighted_contributions = {}
        for w in report["groups"]:
            denominator = Decimal(
                report["groups"][w]["metrics"]["DAILY_WAPE"]["baseline"]["numerator"]
            )
            weighted_contributions[w] = sorted(
                [
                    {
                        "base_id": b,
                        "name": bases[b]["canonical_base_name"],
                        "absolute_error_kg": g[w]["metrics"]["DAILY_WAPE"]["baseline"]["numerator"],
                        "share_of_window_error": fraction(
                            Decimal(g[w]["metrics"]["DAILY_WAPE"]["baseline"]["numerator"]),
                            denominator,
                        ),
                    }
                    for b, g in report["per_base"].items()
                ],
                key=lambda x: (-Decimal(x["absolute_error_kg"]), x["base_id"]),
            )
            macro_metrics[w] = {}
            for name in metrics.ERROR_METRICS:
                macro_metrics[w][name] = {}
                for side in ("baseline", "candidate"):
                    values = [
                        g[w]["metrics"][name][side]["value"] for g in report["per_base"].values()
                    ]
                    valid = [Decimal(v) for v in values if v is not None]
                    macro_metrics[w][name][side] = {
                        **fraction(sum(valid, Decimal(0)), Decimal(len(valid))),
                        "computable_bases": len(valid),
                        "candidate_bases": len(values),
                    }
        tail = {
            k: v
            for k, v in dates.items()
            if "2026-02-23" <= k <= "2026-02-28" or "2026-04-13" <= k <= "2026-04-15"
        }
        return cast(
            dict[str, Any],
            metrics._json(
                {
                    "per_base_ranked": perbase,
                    "totals_unique_base_days": totals,
                    "months": monthly,
                    "dates": dates,
                    "focus_dates": tail,
                    "leads": leads,
                    "equal_base_wape": macro,
                    "equal_base_metrics": macro_metrics,
                    "overlap_weighted_error_contributions": weighted_contributions,
                    "zero_vs_positive": zero_vs_positive,
                    "daily": daily_rows,
                    "zero_base_days": sum(v == 0 for v in actual.values()),
                    "missing_base_days": 39 * 254 - len(actual),
                    "limits": LIMITS,
                }
            ),
        )


def chart(rows: list[dict[str, str]], title: str) -> str:
    """SVG display coordinates only use floats; all business arithmetic is Decimal."""
    fields = ("actual", "baseline", "candidate")
    maximum = max(Decimal(r[m]) for r in rows for m in fields) or Decimal(1)
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="310" viewBox="0 0 1000 310">',
        '<rect width="1000" height="310" fill="white"/>',
        f'<text x="35" y="22">{html.escape(title)}</text>',
        f'<text x="35" y="45">kg; max={maximum}; {rows[0]["date"]} — {rows[-1]["date"]}</text>',
    ]
    for m, color in zip(fields, ("#222222", "#be4b28", "#226faa"), strict=True):
        points = " ".join(
            f"{40 + 920 * i / max(1, len(rows) - 1):.2f},"
            f"{260 - 190 * float(Decimal(r[m]) / maximum):.2f}"
            for i, r in enumerate(rows)
        )
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.3"/>'
        )
    parts.append(
        '<text x="35" y="290">black=actual inbound net weight; '
        "orange=baseline; blue=S2</text></svg>"
    )
    return "\n".join(parts)


def metric_chart(comparison: dict[str, Any]) -> str:
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="650">',
        '<rect width="1000" height="650" fill="white"/>',
        '<text x="20" y="24">Baseline (orange) / S2 (blue); new real models BLOCKED</text>',
    ]
    i = 0
    for window, group in comparison["groups"].items():
        for name in ("DAILY_WAPE", "SINGLE_DAY_PEAK_DATE_MAE", "ROLLING_7DAY_PEAK_START_MAE"):
            m = group["metrics"][name]
            values = [Decimal(m[s]["value"]) for s in ("baseline", "candidate")]
            scale = max(values) or Decimal(1)
            y = 55 + i * 95
            parts.append(f'<text x="20" y="{y}">{window}: {name}</text>')
            for j, (value, color) in enumerate(zip(values, ("#be4b28", "#226faa"), strict=True)):
                parts.append(
                    f'<rect x="20" y="{y + 8 + j * 23}" width="{float(value / scale) * 650:.3f}" '
                    f'height="17" fill="{color}"/>'
                )
                parts.append(f'<text x="690" y="{y + 22 + j * 23}">{value:.9f}</text>')
            i += 1
    return "\n".join(parts + ["</svg>"])


def render(analysis: dict[str, Any], comparison: dict[str, Any]) -> dict[str, bytes]:
    total = analysis["totals_unique_base_days"]["all"]
    lower = sum(
        (
            Decimal(r["baseline"]["bin_mass_error_lower_bound_kg"])
            for r in analysis["per_base_ranked"]
        ),
        Decimal(0),
    )
    lower_share = fraction(lower, Decimal(total["baseline"]["absolute_error"]))
    under = sum(Decimal(r["baseline"]["signed_bias_kg"]) < 0 for r in analysis["per_base_ranked"])
    lines = [
        "# V0.19 S4 — real diagnostics; new model real evaluation BLOCKED",
        "",
        *LIMITS,
        "",
        "训练准入：旧训练来源与本次入库净重标签的口径、日期完整性和可用时间证据不足；未读取额外私有训练表，未用评价标签拟合。",
        "新模型已实现并完成合成时序试验；真实新模型指标为 null，不以合成结果替代。",
        "",
        "## 结论：数量低估是现有曲线处理难以修复的约束，不是已查明的业务成因",
        "",
        f"不重复 Base×日={total['rows']}；标签累计={total['actual']} kg；"
        f"基线预测={total['baseline']['prediction']} kg；{under}/39 基地累计低估。",
        f"逐日绝对误差={total['baseline']['absolute_error']} kg；分箱总量误差下界="
        f"{lower} kg，占比={lower_share['value']}。这个占比不是因果贡献率。",
        "71–73% 的 H7/H15 WAPE 是重叠窗口加权的绝对误差/标签量；"
        "不是全产季误差，不能直接和上述不重复日期累计量混算。",
        f"标签量为零的 Base×日={analysis['zero_base_days']}；"
        f"缺失 Base×日={analysis['missing_base_days']}。零量不因误差较大而剔除。",
        "",
        "## H7/H15 frozen comparison",
        "",
        "| Window / metric | Baseline | S2 |",
        "|---|---:|---:|",
    ]
    for w, g in comparison["groups"].items():
        for metric in metrics.ERROR_METRICS:
            r = g["metrics"][metric]
            lines.append(
                f"| {w} / {metric} | {r['baseline']['value']} | {r['candidate']['value']} |"
            )
    lines += [
        "",
        "## 39 Base error contribution (unique observed target dates, not full-season yield)",
        "",
        "| Base | Actual kg | Baseline kg | Signed bias kg | Absolute error kg | "
        "Bin lower bound kg | Noncausal residual kg |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in analysis["per_base_ranked"]:
        b = r["baseline"]
        lines.append(
            f"| {r['name']} | {r['actual_kg']} | {b['predicted_kg']} | {b['signed_bias_kg']} | "
            f"{b['absolute_error_kg']} | {b['bin_mass_error_lower_bound_kg']} | "
            f"{b['noncausal_residual_kg']} |"
        )
    lines += [
        "",
        "## Interpretation and next data",
        "",
        "Quantity correction cannot be learned from exposed evaluation labels in this run. "
        "Within-bin redistribution cannot repair bin-total mismatch. The residual is "
        "cancellation-sensitive, not a causal timing percentage.",
        "Feb23–28 and Apr13–15 are separately tabulated in analysis.json; the last support bin "
        "is partial. No weather/holiday/management cause is inferred from coincidence.",
        "Capacity planning may use these as uncertain conditional research scenarios only. "
        "Base is not factory; no factory/capacity mapping is inferred.",
        "Needed: exact old-source physical event dictionary; Base/member completeness and "
        "authorized zero calendar; historical effective area and known_at; "
        "mature label/available_at; "
        "frozen lawful early-training and later-validation manifests. Collect comparable weighing, "
        "phenology and management timestamps prospectively. No blind holdout presently available.",
        "",
        "## Per-Base H7/H15 paired outcomes",
        "",
        "| Base | Window | Baseline WAPE | S2 WAPE | Outcome |",
        "|---|---|---:|---:|---|",
    ]
    for r in analysis["per_base_ranked"]:
        for w, g in comparison["per_base"][r["base_id"]].items():
            m = g["metrics"]["DAILY_WAPE"]
            delta = Decimal(m["candidate"]["value"]) - Decimal(m["baseline"]["value"])
            outcome = "IMPROVED" if delta < 0 else "DEGRADED" if delta > 0 else "TIED"
            lines.append(
                f"| {r['name']} | {w} | {m['baseline']['value']} | "
                f"{m['candidate']['value']} | {outcome} |"
            )
    lines += [
        "",
        "## Focus dates and lead diagnostics",
        "",
        "```json",
        json.dumps(
            {
                "focus_dates": analysis["focus_dates"],
                "leads": analysis["leads"],
                "equal_base_wape": analysis["equal_base_wape"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "```",
    ]
    text = "\n".join(lines) + "\n"
    files = {
        "report.md": text.encode(),
        "analysis.json": canonical_bytes(analysis),
        "comparison.json": canonical_bytes(comparison),
    }
    files["metrics.svg"] = metric_chart(comparison).encode()
    images = ['<img src="metrics.svg" alt="WAPE and peak date comparison"/>']
    ranked = analysis["per_base_ranked"]
    for i in sorted({0, 1, 2, len(ranked) // 2, len(ranked) - 1}):
        b = ranked[i]
        filename = f"curve-rank-{i + 1}.svg"
        files[filename] = chart(
            [r for r in analysis["daily"] if r["base_id"] == b["base_id"]], b["name"]
        ).encode()
        images.append(
            f'<h2>{html.escape(b["name"])}</h2><img src="{filename}" alt="actual and predictions"/>'
        )
    files["report.html"] = (
        '<!doctype html><meta charset="utf-8"><title>S4 research</title>'
        "<style>body{max-width:1200px;margin:30px auto;font:15px system-ui}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%}"
        "table{border-collapse:collapse;width:100%;font-size:12px}"
        "td,th{border:1px solid #ddd;padding:5px;text-align:left}</style>"
        + "".join(images)
        + markdown_html(text)
    ).encode()
    return files


def markdown_html(text: str) -> str:
    """Small escaped renderer for this report's headings, tables and JSON block."""
    result, table, code = [], False, False
    for line in text.splitlines():
        if line.startswith("```"):
            result.append("</pre>" if code else "<pre>")
            code = not code
            continue
        if code:
            result.append(html.escape(line) + "\n")
            continue
        if line.startswith("|"):
            if not table:
                result.append("<table>")
                table = True
            if set(line.replace("|", "").replace(" ", "")) <= {"-", ":"}:
                continue
            result.append(
                "<tr>"
                + "".join(
                    "<td>" + html.escape(c.strip()) + "</td>" for c in line.strip("|").split("|")
                )
                + "</tr>"
            )
            continue
        if table:
            result.append("</table>")
            table = False
        if line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")), 3)
            result.append(f"<h{level}>" + html.escape(line.lstrip("# ")) + f"</h{level}>")
        elif line:
            result.append("<p>" + html.escape(line) + "</p>")
    if table:
        result.append("</table>")
    return "\n".join(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s3-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    a = json.loads(owner.read_bytes(args.s3_root / "a/phase-a.json", S3_PINS["a/phase-a.json"]))
    content = owner.verify_a(a, "REAL")
    v = json.loads(
        owner.read_bytes(
            args.s3_root / "verify-a/phase-a-verification.json",
            S3_PINS["verify-a/phase-a-verification.json"],
        )
    )
    if not v["payload"]["verified"] or v["payload"]["a_sha256"] != a["sha256"]:
        raise ValueError("S3_VERIFICATION_MISMATCH")
    report = json.loads(owner.read_bytes(args.s3_root / "b/report.json", S3_PINS["b/report.json"]))
    if (
        report["a_seal_sha256"] != a["sha256"]
        or report["admitted_count"] != 19032
        or report["base_count"] != 39
    ):
        raise ValueError("S3_REPORT_IDENTITY")
    analysis = diagnostics(report, content["registry"])
    comparison = {k: report[k] for k in ("groups", "per_base", "failures", "admission_inventory")}
    comparison.update(
        real_new_models_status="BLOCKED_TRAINING_SOURCE_ADMISSION",
        VOLUME_CALIBRATION_V1=None,
        VOLUME_TIMING_V1=None,
        overall_conclusion="MIXED_S2_NO_RELIABLE_NEW_MODEL_GAIN_ESTABLISHED",
        source_pins=S3_PINS,
        strict_pit=False,
        production_eligible=False,
    )
    files = render(analysis, comparison)
    files["synthetic-e2e.json"] = canonical_bytes(synthetic())
    owner.write_bundle(
        args.output,
        files,
        {
            "task": "V0_19_S4_FORECAST_ACCURACY_IMPROVEMENT_R1",
            "source_pins": S3_PINS,
            "recorded_at": datetime.now(UTC).isoformat(),
            "new_real_models_trained": False,
            "real_data_source": "SEALED_S3_REPORT_ONLY",
            "code_git_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            "new_source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), Path(models.__file__))
            },
        },
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "bases": len(analysis["per_base_ranked"]),
                "new_real_model_training": "BLOCKED",
                "synthetic": "PASS",
            }
        )
    )


if __name__ == "__main__":
    main()
